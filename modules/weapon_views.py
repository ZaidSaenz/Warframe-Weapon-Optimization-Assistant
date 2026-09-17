from __future__ import annotations

import argparse
import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "normalized"
    / "weapons.json"
)

VIEWS_DIR = PROJECT_ROOT / "data" / "views"

LOOKUP_VIEW_PATH = (
    VIEWS_DIR / "weapon_lookup.json"
)

PROFILE_VIEW_PATH = (
    VIEWS_DIR / "weapon_profiles.json"
)

COMPARE_VIEW_PATH = (
    VIEWS_DIR / "weapon_compare.json"
)

SEARCH_VIEW_PATH = (
    VIEWS_DIR / "weapon_search.json"
)

VIEW_SCHEMA_VERSION = "1.1.0"


LOW_BANDS = {
    "low",
    "very_low",
    "exceptionally_low",
}

HIGH_BANDS = {
    "high",
    "very_high",
    "exceptionally_high",
}


# ============================================================
# METRIC DEFINITIONS
# ============================================================


@dataclass(frozen=True)
class MetricSource:
    path: tuple[str, ...]
    value_keys: tuple[str, ...]
    output_name: str


@dataclass(frozen=True)
class MetricView:
    key: str
    sources: tuple[MetricSource, ...]
    unit: str
    higher_is_better: bool


PROFILE_METRICS: tuple[MetricView, ...] = (

    MetricView(
        "damage",
        (
            MetricSource(
                (
                    "damage",
                    "base_multishot_damage",
                ),
                ("damage",),
                "base_multishot_damage",
            ),
            MetricSource(
                (
                    "damage",
                    "base_damage",
                ),
                ("total",),
                "base_damage",
            ),
        ),
        "damage",
        True,
    ),

    MetricView(
        "critical_chance",
        (
            MetricSource(
                (
                    "critical",
                    "chance",
                ),
                ("percent",),
                "critical_chance",
            ),
        ),
        "percent",
        True,
    ),

    MetricView(
        "critical_multiplier",
        (
            MetricSource(
                (
                    "critical",
                    "multiplier",
                ),
                ("times",),
                "critical_multiplier",
            ),
        ),
        "times",
        True,
    ),

    MetricView(
        "status_chance",
        (
            MetricSource(
                (
                    "status",
                    "chance",
                ),
                ("percent",),
                "status_chance",
            ),
        ),
        "percent",
        True,
    ),

    MetricView(
        "fire_rate",
        (
            MetricSource(
                (
                    "handling",
                    "fire_rate",
                ),
                ("per_second",),
                "fire_rate",
            ),
        ),
        "per_second",
        True,
    ),

    MetricView(
        "magazine",
        (
            MetricSource(
                (
                    "handling",
                    "magazine",
                ),
                ("rounds",),
                "magazine",
            ),
        ),
        "rounds",
        True,
    ),

    MetricView(
        "reload",
        (
            MetricSource(
                (
                    "handling",
                    "reload",
                ),
                ("seconds",),
                "reload",
            ),
        ),
        "seconds",
        False,
    ),

    MetricView(
        "attack_speed",
        (
            MetricSource(
                (
                    "handling",
                    "attack_speed",
                ),
                ("attacks_per_second",),
                "attack_speed",
            ),
        ),
        "attacks_per_second",
        True,
    ),

    MetricView(
        "range",
        (
            MetricSource(
                (
                    "handling",
                    "range",
                ),
                ("meters",),
                "range",
            ),
        ),
        "meters",
        True,
    ),

    MetricView(
        "follow_through",
        (
            MetricSource(
                (
                    "handling",
                    "follow_through",
                ),
                ("coefficient",),
                "follow_through",
            ),
        ),
        "coefficient",
        True,
    ),

    MetricView(
        "combo_duration",
        (
            MetricSource(
                (
                    "handling",
                    "combo_duration",
                ),
                ("seconds",),
                "combo_duration",
            ),
        ),
        "seconds",
        True,
    ),

    MetricView(
        "heavy_attack_damage",
        (
            MetricSource(
                (
                    "handling",
                    "heavy_attack",
                ),
                ("damage",),
                "heavy_attack_damage",
            ),
        ),
        "damage",
        True,
    ),

    MetricView(
        "heavy_windup",
        (
            MetricSource(
                (
                    "handling",
                    "heavy_windup",
                ),
                ("seconds",),
                "heavy_windup",
            ),
        ),
        "seconds",
        False,
    ),
)


METRIC_BY_KEY = {
    metric.key: metric
    for metric in PROFILE_METRICS
}


