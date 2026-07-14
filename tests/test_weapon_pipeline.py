from __future__ import annotations

from modules.context_builder import build_analysis_context
from modules.knowledge_retriever import retrieve_knowledge
from modules.rule_engine import evaluate_rules
from modules.weapon_interpreter import interpret_weapon
from modules.weapon_parser import parse_weapon_data


def sample_weapon() -> dict:
    return {
        "weapon_name": "Control weapon",
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


def test_parser_and_interpreter_create_expected_signals():
    parsed = parse_weapon_data(sample_weapon())
    interpretation = interpret_weapon(parsed)

    assert parsed["weapon_category"] == "primary"
    assert interpretation["critical_relationship"] == "aligned"
    assert interpretation["status_relationship"] == "limited"
    assert interpretation["damage_behavior"] == "sustained"
    assert interpretation["target_profile"] == "single_target"


def test_rule_engine_and_retriever_work_together():
    interpretation = {
        "critical_profile": "strong",
        "status_profile": "weak",
        "reload_friction": "moderate",
        "damage_behavior": "sustained",
    }

    rules = [
        {
            "id": "critical",
            "match": "all",
            "conditions": [
                {
                    "field": "critical_profile",
                    "operator": "equals",
                    "value": "strong",
                }
            ],
            "retrieve": ["critical_profile"],
        },
        {
            "id": "reload",
            "match": "all",
            "conditions": [
                {
                    "field": "reload_friction",
                    "operator": "in",
                    "value": ["moderate", "high"],
                }
            ],
            "retrieve": ["reload_friction"],
        },
    ]

    concepts = {
        "critical_profile": {
            "id": "critical_profile",
            "title": "Critical profile",
            "principles": [
                "Critical chance and multiplier must be evaluated together."
            ],
        },
        "reload_friction": {
            "id": "reload_friction",
            "title": "Reload friction",
            "principles": [
                "Reload time must be evaluated relative to magazine duration."
            ],
        },
    }

    concept_ids = evaluate_rules(interpretation, rules)
    retrieved = retrieve_knowledge(concept_ids, concepts)
    context = build_analysis_context(interpretation, retrieved)

    assert concept_ids == ["critical_profile", "reload_friction"]
    assert len(retrieved) == 2
    assert "DETERMINISTIC INTERPRETATION" in context
    assert "RELEVANT KNOWLEDGE" in context
