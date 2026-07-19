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
                "primary_job_selection"
            ],
        }
    ]

    assert evaluate_rules({}, rules) == [
        "primary_job_selection"
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
                "primary_job_selection"
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
                "primary_job_selection"
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
                "primary_job_selection"
            ],
        }
    ]

    with pytest.raises(
        RuleEvaluationError
    ):
        evaluate_rules({}, rules)
