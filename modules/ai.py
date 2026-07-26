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
    SYSTEM_PROMPT as LEGACY_SYSTEM_PROMPT,
    available_improvement_parameters,
    build_synthesis_prompt,
    build_weapon_prompt,
    build_weapon_prompt_plan,
)
from modules.weapon_database import find_weapons
from modules.weapon_pipeline import prepare_weapon_analysis


# -----------------------------------------------------------------------------
# Model configuration
# -----------------------------------------------------------------------------
MODEL_FILE = "Qwen2.5-3B-Instruct-Q4_K_M.gguf"
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / MODEL_FILE

CONTEXT_SIZE = 4096
PARTIAL_MAX_TOKENS = 550
SYNTHESIS_MAX_TOKENS = 700
LEGACY_MAX_TOKENS = 650

ANALYSIS_MODE = "multi_prompt"
VALID_ANALYSIS_MODES = {
    "multi_prompt",
    "single_prompt",
}

DEFAULT_SYSTEM_PROMPT = (
    "Follow the user prompt exactly. "
    "Use only the supplied evidence. "
    "Return only the requested JSON object."
)

# -----------------------------------------------------------------------------
# Shared logger, cached model, and concurrency locks
# -----------------------------------------------------------------------------
logger = get_logger(__name__)

_llm: Any | None = None
_model_lock = Lock()
_inference_lock = Lock()


# -----------------------------------------------------------------------------
# Domain-specific errors
# -----------------------------------------------------------------------------
class ModelResponseError(RuntimeError):
    """Raised when the local model response cannot be used."""


class PromptTaskError(RuntimeError):
    """Raised when one specialized prompt task fails validation."""


# -----------------------------------------------------------------------------
# Model lifecycle
# -----------------------------------------------------------------------------
def get_model() -> Any:
    """Load and reuse the local GGUF model."""
    global _llm

    with _model_lock:
        if _llm is None:
            if not MODEL_PATH.is_file():
                raise FileNotFoundError(
                    f"Model not found: {MODEL_PATH}"
                )

            try:
                from llama_cpp import Llama
            except ImportError as error:
                raise RuntimeError(
                    "llama-cpp-python is not installed."
                ) from error

            logger.info(
                "Loading local model | model=%s",
                MODEL_FILE,
            )

            _llm = Llama(
                model_path=str(MODEL_PATH),
                n_ctx=CONTEXT_SIZE,
                seed=42,
                verbose=False,
            )

    return _llm


def unload_model() -> None:
    """Release the cached model reference."""
    global _llm

    with _model_lock:
        _llm = None


# -----------------------------------------------------------------------------
# Model-response extraction and JSON normalization
# -----------------------------------------------------------------------------
def _extract_content(
    response: Mapping[str, Any],
) -> str:
    """Extract assistant content from llama-cpp output."""
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ModelResponseError(
            "The model returned an unexpected response."
        ) from error

    content = str(content or "").strip()

    if not content:
        raise ModelResponseError(
            "The model returned an empty response."
        )

    return content


def _strip_markdown_fence(text: str) -> str:
    cleaned = text.strip()

    if not cleaned.startswith("```"):
        return cleaned

    first_newline = cleaned.find("\n")

    if first_newline == -1:
        return cleaned.removeprefix("```").removesuffix("```").strip()

    cleaned = cleaned[first_newline + 1 :]

    if cleaned.rstrip().endswith("```"):
        cleaned = cleaned.rstrip()[:-3]

    return cleaned.strip()


def _extract_json_object(text: str) -> str:
    """
    Extract the outermost JSON object from a model response.

    This tolerates a short accidental prefix or suffix while still requiring
    one complete JSON object.
    """
    cleaned = _strip_markdown_fence(text)

    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ModelResponseError(
            "The model response does not contain a JSON object."
        )

    return cleaned[start : end + 1]


def _parse_json(text: str) -> dict[str, Any]:
    """Parse one JSON object from model output."""
    candidate = _extract_json_object(text)

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ModelResponseError(
            "The model response is not valid JSON."
        ) from error

    if not isinstance(data, dict):
        raise ModelResponseError(
            "The model response must be a JSON object."
        )

    return data


# -----------------------------------------------------------------------------
# Low-level inference execution
# -----------------------------------------------------------------------------
def _model_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
) -> dict[str, Any]:
    clean_system = str(
        system_prompt or DEFAULT_SYSTEM_PROMPT
    ).strip()
    clean_prompt = str(user_prompt or "").strip()

    if not clean_prompt:
        raise ValueError("Prompt cannot be empty.")

    with _inference_lock:
        response = get_model().create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": clean_system,
                },
                {
                    "role": "user",
                    "content": clean_prompt,
                },
            ],
            temperature=0.05,
            top_p=0.90,
            repeat_penalty=1.08,
            max_tokens=max_tokens,
            response_format={
                "type": "json_object",
            },
        )

    if not isinstance(response, Mapping):
        raise ModelResponseError(
            "The model returned a non-mapping response."
        )

    return dict(response)


