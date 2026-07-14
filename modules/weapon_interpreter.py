# modules/weapon_interpreter.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from modules.logger import get_logger


logger = get_logger(__name__)

INTERPRETATION_VERSION = 3


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Missing or invalid parsed section: {name}.")
    return value


def _optional_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value

    return {}


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _add_evidence(
    evidence: list[str],
    field: str,
    value: Any,
) -> None:
    if _present(value):
        evidence.append(field)


def _classify_critical_relationship(
    critical_chance: float,
    critical_multiplier: float,
) -> str:
    """
    Return a broad retrieval signal for the critical relationship.

    These labels are retrieval signals rather than universal Warframe verdicts.
    """
    if critical_chance >= 25.0 and critical_multiplier >= 2.0:
        return "aligned"

    if critical_chance >= 15.0 and critical_multiplier >= 1.8:
        return "moderate"

    if (
        critical_chance < 15.0
        and critical_multiplier >= 2.5
    ) or (
        critical_chance >= 25.0
        and critical_multiplier < 1.8
    ):
        return "mixed"

    return "limited"


def _classify_application_frequency(
    firing_mode: str,
    fire_rate: float,
    base_instances: float,
) -> str:
    """
    Describe how frequently the supplied attack pattern creates opportunities.

    This function does not estimate hidden beam ticks.
    """
    if firing_mode == "continuous":
        return "continuous"

    if firing_mode == "automatic":
        if fire_rate >= 10.0 or base_instances >= 3.0:
            return "high"

        if fire_rate >= 4.0:
            return "moderate"

        return "low"

    if firing_mode == "burst":
        if base_instances >= 3.0:
            return "high"

        return "moderate"

    if base_instances >= 4.0:
        return "high"

    if base_instances >= 2.0:
        return "moderate"

    return "low"


def _classify_status_relationship(
    status_chance: float,
    application_frequency: str,
    base_instances: float,
) -> str:
    """
    Estimate status relevance from chance and application pattern.

    The result is a retrieval signal, not a final role decision.
    """
    frequent_application = application_frequency in {
        "continuous",
        "high",
    }

    if status_chance >= 25.0 and frequent_application:
        return "aligned"

    if status_chance >= 20.0:
        return "moderate"

    if status_chance >= 12.0 and (
        frequent_application
        or base_instances >= 3.0
    ):
        return "moderate"

    if status_chance < 12.0 and base_instances >= 4.0:
        return "mixed"

    return "limited"


def _estimate_magazine_duration(
    magazine_size: float,
    fire_rate: float,
) -> float | None:
    if magazine_size <= 0.0 or fire_rate <= 0.0:
        return None

    return magazine_size / fire_rate


def _classify_reload_friction(
    magazine_duration: float | None,
    reload_time: float,
    reload_type: str,
) -> str:
    if reload_time <= 0.0:
        return "low"

    if reload_type in {
        "battery",
        "shell_by_shell",
    }:
        return "special_reload"

    if magazine_duration is None:
        return "undetermined"

    reload_ratio = reload_time / max(
        magazine_duration,
        0.01,
    )

    if reload_ratio >= 0.45:
        return "high"

    if reload_ratio >= 0.20:
        return "moderate"

    return "low"


def _infer_damage_behavior(
    firing_mode: str,
) -> str:
    if firing_mode in {
        "automatic",
        "continuous",
    }:
        return "sustained"

    if firing_mode in {
        "charge",
        "semi_automatic",
    }:
        return "focused"

    if firing_mode == "burst":
        return "burst"

    return "general"


