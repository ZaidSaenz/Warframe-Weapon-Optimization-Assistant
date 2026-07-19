# modules/knowledge.py

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


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
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
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


def load_concepts(
    concepts_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Load concept files and index them by their unique ``id``.
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
        concept = _load_json_file(
            path
        )
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

        principles = concept.get(
            "principles",
            [],
        )

        if (
            not isinstance(principles, list)
            or not all(
                isinstance(item, str)
                and item.strip()
                for item in principles
            )
        ):
            raise KnowledgeLoadError(
                "`principles` must be a list "
                f"of non-empty strings: {path}"
            )

        normalized = dict(concept)
        normalized["id"] = normalized_id
        normalized["principles"] = [
            item.strip()
            for item in principles
        ]

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
    Load every rule file and merge their ``rules`` arrays.
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
    rule_ids: set[str] = set()

    for path in sorted(
        directory.glob("*.json")
    ):
        document = _load_json_file(
            path
        )
        file_rules = document.get(
            "rules",
            [],
        )

        if not isinstance(file_rules, list):
            raise KnowledgeLoadError(
                f"`rules` must be a list: {path}"
            )

        for index, rule in enumerate(
            file_rules
        ):
            if not isinstance(rule, dict):
                raise KnowledgeLoadError(
                    "Every rule must be an object: "
                    f"{path} at index {index}"
                )

            rule_id = rule.get("id")

            if (
                not isinstance(rule_id, str)
                or not rule_id.strip()
            ):
                raise KnowledgeLoadError(
                    "Every rule requires a "
                    f"non-empty string `id`: {path}"
                )

            normalized_id = rule_id.strip()

            if normalized_id in rule_ids:
                raise KnowledgeLoadError(
                    f"Duplicate rule id: {normalized_id}"
                )

            rule_ids.add(normalized_id)

            normalized = dict(rule)
            normalized["id"] = normalized_id
            rules.append(normalized)

    if not rules:
        raise KnowledgeLoadError(
            f"No rules found in: {directory}"
        )

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

    return {
        "concepts": load_concepts(
            base_path / "concepts"
        ),
        "rules": load_rules(
            base_path / "rules"
        ),
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
    Return concepts in the requested order without duplicates.

    With ``strict=True``, a missing concept raises
    ``KnowledgeRetrievalError``. With ``strict=False``, it is skipped.
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

        concept = concepts.get(
            concept_id
        )

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
        retrieved.append(
            dict(concept)
        )

    return retrieved