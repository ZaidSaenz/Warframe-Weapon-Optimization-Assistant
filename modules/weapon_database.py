# Regenerate the normalized weapon database after updating
# data/raw/ExportWeapons.json or data/raw/dict.en.json:
# python -m modules.weapon_database normalize

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "raw" / "ExportWeapons.json"
DEFAULT_DICTIONARY = PROJECT_ROOT / "data" / "raw" / "dict.en.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "normalized" / "weapons.json"
DEFAULT_REPORT = (
    PROJECT_ROOT / "data" / "reports" / "weapon_normalization_report.json"
)
SCHEMA_VERSION = 1

PRODUCT_CATEGORY_MAP = {
    "LongGuns": "primary",
    "Pistols": "secondary",
    "Melee": "melee",
    "SentinelWeapons": "companion",
    "SpaceGuns": "archgun",
    "SpaceMelee": "archmelee",
    "OperatorAmps": "amp",
    "DrifterMelee": "drifter_melee",
    "SpecialItems": "special",
}

TRIGGER_MAP = {
    "AUTO": "automatic",
    "SEMI": "semi_automatic",
    "BURST": "burst",
    "HELD": "continuous",
    "CHARGE": "charge",
    "ACTIVE": "active",
    "DUPLEX": "duplex",
}

STATE_NAME_HINTS = {
    "Loadout_TriggerAuto": "automatic",
    "Loadout_TriggerSemiAuto": "semi_automatic",
    "Loadout_TriggerBurst": "burst",
    "Loadout_TriggerCharge": "charge",
    "Loadout_TriggerContinous": "continuous",
    "Loadout_TriggerContinuous": "continuous",
}

DAMAGE_TYPE_MAP = {
    "DT_IMPACT": "impact",
    "DT_PUNCTURE": "puncture",
    "DT_SLASH": "slash",
    "DT_FIRE": "heat",
    "DT_FREEZE": "cold",
    "DT_ELECTRICITY": "electricity",
    "DT_TOXIN": "toxin",
    "DT_POISON": "toxin",
    "DT_BLAST": "blast",
    "DT_EXPLOSION": "blast",
    "DT_RADIATION": "radiation",
    "DT_GAS": "gas",
    "DT_MAGNETIC": "magnetic",
    "DT_VIRAL": "viral",
    "DT_CORROSIVE": "corrosive",
    "DT_RADIANT": "void",
    "DT_SENTIENT": "tau",
    "DT_TRUE": "true",
    "DT_FINISHER": "finisher",
}

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

KNOWN_BEHAVIOUR_FIELDS = {
    "stateName",
    "fireIterations",
    "impact",
    "projectile",
    "chargedProjectile",
    "burst",
}

KNOWN_PROJECTILE_FIELDS = {
    "attack",
    "explosiveAttack",
}


EXCLUDED_PATH_FRAGMENTS = {
    "/CreaturePetParts/",
    "/MoaPetParts/",
    "/ZanukaPetParts/",
    "/HoverboardParts/",
    "/OperatorAmplifiers/Set1/Barrel/",
    "/OperatorAmplifiers/Set1/Chassis/",
    "/OperatorAmplifiers/Set1/Grip/",
    "/OperatorAmplifiers/Set2/Barrel/",
    "/OperatorAmplifiers/Set2/Chassis/",
    "/OperatorAmplifiers/Set2/Grip/",
    "/ModularMelee01/Balance/",
    "/ModularMelee01/Handle/",
    "/ModularMelee01/Tip/",
    "/ModularMelee02/Handle/",
    "/ModularMelee02/Tip/",
    "/ModularMeleeInfested/Handles/",
    "/ModularMeleeInfested/Tips/",
    "/SUModularPrimarySet1/Handles/",
    "/SUModularSecondarySet1/Barrel/",
    "/SUModularSecondarySet1/Clip/",
    "/SUModularSecondarySet1/Handle/",
    "/InfKitGun/Barrels/",
    "/InfKitGun/Clips/",
    "/InfKitGun/Handles/",
}