def generate_analysis(
    prompt: str,
    *,
    system_prompt: str | None = None,
    max_tokens: int = LEGACY_MAX_TOKENS,
    **_: Any,
) -> str:
    """
    Execute one prompt and return normalized JSON text.

    Retained as a compatibility API for scripts that already call this
    function directly.
    """
    clean_prompt = str(prompt or "").strip()

    if not clean_prompt:
        raise ValueError("Prompt cannot be empty.")

    try:
        response = _model_completion(
            system_prompt=(
                system_prompt
                or DEFAULT_SYSTEM_PROMPT
            ),
            user_prompt=clean_prompt,
            max_tokens=max_tokens,
        )

        analysis = _parse_json(
            _extract_content(response)
        )

        return json.dumps(
            analysis,
            ensure_ascii=False,
            indent=2,
        )

    except Exception as error:
        log_exception(
            logger,
            "Model inference failed.",
            error,
            prompt_characters=len(clean_prompt),
        )
        raise


# -----------------------------------------------------------------------------
# Partial-result and final-result validation
# -----------------------------------------------------------------------------
def _expected_concept_id(
    task_id: str,
) -> str | None:
    return {
        "critical_profile": "critical_profile",
        "status_application": "status_application",
        "mechanical_behavior": "mechanical_behavior",
        "operational_profile": "operational_profile",
    }.get(task_id)


def _validate_partial_result(
    task_id: str,
    result: Mapping[str, Any],
) -> None:
    expected = _expected_concept_id(task_id)

    if expected is None:
        return

    actual = result.get("concept_id")

    if actual != expected:
        raise PromptTaskError(
            f"Task {task_id!r} returned concept_id "
            f"{actual!r}; expected {expected!r}."
        )


def _validate_final_analysis(
    analysis: Mapping[str, Any],
    *,
    allowed_parameters: Sequence[str],
) -> None:
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
        required_fields - set(analysis.keys())
    )

    if missing:
        raise ModelResponseError(
            "Final analysis is missing fields: "
            + ", ".join(missing)
        )

    comfort = analysis.get("comfort")

    if not isinstance(comfort, Mapping):
        raise ModelResponseError(
            "Final comfort must be a JSON object."
        )

    improvements = analysis.get(
        "improvement_priorities"
    )

    if not isinstance(improvements, list):
        raise ModelResponseError(
            "Final improvement_priorities must be a list."
        )

    valid_parameters = {
        *allowed_parameters,
        "none",
    }

    for item in improvements:
        if not isinstance(item, Mapping):
            raise ModelResponseError(
                "Every improvement must be a JSON object."
            )

        parameter = item.get("parameter")

        if parameter not in valid_parameters:
            raise ModelResponseError(
                f"Invalid improvement parameter: {parameter!r}."
            )


# -----------------------------------------------------------------------------
# Specialized task execution and synthesis payload preparation
# -----------------------------------------------------------------------------
def _task_payload_for_synthesis(
    task_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": task_result.get("id"),
        "status": task_result.get("status"),
        "result": task_result.get("result"),
        "error": task_result.get("error"),
    }


def run_prompt_task(
    task: Mapping[str, Any],
    *,
    max_tokens: int = PARTIAL_MAX_TOKENS,
    include_raw_response: bool = False,
) -> dict[str, Any]:
    """
    Execute one isolated analysis task.

    A failed partial task is returned as structured state instead of aborting
    the whole analysis. Final synthesis may preserve uncertainty for that area.
    """
    task_id = str(
        task.get("id") or "unknown"
    )
    system_prompt = str(
        task.get("system_prompt")
        or DEFAULT_SYSTEM_PROMPT
    )
    prompt = str(
        task.get("prompt") or ""
    ).strip()

    if not prompt:
        raise ValueError(
            f"Prompt task {task_id!r} has no prompt."
        )

    try:
        response = _model_completion(
            system_prompt=system_prompt,
            user_prompt=prompt,
            max_tokens=max_tokens,
        )
        raw_response = _extract_content(response)
        result = _parse_json(raw_response)
        _validate_partial_result(
            task_id,
            result,
        )

        state: dict[str, Any] = {
            "id": task_id,
            "status": "ok",
            "result": result,
        }

        if include_raw_response:
            state["raw_response"] = raw_response

        logger.info(
            "Prompt task completed | task=%s "
            "| prompt_characters=%d",
            task_id,
            len(prompt),
        )

        return state

    except Exception as error:
        log_exception(
            logger,
            "Prompt task failed.",
            error,
            task=task_id,
            prompt_characters=len(prompt),
        )

        state = {
            "id": task_id,
            "status": "error",
            "result": None,
            "error": str(error),
        }

        if include_raw_response:
            state["raw_response"] = locals().get(
                "raw_response"
            )

        return state


