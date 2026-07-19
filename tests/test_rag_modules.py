# tests/test_rag_modules.py

from modules.knowledge import retrieve_knowledge
from modules.prompt_builder import build_analysis_context
from modules.rule_engine import evaluate_rules


def test_rule_engine_retrieves_expected_concepts():
    interpretation = {
        "critical_relationship": "aligned",
        "reload_friction": "high",
        "damage_behavior": "sustained",
    }

    rules = [
        {
            "id": "critical_rule",
            "match": "all",
            "conditions": [
                {
                    "field": "critical_relationship",
                    "operator": "equals",
                    "value": "aligned",
                }
            ],
            "retrieve": [
                "critical_profile"
            ],
        },
        {
            "id": "reload_rule",
            "match": "all",
            "conditions": [
                {
                    "field": "reload_friction",
                    "operator": "equals",
                    "value": "high",
                }
            ],
            "retrieve": [
                "reload_friction"
            ],
        },
    ]

    result = evaluate_rules(
        interpretation,
        rules,
    )

    assert result == [
        "critical_profile",
        "reload_friction",
    ]


def test_retriever_returns_requested_concept():
    concepts = {
        "critical_profile": {
            "id": "critical_profile",
            "title": "Critical profile",
            "principles": [
                (
                    "Evaluate chance and "
                    "multiplier together."
                )
            ],
        }
    }

    result = retrieve_knowledge(
        ["critical_profile"],
        concepts,
    )

    assert len(result) == 1
    assert result[0]["id"] == "critical_profile"


def test_context_builder_contains_interpretation_and_knowledge():
    interpretation = {
        "critical_relationship": "aligned",
        "reload_friction": "high",
        "evidence": {
            "critical_relationship": [
                "root_stats.critical_chance_percent",
                "root_stats.critical_multiplier",
            ]
        },
    }

    knowledge = [
        {
            "id": "critical_profile",
            "title": "Critical profile",
            "principles": [
                (
                    "Critical chance and critical "
                    "multiplier must be evaluated "
                    "together."
                )
            ],
        }
    ]

    context = build_analysis_context(
        interpretation,
        knowledge,
    )

    assert (
        "DETERMINISTIC INTERPRETATION"
        in context
    )

    assert (
        "Critical relationship: aligned"
        in context
    )

    assert "RELEVANT KNOWLEDGE" in context

    assert (
        "Critical chance and critical multiplier"
        in context
    )