# modules/ai.py

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from llama_cpp import Llama

from modules.logger import get_logger, log_exception
from modules.prompt_builder import (
    COMFORT_KEYS,
    IMPROVEMENT_DIRECTIONS,
    JOB_KEYS,
    SYSTEM_PROMPT,
    available_improvement_parameters,
    build_weapon_prompt,
)
from modules.weapon_pipeline import prepare_weapon_analysis


MODEL_ID = "Qwen/Qwen2.5-3B-Instruct-GGUF"
MODEL_FILE = "Qwen2.5-3B-Instruct-Q4_K_M.gguf"
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / MODEL_FILE

CONTEXT_SIZE = 4096
MAX_TOKENS = 650
MAX_REPAIR_ATTEMPTS = 1

logger = get_logger(__name__)

_llm: Any | None = None
_model_lock = Lock()
_inference_lock = Lock()


FRICTION_PARAMETERS = {
    "reload_time",
    "magazine_size",
    "ammo_capacity",
    "ammo_pickup",
    "beam_range",
    "punch_through",
    "accuracy",
    "recoil",
    "projectile_speed",
    "charge_time",
    "attack_speed",
    "heavy_attack_wind_up",
}

REINFORCEMENT_PARAMETERS = {
    "critical_chance",
    "critical_multiplier",
    "status_chance",
    "base_damage",
    "fire_rate",
    "multishot",
    "magazine_size",
    "ammo_capacity",
    "ammo_pickup",
    "punch_through",
    "beam_range",
    "attack_speed",
    "range",
    "heavy_attack_damage",
}

ABSENT_FIELD_TERMS: dict[str, tuple[str, ...]] = {
    "accuracy": (
        "accuracy",
        "precisión",
        "puntería",
        "inexactitud",
    ),
    "recoil": (
        "recoil",
        "retroceso",
    ),
    "projectile_speed": (
        "projectile speed",
        "velocidad del proyectil",
        "viaje del proyectil",
        "trayectoria del proyectil",
    ),
    "charge_time": (
        "charge time",
        "charging",
        "tiempo de carga",
        "cargar el disparo",
        "disparo cargado",
    ),
    "heavy_attack_wind_up": (
        "wind-up",
        "heavy wind-up",
        "preparación del ataque pesado",
        "tiempo de preparación",
    ),
}

FIRE_RATE_ONLY_COMFORT_TERMS = (
    "alta frecuencia de disparos",
    "alta cadencia",
    "cadencia alta",
    "high fire rate",
    "high firing frequency",
)

CHARGE_BEHAVIOR_TERMS = (
    "charge behavior",
    "charge-based",
    "charging weapon",
    "arma de carga",
    "comportamiento de carga",
    "cargar el arma",
    "carga del disparo",
)


class ModelResponseError(RuntimeError):
    """Raised when the local model response is invalid."""


def get_model() -> Any:
    """Load the GGUF model lazily and reuse one instance."""
    global _llm

    if _llm is not None:
        return _llm

    with _model_lock:
        if _llm is not None:
            return _llm

        if not MODEL_PATH.is_file():
            logger.error(
                "Model file was not found | path=%s",
                MODEL_PATH,
            )
            raise FileNotFoundError(
                f"Model not found: {MODEL_PATH}"
            )

        try:
            from llama_cpp import Llama
        except ImportError as error:
            log_exception(
                logger,
                "llama-cpp-python is not installed.",
                error,
            )
            raise RuntimeError(
                "llama-cpp-python is not installed "
                "in this environment."
            ) from error

        logger.info(
            "Loading local model | model=%s | context_size=%d",
            MODEL_FILE,
            CONTEXT_SIZE,
        )

        _llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=CONTEXT_SIZE,
            seed=42,
            verbose=False,
        )

        logger.info(
            "Local model loaded successfully."
        )

    return _llm


def unload_model() -> None:
    """Release the model reference for tests or shutdown."""
    global _llm

    with _model_lock:
        _llm = None

    logger.info(
        "Local model reference released."
    )


