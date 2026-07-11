# modules/prompt_builder.py

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


DAMAGE_LABELS = {
    "impact": "Impacto",
    "puncture": "Perforación",
    "slash": "Corte",
    "heat": "Calor",
    "cold": "Frío",
    "electricity": "Electricidad",
    "toxin": "Toxina",
    "blast": "Explosión",
    "corrosive": "Corrosivo",
    "gas": "Gas",
    "magnetic": "Magnético",
    "radiation": "Radiación",
    "viral": "Viral",
    "void": "Vacío",
}

CATEGORY_LABELS = {
    "primary": "Primaria",
    "secondary": "Secundaria",
    "melee": "Melee",
}

FIRING_MODE_LABELS = {
    "automatic": "Automático",
    "semi_automatic": "Semiautomático",
    "burst": "Ráfaga",
    "charge": "Carga",
    "continuous": "Continuo",
}

DELIVERY_LABELS = {
    "hitscan": "Hitscan",
    "projectile": "Proyectil",
    "beam": "Haz",
}


class PromptBuilderError(ValueError):
    pass


def _format_number(value: Any, decimals: int = 4) -> str:
    if value is None:
        return ""

    number = float(value)

    if number.is_integer():
        return str(int(number))

    return f"{number:.{decimals}f}".rstrip("0").rstrip(".")


def _append_stat(
    lines: list[str],
    label: str,
    value: Any,
    suffix: str = "",
) -> None:
    if value is None:
        return

    formatted = _format_number(value)
    lines.append(f"- {label}: {formatted}{suffix}")


def _build_damage_section(damage: Mapping[str, Any]) -> list[str]:
    components = damage.get("components", {})
    distribution = damage.get("distribution_percent", {})

    if not isinstance(components, Mapping) or not components:
        raise PromptBuilderError("No hay componentes de daño base válidos.")

    lines = ["DAÑO BASE"]
    _append_stat(lines, "Daño base total", damage.get("base_total"))

    for damage_type, value in components.items():
        label = DAMAGE_LABELS.get(damage_type, str(damage_type))
        percent = distribution.get(damage_type)

        if percent is None:
            lines.append(f"- {label}: {_format_number(value)}")
        else:
            lines.append(
                f"- {label}: {_format_number(value)} "
                f"({_format_number(percent)} %)"
            )

    dominant_type = damage.get("dominant_type")

    if dominant_type:
        dominant_label = DAMAGE_LABELS.get(
            dominant_type,
            str(dominant_type),
        )
        lines.append(f"- Tipo dominante: {dominant_label}")

    _append_stat(
        lines,
        "Proporción de daño físico",
        damage.get("physical_percent"),
        " %",
    )
    _append_stat(
        lines,
        "Proporción de daño elemental",
        damage.get("elemental_percent"),
        " %",
    )

    return lines


def _build_core_section(core_stats: Mapping[str, Any]) -> list[str]:
    lines = ["ESTADÍSTICAS CENTRALES"]
    _append_stat(
        lines,
        "Probabilidad crítica",
        core_stats.get("critical_chance_percent"),
        " %",
    )
    _append_stat(
        lines,
        "Multiplicador crítico",
        core_stats.get("critical_multiplier"),
        "x",
    )
    _append_stat(
        lines,
        "Probabilidad de estado",
        core_stats.get("status_chance_percent"),
        " %",
    )
    return lines


def _build_ranged_section(weapon_data: Mapping[str, Any]) -> list[str]:
    classification = weapon_data.get("ranged_classification") or {}
    ranged_stats = weapon_data.get("ranged_stats") or {}
    conditional_stats = weapon_data.get("conditional_stats") or {}
    derived = weapon_data.get("derived") or {}

    lines = ["PERFIL DE ARMA A DISTANCIA"]

    firing_mode = classification.get("firing_mode")
    damage_delivery = classification.get("damage_delivery")

    lines.append(
        "- Modo de disparo: "
        + FIRING_MODE_LABELS.get(firing_mode, str(firing_mode))
    )
    lines.append(
        "- Entrega del daño: "
        + DELIVERY_LABELS.get(damage_delivery, str(damage_delivery))
    )
    lines.append(
        "- Múltiples perdigones: "
        + ("Sí" if classification.get("has_multiple_pellets") else "No")
    )
    lines.append(
        "- Explosiva: "
        + ("Sí" if classification.get("is_explosive") else "No")
    )

    _append_stat(lines, "Cadencia de fuego", ranged_stats.get("fire_rate"))
    _append_stat(lines, "Multidisparo base", ranged_stats.get("multishot"))
    _append_stat(lines, "Tamaño del cargador", ranged_stats.get("magazine_size"))
    _append_stat(lines, "Tiempo de recarga", ranged_stats.get("reload_time"), " s")

    _append_stat(
        lines,
        "Disparos por ráfaga",
        conditional_stats.get("shots_per_burst"),
    )
    _append_stat(
        lines,
        "Tiempo de carga",
        conditional_stats.get("charge_time"),
        " s",
    )
    _append_stat(
        lines,
        "Cantidad de perdigones",
        conditional_stats.get("pellet_count"),
    )
    _append_stat(
        lines,
        "Velocidad del proyectil",
        conditional_stats.get("projectile_speed"),
    )
    _append_stat(
        lines,
        "Radio de explosión",
        conditional_stats.get("explosion_radius"),
    )
    _append_stat(
        lines,
        "Alcance del haz",
        conditional_stats.get("beam_range"),
    )

    if derived:
        lines.append("ESTIMACIONES DERIVADAS")
        _append_stat(
            lines,
            "Factor crítico promedio",
            derived.get("critical_factor"),
            "x",
        )
        _append_stat(
            lines,
            "Proyectiles por segundo",
            derived.get("projectiles_per_second"),
        )
        _append_stat(
            lines,
            "Eventos críticos por segundo estimados",
            derived.get("critical_events_per_second_estimate"),
        )
        _append_stat(
            lines,
            "Eventos de estado por segundo estimados",
            derived.get("status_events_per_second_estimate"),
        )
        _append_stat(
            lines,
            "Duración estimada del cargador",
            derived.get("magazine_duration_seconds"),
            " s",
        )
        _append_stat(
            lines,
            "Tiempo del ciclo ocupado en recarga",
            derived.get("reload_downtime_percent"),
            " %",
        )

    return lines


