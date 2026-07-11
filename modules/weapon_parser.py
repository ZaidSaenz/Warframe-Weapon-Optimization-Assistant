# modules/weapon_parser.py

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


DAMAGE_TYPES = (
    "impact",
    "puncture",
    "slash",
    "heat",
    "cold",
    "electricity",
    "toxin",
    "blast",
    "corrosive",
    "gas",
    "magnetic",
    "radiation",
    "viral",
    "void",
)

PHYSICAL_DAMAGE_TYPES = {"impact", "puncture", "slash"}

FIRING_MODES = {
    "automatic",
    "semi_automatic",
    "burst",
    "charge",
    "continuous",
}

DAMAGE_DELIVERY_TYPES = {
    "hitscan",
    "projectile",
    "beam",
}

CATEGORY_ALIASES = {
    "primary": "primary",
    "primaria": "primary",
    "secondary": "secondary",
    "secundaria": "secondary",
    "melee": "melee",
}

DATA_SOURCES = {"manual", "database", "scraping"}


class WeaponValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(
    value: Any,
    field: str,
    errors: list[str],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    required: bool = True,
) -> float | None:
    text = _text(value)

    if not text:
        if required:
            errors.append(f"Falta el campo obligatorio: {field}.")
        return None

    if isinstance(value, bool):
        errors.append(f"{field} debe ser numérico.")
        return None

    try:
        number = float(text.replace(",", "."))
    except (TypeError, ValueError):
        errors.append(f"{field} debe ser numérico.")
        return None

    if not math.isfinite(number):
        errors.append(f"{field} debe ser un número finito.")
        return None

    if minimum is not None and number < minimum:
        errors.append(f"{field} debe ser mayor o igual que {minimum}.")
        return None

    if maximum is not None and number > maximum:
        errors.append(f"{field} debe ser menor o igual que {maximum}.")
        return None

    return number


def _integer(
    value: Any,
    field: str,
    errors: list[str],
    *,
    minimum: int = 0,
    required: bool = True,
) -> int | None:
    number = _number(
        value,
        field,
        errors,
        minimum=float(minimum),
        required=required,
    )

    if number is None:
        return None

    if not number.is_integer():
        errors.append(f"{field} debe ser un número entero.")
        return None

    return int(number)


