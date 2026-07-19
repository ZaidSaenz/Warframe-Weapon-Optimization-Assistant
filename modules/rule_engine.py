# modules/rule_engine.py

from __future__ import annotations

from typing import Any


SUPPORTED_OPERATORS = {
    "equals",
    "not_equals",
    "in",
    "not_in",
    "exists",
    "greater_than",
    "greater_or_equal",
    "less_than",
    "less_or_equal",
}


class RuleEvaluationError(ValueError):
    """Raised when a rule uses an invalid or unsupported structure."""


def _resolve_field(data: dict[str, Any], field: str) -> Any:
    """
    Resolve dot-separated fields such as `confidence.critical_profile`.
    """
    current: Any = data

    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]

    return current


def _evaluate_condition(
    interpretation: dict[str, Any],
    condition: dict[str, Any],
) -> bool:
    field = condition.get("field")
    operator = condition.get("operator")
    expected = condition.get("value")

    if not isinstance(field, str) or not field:
        raise RuleEvaluationError(
            "Rule condition requires a valid `field`."
        )

    if operator not in SUPPORTED_OPERATORS:
        raise RuleEvaluationError(
            f"Unsupported rule operator: {operator}"
        )

    actual = _resolve_field(
        interpretation,
        field,
    )

    if operator == "exists":
        expected_exists = (
            True
            if expected is None
            else bool(expected)
        )
        return (actual is not None) is expected_exists

    if operator == "equals":
        return actual == expected

    if operator == "not_equals":
        return actual != expected

    if operator == "in":
        if not isinstance(expected, list):
            raise RuleEvaluationError(
                "Operator `in` requires a list value."
            )
        return actual in expected

    if operator == "not_in":
        if not isinstance(expected, list):
            raise RuleEvaluationError(
                "Operator `not_in` requires a list value."
            )
        return actual not in expected

    if actual is None:
        return False

    try:
        if operator == "greater_than":
            return actual > expected
        if operator == "greater_or_equal":
            return actual >= expected
        if operator == "less_than":
            return actual < expected
        if operator == "less_or_equal":
            return actual <= expected
    except TypeError as exc:
        raise RuleEvaluationError(
            f"Cannot compare field `{field}` value "
            f"{actual!r} with {expected!r}."
        ) from exc

    return False


def _rule_matches(
    interpretation: dict[str, Any],
    rule: dict[str, Any],
) -> bool:
    always = rule.get("always", False)

    if not isinstance(always, bool):
        raise RuleEvaluationError(
            f"Rule `{rule.get('id', '<unknown>')}` "
            "has invalid `always` value."
        )

    conditions = rule.get("conditions", [])

    if always:
        if conditions not in (None, []):
            raise RuleEvaluationError(
                f"Rule `{rule.get('id', '<unknown>')}` "
                "cannot combine `always: true` with conditions."
            )
        return True

    match_mode = rule.get("match", "all")

    if not isinstance(conditions, list) or not conditions:
        raise RuleEvaluationError(
            f"Rule `{rule.get('id', '<unknown>')}` "
            "requires conditions or `always: true`."
        )

    results = [
        _evaluate_condition(
            interpretation,
            condition,
        )
        for condition in conditions
    ]

    if match_mode == "all":
        return all(results)

    if match_mode == "any":
        return any(results)

    raise RuleEvaluationError(
        f"Rule `{rule.get('id', '<unknown>')}` "
        f"has invalid match mode: {match_mode}"
    )


def evaluate_rules(
    interpretation: dict[str, Any],
    rules: list[dict[str, Any]],
) -> list[str]:
    """
    Return unique concept IDs requested by every matching rule.
    """
    retrieved_ids: list[str] = []
    seen: set[str] = set()

    for rule in rules:
        if not _rule_matches(
            interpretation,
            rule,
        ):
            continue

        concept_ids = rule.get("retrieve", [])

        if not isinstance(concept_ids, list) or not all(
            isinstance(item, str) and item
            for item in concept_ids
        ):
            raise RuleEvaluationError(
                f"Rule `{rule.get('id', '<unknown>')}` "
                "has invalid `retrieve`."
            )

        for concept_id in concept_ids:
            if concept_id not in seen:
                seen.add(concept_id)
                retrieved_ids.append(concept_id)

    return retrieved_ids