# -----------------------------------------------------------------------------
# Multi-prompt and legacy analysis flows
# -----------------------------------------------------------------------------
def _run_multi_prompt_analysis(
    prepared: Mapping[str, Any],
    *,
    include_debug: bool,
) -> dict[str, Any]:
    weapon_data = prepared["weapon_data"]

    plan = build_weapon_prompt_plan(
        weapon_data=weapon_data,
        interpretation=prepared["interpretation"],
        activated_concepts=prepared[
            "activated_concepts"
        ],
        retrieved_knowledge=prepared[
            "retrieved_knowledge"
        ],
    )

    partial_results = [
        run_prompt_task(
            task,
            max_tokens=PARTIAL_MAX_TOKENS,
            include_raw_response=include_debug,
        )
        for task in plan
    ]

    synthesis_input = [
        _task_payload_for_synthesis(item)
        for item in partial_results
    ]

    synthesis_task = build_synthesis_prompt(
        weapon_data=weapon_data,
        partial_results=synthesis_input,
        retrieved_knowledge=prepared[
            "retrieved_knowledge"
        ],
    )

    synthesis_state = run_prompt_task(
        synthesis_task,
        max_tokens=SYNTHESIS_MAX_TOKENS,
        include_raw_response=include_debug,
    )

    if synthesis_state["status"] != "ok":
        raise ModelResponseError(
            "Final synthesis failed: "
            + str(
                synthesis_state.get("error")
                or "unknown error"
            )
        )

    analysis = synthesis_state["result"]
    allowed_parameters = list(
        available_improvement_parameters(
            weapon_data
        )
    )

    _validate_final_analysis(
        analysis,
        allowed_parameters=allowed_parameters,
    )

    result = {
        **prepared,
        "analysis_mode": "multi_prompt",
        "allowed_improvement_parameters": (
            allowed_parameters
        ),
        "analysis": analysis,
    }

    if include_debug:
        result.update(
            {
                "prompt_plan": plan,
                "partial_results": partial_results,
                "synthesis_task": synthesis_task,
                "synthesis_result": synthesis_state,
            }
        )

    return result


def _run_single_prompt_analysis(
    prepared: Mapping[str, Any],
    *,
    include_debug: bool,
) -> dict[str, Any]:
    weapon_data = prepared["weapon_data"]
    prompt = build_weapon_prompt(
        weapon_data=weapon_data,
        analysis_context=prepared[
            "analysis_context"
        ],
    )

    analysis = json.loads(
        generate_analysis(
            prompt,
            system_prompt=LEGACY_SYSTEM_PROMPT,
            max_tokens=LEGACY_MAX_TOKENS,
        )
    )

    allowed_parameters = list(
        available_improvement_parameters(
            weapon_data
        )
    )

    _validate_final_analysis(
        analysis,
        allowed_parameters=allowed_parameters,
    )

    result = {
        **prepared,
        "analysis_mode": "single_prompt",
        "allowed_improvement_parameters": (
            allowed_parameters
        ),
        "analysis": analysis,
    }

    if include_debug:
        result["prompt"] = prompt

    return result


# -----------------------------------------------------------------------------
# Public analysis API
# -----------------------------------------------------------------------------
def analyze_weapon_state(
    normalized_weapon_data: Mapping[str, Any],
    *,
    mode: str = ANALYSIS_MODE,
    include_debug: bool = False,
) -> dict[str, Any]:
    """
    Prepare, execute, and return the complete weapon-analysis state.

    mode="multi_prompt" runs isolated analyses followed by final synthesis.
    mode="single_prompt" preserves the previous monolithic flow.
    """
    selected_mode = str(mode or "").strip()

    if selected_mode not in VALID_ANALYSIS_MODES:
        raise ValueError(
            "mode must be one of: "
            + ", ".join(
                sorted(VALID_ANALYSIS_MODES)
            )
        )

    prepared = prepare_weapon_analysis(
        dict(normalized_weapon_data)
    )

    if selected_mode == "single_prompt":
        return _run_single_prompt_analysis(
            prepared,
            include_debug=include_debug,
        )

    return _run_multi_prompt_analysis(
        prepared,
        include_debug=include_debug,
    )


