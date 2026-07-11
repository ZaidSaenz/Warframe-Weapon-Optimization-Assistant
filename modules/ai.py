# modules/ai.py

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from typing import Any

from llama_cpp import Llama

from modules.prompt_builder import build_weapon_prompt
from modules.weapon_parser import parse_weapon_data


MODEL_ID = "HuggingFaceTB/SmolLM2-1.7B-Instruct"
MODEL_FILE = "SmolLM2-1.7B-Instruct-Q4_K_M.gguf"
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / MODEL_FILE

SYSTEM_PROMPT = """
Eres un analista técnico de estadísticas de armas de Warframe.

Analiza únicamente los datos proporcionados por el usuario.

Reglas:
- No generes builds completas.
- No recomiendes mods, Arcanos, Rivens, polaridades ni Formas.
- No inventes estadísticas, mecánicas ni información ausente.
- No uses el nombre o la identidad del arma para completar información.
- Distingue entre reforzar una fortaleza y corregir una debilidad.
- No presentes las estimaciones derivadas como daño real exacto.
- No evalúes campos opcionales que no hayan sido proporcionados.
- Explica cada conclusión mediante relaciones visibles entre las estadísticas.
- Responde en español claro, directo y sin repetir toda la entrada.
- Respeta exactamente los encabezados solicitados en el mensaje del usuario.
""".strip()

_llm: Llama | None = None
_model_lock = Lock()
_inference_lock = Lock()


def get_model() -> Llama:
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

        _llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=2048,
            seed=42,
            verbose=False,
        )

    return _llm


def _extract_content(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")

    if not isinstance(choices, list) or not choices:
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


def generate_analysis(prompt: str, max_tokens: int = 420) -> str:
    prompt = str(prompt).strip()

    if not prompt:
        raise ValueError("El prompt de análisis está vacío.")

    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        raise TypeError("max_tokens debe ser un número entero.")

    if max_tokens < 1:
        raise ValueError("max_tokens debe ser mayor que cero.")

    try:
        with _inference_lock:
            response = get_model().create_chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=0.2,
                top_p=0.9,
                max_tokens=max_tokens,
            )
    except Exception as error:
        raise RuntimeError(
            "No fue posible generar el análisis del arma."
        ) from error

    if not isinstance(response, Mapping):
        raise RuntimeError("El modelo devolvió un formato de respuesta inválido.")

    return _extract_content(response)


def analyze_weapon(
    weapon_data: Mapping[str, Any],
    max_tokens: int = 420,
) -> str:
    if not isinstance(weapon_data, Mapping):
        raise TypeError(
            "weapon_data debe ser un diccionario o un objeto equivalente."
        )

    if not weapon_data:
        raise ValueError("No se recibieron estadísticas del arma.")

    parsed_weapon = parse_weapon_data(weapon_data)
    prompt = build_weapon_prompt(parsed_weapon)

    return generate_analysis(
        prompt=prompt,
        max_tokens=max_tokens,
    )


generate = generate_analysis