EXCLUDED_PATH_PREFIXES = {
    "/Lotus/Types/Items/Deimos/",
}

WEAPON_STAT_FIELDS = {
    "damagePerShot",
    "totalDamage",
    "criticalChance",
    "criticalMultiplier",
    "procChance",
    "fireRate",
    "behaviours",
    "magazineSize",
    "heavyAttackDamage",
    "range",
}


class WeaponDatabaseError(RuntimeError):
    """Raised when weapon data cannot be loaded or normalized."""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise WeaponDatabaseError(f"Could not read JSON file: {path}") from error
    except json.JSONDecodeError as error:
        raise WeaponDatabaseError(f"Invalid JSON file: {path}") from error


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_localization_dictionary(
    path: Path = DEFAULT_DICTIONARY,
) -> dict[str, str]:
    data = _read_json(path)

    if not isinstance(data, Mapping):
        raise WeaponDatabaseError(
            "The localization dictionary root must be a JSON object."
        )

    translations: dict[str, str] = {}

    for key, value in data.items():
        localized = _clean_text(value)

        if localized is not None:
            translations[str(key)] = localized

    if not translations:
        raise WeaponDatabaseError(
            "The localization dictionary contains no usable entries."
        )

    return translations


def _localized_text(
    key: str | None,
    translations: Mapping[str, str],
) -> str | None:
    if key is None:
        return None

    return _clean_text(
        translations.get(key)
    )


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _clean_number(value: Any, *, digits: int = 6) -> int | float | None:
    number = _finite_number(value)
    if number is None:
        return None
    rounded = round(number, digits)
    return int(rounded) if rounded.is_integer() else rounded


def _percent(value: Any) -> int | float | None:
    number = _finite_number(value)
    return None if number is None else _clean_number(number * 100)


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_enum(value: Any) -> str | None:
    text = _clean_text(value)
    return text.lower() if text else None


def _normalize_trigger(value: Any) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    return TRIGGER_MAP.get(text.upper(), text.lower())


def _trigger_from_state_name(state_name: Any) -> str | None:
    text = _clean_text(state_name)
    if text is None:
        return None
    for fragment, normalized in STATE_NAME_HINTS.items():
        if fragment in text:
            return normalized
    return None


def _normalize_damage_mapping(
    value: Any,
    *,
    unknown_damage_types: Counter[str],
) -> tuple[dict[str, int | float], int | float | None]:
    if not isinstance(value, Mapping):
        return {}, None

    damage: dict[str, int | float] = {}
    status_chance_percent: int | float | None = None

    for raw_key, raw_value in value.items():
        if raw_key == "procChance":
            status_chance_percent = _percent(raw_value)
            continue
        if not str(raw_key).startswith("DT_"):
            continue

        normalized_key = DAMAGE_TYPE_MAP.get(str(raw_key))
        if normalized_key is None:
            normalized_key = str(raw_key).lower()
            unknown_damage_types[str(raw_key)] += 1

        number = _clean_number(raw_value)
        if number not in (None, 0):
            damage[normalized_key] = number

    return damage, status_chance_percent


def _normalize_root_damage(
    value: Any,
    *,
    unknown_root_damage_indexes: Counter[int],
) -> dict[str, int | float]:
    if not isinstance(value, list):
        return {}

    damage: dict[str, int | float] = {}

    for index, raw_value in enumerate(value):
        number = _clean_number(raw_value)
        if number in (None, 0):
            continue

        normalized_key = ROOT_DAMAGE_INDEX_MAP.get(index)
        if normalized_key is None:
            normalized_key = f"unknown_index_{index}"
            unknown_root_damage_indexes[index] += 1

        damage[normalized_key] = number

    return damage


