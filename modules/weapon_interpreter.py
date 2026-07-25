# modules/weapon_interpreter.py

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from modules.logger import get_logger


logger = get_logger(__name__)

INTERPRETATION_VERSION = 6

MELEE_CATEGORIES = {
    "melee",
    "archmelee",
    "drifter_melee",
}

PROJECTILE_COMPONENT_TYPES = {
    "projectile_direct",
    "projectile_radial",
    "charged_projectile_direct",
    "charged_projectile_radial",
}

DIRECT_COMPONENT_TYPES = {
    "direct",
    "projectile_direct",
    "charged_projectile_direct",
}

RADIAL_COMPONENT_TYPES = {
    "projectile_radial",
    "charged_projectile_radial",
}

TRIGGER_NORMALIZATION = {
    "automatic": "automatic",
    "semi_automatic": "semi_automatic",
    "burst": "burst",
    "auto burst": "burst",
    "charge": "charge",
    "continuous": "held",
    "active": "staged",
    "duplex": "duplex",
    None: "undetermined",
}

GENERIC_DAMAGE_SIGNATURES = (
    {"impact": 40.0},
    {
        "impact": 3.33333,
        "puncture": 3.33333,
        "slash": 3.33334,
    },
)

DESCRIPTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "beam_delivery": (
        r"\bcontinuous beam\b",
        r"\bbeam\b",
    ),
    "chaining": (
        r"\barcs? (?:among|between|to)\b",
        r"\bchain(?:s|ed|ing)?\b",
        r"\bnearby enemies\b.*\barc",
    ),
    "spool_up": (
        r"\bspools? up\b",
        r"\bfire rate increases\b",
        r"\bdamage increases while firing\b",
        r"\bramps? up\b",
    ),
    "press_release": (
        r"\bon release\b",
        r"\bpress and release\b",
        r"\bduplex\b",
    ),
    "secondary_activation": (
        r"\balternate fire\b",
        r"\bsecondary fire\b",
        r"\bmanual(?:ly)? detonate\b",
        r"\bdetonate(?:s|d)? on command\b",
        r"\bswitch(?:es)? firing modes?\b",
    ),
    "conditional_extra_instance": (
        r"\badditional projectile\b",
        r"\bextra projectile\b",
        r"\bcreates? another\b",
        r"\bspawns? an? (?:attack|projectile)\b",
    ),
    "ricochet": (
        r"\bricochet\b",
        r"\bbounces? between\b",
    ),
    "returning_projectile": (
        r"\breturns? to\b",
        r"\bboomerang\b",
    ),
    "punch_through": (
        r"\bpunch through\b",
        r"\bpenetrates? (?:enemies|targets|surfaces)\b",
    ),
    "incremental_reload": (
        r"\breloads? (?:one|each) (?:round|shell)\b",
        r"\bround by round\b",
        r"\bshell by shell\b",
    ),
    "staged_reload": (
        r"\bstaged reload\b",
        r"\breload stages?\b",
    ),
    "ammo_regeneration": (
        r"\bregenerates? ammo\b",
        r"\bammo regenerat",
        r"\brecharges? ammunition\b",
    ),
    "unlimited_ammo": (
        r"\bunlimited ammo\b",
        r"\bdoes not consume ammo\b",
    ),
    "maintained_contact": (
        r"\bmaintain(?:ed)? contact\b",
        r"\bwhile the beam remains on\b",
    ),
    "strong_recoil": (
        r"\bstrong recoil\b",
        r"\bheavy recoil\b",
    ),
    "wide_spread": (
        r"\bwide spread\b",
        r"\bhigh spread\b",
    ),
    "slow_projectile": (
        r"\bslow projectile\b",
        r"\bslow-moving projectile\b",
    ),
    "close_range_requirement": (
        r"\bclose range\b",
        r"\bshort range\b",
    ),
}


class WeaponInterpretationError(ValueError):
    """Raised when normalized weapon data cannot be interpreted safely."""


def evidence(
    value: Any,
    confidence: str,
    *source_paths: str,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "confidence": confidence,
        "source_paths": list(source_paths),
        "reason": reason,
    }