SEARCH_CRITERIA: dict[
    str,
    tuple[str, str],
] = {

    "high_damage":
        ("damage", "high"),

    "low_damage":
        ("damage", "low"),

    "high_critical_chance":
        ("critical_chance", "high"),

    "low_critical_chance":
        ("critical_chance", "low"),

    "high_critical_multiplier":
        ("critical_multiplier", "high"),

    "low_critical_multiplier":
        ("critical_multiplier", "low"),

    "high_status_chance":
        ("status_chance", "high"),

    "low_status_chance":
        ("status_chance", "low"),

    "fast_fire_rate":
        ("fire_rate", "high"),

    "slow_fire_rate":
        ("fire_rate", "low"),

    "large_magazine":
        ("magazine", "high"),

    "small_magazine":
        ("magazine", "low"),

    "fast_reload":
        ("reload", "low"),

    "slow_reload":
        ("reload", "high"),

    "fast_attack_speed":
        ("attack_speed", "high"),

    "slow_attack_speed":
        ("attack_speed", "low"),

    "long_range":
        ("range", "high"),

    "short_range":
        ("range", "low"),

    "high_follow_through":
        ("follow_through", "high"),

    "low_follow_through":
        ("follow_through", "low"),

    "long_combo_duration":
        ("combo_duration", "high"),

    "short_combo_duration":
        ("combo_duration", "low"),

    "high_heavy_attack_damage":
        ("heavy_attack_damage", "high"),

    "low_heavy_attack_damage":
        ("heavy_attack_damage", "low"),

    "fast_heavy_windup":
        ("heavy_windup", "low"),

    "slow_heavy_windup":
        ("heavy_windup", "high"),
}


SEARCH_CRITERION_NAMES = sorted(
    SEARCH_CRITERIA
)


# ============================================================
# GENERIC HELPERS
# ============================================================


def load_json(
    path: Path,
) -> Any:

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save_json(
    path: Path,
    data: Any,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def normalize_name(
    value: str,
) -> str:

    return " ".join(
        value.casefold()
        .strip()
        .split()
    )


def extract_weapons(
    payload: Any,
) -> list[dict[str, Any]]:

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "weapons.json root must be a JSON object."
        )

    weapons = payload.get(
        "weapons"
    )

    if isinstance(
        weapons,
        dict,
    ):
        return [
            weapon
            for weapon
            in weapons.values()
            if isinstance(
                weapon,
                dict,
            )
        ]

    if isinstance(
        weapons,
        list,
    ):
        return [
            weapon
            for weapon
            in weapons
            if isinstance(
                weapon,
                dict,
            )
        ]

    raise ValueError(
        "Unsupported weapons.json structure."
    )


def weapon_name(
    weapon: dict[str, Any],
) -> str | None:

    identity = weapon.get(
        "identity"
    )

    if isinstance(
        identity,
        dict,
    ):

        name = identity.get(
            "name"
        )

        if (
            isinstance(name, str)
            and name.strip()
        ):
            return name.strip()

    return None


def nested_dict(
    data: dict[str, Any],
    path: tuple[str, ...],
) -> dict[str, Any] | None:

    current: Any = data

    for key in path:

        if not isinstance(
            current,
            dict,
        ):
            return None

        current = current.get(
            key
        )

    if isinstance(
        current,
        dict,
    ):
        return current

    return None


# ============================================================
# METRIC EXTRACTION
# ============================================================


def metric_snapshot(
    weapon: dict[str, Any],
    metric: MetricView,
) -> dict[str, Any] | None:

    for source in metric.sources:

        stat = nested_dict(
            weapon,
            source.path,
        )

        if stat is None:
            continue

        percentile = stat.get(
            "population_percentile"
        )

        if not isinstance(
            percentile,
            (int, float),
        ):
            continue

        value: Any = None

        for value_key in (
            source.value_keys
        ):

            if value_key in stat:

                value = stat.get(
                    value_key
                )

                break

        return {
            "metric":
                source.output_name,

            "value":
                value,

            "unit":
                metric.unit,

            "percentile":
                float(percentile),

            "band":
                stat.get(
                    "relative_band"
                ),

            "relative":
                stat.get(
                    "guide_tag"
                ),
        }

    return None


def weapon_metric_map(
    weapon: dict[str, Any],
) -> dict[str, dict[str, Any]]:

    metrics: dict[
        str,
        dict[str, Any],
    ] = {}

    for definition in (
        PROFILE_METRICS
    ):

        snapshot = (
            metric_snapshot(
                weapon,
                definition,
            )
        )

        if snapshot is not None:

            metrics[
                definition.key
            ] = snapshot

    return metrics