def _component(
    component_type: str,
    value: Any,
    *,
    unknown_damage_types: Counter[str],
) -> dict[str, Any] | None:
    damage, status_chance_percent = _normalize_damage_mapping(
        value,
        unknown_damage_types=unknown_damage_types,
    )
    if not damage and status_chance_percent is None:
        return None

    component: dict[str, Any] = {
        "component_type": component_type,
        "damage": damage,
    }
    if status_chance_percent is not None:
        component["status_chance_percent"] = status_chance_percent
    return component


def _projectile_components(
    projectile: Any,
    *,
    prefix: str,
    unknown_damage_types: Counter[str],
    unknown_projectile_fields: Counter[str],
) -> list[dict[str, Any]]:
    if not isinstance(projectile, Mapping):
        return []

    for raw_key in projectile:
        if raw_key not in KNOWN_PROJECTILE_FIELDS:
            unknown_projectile_fields[str(raw_key)] += 1

    components: list[dict[str, Any]] = []

    direct = _component(
        f"{prefix}_direct",
        projectile.get("attack"),
        unknown_damage_types=unknown_damage_types,
    )
    if direct is not None:
        components.append(direct)

    radial = _component(
        f"{prefix}_radial",
        projectile.get("explosiveAttack"),
        unknown_damage_types=unknown_damage_types,
    )
    if radial is not None:
        components.append(radial)

    return components


def _normalize_burst(value: Any) -> dict[str, Any] | None:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            number = _clean_number(item)
            normalized[str(key)] = number if number is not None else deepcopy(item)
        return normalized or None
    number = _clean_number(value)
    return {"value": number if number is not None else deepcopy(value)}


def _normalize_behaviour(
    behaviour: Mapping[str, Any],
    *,
    index: int,
    weapon_trigger: str | None,
    root_critical_chance_percent: int | float | None,
    root_critical_multiplier: int | float | None,
    root_status_chance_percent: int | float | None,
    root_fire_rate: int | float | None,
    unknown_damage_types: Counter[str],
    unknown_behaviour_fields: Counter[str],
    unknown_projectile_fields: Counter[str],
) -> dict[str, Any]:
    for raw_key in behaviour:
        if raw_key not in KNOWN_BEHAVIOUR_FIELDS:
            unknown_behaviour_fields[str(raw_key)] += 1

    state_name = _clean_text(behaviour.get("stateName"))
    trigger = _trigger_from_state_name(state_name) or weapon_trigger

    components: list[dict[str, Any]] = []

    impact = _component(
        "direct",
        behaviour.get("impact"),
        unknown_damage_types=unknown_damage_types,
    )
    if impact is not None:
        components.append(impact)

    components.extend(
        _projectile_components(
            behaviour.get("projectile"),
            prefix="projectile",
            unknown_damage_types=unknown_damage_types,
            unknown_projectile_fields=unknown_projectile_fields,
        )
    )
    components.extend(
        _projectile_components(
            behaviour.get("chargedProjectile"),
            prefix="charged_projectile",
            unknown_damage_types=unknown_damage_types,
            unknown_projectile_fields=unknown_projectile_fields,
        )
    )

    mode: dict[str, Any] = {
        "mode_id": f"mode_{index + 1}",
        "state_name": state_name,
        "trigger_type": trigger,
        "fire_iterations": _clean_number(behaviour.get("fireIterations")) or 1,
        "damage_components": components,
    }

    optional_values = {
        "fire_rate": root_fire_rate,
        "critical_chance_percent": root_critical_chance_percent,
        "critical_multiplier": root_critical_multiplier,
        "status_chance_percent": root_status_chance_percent,
    }
    for key, value in optional_values.items():
        if value is not None:
            mode[key] = value

    burst = _normalize_burst(behaviour.get("burst"))
    if burst is not None:
        mode["burst"] = burst

    if behaviour.get("chargedProjectile") is not None:
        mode["charge_evidence"] = True

    return mode


