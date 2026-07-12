"""Select and serialize only the data needed by each AI stage.

This module intentionally contains no Warframe analysis rules. Stable domain
context, role definitions, and few-shot examples live in ``modules.ai``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


# Internal enum values. The model must copy these exact keys in JSON output.
JOB_KEYS = (
    "sustained_damage",
    "focused_damage",
    "group_clear",
    "area_control",
    "status_application",
    "enemy_priming",
    "precision_attacks",
    "heavy_attacks",
    "general_use",
)

COMFORT_KEYS = (
    "comfortable",
    "manageable",
    "demanding",
    "undetermined",
)


class PromptBuilderError(ValueError):
    """Required parsed sections are missing or malformed."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PromptBuilderError(f"Missing required section: {name}.")
    return value


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _compact(values: Mapping[str, Any]) -> dict[str, Any]:
    """Remove absent values without deleting valid zeros or ``False``."""

    return {
        key: value
        for key, value in values.items()
        if _present(value)
    }


def _json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _common(parsed: Mapping[str, Any]) -> dict[str, Any]:
    # weapon_name is deliberately excluded. The model must not use identity to
    # fill missing mechanics from memory.
    return _compact(
        {
            "weapon_category": parsed.get("weapon_category"),
            "special_mechanic": parsed.get("special_mechanic"),
        }
    )


def _core(parsed: Mapping[str, Any]) -> dict[str, Any]:
    core = _mapping(parsed.get("core_stats"), "core_stats")
    return _compact(
        {
            "critical_chance_percent": core.get("critical_chance_percent"),
            "critical_multiplier": core.get("critical_multiplier"),
            "status_chance_percent": core.get("status_chance_percent"),
        }
    )


def _damage(parsed: Mapping[str, Any]) -> dict[str, Any]:
    damage = _mapping(parsed.get("damage"), "damage")
    components = _mapping(damage.get("components"), "damage.components")
    return _compact(
        {
            "base_damage_total": damage.get("base_total"),
            "damage_components": dict(components),
            "dominant_damage_type": damage.get("dominant_type"),
        }
    )


