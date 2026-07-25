# modules/knowledge.py

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from modules.rule_engine import validate_rules


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KNOWLEDGE_PATH = PROJECT_ROOT / "knowledge"


class KnowledgeError(RuntimeError):
    """Base error for loading or retrieving local knowledge."""


class KnowledgeLoadError(KnowledgeError):
    """Raised when the local knowledge base cannot be loaded safely."""


class KnowledgeRetrievalError(KnowledgeError, KeyError):
    """Raised when a requested knowledge concept does not exist."""


def _load_json_file(
    path: Path,
) -> dict[str, Any]:
    try:
        raw_text = path.read_text(
            encoding="utf-8"
        )
        data = json.loads(raw_text)

    except FileNotFoundError as error:
        raise KnowledgeLoadError(
            f"Knowledge file not found: {path}"
        ) from error

    except OSError as error:
        raise KnowledgeLoadError(
            f"Could not read knowledge file: {path}"
        ) from error

    except json.JSONDecodeError as error:
        raise KnowledgeLoadError(
            f"Invalid JSON in {path}: "
            f"line {error.lineno}, "
            f"column {error.colno}"
        ) from error

    if not isinstance(data, dict):
        raise KnowledgeLoadError(
            "Knowledge file must contain "
            f"a JSON object: {path}"
        )

    return data


def _normalize_string_list(
    value: Any,
    *,
    field_name: str,
    path: Path,
    required: bool = False,
) -> list[str]:
    if value is None:
        if required:
            raise KnowledgeLoadError(
                f"`{field_name}` is required: {path}"
            )
        return []

    if (
        not isinstance(value, list)
        or not all(
            isinstance(item, str)
            and item.strip()
            for item in value
        )
    ):
        raise KnowledgeLoadError(
            f"`{field_name}` must be a list "
            f"of non-empty strings: {path}"
        )

    return [
        item.strip()
        for item in value
    ]


def _normalize_interpretation(
    value: Any,
    *,
    path: Path,
) -> dict[str, list[str]]:
    if value is None:
        return {}

    if not isinstance(value, Mapping):
        raise KnowledgeLoadError(
            f"`interpretation` must be an object: {path}"
        )

    normalized: dict[str, list[str]] = {}

    for raw_key, raw_items in value.items():
        if (
            not isinstance(raw_key, str)
            or not raw_key.strip()
        ):
            raise KnowledgeLoadError(
                "Interpretation keys must be "
                f"non-empty strings: {path}"
            )

        normalized[raw_key.strip()] = (
            _normalize_string_list(
                raw_items,
                field_name=(
                    "interpretation."
                    f"{raw_key}"
                ),
                path=path,
                required=True,
            )
        )

    return normalized


def _normalize_conditional_exceptions(
    value: Any,
    *,
    path: Path,
) -> dict[str, list[str]]:
    if value is None:
        return {}

    if not isinstance(value, Mapping):
        raise KnowledgeLoadError(
            "`conditional_exceptions` must "
            f"be an object: {path}"
        )

    normalized: dict[str, list[str]] = {}

    for raw_key, raw_items in value.items():
        if (
            not isinstance(raw_key, str)
            or not raw_key.strip()
        ):
            raise KnowledgeLoadError(
                "Conditional-exception keys "
                f"must be non-empty strings: {path}"
            )

        normalized[raw_key.strip()] = (
            _normalize_string_list(
                raw_items,
                field_name=(
                    "conditional_exceptions."
                    f"{raw_key}"
                ),
                path=path,
                required=True,
            )
        )

    return normalized