def metric_desirability_score(
    snapshot: dict[str, Any],
    definition: MetricView,
) -> float:

    percentile = float(
        snapshot["percentile"]
    )

    if definition.higher_is_better:
        return percentile

    return 100.0 - percentile


def profile_bucket(
    snapshot: dict[str, Any],
    definition: MetricView,
) -> str:

    band = snapshot.get(
        "band"
    )

    if band == "middle_range":
        return "typical"

    if band in HIGH_BANDS:

        if definition.higher_is_better:
            return "strength"

        return "weakness"

    if band in LOW_BANDS:

        if definition.higher_is_better:
            return "weakness"

        return "strength"

    return "typical"


def criterion_matches(
    snapshot: dict[str, Any],
    direction: str,
) -> bool:

    band = snapshot.get(
        "band"
    )

    if direction == "high":
        return band in HIGH_BANDS

    if direction == "low":
        return band in LOW_BANDS

    return False


def criterion_score(
    snapshot: dict[str, Any],
    direction: str,
) -> float:

    percentile = float(
        snapshot.get(
            "percentile",
            0.0,
        )
    )

    if direction == "high":
        return percentile

    return 100.0 - percentile


def compact_profile_item(
    snapshot: dict[str, Any],
) -> dict[str, Any]:

    return {
        "metric":
            snapshot.get(
                "metric"
            ),

        "value":
            snapshot.get(
                "value"
            ),

        "unit":
            snapshot.get(
                "unit"
            ),

        "relative":
            snapshot.get(
                "relative"
            ),
    }


# ============================================================
# TOOL OUTPUT SEMANTICS
# ============================================================

# Compare and search expose literal field names instead of generic
# metric/value/unit structures. This makes weapon -> value association
# much easier for small language models.

COMPARE_FIELD_NAMES = {
    "base_multishot_damage":
        "base_multishot_damage",

    "base_damage":
        "base_damage",

    "critical_chance":
        "critical_chance_percent",

    "critical_multiplier":
        "critical_multiplier_times",

    "status_chance":
        "status_chance_percent",

    "fire_rate":
        "fire_rate_per_second",

    "magazine":
        "magazine_rounds",

    "reload":
        "reload_seconds",

    "attack_speed":
        "attack_speed_per_second",

    "range":
        "range_meters",

    "follow_through":
        "follow_through_coefficient",

    "combo_duration":
        "combo_duration_seconds",

    "heavy_attack_damage":
        "heavy_attack_damage",

    "heavy_windup":
        "heavy_windup_seconds",
}


def comparison_field_name(
    snapshot: dict[str, Any],
) -> str:

    metric = snapshot.get(
        "metric"
    )

    if isinstance(
        metric,
        str,
    ):
        return COMPARE_FIELD_NAMES.get(
            metric,
            metric,
        )

    return "unknown_metric"


def comparison_stats(
    metrics: dict[
        str,
        dict[str, Any],
    ],
) -> dict[str, Any]:
    """
    Convert internal metric snapshots into literal comparable facts.

    Population percentile/band metadata stays internal.
    """

    return {
        comparison_field_name(
            snapshot
        ):
            snapshot.get(
                "value"
            )

        for snapshot
        in metrics.values()

        if isinstance(
            snapshot,
            dict,
        )
    }


def comparison_group_name(
    category: str | None,
) -> str:

    return {
        "primary":
            "primary weapons",

        "secondary":
            "secondary weapons",

        "melee":
            "melee weapons",
    }.get(
        category,
        "weapons in the same canonical category",
    )


# Riven disposition is factual data, but its meaning must be explicit enough
# that a small model does not interpret 1.2 as a direct +20% weapon bonus.

RIVEN_CONTEXT = {
    "very_low":
        "very low Riven mod stat scaling",

    "low":
        "below-average Riven mod stat scaling",

    "neutral":
        "average Riven mod stat scaling",

    "high":
        "above-average Riven mod stat scaling",

    "very_high":
        "very high Riven mod stat scaling",
}


def compact_riven(
    riven: dict[str, Any],
) -> dict[str, Any]:

    out = {
        key:
            riven.get(
                key
            )

        for key in (
            "disposition",
            "dots",
            "rating",
        )

        if riven.get(
            key
        )
        is not None
    }

    rating = riven.get(
        "rating"
    )

    if isinstance(
        rating,
        str,
    ):

        context = (
            RIVEN_CONTEXT.get(
                rating
            )
        )

        if context:
            out[
                "meaning"
            ] = context

    out[
        "scope"
    ] = (
        "Riven disposition describes stat scaling on Riven mods "
        "for this weapon. It does not directly multiply or increase "
        "the weapon's base statistics."
    )

    if "warning" in riven:
        out[
            "warning"
        ] = riven[
            "warning"
        ]

    return out


