from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DATABASE_PATH = Path("data/normalized/weapons.json")
OUTPUT_PATH = Path("data/processed/weapon_3b_inputs.json")
DEFAULT_MODEL_PATH = Path("models/Qwen2.5-3B-Instruct-Q4_K_M.gguf")
DEFAULT_ANALYSIS_DIR = Path("data/generated/weapon_analysis")

PACKET_SCHEMA_VERSION = "1.1.0"
MODULE_VERSION = "2.1.0"


# =============================================================================
# Generic helpers
# =============================================================================

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def remove_empty(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            cleaned = remove_empty(child)
            if cleaned not in (None, "", [], {}):
                result[key] = cleaned
        return result

    if isinstance(value, list):
        result = []
        for child in value:
            cleaned = remove_empty(child)
            if cleaned not in (None, "", [], {}):
                result.append(cleaned)
        return result

    return value


def clean_scalar(value: Any) -> Any:
    if isinstance(value, float):
        nearest_integer = round(value)

        if abs(value - nearest_integer) < 0.00001:
            return int(nearest_integer)

        return round(value, 6)

    return value


def pretty(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )


def get_nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data

    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def fraction_to_percent(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return clean_scalar(value * 100)
    return value


# =============================================================================
# Weapon lookup
# =============================================================================

def find_weapon(
    database: dict[str, Any],
    query: str,
) -> tuple[str, dict[str, Any]] | None:
    weapons = database.get("weapons", {})

    if query in weapons:
        return query, weapons[query]

    q = query.casefold()
    exact = []
    partial = []

    for weapon_id, weapon in weapons.items():
        name = weapon.get("identity", {}).get("name")

        if not isinstance(name, str):
            continue

        if name.casefold() == q:
            exact.append((weapon_id, weapon))
        elif q in name.casefold():
            partial.append((weapon_id, weapon))

    if exact:
        return exact[0]

    if len(partial) == 1:
        return partial[0]

    return None


# =============================================================================
# Compact deterministic packet builder
# =============================================================================

def compact_stat(value: Any) -> Any:
    if not isinstance(value, dict):
        return clean_scalar(value)

    allowed = ("value", "percentile", "extreme")
    result = {
        key: clean_scalar(value[key])
        for key in allowed
        if key in value
    }

    return result or value


def compact_damage(weapon: dict[str, Any]) -> dict[str, Any]:
    damage = weapon.get("damage", {})
    result: dict[str, Any] = {}

    if damage.get("root_total") is not None:
        result["root_total"] = clean_scalar(damage["root_total"])

    if isinstance(damage.get("types"), dict):
        result["types"] = {
            key: clean_scalar(value)
            for key, value in damage["types"].items()
        }

    if isinstance(damage.get("distribution"), dict):
        result["distribution"] = {
            key: clean_scalar(value)
            for key, value in damage["distribution"].items()
        }

    if damage.get("base_volley_damage") is not None:
        result["base_volley_damage"] = compact_stat(
            damage["base_volley_damage"]
        )

    return result


def compact_critical(weapon: dict[str, Any]) -> dict[str, Any]:
    critical = weapon.get("critical", {})
    result: dict[str, Any] = {}

    if not isinstance(critical, dict):
        return result

    if critical.get("chance") is not None:
        result["chance"] = compact_stat(critical["chance"])

    if critical.get("multiplier") is not None:
        result["multiplier"] = compact_stat(critical["multiplier"])

    return result


def compact_status(weapon: dict[str, Any]) -> Any:
    status = weapon.get("status", {})

    if not isinstance(status, dict):
        return None

    if status.get("chance") is None:
        return None

    return compact_stat(status["chance"])


def compact_handling(weapon: dict[str, Any]) -> dict[str, Any]:
    handling = weapon.get("handling", {})
    result: dict[str, Any] = {}

    if not isinstance(handling, dict):
        return result

    wanted = (
        "fire_rate",
        "attack_speed",
        "magazine_size",
        "reload_duration_seconds",
        "range_meters",
        "follow_through",
        "combo_duration_seconds",
        "heavy_attack_damage",
        "heavy_windup_seconds",
    )

    for field in wanted:
        if handling.get(field) is not None:
            result[field] = compact_stat(handling[field])

    return result


def compact_mechanics(weapon: dict[str, Any]) -> dict[str, Any]:
    mechanics = weapon.get("mechanics", {})
    result: dict[str, Any] = {}

    if not isinstance(mechanics, dict):
        return result

    if mechanics.get("trigger") is not None:
        result["trigger"] = mechanics["trigger"]

    if mechanics.get("multishot") is not None:
        result["multishot"] = clean_scalar(mechanics["multishot"])

    tags = mechanics.get("mechanical_tags")

    if isinstance(tags, list) and tags:
        result["tags"] = tags

    return result


def compact_riven(weapon: dict[str, Any]) -> dict[str, Any] | None:
    riven = weapon.get("riven")

    if not isinstance(riven, dict):
        return None

    wanted = ("disposition", "rating", "warning")
    result = {
        key: clean_scalar(riven[key])
        for key in wanted
        if key in riven
    }

    return result or None


def compact_component(component: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for field in (
        "path",
        "damage",
        "total_damage",
        "status_chance",
    ):
        if component.get(field) is None:
            continue

        value = component[field]

        if isinstance(value, dict):
            value = {
                key: clean_scalar(child)
                for key, child in value.items()
            }
        else:
            value = clean_scalar(value)

        result[field] = value

    return result


def compact_behaviour_record(record: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    if record.get("state") is not None:
        result["state"] = record["state"]

    if record.get("fire_iterations") is not None:
        result["fire_iterations"] = clean_scalar(
            record["fire_iterations"]
        )

    if isinstance(record.get("burst"), dict):
        result["burst"] = {
            key: clean_scalar(value)
            for key, value in record["burst"].items()
        }

    components = record.get("components")

    if isinstance(components, list):
        compact_components = [
            compact_component(component)
            for component in components
            if isinstance(component, dict)
        ]

        if compact_components:
            result["components"] = compact_components

    return result


def primary_record_adds_new_information(
    record: dict[str, Any],
) -> bool:
    if isinstance(record.get("burst"), dict) and record["burst"]:
        return True

    fire_iterations = record.get("fire_iterations")

    if (
        isinstance(fire_iterations, (int, float))
        and fire_iterations != 1
    ):
        return True

    components = record.get("components")

    if not isinstance(components, list):
        return False

    valid = [
        component
        for component in components
        if isinstance(component, dict)
    ]

    if len(valid) > 1:
        return True

    if len(valid) == 1:
        path = valid[0].get("path")

        if path not in (None, "", "root", "impact"):
            return True

    return False


def compact_behaviour_evidence(
    weapon: dict[str, Any],
) -> dict[str, Any]:
    records = weapon.get("behaviour_records")

    if not isinstance(records, list):
        return {}

    primary_additional = []
    alternate_modes = []

    for record in records:
        if not isinstance(record, dict):
            continue

        role = record.get("role")

        if role == "primary":
            if primary_record_adds_new_information(record):
                primary_additional.append(
                    compact_behaviour_record(record)
                )

        elif role == "alternate_mode":
            alternate_modes.append(
                compact_behaviour_record(record)
            )

        # "unclassified" intentionally stays in the canonical DB only.

    result: dict[str, Any] = {}

    if primary_additional:
        result["primary_additional"] = primary_additional

    if alternate_modes:
        result["alternate_modes"] = alternate_modes

    return result


def collect_extremes(
    value: Any,
    path: tuple[str, ...] = (),
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []

    if isinstance(value, dict):
        if "percentile" in value and "extreme" in value:
            stat_name = path[-1] if path else "unknown"
            result.append(
                (
                    stat_name,
                    str(value["extreme"]),
                )
            )
            return result

        for key, child in value.items():
            result.extend(
                collect_extremes(
                    child,
                    path + (str(key),),
                )
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(
                collect_extremes(
                    child,
                    path + (str(index),),
                )
            )

    return result


def group_extremes(
    packet: dict[str, Any],
) -> dict[str, list[str]]:
    found = collect_extremes(
        {
            "damage": packet.get("damage", {}),
            "critical": packet.get("critical", {}),
            "status_chance": packet.get("status_chance"),
            "handling": packet.get("handling", {}),
        }
    )

    grouped: dict[str, list[str]] = {}

    for stat_name, level in found:
        grouped.setdefault(level, [])

        if stat_name not in grouped[level]:
            grouped[level].append(stat_name)

    order = (
        "exceptionally_low",
        "very_low",
        "very_high",
        "exceptionally_high",
    )

    return {
        level: grouped[level]
        for level in order
        if level in grouped
    }


def build_packet(
    weapon_id: str,
    weapon: dict[str, Any],
) -> dict[str, Any]:
    identity = weapon.get("identity", {})
    qualitative = weapon.get("qualitative_context", {})
    classification = weapon.get("classification", {})
    population = weapon.get("population", {})

    packet: dict[str, Any] = {
        "weapon": {
            "name": identity.get("name"),
            "category": classification.get("category"),
            "variant_type": classification.get("variant_type"),
        },
        "official_description": qualitative.get(
            "official_description"
        ),
        "comparison_population": {
            "group": population.get("group"),
            "size": population.get("size"),
        },
        "damage": compact_damage(weapon),
        "critical": compact_critical(weapon),
        "status_chance": compact_status(weapon),
        "handling": compact_handling(weapon),
        "mechanics": compact_mechanics(weapon),
        "riven": compact_riven(weapon),
        "behaviour_evidence": compact_behaviour_evidence(weapon),
    }

    packet = remove_empty(packet)

    extremes = group_extremes(packet)

    if extremes:
        packet["notable_extremes"] = extremes

    return packet


# =============================================================================
# Semantic adapters for the 3B
# =============================================================================

def semantic_rating(
    extreme: Any,
    dimension: str,
) -> Any:
    if not isinstance(extreme, str):
        return None

    mappings = {
        "fire_rate": {
            "exceptionally_low": "exceptionally_slow",
            "very_low": "very_slow",
            "very_high": "very_fast",
            "exceptionally_high": "exceptionally_fast",
        },
        "attack_speed": {
            "exceptionally_low": "exceptionally_slow",
            "very_low": "very_slow",
            "very_high": "very_fast",
            "exceptionally_high": "exceptionally_fast",
        },
        "magazine_size": {
            "exceptionally_low": "exceptionally_small",
            "very_low": "very_small",
            "very_high": "very_large",
            "exceptionally_high": "exceptionally_large",
        },
        "reload_duration": {
            "exceptionally_low": "exceptionally_short",
            "very_low": "very_short",
            "very_high": "very_long",
            "exceptionally_high": "exceptionally_long",
        },
        "range": {
            "exceptionally_low": "exceptionally_short_reach",
            "very_low": "very_short_reach",
            "very_high": "very_long_reach",
            "exceptionally_high": "exceptionally_long_reach",
        },
        "heavy_windup": {
            "exceptionally_low": "exceptionally_short",
            "very_low": "very_short",
            "very_high": "very_long",
            "exceptionally_high": "exceptionally_long",
        },
    }

    mapping = mappings.get(dimension)

    if mapping:
        return mapping.get(extreme, extreme)

    return extreme


def semantic_stat(
    stat: Any,
    *,
    value_name: str,
    dimension: str | None = None,
    percent_value: bool = False,
) -> Any:
    if not isinstance(stat, dict):
        return stat

    result: dict[str, Any] = {}

    if "value" in stat:
        value = stat["value"]

        if percent_value:
            value = fraction_to_percent(value)
        else:
            value = clean_scalar(value)

        result[value_name] = value

    if "percentile" in stat:
        result["relative_percentile"] = clean_scalar(
            stat["percentile"]
        )

    if "extreme" in stat:
        result["relative_rating"] = semantic_rating(
            stat["extreme"],
            dimension or "",
        )

    return remove_empty(result)


def semantic_trigger(trigger: Any) -> Any:
    if not isinstance(trigger, str):
        return trigger

    meanings = {
        "AUTO": (
            "fires continuously while the fire control is held, "
            "until firing stops or the magazine is empty"
        ),
        "SEMI": (
            "fires one firing action for each activation of the fire control"
        ),
        "BURST": (
            "fires a fixed burst for each activation of the fire control"
        ),
        "CHARGE": (
            "uses a charge action before firing"
        ),
    }

    result = {"type": trigger}

    if trigger in meanings:
        result["meaning"] = meanings[trigger]

    return result


def semantic_multishot(multishot: Any) -> Any:
    if multishot is None:
        return None

    return {
        "projectiles_per_firing_action": clean_scalar(multishot)
    }


# =============================================================================
# Segment definitions
# =============================================================================

DIRECT_DAMAGE_INSTRUCTIONS = """Analyze only direct-hit and critical characteristics.

The data fields already contain explicit units and separate raw values from relative percentiles.
Use relative_percentile only to describe how unusual a statistic is inside the comparison population.
Do not replace the raw value with its percentile.
Do not discuss status, fire rate, magazine, reload, Riven disposition, builds, or overall weapon quality.
"""


STATUS_INSTRUCTIONS = """Analyze only status-application characteristics.

status_chance.chance_percent is the actual probability of applying a status effect per hit.
relative_percentile only says where that chance ranks inside the comparison population.
damage_distribution_percent describes the percentage composition of base damage; it does not describe total damage output.
Fire rate, attack speed, and projectiles per firing action can create more hit opportunities, but do not invent a proc-per-second formula.
Do not discuss critical hits, reload, magazine size, Riven disposition, builds, or overall weapon quality.
"""


RANGED_HANDLING_INSTRUCTIONS = """Analyze only firing rhythm and sustained-use handling.

The trigger object explicitly defines how the trigger behaves.
Fire rate is expressed in rounds per second.
Magazine size is expressed in rounds available before reloading.
Reload is expressed in seconds; a rating such as very_long means a comparatively long reload.
Do not claim AUTO removes the need to reload.
Do not discuss damage, critical hits, status effects, Riven disposition, builds, or overall weapon quality.
"""


MELEE_HANDLING_INSTRUCTIONS = """Analyze only melee handling and reach.

attack_speed_value is the source attack-speed value for the weapon.
range_meters is weapon reach in meters.
follow_through.damage_retention_factor describes damage retained as a strike continues through multiple enemies.
combo_duration_seconds is the combo retention duration.
heavy_attack_damage is the source heavy-attack damage value.
heavy_windup_seconds is preparation time for a heavy attack.
Relative percentiles describe position inside the comparison population, not overall weapon quality.
"""


IDENTITY_INSTRUCTIONS = """Analyze only clearly stated weapon identity and mechanics.

Use the official description as qualitative context.
Structured mechanics are more reliable than flavor text.
The trigger object already defines its meaning.
projectiles_per_firing_action is a literal projectile count, not a qualitative mechanic name.
Mention a mechanic only when explicitly supported by supplied data.
Do not evaluate numerical performance.
Do not invent hidden modes, builds, mods, evolutions, community opinions, or overall weapon quality.
"""


def build_direct_damage_segment(
    packet: dict[str, Any],
) -> dict[str, Any]:
    damage = packet.get("damage", {})
    critical = packet.get("critical", {})

    return remove_empty(
        {
            "weapon": packet.get("weapon"),
            "comparison_population": packet.get(
                "comparison_population"
            ),
            "base_volley_damage": semantic_stat(
                damage.get("base_volley_damage"),
                value_name="damage_per_firing_action",
            ),
            "critical_chance": semantic_stat(
                critical.get("chance"),
                value_name="chance_percent",
                percent_value=True,
            ),
            "critical_multiplier": semantic_stat(
                critical.get("multiplier"),
                value_name="multiplier_x",
            ),
        }
    )


def build_status_segment(
    packet: dict[str, Any],
) -> dict[str, Any]:
    distribution = get_nested(
        packet,
        "damage",
        "distribution",
    )

    if isinstance(distribution, dict):
        distribution = {
            key: fraction_to_percent(value)
            for key, value in distribution.items()
        }

    return remove_empty(
        {
            "weapon": packet.get("weapon"),
            "comparison_population": packet.get(
                "comparison_population"
            ),
            "status_chance": semantic_stat(
                packet.get("status_chance"),
                value_name="chance_percent",
                percent_value=True,
            ),
            "damage_distribution_percent": distribution,
            "fire_rate": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "fire_rate",
                ),
                value_name="rounds_per_second",
                dimension="fire_rate",
            ),
            "attack_speed": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "attack_speed",
                ),
                value_name="attack_speed_value",
                dimension="attack_speed",
            ),
            "multishot": semantic_multishot(
                get_nested(
                    packet,
                    "mechanics",
                    "multishot",
                )
            ),
        }
    )


def build_ranged_handling_segment(
    packet: dict[str, Any],
) -> dict[str, Any]:
    return remove_empty(
        {
            "weapon": packet.get("weapon"),
            "comparison_population": packet.get(
                "comparison_population"
            ),
            "trigger": semantic_trigger(
                get_nested(
                    packet,
                    "mechanics",
                    "trigger",
                )
            ),
            "fire_rate": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "fire_rate",
                ),
                value_name="rounds_per_second",
                dimension="fire_rate",
            ),
            "magazine": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "magazine_size",
                ),
                value_name="rounds_before_reload",
                dimension="magazine_size",
            ),
            "reload": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "reload_duration_seconds",
                ),
                value_name="seconds",
                dimension="reload_duration",
            ),
        }
    )