def load_concepts(
    concepts_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Load concept files and index them by their unique `id`.

    The loader validates both the current concept schema and the planned
    compact schema with optional `signal_fields`, `interpretation`,
    `conditional_exceptions`, and `exceptions`.
    """
    directory = (
        concepts_path
        or DEFAULT_KNOWLEDGE_PATH / "concepts"
    )

    if not directory.is_dir():
        raise KnowledgeLoadError(
            f"Concept directory not found: {directory}"
        )

    concepts: dict[str, dict[str, Any]] = {}

    for path in sorted(
        directory.glob("*.json")
    ):
        concept = _load_json_file(path)
        concept_id = concept.get("id")

        if (
            not isinstance(concept_id, str)
            or not concept_id.strip()
        ):
            raise KnowledgeLoadError(
                "Concept file requires a "
                f"non-empty string `id`: {path}"
            )

        normalized_id = concept_id.strip()

        if normalized_id in concepts:
            raise KnowledgeLoadError(
                f"Duplicate concept id: {normalized_id}"
            )

        normalized = dict(concept)
        normalized["id"] = normalized_id
        normalized["principles"] = (
            _normalize_string_list(
                concept.get("principles", []),
                field_name="principles",
                path=path,
            )
        )

        if "title" in concept:
            title = concept.get("title")
            if (
                not isinstance(title, str)
                or not title.strip()
            ):
                raise KnowledgeLoadError(
                    "`title` must be a non-empty "
                    f"string when present: {path}"
                )
            normalized["title"] = title.strip()

        for field_name in (
            "signal_fields",
            "related_stats",
            "derived_signals",
            "exceptions",
        ):
            if field_name in concept:
                normalized[field_name] = (
                    _normalize_string_list(
                        concept.get(field_name),
                        field_name=field_name,
                        path=path,
                    )
                )

        if "interpretation" in concept:
            normalized["interpretation"] = (
                _normalize_interpretation(
                    concept.get("interpretation"),
                    path=path,
                )
            )

        if "conditional_exceptions" in concept:
            normalized[
                "conditional_exceptions"
            ] = _normalize_conditional_exceptions(
                concept.get(
                    "conditional_exceptions"
                ),
                path=path,
            )

        concepts[normalized_id] = normalized

    if not concepts:
        raise KnowledgeLoadError(
            "No concept JSON files found in: "
            f"{directory}"
        )

    return concepts


def load_rules(
    rules_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Load every rule file and merge their `rules` arrays.

    Structural validation is delegated to `rule_engine.validate_rules` so
    loading and evaluation share one contract.
    """
    directory = (
        rules_path
        or DEFAULT_KNOWLEDGE_PATH / "rules"
    )

    if not directory.is_dir():
        raise KnowledgeLoadError(
            f"Rule directory not found: {directory}"
        )

    rules: list[dict[str, Any]] = []

    for path in sorted(
        directory.glob("*.json")
    ):
        document = _load_json_file(path)
        file_rules = document.get("rules", [])

        if not isinstance(file_rules, list):
            raise KnowledgeLoadError(
                f"`rules` must be a list: {path}"
            )

        for index, rule in enumerate(file_rules):
            if not isinstance(rule, dict):
                raise KnowledgeLoadError(
                    "Every rule must be an object: "
                    f"{path} at index {index}"
                )

            rules.append(dict(rule))

    if not rules:
        raise KnowledgeLoadError(
            f"No rules found in: {directory}"
        )

    try:
        validate_rules(rules)
    except ValueError as error:
        raise KnowledgeLoadError(
            f"Invalid rule structure: {error}"
        ) from error

    return rules


def load_knowledge_base(
    knowledge_path: Path | None = None,
) -> dict[str, Any]:
    """
    Load the complete deterministic knowledge base.
    """
    base_path = (
        knowledge_path
        or DEFAULT_KNOWLEDGE_PATH
    )

    concepts = load_concepts(
        base_path / "concepts"
    )
    rules = load_rules(
        base_path / "rules"
    )

    referenced_concepts = {
        concept_id
        for rule in rules
        for concept_id in rule.get(
            "retrieve",
            [],
        )
    }

    missing_concepts = sorted(
        referenced_concepts
        - concepts.keys()
    )

    if missing_concepts:
        raise KnowledgeLoadError(
            "Rules reference missing concepts: "
            + ", ".join(missing_concepts)
        )

    return {
        "concepts": concepts,
        "rules": rules,
    }


def retrieve_knowledge(
    concept_ids: Sequence[str],
    concepts: Mapping[
        str,
        Mapping[str, Any],
    ],
    *,
    strict: bool = True,
) -> list[dict[str, Any]]:
    """
    Return concepts in requested order without duplicates.

    With `strict=True`, a missing concept raises
    `KnowledgeRetrievalError`. With `strict=False`, it is skipped.
    """
    if isinstance(
        concept_ids,
        (str, bytes),
    ):
        raise TypeError(
            "concept_ids must be a sequence "
            "of concept identifiers."
        )

    retrieved: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw_concept_id in concept_ids:
        if not isinstance(
            raw_concept_id,
            str,
        ):
            raise TypeError(
                "Every concept id must be a string."
            )

        concept_id = raw_concept_id.strip()

        if not concept_id:
            raise ValueError(
                "Concept ids cannot be empty."
            )

        if concept_id in seen:
            continue

        concept = concepts.get(concept_id)

        if concept is None:
            if strict:
                raise KnowledgeRetrievalError(
                    "Knowledge concept not found: "
                    f"{concept_id}"
                )
            continue

        if not isinstance(
            concept,
            Mapping,
        ):
            raise KnowledgeRetrievalError(
                "Knowledge concept has an invalid "
                f"structure: {concept_id}"
            )

        seen.add(concept_id)
        retrieved.append(dict(concept))

    return retrieved