def _extract_content(
    response: Mapping[str, Any],
) -> str:
    choices = response.get("choices")

    if not isinstance(choices, Sequence) or isinstance(
        choices,
        (str, bytes),
    ):
        raise ModelResponseError(
            "The model did not return a choices list."
        )

    if not choices:
        raise ModelResponseError(
            "The model returned no answer."
        )

    first_choice = choices[0]

    if not isinstance(first_choice, Mapping):
        raise ModelResponseError(
            "The model response has an invalid "
            "choice format."
        )

    message = first_choice.get("message")

    if not isinstance(message, Mapping):
        raise ModelResponseError(
            "The model response does not contain "
            "a message."
        )

    content = str(
        message.get("content") or ""
    ).strip()

    if not content:
        raise ModelResponseError(
            "The model returned an empty answer."
        )

    return content


def _strip_code_fence(text: str) -> str:
    value = str(text or "").strip()

    if value.startswith("```json"):
        value = value[7:]
    elif value.startswith("```"):
        value = value[3:]

    if value.endswith("```"):
        value = value[:-3]

    return value.strip()


def _required_text(
    value: Any,
    field: str,
) -> str:
    text = str(value or "").strip()

    if not text:
        raise ModelResponseError(
            f"Missing or empty text field: {field}."
        )

    return text


def _string_list(
    value: Any,
    field: str,
    *,
    maximum: int,
) -> list[str]:
    if not isinstance(value, list):
        raise ModelResponseError(
            f"{field} must be a list."
        )

    result: list[str] = []

    for item in value:
        text = str(item or "").strip()

        if text:
            result.append(text)

    if len(result) > maximum:
        raise ModelResponseError(
            f"{field} cannot contain more than "
            f"{maximum} items."
        )

    return result