# -----------------------------------------------------------------------------
# Human-readable output formatting
# -----------------------------------------------------------------------------
def _lines(
    values: Any,
    fallback: str,
) -> list[str]:
    items = (
        values
        if isinstance(values, list)
        else []
    )

    return [
        f"- {item}"
        for item in items
    ] or [f"- {fallback}"]


def format_analysis(
    analysis: Mapping[str, Any],
) -> str:
    """Format model JSON for the current text interface."""
    comfort = analysis.get("comfort") or {}
    improvements = (
        analysis.get("improvement_priorities")
        or []
    )

    improvement_lines = [
        (
            f"- {item.get('parameter', 'none')}: "
            f"{item.get('reason_es', '')} "
            f"({item.get('direction', 'none')})"
        )
        for item in improvements
        if isinstance(item, Mapping)
    ] or [
        "- No se identificó una prioridad dominante."
    ]

    return "\n".join(
        [
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
                analysis.get("primary_job")
                or "general_use"
            ),
            str(
                analysis.get("job_reason_es")
                or ""
            ),
            "",
            "Fortalezas",
            *_lines(
                analysis.get("strengths_es"),
                (
                    "No se identificaron "
                    "fortalezas dominantes."
                ),
            ),
            "",
            "Limitaciones",
            *_lines(
                analysis.get("limitations_es"),
                (
                    "No se identificaron "
                    "limitaciones dominantes."
                ),
            ),
            "",
            "Prioridades de mejora",
            *improvement_lines,
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
    ).strip()


def analyze_weapon(
    normalized_weapon_data: Mapping[str, Any],
    *,
    mode: str = ANALYSIS_MODE,
) -> str:
    """Compatibility API for Flask and scripts."""
    state = analyze_weapon_state(
        normalized_weapon_data,
        mode=mode,
        include_debug=False,
    )

    return format_analysis(
        state["analysis"]
    )


# -----------------------------------------------------------------------------
# Command-line input resolution
# -----------------------------------------------------------------------------
def _load_json(
    path: Path,
) -> Mapping[str, Any]:
    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(data, Mapping):
        raise RuntimeError(
            "The JSON root must be an object."
        )

    return data


def _find_weapon_by_name(
    weapon_name: str,
) -> Mapping[str, Any]:
    """
    Resolve one normalized weapon directly from the project database.

    Exact display-name matches are preferred. A single partial match is also
    accepted. Ambiguous searches raise an error instead of silently selecting
    the wrong weapon.
    """
    clean_name = str(
        weapon_name or ""
    ).strip()

    if not clean_name:
        raise ValueError(
            "Weapon name cannot be empty."
        )

    matches = find_weapons(
        clean_name
    )

    if not matches:
        raise RuntimeError(
            f"Weapon not found: {clean_name}"
        )

    exact_matches = [
        weapon
        for weapon in matches
        if isinstance(
            weapon,
            Mapping,
        )
        and str(
            weapon.get("display_name")
            or ""
        ).casefold() == clean_name.casefold()
    ]

    if len(exact_matches) == 1:
        return exact_matches[0]

    valid_matches = [
        weapon
        for weapon in matches
        if isinstance(
            weapon,
            Mapping,
        )
    ]

    if len(valid_matches) == 1:
        return valid_matches[0]

    candidate_names = [
        str(
            weapon.get("display_name")
            or "unknown"
        )
        for weapon in valid_matches[:10]
    ]

    raise RuntimeError(
        f"Weapon search is ambiguous: {clean_name}. "
        "Candidates: "
        + ", ".join(candidate_names)
    )


def _resolve_cli_weapon(
    *,
    weapon_name: str | None,
    input_path: Path | None,
) -> dict[str, Any]:
    """
    Resolve CLI input from the weapon database or an explicit JSON fixture.

    `--weapon` is the normal project workflow. `--input` remains available for
    isolated fixtures, custom records, and regression tests.
    """
    if input_path is not None:
        return dict(
            _load_json(input_path)
        )

    selected_name = (
        str(
            weapon_name or ""
        ).strip()
        or "Amprex"
    )

    return dict(
        _find_weapon_by_name(
            selected_name
        )
    )


