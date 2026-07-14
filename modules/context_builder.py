# modules/context_builder.py

from __future__ import annotations

from typing import Any


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"

    if isinstance(value, list):
        return ", ".join(str(item) for item in value)

    return str(value)


def _format_interpretation(
    interpretation: dict[str, Any],
) -> list[str]:
    ignored_fields = {"confidence", "evidence"}
    lines: list[str] = []

    for key, value in interpretation.items():
        if key in ignored_fields or value in (None, "", [], {}):
            continue

        readable_key = key.replace("_", " ").capitalize()
        lines.append(f"- {readable_key}: {_format_value(value)}")

    evidence = interpretation.get("evidence")
    if isinstance(evidence, dict) and evidence:
        lines.append("")
        lines.append("EVIDENCE USED:")

        for conclusion, fields in evidence.items():
            if not fields:
                continue
            readable_conclusion = conclusion.replace("_", " ")
            lines.append(
                f"- {readable_conclusion}: {_format_value(fields)}"
            )

    return lines


def _format_knowledge(
    retrieved_knowledge: list[dict[str, Any]],
    max_principles_per_concept: int,
) -> list[str]:
    lines: list[str] = []
    seen_principles: set[str] = set()

    for concept in retrieved_knowledge:
        title = concept.get("title") or concept.get("id", "Unnamed concept")
        principles = concept.get("principles", [])

        if not isinstance(principles, list):
            continue

        selected = [
            principle
            for principle in principles
            if isinstance(principle, str) and principle.strip()
        ][:max_principles_per_concept]

        unique = [
            principle
            for principle in selected
            if principle not in seen_principles
        ]

        if not unique:
            continue

        lines.append(f"{title}:")

        for principle in unique:
            seen_principles.add(principle)
            lines.append(f"- {principle}")

        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()

    return lines


def build_analysis_context(
    interpretation: dict[str, Any],
    retrieved_knowledge: list[dict[str, Any]],
    *,
    max_principles_per_concept: int = 3,
) -> str:
    """
    Build a compact deterministic context block for the language model.
    """
    sections: list[str] = []

    interpretation_lines = _format_interpretation(interpretation)
    sections.append(
        "DETERMINISTIC INTERPRETATION:\n"
        + ("\n".join(interpretation_lines) or "- No interpretation available.")
    )

    knowledge_lines = _format_knowledge(
        retrieved_knowledge,
        max_principles_per_concept,
    )
    sections.append(
        "RELEVANT KNOWLEDGE:\n"
        + ("\n".join(knowledge_lines) or "- No additional knowledge retrieved.")
    )

    return "\n\n".join(sections)