# ============================================================
# LOOKUP VIEW
# ============================================================


def compact_behaviour(
    record: dict[str, Any],
) -> dict[str, Any]:

    keep = (
        "state",
        "role",
        "fire_iterations",
        "burst",
        "components",
    )

    return {
        key: record[key]
        for key in keep
        if key in record
    }


def compact_lookup_weapon(
    weapon: dict[str, Any],
) -> dict[str, Any]:

    name = weapon_name(
        weapon
    )

    classification = weapon.get(
        "classification"
    )

    qualitative = weapon.get(
        "qualitative_context"
    )

    damage = weapon.get(
        "damage"
    )

    critical = weapon.get(
        "critical"
    )

    status = weapon.get(
        "status"
    )

    mechanics = weapon.get(
        "mechanics"
    )

    handling = weapon.get(
        "handling"
    )

    out: dict[str, Any] = {
        "name": name,
    }

    # --------------------------------------------------------
    # Classification
    # --------------------------------------------------------

    if isinstance(
        classification,
        dict,
    ):

        out[
            "classification"
        ] = {

            key:
                classification.get(
                    key
                )

            for key in (
                "category",
                "product_category",
                "variant_type",
            )

            if classification.get(
                key
            ) is not None
        }

    # --------------------------------------------------------
    # Official description
    # --------------------------------------------------------

    if isinstance(
        qualitative,
        dict,
    ):

        description = (
            qualitative.get(
                "official_description"
            )
        )

        if (
            isinstance(
                description,
                str,
            )
            and description
        ):

            out[
                "official_description"
            ] = description

    # --------------------------------------------------------
    # Damage
    # --------------------------------------------------------

    if isinstance(
        damage,
        dict,
    ):

        damage_out: dict[
            str,
            Any,
        ] = {}

        base = damage.get(
            "base_damage"
        )

        if isinstance(
            base,
            dict,
        ):

            damage_out[
                "base_damage"
            ] = {

                key:
                    base.get(
                        key
                    )

                for key in (
                    "total",
                    "by_type",
                    "distribution_percent",
                )

                if base.get(
                    key
                )
                not in (
                    None,
                    {},
                    [],
                )
            }

        multishot_damage = (
            damage.get(
                "base_multishot_damage"
            )
        )

        if (
            isinstance(
                multishot_damage,
                dict,
            )
            and multishot_damage.get(
                "damage"
            )
            is not None
        ):

            damage_out[
                "base_multishot_damage"
            ] = multishot_damage.get(
                "damage"
            )

        if damage_out:

            out[
                "damage"
            ] = damage_out

    # --------------------------------------------------------
    # Critical
    # --------------------------------------------------------

    if isinstance(
        critical,
        dict,
    ):

        critical_out: dict[
            str,
            Any,
        ] = {}

        chance = critical.get(
            "chance"
        )

        multiplier = critical.get(
            "multiplier"
        )

        if (
            isinstance(
                chance,
                dict,
            )
            and chance.get(
                "percent"
            )
            is not None
        ):

            critical_out[
                "chance_percent"
            ] = chance.get(
                "percent"
            )

        if (
            isinstance(
                multiplier,
                dict,
            )
            and multiplier.get(
                "times"
            )
            is not None
        ):

            critical_out[
                "multiplier_times"
            ] = multiplier.get(
                "times"
            )

        if critical_out:

            out[
                "critical"
            ] = critical_out

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    if isinstance(
        status,
        dict,
    ):

        chance = status.get(
            "chance"
        )

        if (
            isinstance(
                chance,
                dict,
            )
            and chance.get(
                "percent"
            )
            is not None
        ):

            out[
                "status"
            ] = {
                "chance_percent":
                    chance.get(
                        "percent"
                    )
            }

    # --------------------------------------------------------
    # Mechanics
    # --------------------------------------------------------

    if isinstance(
        mechanics,
        dict,
    ):

        mechanics_out = {

            "trigger":
                mechanics.get(
                    "trigger"
                ),

            "multishot":
                mechanics.get(
                    "multishot"
                ),

            "tags":
                mechanics.get(
                    "mechanical_tags"
                ),
        }

        out[
            "mechanics"
        ] = {

            key: value

            for key, value
            in mechanics_out.items()

            if value not in (
                None,
                [],
                {},
            )
        }

    # --------------------------------------------------------
    # Riven
    # --------------------------------------------------------

    riven = weapon.get(
        "riven"
    )

    if isinstance(
        riven,
        dict,
    ):

        out[
            "riven"
        ] = compact_riven(
            riven
        )

    # --------------------------------------------------------
    # Behaviour records
    # --------------------------------------------------------

    records = weapon.get(
        "behaviour_records"
    )

    if isinstance(
        records,
        list,
    ):

        compact_records = [

            compact_behaviour(
                record
            )

            for record in records

            if isinstance(
                record,
                dict,
            )
        ]

        if compact_records:

            out[
                "behaviours"
            ] = compact_records

    # --------------------------------------------------------
    # Handling
    # --------------------------------------------------------

    if isinstance(
        handling,
        dict,
    ):

        handling_out: dict[
            str,
            Any,
        ] = {}

        flatten = {

            "fire_rate":
                (
                    "per_second",
                    "fire_rate_per_second",
                ),

            "magazine":
                (
                    "rounds",
                    "magazine_rounds",
                ),

            "reload":
                (
                    "seconds",
                    "reload_seconds",
                ),

            "attack_speed":
                (
                    "attacks_per_second",
                    "attack_speed_per_second",
                ),

            "range":
                (
                    "meters",
                    "range_meters",
                ),

            "follow_through":
                (
                    "coefficient",
                    "follow_through",
                ),

            "combo_duration":
                (
                    "seconds",
                    "combo_duration_seconds",
                ),

            "heavy_attack":
                (
                    "damage",
                    "heavy_attack_damage",
                ),

            "heavy_windup":
                (
                    "seconds",
                    "heavy_windup_seconds",
                ),
        }

        for (
            source_key,
            (
                value_key,
                output_key,
            ),
        ) in flatten.items():

            stat = handling.get(
                source_key
            )

            if (
                isinstance(
                    stat,
                    dict,
                )
                and stat.get(
                    value_key
                )
                is not None
            ):

                handling_out[
                    output_key
                ] = stat.get(
                    value_key
                )

        if (
            handling.get(
                "raw_accuracy_value"
            )
            is not None
        ):

            handling_out[
                "raw_accuracy_value"
            ] = handling.get(
                "raw_accuracy_value"
            )

        if (
            handling.get(
                "noise"
            )
            is not None
        ):

            handling_out[
                "noise"
            ] = handling.get(
                "noise"
            )

        if handling_out:

            out[
                "handling"
            ] = handling_out

    return out