def _mapping(
    value: Any,
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WeaponInterpretationError(
            f"Missing or invalid normalized section: {name}."
        )

    return value


def _classification(
    weapon: Mapping[str, Any],
) -> Mapping[str, Any]:
    return _mapping(
        weapon.get("classification"),
        "classification",
    )


def _shared(
    weapon: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = weapon.get("shared_stats")

    return (
        value
        if isinstance(value, Mapping)
        else {}
    )


def _root(
    weapon: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = weapon.get("root_stats")

    return (
        value
        if isinstance(value, Mapping)
        else {}
    )


def _modes(
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


def _components(
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


def _tags(
    weapon: Mapping[str, Any],
) -> set[str]:
    raw_tags = _shared(weapon).get(
        "compatibility_tags"
    )

    if not isinstance(raw_tags, list):
        return set()

    return {
        str(tag).strip().lower()
        for tag in raw_tags
        if str(tag).strip()
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mode_or_root_number(
    mode: Mapping[str, Any],
    weapon: Mapping[str, Any],
    key: str,
) -> tuple[float | None, str | None]:
    mode_value = _number(
        mode.get(key)
    )

    if mode_value is not None:
        return (
            mode_value,
            f"attack_modes[].{key}",
        )

    root_value = _number(
        _root(weapon).get(key)
    )

    if root_value is not None:
        return (
            root_value,
            f"root_stats.{key}",
        )

    return None, None


def _damage_total(
    component: Mapping[str, Any],
) -> float:
    raw_damage = component.get("damage")

    if not isinstance(raw_damage, Mapping):
        return 0.0

    total = 0.0

    for value in raw_damage.values():
        number = _number(value)

        if number is not None:
            total += number

    return total


def _approximately_equal(
    left: float,
    right: float,
    tolerance: float = 0.001,
) -> bool:
    return abs(left - right) <= tolerance


def _matches_signature(
    damage: Mapping[str, Any],
    signature: Mapping[str, float],
) -> bool:
    if set(damage) != set(signature):
        return False

    for key, expected in signature.items():
        actual = _number(
            damage.get(key)
        )

        if (
            actual is None
            or not _approximately_equal(
                actual,
                expected,
            )
        ):
            return False

    return True


def _has_generic_signature(
    mode: Mapping[str, Any],
) -> bool:
    for component in _components(mode):
        damage = component.get("damage")

        if not isinstance(damage, Mapping):
            continue

        if any(
            _matches_signature(
                damage,
                signature,
            )
            for signature
            in GENERIC_DAMAGE_SIGNATURES
        ):
            return True

    return False


def _extract_description_claims(
    weapon: Mapping[str, Any],
) -> list[dict[str, Any]]:
    description = str(
        weapon.get("display_description")
        or weapon.get("description_reference")
        or ""
    ).strip()

    if not description:
        return []

    lowered = description.lower()
    claims: list[dict[str, Any]] = []

    for mechanic_type, patterns in (
        DESCRIPTION_PATTERNS.items()
    ):
        source_fragment: str | None = None

        for pattern in patterns:
            match = re.search(
                pattern,
                lowered,
                flags=re.IGNORECASE,
            )

            if match:
                source_fragment = description[
                    match.start():match.end()
                ]
                break

        if source_fragment is None:
            continue

        claims.append({
            "mechanic_type": mechanic_type,
            "source_fragment": source_fragment,
            "confidence": (
                "validated_description"
            ),
            "affected_mode_id": None,
        })

    return claims


def _claims_of_type(
    claims: list[dict[str, Any]],
    *mechanic_types: str,
) -> list[dict[str, Any]]:
    accepted = set(mechanic_types)

    return [
        claim
        for claim in claims
        if claim.get("mechanic_type")
        in accepted
    ]


def _derive_component_delivery(
    component: Mapping[str, Any],
    tags: set[str],
) -> dict[str, Any]:
    component_type = str(
        component.get("component_type")
        or ""
    )

    if component_type in (
        PROJECTILE_COMPONENT_TYPES
    ):
        delivery_path = "projectile"
        delivery_confidence = "structured"

    elif "beam" in tags:
        delivery_path = "beam"
        delivery_confidence = "normalized"

    else:
        delivery_path = "undetermined"
        delivery_confidence = "unavailable"

    if component_type in RADIAL_COMPONENT_TYPES:
        spatial_application = "radial"

    elif component_type in DIRECT_COMPONENT_TYPES:
        spatial_application = "direct"

    else:
        spatial_application = "undetermined"

    return {
        "component_type": (
            component_type or None
        ),
        "delivery_path": delivery_path,
        "delivery_confidence": (
            delivery_confidence
        ),
        "spatial_application": (
            spatial_application
        ),
    }


def _aggregate_delivery_path(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    paths = {
        record["delivery_path"]
        for record in records
        if record["delivery_path"]
        != "undetermined"
    }

    if len(paths) == 1:
        return evidence(
            next(iter(paths)),
            "derived",
            (
                "attack_modes[]."
                "damage_components[].component_type"
            ),
            "shared_stats.compatibility_tags",
        )

    if len(paths) > 1:
        return evidence(
            "mixed",
            "derived",
            (
                "attack_modes[]."
                "damage_components[].component_type"
            ),
            "shared_stats.compatibility_tags",
        )

    return evidence(
        "undetermined",
        "unavailable",
        reason=(
            "No positive delivery-path evidence "
            "is available."
        ),
    )


def _aggregate_spatial_application(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    applications = {
        record["spatial_application"]
        for record in records
        if record["spatial_application"]
        != "undetermined"
    }

    if applications == {"direct"}:
        value = "direct"

    elif applications == {"radial"}:
        value = "radial"

    elif (
        "direct" in applications
        and "radial" in applications
    ):
        value = "mixed"

    else:
        value = "undetermined"

    return evidence(
        value,
        (
            "derived"
            if value != "undetermined"
            else "unavailable"
        ),
        (
            "attack_modes[]."
            "damage_components[].component_type"
        ),
    )


def _derive_base_instance_count(
    mode: Mapping[str, Any],
    weapon: Mapping[str, Any],
) -> dict[str, Any]:
    fire_iterations = _number(
        mode.get("fire_iterations")
    )
    multishot = _number(
        _shared(weapon).get("multishot")
    )

    if fire_iterations is not None:
        return evidence(
            fire_iterations,
            "normalized",
            "attack_modes[].fire_iterations",
            reason=(
                "Reported iteration count. It is not "
                "automatically treated as pellet count, "
                "ammo cost, or independent status eligibility."
            ),
        )

    if multishot is not None:
        return evidence(
            multishot,
            "normalized",
            "shared_stats.multishot",
            reason=(
                "Fallback candidate count. It is not "
                "multiplied by fire_iterations."
            ),
        )

    return evidence(
        None,
        "unavailable",
        reason=(
            "No usable candidate instance count exists."
        ),
    )


def _derive_recovery_model(
    weapon: Mapping[str, Any],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    tags = _tags(weapon)
    shared = _shared(weapon)

    if "battery" in tags:
        return evidence(
            "battery_like",
            "normalized",
            "shared_stats.compatibility_tags",
            reason=(
                "Battery behavior is identified, but "
                "exact regeneration timing is unknown."
            ),
        )

    if _claims_of_type(
        claims,
        "incremental_reload",
    ):
        return evidence(
            "incremental",
            "validated_description",
            "display_description",
        )

    if _claims_of_type(
        claims,
        "staged_reload",
    ):
        return evidence(
            "staged",
            "validated_description",
            "display_description",
        )

    if _number(
        shared.get("reload_time")
    ) is not None:
        return evidence(
            "conventional_timed_reload",
            "derived",
            "shared_stats.reload_time",
            reason=(
                "A total reload duration exists, but "
                "full-magazine behavior is not "
                "structurally confirmed."
            ),
        )

    return evidence(
        "undetermined",
        "unavailable",
        reason=(
            "No recovery-model evidence is available."
        ),
    )


def _build_mode_profile(
    weapon: Mapping[str, Any],
    mode: Mapping[str, Any],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    components = _components(mode)
    tags = _tags(weapon)

    trigger_raw = mode.get("trigger_type")
    trigger_type = TRIGGER_NORMALIZATION.get(
        trigger_raw,
        str(trigger_raw or "undetermined"),
    )

    critical_chance, critical_path = (
        _mode_or_root_number(
            mode,
            weapon,
            "critical_chance_percent",
        )
    )
    critical_multiplier, multiplier_path = (
        _mode_or_root_number(
            mode,
            weapon,
            "critical_multiplier",
        )
    )
    status_chance, status_path = (
        _mode_or_root_number(
            mode,
            weapon,
            "status_chance_percent",
        )
    )
    fire_rate, fire_rate_path = (
        _mode_or_root_number(
            mode,
            weapon,
            "fire_rate",
        )
    )

    delivery_records = [
        _derive_component_delivery(
            component,
            tags,
        )
        for component in components
    ]

    active_damage_present = (
        bool(components)
        and any(
            _damage_total(component) > 0
            for component in components
        )
    )

    base_instance_count = (
        _derive_base_instance_count(
            mode,
            weapon,
        )
    )

    burst = mode.get("burst")
    burst_count = (
        _number(burst.get("count"))
        if isinstance(burst, Mapping)
        else None
    )

    has_charge = bool(
        mode.get("charge_evidence")
        or trigger_type == "charge"
    )

    repeatable_event = bool(
        active_damage_present
        and fire_rate is not None
        and fire_rate > 0
    )

    if (
        repeatable_event
        and trigger_type
        in {"automatic", "held"}
    ):
        continuity: bool | None = True

    elif trigger_type in {
        "semi_automatic",
        "burst",
        "charge",
        "duplex",
        "staged",
        "melee",
    }:
        continuity = False

    else:
        continuity = None

    conditional_instance = bool(
        _claims_of_type(
            claims,
            "conditional_extra_instance",
            "ricochet",
            "returning_projectile",
        )
    )

    distributed_instance = (
        True
        if (
            isinstance(
                base_instance_count["value"],
                (int, float),
            )
            and base_instance_count["value"] > 1
            and _claims_of_type(
                claims,
                "conditional_extra_instance",
            )
        )
        else None
    )

    return {
        "mode_id": mode.get("mode_id"),
        "signals": {
            "trigger_type": evidence(
                trigger_type,
                "normalized",
                "attack_modes[].trigger_type",
            ),
            "critical_chance": evidence(
                critical_chance,
                (
                    "normalized"
                    if critical_path
                    else "unavailable"
                ),
                *(
                    [critical_path]
                    if critical_path
                    else []
                ),
            ),
            "critical_multiplier": evidence(
                critical_multiplier,
                (
                    "normalized"
                    if multiplier_path
                    else "unavailable"
                ),
                *(
                    [multiplier_path]
                    if multiplier_path
                    else []
                ),
            ),
            "status_chance": evidence(
                status_chance,
                (
                    "normalized"
                    if status_path
                    else "unavailable"
                ),
                *(
                    [status_path]
                    if status_path
                    else []
                ),
            ),
            "fire_rate": evidence(
                fire_rate,
                (
                    "normalized"
                    if fire_rate_path
                    else "unavailable"
                ),
                *(
                    [fire_rate_path]
                    if fire_rate_path
                    else []
                ),
            ),
            "burst_count": evidence(
                burst_count,
                (
                    "structured"
                    if burst_count is not None
                    else "unavailable"
                ),
                "attack_modes[].burst.count",
            ),
            "charge_time": evidence(
                None,
                "unavailable",
                reason=(
                    "Charge evidence can exist without "
                    "a preserved duration."
                ),
            ),
            "has_charge_evidence": evidence(
                has_charge,
                "derived",
                "attack_modes[].charge_evidence",
                "attack_modes[].trigger_type",
            ),
            "has_spool_up_evidence": evidence(
                bool(
                    _claims_of_type(
                        claims,
                        "spool_up",
                    )
                ),
                (
                    "validated_description"
                    if _claims_of_type(
                        claims,
                        "spool_up",
                    )
                    else "unavailable"
                ),
                "display_description",
            ),
            "has_press_release_evidence": evidence(
                bool(
                    trigger_type == "duplex"
                    or "FireOnUp" in str(
                        mode.get("state_name")
                        or ""
                    )
                    or _claims_of_type(
                        claims,
                        "press_release",
                    )
                ),
                "derived",
                "attack_modes[].trigger_type",
                "attack_modes[].state_name",
                "display_description",
            ),
            "has_secondary_activation_evidence":
                evidence(
                    bool(
                        _claims_of_type(
                            claims,
                            "secondary_activation",
                        )
                    ),
                    (
                        "validated_description"
                        if _claims_of_type(
                            claims,
                            "secondary_activation",
                        )
                        else "unavailable"
                    ),
                    "display_description",
                ),
            "base_instance_count":
                base_instance_count,
            "pellet_count": evidence(
                None,
                "unavailable",
                reason=(
                    "The normalized schema does not "
                    "preserve a universal pellet-count "
                    "field."
                ),
            ),
            "multishot": evidence(
                _number(
                    _shared(weapon).get(
                        "multishot"
                    )
                ),
                (
                    "structured"
                    if _number(
                        _shared(weapon).get(
                            "multishot"
                        )
                    ) is not None
                    else "unavailable"
                ),
                "shared_stats.multishot",
            ),
            "damage_component_count": evidence(
                len(components),
                "structured",
                (
                    "attack_modes[]."
                    "damage_components"
                ),
            ),
            "has_conditional_instance_evidence":
                evidence(
                    conditional_instance,
                    (
                        "validated_description"
                        if conditional_instance
                        else "unavailable"
                    ),
                    "display_description",
                ),
            "delivery_path":
                _aggregate_delivery_path(
                    delivery_records
                ),
            "spatial_application":
                _aggregate_spatial_application(
                    delivery_records
                ),
            "has_radial_component": evidence(
                (
                    any(
                        record[
                            "spatial_application"
                        ] == "radial"
                        for record
                        in delivery_records
                    )
                    if components
                    else None
                ),
                (
                    "derived"
                    if components
                    else "unavailable"
                ),
                (
                    "attack_modes[]."
                    "damage_components[]."
                    "component_type"
                ),
            ),
            "active_damage_output_present":
                evidence(
                    (
                        active_damage_present
                        if components
                        else None
                    ),
                    (
                        "derived"
                        if components
                        else "unavailable"
                    ),
                    (
                        "attack_modes[]."
                        "damage_components[].damage"
                    ),
                ),
            "has_repeatable_attack_cycle":
                evidence(
                    repeatable_event,
                    (
                        "derived"
                        if fire_rate is not None
                        else "unavailable"
                    ),
                    "attack_modes[].fire_rate",
                    (
                        "attack_modes[]."
                        "damage_components"
                    ),
                    reason=(
                        "This confirms repeatable attack "
                        "events, not a complete ammo-and-"
                        "recovery cycle."
                    ),
                ),
            "mechanical_application_continuity_present":
                evidence(
                    continuity,
                    (
                        "derived"
                        if continuity is not None
                        else "unavailable"
                    ),
                    "attack_modes[].trigger_type",
                    "attack_modes[].fire_rate",
                ),
            "eligible_status_opportunity_profile_present":
                evidence(
                    (
                        True
                        if (
                            status_chance
                            is not None
                            and base_instance_count[
                                "value"
                            ] is not None
                        )
                        else None
                    ),
                    (
                        "heuristic"
                        if (
                            status_chance
                            is not None
                            and base_instance_count[
                                "value"
                            ] is not None
                        )
                        else "unavailable"
                    ),
                    (
                        "attack_modes[]."
                        "status_chance_percent"
                    ),
                    (
                        "attack_modes[]."
                        "fire_iterations"
                    ),
                    reason=(
                        "Independent eligibility per "
                        "instance is not universally "
                        "confirmed by the export."
                    ),
                ),
            "sustained_cycle_profile_present":
                evidence(
                    None,
                    "unavailable",
                    "shared_stats.magazine_size",
                    "shared_stats.reload_time",
                    "attack_modes[].fire_rate",
                    reason=(
                        "The current schema does not "
                        "guarantee ammo cost per "
                        "consumption event for every "
                        "firing model."
                    ),
                ),
            "distributed_instance_profile_present":
                evidence(
                    distributed_instance,
                    (
                        "validated_description"
                        if distributed_instance is True
                        else "unavailable"
                    ),
                    (
                        "attack_modes[]."
                        "fire_iterations"
                    ),
                    "display_description",
                ),
        },
        "delivery_records": delivery_records,
    }


def _first_non_null_signal(
    mode_profiles: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    for profile in mode_profiles:
        signal = profile["signals"].get(
            field
        )

        if (
            isinstance(signal, Mapping)
            and signal.get("value") is not None
        ):
            return dict(signal)

    return evidence(
        None,
        "unavailable",
        reason=(
            f"No mode produced a usable "
            f"`{field}` value."
        ),
    )


def _any_true_signal(
    mode_profiles: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    saw_false = False
    source_paths: list[str] = []
    confidence: str | None = None

    for profile in mode_profiles:
        signal = profile["signals"].get(
            field
        )

        if not isinstance(signal, Mapping):
            continue

        value = signal.get("value")

        if value is True:
            return evidence(
                True,
                str(
                    signal.get("confidence")
                    or "derived"
                ),
                *signal.get(
                    "source_paths",
                    [],
                ),
            )

        if value is False:
            saw_false = True
            confidence = str(
                signal.get("confidence")
                or "derived"
            )
            source_paths.extend(
                signal.get(
                    "source_paths",
                    [],
                )
            )

    if saw_false:
        return evidence(
            False,
            confidence or "derived",
            *dict.fromkeys(
                source_paths
            ),
        )

    return evidence(
        None,
        "unavailable",
        reason=(
            f"No mode established `{field}`."
        ),
    )


def _build_multi_target_records(
    mode_profiles: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for profile in mode_profiles:
        mode_id = profile.get("mode_id")

        for index, delivery in enumerate(
            profile.get(
                "delivery_records",
                [],
            ),
            start=1,
        ):
            if (
                delivery.get(
                    "spatial_application"
                )
                != "radial"
            ):
                continue

            records.append({
                "mode_id": mode_id,
                "component_index": index,
                "mechanic_type": "radial",
                "radius": None,
                "falloff": None,
                "confidence": (
                    "structured_component"
                ),
            })

    for claim in claims:
        mechanic_type = claim.get(
            "mechanic_type"
        )

        if mechanic_type == "chaining":
            records.append({
                "mode_id": claim.get(
                    "affected_mode_id"
                ),
                "mechanic_type": "chaining",
                "additional_target_count": None,
                "chain_range": None,
                "damage_retention": None,
                "confidence": (
                    "validated_description"
                ),
            })

        elif mechanic_type == "punch_through":
            records.append({
                "mode_id": claim.get(
                    "affected_mode_id"
                ),
                "mechanic_type": (
                    "linear_penetration"
                ),
                "punch_through_depth": None,
                "confidence": (
                    "validated_description"
                ),
            })

    return records


def _build_special_records(
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    specialized_mechanics = {
        "beam_delivery",
        "chaining",
        "punch_through",
        "incremental_reload",
        "staged_reload",
        "ammo_regeneration",
        "unlimited_ammo",
    }

    records: list[dict[str, Any]] = []

    for index, claim in enumerate(
        claims,
        start=1,
    ):
        mechanic_type = claim.get(
            "mechanic_type"
        )

        if (
            mechanic_type
            in specialized_mechanics
        ):
            continue

        records.append({
            "mechanic_id": (
                f"description_mechanic_{index}"
            ),
            "mechanic_type": (
                mechanic_type
                or "unclassified"
            ),
            "affected_mode_id": claim.get(
                "affected_mode_id"
            ),
            "evidence_confidence": (
                claim.get(
                    "confidence",
                    "validated_description",
                )
            ),
            "source_fragment": claim.get(
                "source_fragment"
            ),
        })

    return records


def _build_operational_friction_records(
    weapon: Mapping[str, Any],
    mode_profiles: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    shared = _shared(weapon)
    category = str(
        _classification(weapon).get(
            "category"
        )
        or ""
    )

    reload_time = _number(
        shared.get("reload_time")
    )

    if reload_time is not None:
        records.append({
            "friction_type": "interruption",
            "source": "reload_time",
            "value": reload_time,
            "unit": "seconds",
            "severity": None,
            "confidence": "structured",
        })

    heavy_wind_up = _number(
        shared.get(
            "heavy_attack_wind_up"
        )
    )

    if heavy_wind_up is not None:
        records.append({
            "friction_type": "preparation",
            "source": (
                "heavy_attack_wind_up"
            ),
            "value": heavy_wind_up,
            "unit": "seconds",
            "severity": None,
            "confidence": "structured",
        })

    if any(
        profile["signals"][
            "has_charge_evidence"
        ]["value"] is True
        for profile in mode_profiles
    ):
        records.append({
            "friction_type": "preparation",
            "source": "charge_evidence",
            "value": None,
            "unit": None,
            "severity": None,
            "confidence": "derived",
        })

    if any(
        profile["signals"][
            "has_spool_up_evidence"
        ]["value"] is True
        for profile in mode_profiles
    ):
        records.append({
            "friction_type": "preparation",
            "source": "spool_up",
            "value": None,
            "unit": None,
            "severity": None,
            "confidence": (
                "validated_description"
            ),
        })

    if (
        category in MELEE_CATEGORIES
        and _number(
            shared.get("range")
        ) is not None
    ):
        records.append({
            "friction_type": "positioning",
            "source": "melee_range",
            "value": _number(
                shared.get("range")
            ),
            "unit": "meters",
            "severity": None,
            "confidence": "structured",
        })

    for claim in claims:
        mechanic_type = claim.get(
            "mechanic_type"
        )

        if mechanic_type in {
            "strong_recoil",
            "wide_spread",
        }:
            friction_type = "handling"

        elif mechanic_type in {
            "slow_projectile",
            "maintained_contact",
        }:
            friction_type = "tracking"

        elif (
            mechanic_type
            == "close_range_requirement"
        ):
            friction_type = "positioning"

        else:
            continue

        records.append({
            "friction_type": friction_type,
            "source": (
                "validated_description"
            ),
            "value": mechanic_type,
            "unit": None,
            "severity": None,
            "confidence": (
                "validated_description"
            ),
        })

    return records


def _flatten_signals(
    signals: Mapping[
        str,
        Mapping[str, Any],
    ],
) -> dict[str, Any]:
    return {
        field: record.get("value")
        for field, record
        in signals.items()
        if (
            isinstance(record, Mapping)
            and "value" in record
        )
    }


def interpret_weapon(
    normalized_weapon: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Translate normalized weapon data into auditable internal-library signals.

    This layer does not select a final role, improvement, comfort rating, or
    weapon verdict. It records supported observations and uncertainty only.
    """
    if not isinstance(
        normalized_weapon,
        Mapping,
    ):
        raise TypeError(
            "normalized_weapon must be a Mapping."
        )

    classification = _classification(
        normalized_weapon
    )
    category = str(
        classification.get("category")
        or ""
    )
    modes = _modes(
        normalized_weapon
    )

    if not modes:
        raise WeaponInterpretationError(
            "Normalized weapon requires "
            "at least one attack mode."
        )

    claims = _extract_description_claims(
        normalized_weapon
    )

    mode_profiles = [
        _build_mode_profile(
            normalized_weapon,
            mode,
            claims,
        )
        for mode in modes
    ]

    all_components = [
        component
        for mode in modes
        for component in _components(mode)
    ]

    multi_target_records = (
        _build_multi_target_records(
            mode_profiles,
            claims,
        )
    )
    special_records = (
        _build_special_records(
            claims
        )
    )
    friction_records = (
        _build_operational_friction_records(
            normalized_weapon,
            mode_profiles,
            claims,
        )
    )

    primary_signals = (
        mode_profiles[0]["signals"]
    )

    critical_chance = (
        _first_non_null_signal(
            mode_profiles,
            "critical_chance",
        )
    )
    critical_multiplier = (
        _first_non_null_signal(
            mode_profiles,
            "critical_multiplier",
        )
    )
    status_chance = (
        _first_non_null_signal(
            mode_profiles,
            "status_chance",
        )
    )

    description = str(
        normalized_weapon.get(
            "display_description"
        )
        or normalized_weapon.get(
            "description_reference"
        )
        or ""
    ).strip()

    tags = _tags(
        normalized_weapon
    )
    recovery_model = (
        _derive_recovery_model(
            normalized_weapon,
            claims,
        )
    )

    if "beam" in tags:
        has_beam: bool | None = True
        beam_confidence = "normalized"

    elif _claims_of_type(
        claims,
        "beam_delivery",
    ):
        has_beam = True
        beam_confidence = (
            "validated_description"
        )

    else:
        has_beam = None
        beam_confidence = "unavailable"

    ammo_regeneration = bool(
        _claims_of_type(
            claims,
            "ammo_regeneration",
        )
    )

    signals: dict[
        str,
        dict[str, Any],
    ] = {
        "weapon_category": evidence(
            category,
            "structured",
            "classification.category",
        ),
        "critical_profile_present":
            evidence(
                (
                    critical_chance[
                        "value"
                    ] is not None
                    and critical_multiplier[
                        "value"
                    ] is not None
                ),
                "derived",
                *critical_chance.get(
                    "source_paths",
                    [],
                ),
                *critical_multiplier.get(
                    "source_paths",
                    [],
                ),
            ),
        "critical_chance":
            critical_chance,
        "critical_multiplier":
            critical_multiplier,
        "status_profile_present":
            evidence(
                status_chance[
                    "value"
                ] is not None,
                "derived",
                *status_chance.get(
                    "source_paths",
                    [],
                ),
            ),
        "status_chance":
            status_chance,
        "eligible_status_opportunity_profile_present":
            _any_true_signal(
                mode_profiles,
                (
                    "eligible_status_"
                    "opportunity_profile_present"
                ),
            ),
        "description_present": evidence(
            bool(description),
            "structured",
            "display_description",
        ),
        "description_claims_present":
            evidence(
                bool(claims),
                (
                    "validated_description"
                    if claims
                    else "unavailable"
                ),
                "display_description",
            ),
        "damage_components_present":
            evidence(
                bool(all_components),
                "structured",
                (
                    "attack_modes[]."
                    "damage_components"
                ),
            ),
        "attack_mode_records_count":
            evidence(
                len(modes),
                "structured",
                "attack_modes",
            ),
        "base_instance_count":
            primary_signals[
                "base_instance_count"
            ],
        "damage_component_count":
            evidence(
                len(all_components),
                "structured",
                (
                    "attack_modes[]."
                    "damage_components"
                ),
            ),
        "melee_attack_records_present":
            evidence(
                (
                    category
                    in MELEE_CATEGORIES
                    and bool(modes)
                ),
                "derived",
                "classification.category",
                "attack_modes",
            ),
        "has_radial_component":
            _any_true_signal(
                mode_profiles,
                "has_radial_component",
            ),
        "active_damage_output_present":
            _any_true_signal(
                mode_profiles,
                (
                    "active_damage_"
                    "output_present"
                ),
            ),
        "has_repeatable_attack_cycle":
            _any_true_signal(
                mode_profiles,
                (
                    "has_repeatable_"
                    "attack_cycle"
                ),
            ),
        "delivery_path":
            primary_signals[
                "delivery_path"
            ],
        "spatial_application":
            primary_signals[
                "spatial_application"
            ],
        "uses_beam_delivery":
            evidence(
                has_beam,
                beam_confidence,
                (
                    "shared_stats."
                    "compatibility_tags"
                ),
                "display_description",
            ),
        "has_mode_state_evidence":
            evidence(
                any(
                    bool(
                        mode.get(
                            "state_name"
                        )
                    )
                    for mode in modes
                ),
                "derived",
                "attack_modes[].state_name",
            ),
        "has_parent_mode_relationship":
            evidence(
                None,
                "unavailable",
                reason=(
                    "The normalized schema does "
                    "not preserve parent-mode "
                    "relationships."
                ),
            ),
        "has_ambiguous_mode_records":
            evidence(
                any(
                    (
                        not mode.get(
                            "state_name"
                        )
                        or not _components(
                            mode
                        )
                        or _has_generic_signature(
                            mode
                        )
                    )
                    for mode in modes
                ),
                "heuristic",
                "attack_modes[].state_name",
                (
                    "attack_modes[]."
                    "damage_components"
                ),
            ),
        "recovery_model":
            recovery_model,
        "preparation_friction_present":
            evidence(
                any(
                    record[
                        "friction_type"
                    ] == "preparation"
                    for record
                    in friction_records
                ),
                "derived",
                (
                    "shared_stats."
                    "heavy_attack_wind_up"
                ),
                (
                    "attack_modes[]."
                    "charge_evidence"
                ),
                "display_description",
            ),
        "interruption_friction_present":
            evidence(
                any(
                    record[
                        "friction_type"
                    ] == "interruption"
                    for record
                    in friction_records
                ),
                "derived",
                "shared_stats.reload_time",
            ),
        "has_spool_up_evidence":
            _any_true_signal(
                mode_profiles,
                "has_spool_up_evidence",
            ),
        "has_press_release_evidence":
            _any_true_signal(
                mode_profiles,
                "has_press_release_evidence",
            ),
        "has_secondary_activation_evidence":
            _any_true_signal(
                mode_profiles,
                (
                    "has_secondary_"
                    "activation_evidence"
                ),
            ),
        "has_chaining": evidence(
            bool(
                _claims_of_type(
                    claims,
                    "chaining",
                )
            ),
            (
                "validated_description"
                if _claims_of_type(
                    claims,
                    "chaining",
                )
                else "unavailable"
            ),
            "display_description",
        ),
        "has_conditional_instance_evidence":
            _any_true_signal(
                mode_profiles,
                (
                    "has_conditional_"
                    "instance_evidence"
                ),
            ),
        "handling_friction_present":
            evidence(
                any(
                    record[
                        "friction_type"
                    ] == "handling"
                    for record
                    in friction_records
                ),
                (
                    "validated_description"
                    if any(
                        record[
                            "friction_type"
                        ] == "handling"
                        for record
                        in friction_records
                    )
                    else "unavailable"
                ),
                "display_description",
            ),
        "tracking_friction_present":
            evidence(
                any(
                    record[
                        "friction_type"
                    ] == "tracking"
                    for record
                    in friction_records
                ),
                (
                    "validated_description"
                    if any(
                        record[
                            "friction_type"
                        ] == "tracking"
                        for record
                        in friction_records
                    )
                    else "unavailable"
                ),
                "display_description",
            ),
        "positioning_friction_present":
            evidence(
                any(
                    record[
                        "friction_type"
                    ] == "positioning"
                    for record
                    in friction_records
                ),
                "derived",
                "shared_stats.range",
                "display_description",
            ),
        "validated_description_mechanic_present":
            evidence(
                bool(claims),
                (
                    "validated_description"
                    if claims
                    else "unavailable"
                ),
                "display_description",
            ),
        "special_mechanic_records_present":
            evidence(
                bool(special_records),
                (
                    "derived"
                    if special_records
                    else "unavailable"
                ),
                "display_description",
            ),
        "structured_special_mechanic_present":
            evidence(
                bool(
                    normalized_weapon.get(
                        "structured_mechanics"
                    )
                ),
                (
                    "structured"
                    if normalized_weapon.get(
                        "structured_mechanics"
                    )
                    else "unavailable"
                ),
                "structured_mechanics",
            ),
        "distributed_instance_profile_present":
            _any_true_signal(
                mode_profiles,
                (
                    "distributed_instance_"
                    "profile_present"
                ),
            ),
        "mechanical_application_continuity_present":
            _any_true_signal(
                mode_profiles,
                (
                    "mechanical_application_"
                    "continuity_present"
                ),
            ),
        "operational_friction_records_present":
            evidence(
                bool(friction_records),
                (
                    "derived"
                    if friction_records
                    else "unavailable"
                ),
                "shared_stats",
                "attack_modes",
                "display_description",
            ),
        "multi_target_mechanic_records_present":
            evidence(
                bool(
                    multi_target_records
                ),
                (
                    "derived"
                    if multi_target_records
                    else "unavailable"
                ),
                (
                    "attack_modes[]."
                    "damage_components"
                ),
                "display_description",
            ),
        "trigger_type":
            primary_signals[
                "trigger_type"
            ],
        "burst_count":
            primary_signals[
                "burst_count"
            ],
        "charge_time":
            primary_signals[
                "charge_time"
            ],
        "pellet_count":
            primary_signals[
                "pellet_count"
            ],
        "multishot":
            primary_signals[
                "multishot"
            ],
        "reload_time": evidence(
            _number(
                _shared(
                    normalized_weapon
                ).get("reload_time")
            ),
            (
                "structured"
                if _number(
                    _shared(
                        normalized_weapon
                    ).get("reload_time")
                ) is not None
                else "unavailable"
            ),
            "shared_stats.reload_time",
        ),
        "reload_delay": evidence(
            None,
            "unavailable",
            reason=(
                "Field is not preserved by "
                "the normalized schema."
            ),
        ),
        "reload_rate": evidence(
            None,
            "unavailable",
            reason=(
                "Field is not preserved by "
                "the normalized schema."
            ),
        ),
        "reload_unit_time": evidence(
            None,
            "unavailable",
            reason=(
                "Field is not preserved by "
                "the normalized schema."
            ),
        ),
        "punch_through_depth":
            evidence(
                None,
                "unavailable",
                reason=(
                    "Description may prove "
                    "penetration, but not a "
                    "numeric depth."
                ),
            ),
        "sustained_cycle_profile_present":
            _any_true_signal(
                mode_profiles,
                (
                    "sustained_cycle_"
                    "profile_present"
                ),
            ),
        "ammo_reserve_model":
            evidence(
                (
                    "not_applicable"
                    if category
                    in MELEE_CATEGORIES
                    else "unlimited"
                    if _claims_of_type(
                        claims,
                        "unlimited_ammo",
                    )
                    else "regenerative"
                    if ammo_regeneration
                    else "undetermined"
                ),
                (
                    "derived"
                    if category
                    in MELEE_CATEGORIES
                    else (
                        "validated_description"
                        if _claims_of_type(
                            claims,
                            "unlimited_ammo",
                            "ammo_regeneration",
                        )
                        else "unavailable"
                    )
                ),
                "classification.category",
                "display_description",
            ),
        "ammo_reserve_capacity":
            evidence(
                None,
                "unavailable",
                reason=(
                    "Reserve capacity is not "
                    "preserved by the normalized "
                    "schema."
                ),
            ),
        "ammo_cost_per_consumption_event":
            evidence(
                None,
                "unavailable",
                reason=(
                    "The export does not provide "
                    "a universal ammo cost per "
                    "event."
                ),
            ),
        "consumption_event_frequency_present":
            evidence(
                (
                    True
                    if primary_signals[
                        "fire_rate"
                    ]["value"] is not None
                    else None
                ),
                (
                    "derived"
                    if primary_signals[
                        "fire_rate"
                    ]["value"] is not None
                    else "unavailable"
                ),
                *primary_signals[
                    "fire_rate"
                ].get(
                    "source_paths",
                    [],
                ),
                reason=(
                    "Event frequency is known, "
                    "but ammo cost per event may "
                    "not be."
                ),
            ),
        "ammo_regeneration_present":
            evidence(
                (
                    True
                    if ammo_regeneration
                    else None
                ),
                (
                    "validated_description"
                    if ammo_regeneration
                    else "unavailable"
                ),
                "display_description",
            ),
    }

    result = {
        "interpretation_version": (
            INTERPRETATION_VERSION
        ),
        "weapon_name": (
            normalized_weapon.get(
                "display_name"
            )
        ),
        "signals": signals,
        "flat_signals": (
            _flatten_signals(
                signals
            )
        ),
        "mode_profiles": mode_profiles,
        "records": {
            "description_claims": claims,
            "multi_target_mechanics": (
                multi_target_records
            ),
            "special_mechanics": (
                special_records
            ),
            "operational_friction": (
                friction_records
            ),
        },
    }

    logger.info(
        "Weapon signal derivation completed "
        "| weapon=%s | category=%s "
        "| modes=%s | claims=%s",
        normalized_weapon.get(
            "display_name"
        ),
        category,
        len(modes),
        len(claims),
    )

    return result


analyze_parsed_weapon = interpret_weapon