# -----------------------------------------------------------------------------
# Command-line inspection helpers
# -----------------------------------------------------------------------------
def _print_prompt_plan(
    state: Mapping[str, Any],
) -> None:
    plan = state.get("prompt_plan")

    if not isinstance(plan, list):
        return

    print("\n--- PROMPT PLAN ---\n")

    for index, task in enumerate(
        plan,
        start=1,
    ):
        if not isinstance(task, Mapping):
            continue

        prompt = str(
            task.get("prompt") or ""
        )

        print(
            f"{index}. {task.get('id')} "
            f"| characters={len(prompt)} "
            f"| approx_tokens={len(prompt) // 4}"
        )


def _print_prompts(
    state: Mapping[str, Any],
) -> None:
    plan = state.get("prompt_plan")

    if isinstance(plan, list):
        for index, task in enumerate(
            plan,
            start=1,
        ):
            if not isinstance(task, Mapping):
                continue

            print(
                f"\n--- PROMPT {index}: "
                f"{task.get('id')} ---\n"
            )
            print(
                task.get("prompt") or ""
            )

    synthesis_task = state.get(
        "synthesis_task"
    )

    if isinstance(
        synthesis_task,
        Mapping,
    ):
        print(
            "\n--- FINAL SYNTHESIS PROMPT ---\n"
        )
        print(
            synthesis_task.get("prompt")
            or ""
        )


# -----------------------------------------------------------------------------
# Command-line entry point
# -----------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Test the local Warframe "
            "weapon analyzer."
        )
    )
    input_group = (
        parser.add_mutually_exclusive_group()
    )

    input_group.add_argument(
        "--weapon",
        type=str,
        help=(
            "Weapon name to resolve from the normalized database. "
            "Defaults to Amprex when neither input option is supplied."
        ),
    )
    input_group.add_argument(
        "--input",
        type=Path,
        help=(
            "Optional JSON file containing one normalized weapon. "
            "Useful for fixtures and custom tests."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=sorted(
            VALID_ANALYSIS_MODES
        ),
        default=ANALYSIS_MODE,
    )
    parser.add_argument(
        "--show-state",
        action="store_true",
    )
    parser.add_argument(
        "--show-plan",
        action="store_true",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
    )
    parser.add_argument(
        "--show-partials",
        action="store_true",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
    )
    args = parser.parse_args()

    weapon = _resolve_cli_weapon(
        weapon_name=args.weapon,
        input_path=args.input,
    )

    if args.no_ai:
        prepared = prepare_weapon_analysis(
            weapon
        )

        if args.mode == "single_prompt":
            prompt = build_weapon_prompt(
                weapon_data=prepared[
                    "weapon_data"
                ],
                analysis_context=prepared[
                    "analysis_context"
                ],
            )

            if args.show_state:
                print(
                    "\n--- RAG STATE ---\n"
                )
                print(
                    json.dumps(
                        prepared,
                        ensure_ascii=False,
                        indent=2,
                    )
                )

            if args.show_prompt:
                print(
                    "\n--- FINAL PROMPT ---\n"
                )
                print(prompt)

            return

        plan = build_weapon_prompt_plan(
            weapon_data=prepared[
                "weapon_data"
            ],
            interpretation=prepared[
                "interpretation"
            ],
            activated_concepts=prepared[
                "activated_concepts"
            ],
            retrieved_knowledge=prepared[
                "retrieved_knowledge"
            ],
        )

        preview_state = {
            **prepared,
            "prompt_plan": plan,
        }

        if args.show_state:
            print(
                "\n--- RAG STATE ---\n"
            )
            print(
                json.dumps(
                    prepared,
                    ensure_ascii=False,
                    indent=2,
                )
            )

        if args.show_plan:
            _print_prompt_plan(
                preview_state
            )

        if args.show_prompt:
            _print_prompts(
                preview_state
            )

        return

    state = analyze_weapon_state(
        weapon,
        mode=args.mode,
        include_debug=True,
    )

    if args.show_state:
        print(
            "\n--- ANALYSIS STATE ---\n"
        )
        print(
            json.dumps(
                {
                    "interpretation": state[
                        "interpretation"
                    ],
                    "activated_concepts": state[
                        "activated_concepts"
                    ],
                    "retrieved_knowledge": state[
                        "retrieved_knowledge"
                    ],
                    "allowed_improvement_parameters": state[
                        "allowed_improvement_parameters"
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    if args.show_plan:
        _print_prompt_plan(state)

    if args.show_prompt:
        _print_prompts(state)

    if args.show_partials:
        print(
            "\n--- PARTIAL RESULTS ---\n"
        )
        print(
            json.dumps(
                state.get(
                    "partial_results",
                    [],
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

    print("\n--- ANALYSIS ---\n")
    print(
        format_analysis(
            state["analysis"]
        )
    )


if __name__ == "__main__":
    main()