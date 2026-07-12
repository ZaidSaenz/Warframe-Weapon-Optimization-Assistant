# modules/weapon_parser.py

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = 3

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
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


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

    if total_base_damage > 0:
        distribution_percent = {
            damage_type: round(value / total_base_damage * 100.0, 4)
            for damage_type, value in components.items()
        }
    else:
        distribution_percent = {}

    dominant_type = max(components, key=components.get) if components else None
    dominant_percent = (
        distribution_percent.get(dominant_type, 0.0)
        if dominant_type is not None
        else 0.0
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
        "dominant_percent": round(dominant_percent, 4),
        "physical_percent": round(physical_percent, 4),
        "elemental_percent": (
            round(100.0 - physical_percent, 4)
            if total_base_damage > 0
            else 0.0
        ),
    }


def _parse_ranged_classification(
    raw_data: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "firing_mode": _normalize_choice(
            raw_data.get("firing_mode"),
            "firing_mode",
            FIRING_MODES,
            errors,
        ),
        "damage_delivery": _normalize_choice(
            raw_data.get("damage_delivery"),
            "damage_delivery",
            DAMAGE_DELIVERY_TYPES,
            errors,
        ),
        "reload_type": _normalize_choice(
            raw_data.get("reload_type"),
            "reload_type",
            RELOAD_TYPES,
            errors,
            default="magazine",
        ),
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
    reload_type = classification.get("reload_type")
    has_multiple_pellets = bool(
        classification.get("has_multiple_pellets")
    )
    is_explosive = bool(classification.get("is_explosive"))

    if firing_mode == "burst":
        stats["shots_per_burst"] = _integer(
            raw_data.get("shots_per_burst"),
            "shots_per_burst",
            errors,
            minimum=2,
        )

    if firing_mode == "charge":
        stats["charge_time"] = _number(
            raw_data.get("charge_time"),
            "charge_time",
            errors,
            minimum=0.0001,
        )

    stats["pellet_count"] = 1
    if has_multiple_pellets:
        stats["pellet_count"] = _integer(
            raw_data.get("pellet_count"),
            "pellet_count",
            errors,
            minimum=2,
        )

    if damage_delivery == "projectile":
        projectile_speed = _optional_number(
            raw_data,
            "projectile_speed",
            errors,
            minimum=0.0001,
        )
        if projectile_speed is not None:
            stats["projectile_speed"] = projectile_speed

    if damage_delivery == "beam":
        beam_range = _optional_number(
            raw_data,
            "beam_range",
            errors,
            minimum=0.0001,
        )
        if beam_range is not None:
            stats["beam_range"] = beam_range

    if is_explosive:
        explosion_radius = _optional_number(
            raw_data,
            "explosion_radius",
            errors,
            minimum=0.0001,
        )
        if explosion_radius is not None:
            stats["explosion_radius"] = explosion_radius

    if reload_type == "battery":
        stats["reload_delay"] = _number(
            raw_data.get("reload_delay"),
            "reload_delay",
            errors,
            minimum=0.0,
        )
        stats["recharge_rate_per_second"] = _number(
            raw_data.get("recharge_rate_per_second"),
            "recharge_rate_per_second",
            errors,
            minimum=0.0001,
        )

    if reload_type == "shell_by_shell":
        stats["reload_time_per_round"] = _number(
            raw_data.get("reload_time_per_round"),
            "reload_time_per_round",
            errors,
            minimum=0.0001,
        )
        initial_delay = _optional_number(
            raw_data,
            "reload_initial_delay",
            errors,
            minimum=0.0,
        )
        if initial_delay is not None:
            stats["reload_initial_delay"] = initial_delay

    return {
        key: value
        for key, value in stats.items()
        if value is not None
    }


def _parse_ranged_stats(
    raw_data: Mapping[str, Any],
    classification: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    reload_type = classification.get("reload_type")

    stats: dict[str, Any] = {
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
        "ammo_per_shot": _optional_number(
            raw_data,
            "ammo_per_shot",
            errors,
            minimum=0.0001,
        ) or 1.0,
    }

    if reload_type == "magazine":
        stats["reload_time"] = _number(
            raw_data.get("reload_time"),
            "reload_time",
            errors,
            minimum=0.0001,
        )
    else:
        reload_time = _optional_number(
            raw_data,
            "reload_time",
            errors,
            minimum=0.0001,
        )
        if reload_time is not None:
            stats["displayed_reload_time"] = reload_time

    return {
        key: value
        for key, value in stats.items()
        if value is not None
    }


def _parse_melee_stats(
    raw_data: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    stats: dict[str, Any] = {
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
    }

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

    if (heavy_attack_damage is None) != (heavy_attack_wind_up is None):
        errors.append(
            "heavy_attack_damage y heavy_attack_wind_up deben enviarse juntos."
        )

    if heavy_attack_damage is not None:
        stats["heavy_attack_damage"] = heavy_attack_damage
    if heavy_attack_wind_up is not None:
        stats["heavy_attack_wind_up"] = heavy_attack_wind_up

    melee_family = _optional_text(raw_data.get("melee_family"))
    if melee_family:
        stats["melee_family"] = melee_family.lower()

    return {
        key: value
        for key, value in stats.items()
        if value is not None
    }


def _probability_at_least_one_event(
    probability_percent: float,
    multishot: float,
    pellet_count: int,
) -> float:
    """Estimate event reliability with fractional multishot.

    Fractional multishot is treated as an integer number of projectiles plus
    one additional projectile group with probability equal to the fraction.
    Each projectile group contains ``pellet_count`` independent hit instances.
    """
    if probability_percent <= 0:
        return 0.0
    if probability_percent >= 100:
        return 100.0

    probability = probability_percent / 100.0
    whole_projectiles = math.floor(multishot)
    fractional_projectile = multishot - whole_projectiles

    no_event_per_projectile = (1.0 - probability) ** pellet_count
    no_event_probability = no_event_per_projectile ** whole_projectiles
    no_event_probability *= (
        (1.0 - fractional_projectile)
        + fractional_projectile * no_event_per_projectile
    )

    return round((1.0 - no_event_probability) * 100.0, 4)


def _critical_tier_profile(critical_chance: float) -> dict[str, Any]:
    tiers = critical_chance / 100.0
    guaranteed_tier = math.floor(tiers)
    next_tier_chance = (tiers - guaranteed_tier) * 100.0

    return {
        "average_tier": round(tiers, 4),
        "guaranteed_tier": guaranteed_tier,
        "next_tier_chance_percent": round(next_tier_chance, 4),
    }


def _status_tier_profile(status_chance: float) -> dict[str, Any]:
    procs = status_chance / 100.0
    guaranteed_procs = math.floor(procs)
    extra_proc_chance = (procs - guaranteed_procs) * 100.0

    return {
        "expected_procs_per_instance": round(procs, 4),
        "guaranteed_procs_per_instance": guaranteed_procs,
        "extra_proc_chance_percent": round(extra_proc_chance, 4),
    }


def _derive_ranged(
    classification: Mapping[str, Any],
    ranged_stats: Mapping[str, Any],
    conditional_stats: Mapping[str, Any],
    critical_chance: float,
    critical_multiplier: float,
    status_chance: float,
) -> tuple[dict[str, Any], list[str]]:
    fire_rate = float(ranged_stats["fire_rate"])
    multishot = float(ranged_stats["multishot"])
    magazine_size = int(ranged_stats["magazine_size"])
    ammo_per_shot = float(ranged_stats["ammo_per_shot"])
    pellet_count = int(conditional_stats.get("pellet_count", 1))
    firing_mode = str(classification["firing_mode"])
    reload_type = str(classification["reload_type"])

    effective_shot_rate = fire_rate
    assumptions = [
        "fire_rate se interpreta como la tasa nominal de disparos o instancias consumiendo munición.",
        "multishot y pellet_count se usan para estimar oportunidades de crítico y estado, no daño real.",
    ]

    if firing_mode == "charge":
        charge_time = float(conditional_stats["charge_time"])
        charge_limited_rate = 1.0 / charge_time
        effective_shot_rate = min(fire_rate, charge_limited_rate)
        assumptions.append(
            "En modo charge se limita la tasa nominal por 1 / charge_time; no se modelan animaciones adicionales."
        )

    if firing_mode == "burst":
        assumptions.append(
            "En modo burst, fire_rate se conserva como cadencia de disparos; no se conoce la pausa entre ráfagas."
        )

    if firing_mode == "continuous":
        assumptions.append(
            "En modo continuous, las instancias por segundo son una aproximación basada en la cadencia declarada."
        )

    instances_per_shot = multishot * pellet_count
    instances_per_second = effective_shot_rate * instances_per_shot
    critical_factor = 1.0 + (critical_chance / 100.0) * (
        critical_multiplier - 1.0
    )

    ammo_consumption_per_second = effective_shot_rate * ammo_per_shot
    magazine_duration = magazine_size / ammo_consumption_per_second

    derived: dict[str, Any] = {
        "expected_critical_damage_factor": round(critical_factor, 4),
        "critical_tier_profile": _critical_tier_profile(critical_chance),
        "status_tier_profile": _status_tier_profile(status_chance),
        "effective_shot_rate": round(effective_shot_rate, 4),
        "nominal_instances_per_shot": round(instances_per_shot, 4),
        "nominal_instances_per_second": round(instances_per_second, 4),
        "expected_critical_tiers_per_shot": round(
            instances_per_shot * critical_chance / 100.0,
            4,
        ),
        "expected_critical_tiers_per_second": round(
            instances_per_second * critical_chance / 100.0,
            4,
        ),
        "expected_status_procs_per_shot": round(
            instances_per_shot * status_chance / 100.0,
            4,
        ),
        "expected_status_procs_per_second": round(
            instances_per_second * status_chance / 100.0,
            4,
        ),
        "chance_at_least_one_critical_hit_per_shot_percent": (
            _probability_at_least_one_event(
                critical_chance,
                multishot,
                pellet_count,
            )
        ),
        "chance_at_least_one_status_proc_per_shot_percent": (
            _probability_at_least_one_event(
                status_chance,
                multishot,
                pellet_count,
            )
        ),
        "ammo_consumption_per_second": round(
            ammo_consumption_per_second,
            4,
        ),
        "magazine_duration_seconds": round(magazine_duration, 4),
    }

    shots_per_burst = conditional_stats.get("shots_per_burst")
    if shots_per_burst is not None:
        derived["nominal_instances_per_burst"] = round(
            float(shots_per_burst) * instances_per_shot,
            4,
        )

    if reload_type == "magazine":
        reload_time = float(ranged_stats["reload_time"])
        cycle_duration = magazine_duration + reload_time
        derived.update({
            "full_reload_duration_seconds": round(reload_time, 4),
            "full_cycle_duration_seconds": round(cycle_duration, 4),
            "reload_downtime_percent": round(
                reload_time / cycle_duration * 100.0,
                4,
            ),
        })

    elif reload_type == "battery":
        reload_delay = float(conditional_stats["reload_delay"])
        recharge_rate = float(
            conditional_stats["recharge_rate_per_second"]
        )
        full_recharge_time = reload_delay + magazine_size / recharge_rate
        full_cycle_duration = magazine_duration + full_recharge_time
        derived.update({
            "battery_reload_delay_seconds": round(reload_delay, 4),
            "battery_full_recharge_seconds": round(
                full_recharge_time,
                4,
            ),
            "full_cycle_duration_seconds": round(
                full_cycle_duration,
                4,
            ),
            "full_recharge_downtime_percent": round(
                full_recharge_time / full_cycle_duration * 100.0,
                4,
            ),
        })
        assumptions.append(
            "La batería se evalúa suponiendo vaciado completo y espera hasta recuperar todo el cargador."
        )

    elif reload_type == "shell_by_shell":
        reload_per_round = float(
            conditional_stats["reload_time_per_round"]
        )
        initial_delay = float(
            conditional_stats.get("reload_initial_delay", 0.0)
        )
        full_reload_time = initial_delay + magazine_size * reload_per_round
        full_cycle_duration = magazine_duration + full_reload_time
        derived.update({
            "full_reload_duration_seconds": round(
                full_reload_time,
                4,
            ),
            "full_cycle_duration_seconds": round(
                full_cycle_duration,
                4,
            ),
            "full_reload_downtime_percent": round(
                full_reload_time / full_cycle_duration * 100.0,
                4,
            ),
        })
        assumptions.append(
            "La recarga shell_by_shell se calcula para recuperar el cargador completo; no se modelan recargas parciales."
        )

    return derived, assumptions


def _derive_melee(
    melee_stats: Mapping[str, Any],
    total_base_damage: float,
    critical_chance: float,
    critical_multiplier: float,
    status_chance: float,
) -> tuple[dict[str, Any], list[str]]:
    critical_factor = 1.0 + (critical_chance / 100.0) * (
        critical_multiplier - 1.0
    )

    derived: dict[str, Any] = {
        "expected_critical_damage_factor": round(critical_factor, 4),
        "critical_tier_profile": _critical_tier_profile(critical_chance),
        "status_tier_profile": _status_tier_profile(status_chance),
        "expected_critical_tiers_per_hit": round(
            critical_chance / 100.0,
            4,
        ),
        "expected_status_procs_per_hit": round(
            status_chance / 100.0,
            4,
        ),
    }

    heavy_damage = melee_stats.get("heavy_attack_damage")
    heavy_wind_up = melee_stats.get("heavy_attack_wind_up")

    if heavy_damage is not None and total_base_damage > 0:
        derived["heavy_to_base_damage_ratio"] = round(
            float(heavy_damage) / total_base_damage,
            4,
        )

    if heavy_damage is not None and heavy_wind_up is not None:
        derived["heavy_raw_output_index"] = round(
            float(heavy_damage) / float(heavy_wind_up),
            4,
        )

    assumptions = [
        "attack_speed no se convierte a ataques por segundo porque faltan postura, animaciones e impactos por movimiento.",
        "heavy_raw_output_index compara daño declarado y preparación; no representa DPS real ni idoneidad definitiva."
    ]

    return derived, assumptions


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
        maximum=1000.0,
    )
    critical_multiplier = _number(
        raw_data.get("critical_multiplier"),
        "critical_multiplier",
        errors,
        minimum=1.0,
        maximum=100.0,
    )
    status_chance = _number(
        raw_data.get("status_chance_percent"),
        "status_chance_percent",
        errors,
        minimum=0.0,
        maximum=1000.0,
    )

    damage = _parse_base_damage(raw_data, errors)

    ranged_classification: dict[str, Any] | None = None
    ranged_stats: dict[str, Any] | None = None
    melee_stats: dict[str, Any] | None = None
    conditional_stats: dict[str, Any] = {}
    derived: dict[str, Any] = {}
    calculation_assumptions: list[str] = []

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
        ranged_stats = _parse_ranged_stats(
            raw_data,
            ranged_classification,
            errors,
        )

    if category == "melee":
        melee_stats = _parse_melee_stats(raw_data, errors)

    has_special_mechanics = _boolean(
        raw_data.get("has_special_mechanics"),
        "has_special_mechanics",
        errors,
        default=False,
    )
    heavy_context_complete = _boolean(
        raw_data.get("heavy_context_complete"),
        "heavy_context_complete",
        errors,
        default=False,
    )
    special_mechanics_note = _optional_text(
        raw_data.get("special_mechanics_note")
    )

    if errors:
        raise WeaponValidationError(errors)

    assert critical_chance is not None
    assert critical_multiplier is not None
    assert status_chance is not None

    if category in {"primary", "secondary"}:
        assert ranged_classification is not None
        assert ranged_stats is not None
        derived, calculation_assumptions = _derive_ranged(
            ranged_classification,
            ranged_stats,
            conditional_stats,
            critical_chance,
            critical_multiplier,
            status_chance,
        )
    else:
        assert melee_stats is not None
        derived, calculation_assumptions = _derive_melee(
            melee_stats,
            float(damage["base_total"]),
            critical_chance,
            critical_multiplier,
            status_chance,
        )

    return {
        "schema_version": SCHEMA_VERSION,
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
        "calculation_assumptions": calculation_assumptions,
        "context": {
            "has_special_mechanics": has_special_mechanics,
            "special_mechanics_note": special_mechanics_note,
            "heavy_context_complete": heavy_context_complete,
        },
    }


parse = parse_weapon_data