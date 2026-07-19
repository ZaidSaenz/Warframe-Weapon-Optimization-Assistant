# modules/weapon_interpreter.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from modules.logger import get_logger


logger = get_logger(__name__)

INTERPRETATION_VERSION = 4

RANGED_CATEGORIES = {
    "primary",
    "secondary",
    "companion",
    "archgun",
    "amp",
    "special",
}

MELEE_CATEGORIES = {
    "melee",
    "archmelee",
    "drifter_melee",
}


def _mapping(
    value: Any,
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(
            f"Missing or invalid normalized section: {name}."
        )

    return value


def _optional_mapping(
    value: Any,
) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(
    value: Any,
    default: float = 0.0,
) -> float:
    if isinstance(value, bool):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_number(
    value: Any,
) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _add_evidence(
    evidence: list[str],
    field: str,
    value: Any,
) -> None:
    if _present(value):
        evidence.append(field)


def _first_attack_mode(
    weapon: Mapping[str, Any],
) -> Mapping[str, Any]:
    modes = weapon.get("attack_modes")

    if not isinstance(modes, list) or not modes:
        raise ValueError(
            "Normalized weapon requires at least one attack mode."
        )

    for mode in modes:
        if isinstance(mode, Mapping):
            return mode

    raise ValueError(
        "Normalized weapon contains no valid attack mode."
    )


def _damage_components(
    mode: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    raw_components = mode.get("damage_components")

    if not isinstance(raw_components, list):
        return []

    return [
        component
        for component in raw_components
        if isinstance(component, Mapping)
    ]


def _compatibility_tags(
    shared_stats: Mapping[str, Any],
) -> set[str]:
    raw_tags = shared_stats.get("compatibility_tags")

    if not isinstance(raw_tags, list):
        return set()

    return {
        str(tag).strip().lower()
        for tag in raw_tags
        if str(tag).strip()
    }


def _classify_critical_relationship(
    critical_chance: float,
    critical_multiplier: float,
) -> str:
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
    trigger_type: str,
    fire_rate: float,
    delivery_instances: float,
) -> str:
    if trigger_type == "continuous":
        return "continuous"

    if trigger_type == "automatic":
        if fire_rate >= 10.0 or delivery_instances >= 3.0:
            return "high"

        if fire_rate >= 4.0:
            return "moderate"

        return "low"

    if trigger_type == "burst":
        if delivery_instances >= 3.0:
            return "high"

        return "moderate"

    if delivery_instances >= 4.0:
        return "high"

    if delivery_instances >= 2.0:
        return "moderate"

    return "low"


def _classify_status_relationship(
    status_chance: float,
    application_frequency: str,
    delivery_instances: float,
) -> str:
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
        or delivery_instances >= 3.0
    ):
        return "moderate"

    if status_chance < 12.0 and delivery_instances >= 4.0:
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
) -> str:
    if reload_time <= 0.0:
        return "low"

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
    trigger_type: str,
) -> str:
    if trigger_type in {
        "automatic",
        "continuous",
        "active",
    }:
        return "sustained"

    if trigger_type in {
        "charge",
        "semi_automatic",
        "duplex",
    }:
        return "focused"

    if trigger_type == "burst":
        return "burst"

    return "general"


def _infer_damage_delivery(
    trigger_type: str,
    tags: set[str],
    components: list[Mapping[str, Any]],
) -> str:
    if "beam" in tags or trigger_type == "continuous":
        return "beam"

    component_types = {
        str(component.get("component_type") or "")
        for component in components
    }

    if any(
        component_type.startswith("projectile")
        or component_type.startswith("charged_projectile")
        for component_type in component_types
    ):
        return "projectile"

    return "direct"


