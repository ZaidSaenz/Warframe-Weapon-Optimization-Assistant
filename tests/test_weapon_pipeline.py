from modules.weapon_interpreter import analyze_parsed_weapon, format_analysis
from modules.weapon_parser import parse_weapon_data


def sample_weapon():
    return {
        "weapon_name": "Sample",
        "data_source": "manual",
        "weapon_category": "primary",
        "firing_mode": "automatic",
        "damage_delivery": "hitscan",
        "reload_type": "magazine",
        "has_multiple_pellets": False,
        "is_explosive": False,
        "base_damage": {"impact": 1.2, "puncture": 4.8, "slash": 6.0},
        "critical_chance_percent": 30,
        "critical_multiplier": 3.0,
        "status_chance_percent": 10,
        "fire_rate": 15,
        "multishot": 1,
        "magazine_size": 200,
        "reload_time": 3,
        "special_mechanic": "",
    }


def fake_generator(stage, prompt, max_tokens):
    assert prompt
    assert max_tokens > 0

    if stage == "behavior":
        return (
            '{"summary_es":"Dispara impactos directos de forma automática '
            'y mantiene una secuencia prolongada.",'
            '"traits_es":["ataques repetidos","entrega directa"]}'
        )
    if stage == "job":
        return (
            '{"job":"sustained_damage",'
            '"reason_es":"El patrón automático y continuo favorece mantener '
            'presión sobre el objetivo."}'
        )
    if stage == "improvements":
        return (
            '{"improvements":['
            '{"parameter":"critical_multiplier",'
            '"direction":"reinforce",'
            '"reason_es":"Refuerza la forma en que los impactos repetidos '
            'entregan daño."}]}'
        )
    if stage == "comfort":
        return (
            '{"rating":"manageable",'
            '"description_es":"El cargador permite una ventana larga y la '
            'recarga aparece después de un periodo amplio.",'
            '"frictions_es":["recarga perceptible al vaciar el cargador"]}'
        )
    raise AssertionError(stage)


def test_pipeline_without_real_model():
    parsed = parse_weapon_data(sample_weapon())
    result = analyze_parsed_weapon(parsed, fake_generator)

    assert result["job"]["key"] == "sustained_damage"
    assert result["comfort"]["rating_key"] == "manageable"
    assert "Trabajo sugerido" in format_analysis(result)
