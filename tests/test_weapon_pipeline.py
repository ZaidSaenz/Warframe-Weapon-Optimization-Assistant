from __future__ import annotations

from modules.knowledge import retrieve_knowledge
from modules.prompt_builder import build_analysis_context
from modules.rule_engine import evaluate_rules
from modules.weapon_interpreter import interpret_weapon
from modules.weapon_pipeline import prepare_weapon_analysis


def sample_weapon() -> dict:
    return {
        "schema_version": 1,
        "weapon_id": "/Test/ControlWeapon",
        "name_key": "/Test/ControlWeaponName",
        "display_name": "Control Weapon",
        "description_key": "/Test/ControlWeaponDesc",
        "display_description": (
            "A deterministic test weapon."
        ),
        "classification": {
            "category": "primary",
            "source_category": "LongGuns",
            "weapon_class": "rifle",
            "variant_type": "vt_normal",
            "mastery_rank": 0,
            "slot": 1,
        },
        "shared_stats": {
            "magazine_size": 200,
            "reload_time": 3,
            "multishot": 1,
            "accuracy": 100,
            "noise": "alarming",
            "trigger_type": "automatic",
            "compatibility_tags": [],
        },
        "root_stats": {
            "total_damage": 12,
            "damage": {
                "impact": 1.2,
                "puncture": 4.8,
                "slash": 6.0,
            },
            "critical_chance_percent": 30,
            "critical_multiplier": 3.0,
            "status_chance_percent": 10,
            "fire_rate": 15,
        },
        "attack_modes": [
            {
                "mode_id": "mode_1",
                "state_name": (
                    "/Lotus/Language/Menu/"
                    "Loadout_TriggerAuto"
                ),
                "trigger_type": "automatic",
                "fire_iterations": 1,
                "damage_components": [
                    {
                        "component_type": "direct",
                        "damage": {
                            "impact": 1.2,
                            "puncture": 4.8,
                            "slash": 6.0,
                        },
                        "status_chance_percent": 10,
                    }
                ],
                "fire_rate": 15,
                "critical_chance_percent": 30,
                "critical_multiplier": 3.0,
                "status_chance_percent": 10,
            }
        ],
        "source": {
            "parent_name": None,
            "icon": None,
            "codex_secret": False,
            "tradable": False,
            "introduced_at": None,
            "normalization_status": "complete",
            "warnings": [],
        },
    }


def test_interpreter_creates_expected_signals():
    interpretation = interpret_weapon(
        sample_weapon()
    )

    assert interpretation[
        "weapon_category"
    ] == "primary"

    assert interpretation[
        "critical_relationship"
    ] == "aligned"

    assert interpretation[
        "status_relationship"
    ] == "limited"

    assert interpretation[
        "damage_behavior"
    ] == "sustained"

    assert interpretation[
        "target_profile"
    ] == "single_target"


def test_prepare_weapon_analysis_uses_normalized_weapon():
    prepared = prepare_weapon_analysis(
        sample_weapon()
    )

    assert prepared[
        "weapon_data"
    ]["display_name"] == "Control Weapon"

    assert prepared[
        "interpretation"
    ]["weapon_category"] == "primary"

    assert isinstance(
        prepared["activated_concepts"],
        list,
    )

    assert isinstance(
        prepared["retrieved_knowledge"],
        list,
    )

    assert (
        "DETERMINISTIC INTERPRETATION"
        in prepared["analysis_context"]
    )


def test_rule_engine_and_retriever_work_together():
    interpretation = {
        "critical_relationship": "aligned",
        "status_relationship": "limited",
        "reload_friction": "moderate",
        "damage_behavior": "sustained",
    }

    rules = [
        {
            "id": "critical",
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
            "id": "reload",
            "match": "all",
            "conditions": [
                {
                    "field": "reload_friction",
                    "operator": "in",
                    "value": [
                        "moderate",
                        "high",
                    ],
                }
            ],
            "retrieve": [
                "reload_friction"
            ],
        },
    ]

    concepts = {
        "critical_profile": {
            "id": "critical_profile",
            "title": "Critical profile",
            "principles": [
                (
                    "Critical chance and multiplier "
                    "must be evaluated together."
                )
            ],
        },
        "reload_friction": {
            "id": "reload_friction",
            "title": "Reload friction",
            "principles": [
                (
                    "Reload time must be evaluated "
                    "relative to magazine duration."
                )
            ],
        },
    }

    concept_ids = evaluate_rules(
        interpretation,
        rules,
    )

    retrieved = retrieve_knowledge(
        concept_ids,
        concepts,
    )

    context = build_analysis_context(
        interpretation,
        retrieved,
    )

    assert concept_ids == [
        "critical_profile",
        "reload_friction",
    ]

    assert len(retrieved) == 2

    assert (
        "DETERMINISTIC INTERPRETATION"
        in context
    )

    assert "RELEVANT KNOWLEDGE" in context