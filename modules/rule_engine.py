# modules/rule_engine.py

from __future__ import annotations

from collections.abc import Mapping
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

_EVIDENCE_KEYS = {
    "value",
    "confidence",
    "source_paths",
    "reason",
}

_MISSING = object()


class RuleEvaluationError(ValueError):
    """Raised when a rule uses an invalid or unsupported structure."""


def _is_evidence_record(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and "value" in value
        and bool(_EVIDENCE_KEYS.intersection(value))
    )


def _unwrap(value: Any) -> Any:
    if _is_evidence_record(value):
        return value.get("value")

    return value


def _resolve_path(
    data: Mapping[str, Any],
    field: str,
) -> Any:
    current: Any = data

    for part in field.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING

        current = current[part]

    return current


def _resolve_field(
    interpretation: Mapping[str, Any],
    field: str,
) -> Any:
    """
    Resolve a field from:
    - interpretation root;
    - interpretation["signals"];
    - interpretation["flat_signals"].

    Evidence records are automatically unwrapped to their `value`.
    """
    candidates = (
        interpretation,
        interpretation.get("signals", {}),
        interpretation.get("flat_signals", {}),
    )

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue

        value = _resolve_path(
            candidate,
            field,
        )

        if value is not _MISSING:
            return _unwrap(value)

    return _MISSING


def _resolve_confidence(
    interpretation: Mapping[str, Any],
    field: str,
) -> str | None:
    candidates = (
        interpretation,
        interpretation.get("signals", {}),
    )

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue

        value = _resolve_path(
            candidate,
            field,
        )

        if not _is_evidence_record(value):
            continue

        confidence = value.get("confidence")

        return (
            str(confidence)
            if confidence is not None
            else None
        )

    return None


def _confidence_matches(
    interpretation: Mapping[str, Any],
    condition: Mapping[str, Any],
) -> bool:
    allowed = condition.get("confidence_in")

    if allowed is None:
        return True

    if (
        not isinstance(allowed, list)
        or not allowed
        or not all(
            isinstance(item, str) and item
            for item in allowed
        )
    ):
        raise RuleEvaluationError(
            "`confidence_in` must be a non-empty list of strings."
        )

    field = condition.get("field")

    if not isinstance(field, str) or not field:
        return False

    confidence = _resolve_confidence(
        interpretation,
        field,
    )

    return confidence in allowed


def _evaluate_condition(
    interpretation: Mapping[str, Any],
    condition: Mapping[str, Any],
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

    if not _confidence_matches(
        interpretation,
        condition,
    ):
        return False

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

        actual_exists = (
            actual is not _MISSING
            and actual is not None
        )

        return actual_exists is expected_exists

    if actual is _MISSING:
        return False

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
    interpretation: Mapping[str, Any],
    rule: Mapping[str, Any],
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

    if not isinstance(conditions, list) or not conditions:
        raise RuleEvaluationError(
            f"Rule `{rule.get('id', '<unknown>')}` "
            "requires conditions or `always: true`."
        )

    match_mode = rule.get("match", "all")

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


def validate_rules(
    rules: list[dict[str, Any]],
) -> None:
    seen_ids: set[str] = set()

    for rule in rules:
        rule_id = rule.get("id")

        if not isinstance(rule_id, str) or not rule_id:
            raise RuleEvaluationError(
                "Every rule requires a non-empty string `id`."
            )

        if rule_id in seen_ids:
            raise RuleEvaluationError(
                f"Duplicate rule id: {rule_id}"
            )

        seen_ids.add(rule_id)

        retrieve = rule.get("retrieve")

        if (
            not isinstance(retrieve, list)
            or not retrieve
            or not all(
                isinstance(item, str) and item
                for item in retrieve
            )
        ):
            raise RuleEvaluationError(
                f"Rule `{rule_id}` has invalid `retrieve`."
            )


def evaluate_rules(
    interpretation: Mapping[str, Any],
    rules: list[dict[str, Any]],
) -> list[str]:
    """
    Return unique concept IDs requested by every matching rule.

    Supports both the previous flat interpretation dictionary and the new
    evidence-aware contract returned by `weapon_interpreter.py`.
    """
    validate_rules(rules)

    retrieved_ids: list[str] = []
    seen: set[str] = set()

    for rule in rules:
        if not _rule_matches(
            interpretation,
            rule,
        ):
            continue

        for concept_id in rule["retrieve"]:
            if concept_id in seen:
                continue

            seen.add(concept_id)
            retrieved_ids.append(concept_id)

    return retrieved_ids