def _infer_multi_target_evidence(
    tags: set[str],
    components: list[Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    evidence: list[str] = []

    if "aoe" in tags:
        evidence.append(
            "compatibility_tags.aoe"
        )

    if "beam" in tags and "aoe" in tags:
        evidence.append(
            "compatibility_tags.beam"
        )

    radial_components = [
        component
        for component in components
        if str(
            component.get("component_type") or ""
        ).endswith("_radial")
    ]

    if radial_components:
        evidence.append(
            "attack_modes.damage_components.radial"
        )

    return bool(evidence), evidence


def _infer_target_profile(
    multi_target: bool,
    delivery_instances: float,
) -> str:
    if multi_target:
        return "multi_target_capable"

    if delivery_instances > 1.0:
        return "spread_delivery"

    return "single_target"


def _classify_ammo_consumption(
    fire_rate: float,
    magazine_duration: float | None,
) -> tuple[str, str]:
    if fire_rate <= 0.0:
        return "undetermined", "undetermined"

    if fire_rate >= 12.0 and (
        magazine_duration is None
        or magazine_duration <= 10.0
    ):
        consumption = "elevated"
    elif fire_rate >= 5.0:
        consumption = "moderate"
    else:
        consumption = "low"

    return consumption, "undetermined"


def _mode_stat(
    mode: Mapping[str, Any],
    root_stats: Mapping[str, Any],
    key: str,
    *,
    default: float = 0.0,
) -> float:
    if _present(mode.get(key)):
        return _number(
            mode.get(key),
            default,
        )

    return _number(
        root_stats.get(key),
        default,
    )


def _interpret_ranged(
    weapon: Mapping[str, Any],
) -> dict[str, Any]:
    classification = _mapping(
        weapon.get("classification"),
        "classification",
    )
    shared_stats = _mapping(
        weapon.get("shared_stats"),
        "shared_stats",
    )
    root_stats = _mapping(
        weapon.get("root_stats"),
        "root_stats",
    )
    mode = _first_attack_mode(
        weapon
    )
    components = _damage_components(
        mode
    )
    tags = _compatibility_tags(
        shared_stats
    )

    category = str(
        classification.get("category") or ""
    )
    weapon_class = classification.get(
        "weapon_class"
    )

    trigger_type = str(
        mode.get("trigger_type")
        or shared_stats.get("trigger_type")
        or ""
    )

    fire_rate = _mode_stat(
        mode,
        root_stats,
        "fire_rate",
    )
    critical_chance = _mode_stat(
        mode,
        root_stats,
        "critical_chance_percent",
    )
    critical_multiplier = _mode_stat(
        mode,
        root_stats,
        "critical_multiplier",
        default=1.0,
    )
    status_chance = _mode_stat(
        mode,
        root_stats,
        "status_chance_percent",
    )

    multishot = max(
        _number(
            shared_stats.get("multishot"),
            1.0,
        ),
        0.01,
    )
    fire_iterations = max(
        _number(
            mode.get("fire_iterations"),
            1.0,
        ),
        1.0,
    )
    delivery_instances = (
        multishot * fire_iterations
    )

    magazine_size = _number(
        shared_stats.get("magazine_size")
    )
    reload_time = _number(
        shared_stats.get("reload_time")
    )
    magazine_duration = _estimate_magazine_duration(
        magazine_size,
        fire_rate,
    )

    application_frequency = _classify_application_frequency(
        trigger_type,
        fire_rate,
        delivery_instances,
    )

    multi_target, target_evidence = _infer_multi_target_evidence(
        tags,
        components,
    )
    target_profile = _infer_target_profile(
        multi_target,
        delivery_instances,
    )

    consumption_rate, ammo_economy = _classify_ammo_consumption(
        fire_rate,
        magazine_duration,
    )

    damage_delivery = _infer_damage_delivery(
        trigger_type,
        tags,
        components,
    )

    critical_evidence: list[str] = []
    _add_evidence(
        critical_evidence,
        "root_stats.critical_chance_percent",
        root_stats.get("critical_chance_percent"),
    )
    _add_evidence(
        critical_evidence,
        "root_stats.critical_multiplier",
        root_stats.get("critical_multiplier"),
    )

    status_evidence: list[str] = []
    _add_evidence(
        status_evidence,
        "root_stats.status_chance_percent",
        root_stats.get("status_chance_percent"),
    )
    _add_evidence(
        status_evidence,
        "root_stats.fire_rate",
        root_stats.get("fire_rate"),
    )
    _add_evidence(
        status_evidence,
        "shared_stats.multishot",
        shared_stats.get("multishot"),
    )
    _add_evidence(
        status_evidence,
        "attack_modes.fire_iterations",
        mode.get("fire_iterations"),
    )
    _add_evidence(
        status_evidence,
        "attack_modes.trigger_type",
        mode.get("trigger_type"),
    )

    reload_evidence: list[str] = []
    _add_evidence(
        reload_evidence,
        "shared_stats.magazine_size",
        shared_stats.get("magazine_size"),
    )
    _add_evidence(
        reload_evidence,
        "shared_stats.reload_time",
        shared_stats.get("reload_time"),
    )
    _add_evidence(
        reload_evidence,
        "root_stats.fire_rate",
        root_stats.get("fire_rate"),
    )

    ammo_evidence: list[str] = []
    _add_evidence(
        ammo_evidence,
        "root_stats.fire_rate",
        root_stats.get("fire_rate"),
    )
    _add_evidence(
        ammo_evidence,
        "shared_stats.magazine_size",
        shared_stats.get("magazine_size"),
    )

    return {
        "interpretation_version": INTERPRETATION_VERSION,
        "weapon_category": category,
        "weapon_class": weapon_class,
        "attack_behavior": trigger_type or "unknown",
        "damage_delivery": damage_delivery,
        "damage_behavior": _infer_damage_behavior(
            trigger_type
        ),
        "critical_relationship": _classify_critical_relationship(
            critical_chance,
            critical_multiplier,
        ),
        "status_relationship": _classify_status_relationship(
            status_chance,
            application_frequency,
            delivery_instances,
        ),
        "application_frequency": application_frequency,
        "continuous_application": (
            trigger_type == "continuous"
        ),
        "reload_friction": _classify_reload_friction(
            magazine_duration,
            reload_time,
        ),
        "consumption_rate_signal": consumption_rate,
        "ammo_economy_signal": ammo_economy,
        "target_profile": target_profile,
        "has_structured_multi_target_evidence": multi_target,
        "special_mechanic_present": multi_target,
        "mechanic_profile": {
            "has_area_delivery": multi_target,
            "has_radial_component": any(
                str(
                    component.get("component_type") or ""
                ).endswith("_radial")
                for component in components
            ),
            "has_beam_tag": "beam" in tags,
            "has_aoe_tag": "aoe" in tags,
        },
        "base_instances_per_delivery": round(
            delivery_instances,
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
        "attack_mode_count": len(
            weapon.get("attack_modes", [])
        ),
        "evidence": {
            "critical_relationship": critical_evidence,
            "status_relationship": status_evidence,
            "reload_friction": reload_evidence,
            "ammo_economy_signal": ammo_evidence,
            "target_profile": target_evidence,
            "mechanic_profile": target_evidence,
        },
    }


def _interpret_melee(
    weapon: Mapping[str, Any],
) -> dict[str, Any]:
    classification = _mapping(
        weapon.get("classification"),
        "classification",
    )
    shared_stats = _mapping(
        weapon.get("shared_stats"),
        "shared_stats",
    )
    root_stats = _mapping(
        weapon.get("root_stats"),
        "root_stats",
    )
    mode = _first_attack_mode(
        weapon
    )

    category = str(
        classification.get("category") or ""
    )
    weapon_class = classification.get(
        "weapon_class"
    )

    attack_speed = _mode_stat(
        mode,
        root_stats,
        "fire_rate",
    )
    melee_range = _number(
        shared_stats.get("range")
    )
    heavy_damage = _number(
        shared_stats.get("heavy_attack_damage")
    )
    heavy_wind_up = _number(
        shared_stats.get("heavy_attack_wind_up")
    )

    critical_chance = _mode_stat(
        mode,
        root_stats,
        "critical_chance_percent",
    )
    critical_multiplier = _mode_stat(
        mode,
        root_stats,
        "critical_multiplier",
        default=1.0,
    )
    status_chance = _mode_stat(
        mode,
        root_stats,
        "status_chance_percent",
    )

    if heavy_damage > 0.0:
        damage_behavior = "heavy_attacks"
    elif attack_speed >= 1.0:
        damage_behavior = "sustained_melee"
    else:
        damage_behavior = "deliberate_melee"

    if heavy_wind_up >= 1.0:
        handling_friction = "high"
    elif heavy_wind_up > 0.0 or (
        attack_speed > 0.0
        and attack_speed < 0.9
    ):
        handling_friction = "moderate"
    else:
        handling_friction = "low"

    application_frequency = (
        "high"
        if attack_speed >= 1.2
        else "moderate"
        if attack_speed >= 0.9
        else "low"
    )

    multi_target = melee_range >= 3.0

    critical_evidence: list[str] = []
    _add_evidence(
        critical_evidence,
        "root_stats.critical_chance_percent",
        root_stats.get("critical_chance_percent"),
    )
    _add_evidence(
        critical_evidence,
        "root_stats.critical_multiplier",
        root_stats.get("critical_multiplier"),
    )

    status_evidence: list[str] = []
    _add_evidence(
        status_evidence,
        "root_stats.status_chance_percent",
        root_stats.get("status_chance_percent"),
    )
    _add_evidence(
        status_evidence,
        "root_stats.fire_rate",
        root_stats.get("fire_rate"),
    )

    handling_evidence: list[str] = []
    _add_evidence(
        handling_evidence,
        "root_stats.fire_rate",
        root_stats.get("fire_rate"),
    )
    _add_evidence(
        handling_evidence,
        "shared_stats.heavy_attack_wind_up",
        shared_stats.get("heavy_attack_wind_up"),
    )

    target_evidence: list[str] = []
    _add_evidence(
        target_evidence,
        "shared_stats.range",
        shared_stats.get("range"),
    )

    return {
        "interpretation_version": INTERPRETATION_VERSION,
        "weapon_category": category,
        "weapon_class": weapon_class,
        "attack_behavior": damage_behavior,
        "damage_behavior": damage_behavior,
        "critical_relationship": _classify_critical_relationship(
            critical_chance,
            critical_multiplier,
        ),
        "status_relationship": _classify_status_relationship(
            status_chance,
            application_frequency,
            max(attack_speed, 1.0),
        ),
        "application_frequency": application_frequency,
        "continuous_application": False,
        "reload_friction": "not_applicable",
        "handling_friction": handling_friction,
        "consumption_rate_signal": "not_applicable",
        "ammo_economy_signal": "not_applicable",
        "target_profile": (
            "multi_target_capable"
            if multi_target
            else "close_range"
        ),
        "has_structured_multi_target_evidence": multi_target,
        "special_mechanic_present": False,
        "mechanic_profile": {
            "has_area_delivery": multi_target,
            "has_radial_component": False,
            "has_beam_tag": False,
            "has_aoe_tag": False,
        },
        "base_instances_per_delivery": 1.0,
        "estimated_magazine_duration_seconds": None,
        "attack_mode_count": len(
            weapon.get("attack_modes", [])
        ),
        "evidence": {
            "critical_relationship": critical_evidence,
            "status_relationship": status_evidence,
            "handling_friction": handling_evidence,
            "target_profile": target_evidence,
            "mechanic_profile": target_evidence,
        },
    }


def interpret_weapon(
    normalized_weapon: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Convert one weapon_database.py entry into deterministic retrieval signals.

    The returned labels support rule selection and prompt construction. They
    are auditable signals, not final weapon verdicts.
    """
    if not isinstance(
        normalized_weapon,
        Mapping,
    ):
        raise TypeError(
            "normalized_weapon must be a Mapping."
        )

    classification = _mapping(
        normalized_weapon.get("classification"),
        "classification",
    )
    category = str(
        classification.get("category") or ""
    )

    logger.info(
        "Starting deterministic weapon interpretation "
        "| weapon=%s | category=%s",
        normalized_weapon.get("display_name"),
        category,
    )

    if category in RANGED_CATEGORIES:
        interpretation = _interpret_ranged(
            normalized_weapon
        )
    elif category in MELEE_CATEGORIES:
        interpretation = _interpret_melee(
            normalized_weapon
        )
    else:
        raise ValueError(
            f"Unsupported normalized weapon category: {category}"
        )

    logger.info(
        "Weapon interpretation completed "
        "| critical=%s | status=%s "
        "| behavior=%s | target=%s "
        "| reload=%s",
        interpretation.get("critical_relationship"),
        interpretation.get("status_relationship"),
        interpretation.get("damage_behavior"),
        interpretation.get("target_profile"),
        interpretation.get("reload_friction"),
    )

    return interpretation


analyze_parsed_weapon = interpret_weapon