# ============================================================
# VIEW BUILDER
# ============================================================


def build_weapon_views(
    *,
    database_path: Path = DATABASE_PATH,
    views_dir: Path = VIEWS_DIR,
) -> dict[str, Any]:

    payload = load_json(
        database_path
    )

    weapons = extract_weapons(
        payload
    )

    source_schema_version = (
        payload.get(
            "schema_version"
        )
    )

    lookup: dict[
        str,
        Any,
    ] = {}

    profiles: dict[
        str,
        Any,
    ] = {}

    compare: dict[
        str,
        Any,
    ] = {}

    search: dict[
        str,
        Any,
    ] = {}

    for weapon in weapons:

        name = weapon_name(
            weapon
        )

        if not isinstance(
            name,
            str,
        ):
            continue

        classification = (
            weapon.get(
                "classification"
            )
        )

        category = (

            classification.get(
                "category"
            )

            if isinstance(
                classification,
                dict,
            )

            else None
        )

        metrics = weapon_metric_map(
            weapon
        )

        # ----------------------------------------------------
        # Lookup
        # ----------------------------------------------------

        lookup[
            name
        ] = compact_lookup_weapon(
            weapon
        )

        # ----------------------------------------------------
        # Profile
        # ----------------------------------------------------

        strengths: list[
            tuple[
                float,
                dict[str, Any],
            ]
        ] = []

        weaknesses: list[
            tuple[
                float,
                dict[str, Any],
            ]
        ] = []

        typical: list[
            dict[str, Any]
        ] = []

        for (
            metric_key,
            snapshot,
        ) in metrics.items():

            definition = (
                METRIC_BY_KEY[
                    metric_key
                ]
            )

            score = (
                metric_desirability_score(
                    snapshot,
                    definition,
                )
            )

            bucket = profile_bucket(
                snapshot,
                definition,
            )

            item = compact_profile_item(
                snapshot
            )

            if bucket == "strength":

                strengths.append(
                    (
                        score,
                        item,
                    )
                )

            elif bucket == "weakness":

                weaknesses.append(
                    (
                        score,
                        item,
                    )
                )

            else:

                typical.append(
                    item
                )

        strengths.sort(
            key=lambda pair:
                pair[0],
            reverse=True,
        )

        weaknesses.sort(
            key=lambda pair:
                pair[0],
        )

        profiles[
            name
        ] = {

            "weapon":
                name,

            "category":
                category,

            "comparison_group":
                comparison_group_name(
                    category
                ),

            "strengths": [
                item
                for _score, item
                in strengths
            ],

            "weaknesses": [
                item
                for _score, item
                in weaknesses
            ],

            "typical":
                typical,
        }

        # ----------------------------------------------------
        # Compare
        # ----------------------------------------------------

        compare[
            name
        ] = {

            "weapon":
                name,

            "category":
                category,

            "stats":
                comparison_stats(
                    metrics
                ),
        }

        # ----------------------------------------------------
        # Search
        #
        # Keep percentile + band internally because Python
        # needs them for deterministic filtering/ranking.
        # They are NOT all sent back to the LLM.
        # ----------------------------------------------------

        search[
            name
        ] = {

            "weapon":
                name,

            "category":
                category,

            "metrics":
                metrics,
        }

    expected = len(
        weapons
    )

    counts = {

        "lookup":
            len(
                lookup
            ),

        "profiles":
            len(
                profiles
            ),

        "compare":
            len(
                compare
            ),

        "search":
            len(
                search
            ),
    }

    if any(
        count != expected
        for count in counts.values()
    ):

        raise ValueError(
            "View generation lost canonical weapons: "
            f"expected={expected}, counts={counts}"
        )

    views_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    outputs = {

        "lookup":
            views_dir
            / "weapon_lookup.json",

        "profiles":
            views_dir
            / "weapon_profiles.json",

        "compare":
            views_dir
            / "weapon_compare.json",

        "search":
            views_dir
            / "weapon_search.json",
    }

    payloads = {

        "lookup":
            lookup,

        "profiles":
            profiles,

        "compare":
            compare,

        "search":
            search,
    }

    for (
        key,
        path,
    ) in outputs.items():

        save_json(
            path,
            {
                "view_schema_version":
                    VIEW_SCHEMA_VERSION,

                "source_schema_version":
                    source_schema_version,

                "source_database":
                    str(
                        database_path
                    ),

                "weapon_count":
                    counts[
                        key
                    ],

                "weapons":
                    payloads[
                        key
                    ],
            },
        )

    return {

        "view_schema_version":
            VIEW_SCHEMA_VERSION,

        "source_schema_version":
            source_schema_version,

        "weapon_count":
            expected,

        "counts":
            counts,

        "paths": {
            key:
                str(path)

            for (
                key,
                path,
            )
            in outputs.items()
        },
    }