def _build_melee_section(weapon_data: Mapping[str, Any]) -> list[str]:
    melee_stats = weapon_data.get("melee_stats") or {}
    derived = weapon_data.get("derived") or {}

    lines = ["PERFIL MELEE"]
    _append_stat(
        lines,
        "Velocidad de ataque",
        melee_stats.get("attack_speed"),
    )
    _append_stat(lines, "Alcance", melee_stats.get("range"))
    _append_stat(
        lines,
        "Daño de ataque pesado",
        melee_stats.get("heavy_attack_damage"),
    )
    _append_stat(
        lines,
        "Preparación de ataque pesado",
        melee_stats.get("heavy_attack_wind_up"),
        " s",
    )

    if derived:
        lines.append("ESTIMACIONES DERIVADAS")
        _append_stat(
            lines,
            "Factor crítico promedio",
            derived.get("critical_factor"),
            "x",
        )
        _append_stat(
            lines,
            "Eventos críticos por segundo estimados",
            derived.get("critical_events_per_second_estimate"),
        )
        _append_stat(
            lines,
            "Eventos de estado por segundo estimados",
            derived.get("status_events_per_second_estimate"),
        )
        _append_stat(
            lines,
            "Relación entre ataque pesado y daño base",
            derived.get("heavy_to_base_damage_ratio"),
            "x",
        )
        _append_stat(
            lines,
            "Daño pesado por segundo de preparación",
            derived.get("heavy_damage_per_wind_up_second"),
        )

    return lines


def build_weapon_prompt(weapon_data: Mapping[str, Any]) -> str:
    if not isinstance(weapon_data, Mapping):
        raise TypeError("weapon_data debe ser un diccionario o Mapping.")

    if weapon_data.get("schema_version") != 2:
        raise PromptBuilderError(
            "El constructor requiere datos validados con schema_version 2."
        )

    category = weapon_data.get("weapon_category")

    if category not in CATEGORY_LABELS:
        raise PromptBuilderError("La categoría del arma no es válida.")

    damage = weapon_data.get("damage")
    core_stats = weapon_data.get("core_stats")

    if not isinstance(damage, Mapping):
        raise PromptBuilderError("Falta la sección de daño validado.")

    if not isinstance(core_stats, Mapping):
        raise PromptBuilderError("Faltan las estadísticas centrales validadas.")

    lines = [
        "Analiza exclusivamente las siguientes estadísticas base de un arma de Warframe.",
        "No uses el nombre del arma ni información externa para completar datos ausentes.",
        "Evalúa las relaciones internas entre sus estadísticas, no una build existente.",
        "",
        f"CATEGORÍA: {CATEGORY_LABELS[category]}",
        "",
        *_build_damage_section(damage),
        "",
        *_build_core_section(core_stats),
        "",
    ]

    if category in {"primary", "secondary"}:
        lines.extend(_build_ranged_section(weapon_data))
    else:
        lines.extend(_build_melee_section(weapon_data))

    lines.extend([
        "",
        "RESPONDE EN ESTE FORMATO:",
        "Tendencia principal: explica el patrón estadístico dominante.",
        "Fortalezas: indica las estadísticas que ya favorecen al arma.",
        "Limitaciones: señala las estadísticas que restringen su desempeño.",
        "Prioridades: distingue entre reforzar fortalezas y corregir debilidades.",
        "Uso recomendado: indica los estilos de uso coherentes con los datos.",
        "Uso poco recomendado: indica estilos desfavorables y explica por qué.",
        "",
        "REGLAS DE RESPUESTA:",
        "- No generes una build completa.",
        "- No recomiendes mods, Arcanos, Rivens, polaridades ni Formas.",
        "- No inventes estadísticas, mecánicas o datos ausentes.",
        "- No trates las estimaciones derivadas como daño real exacto.",
        "- Si faltan datos opcionales, no saques conclusiones sobre ellos.",
        "- Sé concreto y evita repetir toda la tabla de estadísticas.",
    ])

    return "\n".join(lines).strip()


build_prompt = build_weapon_prompt