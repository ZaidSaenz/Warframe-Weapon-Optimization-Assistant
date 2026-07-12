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

from modules.prompt_builder import build_weapon_prompt, expected_headings
from modules.weapon_interpreter import interpret_weapon_data
from modules.weapon_parser import parse_weapon_data


MODEL_ID = "HuggingFaceTB/SmolLM2-1.7B-Instruct"
MODEL_FILE = "SmolLM2-1.7B-Instruct-Q4_K_M.gguf"
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / MODEL_FILE

CONTEXT_SIZE = 4096
DEFAULT_MAX_TOKENS = 420

SYSTEM_PROMPT = """
Eres un redactor técnico de análisis estadísticos de armas de Warframe.

Recibirás conclusiones ya calculadas por reglas deterministas. Tu tarea es
explicarlas con claridad, no volver a calcularlas ni sustituirlas por
conocimiento externo.

Reglas:
- Usa únicamente la información proporcionada.
- No contradigas clasificaciones, prioridades ni límites recibidos.
- No inventes pasivas, evoluciones, ataques alternativos o mecánicas.
- No presentes estimaciones como daño real exacto.
- No recomiendes mods, Arcanos, Rivens, polaridades, Formas ni builds completas.
- Distingue entre reforzar una fortaleza y corregir una debilidad.
- Respeta exactamente los encabezados solicitados.
- Responde en español claro, directo y sin repetir toda la entrada.
""".strip()

_llm: Any | None = None
_model_lock = Lock()
_inference_lock = Lock()


def get_model() -> Any:
    global _llm

    if _llm is not None:
        return _llm

    with _model_lock:
        if _llm is not None:
            return _llm

        if not MODEL_PATH.is_file():
            raise FileNotFoundError(
                f"No se encontró el modelo local: {MODEL_PATH}"
            )

        try:
            from llama_cpp import Llama
        except ImportError as error:
            raise RuntimeError(
                "llama-cpp-python no está instalado en este entorno."
            ) from error

        _llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=CONTEXT_SIZE,
            seed=42,
            verbose=False,
        )

    return _llm


def unload_model() -> None:
    global _llm

    with _model_lock:
        _llm = None


def _extract_content(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")

    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)):
        raise RuntimeError("El modelo no devolvió una lista de respuestas.")

    if not choices:
        raise RuntimeError("El modelo no devolvió ninguna respuesta.")

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise RuntimeError("La respuesta del modelo tiene un formato inválido.")

    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        raise RuntimeError("La respuesta del modelo no contiene un mensaje.")

    content = str(message.get("content") or "").strip()
    if not content:
        raise RuntimeError("El modelo devolvió una respuesta vacía.")

    return content


