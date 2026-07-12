"""Pruebas sin cargar llama_cpp ni el modelo GGUF."""

from __future__ import annotations

from modules.weapon_interpreter import analyze_parsed_weapon, format_analysis
from modules.weapon_parser import parse_weapon_data


def sample_weapon() -> dict:
    return {
        "data_source": "manual",
        "weapon_category": "primary",
        "firing_mode": "automatic",
        "damage_delivery": "hitscan",
        "reload_type": "magazine",
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
        "special_mechanic": "",
    }


def fake_generator(prompt: str, max_tokens: int) -> str:
    del max_tokens

    if "Describe qué hace el arma" in prompt:
        return (
            "COMPORTAMIENTO: Dispara automáticamente impactos repetidos y "
            "mantiene una secuencia prolongada de fuego.\n"
            "RASGOS:\n"
            "- funcionamiento automático\n"
            "- entrega repetida de impactos"
        )

    if "Determina el trabajo principal" in prompt:
        return (
            "TRABAJO: daño sostenido\n"
            "JUSTIFICACIÓN: La cadencia y el cargador favorecen mantener "
            "presión continua."
        )

    if "Forma una lista breve" in prompt:
        return (
            "MEJORAS:\n"
            "- probabilidad crítica | refuerza el rendimiento durante los "
            "impactos repetidos\n"
            "- recarga | reduce la pausa entre ventanas de fuego"
        )

    if "Describe la comodidad operativa" in prompt:
        return (
            "COMODIDAD: manejable\n"
            "DESCRIPCIÓN: El cargador permite periodos largos de uso antes de "
            "una recarga perceptible.\n"
            "FRICCIONES:\n"
            "- pausa al vaciar el cargador"
        )

    raise AssertionError("Prompt inesperado")


def test_pipeline_without_model() -> None:
    parsed = parse_weapon_data(sample_weapon())
    analysis = analyze_parsed_weapon(parsed, fake_generator)
    text = format_analysis(analysis)

    assert analysis["job"]["name"] == "daño sostenido"
    assert analysis["comfort"]["rating"] == "manejable"
    assert len(analysis["improvements"]) == 2
    assert "Trabajo sugerido" in text
