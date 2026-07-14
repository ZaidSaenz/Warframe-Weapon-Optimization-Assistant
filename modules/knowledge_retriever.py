# modules/knowledge_retriever.py

from __future__ import annotations

from typing import Any


class KnowledgeRetrievalError(KeyError):
    """Raised when a requested concept does not exist."""


def retrieve_knowledge(
    concept_ids: list[str],
    concepts: dict[str, dict[str, Any]],
    *,
    strict: bool = True,
) -> list[dict[str, Any]]:
    """
    Retrieve concepts by ID.

    `strict=True` raises an error for missing concepts.
    `strict=False` silently ignores missing concepts.
    """
    retrieved: list[dict[str, Any]] = []

    for concept_id in concept_ids:
        concept = concepts.get(concept_id)

        if concept is None:
            if strict:
                raise KnowledgeRetrievalError(
                    f"Knowledge concept not found: {concept_id}"
                )
            continue

        retrieved.append(concept)

    return retrieved