def _clean_generated_text(content: str) -> str:
    text = content.strip()

    text = re.sub(
        r"^```(?:markdown|text)?\s*|\s*```$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    for heading in expected_headings():
        escaped = re.escape(heading)
        text = re.sub(
            rf"(?im)^\s*(?:[-*]\s*)?\*\*{escaped}:?\*\*\s*",
            f"{heading}: ",
            text,
        )
        text = re.sub(
            rf"(?im)^\s*#+\s*{escaped}:?\s*",
            f"{heading}: ",
            text,
        )

    return text.strip()


def _missing_headings(content: str) -> list[str]:
    lowered = content.casefold()
    return [
        heading
        for heading in expected_headings()
        if f"{heading}:".casefold() not in lowered
    ]


def _create_completion(
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
) -> str:
    try:
        with _inference_lock:
            response = get_model().create_chat_completion(
                messages=messages,
                temperature=0.10,
                top_p=0.90,
                repeat_penalty=1.12,
                max_tokens=max_tokens,
            )
    except Exception as error:
        raise RuntimeError(
            "No fue posible generar el análisis del arma."
        ) from error

    if not isinstance(response, Mapping):
        raise RuntimeError("El modelo devolvió un formato de respuesta inválido.")

    return _clean_generated_text(_extract_content(response))


def generate_analysis(
    prompt: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    *,
    strict_format: bool = True,
) -> str:
    prompt = str(prompt).strip()

    if not prompt:
        raise ValueError("El prompt de análisis está vacío.")

    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        raise TypeError("max_tokens debe ser un número entero.")

    if max_tokens < 1:
        raise ValueError("max_tokens debe ser mayor que cero.")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    content = _create_completion(messages, max_tokens=max_tokens)
    missing = _missing_headings(content)

    if strict_format and missing:
        correction = (
            "Reescribe tu respuesta completa. Conserva las conclusiones, pero "
            "usa exactamente estos seis encabezados con dos puntos y no agregues "
            "otros encabezados: "
            + ", ".join(expected_headings())
            + "."
        )
        retry_messages = [
            *messages,
            {"role": "assistant", "content": content},
            {"role": "user", "content": correction},
        ]
        retry_content = _create_completion(
            retry_messages,
            max_tokens=max_tokens,
        )

        if not _missing_headings(retry_content):
            return retry_content

    return content


def prepare_weapon_analysis(
    raw_weapon_data: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(raw_weapon_data, Mapping):
        raise TypeError(
            "raw_weapon_data debe ser un diccionario o un objeto equivalente."
        )

    if not raw_weapon_data:
        raise ValueError("No se recibieron estadísticas del arma.")

    parsed = parse_weapon_data(raw_weapon_data)
    interpreted = interpret_weapon_data(parsed)
    prompt = build_weapon_prompt(interpreted)

    return {
        "parsed": parsed,
        "interpreted": interpreted,
        "prompt": prompt,
    }


def analyze_weapon(
    weapon_data: Mapping[str, Any],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    *,
    strict_format: bool = True,
) -> str:
    prepared = prepare_weapon_analysis(weapon_data)

    return generate_analysis(
        prompt=prepared["prompt"],
        max_tokens=max_tokens,
        strict_format=strict_format,
    )


def _sample_weapon() -> dict[str, Any]:
    return {
        "data_source": "manual",
        "weapon_category": "primary",
        "firing_mode": "automatic",
        "damage_delivery": "hitscan",
        "has_multiple_pellets": False,
        "is_explosive": False,
        "base_damage": {
            "impact": 1.2,
            "puncture": 4.8,
            "slash": 6.0,
        },
        "critical_chance_percent": 30,
        "critical_multiplier": 3.0,
        "status_chance_percent": 10,
        "fire_rate": 15,
        "multishot": 1,
        "magazine_size": 200,
        "reload_time": 3,
    }


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuntimeError(f"No fue posible leer {path}.") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{path} no contiene JSON válido.") from error

    if not isinstance(data, Mapping):
        raise RuntimeError("El JSON debe contener un objeto en la raíz.")

    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prueba el pipeline local de análisis de armas."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--input",
        type=Path,
        help="Archivo JSON con estadísticas del arma.",
    )
    source.add_argument(
        "--sample",
        action="store_true",
        help="Usa un arma automática de ejemplo.",
    )
    parser.add_argument(
        "--show-parsed",
        action="store_true",
        help="Muestra la salida del parser.",
    )
    parser.add_argument(
        "--show-interpreted",
        action="store_true",
        help="Muestra la salida del intérprete.",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Muestra el prompt final.",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Prepara el pipeline sin cargar el modelo.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
    )
    parser.add_argument(
        "--no-strict-format",
        action="store_true",
        help="No reintenta cuando faltan encabezados.",
    )
    args = parser.parse_args()

    raw_data = _load_json(args.input) if args.input else _sample_weapon()
    prepared = prepare_weapon_analysis(raw_data)

    if args.show_parsed:
        print("\n--- PARSED ---\n")
        print(json.dumps(prepared["parsed"], ensure_ascii=False, indent=2))

    if args.show_interpreted:
        print("\n--- INTERPRETED ---\n")
        print(json.dumps(prepared["interpreted"], ensure_ascii=False, indent=2))

    if args.show_prompt:
        print("\n--- PROMPT ---\n")
        print(prepared["prompt"])

    if args.no_ai:
        if not (
            args.show_parsed
            or args.show_interpreted
            or args.show_prompt
        ):
            print(json.dumps(prepared["interpreted"], ensure_ascii=False, indent=2))
        return

    result = generate_analysis(
        prepared["prompt"],
        max_tokens=args.max_tokens,
        strict_format=not args.no_strict_format,
    )
    print("\n--- RESPUESTA ---\n")
    print(result)


if __name__ == "__main__":
    main()


generate = generate_analysis