def _parse_improvements(
    value: Any,
    allowed_parameters: set[str],
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ModelResponseError(
            "improvement_priorities must be "
            "a non-empty list."
        )

    if len(value) > 3:
        raise ModelResponseError(
            "improvement_priorities cannot contain "
            "more than 3 items."
        )

    results: list[dict[str, str]] = []

    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ModelResponseError(
                f"improvement_priorities[{index}] "
                "must be an object."
            )

        parameter = str(
            item.get("parameter") or ""
        ).strip()

        direction = str(
            item.get("direction") or ""
        ).strip()

        reason = _required_text(
            item.get("reason_es"),
            (
                "improvement_priorities"
                f"[{index}].reason_es"
            ),
        )

        if parameter not in allowed_parameters:
            raise ModelResponseError(
                "Improvement parameter is not "
                f"allowed: {parameter}."
            )

        if direction not in IMPROVEMENT_DIRECTIONS:
            raise ModelResponseError(
                "Invalid improvement direction: "
                f"{direction}."
            )

        if parameter == "none":
            if direction != "none":
                raise ModelResponseError(
                    "Parameter none requires "
                    "direction none."
                )

        elif direction == "none":
            raise ModelResponseError(
                "Direction none is only valid "
                "with parameter none."
            )

        results.append(
            {
                "parameter": parameter,
                "direction": direction,
                "reason_es": reason,
            }
        )

    none_items = [
        item
        for item in results
        if item["parameter"] == "none"
    ]

    if none_items and len(results) != 1:
        raise ModelResponseError(
            "Parameter none must be the only "
            "improvement."
        )

    return results


def _parse_comfort(
    value: Any,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ModelResponseError(
            "comfort must be an object."
        )

    rating = str(
        value.get("rating") or ""
    ).strip()

    if rating not in COMFORT_KEYS:
        raise ModelResponseError(
            f"Invalid comfort rating: {rating}."
        )

    reason = _required_text(
        value.get("reason_es"),
        "comfort.reason_es",
    )

    return {
        "rating": rating,
        "reason_es": reason,
    }


def _parse_model_json(
    text: str,
    *,
    allowed_parameters: tuple[str, ...],
) -> dict[str, Any]:
    cleaned = _strip_code_fence(text)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ModelResponseError(
            "The model response is not valid JSON."
        ) from error

    if not isinstance(data, dict):
        raise ModelResponseError(
            "The model JSON root must be an object."
        )

    required_fields = {
        "behavior_summary_es",
        "primary_job",
        "job_reason_es",
        "strengths_es",
        "limitations_es",
        "improvement_priorities",
        "comfort",
    }

    missing = sorted(
        required_fields - set(data)
    )

    if missing:
        raise ModelResponseError(
            "The model response is missing fields: "
            + ", ".join(missing)
        )

    unexpected = sorted(
        set(data) - required_fields
    )

    if unexpected:
        raise ModelResponseError(
            "The model response contains "
            "unexpected fields: "
            + ", ".join(unexpected)
        )

    primary_job = str(
        data.get("primary_job") or ""
    ).strip()

    if primary_job not in JOB_KEYS:
        raise ModelResponseError(
            f"Invalid primary_job: {primary_job}."
        )

    allowed = set(allowed_parameters)
    allowed.add("none")

    strengths = _string_list(
        data.get("strengths_es"),
        "strengths_es",
        maximum=3,
    )

    limitations = _string_list(
        data.get("limitations_es"),
        "limitations_es",
        maximum=3,
    )

    if not strengths and not limitations:
        raise ModelResponseError(
            "At least one strength or limitation "
            "must be provided."
        )

    return {
        "behavior_summary_es": _required_text(
            data.get("behavior_summary_es"),
            "behavior_summary_es",
        ),
        "primary_job": primary_job,
        "job_reason_es": _required_text(
            data.get("job_reason_es"),
            "job_reason_es",
        ),
        "strengths_es": strengths,
        "limitations_es": limitations,
        "improvement_priorities": (
            _parse_improvements(
                data.get(
                    "improvement_priorities"
                ),
                allowed,
            )
        ),
        "comfort": _parse_comfort(
            data.get("comfort")
        ),
    }


def _nested_mapping(
    value: Any,
) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value

    return {}


def _normalized_text(
    value: Any,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower(),
    )


def _collect_analysis_text(
    analysis: Mapping[str, Any],
) -> str:
    parts: list[Any] = [
        analysis.get("behavior_summary_es"),
        analysis.get("job_reason_es"),
    ]

    strengths = analysis.get("strengths_es")
    if isinstance(strengths, list):
        parts.extend(strengths)

    limitations = analysis.get("limitations_es")
    if isinstance(limitations, list):
        parts.extend(limitations)

    improvements = analysis.get(
        "improvement_priorities"
    )

    if isinstance(improvements, list):
        for item in improvements:
            if isinstance(item, Mapping):
                parts.append(
                    item.get("reason_es")
                )

    comfort = analysis.get("comfort")

    if isinstance(comfort, Mapping):
        parts.append(
            comfort.get("reason_es")
        )

    return _normalized_text(
        " ".join(
            str(part or "")
            for part in parts
        )
    )


def _available_operational_fields(
    weapon_data: Mapping[str, Any],
) -> set[str]:
    available: set[str] = set()

    shared_stats = _nested_mapping(
        weapon_data.get("shared_stats")
    )
    root_stats = _nested_mapping(
        weapon_data.get("root_stats")
    )

    for field, value in shared_stats.items():
        if value not in (None, "", [], {}):
            available.add(str(field))

    for field, value in root_stats.items():
        if value not in (None, "", [], {}):
            available.add(str(field))

    attack_modes = weapon_data.get(
        "attack_modes"
    )

    if isinstance(attack_modes, list):
        for mode in attack_modes:
            if not isinstance(mode, Mapping):
                continue

            for field, value in mode.items():
                if value not in (None, "", [], {}):
                    available.add(str(field))

    if "trigger_type" in available:
        available.add("firing_mode")

    if "fire_rate" in available:
        category = _nested_mapping(
            weapon_data.get("classification")
        ).get("category")

        if category in {
            "melee",
            "archmelee",
            "drifter_melee",
        }:
            available.add("attack_speed")

    if "range" in available:
        category = _nested_mapping(
            weapon_data.get("classification")
        ).get("category")

        if category in {
            "melee",
            "archmelee",
            "drifter_melee",
        }:
            available.add("melee_range")

    return available


def _infer_primary_job_hint(
    interpretation: Mapping[str, Any],
) -> str | None:
    mechanic = _nested_mapping(
        interpretation.get("mechanic_profile")
    )

    target_profile = interpretation.get(
        "target_profile"
    )

    damage_behavior = interpretation.get(
        "damage_behavior"
    )

    attack_behavior = interpretation.get(
        "attack_behavior"
    )

    has_area_delivery = (
        mechanic.get("has_area_delivery") is True
        or mechanic.get("has_radial_component") is True
        or interpretation.get(
            "has_structured_multi_target_evidence"
        ) is True
    )

    if (
        target_profile == "multi_target_capable"
        and has_area_delivery
    ):
        return "group_clear"

    if damage_behavior == "heavy_attacks":
        return "heavy_attacks"

    if (
        damage_behavior == "focused"
        and target_profile in {
            "single_target",
            "close_range",
        }
    ):
        return "focused_damage"

    if (
        attack_behavior == "charge"
        and target_profile == "single_target"
    ):
        return "focused_damage"

    return None


def _validate_improvement_semantics(
    analysis: Mapping[str, Any],
) -> None:
    improvements = analysis.get(
        "improvement_priorities"
    )

    if not isinstance(improvements, list):
        return

    seen_parameters: set[str] = set()

    for index, item in enumerate(improvements):
        if not isinstance(item, Mapping):
            continue

        parameter = str(
            item.get("parameter") or ""
        )

        direction = str(
            item.get("direction") or ""
        )

        if parameter in seen_parameters:
            raise ModelResponseError(
                "Duplicate improvement parameter: "
                f"{parameter}."
            )

        seen_parameters.add(parameter)

        if parameter == "none":
            continue

        if (
            direction == "correct_friction"
            and parameter
            not in FRICTION_PARAMETERS
        ):
            raise ModelResponseError(
                f"{parameter} cannot use "
                "correct_friction because it does "
                "not represent an operational "
                "friction parameter."
            )

        if (
            direction == "reinforce"
            and parameter
            not in REINFORCEMENT_PARAMETERS
        ):
            raise ModelResponseError(
                f"{parameter} cannot use reinforce "
                "under the current semantic rules."
            )

        reason = _normalized_text(
            item.get("reason_es")
        )

        if (
            parameter == "status_chance"
            and direction == "correct_friction"
        ):
            raise ModelResponseError(
                "status_chance cannot correct "
                "operational friction."
            )

        if (
            parameter == "critical_multiplier"
            and "recarga" in reason
        ):
            raise ModelResponseError(
                "critical_multiplier cannot be "
                "justified as a reload correction."
            )

        if (
            parameter == "reload_time"
            and direction != "correct_friction"
        ):
            raise ModelResponseError(
                "reload_time must use "
                "correct_friction."
            )


def _validate_absent_field_references(
    analysis: Mapping[str, Any],
    *,
    weapon_data: Mapping[str, Any],
) -> None:
    available = _available_operational_fields(
        weapon_data
    )

    combined_text = _collect_analysis_text(
        analysis
    )

    for field, terms in ABSENT_FIELD_TERMS.items():
        if field in available:
            continue

        matched = [
            term
            for term in terms
            if term in combined_text
        ]

        if matched:
            raise ModelResponseError(
                "The response references absent "
                f"field {field}: {matched[0]}."
            )


def _validate_beam_semantics(
    analysis: Mapping[str, Any],
    *,
    interpretation: Mapping[str, Any],
) -> None:
    if (
        interpretation.get("damage_delivery")
        != "beam"
    ):
        return

    if (
        interpretation.get("attack_behavior")
        != "continuous"
    ):
        return

    combined_text = _collect_analysis_text(
        analysis
    )

    for term in CHARGE_BEHAVIOR_TERMS:
        if term in combined_text:
            raise ModelResponseError(
                "A continuous beam cannot be "
                "described as charge behavior "
                "without explicit charge data."
            )


def _has_demanding_evidence(
    weapon_data: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> bool:
    if (
        interpretation.get("reload_friction")
        == "high"
    ):
        return True

    if (
        interpretation.get("handling_friction")
        == "high"
    ):
        return True

    shared_stats = _nested_mapping(
        weapon_data.get("shared_stats")
    )

    operational_values = (
        shared_stats.get("accuracy"),
        shared_stats.get("recoil"),
        shared_stats.get("heavy_attack_wind_up"),
    )

    if any(
        value not in (None, "")
        for value in operational_values
    ):
        return True

    attack_modes = weapon_data.get(
        "attack_modes"
    )

    if isinstance(attack_modes, list):
        for mode in attack_modes:
            if not isinstance(mode, Mapping):
                continue

            if mode.get("trigger_type") == "charge":
                return True

    return False


def _validate_comfort_semantics(
    analysis: Mapping[str, Any],
    *,
    weapon_data: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> None:
    comfort = analysis.get("comfort")

    if not isinstance(comfort, Mapping):
        return

    rating = comfort.get("rating")
    reason = _normalized_text(
        comfort.get("reason_es")
    )

    if rating == "demanding":
        if not _has_demanding_evidence(
            weapon_data,
            interpretation,
        ):
            raise ModelResponseError(
                "Comfort rating demanding lacks "
                "supplied operational evidence."
            )

        if any(
            term in reason
            for term in FIRE_RATE_ONLY_COMFORT_TERMS
        ):
            other_evidence_terms = (
                "recarga",
                "reload",
                "retroceso",
                "recoil",
                "precisión",
                "accuracy",
                "proyectil",
                "projectile",
                "alcance",
                "range",
                "wind-up",
                "preparación",
            )

            if not any(
                term in reason
                for term in other_evidence_terms
            ):
                raise ModelResponseError(
                    "High fire rate alone cannot "
                    "justify demanding comfort."
                )


def _validate_primary_job(
    analysis: Mapping[str, Any],
    *,
    interpretation: Mapping[str, Any],
) -> None:
    hint = _infer_primary_job_hint(
        interpretation
    )

    if hint is None:
        return

    actual = analysis.get("primary_job")

    if actual != hint:
        raise ModelResponseError(
            "Unsupported primary_job. "
            f"Expected {hint} from deterministic "
            f"evidence, received {actual}."
        )


def _validate_area_semantics(
    analysis: Mapping[str, Any],
    *,
    interpretation: Mapping[str, Any],
) -> None:
    mechanic = _nested_mapping(
        interpretation.get("mechanic_profile")
    )

    has_area_evidence = (
        mechanic.get("has_area_delivery") is True
        or mechanic.get("has_radial_component") is True
        or interpretation.get(
            "has_structured_multi_target_evidence"
        ) is True
    )

    combined_text = _collect_analysis_text(
        analysis
    )

    unsupported_area_terms = (
        "explosión",
        "explosive",
        "radial",
    )

    if has_area_evidence:
        return

    for term in unsupported_area_terms:
        if term in combined_text:
            raise ModelResponseError(
                "The response claims area or radial "
                "behavior without structured evidence."
            )


def _validate_semantics(
    analysis: Mapping[str, Any],
    *,
    weapon_data: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> None:
    _validate_primary_job(
        analysis,
        interpretation=interpretation,
    )

    _validate_improvement_semantics(
        analysis
    )

    _validate_absent_field_references(
        analysis,
        weapon_data=weapon_data,
    )

    _validate_beam_semantics(
        analysis,
        interpretation=interpretation,
    )

    _validate_comfort_semantics(
        analysis,
        weapon_data=weapon_data,
        interpretation=interpretation,
    )

    _validate_area_semantics(
        analysis,
        interpretation=interpretation,
    )


def _create_completion(
    messages: list[dict[str, str]],
) -> str:
    with _inference_lock:
        response = (
            get_model().create_chat_completion(
                messages=messages,
                temperature=0.05,
                top_p=0.90,
                repeat_penalty=1.08,
                max_tokens=MAX_TOKENS,
                response_format={
                    "type": "json_object"
                },
            )
        )

    if not isinstance(response, Mapping):
        raise ModelResponseError(
            "The model returned an invalid "
            "response container."
        )

    return _extract_content(response)


def _build_repair_prompt(
    original_prompt: str,
    previous_response: str,
    validation_error: Exception,
    allowed_parameters: tuple[str, ...],
    interpretation: Mapping[str, Any],
) -> str:
    primary_job_hint = (
        _infer_primary_job_hint(
            interpretation
        )
    )

    repair_constraints = {
        "primary_job_hint": primary_job_hint,
        "allowed_improvement_parameters": [
            *allowed_parameters,
            "none",
        ],
        "validation_error": str(
            validation_error
        ),
    }

    return (
        f"{original_prompt}\n\n"
        "REPAIR_REQUIRED:\n"
        "The previous response was valid enough "
        "to inspect but failed schema or semantic "
        "validation.\n\n"
        "PREVIOUS_INVALID_RESPONSE:\n"
        f"{previous_response}\n\n"
        "REPAIR_CONSTRAINTS:\n"
        f"{json.dumps(
            repair_constraints,
            ensure_ascii=False,
            indent=2,
        )}\n\n"
        "Return a completely corrected JSON object.\n"
        "Do not explain the repair.\n"
        "Do not use Markdown.\n"
        "Do not repeat unsupported conclusions.\n"
        "Use exactly the schema required by the "
        "system prompt."
    )


def _validate_generated_content(
    raw_content: str,
    *,
    allowed_parameters: tuple[str, ...],
    weapon_data: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> dict[str, Any]:
    parsed = _parse_model_json(
        raw_content,
        allowed_parameters=allowed_parameters,
    )

    _validate_semantics(
        parsed,
        weapon_data=weapon_data,
        interpretation=interpretation,
    )

    return parsed


def generate_analysis(
    prompt: str,
    *,
    allowed_parameters: tuple[str, ...],
    weapon_data: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> str:
    """
    Run local inference and validate structure and semantics.

    One repair inference is attempted when the first response fails.
    """
    clean_prompt = str(
        prompt or ""
    ).strip()

    if not clean_prompt:
        raise ValueError(
            "Prompt cannot be empty."
        )

    if not isinstance(
        weapon_data,
        Mapping,
    ):
        raise TypeError(
            "weapon_data must be a Mapping."
        )

    if not isinstance(
        interpretation,
        Mapping,
    ):
        raise TypeError(
            "interpretation must be a Mapping."
        )

    job_hint = _infer_primary_job_hint(
        interpretation
    )

    logger.info(
        "Starting model inference "
        "| prompt_characters=%d "
        "| allowed_parameters=%s "
        "| primary_job_hint=%s",
        len(clean_prompt),
        ",".join(
            allowed_parameters
        ) or "none",
        job_hint or "none",
    )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": clean_prompt,
        },
    ]

    try:
        raw_content = _create_completion(
            messages
        )

        try:
            parsed = (
                _validate_generated_content(
                    raw_content,
                    allowed_parameters=(
                        allowed_parameters
                    ),
                    weapon_data=weapon_data,
                    interpretation=(
                        interpretation
                    ),
                )
            )

        except ModelResponseError as first_error:
            logger.warning(
                "Initial model response failed "
                "validation | error=%s",
                first_error,
            )

            if MAX_REPAIR_ATTEMPTS < 1:
                raise

            repair_prompt = _build_repair_prompt(
                clean_prompt,
                raw_content,
                first_error,
                allowed_parameters,
                interpretation,
            )

            repair_messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": repair_prompt,
                },
            ]

            repaired_content = (
                _create_completion(
                    repair_messages
                )
            )

            parsed = (
                _validate_generated_content(
                    repaired_content,
                    allowed_parameters=(
                        allowed_parameters
                    ),
                    weapon_data=weapon_data,
                    interpretation=(
                        interpretation
                    ),
                )
            )

            logger.info(
                "Model response repaired "
                "successfully."
            )

        normalized = json.dumps(
            parsed,
            ensure_ascii=False,
            indent=2,
        )

        logger.info(
            "Model inference completed "
            "| response_characters=%d",
            len(normalized),
        )

        return normalized

    except Exception as error:
        log_exception(
            logger,
            "Model inference failed.",
            error,
            prompt_characters=(
                len(clean_prompt)
            ),
            allowed_parameters=(
                allowed_parameters
            ),
            primary_job_hint=job_hint,
        )
        raise


def analyze_weapon_state(
    normalized_weapon_data: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Return deterministic RAG state and validated analysis.
    """
    if not isinstance(
        normalized_weapon_data,
        Mapping,
    ):
        raise TypeError(
            "normalized_weapon_data must be a Mapping."
        )

    if not normalized_weapon_data:
        raise ValueError(
            "No weapon data was supplied."
        )

    weapon_dict = dict(
        normalized_weapon_data
    )

    prepared = prepare_weapon_analysis(
        weapon_dict
    )

    weapon_data = prepared[
        "weapon_data"
    ]

    interpretation = prepared[
        "interpretation"
    ]

    allowed_parameters = (
        available_improvement_parameters(
            weapon_data
        )
    )

    prompt = build_weapon_prompt(
        weapon_data=weapon_data,
        analysis_context=prepared[
            "analysis_context"
        ],
    )

    raw_analysis = generate_analysis(
        prompt,
        allowed_parameters=(
            allowed_parameters
        ),
        weapon_data=weapon_data,
        interpretation=interpretation,
    )

    analysis = json.loads(
        raw_analysis
    )

    return {
        **prepared,
        "primary_job_hint": (
            _infer_primary_job_hint(
                interpretation
            )
        ),
        "allowed_improvement_parameters": list(
            allowed_parameters
        ),
        "prompt": prompt,
        "analysis": analysis,
    }


def _format_list(
    values: Any,
    empty_message: str,
) -> list[str]:
    if not isinstance(values, list):
        return [
            f"- {empty_message}"
        ]

    items = [
        str(value).strip()
        for value in values
        if str(value).strip()
    ]

    if not items:
        return [
            f"- {empty_message}"
        ]

    return [
        f"- {item}"
        for item in items
    ]


def _format_improvements(
    values: Any,
) -> list[str]:
    if not isinstance(
        values,
        list,
    ) or not values:
        return [
            "- No se identificó una "
            "prioridad dominante."
        ]

    lines: list[str] = []

    for item in values:
        if not isinstance(
            item,
            Mapping,
        ):
            continue

        parameter = str(
            item.get("parameter")
            or "none"
        ).strip()

        direction = str(
            item.get("direction")
            or "none"
        ).strip()

        reason = str(
            item.get("reason_es")
            or ""
        ).strip()

        if parameter == "none":
            lines.append(
                "- Sin mejora dominante: "
                f"{reason}"
            )
            continue

        lines.append(
            f"- {parameter}: {reason} "
            f"({direction})"
        )

    return lines or [
        "- No se identificó una "
        "prioridad dominante."
    ]


def format_analysis(
    analysis: Mapping[str, Any],
) -> str:
    """Format validated JSON for the text interface."""
    comfort = analysis.get(
        "comfort"
    )

    if not isinstance(
        comfort,
        Mapping,
    ):
        comfort = {}

    lines = [
        "¿Qué hace el arma?",
        str(
            analysis.get(
                "behavior_summary_es"
            )
            or "No determinado."
        ),
        "",
        "Trabajo sugerido",
        str(
            analysis.get(
                "primary_job"
            )
            or "general_use"
        ),
        str(
            analysis.get(
                "job_reason_es"
            )
            or ""
        ),
        "",
        "Fortalezas",
        *_format_list(
            analysis.get(
                "strengths_es"
            ),
            (
                "No se identificaron "
                "fortalezas dominantes."
            ),
        ),
        "",
        "Limitaciones",
        *_format_list(
            analysis.get(
                "limitations_es"
            ),
            (
                "No se identificaron "
                "limitaciones dominantes."
            ),
        ),
        "",
        "Prioridades de mejora",
        *_format_improvements(
            analysis.get(
                "improvement_priorities"
            )
        ),
        "",
        "Comodidad",
        str(
            comfort.get("rating")
            or "undetermined"
        ),
        str(
            comfort.get("reason_es")
            or ""
        ),
    ]

    return "\n".join(
        lines
    ).strip()


def analyze_weapon(
    normalized_weapon_data: Mapping[str, Any],
) -> str:
    """Compatibility API for Flask and scripts."""
    state = analyze_weapon_state(
        normalized_weapon_data
    )

    return format_analysis(
        state["analysis"]
    )


def _load_json(
    path: Path,
) -> Mapping[str, Any]:
    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except OSError as error:
        raise RuntimeError(
            f"Could not read {path}."
        ) from error

    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{path} does not contain "
            "valid JSON."
        ) from error

    if not isinstance(
        data,
        Mapping,
    ):
        raise RuntimeError(
            "The JSON root must be "
            "an object."
        )

    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Test the local RAG Warframe "
            "weapon analyzer."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path(
            "data/normalized/weapon_test.json"
        ),
        help=(
            "JSON file containing one normalized "
            "weapon entry."
        ),
    )

    parser.add_argument(
        "--show-state",
        action="store_true",
        help=(
            "Show deterministic "
            "interpretation and "
            "retrieved concepts."
        ),
    )

    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help=(
            "Show the final RAG prompt."
        ),
    )

    parser.add_argument(
        "--no-ai",
        action="store_true",
        help=(
            "Prepare the RAG context "
            "without loading the model."
        ),
    )

    args = parser.parse_args()

    raw_data = _load_json(
        args.input
    )

    prepared = prepare_weapon_analysis(
        dict(raw_data)
    )

    weapon_data = prepared[
        "weapon_data"
    ]

    interpretation = prepared[
        "interpretation"
    ]

    allowed_parameters = (
        available_improvement_parameters(
            weapon_data
        )
    )

    prompt = build_weapon_prompt(
        weapon_data=weapon_data,
        analysis_context=prepared[
            "analysis_context"
        ],
    )

    if args.show_state:
        visible_state = {
            "interpretation": (
                interpretation
            ),
            "primary_job_hint": (
                _infer_primary_job_hint(
                    interpretation
                )
            ),
            "activated_concepts": (
                prepared[
                    "activated_concepts"
                ]
            ),
            "retrieved_knowledge": (
                prepared[
                    "retrieved_knowledge"
                ]
            ),
            "allowed_improvement_parameters": list(
                allowed_parameters
            ),
        }

        print(
            "\n--- RAG STATE ---\n"
        )

        print(
            json.dumps(
                visible_state,
                ensure_ascii=False,
                indent=2,
            )
        )

    if args.show_prompt:
        print(
            "\n--- FINAL PROMPT ---\n"
        )
        print(prompt)

    if args.no_ai:
        return

    analysis_json = generate_analysis(
        prompt,
        allowed_parameters=(
            allowed_parameters
        ),
        weapon_data=weapon_data,
        interpretation=interpretation,
    )

    analysis = json.loads(
        analysis_json
    )

    print(
        "\n--- ANALYSIS ---\n"
    )

    print(
        format_analysis(
            analysis
        )
    )


if __name__ == "__main__":
    main()