def _ranged_sections(
    parsed: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    ranged = _mapping(parsed.get("ranged"), "ranged")
    classification = _mapping(
        ranged.get("classification"),
        "ranged.classification",
    )
    stats = _mapping(ranged.get("stats"), "ranged.stats")
    conditional = _mapping(
        ranged.get("conditional_stats"),
        "ranged.conditional_stats",
    )
    return classification, stats, conditional


def _ranged_behavior(parsed: Mapping[str, Any]) -> dict[str, Any]:
    classification, stats, conditional = _ranged_sections(parsed)
    return _compact(
        {
            **_common(parsed),
            "firing_mode": classification.get("firing_mode"),
            "damage_delivery": classification.get("damage_delivery"),
            "reload_type": classification.get("reload_type"),
            "has_multiple_pellets": classification.get(
                "has_multiple_pellets"
            ),
            "is_explosive": classification.get("is_explosive"),
            "fire_rate": stats.get("fire_rate"),
            "magazine_size": stats.get("magazine_size"),
            "multishot": stats.get("multishot"),
            "shots_per_burst": conditional.get("shots_per_burst"),
            "pellet_count": conditional.get("pellet_count"),
            "charge_time": conditional.get("charge_time"),
            "projectile_speed": conditional.get("projectile_speed"),
            "beam_range": conditional.get("beam_range"),
            "explosion_radius": conditional.get("explosion_radius"),
        }
    )


def _melee_behavior(parsed: Mapping[str, Any]) -> dict[str, Any]:
    melee = _mapping(parsed.get("melee"), "melee")
    stats = _mapping(melee.get("stats"), "melee.stats")
    return _compact(
        {
            **_common(parsed),
            "attack_speed": stats.get("attack_speed"),
            "range": stats.get("range"),
            "heavy_attack_damage": stats.get("heavy_attack_damage"),
            "heavy_attack_wind_up": stats.get("heavy_attack_wind_up"),
        }
    )


def behavior_data(parsed: Mapping[str, Any]) -> dict[str, Any]:
    category = parsed.get("weapon_category")
    if category in {"primary", "secondary"}:
        return _ranged_behavior(parsed)
    if category == "melee":
        return _melee_behavior(parsed)
    raise PromptBuilderError("Invalid weapon_category.")


def job_data(parsed: Mapping[str, Any]) -> dict[str, Any]:
    data = {
        **behavior_data(parsed),
        **_core(parsed),
        **_damage(parsed),
    }

    if parsed.get("weapon_category") in {"primary", "secondary"}:
        classification, stats, conditional = _ranged_sections(parsed)
        data.update(
            _compact(
                {
                    "reload_time": stats.get("reload_time"),
                    "ammo_capacity": stats.get("ammo_capacity"),
                    "accuracy": stats.get("accuracy"),
                    "recoil": stats.get("recoil"),
                    "punch_through": stats.get("punch_through"),
                    "battery_recharge_rate": conditional.get(
                        "battery_recharge_rate"
                    ),
                    "reload_per_round": conditional.get(
                        "reload_per_round"
                    ),
                    "reload_type": classification.get("reload_type"),
                }
            )
        )

    return data


def available_improvement_parameters(
    parsed: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return exact internal parameter keys the model may select."""

    parameters = [
        "base_damage",
        "critical_chance",
        "critical_multiplier",
        "status_chance",
    ]

    category = parsed.get("weapon_category")

    if category in {"primary", "secondary"}:
        _, stats, conditional = _ranged_sections(parsed)
        field_map = (
            (stats.get("fire_rate"), "fire_rate"),
            (stats.get("multishot"), "multishot"),
            (stats.get("magazine_size"), "magazine_size"),
            (stats.get("reload_time"), "reload_time"),
            (stats.get("ammo_capacity"), "ammo_capacity"),
            (stats.get("accuracy"), "accuracy"),
            (stats.get("recoil"), "recoil"),
            (stats.get("punch_through"), "punch_through"),
            (conditional.get("projectile_speed"), "projectile_speed"),
            (conditional.get("beam_range"), "beam_range"),
            (conditional.get("explosion_radius"), "explosion_radius"),
            (conditional.get("charge_time"), "charge_time"),
            (
                conditional.get("battery_recharge_rate"),
                "battery_recharge_rate",
            ),
            (conditional.get("reload_per_round"), "reload_per_round"),
        )
        parameters.extend(
            key for value, key in field_map if _present(value)
        )

    elif category == "melee":
        melee = _mapping(parsed.get("melee"), "melee")
        stats = _mapping(melee.get("stats"), "melee.stats")
        field_map = (
            (stats.get("attack_speed"), "attack_speed"),
            (stats.get("range"), "melee_range"),
            (stats.get("heavy_attack_damage"), "heavy_attack_damage"),
            (stats.get("heavy_attack_wind_up"), "heavy_attack_wind_up"),
        )
        parameters.extend(
            key for value, key in field_map if _present(value)
        )

    return tuple(dict.fromkeys(parameters))


def improvement_data(parsed: Mapping[str, Any]) -> dict[str, Any]:
    return job_data(parsed)


def comfort_data(parsed: Mapping[str, Any]) -> dict[str, Any]:
    category = parsed.get("weapon_category")

    if category in {"primary", "secondary"}:
        classification, stats, conditional = _ranged_sections(parsed)
        return _compact(
            {
                **_common(parsed),
                "firing_mode": classification.get("firing_mode"),
                "damage_delivery": classification.get("damage_delivery"),
                "reload_type": classification.get("reload_type"),
                "fire_rate": stats.get("fire_rate"),
                "magazine_size": stats.get("magazine_size"),
                "reload_time": stats.get("reload_time"),
                "ammo_capacity": stats.get("ammo_capacity"),
                "accuracy": stats.get("accuracy"),
                "recoil": stats.get("recoil"),
                "projectile_speed": conditional.get("projectile_speed"),
                "beam_range": conditional.get("beam_range"),
                "charge_time": conditional.get("charge_time"),
                "battery_recharge_rate": conditional.get(
                    "battery_recharge_rate"
                ),
                "reload_per_round": conditional.get("reload_per_round"),
            }
        )

    if category == "melee":
        melee = _mapping(parsed.get("melee"), "melee")
        stats = _mapping(melee.get("stats"), "melee.stats")
        return _compact(
            {
                **_common(parsed),
                "attack_speed": stats.get("attack_speed"),
                "range": stats.get("range"),
                "heavy_attack_wind_up": stats.get(
                    "heavy_attack_wind_up"
                ),
            }
        )

    raise PromptBuilderError("Invalid weapon_category.")


def build_behavior_prompt(parsed: Mapping[str, Any]) -> str:
    return (
        "Analyze the weapon data for the behavior stage.\n"
        "DATA:\n"
        f"{_json(behavior_data(parsed))}"
    )


def build_job_prompt(
    parsed: Mapping[str, Any],
    behavior: Mapping[str, Any],
) -> str:
    payload = {
        "behavior_result": behavior,
        "weapon_data": job_data(parsed),
    }
    return (
        "Select the most plausible primary job for this weapon.\n"
        "DATA:\n"
        f"{_json(payload)}"
    )


def build_improvement_prompt(
    parsed: Mapping[str, Any],
    behavior: Mapping[str, Any],
    job: Mapping[str, Any],
) -> str:
    payload = {
        "behavior_result": behavior,
        "selected_job": job,
        "allowed_parameter_keys": list(
            available_improvement_parameters(parsed)
        ),
        "weapon_data": improvement_data(parsed),
    }
    return (
        "Choose the parameters that best support the selected job.\n"
        "DATA:\n"
        f"{_json(payload)}"
    )


def build_comfort_prompt(parsed: Mapping[str, Any]) -> str:
    return (
        "Analyze operational comfort only.\n"
        "DATA:\n"
        f"{_json(comfort_data(parsed))}"
    )
