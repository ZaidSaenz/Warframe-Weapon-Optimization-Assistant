"""Coordinate four independent logical AI stages.

The module does not decide weapon roles with mathematical thresholds. It only
runs each stage, validates strict JSON, and persists selected results between
stages.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from modules.prompt_builder import (
    COMFORT_KEYS,
    JOB_KEYS,
    available_improvement_parameters,
    build_behavior_prompt,
    build_comfort_prompt,
    build_improvement_prompt,
    build_job_prompt,
)


ANALYSIS_VERSION = 3

BEHAVIOR_MAX_TOKENS = 140
JOB_MAX_TOKENS = 120
IMPROVEMENT_MAX_TOKENS = 180
COMFORT_MAX_TOKENS = 140

# stage_name, user_prompt, max_tokens -> generated text
StageGenerator = Callable[[str, str, int], str]


JOB_LABELS_ES = {
    "sustained_damage": "daño sostenido",
    "focused_damage": "daño concentrado",
    "group_clear": "limpieza de grupos",
    "area_control": "control de área",
    "status_application": "aplicación de estados",
    "enemy_priming": "preparación de enemigos",
    "precision_attacks": "ataques precisos",
    "heavy_attacks": "ataques pesados",
    "general_use": "uso general",
}

COMFORT_LABELS_ES = {
    "comfortable": "cómoda",
    "manageable": "manejable",
    "demanding": "exigente",
    "undetermined": "no determinada",
}

PARAMETER_LABELS_ES = {
    "base_damage": "daño base",
    "critical_chance": "probabilidad crítica",
    "critical_multiplier": "multiplicador crítico",
    "status_chance": "probabilidad de estado",
    "fire_rate": "cadencia",
    "multishot": "multidisparo",
    "magazine_size": "cargador",
    "reload_time": "recarga",
    "ammo_capacity": "capacidad de munición",
    "accuracy": "precisión",
    "recoil": "retroceso",
    "punch_through": "Punch Through",
    "projectile_speed": "velocidad de proyectil",
    "beam_range": "alcance del haz",
    "explosion_radius": "radio de explosión",
    "charge_time": "tiempo de carga",
    "battery_recharge_rate": "recarga de batería",
    "reload_per_round": "recarga por cartucho",
    "attack_speed": "velocidad de ataque",
    "melee_range": "alcance melee",
    "heavy_attack_damage": "daño de ataque pesado",
    "heavy_attack_wind_up": "preparación del ataque pesado",
    "none": "ninguna mejora dominante",
}

DIRECTION_LABELS_ES = {
    "reinforce": "reforzar",
    "correct_friction": "corregir fricción",
    "none": "sin cambio",
}


class StageFormatError(ValueError):
    """The model answered, but its JSON did not match the stage schema."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StageFormatError(f"Missing structured section: {name}.")
    return value


