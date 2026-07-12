
# modules/prompt_builder.py

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from modules.weapon_interpreter import interpret_weapon_data


CATEGORY_LABELS = {
    "primary": "Primaria",
    "secondary": "Secundaria",
    "melee": "Melee",
}

EXPECTED_HEADINGS = (
    "Tendencia principal",
    "Fortalezas",
    "Limitaciones",
    "Prioridades",
    "Uso recomendado",
    "Uso poco recomendado",
)


class PromptBuilderError(ValueError):
    pass


def _format_number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return ""

    number = float(value)
    if number.is_integer():
        return str(int(number))

    return f"{number:.{decimals}f}".rstrip("0").rstrip(".")


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PromptBuilderError(f"Falta la sección interpretada: {name}.")
    return value


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _finding_lines(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []

    lines: list[str] = []
    for finding in value:
        if not isinstance(finding, Mapping):
            continue

        statement = str(finding.get("statement") or "").strip()
        evidence = _as_text_list(finding.get("evidence"))

        if not statement:
            continue

        if evidence:
            lines.append(f"- {statement} Evidencia: {' '.join(evidence)}")
        else:
            lines.append(f"- {statement}")

    return lines


def _list_lines(value: Any) -> list[str]:
    return [f"- {item}" for item in _as_text_list(value)]


def _normalize_input(data: Mapping[str, Any]) -> Mapping[str, Any]:
    if data.get("interpretation_version") == 1:
        return data

    if data.get("schema_version") == 3:
        return interpret_weapon_data(data)

    raise PromptBuilderError(
        "El constructor requiere una interpretación versión 1 o datos parseados con schema_version 3."
    )


def build_weapon_prompt(data: Mapping[str, Any]) -> str:
    if not isinstance(data, Mapping):
        raise TypeError("data debe ser un diccionario o Mapping.")

    interpretation = _normalize_input(data)
    category = str(interpretation.get("weapon_category"))

    if category not in CATEGORY_LABELS:
        raise PromptBuilderError("La categoría interpretada no es válida.")

    tendency = _require_mapping(
        interpretation.get("tendency"),
        "tendency",
    )
    profiles = _require_mapping(
        interpretation.get("profiles"),
        "profiles",
    )
    priorities = _require_mapping(
        interpretation.get("priorities"),
        "priorities",
    )
    use_cases = _require_mapping(
        interpretation.get("use_cases"),
        "use_cases",
    )
    confidence = _require_mapping(
        interpretation.get("confidence"),
        "confidence",
    )
    special_context = interpretation.get("special_context") or {}
    if not isinstance(special_context, Mapping):
        special_context = {}

    critical = _require_mapping(profiles.get("critical"), "profiles.critical")
    status = _require_mapping(profiles.get("status"), "profiles.status")
    damage = _require_mapping(profiles.get("damage"), "profiles.damage")
    impact_frequency = profiles.get("impact_frequency")
    continuity = profiles.get("continuity")

    lines = [
        "Los siguientes datos ya fueron validados, calculados e interpretados por reglas deterministas.",
        "Redacta el análisis sin recalcular, cambiar clasificaciones ni agregar conocimiento externo.",
        "",
        f"CATEGORÍA: {CATEGORY_LABELS[category]}",
        (
            f"CONFIANZA DEL ANÁLISIS: {confidence.get('label', 'no determinada')} "
            f"({confidence.get('scope', 'alcance no especificado')})"
        ),
        "",
        "TENDENCIA CALCULADA",
        f"- {str(tendency.get('statement') or '').strip()}",
        *_list_lines(tendency.get("evidence")),
        "",
        "PERFILES CALCULADOS",
        (
            "- Crítico: "
            f"{critical.get('rating_label')} | "
            f"{_format_number(critical.get('chance_percent'))} % | "
            f"{_format_number(critical.get('multiplier'))}x | "
            f"factor promedio {_format_number(critical.get('expected_damage_factor'))}x."
        ),
        (
            "- Estado: "
            f"{status.get('rating_label')} | "
            f"{_format_number(status.get('chance_percent'))} % por impacto"
            + (
                f" | {_format_number(status.get('expected_procs_per_second'))} procs/s estimados."
                if status.get("expected_procs_per_second") is not None
                else "."
            )
        ),
        (
            "- Daño base: "
            f"tipo dominante {damage.get('dominant_label')} "
            f"({_format_number(damage.get('dominant_percent'))} %); "
            f"distribución {damage.get('concentration_label')}."
        ),
    ]

    if isinstance(impact_frequency, Mapping):
        lines.append(
            "- Frecuencia de impactos: "
            f"{impact_frequency.get('rating_label')} "
            f"({_format_number(impact_frequency.get('instances_per_second'))} instancias/s nominales)."
        )

    if isinstance(continuity, Mapping):
        lines.append(
            "- Continuidad: ventana de fuego "
            f"{continuity.get('fire_window_label')} "
            f"({_format_number(continuity.get('magazine_duration_seconds'))} s); "
            f"presión de recarga {continuity.get('reload_pressure_label')}"
            + (
                f" ({_format_number(continuity.get('downtime_percent'))} % del ciclo)."
                if continuity.get("downtime_percent") is not None
                else "."
            )
        )

    strengths = _finding_lines(interpretation.get("strengths"))
    limitations = _finding_lines(interpretation.get("limitations"))

    lines.extend([
        "",
        "FORTALEZAS CONFIRMADAS",
        *(strengths or ["- No se confirmó una fortaleza dominante con las reglas actuales."]),
        "",
        "LIMITACIONES CONFIRMADAS",
        *(limitations or ["- No se confirmó una limitación dominante con las reglas actuales."]),
        "",
        "PRIORIDADES YA DETERMINADAS",
        "Reforzar:",
        *(_list_lines(priorities.get("reinforce")) or ["- Sin prioridad de refuerzo dominante."]),
        "Corregir:",
        *(_list_lines(priorities.get("correct")) or ["- Sin corrección dominante."]),
        "Evitar forzar:",
        *(_list_lines(priorities.get("avoid_forcing")) or ["- Ninguna ruta adicional identificada."]),
        "",
        "USOS COMPATIBLES",
        *(_list_lines(use_cases.get("recommended")) or ["- No determinado."]),
        "",
        "USOS POCO COMPATIBLES",
        *(_list_lines(use_cases.get("poor_fit")) or ["- No determinado."]),
        "",
        "LÍMITES OBLIGATORIOS",
        *(_list_lines(confidence.get("limits")) or ["- Usa solo los datos proporcionados."]),
        *(_list_lines(interpretation.get("calculation_assumptions"))),
        "Contexto faltante que no debe suponerse:",
        *(_list_lines(confidence.get("missing_context")) or ["- Ninguno declarado."]),
        "Conclusiones prohibidas:",
        *(_list_lines(interpretation.get("forbidden_conclusions")) or ["- Información no incluida en la entrada."]),
        "",
        "FORMATO OBLIGATORIO",
        "Tendencia principal: una o dos oraciones.",
        "Fortalezas: máximo tres oraciones.",
        "Limitaciones: máximo tres oraciones.",
        "Prioridades: distingue claramente reforzar fortalezas y corregir debilidades.",
        "Uso recomendado: una o dos oraciones.",
        "Uso poco recomendado: una o dos oraciones.",
        "",
        "No repitas la tabla completa. No uses listas de estadísticas sin interpretación.",
        "No recomiendes objetos concretos ni una build completa.",
    ])


    special_note = str(
        special_context.get("special_mechanics_note") or ""
    ).strip()
    if special_note:
        limits_index = lines.index("LÍMITES OBLIGATORIOS")
        lines[limits_index:limits_index] = [
            "CONTEXTO ESPECIAL DECLARADO",
            f"- {special_note}",
            "- Menciónalo únicamente como contexto declarado; no inventes consecuencias adicionales.",
            "",
        ]

    return "\n".join(line for line in lines if line is not None).strip()


def expected_headings() -> tuple[str, ...]:
    return EXPECTED_HEADINGS


build_prompt = build_weapon_prompt