# ============================================================
# RUNTIME VIEW DATABASE
# ============================================================


class WeaponViewDatabase:

    def __init__(
        self,
        path: Path = DATABASE_PATH,
        views_dir: Path = VIEWS_DIR,
    ):

        self.path = Path(
            path
        )

        self.views_dir = Path(
            views_dir
        )

        self.lookup_view = (
            self._load_view(
                "weapon_lookup.json"
            )
        )

        self.profile_view = (
            self._load_view(
                "weapon_profiles.json"
            )
        )

        self.compare_view = (
            self._load_view(
                "weapon_compare.json"
            )
        )

        self.search_view = (
            self._load_view(
                "weapon_search.json"
            )
        )

        self.schema_version = (
            self.lookup_view.get(
                "source_schema_version"
            )
        )

        self.lookup_weapons = (
            self._view_weapons(
                self.lookup_view
            )
        )

        self.profile_weapons = (
            self._view_weapons(
                self.profile_view
            )
        )

        self.compare_weapons_data = (
            self._view_weapons(
                self.compare_view
            )
        )

        self.search_weapons_data = (
            self._view_weapons(
                self.search_view
            )
        )

        counts = {

            len(
                self.lookup_weapons
            ),

            len(
                self.profile_weapons
            ),

            len(
                self.compare_weapons_data
            ),

            len(
                self.search_weapons_data
            ),
        }

        if len(
            counts
        ) != 1:

            raise ValueError(
                "Weapon view counts do not match. "
                "Rebuild the database/views."
            )

        self.index: dict[
            str,
            str,
        ] = {

            normalize_name(
                name
            ):
                name

            for name
            in self.lookup_weapons

            if isinstance(
                name,
                str,
            )
        }

    def _load_view(
        self,
        filename: str,
    ) -> dict[str, Any]:

        path = (
            self.views_dir
            / filename
        )

        if not path.exists():

            raise FileNotFoundError(
                f"Weapon view not found: {path}. "
                "Run "
                "`python -m modules.weapon_database build`."
            )

        payload = load_json(
            path
        )

        if not isinstance(
            payload,
            dict,
        ):

            raise ValueError(
                f"Invalid weapon view: {path}"
            )

        return payload

    @staticmethod
    def _view_weapons(
        payload: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:

        weapons = payload.get(
            "weapons"
        )

        if not isinstance(
            weapons,
            dict,
        ):

            raise ValueError(
                "Weapon view has no 'weapons' object."
            )

        return {

            str(name):
                record

            for (
                name,
                record,
            )
            in weapons.items()

            if isinstance(
                record,
                dict,
            )
        }

    def _exact_name(
        self,
        weapon_name: str,
    ) -> str | None:

        return self.index.get(
            normalize_name(
                weapon_name
            )
        )

    def _not_found(
        self,
        weapon_name: str,
    ) -> dict[str, Any]:

        query = normalize_name(
            weapon_name
        )

        matches = (
            difflib.get_close_matches(
                query,
                list(
                    self.index.keys()
                ),
                n=5,
                cutoff=0.55,
            )
        )

        return {
            "found":
                False,

            "query":
                weapon_name,

            "suggestions": [
                self.index[
                    key
                ]
                for key
                in matches
            ],
        }

    # --------------------------------------------------------
    # TOOL 1
    # --------------------------------------------------------

    def get_weapon(
        self,
        weapon_name: str,
    ) -> dict[str, Any]:

        name = self._exact_name(
            weapon_name
        )

        if name is None:

            return self._not_found(
                weapon_name
            )

        return {
            "found":
                True,

            "query":
                weapon_name,

            "weapon":
                self.lookup_weapons[
                    name
                ],
        }

    # --------------------------------------------------------
    # TOOL 2
    # --------------------------------------------------------

    def get_weapon_profile(
        self,
        weapon_name: str,
    ) -> dict[str, Any]:

        name = self._exact_name(
            weapon_name
        )

        if name is None:

            return self._not_found(
                weapon_name
            )

        profile = (
            self.profile_weapons[
                name
            ]
        )

        return {
            "found":
                True,

            "query":
                weapon_name,

            **profile,

            "note": (
                "Strengths and weaknesses are relative "
                "statistical extremes inside the weapon "
                "population, not an overall weapon rating."
            ),
        }

    # --------------------------------------------------------
    # TOOL 3
    # --------------------------------------------------------

    def compare_weapons(
        self,
        weapon_names: list[str],
    ) -> dict[str, Any]:

        cleaned = [
            name.strip()

            for name
            in weapon_names

            if (
                isinstance(
                    name,
                    str,
                )
                and name.strip()
            )
        ]

        if len(
            cleaned
        ) < 2:

            return {
                "error": (
                    "compare_weapons requires at least "
                    "two weapon names."
                )
            }

        found: list[str] = []

        missing: list[
            dict[str, Any]
        ] = []

        for requested in cleaned:

            name = self._exact_name(
                requested
            )

            if name is None:

                missing.append(
                    self._not_found(
                        requested
                    )
                )

            else:

                found.append(
                    name
                )

        if len(
            found
        ) < 2:

            return {
                "found":
                    False,

                "requested":
                    cleaned,

                "missing":
                    missing,

                "error": (
                    "Fewer than two requested weapons "
                    "were found exactly."
                ),
            }

        stat_maps: dict[
            str,
            dict[str, Any],
        ] = {}

        for name in found:

            record = (
                self.compare_weapons_data[
                    name
                ]
            )

            stats = record.get(
                "stats",
                {},
            )

            if not isinstance(
                stats,
                dict,
            ):
                stats = {}

            stat_maps[
                name
            ] = stats

        common_metrics = set.intersection(
            *(
                set(
                    stats
                )

                for stats
                in stat_maps.values()
            )
        )

        ordered_metrics = sorted(
            common_metrics
        )

        weapon_rows = {
            name: {
                metric:
                    stat_maps[
                        name
                    ][
                        metric
                    ]

                for metric
                in ordered_metrics
            }

            for name
            in found
        }

        return {
            "found":
                True,

            "requested":
                cleaned,

            "weapons_compared":
                found,

            "missing":
                missing,

            "metrics":
                ordered_metrics,

            "weapons":
                weapon_rows,

            "note": (
                "Values are grouped by weapon. "
                "Keep every value associated with its weapon."
            ),
        }


    # --------------------------------------------------------
    # TOOL 4
    # --------------------------------------------------------

    def search_weapons(
        self,
        *,
        criteria: list[str],
        category: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:

        clean_criteria: list[
            str
        ] = []

        for criterion in criteria:

            if (
                isinstance(
                    criterion,
                    str,
                )
                and criterion
                in SEARCH_CRITERIA
                and criterion
                not in clean_criteria
            ):

                clean_criteria.append(
                    criterion
                )

        if not clean_criteria:

            return {
                "error": (
                    "search_weapons requires at least "
                    "one supported statistical criterion."
                ),

                "supported_criteria":
                    SEARCH_CRITERION_NAMES,
            }

        if category == "any":
            category = None

        if category not in {
            None,
            "primary",
            "secondary",
            "melee",
        }:

            return {
                "error": (
                    "Unsupported category. Use primary, "
                    "secondary, melee, or any."
                )
            }

        limit = max(
            1,
            min(
                int(
                    limit
                ),
                20,
            ),
        )

        candidates: list[
            tuple[
                float,
                str,
                dict[str, Any],
            ]
        ] = []

        for (
            name,
            record,
        ) in (
            self.search_weapons_data.items()
        ):

            weapon_category = (
                record.get(
                    "category"
                )
            )

            if (
                category is not None
                and weapon_category
                != category
            ):
                continue

            metrics = record.get(
                "metrics"
            )

            if not isinstance(
                metrics,
                dict,
            ):
                continue

            result_fields: dict[
                str,
                Any,
            ] = {}

            scores: list[
                float
            ] = []

            failed = False

            for criterion in (
                clean_criteria
            ):

                (
                    metric_key,
                    direction,
                ) = SEARCH_CRITERIA[
                    criterion
                ]

                snapshot = metrics.get(
                    metric_key
                )

                if (
                    not isinstance(
                        snapshot,
                        dict,
                    )
                    or not criterion_matches(
                        snapshot,
                        direction,
                    )
                ):

                    failed = True
                    break

                field_name = (
                    comparison_field_name(
                        snapshot
                    )
                )

                result_fields[
                    field_name
                ] = snapshot.get(
                    "value"
                )

                scores.append(
                    criterion_score(
                        snapshot,
                        direction,
                    )
                )

            if failed:
                continue

            score = (
                sum(
                    scores
                )
                / len(
                    scores
                )

                if scores

                else 0.0
            )

            candidates.append(
                (
                    score,
                    name,
                    {
                        "weapon":
                            name,

                        "category":
                            weapon_category,

                        **result_fields,
                    },
                )
            )

        # Percentile-derived ranking stays entirely inside Python.
        candidates.sort(
            key=lambda item: (
                -item[
                    0
                ],
                item[
                    1
                ].casefold(),
            )
        )

        selected = candidates[
            :limit
        ]

        results = [
            {
                "rank":
                    rank,

                **record,
            }

            for (
                rank,
                (
                    _score,
                    _name,
                    record,
                ),
            )

            in enumerate(
                selected,
                start=1,
            )
        ]

        return {
            "found":
                bool(
                    results
                ),

            "category":
                category
                or "any",

            "criteria":
                clean_criteria,

            "result_count":
                len(
                    results
                ),

            "total_matches":
                len(
                    candidates
                ),

            "results":
                results,

            "note": (
                "Every returned weapon satisfies all requested "
                "criteria. Ranking is deterministic; preserve it."
            ),
        }


    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    def summary(
        self,
    ) -> dict[str, Any]:

        return {
            "database":
                str(
                    self.path
                ),

            "views_dir":
                str(
                    self.views_dir
                ),

            "schema_version":
                self.schema_version,

            "weapons_loaded":
                len(
                    self.lookup_weapons
                ),

            "indexed_names":
                len(
                    self.index
                ),

            "tools": [
                "get_weapon",
                "get_weapon_profile",
                "compare_weapons",
                "search_weapons",
            ],
        }


# ============================================================
# CLI
# ============================================================


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic tool-specific weapon views."
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DATABASE_PATH,
    )

    parser.add_argument(
        "--views-dir",
        type=Path,
        default=VIEWS_DIR,
    )

    args = parser.parse_args()

    report = build_weapon_views(
        database_path=args.database,
        views_dir=args.views_dir,
    )

    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