def _infer_structured_multi_target_evidence(
    classification: Mapping[str, Any],
    stats: Mapping[str, Any],
    conditional: Mapping[str, Any],
    mechanics: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    """
    Detect multi-target evidence only from normalized structured fields.
    """
    evidence: list[str] = []

    is_explosive = bool(
        classification.get("is_explosive")
    )

    explosion_radius = _number(
        conditional.get("explosion_radius")
    )

    punch_through = _number(
        stats.get("punch_through")
    )

    has_chaining = bool(
        mechanics.get("has_chaining")
    )

    chain_targets = _number(
        mechanics.get("chain_targets")
    )

    if is_explosive:
        evidence.append("is_explosive")

    if explosion_radius > 0.0:
        evidence.append("explosion_radius")

    if punch_through > 0.0:
        evidence.append("punch_through")

    if has_chaining:
        evidence.append("has_chaining")

    if chain_targets > 0.0:
        evidence.append("chain_targets")

    return bool(evidence), evidence


def _infer_target_profile(
    has_structured_multi_target_evidence: bool,
    has_multiple_pellets: bool,
    special_mechanic_present: bool,
) -> str:
    if has_structured_multi_target_evidence:
        return "multi_target_capable"

    if has_multiple_pellets:
        return "spread_delivery"

    if special_mechanic_present:
        return "special_mechanic_requires_review"

    return "single_target"


def _classify_ammo_consumption(
    fire_rate: float,
    magazine_duration: float | None,
    ammo_capacity: float | None,
    ammo_pickup: float | None,
    ammo_cost_per_damage_tick: float | None,
) -> tuple[str, str]:
    """
    Return both a consumption-rate signal and an economy-confidence signal.

    consumption_rate_signal describes how quickly the current attack pattern
    may consume ammunition.

    ammo_economy_signal describes whether the supplied reserve, pickup and cost
    information is sufficient to assess long-duration ammunition pressure.
    """
    if fire_rate <= 0.0:
        return "undetermined", "undetermined"

    if fire_rate >= 12.0 and (
        magazine_duration is None
        or magazine_duration <= 10.0
    ):
        consumption_rate_signal = "elevated"
    elif fire_rate >= 5.0:
        consumption_rate_signal = "moderate"
    else:
        consumption_rate_signal = "low"

    has_complete_economy_data = all(
        value is not None
        for value in (
            ammo_capacity,
            ammo_pickup,
            ammo_cost_per_damage_tick,
        )
    )

    if not has_complete_economy_data:
        return consumption_rate_signal, "undetermined"

    assert ammo_capacity is not None
    assert ammo_pickup is not None
    assert ammo_cost_per_damage_tick is not None

    if ammo_cost_per_damage_tick <= 0.0:
        return consumption_rate_signal, "low"

    recoverable_ticks = (
        ammo_pickup / ammo_cost_per_damage_tick
    )

    reserve_ticks = (
        ammo_capacity / ammo_cost_per_damage_tick
    )

    if recoverable_ticks >= 100.0 and reserve_ticks >= 1000.0:
        economy_signal = "low"
    elif recoverable_ticks >= 30.0:
        economy_signal = "moderate"
    else:
        economy_signal = "elevated"

    return consumption_rate_signal, economy_signal


def _infer_mechanic_profile(
    mechanics: Mapping[str, Any],
) -> dict[str, Any]:
    has_chaining = bool(
        mechanics.get("has_chaining")
    )

    has_damage_ramp = bool(
        mechanics.get("has_damage_ramp")
    )

    chain_targets = (
        int(_number(mechanics.get("chain_targets")))
        if _present(mechanics.get("chain_targets"))
        else None
    )

    chain_range = (
        _number(mechanics.get("chain_range"))
        if _present(mechanics.get("chain_range"))
        else None
    )

    chain_retention = (
        _number(
            mechanics.get(
                "chain_damage_retention_percent"
            )
        )
        if _present(
            mechanics.get(
                "chain_damage_retention_percent"
            )
        )
        else None
    )

    return {
        "has_chaining": has_chaining,
        "chain_targets": chain_targets,
        "chain_range": chain_range,
        "chain_damage_retention_percent": (
            chain_retention
        ),
        "has_damage_ramp": has_damage_ramp,
    }


def _infer_ranged_behavior(
    parsed: Mapping[str, Any],
) -> dict[str, Any]:
    ranged = _mapping(
        parsed.get("ranged"),
        "ranged",
    )

    classification = _mapping(
        ranged.get("classification"),
        "ranged.classification",
    )

    stats = _mapping(
        ranged.get("stats"),
        "ranged.stats",
    )

    conditional = _optional_mapping(
        ranged.get("conditional_stats")
    )

    mechanics = _optional_mapping(
        parsed.get("mechanics")
    )

    core = _mapping(
        parsed.get("core_stats"),
        "core_stats",
    )

    firing_mode = str(
        classification.get("firing_mode") or ""
    )

    damage_delivery = str(
        classification.get("damage_delivery") or ""
    )

    reload_type = str(
        classification.get("reload_type")
        or "magazine"
    )

    has_multiple_pellets = bool(
        classification.get("has_multiple_pellets")
    )

    fire_rate = _number(
        stats.get("fire_rate")
    )

    multishot = max(
        _number(
            stats.get("multishot"),
            1.0,
        ),
        0.01,
    )

    magazine_size = _number(
        stats.get("magazine_size")
    )

    reload_time = _number(
        stats.get("reload_time")
    )

    ammo_capacity = (
        _number(stats.get("ammo_capacity"))
        if _present(stats.get("ammo_capacity"))
        else None
    )

    ammo_pickup = (
        _number(stats.get("ammo_pickup"))
        if _present(stats.get("ammo_pickup"))
        else None
    )

    ammo_cost_per_damage_tick = (
        _number(
            stats.get("ammo_cost_per_damage_tick")
        )
        if _present(
            stats.get("ammo_cost_per_damage_tick")
        )
        else None
    )

    pellet_count = (
        max(
            _number(
                conditional.get("pellet_count"),
                1.0,
            ),
            1.0,
        )
        if has_multiple_pellets
        else 1.0
    )

    burst_count = (
        max(
            _number(
                conditional.get("shots_per_burst"),
                1.0,
            ),
            1.0,
        )
        if firing_mode == "burst"
        else 1.0
    )

    base_instances = (
        multishot
        * pellet_count
        * burst_count
    )

    critical_chance = _number(
        core.get("critical_chance_percent")
    )

    critical_multiplier = _number(
        core.get("critical_multiplier"),
        1.0,
    )

    status_chance = _number(
        core.get("status_chance_percent")
    )

    magazine_duration = _estimate_magazine_duration(
        magazine_size,
        fire_rate,
    )

    application_frequency = (
        _classify_application_frequency(
            firing_mode,
            fire_rate,
            base_instances,
        )
    )

    (
        structured_multi_target,
        multi_target_evidence,
    ) = _infer_structured_multi_target_evidence(
        classification,
        stats,
        conditional,
        mechanics,
    )

    special_mechanic_present = bool(
        parsed.get("special_mechanic")
    )

    target_profile = _infer_target_profile(
        structured_multi_target,
        has_multiple_pellets,
        special_mechanic_present,
    )

    (
        consumption_rate_signal,
        ammo_economy_signal,
    ) = _classify_ammo_consumption(
        fire_rate,
        magazine_duration,
        ammo_capacity,
        ammo_pickup,
        ammo_cost_per_damage_tick,
    )

    mechanic_profile = _infer_mechanic_profile(
        mechanics
    )

    critical_evidence: list[str] = []
    _add_evidence(
        critical_evidence,
        "critical_chance_percent",
        core.get("critical_chance_percent"),
    )
    _add_evidence(
        critical_evidence,
        "critical_multiplier",
        core.get("critical_multiplier"),
    )

    status_evidence: list[str] = []
    _add_evidence(
        status_evidence,
        "status_chance_percent",
        core.get("status_chance_percent"),
    )
    _add_evidence(
        status_evidence,
        "fire_rate",
        stats.get("fire_rate"),
    )
    _add_evidence(
        status_evidence,
        "multishot",
        stats.get("multishot"),
    )
    _add_evidence(
        status_evidence,
        "pellet_count",
        conditional.get("pellet_count"),
    )
    _add_evidence(
        status_evidence,
        "shots_per_burst",
        conditional.get("shots_per_burst"),
    )
    _add_evidence(
        status_evidence,
        "firing_mode",
        classification.get("firing_mode"),
    )

    reload_evidence: list[str] = []
    _add_evidence(
        reload_evidence,
        "fire_rate",
        stats.get("fire_rate"),
    )
    _add_evidence(
        reload_evidence,
        "magazine_size",
        stats.get("magazine_size"),
    )
    _add_evidence(
        reload_evidence,
        "reload_time",
        stats.get("reload_time"),
    )
    _add_evidence(
        reload_evidence,
        "reload_type",
        classification.get("reload_type"),
    )

    target_evidence = list(
        multi_target_evidence
    )

    if has_multiple_pellets:
        target_evidence.append(
            "has_multiple_pellets"
        )

    if special_mechanic_present:
        target_evidence.append(
            "special_mechanic"
        )

    ammo_evidence: list[str] = []
    _add_evidence(
        ammo_evidence,
        "fire_rate",
        stats.get("fire_rate"),
    )
    _add_evidence(
        ammo_evidence,
        "magazine_size",
        stats.get("magazine_size"),
    )
    _add_evidence(
        ammo_evidence,
        "ammo_capacity",
        stats.get("ammo_capacity"),
    )
    _add_evidence(
        ammo_evidence,
        "ammo_pickup",
        stats.get("ammo_pickup"),
    )
    _add_evidence(
        ammo_evidence,
        "ammo_cost_per_damage_tick",
        stats.get("ammo_cost_per_damage_tick"),
    )

    mechanics_evidence: list[str] = []
    _add_evidence(
        mechanics_evidence,
        "has_chaining",
        mechanics.get("has_chaining"),
    )
    _add_evidence(
        mechanics_evidence,
        "chain_targets",
        mechanics.get("chain_targets"),
    )
    _add_evidence(
        mechanics_evidence,
        "chain_range",
        mechanics.get("chain_range"),
    )
    _add_evidence(
        mechanics_evidence,
        "chain_damage_retention_percent",
        mechanics.get(
            "chain_damage_retention_percent"
        ),
    )
    _add_evidence(
        mechanics_evidence,
        "has_damage_ramp",
        mechanics.get("has_damage_ramp"),
    )

    return {
        "interpretation_version": (
            INTERPRETATION_VERSION
        ),
        "weapon_category": (
            parsed.get("weapon_category")
        ),
        "weapon_class": (
            parsed.get("weapon_class")
        ),
        "attack_behavior": firing_mode,
        "damage_delivery": damage_delivery,
        "damage_behavior": (
            _infer_damage_behavior(firing_mode)
        ),
        "critical_relationship": (
            _classify_critical_relationship(
                critical_chance,
                critical_multiplier,
            )
        ),
        "status_relationship": (
            _classify_status_relationship(
                status_chance,
                application_frequency,
                base_instances,
            )
        ),
        "application_frequency": (
            application_frequency
        ),
        "continuous_application": (
            firing_mode == "continuous"
        ),
        "reload_friction": (
            _classify_reload_friction(
                magazine_duration,
                reload_time,
                reload_type,
            )
        ),
        "consumption_rate_signal": (
            consumption_rate_signal
        ),
        "ammo_economy_signal": (
            ammo_economy_signal
        ),
        "target_profile": target_profile,
        "has_structured_multi_target_evidence": (
            structured_multi_target
        ),
        "special_mechanic_present": (
            special_mechanic_present
        ),
        "mechanic_profile": (
            mechanic_profile
        ),
        "base_instances_per_delivery": round(
            base_instances,
            3,
        ),
        "estimated_magazine_duration_seconds": (
            round(
                magazine_duration,
                3,
            )
            if magazine_duration is not None
            else None
        ),
        "evidence": {
            "critical_relationship": (
                critical_evidence
            ),
            "status_relationship": (
                status_evidence
            ),
            "reload_friction": (
                reload_evidence
            ),
            "ammo_economy_signal": (
                ammo_evidence
            ),
            "target_profile": (
                target_evidence
            ),
            "mechanic_profile": (
                mechanics_evidence
            ),
        },
    }


def _infer_melee_behavior(
    parsed: Mapping[str, Any],
) -> dict[str, Any]:
    melee = _mapping(
        parsed.get("melee"),
        "melee",
    )

    stats = _mapping(
        melee.get("stats"),
        "melee.stats",
    )

    core = _mapping(
        parsed.get("core_stats"),
        "core_stats",
    )

    mechanics = _optional_mapping(
        parsed.get("mechanics")
    )

    attack_speed = _number(
        stats.get("attack_speed")
    )

    melee_range = _number(
        stats.get("range")
    )

    heavy_damage = _number(
        stats.get("heavy_attack_damage")
    )

    heavy_wind_up = _number(
        stats.get("heavy_attack_wind_up")
    )

    critical_chance = _number(
        core.get("critical_chance_percent")
    )

    critical_multiplier = _number(
        core.get("critical_multiplier"),
        1.0,
    )

    status_chance = _number(
        core.get("status_chance_percent")
    )

    if heavy_damage > 0.0 and heavy_wind_up > 0.0:
        damage_behavior = "heavy_attacks"
    elif attack_speed >= 1.0:
        damage_behavior = "sustained_melee"
    else:
        damage_behavior = "deliberate_melee"

    if heavy_wind_up >= 1.0:
        handling_friction = "high"
    elif heavy_wind_up > 0.0 or attack_speed < 0.9:
        handling_friction = "moderate"
    else:
        handling_friction = "low"

    special_mechanic_present = bool(
        parsed.get("special_mechanic")
    )

    has_chaining = bool(
        mechanics.get("has_chaining")
    )

    if melee_range >= 3.0 or has_chaining:
        target_profile = "multi_target_capable"
    elif special_mechanic_present:
        target_profile = (
            "special_mechanic_requires_review"
        )
    else:
        target_profile = "close_range"

    application_frequency = (
        "high"
        if attack_speed >= 1.2
        else "moderate"
        if attack_speed >= 0.9
        else "low"
    )

    critical_evidence: list[str] = []
    _add_evidence(
        critical_evidence,
        "critical_chance_percent",
        core.get("critical_chance_percent"),
    )
    _add_evidence(
        critical_evidence,
        "critical_multiplier",
        core.get("critical_multiplier"),
    )

    status_evidence: list[str] = []
    _add_evidence(
        status_evidence,
        "status_chance_percent",
        core.get("status_chance_percent"),
    )
    _add_evidence(
        status_evidence,
        "attack_speed",
        stats.get("attack_speed"),
    )

    handling_evidence: list[str] = []
    _add_evidence(
        handling_evidence,
        "attack_speed",
        stats.get("attack_speed"),
    )
    _add_evidence(
        handling_evidence,
        "heavy_attack_wind_up",
        stats.get("heavy_attack_wind_up"),
    )

    target_evidence: list[str] = []
    _add_evidence(
        target_evidence,
        "range",
        stats.get("range"),
    )
    _add_evidence(
        target_evidence,
        "has_chaining",
        mechanics.get("has_chaining"),
    )
    _add_evidence(
        target_evidence,
        "chain_targets",
        mechanics.get("chain_targets"),
    )

    if special_mechanic_present:
        target_evidence.append(
            "special_mechanic"
        )

    return {
        "interpretation_version": (
            INTERPRETATION_VERSION
        ),
        "weapon_category": "melee",
        "weapon_class": (
            parsed.get("weapon_class")
        ),
        "attack_behavior": damage_behavior,
        "damage_behavior": damage_behavior,
        "critical_relationship": (
            _classify_critical_relationship(
                critical_chance,
                critical_multiplier,
            )
        ),
        "status_relationship": (
            _classify_status_relationship(
                status_chance,
                application_frequency,
                max(attack_speed, 1.0),
            )
        ),
        "application_frequency": (
            application_frequency
        ),
        "reload_friction": "not_applicable",
        "handling_friction": (
            handling_friction
        ),
        "target_profile": target_profile,
        "has_structured_multi_target_evidence": (
            melee_range >= 3.0
            or has_chaining
        ),
        "special_mechanic_present": (
            special_mechanic_present
        ),
        "mechanic_profile": (
            _infer_mechanic_profile(mechanics)
        ),
        "evidence": {
            "critical_relationship": (
                critical_evidence
            ),
            "status_relationship": (
                status_evidence
            ),
            "handling_friction": (
                handling_evidence
            ),
            "target_profile": (
                target_evidence
            ),
        },
    }


def interpret_weapon(
    parsed_weapon: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Convert normalized weapon data into deterministic retrieval signals.

    The returned labels are auditable retrieval signals and not final verdicts.
    """
    if not isinstance(parsed_weapon, Mapping):
        raise TypeError(
            "parsed_weapon must be a Mapping."
        )

    category = parsed_weapon.get(
        "weapon_category"
    )

    logger.info(
        "Starting deterministic weapon interpretation "
        "| category=%s",
        category,
    )

    if category in {
        "primary",
        "secondary",
    }:
        interpretation = _infer_ranged_behavior(
            parsed_weapon
        )

    elif category == "melee":
        interpretation = _infer_melee_behavior(
            parsed_weapon
        )

    else:
        raise ValueError(
            f"Unsupported weapon category: {category}"
        )

    logger.info(
        "Weapon interpretation completed "
        "| critical=%s | status=%s "
        "| behavior=%s | target=%s "
        "| ammo_economy=%s",
        interpretation.get(
            "critical_relationship"
        ),
        interpretation.get(
            "status_relationship"
        ),
        interpretation.get(
            "damage_behavior"
        ),
        interpretation.get(
            "target_profile"
        ),
        interpretation.get(
            "ammo_economy_signal"
        ),
    )

    return interpretation


# Compatibility alias.
analyze_parsed_weapon = interpret_weapon
