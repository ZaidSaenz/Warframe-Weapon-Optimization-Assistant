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


def test_interpreter_creates_expected_v6_signals() -> None:
    interpretation = interpret_weapon(
        sample_weapon()
    )

    flat = interpretation[
        "flat_signals"
    ]

    assert (
        interpretation[
            "interpretation_version"
        ]
        == 6
    )
    assert flat["weapon_category"] == "primary"
    assert flat["critical_profile_present"] is True
    assert flat["critical_chance"] == 30
    assert flat["critical_multiplier"] == 3
    assert flat["status_profile_present"] is True
    assert flat["has_repeatable_attack_cycle"] is True
    assert (
        flat[
            "mechanical_application_continuity_present"
        ]
        is True
    )
    assert (
        flat[
            "multi_target_mechanic_records_present"
        ]
        is False
    )


def test_prepare_weapon_analysis_uses_v6_interpretation() -> None:
    prepared = prepare_weapon_analysis(
        sample_weapon()
    )

    assert (
        prepared["weapon_data"]["display_name"]
        == "Control Weapon"
    )

    interpretation = prepared[
        "interpretation"
    ]

    assert (
        interpretation[
            "flat_signals"
        ]["weapon_category"]
        == "primary"
    )

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


def test_rule_engine_and_retriever_support_v6_contract() -> None:
    interpretation = {
        "signals": {
            "critical_profile_present": {
                "value": True,
                "confidence": "derived",
                "source_paths": [
                    "root_stats.critical_chance_percent",
                    "root_stats.critical_multiplier",
                ],
                "reason": None,
            },
            "reload_time": {
                "value": 2.0,
                "confidence": "structured",
                "source_paths": [
                    "shared_stats.reload_time",
                ],
                "reason": None,
            },
        },
        "flat_signals": {
            "critical_profile_present": True,
            "reload_time": 2.0,
        },
    }

    rules = [
        {
            "id": "critical",
            "conditions": [
                {
                    "field": "critical_profile_present",
                    "operator": "equals",
                    "value": True,
                    "confidence_in": [
                        "derived",
                    ],
                }
            ],
            "retrieve": [
                "critical_profile",
            ],
        },
        {
            "id": "reload",
            "conditions": [
                {
                    "field": "reload_time",
                    "operator": "greater_than",
                    "value": 0,
                }
            ],
            "retrieve": [
                "reload_friction",
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
                    "Reload interruption must be "
                    "evaluated from supported cycle data."
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

    assert concept_ids == [
        "critical_profile",
        "reload_friction",
    ]
    assert len(retrieved) == 2


def test_context_builder_legacy_surface_remains_available() -> None:
    interpretation = {
        "critical_relationship": "aligned",
        "reload_friction": "moderate",
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
    assert "RELEVANT KNOWLEDGE" in context
