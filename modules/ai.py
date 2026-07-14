
# modules/ai.py

from __future__ import annotations

import argparse
import json
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
from modules.weapon_interpreter import interpret_weapon
from modules.weapon_parser import parse_weapon_data
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


class ModelResponseError(RuntimeError):
    """Raised when the local model response is empty or malformed."""


def get_model() -> Any:
    """Load the GGUF model lazily and reuse one instance."""
    global _llm

    if _llm is not None:
        return _llm

    with _model_lock:
        if _llm is not None:
            return _llm

        if not MODEL_PATH.is_file():
            logger.error("Model file was not found | path=%s", MODEL_PATH)
            raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

        try:
            from llama_cpp import Llama
        except ImportError as error:
            log_exception(
                logger,
                "llama-cpp-python is not installed.",
                error,
            )
            raise RuntimeError(
                "llama-cpp-python is not installed in this environment."
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

        logger.info("Local model loaded successfully.")

    return _llm


def unload_model() -> None:
    """Release the model reference for tests or controlled shutdown."""
    global _llm

    with _model_lock:
        _llm = None

    logger.info("Local model reference released.")


def _extract_content(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")

    if not isinstance(choices, Sequence) or isinstance(
        choices,
        (str, bytes),
    ):
        raise ModelResponseError("The model did not return a choices list.")

    if not choices:
        raise ModelResponseError("The model returned no answer.")

    first_choice = choices[0]

    if not isinstance(first_choice, Mapping):
        raise ModelResponseError(
            "The model response has an invalid choice format."
        )

    message = first_choice.get("message")

    if not isinstance(message, Mapping):
        raise ModelResponseError(
            "The model response does not contain a message."
        )

    content = str(message.get("content") or "").strip()

    if not content:
        raise ModelResponseError("The model returned an empty answer.")

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
        raise ModelResponseError(f"{field} must be a list.")

    result: list[str] = []

    for item in value:
        text = str(item or "").strip()

        if text:
            result.append(text)

    if len(result) > maximum:
        raise ModelResponseError(
            f"{field} cannot contain more than {maximum} items."
        )

    return result


def _parse_improvements(
    value: Any,
    allowed_parameters: set[str],
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ModelResponseError(
            "improvement_priorities must be a non-empty list."
        )

    if len(value) > 3:
        raise ModelResponseError(
            "improvement_priorities cannot contain more than 3 items."
        )

    results: list[dict[str, str]] = []

    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ModelResponseError(
                f"improvement_priorities[{index}] must be an object."
            )

        parameter = str(item.get("parameter") or "").strip()
        direction = str(item.get("direction") or "").strip()
        reason = _required_text(
            item.get("reason_es"),
            f"improvement_priorities[{index}].reason_es",
        )

        if parameter not in allowed_parameters:
            raise ModelResponseError(
                f"Improvement parameter is not allowed: {parameter}."
            )

        if direction not in IMPROVEMENT_DIRECTIONS:
            raise ModelResponseError(
                f"Invalid improvement direction: {direction}."
            )

        if parameter == "none":
            if direction != "none":
                raise ModelResponseError(
                    "Parameter none requires direction none."
                )
        elif direction == "none":
            raise ModelResponseError(
                "Direction none is only valid with parameter none."
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
            "Parameter none must be the only improvement."
        )

    return results


def _parse_comfort(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ModelResponseError("comfort must be an object.")

    rating = str(value.get("rating") or "").strip()

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

    missing = sorted(required_fields - set(data))

    if missing:
        raise ModelResponseError(
            "The model response is missing fields: "
            + ", ".join(missing)
        )

    unexpected = sorted(set(data) - required_fields)

    if unexpected:
        raise ModelResponseError(
            "The model response contains unexpected fields: "
            + ", ".join(unexpected)
        )

    primary_job = str(data.get("primary_job") or "").strip()

    if primary_job not in JOB_KEYS:
        raise ModelResponseError(
            f"Invalid primary_job: {primary_job}."
        )

    allowed = set(allowed_parameters)
    allowed.add("none")

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
        "strengths_es": _string_list(
            data.get("strengths_es"),
            "strengths_es",
            maximum=3,
        ),
        "limitations_es": _string_list(
            data.get("limitations_es"),
            "limitations_es",
            maximum=3,
        ),
        "improvement_priorities": _parse_improvements(
            data.get("improvement_priorities"),
            allowed,
        ),
        "comfort": _parse_comfort(data.get("comfort")),
    }


def _create_completion(
    messages: list[dict[str, str]],
) -> str:
    with _inference_lock:
        response = get_model().create_chat_completion(
            messages=messages,
            temperature=0.05,
            top_p=0.90,
            repeat_penalty=1.08,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
        )

    if not isinstance(response, Mapping):
        raise ModelResponseError(
            "The model returned an invalid response container."
        )

    return _extract_content(response)


def _build_repair_prompt(
    original_prompt: str,
    validation_error: Exception,
    allowed_parameters: tuple[str, ...],
) -> str:
    return (
        f"{original_prompt}\n\n"
        "FORMAT_REPAIR:\n"
        "The previous JSON response failed validation.\n"
        f"Validation error: {validation_error}\n"
        "Return a completely new JSON object from scratch.\n"
        "Do not explain the error.\n"
        "Do not use Markdown.\n"
        "Use exactly the schema required by the system prompt.\n"
        "Allowed improvement parameters are:\n"
        f"{json.dumps([*allowed_parameters, 'none'], ensure_ascii=False)}"
    )


def generate_analysis(
    prompt: str,
    *,
    allowed_parameters: tuple[str, ...],
) -> str:
    """
    Run one local inference and validate the complete response schema.

    If the first response fails validation, one repair inference is attempted
    using the same source prompt plus the exact validation error.
    """
    clean_prompt = str(prompt or "").strip()

    if not clean_prompt:
        raise ValueError("Prompt cannot be empty.")

    logger.info(
        "Starting model inference | prompt_characters=%d "
        "| allowed_parameters=%s",
        len(clean_prompt),
        ",".join(allowed_parameters) or "none",
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
        raw_content = _create_completion(messages)

        try:
            parsed = _parse_model_json(
                raw_content,
                allowed_parameters=allowed_parameters,
            )
        except ModelResponseError as first_error:
            logger.warning(
                "Initial model response failed validation "
                "| error=%s",
                first_error,
            )

            if MAX_REPAIR_ATTEMPTS < 1:
                raise

            repair_prompt = _build_repair_prompt(
                clean_prompt,
                first_error,
                allowed_parameters,
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

            repaired_content = _create_completion(repair_messages)

            parsed = _parse_model_json(
                repaired_content,
                allowed_parameters=allowed_parameters,
            )

            logger.info(
                "Model response repaired successfully."
            )

        normalized = json.dumps(
            parsed,
            ensure_ascii=False,
            indent=2,
        )

        logger.info(
            "Model inference completed | response_characters=%d",
            len(normalized),
        )

        return normalized

    except Exception as error:
        log_exception(
            logger,
            "Model inference failed.",
            error,
            prompt_characters=len(clean_prompt),
            allowed_parameters=allowed_parameters,
        )
        raise


def analyze_weapon_state(
    raw_weapon_data: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Return deterministic RAG state and the validated model analysis.
    """
    if not isinstance(raw_weapon_data, Mapping):
        raise TypeError(
            "raw_weapon_data must be a Mapping."
        )

    if not raw_weapon_data:
        raise ValueError(
            "No weapon data was supplied."
        )

    raw_dict = dict(raw_weapon_data)

    prepared = prepare_weapon_analysis(
        raw_dict,
        parser=parse_weapon_data,
        interpreter=interpret_weapon,
    )

    weapon_data = prepared["weapon_data"]

    allowed_parameters = available_improvement_parameters(
        weapon_data
    )

    prompt = build_weapon_prompt(
        weapon_data=weapon_data,
        analysis_context=prepared["analysis_context"],
    )

    raw_analysis = generate_analysis(
        prompt,
        allowed_parameters=allowed_parameters,
    )

    analysis = json.loads(raw_analysis)

    return {
        **prepared,
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
        return [f"- {empty_message}"]

    items = [
        str(value).strip()
        for value in values
        if str(value).strip()
    ]

    if not items:
        return [f"- {empty_message}"]

    return [f"- {item}" for item in items]


def _format_improvements(
    values: Any,
) -> list[str]:
    if not isinstance(values, list) or not values:
        return [
            "- No se identificó una prioridad dominante."
        ]

    lines: list[str] = []

    for item in values:
        if not isinstance(item, Mapping):
            continue

        parameter = str(
            item.get("parameter") or "none"
        ).strip()

        direction = str(
            item.get("direction") or "none"
        ).strip()

        reason = str(
            item.get("reason_es") or ""
        ).strip()

        if parameter == "none":
            lines.append(
                f"- Sin mejora dominante: {reason}"
            )
            continue

        lines.append(
            f"- {parameter}: {reason} ({direction})"
        )

    return lines or [
        "- No se identificó una prioridad dominante."
    ]


def format_analysis(
    analysis: Mapping[str, Any],
) -> str:
    """
    Format validated model JSON for the existing text interface.
    """
    comfort = analysis.get("comfort")

    if not isinstance(comfort, Mapping):
        comfort = {}

    lines = [
        "¿Qué hace el arma?",
        str(
            analysis.get("behavior_summary_es")
            or "No determinado."
        ),
        "",
        "Trabajo sugerido",
        str(
            analysis.get("primary_job")
            or "general_use"
        ),
        str(
            analysis.get("job_reason_es")
            or ""
        ),
        "",
        "Fortalezas",
        *_format_list(
            analysis.get("strengths_es"),
            "No se identificaron fortalezas dominantes.",
        ),
        "",
        "Limitaciones",
        *_format_list(
            analysis.get("limitations_es"),
            "No se identificaron limitaciones dominantes.",
        ),
        "",
        "Prioridades de mejora",
        *_format_improvements(
            analysis.get("improvement_priorities")
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

    return "\n".join(lines).strip()


def analyze_weapon(
    raw_weapon_data: Mapping[str, Any],
) -> str:
    """
    Compatibility API for Flask and scripts that expect one formatted string.
    """
    state = analyze_weapon_state(raw_weapon_data)
    return format_analysis(state["analysis"])


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except OSError as error:
        raise RuntimeError(
            f"Could not read {path}."
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{path} does not contain valid JSON."
        ) from error

    if not isinstance(data, Mapping):
        raise RuntimeError(
            "The JSON root must be an object."
        )

    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Test the local RAG Warframe weapon analyzer."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("weapon_test.json"),
        help="Weapon JSON file.",
    )

    parser.add_argument(
        "--show-state",
        action="store_true",
        help=(
            "Show deterministic interpretation and "
            "retrieved concepts."
        ),
    )

    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Show the final RAG prompt.",
    )

    parser.add_argument(
        "--no-ai",
        action="store_true",
        help=(
            "Prepare the RAG context without loading "
            "the model."
        ),
    )

    args = parser.parse_args()

    raw_data = _load_json(args.input)

    prepared = prepare_weapon_analysis(
        dict(raw_data),
        parser=parse_weapon_data,
        interpreter=interpret_weapon,
    )

    weapon_data = prepared["weapon_data"]

    allowed_parameters = available_improvement_parameters(
        weapon_data
    )

    prompt = build_weapon_prompt(
        weapon_data=weapon_data,
        analysis_context=prepared["analysis_context"],
    )

    if args.show_state:
        visible_state = {
            "interpretation": prepared["interpretation"],
            "activated_concepts": prepared["activated_concepts"],
            "retrieved_knowledge": prepared[
                "retrieved_knowledge"
            ],
            "allowed_improvement_parameters": list(
                allowed_parameters
            ),
        }

        print("\n--- RAG STATE ---\n")
        print(
            json.dumps(
                visible_state,
                ensure_ascii=False,
                indent=2,
            )
        )

    if args.show_prompt:
        print("\n--- FINAL PROMPT ---\n")
        print(prompt)

    if args.no_ai:
        return

    analysis_json = generate_analysis(
        prompt,
        allowed_parameters=allowed_parameters,
    )

    analysis = json.loads(analysis_json)

    print("\n--- ANALYSIS ---\n")
    print(format_analysis(analysis))


if __name__ == "__main__":
    main()
