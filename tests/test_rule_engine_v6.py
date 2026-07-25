from __future__ import annotations

import pytest

from modules.rule_engine import (
    RuleEvaluationError,
    evaluate_rules,
)


def test_always_rule_matches() -> None:
    rules = [
        {
            "id": "global",
            "always": True,
            "retrieve": [
                "primary_job_selection",
            ],
        }
    ]

    assert evaluate_rules({}, rules) == [
        "primary_job_selection",
    ]


def test_always_rule_rejects_conditions() -> None:
    rules = [
        {
            "id": "invalid",
            "always": True,
            "conditions": [
                {
                    "field": "weapon_category",
                    "operator": "equals",
                    "value": "primary",
                }
            ],
            "retrieve": [
                "primary_job_selection",
            ],
        }
    ]

    with pytest.raises(
        RuleEvaluationError
    ):
        evaluate_rules({}, rules)


def test_empty_rule_requires_always() -> None:
    rules = [
        {
            "id": "invalid",
            "conditions": [],
            "retrieve": [
                "primary_job_selection",
            ],
        }
    ]

    with pytest.raises(
        RuleEvaluationError
    ):
        evaluate_rules({}, rules)


def test_always_must_be_boolean() -> None:
    rules = [
        {
            "id": "invalid",
            "always": "yes",
            "retrieve": [
                "primary_job_selection",
            ],
        }
    ]

    with pytest.raises(
        RuleEvaluationError
    ):
        evaluate_rules({}, rules)


def test_rule_reads_evidence_record_value() -> None:
    interpretation = {
        "signals": {
            "uses_beam_delivery": {
                "value": True,
                "confidence": "normalized",
                "source_paths": [
                    "shared_stats.compatibility_tags",
                ],
                "reason": None,
            }
        },
        "flat_signals": {
            "uses_beam_delivery": True,
        },
    }

    rules = [
        {
            "id": "beam",
            "conditions": [
                {
                    "field": "uses_beam_delivery",
                    "operator": "equals",
                    "value": True,
                }
            ],
            "retrieve": [
                "beam_behavior",
            ],
        }
    ]

    assert evaluate_rules(
        interpretation,
        rules,
    ) == [
        "beam_behavior",
    ]


def test_confidence_gate_rejects_heuristic_signal() -> None:
    interpretation = {
        "signals": {
            "has_ambiguous_mode_records": {
                "value": True,
                "confidence": "heuristic",
                "source_paths": [
                    "attack_modes",
                ],
                "reason": None,
            }
        }
    }

    rules = [
        {
            "id": "multi_mode",
            "conditions": [
                {
                    "field": "has_ambiguous_mode_records",
                    "operator": "equals",
                    "value": True,
                    "confidence_in": [
                        "structured",
                        "normalized",
                        "derived",
                    ],
                }
            ],
            "retrieve": [
                "multi_mode_behavior",
            ],
        }
    ]

    assert evaluate_rules(
        interpretation,
        rules,
    ) == []


def test_missing_field_does_not_match_not_equals() -> None:
    rules = [
        {
            "id": "missing",
            "conditions": [
                {
                    "field": "not_available",
                    "operator": "not_equals",
                    "value": "anything",
                }
            ],
            "retrieve": [
                "should_not_match",
            ],
        }
    ]

    assert evaluate_rules(
        {},
        rules,
    ) == []


def test_duplicate_rule_ids_are_rejected() -> None:
    rules = [
        {
            "id": "duplicate",
            "always": True,
            "retrieve": [
                "one",
            ],
        },
        {
            "id": "duplicate",
            "always": True,
            "retrieve": [
                "two",
            ],
        },
    ]

    with pytest.raises(
        RuleEvaluationError
    ):
        evaluate_rules(
            {},
            rules,
        )