def build_melee_handling_segment(
    packet: dict[str, Any],
) -> dict[str, Any]:
    follow_through = semantic_stat(
        get_nested(
            packet,
            "handling",
            "follow_through",
        ),
        value_name="damage_retention_factor",
    )

    return remove_empty(
        {
            "weapon": packet.get("weapon"),
            "comparison_population": packet.get(
                "comparison_population"
            ),
            "attack_speed": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "attack_speed",
                ),
                value_name="attack_speed_value",
                dimension="attack_speed",
            ),
            "range": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "range_meters",
                ),
                value_name="meters",
                dimension="range",
            ),
            "follow_through": follow_through,
            "combo_duration": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "combo_duration_seconds",
                ),
                value_name="seconds",
            ),
            "heavy_attack_damage": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "heavy_attack_damage",
                ),
                value_name="damage",
            ),
            "heavy_windup": semantic_stat(
                get_nested(
                    packet,
                    "handling",
                    "heavy_windup_seconds",
                ),
                value_name="seconds",
                dimension="heavy_windup",
            ),
        }
    )


def build_identity_segment(
    packet: dict[str, Any],
) -> dict[str, Any]:
    mechanics = packet.get("mechanics", {})

    semantic_mechanics = remove_empty(
        {
            "trigger": semantic_trigger(
                mechanics.get("trigger")
                if isinstance(mechanics, dict)
                else None
            ),
            "multishot": semantic_multishot(
                mechanics.get("multishot")
                if isinstance(mechanics, dict)
                else None
            ),
            "tags": (
                mechanics.get("tags")
                if isinstance(mechanics, dict)
                else None
            ),
        }
    )

    return remove_empty(
        {
            "weapon": packet.get("weapon"),
            "official_description": packet.get(
                "official_description"
            ),
            "mechanics": semantic_mechanics,
            "behaviour_evidence": packet.get(
                "behaviour_evidence"
            ),
        }
    )


