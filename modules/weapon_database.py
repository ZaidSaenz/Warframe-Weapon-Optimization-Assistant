from __future__ import annotations

import argparse
import bisect
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Paths / schema
# ---------------------------------------------------------------------------

RAW_WEAPONS_PATH = Path("data/raw/ExportWeapons.json")
LOCALIZATION_PATH = Path("data/raw/dict.en.json")
OUTPUT_PATH = Path("data/normalized/weapons.json")
REPORT_PATH = Path("data/reports/weapon_database_report.json")

SCHEMA_VERSION = "2.5.0"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

CATEGORY_MAP = {
    "LongGuns": "primary",
    "Pistols": "secondary",
    "Melee": "melee",
    "SentinelWeapons": "companion",
    "SpaceGuns": "archgun",
    "SpaceMelee": "archmelee",
    "OperatorAmps": "amp",
    "SpecialItems": "special",
}

# V1 population model: only these groups get percentiles.
EVALUATED_POPULATIONS = {"LongGuns", "Pistols", "Melee"}

# Small, intentional allowlist: only tags that are directly useful to a small LLM.
MECHANICAL_TAGS = {
    "PROJECTILE",
    "AOE",
    "BEAM",
    "THROWN",
    "DEPLOYABLE",
    "SINGLESHOT",
    "SECONDARYSHOTGUN",
    "SEMI_AUTO",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def clean_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    if float(value).is_integer():
        return int(value)
    return round(float(value), 6)


def localized(key: Any, dictionary: dict[str, str]) -> str | None:
    if not isinstance(key, str) or not key:
        return None
    return dictionary.get(key, key)


def friendly_damage_type(raw_key: str) -> str:
    name = raw_key.removeprefix("DT_").lower()
    aliases = {
        "fire": "heat",
        "freeze": "cold",
        "poison": "toxin",
        "explosion": "blast",
        "radiant": "void",
    }
    return aliases.get(name, name)


# damagePerShot is an indexed array in the public export.
ROOT_DAMAGE_INDEX_MAP = {
    0: "impact",
    1: "puncture",
    2: "slash",
    3: "heat",
    4: "cold",
    5: "electricity",
    6: "toxin",
    7: "blast",
    8: "radiation",
    9: "gas",
    10: "magnetic",
    11: "viral",
    12: "corrosive",
    13: "void",
    14: "tau",
    15: "true",
    16: "finisher",
}


def normalize_root_damage(value: Any) -> tuple[dict[str, int | float], list[int]]:
    """Convert root damagePerShot array into named damage types."""
    if not isinstance(value, list):
        return {}, []

    damage: dict[str, int | float] = {}
    unknown_indexes: list[int] = []

    for index, raw_value in enumerate(value):
        number = as_number(raw_value)
        if number is None or number == 0:
            continue

        key = ROOT_DAMAGE_INDEX_MAP.get(index)
        if key is None:
            key = f"unknown_index_{index}"
            unknown_indexes.append(index)

        damage[key] = clean_number(number)

    return damage, unknown_indexes


def fraction_to_percent(value: float | None) -> int | float | None:
    """
    Convert a normalized probability/fraction into a human-readable percent.

    Example:
        0.24 -> 24
        0.055 -> 5.5
    """
    if value is None:
        return None
    return clean_number(value * 100.0)


def damage_distribution_percent(
    damage: dict[str, int | float],
) -> dict[str, float]:
    """
    Return root damage composition as percentages from 0 to 100.

    Example:
        {"impact": 29, "heat": 53}
        ->
        {"impact": 35.3659, "heat": 64.6341}
    """
    total = sum(float(value) for value in damage.values())

    if total <= 0:
        return {}

    return {
        key: round(
            100.0 * float(value) / total,
            4,
        )
        for key, value in damage.items()
    }


# ---------------------------------------------------------------------------
# Riven disposition
# ---------------------------------------------------------------------------

def classify_riven(value: float | None) -> dict[str, Any] | None:
    """Convert omegaAttenuation to the game's familiar 1-5 disposition tiers."""
    if value is None:
        return None

    if value < 0.50 or value > 1.55:
        return {
            "disposition": clean_number(value),
            "warning": "unexpected_riven_disposition",
        }

    if value < 0.70:
        dots, rating, meaning = 1, "very_low", "weak_riven_stat_scaling"
    elif value < 0.90:
        dots, rating, meaning = 2, "low", "below_average_riven_stat_scaling"
    elif value <= 1.10:
        dots, rating, meaning = 3, "neutral", "average_riven_stat_scaling"
    elif value <= 1.30:
        dots, rating, meaning = 4, "high", "above_average_riven_stat_scaling"
    else:
        dots, rating, meaning = 5, "very_high", "very_strong_riven_stat_scaling"

    return {
        "disposition": clean_number(value),
        "dots": dots,
        "rating": rating,
        "meaning": meaning,
    }


# ---------------------------------------------------------------------------
# Percentiles
# ---------------------------------------------------------------------------

def relative_band(percentile: float) -> str:
    """
    Describe relative position inside a population.

    These labels never mean good/bad. They only describe the numerical
    position of a metric compared with weapons in the same population.

    The bands are deliberately symmetric around the middle range so that a
    small language model does not need to infer whether percentile 82 is
    meaningfully above average.
    """
    if percentile <= 5:
        return "exceptionally_low"
    if percentile <= 15:
        return "very_low"
    if percentile <= 30:
        return "low"
    if percentile < 70:
        return "middle_range"
    if percentile < 85:
        return "high"
    if percentile < 95:
        return "very_high"
    return "exceptionally_high"




def percentile_midrank(sorted_values: list[float], value: float) -> float:
    """
    Deterministic percentile with ties:

        percentile = 100 * (L + 0.5E) / N

    L = population values lower than the target
    E = population values exactly equal to the target
    N = population size for that metric
    """
    if not sorted_values:
        raise ValueError("Cannot calculate percentile from an empty population.")

    left = bisect.bisect_left(sorted_values, value)
    right = bisect.bisect_right(sorted_values, value)
    equal = right - left
    return 100.0 * (left + 0.5 * equal) / len(sorted_values)


# ---------------------------------------------------------------------------
# Weapon selection
# ---------------------------------------------------------------------------

def is_selectable_weapon(weapon_id: str, weapon: Any) -> tuple[bool, str | None]:
    """
    Keep the selection rule intentionally boring.

    The current export contains many non-weapon entries. Requiring `slot`, a
    category/name, and at least one core combat field reproduces the practical
    selectable-weapon population while avoiding old path/regex rule forests.
    """
    if not isinstance(weapon, dict):
        return False, "not_an_object"
    if weapon.get("slot") is None:
        return False, "missing_slot"
    if not isinstance(weapon.get("productCategory"), str):
        return False, "missing_product_category"
    if not isinstance(weapon.get("name"), str):
        return False, "missing_name"

    has_combat_data = any(
        as_number(weapon.get(field)) is not None
        for field in (
            "totalDamage",
            "criticalChance",
            "criticalMultiplier",
            "procChance",
            "fireRate",
        )
    )
    if not has_combat_data:
        return False, "missing_combat_data"

    return True, None



# ---------------------------------------------------------------------------
# Canonical identity resolution
# ---------------------------------------------------------------------------

def normalize_display_name(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def duplicate_name_penalty(
    weapon_id: str,
) -> tuple[int, list[str]]:
    """
    Conservative penalty used ONLY when multiple selectable records resolve
    to the exact same localized display name.

    This is intentionally not a global path filter.
    Legitimate player-facing weapons may live under /Types/ or use unusual slots.
    """

    lowered = weapon_id.casefold()

    penalty = 0
    reasons: list[str] = []

    if "doppelganger" in lowered:
        penalty += 100
        reasons.append("doppelganger_path")

    if "/enemies/" in lowered:
        penalty += 50
        reasons.append("enemy_path")

    if "boss" in lowered:
        penalty += 25
        reasons.append("boss_path")

    return penalty, reasons


def resolve_duplicate_names(
    selected: dict[str, dict[str, Any]],
    dictionary: dict[str, str],
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Ensure one canonical selectable record per localized weapon name.

    Rules:
    - Unique names are untouched.
    - Duplicate names are evaluated only within their collision group.
    - Internal-looking records receive a conservative penalty.
    - A single lowest-penalty candidate is kept.
    - Ties are NOT guessed: the build stops for manual review.
    """

    groups: dict[str, list[str]] = defaultdict(list)

    for weapon_id, weapon in selected.items():
        name_key = weapon.get("name")
        display_name = localized(name_key, dictionary)

        if not isinstance(display_name, str):
            continue

        groups[
            normalize_display_name(display_name)
        ].append(weapon_id)

    resolved = dict(selected)
    report: list[dict[str, Any]] = []

    for normalized_name, weapon_ids in sorted(groups.items()):

        if len(weapon_ids) <= 1:
            continue

        candidates = []

        for weapon_id in weapon_ids:
            penalty, reasons = duplicate_name_penalty(
                weapon_id
            )

            candidates.append(
                {
                    "weapon_id": weapon_id,
                    "penalty": penalty,
                    "reasons": reasons,
                }
            )

        minimum_penalty = min(
            item["penalty"]
            for item in candidates
        )

        winners = [
            item
            for item in candidates
            if item["penalty"] == minimum_penalty
        ]

        if len(winners) != 1:
            detail = json.dumps(
                candidates,
                ensure_ascii=False,
                indent=2,
            )

            raise ValueError(
                "Ambiguous duplicate localized weapon name "
                f"{normalized_name!r}. Manual review required:\n"
                f"{detail}"
            )

        kept = winners[0]["weapon_id"]

        removed = [
            item["weapon_id"]
            for item in candidates
            if item["weapon_id"] != kept
        ]

        for weapon_id in removed:
            resolved.pop(
                weapon_id,
                None,
            )

        display_name = localized(
            selected[kept].get("name"),
            dictionary,
        )

        report.append(
            {
                "name": display_name,
                "kept": kept,
                "removed": removed,
                "candidates": candidates,
            }
        )

    return resolved, report


# ---------------------------------------------------------------------------
# Behaviour-record normalization
# ---------------------------------------------------------------------------

def extract_damage_components(node: Any, path: str = "") -> list[dict[str, Any]]:
    """
    Recursively find dictionaries containing DT_* values.

    We preserve structure instead of trying to decide what a component means.
    Paths such as projectile.attack, projectile.explosiveAttack,
    chargedProjectile.attack, impact, etc. are therefore retained as facts.
    """
    components: list[dict[str, Any]] = []

    if isinstance(node, dict):
        damage = {
            friendly_damage_type(key): clean_number(float(value))
            for key, value in node.items()
            if isinstance(key, str)
            and key.startswith("DT_")
            and as_number(value) is not None
            and float(value) != 0
        }

        if damage:
            component: dict[str, Any] = {
                "path": path or "root",
                "damage": {
                    "total": clean_number(
                        sum(
                            float(v)
                            for v in damage.values()
                        )
                    ),
                    "by_type": damage,
                },
            }
            proc = as_number(node.get("procChance"))
            if proc is not None:
                component["proc_chance_raw"] = clean_number(proc)
            components.append(component)

        for key, value in node.items():
            if isinstance(value, (dict, list)):
                child_path = f"{path}.{key}" if path else str(key)
                components.extend(extract_damage_components(value, child_path))

    elif isinstance(node, list):
        for index, value in enumerate(node):
            child_path = f"{path}[{index}]" if path else f"[{index}]"
            components.extend(extract_damage_components(value, child_path))

    return components


def normalize_trigger_value(value: Any, dictionary: dict[str, str]) -> str | None:
    if not isinstance(value, str) or not value:
        return None

    # Root trigger is commonly already AUTO/SEMI/BURST/etc. Behaviour stateName
    # is commonly a localization key. Resolve either form into comparable text.
    resolved = localized(value, dictionary)
    if not isinstance(resolved, str):
        return None
    return resolved.strip().upper()


def classify_behaviour_role(
    *,
    root_trigger: str | None,
    behaviour_state: str | None,
    primary_assigned: bool,
) -> str:
    """
    Conservative structural classification.

    - First record compatible with the root trigger -> primary
    - Explicitly different trigger/state -> alternate_mode
    - Remaining records -> unclassified

    This avoids assuming Incarnon, radial, charged, etc. unless
    the source explicitly identifies that behaviour.
    """

    compatible_with_root = (
        behaviour_state is None
        or root_trigger is None
        or behaviour_state == root_trigger
    )

    if not primary_assigned and compatible_with_root:
        return "primary"

    if (
        behaviour_state is not None
        and root_trigger is not None
        and behaviour_state != root_trigger
    ):
        return "alternate_mode"

    return "unclassified"




def normalize_behaviour_record(
    behavior: dict[str, Any],
    index: int,
    dictionary: dict[str, str],
    root_trigger: str | None,
    primary_assigned: bool,
) -> dict[str, Any]:

    record: dict[str, Any] = {
        "index": index,
    }

    state_name = behavior.get("stateName")
    behaviour_state: str | None = None

    if isinstance(state_name, str):
        record["state_key"] = state_name
        record["state"] = localized(
            state_name,
            dictionary,
        )

        behaviour_state = normalize_trigger_value(
            state_name,
            dictionary,
        )

    record["role"] = classify_behaviour_role(
        root_trigger=root_trigger,
        behaviour_state=behaviour_state,
        primary_assigned=primary_assigned,
    )

    fire_iterations = as_number(
        behavior.get("fireIterations")
    )

    if fire_iterations is not None:
        record["fire_iterations"] = clean_number(
            fire_iterations
        )

    burst = behavior.get("burst")

    if isinstance(burst, dict):
        burst_out: dict[str, Any] = {}

        count = as_number(
            burst.get("count")
        )

        delay = as_number(
            burst.get("delay")
        )

        if count is not None:
            burst_out["count"] = clean_number(
                count
            )

        if delay is not None:
            burst_out["delay_seconds"] = clean_number(
                delay
            )

        if burst_out:
            record["burst"] = burst_out

    components = extract_damage_components(
        behavior
    )

    if components:
        record["components"] = components

    return record


def normalize_behaviour_records(
    weapon: dict[str, Any],
    dictionary: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:

    behaviours = weapon.get("behaviours")

    if not isinstance(behaviours, list):
        return [], 0

    root_trigger = normalize_trigger_value(
        weapon.get("trigger"),
        dictionary,
    )

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    deduped = 0
    primary_assigned = False

    for index, behavior in enumerate(behaviours):

        if not isinstance(behavior, dict):
            continue

        record = normalize_behaviour_record(
            behavior=behavior,
            index=index,
            dictionary=dictionary,
            root_trigger=root_trigger,
            primary_assigned=primary_assigned,
        )

        # Exact structural dedupe only.
        #
        # Role and index are excluded so duplicated source
        # structures can collapse without pretending that
        # semantically different records are equivalent.
        signature_source = {
            key: value
            for key, value in record.items()
            if key not in {
                "index",
                "role",
            }
        }

        signature = json.dumps(
            signature_source,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        if signature in seen:
            deduped += 1
            continue

        seen.add(signature)

        if record.get("role") == "primary":
            primary_assigned = True

        records.append(record)

    return records, deduped


# ---------------------------------------------------------------------------
# Canonical weapon record
# ---------------------------------------------------------------------------

def canonical_weapon(
    weapon_id: str,
    weapon: dict[str, Any],
    dictionary: dict[str, str],
) -> tuple[dict[str, Any], int]:

    product_category = weapon.get(
        "productCategory"
    )

    category = CATEGORY_MAP.get(
        product_category,
        str(product_category).lower(),
    )

    name_key = weapon.get("name")
    description_key = weapon.get(
        "description"
    )

    behaviour_records, deduped_records = (
        normalize_behaviour_records(
            weapon,
            dictionary,
        )
    )

    (
        root_damage_types,
        unknown_root_damage_indexes,
    ) = normalize_root_damage(
        weapon.get("damagePerShot")
    )

    compatibility_tags = [
        str(tag)
        for tag in weapon.get(
            "compatibilityTags",
            [],
        )
        if isinstance(tag, str)
    ]

    mechanical_tags = sorted(
        tag
        for tag in compatibility_tags
        if tag in MECHANICAL_TAGS
    )

    total_damage = as_number(
        weapon.get("totalDamage")
    )

    critical_chance = as_number(
        weapon.get("criticalChance")
    )

    critical_multiplier = as_number(
        weapon.get("criticalMultiplier")
    )

    status_chance = as_number(
        weapon.get("procChance")
    )

    out: dict[str, Any] = {

        "weapon_id": weapon_id,

        "identity": {
            "name": localized(
                name_key,
                dictionary,
            ),
            "name_key": name_key,
        },

        "qualitative_context": {
            "official_description": localized(
                description_key,
                dictionary,
            ),
            "usage": "weapon_context",
        },

        "classification": {
            "category": category,
            "product_category": product_category,
            "slot": weapon.get("slot"),
            "variant_type": weapon.get(
                "variantType"
            ),
        },

        "damage": {
            "base_damage": {
                "total": clean_number(
                    total_damage
                ),
                "by_type": root_damage_types,
                "distribution_percent":
                    damage_distribution_percent(
                        root_damage_types
                    ),
            },
        },

        "critical": {
            "chance": {
                "percent": fraction_to_percent(
                    critical_chance
                ),
            },
            "multiplier": {
                "times": clean_number(
                    critical_multiplier
                ),
            },
        },

        "status": {
            "chance": {
                "percent": fraction_to_percent(
                    status_chance
                ),
            },
        },

        "mechanics": {
            "trigger": weapon.get("trigger"),
            "multishot": clean_number(
                as_number(
                    weapon.get("multishot")
                )
            ),
            "mechanical_tags":
                mechanical_tags,
        },

        "riven": classify_riven(
            as_number(
                weapon.get(
                    "omegaAttenuation"
                )
            )
        ),

        "behaviour_records":
            behaviour_records,

        "source": {
            "description_key":
                description_key,
            "compatibility_tags":
                compatibility_tags,
        },
    }

    if unknown_root_damage_indexes:
        out["source"][
            "unknown_root_damage_indexes"
        ] = unknown_root_damage_indexes

    # --------------------------------------------------------
    # Ranged / firearm-like handling
    # --------------------------------------------------------

    if category in {
        "primary",
        "secondary",
        "archgun",
        "companion",
        "amp",
        "special",
    }:

        out["handling"] = {

            "fire_rate": {
                "per_second": clean_number(
                    as_number(
                        weapon.get("fireRate")
                    )
                ),
            },

            "magazine": {
                "rounds": clean_number(
                    as_number(
                        weapon.get(
                            "magazineSize"
                        )
                    )
                ),
            },

            "reload": {
                "seconds": clean_number(
                    as_number(
                        weapon.get("reloadTime")
                    )
                ),
            },

            # Meaning of this public-export number is not
            # sufficiently clear for semantic interpretation.
            "raw_accuracy_value":
                clean_number(
                    as_number(
                        weapon.get("accuracy")
                    )
                ),

            "noise": weapon.get("noise"),
        }

        multishot = as_number(
            weapon.get("multishot")
        )

        if (
            total_damage is not None
            and multishot is not None
        ):

            # Transparent arithmetic only:
            #
            # totalDamage * multishot
            #
            # This intentionally does NOT claim to represent
            # burst damage, DPS, secondary explosions, etc.
            out["damage"][
                "base_multishot_damage"
            ] = {
                "damage": clean_number(
                    total_damage
                    * multishot
                )
            }

    # --------------------------------------------------------
    # Melee handling
    # --------------------------------------------------------

    if category in {
        "melee",
        "archmelee",
    }:

        out["handling"] = {

            "attack_speed": {
                "attacks_per_second":
                    clean_number(
                        as_number(
                            weapon.get(
                                "fireRate"
                            )
                        )
                    ),
            },

            "range": {
                "meters":
                    clean_number(
                        as_number(
                            weapon.get(
                                "range"
                            )
                        )
                    ),
            },

            "follow_through": {
                "coefficient":
                    clean_number(
                        as_number(
                            weapon.get(
                                "followThrough"
                            )
                        )
                    ),
            },

            "combo_duration": {
                "seconds":
                    clean_number(
                        as_number(
                            weapon.get(
                                "comboDuration"
                            )
                        )
                    ),
            },

            "heavy_attack": {
                "damage":
                    clean_number(
                        as_number(
                            weapon.get(
                                "heavyAttackDamage"
                            )
                        )
                    ),
            },

            "heavy_windup": {
                "seconds":
                    clean_number(
                        as_number(
                            weapon.get(
                                "windUp"
                            )
                        )
                    ),
            },
        }

    return out, deduped_records


# ---------------------------------------------------------------------------
# Population statistics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricSpec:
    output_path: tuple[str, ...]
    source_field: str | None = None
    derived: str | None = None

    # Deterministic semantic guidance for small language models.
    # These descriptors do not rate weapon quality. They only translate the
    # numerical direction of the metric into plain language.
    context_name: str = "metric"
    low_descriptor: str = "low"
    high_descriptor: str = "high"


POPULATION_CONTEXT_NAMES = {
    "LongGuns": "primary weapons",
    "Pistols": "secondary weapons",
    "Melee": "melee weapons",
}


def relative_guidance(
    spec: MetricSpec,
    band: str,
    population: str,
) -> tuple[str, str]:
    """
    Convert a deterministic percentile band into two LLM-friendly fields:

    - guide_tag: compact machine-readable semantic tag
    - relative_context: short natural-language interpretation

    Examples:
        high critical chance
        exceptionally fast fire rate
        very slow reload

    This function never decides whether a stat is good or bad for a build.
    """
    low_prefix = {
        "exceptionally_low": "exceptionally ",
        "very_low": "very ",
        "low": "",
    }
    high_prefix = {
        "high": "",
        "very_high": "very ",
        "exceptionally_high": "exceptionally ",
    }

    if band == "middle_range":
        description = f"typical {spec.context_name}"
    elif band in low_prefix:
        description = (
            f"{low_prefix[band]}{spec.low_descriptor} {spec.context_name}"
        )
    elif band in high_prefix:
        description = (
            f"{high_prefix[band]}{spec.high_descriptor} {spec.context_name}"
        )
    else:
        raise ValueError(f"Unsupported relative band: {band!r}")

    population_name = POPULATION_CONTEXT_NAMES.get(
        population,
        f"weapons in {population}",
    )

    guide_tag = "_".join(description.casefold().split())
    relative_context = (
        f"{description} compared with other {population_name}"
    )

    return guide_tag, relative_context


def metric_specs_for_population(
    population: str,
) -> dict[str, MetricSpec]:

    if population in {
        "LongGuns",
        "Pistols",
    }:

        return {
            "critical_chance": MetricSpec(
                ("critical", "chance"),
                "criticalChance",
                context_name="critical chance",
            ),
            "critical_multiplier": MetricSpec(
                ("critical", "multiplier"),
                "criticalMultiplier",
                context_name="critical multiplier",
            ),
            "status_chance": MetricSpec(
                ("status", "chance"),
                "procChance",
                context_name="status chance",
            ),
            "fire_rate": MetricSpec(
                ("handling", "fire_rate"),
                "fireRate",
                context_name="fire rate",
                low_descriptor="slow",
                high_descriptor="fast",
            ),
            "magazine_size": MetricSpec(
                ("handling", "magazine"),
                "magazineSize",
                context_name="magazine",
                low_descriptor="small",
                high_descriptor="large",
            ),
            "reload_duration_seconds": MetricSpec(
                ("handling", "reload"),
                "reloadTime",
                context_name="reload",
                low_descriptor="fast",
                high_descriptor="slow",
            ),
            "base_multishot_damage": MetricSpec(
                ("damage", "base_multishot_damage"),
                derived="base_multishot_damage",
                context_name="base multishot damage",
            ),
        }

    if population == "Melee":

        return {
            "total_damage": MetricSpec(
                ("damage", "base_damage"),
                "totalDamage",
                context_name="base damage",
            ),
            "critical_chance": MetricSpec(
                ("critical", "chance"),
                "criticalChance",
                context_name="critical chance",
            ),
            "critical_multiplier": MetricSpec(
                ("critical", "multiplier"),
                "criticalMultiplier",
                context_name="critical multiplier",
            ),
            "status_chance": MetricSpec(
                ("status", "chance"),
                "procChance",
                context_name="status chance",
            ),
            "attack_speed": MetricSpec(
                ("handling", "attack_speed"),
                "fireRate",
                context_name="attack speed",
                low_descriptor="slow",
                high_descriptor="fast",
            ),
            "range_meters": MetricSpec(
                ("handling", "range"),
                "range",
                context_name="melee range",
                low_descriptor="short",
                high_descriptor="long",
            ),
            "follow_through": MetricSpec(
                ("handling", "follow_through"),
                "followThrough",
                context_name="follow-through",
            ),
            "combo_duration_seconds": MetricSpec(
                ("handling", "combo_duration"),
                "comboDuration",
                context_name="combo duration",
                low_descriptor="short",
                high_descriptor="long",
            ),
            "heavy_attack_damage": MetricSpec(
                ("handling", "heavy_attack"),
                "heavyAttackDamage",
                context_name="heavy attack damage",
            ),
            "heavy_windup_seconds": MetricSpec(
                ("handling", "heavy_windup"),
                "windUp",
                context_name="heavy attack windup",
                low_descriptor="short",
                high_descriptor="long",
            ),
        }

    return {}


def metric_value(
    raw_weapon: dict[str, Any],
    spec: MetricSpec,
) -> float | None:

    if spec.source_field is not None:
        return as_number(
            raw_weapon.get(
                spec.source_field
            )
        )

    if (
        spec.derived
        == "base_multishot_damage"
    ):

        total = as_number(
            raw_weapon.get("totalDamage")
        )

        multishot = as_number(
            raw_weapon.get("multishot")
        )

        if (
            total is None
            or multishot is None
        ):
            return None

        return total * multishot

    return None


def add_nested_population_metadata(
    weapon: dict[str, Any],
    path: tuple[str, ...],
    *,
    percentile: float,
    band: str,
    guide_tag: str,
    relative_context: str,
) -> None:
    """
    Add population metadata without replacing the canonical
    stat object.

    This keeps field types stable across evaluated and
    non-evaluated weapon classes.
    """

    cursor = weapon

    for key in path[:-1]:
        cursor = cursor.setdefault(
            key,
            {},
        )

    stat = cursor.get(
        path[-1]
    )

    if not isinstance(stat, dict):
        raise TypeError(
            "Expected canonical stat object at "
            + ".".join(path)
        )

    stat[
        "population_percentile"
    ] = percentile

    stat[
        "relative_band"
    ] = band

    stat[
        "guide_tag"
    ] = guide_tag

    stat[
        "relative_context"
    ] = relative_context


def add_population_statistics(
    raw_selected: dict[
        str,
        dict[str, Any],
    ],
    normalized: dict[
        str,
        dict[str, Any],
    ],
) -> dict[str, Any]:

    populations: dict[
        str,
        list[str],
    ] = defaultdict(list)

    for weapon_id, raw in (
        raw_selected.items()
    ):

        population = raw.get(
            "productCategory"
        )

        if (
            population
            in EVALUATED_POPULATIONS
        ):
            populations[
                population
            ].append(
                weapon_id
            )

    population_report: dict[
        str,
        Any,
    ] = {}

    for (
        population,
        weapon_ids,
    ) in sorted(
        populations.items()
    ):

        specs = (
            metric_specs_for_population(
                population
            )
        )

        distributions: dict[
            str,
            list[float],
        ] = {}

        for (
            metric_name,
            spec,
        ) in specs.items():

            values = [
                value
                for weapon_id
                in weapon_ids
                if (
                    value := metric_value(
                        raw_selected[
                            weapon_id
                        ],
                        spec,
                    )
                )
                is not None
            ]

            distributions[
                metric_name
            ] = sorted(
                values
            )

        population_report[
            population
        ] = {

            "population_size":
                len(weapon_ids),

            "metric_sample_sizes": {
                metric:
                    len(values)
                for (
                    metric,
                    values,
                )
                in distributions.items()
            },
        }

        for weapon_id in weapon_ids:

            raw = raw_selected[
                weapon_id
            ]

            out = normalized[
                weapon_id
            ]

            out["population"] = {
                "group": population,
                "size": len(
                    weapon_ids
                ),
            }

            for (
                metric_name,
                spec,
            ) in specs.items():

                value = metric_value(
                    raw,
                    spec,
                )

                values = distributions[
                    metric_name
                ]

                if (
                    value is None
                    or not values
                ):
                    continue

                percentile = round(
                    percentile_midrank(
                        values,
                        value,
                    ),
                    2,
                )

                band = relative_band(
                    percentile
                )

                (
                    guide_tag,
                    relative_context,
                ) = relative_guidance(
                    spec,
                    band,
                    population,
                )

                add_nested_population_metadata(
                    out,
                    spec.output_path,
                    percentile=percentile,
                    band=band,
                    guide_tag=guide_tag,
                    relative_context=relative_context,
                )

    # Preserve other classes without forcing invalid
    # cross-category statistical comparisons.
    for (
        weapon_id,
        raw,
    ) in raw_selected.items():

        if (
            raw.get(
                "productCategory"
            )
            not in EVALUATED_POPULATIONS
        ):

            normalized[
                weapon_id
            ]["population"] = {

                "group":
                    raw.get(
                        "productCategory"
                    ),

                "evaluated":
                    False,

                "reason":
                    "population_not_enabled_in_v1",
            }

    return population_report


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_database(
    raw_path: Path = RAW_WEAPONS_PATH,
    localization_path: Path = LOCALIZATION_PATH,
    output_path: Path = OUTPUT_PATH,
    report_path: Path = REPORT_PATH,
) -> dict[str, Any]:
    raw = load_json(raw_path)
    dictionary = load_json(localization_path)

    if not isinstance(raw, dict):
        raise ValueError("ExportWeapons.json root must be a JSON object.")
    if not isinstance(dictionary, dict):
        raise ValueError("dict.en.json root must be a JSON object.")

    selected: dict[str, dict[str, Any]] = {}
    exclusions = Counter()

    for weapon_id, weapon in raw.items():
        ok, reason = is_selectable_weapon(weapon_id, weapon)
        if not ok:
            exclusions[reason or "unknown"] += 1
            continue
        selected[weapon_id] = weapon

    selectable_before_name_canonicalization = len(selected)

    selected, duplicate_name_collisions = (
        resolve_duplicate_names(
            selected,
            dictionary,
        )
    )

    duplicate_name_records_removed = (
        selectable_before_name_canonicalization
        - len(selected)
    )

    if duplicate_name_records_removed:
        exclusions[
            "duplicate_localized_name_noncanonical"
        ] += duplicate_name_records_removed

    normalized: dict[str, dict[str, Any]] = {}
    category_counts = Counter()
    deduped_records = 0
    missing_localized_names = 0
    missing_localized_descriptions = 0

    for weapon_id, weapon in selected.items():
        out, removed_records = canonical_weapon(weapon_id, weapon, dictionary)
        deduped_records += removed_records

        if out["identity"]["name"] == out["identity"]["name_key"]:
            missing_localized_names += 1

        description = out.get("qualitative_context", {}).get("official_description")
        description_key = out.get("source", {}).get("description_key")
        if description_key and description == description_key:
            missing_localized_descriptions += 1

        category_counts[str(weapon.get("productCategory"))] += 1
        normalized[weapon_id] = out

    population_report = add_population_statistics(selected, normalized)

    database = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "weapons": str(raw_path),
            "localization": str(localization_path),
        },
        "weapon_count": len(normalized),
        "weapons": normalized,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "raw_entries": len(raw),
        "selectable_weapons_before_name_canonicalization": (
            selectable_before_name_canonicalization
        ),
        "selected_weapons": len(selected),
        "excluded_entries": len(raw) - len(selected),
        "exclusion_reasons": dict(exclusions.most_common()),
        "product_categories": dict(category_counts.most_common()),
        "evaluated_populations": population_report,
        "exact_duplicate_behaviour_records_removed": deduped_records,
        "duplicate_name_records_removed": duplicate_name_records_removed,
        "duplicate_name_collisions": duplicate_name_collisions,
        "missing_localized_names": missing_localized_names,
        "missing_localized_descriptions": missing_localized_descriptions,
        "notes": [
            "Population percentiles describe relative position, not weapon quality.",
            "Relative bands describe numerical position only, never good/bad quality.",
            "Guide tags and relative_context are deterministic translations of percentile direction, not build recommendations.",
            "Metric-specific direction is explicit: high fire rate means fast, high reload duration means slow, high magazine size means large.",
            "Probability-like root statistics are exposed as percentages from 0 to 100.",
            "Population percentile fields are explicitly named population_percentile.",
            "Canonical stat objects keep the same type whether or not population statistics are available.",
            "Riven disposition uses a fixed rule instead of population percentiles.",
            "Accuracy is preserved as raw_accuracy_value and is not semantically interpreted.",
            "Nested behaviour procChance values are preserved as proc_chance_raw until their exact semantics are verified.",
            "Behaviour records preserve structural damage components without semantic merging.",
            "Behaviour roles are conservative: primary, alternate_mode, or unclassified.",
            "The first behaviour compatible with the root trigger becomes primary.",
            "Root damage amounts are exposed under base_damage.by_type; only distribution_percent represents percentages.",
            "Damage distribution is exposed as percentages from 0 to 100.",
            "base_multishot_damage means totalDamage multiplied by multishot only; it is not DPS or full trigger-event damage.",
            "Official descriptions are exposed as qualitative weapon context for the language model.",
            "Descriptions never override structured numerical or mechanical data.",
            "Only LongGuns, Pistols, and Melee receive population evaluation in V1.",
            "Duplicate localized names are canonicalized before population statistics.",
        ],
    }

    save_json(output_path, database)
    save_json(report_path, report)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def find_weapon(
    database: dict[str, Any],
    query: str,
) -> tuple[str, dict[str, Any]] | None:
    weapons = database.get("weapons", {})

    if query in weapons:
        return query, weapons[query]

    q = query.casefold()
    exact_name_matches = []
    partial_matches = []

    for weapon_id, weapon in weapons.items():
        name = weapon.get("identity", {}).get("name") if isinstance(weapon, dict) else None
        if not isinstance(name, str):
            continue
        if name.casefold() == q:
            exact_name_matches.append((weapon_id, weapon))
        elif q in name.casefold():
            partial_matches.append((weapon_id, weapon))

    if exact_name_matches:
        return exact_name_matches[0]
    if len(partial_matches) == 1:
        return partial_matches[0]
    return None


def command_build(args: argparse.Namespace) -> None:
    report = build_database(
        raw_path=Path(args.raw),
        localization_path=Path(args.localization),
        output_path=Path(args.output),
        report_path=Path(args.report),
    )

    print("========================================")
    print("WEAPON DATABASE BUILT")
    print("========================================")
    print(f"Raw entries:        {report['raw_entries']}")
    print(f"Selected weapons:   {report['selected_weapons']}")
    print(f"Excluded entries:   {report['excluded_entries']}")
    print()
    print("Evaluated populations:")
    for population, info in report["evaluated_populations"].items():
        print(f"  {population:<12} {info['population_size']:>4}")
    print()
    print(f"Database: {args.output}")
    print(f"Report:   {args.report}")


def command_inspect(args: argparse.Namespace) -> None:
    database = load_json(Path(args.database))
    result = find_weapon(database, args.query)
    if result is None:
        raise SystemExit(f"Weapon not found or query is ambiguous: {args.query!r}")

    weapon_id, weapon = result
    print(weapon_id)
    print(json.dumps(weapon, ensure_ascii=False, indent=2))


def command_list(args: argparse.Namespace) -> None:
    database = load_json(Path(args.database))
    weapons = database.get("weapons", {})

    rows = []
    for weapon_id, weapon in weapons.items():
        category = weapon.get("classification", {}).get("category")
        name = weapon.get("identity", {}).get("name")
        if args.category and category != args.category:
            continue
        rows.append((str(name), str(category), weapon_id))

    for name, category, weapon_id in sorted(rows, key=lambda row: row[0].casefold()):
        print(f"{name:<35} {category:<12} {weapon_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and inspect the deterministic Warframe weapon database."
    )
    subparsers = parser.add_subparsers(dest="command")

    build = subparsers.add_parser("build", help="Build the weapon database.")
    build.add_argument("--raw", default=str(RAW_WEAPONS_PATH))
    build.add_argument("--localization", default=str(LOCALIZATION_PATH))
    build.add_argument("--output", default=str(OUTPUT_PATH))
    build.add_argument("--report", default=str(REPORT_PATH))
    build.set_defaults(func=command_build)

    inspect = subparsers.add_parser("inspect", help="Inspect one weapon.")
    inspect.add_argument("query")
    inspect.add_argument("--database", default=str(OUTPUT_PATH))
    inspect.set_defaults(func=command_inspect)

    list_cmd = subparsers.add_parser("list", help="List weapons.")
    list_cmd.add_argument(
        "--category",
        choices=[
            "primary",
            "secondary",
            "melee",
            "companion",
            "archgun",
            "archmelee",
            "amp",
            "special",
        ],
    )
    list_cmd.add_argument("--database", default=str(OUTPUT_PATH))
    list_cmd.set_defaults(func=command_list)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # `python -m modules.weapon_database` builds by default.
    if not getattr(args, "command", None):
        args = parser.parse_args(["build"])

    args.func(args)


if __name__ == "__main__":
    main()