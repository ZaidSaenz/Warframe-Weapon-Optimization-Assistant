"""Validación y normalización de datos de armas.

Este módulo solo responde una pregunta: ¿qué datos objetivos recibió el
programa? No intenta decidir si una estadística es buena, mala o adecuada para
una build. Las interpretaciones de uso pertenecen a la capa de IA.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = 4
MAX_WEAPON_NAME_LENGTH = 120
MAX_SPECIAL_MECHANIC_LENGTH = 2000

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

RELOAD_TYPES = {
    "magazine",
    "battery",
    "shell_by_shell",
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
    """Agrupa todos los errores encontrados en una sola validación."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _optional_text(
    value: Any,
    field: str,
    errors: list[str],
    *,
    maximum_length: int,
) -> str | None:
    text = _text(value)

    if not text:
        return None

    if len(text) > maximum_length:
        errors.append(
            f"{field} no puede superar {maximum_length} caracteres."
        )
        return None

    return text


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
    maximum: int | None = None,
    required: bool = True,
) -> int | None:
    number = _number(
        value,
        field,
        errors,
        minimum=float(minimum),
        maximum=float(maximum) if maximum is not None else None,
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


def _optional_integer(
    raw_data: Mapping[str, Any],
    field: str,
    errors: list[str],
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int | None:
    if not _text(raw_data.get(field)):
        return None

    return _integer(
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


def _normalize_choice(
    value: Any,
    field: str,
    allowed_values: set[str],
    errors: list[str],
    *,
    default: str | None = None,
) -> str:
    normalized = _text(value).lower()

    if not normalized and default is not None:
        return default

    if not normalized:
        errors.append(f"Falta el campo obligatorio: {field}.")
        return ""

    if normalized not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        errors.append(
            f"{field} no es válido. Valores permitidos: {allowed}."
        )

    return normalized


def _normalize_category(value: Any, errors: list[str]) -> str:
    category = CATEGORY_ALIASES.get(_text(value).lower(), "")

    if not category:
        errors.append("weapon_category debe ser primary, secondary o melee.")

    return category


def _compact(values: Mapping[str, Any]) -> dict[str, Any]:
    """Elimina únicamente valores ausentes; conserva cero y False."""

    return {
        key: value
        for key, value in values.items()
        if value is not None and value != ""
    }


def _parse_base_damage(
    raw_data: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    source = raw_data.get("base_damage")

    if not isinstance(source, Mapping):
        errors.append("base_damage debe ser un diccionario de tipos de daño.")
        source = {}

    normalized_source = {
        _text(key).lower(): value
        for key, value in source.items()
    }

    unknown_types = sorted(
        damage_type
        for damage_type in normalized_source
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
        if damage_type not in normalized_source:
            continue

        value = _number(
            normalized_source.get(damage_type),
            f"base_damage.{damage_type}",
            errors,
            minimum=0.0,
        )

        if value is not None and value > 0:
            components[damage_type] = round(value, 4)

    total = round(sum(components.values()), 4)

    if total <= 0:
        errors.append(
            "base_damage debe contener al menos un tipo de daño mayor que cero."
        )

    distribution = (
        {
            damage_type: round(value / total * 100.0, 4)
            for damage_type, value in components.items()
        }
        if total > 0
        else {}
    )

    dominant_type = max(components, key=components.get) if components else None
    physical_total = sum(
        components.get(damage_type, 0.0)
        for damage_type in PHYSICAL_DAMAGE_TYPES
    )

    return {
        "base_total": total,
        "components": components,
        "distribution_percent": distribution,
        "dominant_type": dominant_type,
        "physical_percent": (
            round(physical_total / total * 100.0, 4) if total > 0 else 0.0
        ),
        "elemental_percent": (
            round((total - physical_total) / total * 100.0, 4)
            if total > 0
            else 0.0
        ),
    }


def _parse_ranged(
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
    reload_type = _normalize_choice(
        raw_data.get("reload_type"),
        "reload_type",
        RELOAD_TYPES,
        errors,
        default="magazine",
    )

    has_multiple_pellets = _boolean(
        raw_data.get("has_multiple_pellets"),
        "has_multiple_pellets",
        errors,
    )
    is_explosive = _boolean(
        raw_data.get("is_explosive"),
        "is_explosive",
        errors,
    )

    classification = {
        "firing_mode": firing_mode,
        "damage_delivery": damage_delivery,
        "reload_type": reload_type,
        "has_multiple_pellets": has_multiple_pellets,
        "is_explosive": is_explosive,
    }

    stats = _compact(
        {
            "fire_rate": _number(
                raw_data.get("fire_rate"),
                "fire_rate",
                errors,
                minimum=0.0001,
            ),
            "multishot": _number(
                raw_data.get("multishot"),
                "multishot",
                errors,
                minimum=0.0001,
            ),
            "magazine_size": _integer(
                raw_data.get("magazine_size"),
                "magazine_size",
                errors,
                minimum=1,
            ),
            "reload_time": _number(
                raw_data.get("reload_time"),
                "reload_time",
                errors,
                minimum=0.0,
            ),
            "ammo_capacity": _optional_integer(
                raw_data,
                "ammo_capacity",
                errors,
                minimum=1,
            ),
            "accuracy": _optional_number(
                raw_data,
                "accuracy",
                errors,
                minimum=0.0,
            ),
            "recoil": _optional_number(
                raw_data,
                "recoil",
                errors,
                minimum=0.0,
            ),
            "punch_through": _optional_number(
                raw_data,
                "punch_through",
                errors,
                minimum=0.0,
            ),
        }
    )

    conditional = {
        "shots_per_burst": None,
        "charge_time": None,
        "pellet_count": None,
        "projectile_speed": None,
        "beam_range": None,
        "explosion_radius": None,
        "battery_recharge_rate": None,
        "reload_per_round": None,
    }

    if firing_mode == "burst":
        conditional["shots_per_burst"] = _integer(
            raw_data.get("shots_per_burst"),
            "shots_per_burst",
            errors,
            minimum=1,
        )

    if firing_mode == "charge":
        conditional["charge_time"] = _number(
            raw_data.get("charge_time"),
            "charge_time",
            errors,
            minimum=0.0001,
        )

    if has_multiple_pellets:
        conditional["pellet_count"] = _integer(
            raw_data.get("pellet_count"),
            "pellet_count",
            errors,
            minimum=1,
        )

    if damage_delivery == "projectile":
        conditional["projectile_speed"] = _optional_number(
            raw_data,
            "projectile_speed",
            errors,
            minimum=0.0001,
        )

    if damage_delivery == "beam":
        conditional["beam_range"] = _optional_number(
            raw_data,
            "beam_range",
            errors,
            minimum=0.0001,
        )

    if is_explosive:
        conditional["explosion_radius"] = _optional_number(
            raw_data,
            "explosion_radius",
            errors,
            minimum=0.0001,
        )

    if reload_type == "battery":
        conditional["battery_recharge_rate"] = _optional_number(
            raw_data,
            "battery_recharge_rate",
            errors,
            minimum=0.0001,
        )

    if reload_type == "shell_by_shell":
        conditional["reload_per_round"] = _optional_number(
            raw_data,
            "reload_per_round",
            errors,
            minimum=0.0001,
        )

    return {
        "classification": classification,
        "stats": stats,
        "conditional_stats": _compact(conditional),
    }


def _parse_melee(
    raw_data: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "stats": _compact(
            {
                "attack_speed": _number(
                    raw_data.get("attack_speed"),
                    "attack_speed",
                    errors,
                    minimum=0.0001,
                ),
                "range": _number(
                    raw_data.get("range"),
                    "range",
                    errors,
                    minimum=0.0001,
                ),
                "heavy_attack_damage": _optional_number(
                    raw_data,
                    "heavy_attack_damage",
                    errors,
                    minimum=0.0001,
                ),
                "heavy_attack_wind_up": _optional_number(
                    raw_data,
                    "heavy_attack_wind_up",
                    errors,
                    minimum=0.0001,
                ),
            }
        )
    }


def parse_weapon_data(raw_data: Mapping[str, Any]) -> dict[str, Any]:
    """Valida una entrada y devuelve un esquema objetivo y normalizado.

    El resultado no contiene perfiles, puntuaciones ni recomendaciones.
    """

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

    weapon_name = _optional_text(
        raw_data.get("weapon_name"),
        "weapon_name",
        errors,
        maximum_length=MAX_WEAPON_NAME_LENGTH,
    )
    special_mechanic = _optional_text(
        raw_data.get("special_mechanic"),
        "special_mechanic",
        errors,
        maximum_length=MAX_SPECIAL_MECHANIC_LENGTH,
    )

    core_stats = {
        "critical_chance_percent": _number(
            raw_data.get("critical_chance_percent"),
            "critical_chance_percent",
            errors,
            minimum=0.0,
        ),
        "critical_multiplier": _number(
            raw_data.get("critical_multiplier"),
            "critical_multiplier",
            errors,
            minimum=1.0,
        ),
        "status_chance_percent": _number(
            raw_data.get("status_chance_percent"),
            "status_chance_percent",
            errors,
            minimum=0.0,
        ),
    }

    damage = _parse_base_damage(raw_data, errors)

    ranged: dict[str, Any] | None = None
    melee: dict[str, Any] | None = None

    if category in {"primary", "secondary"}:
        ranged = _parse_ranged(raw_data, errors)
    elif category == "melee":
        melee = _parse_melee(raw_data, errors)

    if errors:
        raise WeaponValidationError(errors)

    return {
        "schema_version": SCHEMA_VERSION,
        "data_source": source,
        "weapon_name": weapon_name,
        "weapon_category": category,
        "special_mechanic": special_mechanic,
        "damage": damage,
        "core_stats": core_stats,
        "ranged": ranged,
        "melee": melee,
    }


# Alias corto para scripts y pruebas.
parse = parse_weapon_data