def _canonical_mode(mode: Mapping[str, Any]) -> str:
    comparable = {key: value for key, value in mode.items() if key != "mode_id"}
    return json.dumps(
        comparable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _deduplicate_modes(
    modes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    removed = 0

    for mode in modes:
        signature = _canonical_mode(mode)
        if signature in seen:
            removed += 1
            continue
        seen.add(signature)
        result.append(mode)

    for index, mode in enumerate(result, start=1):
        mode["mode_id"] = f"mode_{index}"

    return result, removed


def _fallback_mode(
    weapon: Mapping[str, Any],
    *,
    root_damage: dict[str, int | float],
    trigger: str | None,
    critical_chance_percent: int | float | None,
    critical_multiplier: int | float | None,
    status_chance_percent: int | float | None,
    fire_rate: int | float | None,
) -> dict[str, Any]:
    component: dict[str, Any] = {
        "component_type": "root_fallback",
        "damage": root_damage,
    }
    if status_chance_percent is not None:
        component["status_chance_percent"] = status_chance_percent

    mode: dict[str, Any] = {
        "mode_id": "mode_1",
        "state_name": None,
        "trigger_type": trigger,
        "fire_iterations": _clean_number(weapon.get("multishot")) or 1,
        "damage_components": [component],
    }

    optional_values = {
        "fire_rate": fire_rate,
        "critical_chance_percent": critical_chance_percent,
        "critical_multiplier": critical_multiplier,
        "status_chance_percent": status_chance_percent,
    }
    for key, value in optional_values.items():
        if value is not None:
            mode[key] = value

    return mode


def _weapon_class(weapon: Mapping[str, Any]) -> str | None:
    for key in ("holsterCategory", "gunType"):
        value = _normalize_enum(weapon.get(key))
        if value:
            return value

    tags = weapon.get("compatibilityTags")
    if isinstance(tags, list):
        for tag in tags:
            text = _normalize_enum(tag)
            if text and text.endswith("_stance"):
                return text.removesuffix("_stance")

    return None


def _has_weapon_statistics(
    weapon: Mapping[str, Any],
) -> bool:
    present = sum(
        field in weapon
        for field in WEAPON_STAT_FIELDS
    )
    return present >= 4


def _has_usable_weapon_data(
    weapon: Mapping[str, Any],
) -> bool:
    total_damage = _clean_number(
        weapon.get("totalDamage")
    )

    damage_per_shot = weapon.get(
        "damagePerShot"
    )

    has_root_damage = (
        isinstance(damage_per_shot, list)
        and any(
            (_clean_number(value) or 0) > 0
            for value in damage_per_shot
        )
    )

    behaviours = weapon.get("behaviours")

    has_behaviours = (
        isinstance(behaviours, list)
        and any(
            isinstance(behaviour, Mapping)
            and bool(behaviour)
            for behaviour in behaviours
        )
    )

    has_melee_damage = any(
        (_clean_number(weapon.get(field)) or 0) > 0
        for field in (
            "heavyAttackDamage",
            "slamAttack",
            "slamRadialDamage",
            "slideAttack",
            "heavySlamAttack",
            "heavySlamRadialDamage",
        )
    )

    return bool(
        (total_damage or 0) > 0
        or has_root_damage
        or has_behaviours
        or has_melee_damage
    )


def is_selectable_weapon(
    weapon_id: str,
    weapon: Mapping[str, Any],
) -> tuple[bool, str | None]:
    for prefix in EXCLUDED_PATH_PREFIXES:
        if weapon_id.startswith(prefix):
            return False, "reward_or_non_weapon_item"

    for fragment in EXCLUDED_PATH_FRAGMENTS:
        if fragment in weapon_id:
            return False, "modular_or_equipment_component"

    if not _has_weapon_statistics(weapon):
        return False, "insufficient_weapon_statistics"

    if not _has_usable_weapon_data(weapon):
        return False, "no_usable_weapon_data"

    return True, None


def normalize_weapon(
    weapon_id: str,
    weapon: Mapping[str, Any],
    *,
    translations: Mapping[str, str],
    report: dict[str, Any],
) -> dict[str, Any]:
    unknown_damage_types: Counter[str] = report["_unknown_damage_types"]
    unknown_root_damage_indexes: Counter[int] = report[
        "_unknown_root_damage_indexes"
    ]
    unknown_behaviour_fields: Counter[str] = report[
        "_unknown_behaviour_fields"
    ]
    unknown_projectile_fields: Counter[str] = report[
        "_unknown_projectile_fields"
    ]

    warnings: list[str] = []

    name_key = _clean_text(
        weapon.get("name")
    )
    display_name = _localized_text(
        name_key,
        translations,
    )

    description_key = _clean_text(
        weapon.get("description")
    )
    display_description = _localized_text(
        description_key,
        translations,
    )

    if display_name is None:
        report["missing_display_names"] += 1
    else:
        report["resolved_display_names"] += 1

    source_category = _clean_text(weapon.get("productCategory"))
    category = PRODUCT_CATEGORY_MAP.get(source_category or "", "unknown")

    if category == "unknown":
        warnings.append(f"Unknown product category: {source_category}")

    critical_chance_percent = _percent(weapon.get("criticalChance"))
    critical_multiplier = _clean_number(weapon.get("criticalMultiplier"))
    status_chance_percent = _percent(weapon.get("procChance"))
    fire_rate = _clean_number(weapon.get("fireRate"))
    trigger = _normalize_trigger(weapon.get("trigger"))

    root_damage = _normalize_root_damage(
        weapon.get("damagePerShot"),
        unknown_root_damage_indexes=unknown_root_damage_indexes,
    )

    shared_stats: dict[str, Any] = {}
    shared_field_map = {
        "magazineSize": "magazine_size",
        "reloadTime": "reload_time",
        "accuracy": "accuracy",
        "multishot": "multishot",
        "range": "range",
        "followThrough": "follow_through",
        "blockingAngle": "blocking_angle",
        "comboDuration": "combo_duration",
        "windUp": "heavy_attack_wind_up",
        "slamAttack": "slam_attack_damage",
        "slamRadialDamage": "slam_radial_damage",
        "slamRadius": "slam_radius",
        "slideAttack": "slide_attack_damage",
        "heavyAttackDamage": "heavy_attack_damage",
        "heavySlamAttack": "heavy_slam_attack_damage",
        "heavySlamRadialDamage": "heavy_slam_radial_damage",
        "heavySlamRadius": "heavy_slam_radius",
    }

    for source_key, target_key in shared_field_map.items():
        number = _clean_number(weapon.get(source_key))
        if number is not None:
            shared_stats[target_key] = number

    noise = _normalize_enum(weapon.get("noise"))
    if noise is not None:
        shared_stats["noise"] = noise
    if trigger is not None:
        shared_stats["trigger_type"] = trigger

    compatibility_tags = weapon.get("compatibilityTags")
    if isinstance(compatibility_tags, list):
        cleaned_tags = [
            str(tag).strip().lower()
            for tag in compatibility_tags
            if str(tag).strip()
        ]
        if cleaned_tags:
            shared_stats["compatibility_tags"] = cleaned_tags

    raw_behaviours = weapon.get("behaviours")
    modes: list[dict[str, Any]] = []

    if isinstance(raw_behaviours, list):
        for index, raw_behaviour in enumerate(raw_behaviours):
            if not isinstance(raw_behaviour, Mapping):
                warnings.append(f"Behaviour {index} is not a JSON object.")
                continue

            mode = _normalize_behaviour(
                raw_behaviour,
                index=index,
                weapon_trigger=trigger,
                root_critical_chance_percent=critical_chance_percent,
                root_critical_multiplier=critical_multiplier,
                root_status_chance_percent=status_chance_percent,
                root_fire_rate=fire_rate,
                unknown_damage_types=unknown_damage_types,
                unknown_behaviour_fields=unknown_behaviour_fields,
                unknown_projectile_fields=unknown_projectile_fields,
            )

            if not mode["damage_components"]:
                warnings.append(
                    f"Behaviour {index} has no recognized damage components."
                )

            modes.append(mode)

    modes, duplicate_count = _deduplicate_modes(modes)
    report["deduplicated_modes"] += duplicate_count

    usable_modes = [mode for mode in modes if mode.get("damage_components")]
    used_fallback = not usable_modes

    if used_fallback:
        usable_modes = [
            _fallback_mode(
                weapon,
                root_damage=root_damage,
                trigger=trigger,
                critical_chance_percent=critical_chance_percent,
                critical_multiplier=critical_multiplier,
                status_chance_percent=status_chance_percent,
                fire_rate=fire_rate,
            )
        ]
        warnings.append(
            "No usable behaviours were found; root statistics were used as fallback."
        )

    normalization_status = "fallback" if used_fallback else "complete"
    if warnings and not used_fallback:
        normalization_status = "partial"

    return {
        "schema_version": SCHEMA_VERSION,
        "weapon_id": weapon_id,
        "name_key": name_key,
        "display_name": display_name,
        "description_key": description_key,
        "display_description": display_description,
        "classification": {
            "category": category,
            "source_category": source_category,
            "weapon_class": _weapon_class(weapon),
            "variant_type": _normalize_enum(weapon.get("variantType")),
            "mastery_rank": _clean_number(weapon.get("masteryReq")),
            "slot": _clean_number(weapon.get("slot")),
        },
        "shared_stats": shared_stats,
        "root_stats": {
            "total_damage": _clean_number(weapon.get("totalDamage")),
            "damage": root_damage,
            "critical_chance_percent": critical_chance_percent,
            "critical_multiplier": critical_multiplier,
            "status_chance_percent": status_chance_percent,
            "fire_rate": fire_rate,
        },
        "attack_modes": usable_modes,
        "source": {
            "parent_name": _clean_text(weapon.get("parentName")),
            "icon": _clean_text(weapon.get("icon")),
            "codex_secret": bool(weapon.get("codexSecret", False)),
            "tradable": bool(weapon.get("tradable", False)),
            "introduced_at": _clean_number(weapon.get("introducedAt")),
            "normalization_status": normalization_status,
            "warnings": warnings,
        },
    }


def load_raw_dataset(path: Path = DEFAULT_SOURCE) -> dict[str, dict[str, Any]]:
    data = _read_json(path)
    if not isinstance(data, Mapping):
        raise WeaponDatabaseError("The weapon export root must be a JSON object.")

    weapons = {
        str(weapon_id): dict(weapon)
        for weapon_id, weapon in data.items()
        if isinstance(weapon, Mapping)
    }
    if not weapons:
        raise WeaponDatabaseError("No weapon objects were found in the dataset.")
    return weapons


def normalize_dataset(
    *,
    source_path: Path = DEFAULT_SOURCE,
    dictionary_path: Path = DEFAULT_DICTIONARY,
    output_path: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_weapons = load_raw_dataset(source_path)
    translations = load_localization_dictionary(
        dictionary_path
    )

    internal_report: dict[str, Any] = {
        "weapon_count": len(raw_weapons),
        "eligible_weapon_count": 0,
        "excluded_entry_count": 0,
        "excluded_by_reason": Counter(),
        "excluded_examples": [],
        "complete": 0,
        "partial": 0,
        "fallback": 0,
        "failed": 0,
        "deduplicated_modes": 0,
        "resolved_display_names": 0,
        "missing_display_names": 0,
        "failures": [],
        "_unknown_damage_types": Counter(),
        "_unknown_root_damage_indexes": Counter(),
        "_unknown_behaviour_fields": Counter(),
        "_unknown_projectile_fields": Counter(),
    }

    normalized_weapons: dict[str, Any] = {}

    for weapon_id, weapon in raw_weapons.items():
        selectable, exclusion_reason = is_selectable_weapon(
            weapon_id,
            weapon,
        )

        if not selectable:
            internal_report["excluded_entry_count"] += 1
            internal_report["excluded_by_reason"][
                exclusion_reason or "unknown"
            ] += 1

            if len(internal_report["excluded_examples"]) < 50:
                internal_report["excluded_examples"].append(
                    {
                        "weapon_id": weapon_id,
                        "name_key": _clean_text(
                            weapon.get("name")
                        ),
                        "reason": exclusion_reason,
                    }
                )
            continue

        internal_report["eligible_weapon_count"] += 1

        try:
            normalized = normalize_weapon(
                weapon_id,
                weapon,
                translations=translations,
                report=internal_report,
            )
        except Exception as error:
            internal_report["failed"] += 1
            internal_report["failures"].append(
                {"weapon_id": weapon_id, "error": str(error)}
            )
            continue

        status = normalized["source"]["normalization_status"]
        internal_report[status] += 1
        normalized_weapons[weapon_id] = normalized

    generated_at = datetime.now(timezone.utc).isoformat()

    database = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "source_file": str(source_path),
        "dictionary_file": str(dictionary_path),
        "weapon_count": len(normalized_weapons),
        "weapons": normalized_weapons,
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "source_file": str(source_path),
        "dictionary_file": str(dictionary_path),
        "output_file": str(output_path),
        "weapon_count": internal_report["weapon_count"],
        "eligible_weapon_count": internal_report[
            "eligible_weapon_count"
        ],
        "excluded_entry_count": internal_report[
            "excluded_entry_count"
        ],
        "excluded_by_reason": dict(
            internal_report["excluded_by_reason"].most_common()
        ),
        "excluded_examples": internal_report[
            "excluded_examples"
        ],
        "normalized_weapon_count": len(normalized_weapons),
        "complete": internal_report["complete"],
        "partial": internal_report["partial"],
        "fallback": internal_report["fallback"],
        "failed": internal_report["failed"],
        "deduplicated_modes": internal_report["deduplicated_modes"],
        "resolved_display_names": internal_report[
            "resolved_display_names"
        ],
        "missing_display_names": internal_report[
            "missing_display_names"
        ],
        "unknown_damage_types": dict(
            internal_report["_unknown_damage_types"].most_common()
        ),
        "unknown_root_damage_indexes": {
            str(key): count
            for key, count in internal_report[
                "_unknown_root_damage_indexes"
            ].most_common()
        },
        "unknown_behaviour_fields": dict(
            internal_report["_unknown_behaviour_fields"].most_common()
        ),
        "unknown_projectile_fields": dict(
            internal_report["_unknown_projectile_fields"].most_common()
        ),
        "failures": internal_report["failures"],
    }

    _write_json(output_path, database)
    _write_json(report_path, report)
    return database, report


def load_normalized_database(path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    data = _read_json(path)
    if not isinstance(data, Mapping):
        raise WeaponDatabaseError(
            "The normalized database root must be an object."
        )
    if not isinstance(data.get("weapons"), Mapping):
        raise WeaponDatabaseError(
            "The normalized database does not contain a weapons object."
        )
    return dict(data)


def find_weapons(
    query: str,
    *,
    database_path: Path = DEFAULT_OUTPUT,
) -> list[dict[str, Any]]:
    database = load_normalized_database(database_path)
    weapons = database["weapons"]
    needle = query.casefold().strip()
    matches: list[dict[str, Any]] = []

    for weapon_id, weapon in weapons.items():
        if not isinstance(weapon, Mapping):
            continue

        classification = weapon.get("classification")
        source_category = (
            classification.get("source_category")
            if isinstance(classification, Mapping)
            else ""
        )

        searchable = " ".join(
            str(value or "")
            for value in (
                weapon_id,
                weapon.get("name_key"),
                weapon.get("display_name"),
                weapon.get("description_key"),
                source_category,
            )
        ).casefold()

        if needle in searchable:
            matches.append(dict(weapon))

    return matches


def list_weapons(
    *,
    database_path: Path = DEFAULT_OUTPUT,
    category: str | None = None,
) -> list[dict[str, Any]]:
    database = load_normalized_database(database_path)
    results: list[dict[str, Any]] = []

    for weapon in database["weapons"].values():
        if not isinstance(weapon, Mapping):
            continue
        classification = weapon.get("classification")
        if not isinstance(classification, Mapping):
            continue
        if category is not None and classification.get("category") != category:
            continue

        results.append(
            {
                "weapon_id": weapon.get("weapon_id"),
                "display_name": weapon.get("display_name"),
                "name_key": weapon.get("name_key"),
                "category": classification.get("category"),
                "weapon_class": classification.get("weapon_class"),
                "mastery_rank": classification.get("mastery_rank"),
            }
        )

    results.sort(
        key=lambda item: str(
            item.get("display_name")
            or item.get("name_key")
            or item.get("weapon_id")
            or ""
        ).casefold()
    )

    return results


def _print_summary(report: Mapping[str, Any]) -> None:
    visible = {
        "weapon_count": report.get("weapon_count"),
        "eligible_weapon_count": report.get(
            "eligible_weapon_count"
        ),
        "excluded_entry_count": report.get(
            "excluded_entry_count"
        ),
        "normalized_weapon_count": report.get("normalized_weapon_count"),
        "complete": report.get("complete"),
        "partial": report.get("partial"),
        "fallback": report.get("fallback"),
        "failed": report.get("failed"),
        "deduplicated_modes": report.get("deduplicated_modes"),
        "resolved_display_names": report.get(
            "resolved_display_names"
        ),
        "missing_display_names": report.get(
            "missing_display_names"
        ),
        "unknown_damage_type_count": len(
            report.get("unknown_damage_types", {})
        ),
        "unknown_behaviour_field_count": len(
            report.get("unknown_behaviour_fields", {})
        ),
    }
    print(json.dumps(visible, ensure_ascii=False, indent=2))


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize and inspect the local Warframe weapon database."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize_parser = subparsers.add_parser(
        "normalize",
        help="Generate the normalized weapon database.",
    )
    normalize_parser.add_argument("--input", type=Path, default=DEFAULT_SOURCE)
    normalize_parser.add_argument(
        "--dictionary",
        type=Path,
        default=DEFAULT_DICTIONARY,
    )
    normalize_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    normalize_parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect matching normalized weapon entries.",
    )
    inspect_parser.add_argument(
        "query",
        help="Text contained in the weapon id or localization keys.",
    )
    inspect_parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    list_parser = subparsers.add_parser("list", help="List normalized weapons.")
    list_parser.add_argument("--database", type=Path, default=DEFAULT_OUTPUT)
    list_parser.add_argument(
        "--category",
        choices=sorted(set(PRODUCT_CATEGORY_MAP.values()) | {"unknown"}),
    )
    list_parser.add_argument("--limit", type=int, default=50)

    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        if args.command == "normalize":
            _, report = normalize_dataset(
                source_path=args.input,
                dictionary_path=args.dictionary,
                output_path=args.output,
                report_path=args.report,
            )
            _print_summary(report)
            print()
            print(f"Normalized database saved to: {args.output}")
            print(f"Normalization report saved to: {args.report}")
            return 0

        if args.command == "inspect":
            matches = find_weapons(args.query, database_path=args.database)
            print(json.dumps(matches, ensure_ascii=False, indent=2))
            return 0

        if args.command == "list":
            weapons = list_weapons(
                database_path=args.database,
                category=args.category,
            )
            print(
                json.dumps(
                    weapons[: max(args.limit, 0)],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

    except WeaponDatabaseError as error:
        print(f"Weapon database error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())