def segment_has_payload(
    data: dict[str, Any],
) -> bool:
    ignored = {
        "weapon",
        "comparison_population",
    }

    return any(
        key not in ignored
        and value not in (None, "", [], {})
        for key, value in data.items()
    )


def build_segments(
    packet: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    category = get_nested(
        packet,
        "weapon",
        "category",
    )

    segments: dict[str, dict[str, Any]] = {
        "direct_damage_and_critical": {
            "instructions": DIRECT_DAMAGE_INSTRUCTIONS,
            "data": build_direct_damage_segment(packet),
        },
        "status_application": {
            "instructions": STATUS_INSTRUCTIONS,
            "data": build_status_segment(packet),
        },
        "identity_and_mechanics": {
            "instructions": IDENTITY_INSTRUCTIONS,
            "data": build_identity_segment(packet),
        },
    }

    if category == "melee":
        segments["handling"] = {
            "instructions": MELEE_HANDLING_INSTRUCTIONS,
            "data": build_melee_handling_segment(packet),
        }
    else:
        segments["handling"] = {
            "instructions": RANGED_HANDLING_INSTRUCTIONS,
            "data": build_ranged_handling_segment(packet),
        }

    return {
        name: segment
        for name, segment in segments.items()
        if segment_has_payload(segment["data"])
    }


# =============================================================================
# Prompt construction
# =============================================================================

def build_segment_messages(
    *,
    instructions: str,
    data: dict[str, Any],
    language: str,
) -> list[dict[str, str]]:
    user_prompt = f"""TASK:
{instructions.strip()}

OUTPUT:
Return one short paragraph in {language}.
Use only the supplied data.
Do not add facts that are not present.

DATA:
{pretty(data)}
"""

    return [
        {
            "role": "system",
            "content": (
                "You analyze one narrow aspect of one Warframe weapon. "
                "Raw values and relative percentiles are different concepts. "
                "Never substitute one for the other. "
                "Do not infer unrelated mechanics."
            ),
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]


def build_synthesis_messages(
    *,
    packet: dict[str, Any],
    analyses: dict[str, str],
    language: str,
) -> list[dict[str, str]]:
    synthesis_data = remove_empty(
        {
            "weapon": packet.get("weapon"),
            "direct_damage_and_critical": analyses.get(
                "direct_damage_and_critical"
            ),
            "status_application": analyses.get(
                "status_application"
            ),
            "handling": analyses.get("handling"),
            "identity_and_mechanics": analyses.get(
                "identity_and_mechanics"
            ),
            "riven": packet.get("riven"),
        }
    )

    user_prompt = f"""TASK:
Combine the independent analyses below into one concise description of the weapon.

RULES:
1. Use only facts already present in the segment analyses or deterministic Riven data.
2. Do not add mechanics, builds, mods, formulas, evolutions, or community opinions.
3. Do not reinterpret a segment into a different meaning.
4. Merge repetition instead of repeating the same fact.
5. Riven disposition describes Riven stat scaling, not base weapon strength.

OUTPUT:
Write one clear player-facing paragraph in {language}.

SEGMENT_ANALYSES:
{pretty(synthesis_data)}
"""

    return [
        {
            "role": "system",
            "content": (
                "You are only a synthesis layer. "
                "Combine supplied conclusions without introducing new facts."
            ),
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]


def build_prompt(
    packet: dict[str, Any],
    language: str = "Spanish",
) -> dict[str, Any]:
    prompts = {}

    for name, segment in build_segments(packet).items():
        prompts[name] = build_segment_messages(
            instructions=segment["instructions"],
            data=segment["data"],
            language=language,
        )

    prompts["synthesis_note"] = (
        "The synthesis prompt is created only after the independent segment "
        "responses exist. It receives those responses, not the full weapon packet."
    )

    return prompts


# =============================================================================
# Model execution
# =============================================================================

def call_model(
    llm: Any,
    messages: list[dict[str, str]],
    *,
    temperature: float,
    max_tokens: int,
) -> str:
    response = llm.create_chat_completion(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    text = response["choices"][0]["message"]["content"]

    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("The model returned an empty response.")

    return text.strip()


def analyze_packet(
    llm: Any,
    packet: dict[str, Any],
    *,
    language: str,
    temperature: float,
    segment_max_tokens: int,
    synthesis_max_tokens: int,
) -> dict[str, Any]:
    analyses: dict[str, str] = {}

    # Every segment starts with a completely new messages list.
    for name, segment in build_segments(packet).items():
        messages = build_segment_messages(
            instructions=segment["instructions"],
            data=segment["data"],
            language=language,
        )

        analyses[name] = call_model(
            llm,
            messages,
            temperature=temperature,
            max_tokens=segment_max_tokens,
        )

    # Final call receives only the conclusions plus deterministic Riven data.
    final_description = call_model(
        llm,
        build_synthesis_messages(
            packet=packet,
            analyses=analyses,
            language=language,
        ),
        temperature=temperature,
        max_tokens=synthesis_max_tokens,
    )

    return {
        "module_version": MODULE_VERSION,
        "packet_schema_version": PACKET_SCHEMA_VERSION,
        "weapon": packet.get("weapon"),
        "segments": analyses,
        "riven": packet.get("riven"),
        "final_description": final_description,
    }


# =============================================================================
# Batch packet library
# =============================================================================

def build_all(
    database_path: Path = DATABASE_PATH,
    output_path: Path = OUTPUT_PATH,
) -> dict[str, Any]:
    database = load_json(database_path)
    weapons = database.get("weapons", {})

    packets = {
        weapon_id: build_packet(weapon_id, weapon)
        for weapon_id, weapon in weapons.items()
        if isinstance(weapon, dict)
    }

    output = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "weapon_count": len(packets),
        "weapons": packets,
    }

    save_json(output_path, output)

    return output


# =============================================================================
# Persistence
# =============================================================================

def safe_filename(name: str) -> str:
    cleaned = []

    for char in name:
        if char.isalnum() or char in ("-", "_"):
            cleaned.append(char)
        elif char.isspace():
            cleaned.append("_")

    return "".join(cleaned) or "weapon"


def save_analysis(
    result: dict[str, Any],
    output_dir: Path,
) -> Path:
    name = get_nested(
        result,
        "weapon",
        "name",
    ) or "weapon"

    path = output_dir / f"{safe_filename(str(name))}.json"
    save_json(path, result)

    return path


# =============================================================================
# CLI helpers
# =============================================================================

def load_weapon_packet(
    query: str,
    database_path: Path,
) -> dict[str, Any]:
    database = load_json(database_path)
    result = find_weapon(database, query)

    if result is None:
        raise SystemExit(
            f"Weapon not found or query is ambiguous: {query!r}"
        )

    weapon_id, weapon = result

    return build_packet(
        weapon_id,
        weapon,
    )


def command_show(args: argparse.Namespace) -> None:
    packet = load_weapon_packet(
        args.query,
        Path(args.database),
    )

    print(pretty(packet))


def command_build(args: argparse.Namespace) -> None:
    output = build_all(
        database_path=Path(args.database),
        output_path=Path(args.output),
    )

    print("========================================")
    print("3B INPUT LIBRARY BUILT")
    print("========================================")
    print(f"Schema:  {PACKET_SCHEMA_VERSION}")
    print(f"Weapons: {output['weapon_count']}")
    print(f"Output:  {args.output}")


def command_segments(args: argparse.Namespace) -> None:
    packet = load_weapon_packet(
        args.query,
        Path(args.database),
    )

    segments = {
        name: segment["data"]
        for name, segment in build_segments(packet).items()
    }

    print(pretty(segments))


def command_prompt(args: argparse.Namespace) -> None:
    packet = load_weapon_packet(
        args.query,
        Path(args.database),
    )

    print(
        pretty(
            build_prompt(
                packet,
                language=args.language,
            )
        )
    )


def command_analyze(args: argparse.Namespace) -> None:
    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise SystemExit(
            "llama-cpp-python is required only for the 'analyze' command."
        ) from exc

    model_path = Path(args.model)

    if not model_path.exists():
        raise SystemExit(
            f"Model not found: {model_path}"
        )

    packet = load_weapon_packet(
        args.query,
        Path(args.database),
    )

    print("========================================")
    print("LOADING MODEL")
    print("========================================")
    print(model_path)

    llm = Llama(
        model_path=str(model_path),
        n_ctx=args.n_ctx,
        n_threads=args.n_threads,
        verbose=args.verbose,
    )

    print()
    print("========================================")
    print("INDEPENDENT SEGMENTS")
    print("========================================")

    result = analyze_packet(
        llm,
        packet,
        language=args.language,
        temperature=args.temperature,
        segment_max_tokens=args.segment_max_tokens,
        synthesis_max_tokens=args.synthesis_max_tokens,
    )

    for name, text in result["segments"].items():
        print()
        print(f"[{name}]")
        print(text)

    print()
    print("========================================")
    print("FINAL SYNTHESIS")
    print("========================================")
    print(result["final_description"])

    if args.save:
        path = save_analysis(
            result,
            Path(args.output_dir),
        )

        print()
        print(f"Saved: {path}")


# =============================================================================
# CLI
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build compact weapon packets and analyze them "
            "through independent semantically explicit LLM calls."
        )
    )

    subparsers = parser.add_subparsers(
        dest="command"
    )

    show = subparsers.add_parser(
        "show",
        help="Show the compact deterministic packet for one weapon.",
    )
    show.add_argument("query")
    show.add_argument(
        "--database",
        default=str(DATABASE_PATH),
    )
    show.set_defaults(func=command_show)

    build = subparsers.add_parser(
        "build",
        help="Build compact packets for every weapon.",
    )
    build.add_argument(
        "--database",
        default=str(DATABASE_PATH),
    )
    build.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
    )
    build.set_defaults(func=command_build)

    segments = subparsers.add_parser(
        "segments",
        help="Show semantically explicit independent data blocks.",
    )
    segments.add_argument("query")
    segments.add_argument(
        "--database",
        default=str(DATABASE_PATH),
    )
    segments.set_defaults(func=command_segments)

    prompt = subparsers.add_parser(
        "prompt",
        help="Show the independent prompts sent to the model.",
    )
    prompt.add_argument("query")
    prompt.add_argument(
        "--database",
        default=str(DATABASE_PATH),
    )
    prompt.add_argument(
        "--language",
        default="Spanish",
    )
    prompt.set_defaults(func=command_prompt)

    analyze = subparsers.add_parser(
        "analyze",
        help="Run independent segment calls and one final synthesis.",
    )
    analyze.add_argument("query")
    analyze.add_argument(
        "--database",
        default=str(DATABASE_PATH),
    )
    analyze.add_argument(
        "--model",
        default=str(DEFAULT_MODEL_PATH),
    )
    analyze.add_argument(
        "--language",
        default="Spanish",
    )
    analyze.add_argument(
        "--n-ctx",
        type=int,
        default=2048,
    )
    analyze.add_argument(
        "--n-threads",
        type=int,
        default=4,
    )
    analyze.add_argument(
        "--temperature",
        type=float,
        default=0.1,
    )
    analyze.add_argument(
        "--segment-max-tokens",
        type=int,
        default=120,
    )
    analyze.add_argument(
        "--synthesis-max-tokens",
        type=int,
        default=240,
    )
    analyze.add_argument(
        "--save",
        action="store_true",
    )
    analyze.add_argument(
        "--output-dir",
        default=str(DEFAULT_ANALYSIS_DIR),
    )
    analyze.add_argument(
        "--verbose",
        action="store_true",
    )
    analyze.set_defaults(func=command_analyze)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not getattr(args, "command", None):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()