def _optional_number(
    raw_data: Mapping[str, Any],
    field: str,
    errors: list[str],
    *,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float | None:
    if not _text(raw_data.get(field)):
        return None

    return _number(
        raw_data.get(field),
        field,
        errors,
        minimum=minimum,
        maximum=maximum,
        required=False,
    )


def _boolean(
    value: Any,
    field: str,
    errors: list[str],
    *,
    default: bool = False,
) -> bool:
    if value is None or _text(value) == "":
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in {0, 1}:
        return bool(value)

    normalized = _text(value).lower()

    if normalized in {"true", "1", "yes", "si", "sí"}:
        return True

    if normalized in {"false", "0", "no"}:
        return False

    errors.append(f"{field} debe ser verdadero o falso.")
    return default


def _normalize_category(value: Any, errors: list[str]) -> str:
    category = CATEGORY_ALIASES.get(_text(value).lower(), "")

    if not category:
        errors.append("weapon_category debe ser primary, secondary o melee.")

    return category


def _normalize_choice(
    value: Any,
    field: str,
    allowed_values: set[str],
    errors: list[str],
) -> str:
    normalized = _text(value).lower()

    if not normalized:
        errors.append(f"Falta el campo obligatorio: {field}.")
        return ""

    if normalized not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        errors.append(
            f"{field} no es válido. Valores permitidos: {allowed}."
        )

    return normalized


def _parse_base_damage(
    raw_data: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    source = raw_data.get("base_damage")

    if not isinstance(source, Mapping):
        errors.append("base_damage debe ser un diccionario de tipos de daño.")
        source = {}

    unknown_types = sorted(
        str(damage_type)
        for damage_type in source
        if damage_type not in DAMAGE_TYPES
    )

    if unknown_types:
        errors.append(
            "base_damage contiene tipos no permitidos: "
            + ", ".join(unknown_types)
            + "."
        )

    components: dict[str, float] = {}

    for damage_type in DAMAGE_TYPES:
        if damage_type not in source:
            continue

        value = _number(
            source.get(damage_type),
            f"base_damage.{damage_type}",
            errors,
            minimum=0.0001,
        )

        if value is not None and value > 0:
            components[damage_type] = value

    total_base_damage = round(sum(components.values()), 4)

    if total_base_damage <= 0:
        errors.append(
            "base_damage debe contener al menos un tipo de daño mayor que cero."
        )

    distribution_percent = {
        damage_type: round(value / total_base_damage * 100.0, 4)
        for damage_type, value in components.items()
    } if total_base_damage > 0 else {}

    dominant_type = (
        max(components, key=components.get)
        if components
        else None
    )

    physical_damage = sum(
        components.get(damage_type, 0.0)
        for damage_type in PHYSICAL_DAMAGE_TYPES
    )
    physical_percent = (
        physical_damage / total_base_damage * 100.0
        if total_base_damage > 0
        else 0.0
    )

    return {
        "base_total": total_base_damage,
        "components": components,
        "distribution_percent": distribution_percent,
        "dominant_type": dominant_type,
        "physical_percent": round(physical_percent, 4),
        "elemental_percent": round(100.0 - physical_percent, 4)
        if total_base_damage > 0
        else 0.0,
    }


def _parse_ranged_classification(
    raw_data: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    firing_mode = _normalize_choice(
        raw_data.get("firing_mode"),
        "firing_mode",
        FIRING_MODES,
        errors,
    )
    damage_delivery = _normalize_choice(
        raw_data.get("damage_delivery"),
        "damage_delivery",
        DAMAGE_DELIVERY_TYPES,
        errors,
    )

    return {
        "firing_mode": firing_mode,
        "damage_delivery": damage_delivery,
        "has_multiple_pellets": _boolean(
            raw_data.get("has_multiple_pellets"),
            "has_multiple_pellets",
            errors,
        ),
        "is_explosive": _boolean(
            raw_data.get("is_explosive"),
            "is_explosive",
            errors,
        ),
    }


def _parse_conditional_stats(
    raw_data: Mapping[str, Any],
    classification: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    stats: dict[str, Any] = {}

    firing_mode = classification.get("firing_mode")
    damage_delivery = classification.get("damage_delivery")
    has_multiple_pellets = bool(
        classification.get("has_multiple_pellets")
    )
    is_explosive = bool(classification.get("is_explosive"))

    if firing_mode == "burst":
        stats["shots_per_burst"] = _integer(
            raw_data.get("shots_per_burst"),
            "shots_per_burst",
            errors,
            minimum=1,
        )

    if firing_mode == "charge":
        stats["charge_time"] = _number(
            raw_data.get("charge_time"),
            "charge_time",
            errors,
            minimum=0.0001,
        )

    if has_multiple_pellets:
        stats["pellet_count"] = _integer(
            raw_data.get("pellet_count"),
            "pellet_count",
            errors,
            minimum=1,
        )

    if damage_delivery == "projectile":
        stats["projectile_speed"] = _optional_number(
            raw_data,
            "projectile_speed",
            errors,
            minimum=0.0001,
        )

    if damage_delivery == "beam":
        stats["beam_range"] = _optional_number(
            raw_data,
            "beam_range",
            errors,
            minimum=0.0001,
        )

    if is_explosive:
        stats["explosion_radius"] = _optional_number(
            raw_data,
            "explosion_radius",
            errors,
            minimum=0.0001,
        )

    return {
        key: value
        for key, value in stats.items()
        if value is not None
    }


def _parse_ranged_stats(
    raw_data: Mapping[str, Any],
    critical_chance: float | None,
    status_chance: float | None,
    total_base_damage: float,
    critical_multiplier: float | None,
    errors: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    fire_rate = _number(
        raw_data.get("fire_rate"),
        "fire_rate",
        errors,
        minimum=0.0001,
    )
    multishot = _number(
        raw_data.get("multishot"),
        "multishot",
        errors,
        minimum=0.0001,
    )
    magazine_size = _integer(
        raw_data.get("magazine_size"),
        "magazine_size",
        errors,
        minimum=1,
    )
    reload_time = _number(
        raw_data.get("reload_time"),
        "reload_time",
        errors,
        minimum=0.0001,
    )

    stats = {
        "fire_rate": fire_rate,
        "multishot": multishot,
        "magazine_size": magazine_size,
        "reload_time": reload_time,
    }

    derived: dict[str, Any] = {}

    if all(
        value is not None
        for value in (
            fire_rate,
            multishot,
            magazine_size,
            reload_time,
            critical_chance,
            status_chance,
            critical_multiplier,
        )
    ) and total_base_damage > 0:
        critical_factor = 1 + (critical_chance / 100.0) * (
            critical_multiplier - 1
        )
        magazine_duration = magazine_size / fire_rate
        cycle_duration = magazine_duration + reload_time
        sustained_trigger_rate = magazine_size / cycle_duration

        derived = {
            "critical_factor": round(critical_factor, 4),
            "projectiles_per_second": round(fire_rate * multishot, 4),
            "critical_events_per_second_estimate": round(
                fire_rate * multishot * critical_chance / 100.0,
                4,
            ),
            "status_events_per_second_estimate": round(
                fire_rate * multishot * status_chance / 100.0,
                4,
            ),
            "magazine_duration_seconds": round(magazine_duration, 4),
            "reload_downtime_percent": round(
                reload_time / cycle_duration * 100.0,
                4,
            ),
            "simple_burst_dps_estimate": round(
                total_base_damage
                * critical_factor
                * multishot
                * fire_rate,
                4,
            ),
            "simple_sustained_dps_estimate": round(
                total_base_damage
                * critical_factor
                * multishot
                * sustained_trigger_rate,
                4,
            ),
        }

    return stats, derived


def _parse_melee_stats(
    raw_data: Mapping[str, Any],
    critical_chance: float | None,
    status_chance: float | None,
    total_base_damage: float,
    critical_multiplier: float | None,
    errors: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    attack_speed = _number(
        raw_data.get("attack_speed"),
        "attack_speed",
        errors,
        minimum=0.0001,
    )
    range_value = _number(
        raw_data.get("range"),
        "range",
        errors,
        minimum=0.0001,
    )
    heavy_attack_damage = _optional_number(
        raw_data,
        "heavy_attack_damage",
        errors,
        minimum=0.0001,
    )
    heavy_attack_wind_up = _optional_number(
        raw_data,
        "heavy_attack_wind_up",
        errors,
        minimum=0.0001,
    )

    stats = {
        "attack_speed": attack_speed,
        "range": range_value,
    }

    if heavy_attack_damage is not None:
        stats["heavy_attack_damage"] = heavy_attack_damage

    if heavy_attack_wind_up is not None:
        stats["heavy_attack_wind_up"] = heavy_attack_wind_up

    derived: dict[str, Any] = {}

    if all(
        value is not None
        for value in (
            attack_speed,
            critical_chance,
            status_chance,
            critical_multiplier,
        )
    ) and total_base_damage > 0:
        critical_factor = 1 + (critical_chance / 100.0) * (
            critical_multiplier - 1
        )

        derived = {
            "critical_factor": round(critical_factor, 4),
            "critical_events_per_second_estimate": round(
                attack_speed * critical_chance / 100.0,
                4,
            ),
            "status_events_per_second_estimate": round(
                attack_speed * status_chance / 100.0,
                4,
            ),
            "simple_light_attack_dps_estimate": round(
                total_base_damage * critical_factor * attack_speed,
                4,
            ),
        }

    if heavy_attack_damage is not None and total_base_damage > 0:
        derived["heavy_to_base_damage_ratio"] = round(
            heavy_attack_damage / total_base_damage,
            4,
        )

    if (
        heavy_attack_damage is not None
        and heavy_attack_wind_up is not None
    ):
        derived["heavy_damage_per_wind_up_second"] = round(
            heavy_attack_damage / heavy_attack_wind_up,
            4,
        )

    return stats, derived


def parse_weapon_data(raw_data: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_data, Mapping):
        raise TypeError("raw_data debe ser un diccionario o Mapping.")

    errors: list[str] = []

    category = _normalize_category(
        raw_data.get("weapon_category"),
        errors,
    )

    source = _text(raw_data.get("data_source", "manual")).lower()

    if source not in DATA_SOURCES:
        errors.append("data_source debe ser manual, database o scraping.")

    critical_chance = _number(
        raw_data.get("critical_chance_percent"),
        "critical_chance_percent",
        errors,
        minimum=0.0,
    )
    critical_multiplier = _number(
        raw_data.get("critical_multiplier"),
        "critical_multiplier",
        errors,
        minimum=1.0,
    )
    status_chance = _number(
        raw_data.get("status_chance_percent"),
        "status_chance_percent",
        errors,
        minimum=0.0,
    )

    damage = _parse_base_damage(raw_data, errors)
    total_base_damage = damage["base_total"]

    ranged_classification = None
    ranged_stats = None
    melee_stats = None
    conditional_stats: dict[str, Any] = {}
    derived: dict[str, Any] = {}

    if category in {"primary", "secondary"}:
        ranged_classification = _parse_ranged_classification(
            raw_data,
            errors,
        )
        conditional_stats = _parse_conditional_stats(
            raw_data,
            ranged_classification,
            errors,
        )
        ranged_stats, derived = _parse_ranged_stats(
            raw_data,
            critical_chance,
            status_chance,
            total_base_damage,
            critical_multiplier,
            errors,
        )

    if category == "melee":
        melee_stats, derived = _parse_melee_stats(
            raw_data,
            critical_chance,
            status_chance,
            total_base_damage,
            critical_multiplier,
            errors,
        )

    if errors:
        raise WeaponValidationError(errors)

    return {
        "schema_version": 2,
        "data_source": source,
        "weapon_category": category,
        "ranged_classification": ranged_classification,
        "damage": damage,
        "core_stats": {
            "critical_chance_percent": critical_chance,
            "critical_multiplier": critical_multiplier,
            "status_chance_percent": status_chance,
        },
        "ranged_stats": ranged_stats,
        "melee_stats": melee_stats,
        "conditional_stats": conditional_stats,
        "derived": derived,
    }


parse = parse_weapon_data