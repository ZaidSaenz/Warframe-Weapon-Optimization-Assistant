# modules/weapon_interpreter.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from modules.logger import get_logger


logger = get_logger(__name__)

INTERPRETATION_VERSION = 5

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

# Description mechanics already covered by specialized knowledge concepts.
# They should not trigger the generic special-mechanic fallback by themselves.
KNOWN_DESCRIPTION_MECHANICS = {
    "chaining",
    "ricochet",
    "homing",
    "lock_on",
    "delayed_activation",
    "explosion",
    "damage_ramp",
    "returning_projectile",
    "deployable",
    "grouping",
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


def _present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _add_evidence(
    evidence: list[str],
    field: str,
    value: Any,
) -> None:
    if _present(value):
        evidence.append(field)


def _attack_modes(
    weapon: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    raw_modes = weapon.get("attack_modes")

    if not isinstance(raw_modes, list):
        return []

    return [
        mode
        for mode in raw_modes
        if isinstance(mode, Mapping)
    ]


def _first_attack_mode(
    weapon: Mapping[str, Any],
) -> Mapping[str, Any]:
    modes = _attack_modes(
        weapon
    )

    if not modes:
        raise ValueError(
            "Normalized weapon requires at least one valid attack mode."
        )

    return modes[0]


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


def _classify_critical_relationship(
    critical_chance: float,
    critical_multiplier: float,
) -> str:
    if (
        critical_chance >= 25.0
        and critical_multiplier >= 2.0
    ):
        return "aligned"

    if (
        critical_chance >= 15.0
        and critical_multiplier >= 1.8
    ):
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
        if (
            fire_rate >= 10.0
            or delivery_instances >= 3.0
        ):
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

    if (
        status_chance >= 25.0
        and frequent_application
    ):
        return "aligned"

    if status_chance >= 20.0:
        return "moderate"

    if (
        status_chance >= 12.0
        and (
            frequent_application
            or delivery_instances >= 3.0
        )
    ):
        return "moderate"

    if (
        status_chance < 12.0
        and delivery_instances >= 4.0
    ):
        return "mixed"

    return "limited"


def _estimate_magazine_duration(
    magazine_size: float,
    fire_rate: float,
) -> float | None:
    if (
        magazine_size <= 0.0
        or fire_rate <= 0.0
    ):
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


def _classify_ammo_consumption(
    fire_rate: float,
    magazine_duration: float | None,
) -> tuple[str, str]:
    if fire_rate <= 0.0:
        return "undetermined", "undetermined"

    if (
        fire_rate >= 12.0
        and (
            magazine_duration is None
            or magazine_duration <= 10.0
        )
    ):
        consumption = "elevated"
    elif fire_rate >= 5.0:
        consumption = "moderate"
    else:
        consumption = "low"

    return consumption, "undetermined"


def _component_type_profile(
    modes: list[Mapping[str, Any]],
) -> dict[str, Any]:
    component_types = {
        str(
            component.get("component_type")
            or ""
        )
        for mode in modes
        for component in _damage_components(mode)
        if component.get("component_type")
    }

    has_direct = "direct" in component_types
    has_projectile_direct = (
        "projectile_direct" in component_types
    )
    has_projectile_radial = (
        "projectile_radial" in component_types
    )
    has_charged_projectile = any(
        item.startswith(
            "charged_projectile"
        )
        for item in component_types
    )
    has_charged_radial = (
        "charged_projectile_radial"
        in component_types
    )

    return {
        "types": sorted(component_types),
        "has_direct_component": has_direct,
        "has_projectile_direct_component": (
            has_projectile_direct
        ),
        "has_projectile_radial_component": (
            has_projectile_radial
        ),
        "has_charged_projectile_component": (
            has_charged_projectile
        ),
        "has_charged_projectile_radial_component": (
            has_charged_radial
        ),
    }


def _infer_delivery_profile(
    *,
    trigger_type: str,
    tags: set[str],
    component_profile: Mapping[str, Any],
) -> str:
    if (
        "beam" in tags
        or trigger_type == "continuous"
    ):
        return "beam"

    has_projectile = bool(
        component_profile.get(
            "has_projectile_direct_component"
        )
        or component_profile.get(
            "has_charged_projectile_component"
        )
    )
    has_radial = bool(
        component_profile.get(
            "has_projectile_radial_component"
        )
        or component_profile.get(
            "has_charged_projectile_radial_component"
        )
    )
    has_direct = bool(
        component_profile.get(
            "has_direct_component"
        )
    )

    active_types = sum(
        (
            has_direct,
            has_projectile,
            has_radial,
        )
    )

    if active_types > 1:
        return "mixed"

    if has_radial:
        return "radial"

    if has_projectile:
        return "projectile"

    return "direct"


def _classify_mode_relationship(
    modes: list[Mapping[str, Any]],
) -> str:
    if len(modes) <= 1:
        return "single_mode"

    signatures: set[
        tuple[str, tuple[str, ...]]
    ] = set()

    ambiguous = False

    for mode in modes:
        trigger_type = str(
            mode.get("trigger_type") or ""
        )
        component_types = tuple(
            sorted(
                str(
                    component.get(
                        "component_type"
                    )
                    or ""
                )
                for component in _damage_components(
                    mode
                )
            )
        )

        if not trigger_type and not component_types:
            ambiguous = True

        signatures.add(
            (
                trigger_type,
                component_types,
            )
        )

    if ambiguous:
        return "ambiguous_modes"

    if len(signatures) == 1:
        return "multiple_similar_modes"

    return "multiple_distinct_modes"


def _attack_rhythm_profile(
    modes: list[Mapping[str, Any]],
    primary_trigger: str,
) -> dict[str, Any]:
    burst_count: float | None = None
    burst_delay: float | None = None
    has_burst = False
    has_charge = False
    has_active = False
    has_duplex = False

    for mode in modes:
        trigger = str(
            mode.get("trigger_type") or ""
        )

        if trigger == "burst":
            has_burst = True
            burst = mode.get("burst")

            if isinstance(burst, Mapping):
                if _present(
                    burst.get("count")
                ):
                    burst_count = _number(
                        burst.get("count")
                    )

                if _present(
                    burst.get("delay")
                ):
                    burst_delay = _number(
                        burst.get("delay")
                    )

        if (
            trigger == "charge"
            or mode.get("charge_evidence")
            is True
        ):
            has_charge = True

        if trigger == "active":
            has_active = True

        if trigger == "duplex":
            has_duplex = True

    return {
        "attack_behavior": (
            primary_trigger
            or "unknown"
        ),
        "has_burst_evidence": has_burst,
        "burst_count": burst_count,
        "burst_delay": burst_delay,
        "has_charge_evidence": has_charge,
        "has_active_trigger_evidence": (
            has_active
        ),
        "has_duplex_evidence": has_duplex,
    }


def _instance_profile(
    *,
    multishot: float,
    fire_iterations: float,
    mode: Mapping[str, Any],
) -> dict[str, Any]:
    sources: list[str] = []

    if multishot > 1.0:
        sources.append("multishot")

    if fire_iterations > 1.0:
        sources.append("fire_iterations")

    if str(
        mode.get("trigger_type") or ""
    ) == "burst":
        burst = mode.get("burst")

        if isinstance(burst, Mapping):
            burst_count = _number(
                burst.get("count"),
                1.0,
            )

            if burst_count > 1.0:
                sources.append("burst")

    # Neutral estimate only: this must not be treated as pellet count,
    # extra ammunition cost, or multi-target coverage without other evidence.
    delivery_instances = max(
        multishot,
        1.0,
    ) * max(
        fire_iterations,
        1.0,
    )

    return {
        "base_instances_per_delivery": round(
            delivery_instances,
            3,
        ),
        "has_multi_instance_evidence": (
            delivery_instances > 1.0
            or "burst" in sources
        ),
        "instance_source": (
            "single"
            if not sources
            else sources[0]
            if len(sources) == 1
            else "mixed"
        ),
    }


def _description_profile(
    weapon: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Extract conservative qualitative mechanics from official description text.

    These labels are evidence hints only. They never become numeric statistics
    and remain separate from structured mechanics produced by normalization.
    """
    description = str(
        weapon.get("display_description")
        or weapon.get(
            "description_reference"
        )
        or ""
    ).strip()

    lowered = description.lower()

    mechanic_terms = {
        "chain": "chaining",
        "arc": "chaining",
        "ricochet": "ricochet",
        "homing": "homing",
        "lock-on": "lock_on",
        "lock on": "lock_on",
        "detonate": "delayed_activation",
        "detonation": "delayed_activation",
        "explode": "explosion",
        "exploding": "explosion",
        "ramp": "damage_ramp",
        "increase its damage": "damage_ramp",
        "return": "returning_projectile",
        "deploy": "deployable",
        "snare": "grouping",
        "dragging them together": "grouping",
    }

    mechanics = sorted(
        {
            mechanic_id
            for term, mechanic_id
            in mechanic_terms.items()
            if term in lowered
        }
    )

    return {
        "description_mechanic_present": bool(
            mechanics
        ),
        "description_evidence_quality": (
            "qualitative_extension"
            if mechanics
            else "absent"
        ),
        "description_mechanics": mechanics,
    }


def _special_mechanic_profile(
    *,
    description_profile: Mapping[str, Any],
    structured_mechanics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Separate structured mechanics from mechanics inferred from description text.

    The generic review concept is reserved for explicit mechanics that are not
    already handled by a specialized concept, or for unknown description
    mechanics that require cautious interpretation.
    """
    structured_mechanics = (
        structured_mechanics
        if isinstance(structured_mechanics, Mapping)
        else {}
    )

    description_mechanics = {
        str(item)
        for item in description_profile.get(
            "description_mechanics",
            [],
        )
        if str(item)
    }

    structured_present = bool(
        structured_mechanics
    )
    description_present = bool(
        description_profile.get(
            "description_mechanic_present"
        )
    )

    unknown_description_mechanics = (
        description_mechanics
        - KNOWN_DESCRIPTION_MECHANICS
    )

    return {
        "special_mechanic_present": (
            structured_present
            or description_present
        ),
        "has_explicit_special_mechanic": (
            structured_present
        ),
        "special_mechanic_needs_review": bool(
            structured_present
            or unknown_description_mechanics
        ),
        "unknown_description_mechanics": sorted(
            unknown_description_mechanics
        ),
    }


def _multi_target_profile(
    *,
    tags: set[str],
    component_profile: Mapping[str, Any],
    description_profile: Mapping[str, Any],
) -> dict[str, Any]:
    evidence: list[str] = []
    target_types: list[str] = []

    has_radial = bool(
        component_profile.get(
            "has_projectile_radial_component"
        )
        or component_profile.get(
            "has_charged_projectile_radial_component"
        )
    )

    if has_radial:
        evidence.append(
            "attack_modes.damage_components.radial"
        )
        target_types.append("radial")

    mechanics = set(
        description_profile.get(
            "description_mechanics",
            [],
        )
    )

    if "chaining" in mechanics:
        evidence.append(
            "display_description.chaining"
        )
        target_types.append("chaining")

    if "grouping" in mechanics:
        evidence.append(
            "display_description.grouping"
        )
        target_types.append("grouping")

    if (
        "aoe" in tags
        and not evidence
    ):
        evidence.append(
            "compatibility_tags.aoe"
        )
        target_types.append("unknown")

    return {
        "target_profile": (
            "multi_target_capable"
            if evidence
            else "single_target"
        ),
        "multi_target_type": (
            target_types[0]
            if len(target_types) == 1
            else "mixed"
            if len(target_types) > 1
            else "none"
        ),
        "multi_target_evidence_quality": (
            "structured"
            if has_radial
            else "descriptive"
            if any(
                item.startswith(
                    "display_description."
                )
                for item in evidence
            )
            else "compatibility_tag"
            if evidence
            else "none"
        ),
        "has_structured_multi_target_evidence": (
            has_radial
        ),
        "multi_target_evidence": evidence,
    }


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
    modes = _attack_modes(
        weapon
    )
    mode = _first_attack_mode(
        weapon
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

    instance_profile = _instance_profile(
        multishot=multishot,
        fire_iterations=fire_iterations,
        mode=mode,
    )
    delivery_instances = float(
        instance_profile[
            "base_instances_per_delivery"
        ]
    )

    magazine_size = _number(
        shared_stats.get("magazine_size")
    )
    reload_time = _number(
        shared_stats.get("reload_time")
    )
    magazine_duration = (
        _estimate_magazine_duration(
            magazine_size,
            fire_rate,
        )
    )

    application_frequency = (
        _classify_application_frequency(
            trigger_type,
            fire_rate,
            delivery_instances,
        )
    )

    consumption_rate, ammo_economy = (
        _classify_ammo_consumption(
            fire_rate,
            magazine_duration,
        )
    )

    component_profile = (
        _component_type_profile(
            modes
        )
    )
    damage_delivery = (
        _infer_delivery_profile(
            trigger_type=trigger_type,
            tags=tags,
            component_profile=component_profile,
        )
    )

    rhythm_profile = (
        _attack_rhythm_profile(
            modes,
            trigger_type,
        )
    )
    description_profile = (
        _description_profile(
            weapon
        )
    )
    target_profile = (
        _multi_target_profile(
            tags=tags,
            component_profile=component_profile,
            description_profile=description_profile,
        )
    )

    critical_evidence: list[str] = []
    _add_evidence(
        critical_evidence,
        "root_stats.critical_chance_percent",
        root_stats.get(
            "critical_chance_percent"
        ),
    )
    _add_evidence(
        critical_evidence,
        "root_stats.critical_multiplier",
        root_stats.get(
            "critical_multiplier"
        ),
    )

    status_evidence: list[str] = []
    _add_evidence(
        status_evidence,
        "root_stats.status_chance_percent",
        root_stats.get(
            "status_chance_percent"
        ),
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

    # The current normalized schema does not expose a dedicated structured
    # special-mechanic section. This placeholder keeps descriptive and
    # structured evidence separate until normalization provides one.
    structured_mechanics = weapon.get(
        "structured_mechanics"
    )
    special_profile = _special_mechanic_profile(
        description_profile=description_profile,
        structured_mechanics=(
            structured_mechanics
            if isinstance(
                structured_mechanics,
                Mapping,
            )
            else None
        ),
    )

    return {
        "interpretation_version": (
            INTERPRETATION_VERSION
        ),
        "weapon_category": category,
        "weapon_class": weapon_class,
        **rhythm_profile,
        "damage_delivery": damage_delivery,
        "damage_delivery_types": (
            component_profile["types"]
        ),
        **{
            key: value
            for key, value
            in component_profile.items()
            if key != "types"
        },
        "damage_behavior": (
            _infer_damage_behavior(
                trigger_type
            )
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
                delivery_instances,
            )
        ),
        "application_frequency": (
            application_frequency
        ),
        "continuous_application": (
            trigger_type == "continuous"
        ),
        "reload_friction": (
            _classify_reload_friction(
                magazine_duration,
                reload_time,
            )
        ),
        "consumption_rate_signal": (
            consumption_rate
        ),
        "ammo_economy_signal": (
            ammo_economy
        ),
        **target_profile,
        **special_profile,
        **description_profile,
        "mechanic_profile": {
            "has_multi_target_delivery": (
                target_profile[
                    "target_profile"
                ]
                == "multi_target_capable"
            ),
            "has_radial_component": bool(
                component_profile[
                    "has_projectile_radial_component"
                ]
                or component_profile[
                    "has_charged_projectile_radial_component"
                ]
            ),
            "has_beam_tag": (
                "beam" in tags
            ),
            "has_aoe_tag": (
                "aoe" in tags
            ),
        },
        **instance_profile,
        "estimated_magazine_duration_seconds": (
            round(
                magazine_duration,
                3,
            )
            if magazine_duration
            is not None
            else None
        ),
        "attack_mode_count": len(
            modes
        ),
        "mode_relationship": (
            _classify_mode_relationship(
                modes
            )
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
                target_profile[
                    "multi_target_evidence"
                ]
            ),
            "damage_delivery": (
                component_profile["types"]
            ),
            "description_mechanics": (
                description_profile[
                    "description_mechanics"
                ]
            ),
            "special_mechanic_needs_review": (
                special_profile[
                    "unknown_description_mechanics"
                ]
            ),
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
    modes = _attack_modes(
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
        shared_stats.get(
            "heavy_attack_damage"
        )
    )
    heavy_wind_up = _number(
        shared_stats.get(
            "heavy_attack_wind_up"
        )
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

    # Generic melee exports commonly include heavy-attack values. Their
    # presence proves capability, not that heavy attacks define the main role.
    has_heavy_attack_evidence = (
        heavy_damage > 0.0
        and heavy_wind_up > 0.0
    )
    has_slam_evidence = any(
        _number(
            shared_stats.get(field)
        ) > 0.0
        for field in (
            "slam_attack_damage",
            "slam_radial_damage",
            "slam_radius",
        )
    )
    has_heavy_slam_evidence = any(
        _number(
            shared_stats.get(field)
        ) > 0.0
        for field in (
            "heavy_slam_attack_damage",
            "heavy_slam_radial_damage",
            "heavy_slam_radius",
        )
    )

    if (
        has_heavy_attack_evidence
        and (
            has_slam_evidence
            or has_heavy_slam_evidence
        )
    ):
        melee_profile = "mixed_melee"
    elif has_heavy_attack_evidence:
        melee_profile = (
            "heavy_attack_capable"
        )
    elif (
        has_slam_evidence
        or has_heavy_slam_evidence
    ):
        melee_profile = "slam_capable"
    else:
        melee_profile = (
            "normal_attack_focused"
        )

    damage_behavior = (
        "sustained_melee"
        if attack_speed >= 1.0
        else "deliberate_melee"
    )

    if heavy_wind_up >= 1.0:
        handling_friction = "high"
    elif (
        heavy_wind_up > 0.0
        or (
            attack_speed > 0.0
            and attack_speed < 0.9
        )
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

    reach_profile = (
        "extended"
        if melee_range >= 3.0
        else "standard"
        if melee_range > 0.0
        else "undetermined"
    )

    critical_evidence: list[str] = []
    _add_evidence(
        critical_evidence,
        "root_stats.critical_chance_percent",
        root_stats.get(
            "critical_chance_percent"
        ),
    )
    _add_evidence(
        critical_evidence,
        "root_stats.critical_multiplier",
        root_stats.get(
            "critical_multiplier"
        ),
    )

    status_evidence: list[str] = []
    _add_evidence(
        status_evidence,
        "root_stats.status_chance_percent",
        root_stats.get(
            "status_chance_percent"
        ),
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
        shared_stats.get(
            "heavy_attack_wind_up"
        ),
    )

    target_evidence: list[str] = []
    _add_evidence(
        target_evidence,
        "shared_stats.range",
        shared_stats.get("range"),
    )

    return {
        "interpretation_version": (
            INTERPRETATION_VERSION
        ),
        "weapon_category": category,
        "weapon_class": weapon_class,
        "attack_behavior": (
            "melee_repeated"
        ),
        "damage_behavior": (
            damage_behavior
        ),
        "melee_profile": melee_profile,
        "has_heavy_attack_evidence": (
            has_heavy_attack_evidence
        ),
        "has_slam_evidence": (
            has_slam_evidence
        ),
        "has_heavy_slam_evidence": (
            has_heavy_slam_evidence
        ),
        "reach_profile": reach_profile,
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
                max(
                    attack_speed,
                    1.0,
                ),
            )
        ),
        "application_frequency": (
            application_frequency
        ),
        "continuous_application": False,
        "reload_friction": (
            "not_applicable"
        ),
        "handling_friction": (
            handling_friction
        ),
        "consumption_rate_signal": (
            "not_applicable"
        ),
        "ammo_economy_signal": (
            "not_applicable"
        ),
        "target_profile": (
            "undetermined"
        ),
        "multi_target_type": "none",
        "multi_target_evidence_quality": (
            "none"
        ),
        "has_structured_multi_target_evidence": (
            False
        ),
        "special_mechanic_present": (
            False
        ),
        "has_explicit_special_mechanic": (
            False
        ),
        "special_mechanic_needs_review": (
            False
        ),
        "unknown_description_mechanics": [],
        "description_mechanic_present": (
            False
        ),
        "description_evidence_quality": (
            "absent"
        ),
        "description_mechanics": [],
        "mechanic_profile": {
            "has_multi_target_delivery": (
                False
            ),
            "has_radial_component": (
                False
            ),
            "has_beam_tag": False,
            "has_aoe_tag": False,
        },
        "base_instances_per_delivery": (
            1.0
        ),
        "has_multi_instance_evidence": (
            False
        ),
        "instance_source": "single",
        "estimated_magazine_duration_seconds": (
            None
        ),
        "attack_mode_count": len(
            modes
        ),
        "mode_relationship": (
            _classify_mode_relationship(
                modes
            )
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
            "reach_profile": (
                target_evidence
            ),
            "melee_profile": [
                "shared_stats.heavy_attack_damage",
                "shared_stats.heavy_attack_wind_up",
                "shared_stats.slam_attack_damage",
                "shared_stats.heavy_slam_attack_damage",
            ],
        },
    }


def interpret_weapon(
    normalized_weapon: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Convert one normalized weapon entry into deterministic retrieval signals.

    Returned labels are auditable routing signals, not final weapon verdicts.
    """
    if not isinstance(
        normalized_weapon,
        Mapping,
    ):
        raise TypeError(
            "normalized_weapon must be a Mapping."
        )

    classification = _mapping(
        normalized_weapon.get(
            "classification"
        ),
        "classification",
    )
    category = str(
        classification.get("category") or ""
    )

    logger.info(
        "Starting deterministic weapon interpretation "
        "| weapon=%s | category=%s",
        normalized_weapon.get(
            "display_name"
        ),
        category,
    )

    if category in RANGED_CATEGORIES:
        interpretation = (
            _interpret_ranged(
                normalized_weapon
            )
        )
    elif category in MELEE_CATEGORIES:
        interpretation = (
            _interpret_melee(
                normalized_weapon
            )
        )
    else:
        raise ValueError(
            "Unsupported normalized weapon "
            f"category: {category}"
        )

    logger.info(
        "Weapon interpretation completed "
        "| critical=%s | status=%s "
        "| behavior=%s | target=%s "
        "| reload=%s | delivery=%s "
        "| modes=%s",
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
            "reload_friction"
        ),
        interpretation.get(
            "damage_delivery"
        ),
        interpretation.get(
            "mode_relationship"
        ),
    )

    return interpretation


analyze_parsed_weapon = interpret_weapon