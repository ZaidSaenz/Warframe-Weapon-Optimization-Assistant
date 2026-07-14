# modules/knowledge_loader.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KNOWLEDGE_PATH = PROJECT_ROOT / "knowledge"


class KnowledgeLoadError(RuntimeError):
    """Raised when the local knowledge base cannot be loaded safely."""


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise KnowledgeLoadError(f"Knowledge file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise KnowledgeLoadError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(data, dict):
        raise KnowledgeLoadError(f"Knowledge file must contain a JSON object: {path}")

    return data


def load_concepts(
    concepts_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Load all concept JSON files and index them by their unique `id`.
    """
    directory = concepts_path or DEFAULT_KNOWLEDGE_PATH / "concepts"

    if not directory.exists():
        raise KnowledgeLoadError(f"Concept directory not found: {directory}")

    concepts: dict[str, dict[str, Any]] = {}

    for path in sorted(directory.glob("*.json")):
        concept = _load_json_file(path)
        concept_id = concept.get("id")

        if not isinstance(concept_id, str) or not concept_id.strip():
            raise KnowledgeLoadError(
                f"Concept file requires a non-empty string `id`: {path}"
            )

        if concept_id in concepts:
            raise KnowledgeLoadError(f"Duplicate concept id: {concept_id}")

        principles = concept.get("principles", [])
        if not isinstance(principles, list) or not all(
            isinstance(item, str) for item in principles
        ):
            raise KnowledgeLoadError(
                f"`principles` must be a list of strings: {path}"
            )

        concepts[concept_id] = concept

    if not concepts:
        raise KnowledgeLoadError(f"No concept JSON files found in: {directory}")

    return concepts


def load_rules(
    rules_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Load all rule JSON files and merge their `rules` arrays.
    """
    directory = rules_path or DEFAULT_KNOWLEDGE_PATH / "rules"

    if not directory.exists():
        raise KnowledgeLoadError(f"Rule directory not found: {directory}")

    rules: list[dict[str, Any]] = []
    rule_ids: set[str] = set()

    for path in sorted(directory.glob("*.json")):
        document = _load_json_file(path)
        file_rules = document.get("rules", [])

        if not isinstance(file_rules, list):
            raise KnowledgeLoadError(f"`rules` must be a list: {path}")

        for rule in file_rules:
            if not isinstance(rule, dict):
                raise KnowledgeLoadError(f"Every rule must be an object: {path}")

            rule_id = rule.get("id")
            if not isinstance(rule_id, str) or not rule_id.strip():
                raise KnowledgeLoadError(
                    f"Every rule requires a non-empty string `id`: {path}"
                )

            if rule_id in rule_ids:
                raise KnowledgeLoadError(f"Duplicate rule id: {rule_id}")

            rule_ids.add(rule_id)
            rules.append(rule)

    if not rules:
        raise KnowledgeLoadError(f"No rules found in: {directory}")

    return rules


def load_knowledge_base(
    knowledge_path: Path | None = None,
) -> dict[str, Any]:
    """
    Load the complete deterministic RAG knowledge base.
    """
    base_path = knowledge_path or DEFAULT_KNOWLEDGE_PATH

    return {
        "concepts": load_concepts(base_path / "concepts"),
        "rules": load_rules(base_path / "rules"),
    }