def _strip_code_fence(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip()


def _json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_code_fence(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise StageFormatError("Response is not valid JSON.") from error

    if not isinstance(data, dict):
        raise StageFormatError("Response JSON must be an object.")
    return data


def _short_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise StageFormatError(f"Missing text field: {field}.")
    return text


def _string_list(value: Any, field: str, maximum: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise StageFormatError(f"{field} must be a list.")

    result = [str(item).strip() for item in value if str(item).strip()]
    return result[:maximum]


def parse_behavior_response(text: str) -> dict[str, Any]:
    data = _json_object(text)
    return {
        "summary": _short_text(data.get("summary_es"), "summary_es"),
        "traits": _string_list(data.get("traits_es"), "traits_es", 3),
    }


def parse_job_response(text: str) -> dict[str, Any]:
    data = _json_object(text)
    job = str(data.get("job") or "").strip()
    if job not in JOB_KEYS:
        raise StageFormatError("job is not an allowed enum value.")

    return {
        "key": job,
        "name": JOB_LABELS_ES[job],
        "reason": _short_text(data.get("reason_es"), "reason_es"),
    }


def parse_improvement_response(
    text: str,
    allowed_parameters: tuple[str, ...],
) -> list[dict[str, str]]:
    data = _json_object(text)
    items = data.get("improvements")
    if not isinstance(items, list) or not items:
        raise StageFormatError("improvements must be a non-empty list.")

    allowed = set(allowed_parameters)
    allowed.add("none")
    results: list[dict[str, str]] = []

    for item in items[:3]:
        if not isinstance(item, Mapping):
            raise StageFormatError("Each improvement must be an object.")

        parameter = str(item.get("parameter") or "").strip()
        direction = str(item.get("direction") or "").strip()
        reason = _short_text(item.get("reason_es"), "reason_es")

        if parameter not in allowed:
            raise StageFormatError(
                f"Improvement parameter is not allowed: {parameter}."
            )
        allowed_directions = {"reinforce", "correct_friction"}
        if parameter == "none":
            allowed_directions.add("none")
        if direction not in allowed_directions:
            raise StageFormatError("Invalid improvement direction.")

        results.append(
            {
                "parameter_key": parameter,
                "parameter": PARAMETER_LABELS_ES.get(parameter, parameter),
                "direction_key": direction,
                "direction": DIRECTION_LABELS_ES[direction],
                "reason": reason,
            }
        )

    if any(item["parameter_key"] == "none" for item in results):
        if len(results) != 1:
            raise StageFormatError("none must be the only improvement.")

    return results


def parse_comfort_response(text: str) -> dict[str, Any]:
    data = _json_object(text)
    rating = str(data.get("rating") or "").strip()
    if rating not in COMFORT_KEYS:
        raise StageFormatError("rating is not an allowed enum value.")

    return {
        "rating_key": rating,
        "rating": COMFORT_LABELS_ES[rating],
        "description": _short_text(
            data.get("description_es"),
            "description_es",
        ),
        "frictions": _string_list(
            data.get("frictions_es"),
            "frictions_es",
            2,
        ),
    }


def _run_validated_stage(
    *,
    stage_name: str,
    prompt: str,
    max_tokens: int,
    generator: StageGenerator,
    parser: Callable[[str], Any],
) -> tuple[Any, str, bool]:
    """Run one stage and retry once using the same clean stage context."""

    raw_response = generator(stage_name, prompt, max_tokens)

    try:
        return parser(raw_response), raw_response, False
    except StageFormatError as first_error:
        repair_prompt = (
            f"{prompt}\n\n"
            "FORMAT_REPAIR:\n"
            f"The previous response failed validation: {first_error}\n"
            "Return a new answer from scratch. Output only the exact JSON "
            "object required by the stage system instructions."
        )
        repaired = generator(stage_name, repair_prompt, max_tokens)

        try:
            return parser(repaired), repaired, True
        except StageFormatError as second_error:
            raise StageFormatError(
                f"Stage {stage_name} failed after one retry: {second_error}"
            ) from second_error


def analyze_parsed_weapon(
    parsed_weapon: Mapping[str, Any],
    generator: StageGenerator,
    *,
    include_debug: bool = False,
) -> dict[str, Any]:
    """Run behavior, job, improvement, and comfort with clean contexts."""

    if not isinstance(parsed_weapon, Mapping):
        raise TypeError("parsed_weapon must be a Mapping.")

    warnings: list[str] = []
    debug: dict[str, Any] = {"prompts": {}, "raw_responses": {}}

    behavior_prompt = build_behavior_prompt(parsed_weapon)
    behavior, behavior_raw, retried = _run_validated_stage(
        stage_name="behavior",
        prompt=behavior_prompt,
        max_tokens=BEHAVIOR_MAX_TOKENS,
        generator=generator,
        parser=parse_behavior_response,
    )
    if retried:
        warnings.append("Behavior stage required one retry.")

    job_prompt = build_job_prompt(parsed_weapon, behavior)
    job, job_raw, retried = _run_validated_stage(
        stage_name="job",
        prompt=job_prompt,
        max_tokens=JOB_MAX_TOKENS,
        generator=generator,
        parser=parse_job_response,
    )
    if retried:
        warnings.append("Job stage required one retry.")

    allowed_parameters = available_improvement_parameters(parsed_weapon)
    improvement_prompt = build_improvement_prompt(
        parsed_weapon,
        behavior,
        job,
    )
    improvements, improvements_raw, retried = _run_validated_stage(
        stage_name="improvements",
        prompt=improvement_prompt,
        max_tokens=IMPROVEMENT_MAX_TOKENS,
        generator=generator,
        parser=lambda value: parse_improvement_response(
            value,
            allowed_parameters,
        ),
    )
    if retried:
        warnings.append("Improvement stage required one retry.")

    comfort_prompt = build_comfort_prompt(parsed_weapon)
    comfort, comfort_raw, retried = _run_validated_stage(
        stage_name="comfort",
        prompt=comfort_prompt,
        max_tokens=COMFORT_MAX_TOKENS,
        generator=generator,
        parser=parse_comfort_response,
    )
    if retried:
        warnings.append("Comfort stage required one retry.")

    state: dict[str, Any] = {
        "analysis_version": ANALYSIS_VERSION,
        "weapon_category": parsed_weapon.get("weapon_category"),
        "behavior": behavior,
        "job": job,
        "improvements": improvements,
        "comfort": comfort,
        "warnings": warnings,
    }

    if include_debug:
        debug["prompts"] = {
            "behavior": behavior_prompt,
            "job": job_prompt,
            "improvements": improvement_prompt,
            "comfort": comfort_prompt,
        }
        debug["raw_responses"] = {
            "behavior": behavior_raw,
            "job": job_raw,
            "improvements": improvements_raw,
            "comfort": comfort_raw,
        }
        state["debug"] = debug

    return state


def format_analysis(analysis: Mapping[str, Any]) -> str:
    """Format the validated state without asking the model to rewrite it."""

    behavior = _mapping(analysis.get("behavior"), "behavior")
    job = _mapping(analysis.get("job"), "job")
    comfort = _mapping(analysis.get("comfort"), "comfort")
    improvements = analysis.get("improvements") or []

    lines = [
        "¿Qué hace el arma?",
        str(behavior.get("summary") or "No determinado."),
    ]

    traits = behavior.get("traits") or []
    if traits:
        lines.append("Rasgos:")
        lines.extend(f"- {item}" for item in traits)

    lines.extend(
        [
            "",
            "Trabajo sugerido",
            str(job.get("name") or "Uso general"),
            str(job.get("reason") or ""),
            "",
            "Aspectos que conviene mejorar",
        ]
    )

    if isinstance(improvements, list) and improvements:
        for item in improvements:
            if not isinstance(item, Mapping):
                continue
            lines.append(
                f"- {item.get('parameter')}: {item.get('reason')} "
                f"({item.get('direction')})"
            )
    else:
        lines.append("- Ninguna mejora determinada.")

    lines.extend(
        [
            "",
            "Comodidad",
            str(comfort.get("rating") or "No determinada"),
            str(comfort.get("description") or ""),
        ]
    )

    frictions = comfort.get("frictions") or []
    if frictions:
        lines.append("Fricciones:")
        lines.extend(f"- {item}" for item in frictions)

    return "\n".join(lines).strip()
