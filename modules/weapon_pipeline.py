# modules/weapon_pipeline.py

from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable

from modules.context_builder import build_analysis_context
from modules.knowledge_loader import load_knowledge_base
from modules.knowledge_retriever import retrieve_knowledge
from modules.rule_engine import evaluate_rules


@lru_cache(maxsize=1)
def get_knowledge_base() -> dict[str, Any]:
    """
    Cache the local knowledge base so JSON files are not reloaded per request.

    Call `get_knowledge_base.cache_clear()` during development after editing
    knowledge files.
    """
    return load_knowledge_base()


def prepare_weapon_analysis(
    raw_data: dict[str, Any],
    *,
    parser: Callable[[dict[str, Any]], dict[str, Any]],
    interpreter: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """
    Execute every deterministic stage before prompting the language model.

    Existing project functions are injected to avoid coupling this module
    to an interface that may still be changing.
    """
    weapon_data = parser(raw_data)
    interpretation = interpreter(weapon_data)

    if not isinstance(weapon_data, dict):
        raise TypeError("The weapon parser must return a dictionary.")

    if not isinstance(interpretation, dict):
        raise TypeError("The weapon interpreter must return a dictionary.")

    knowledge_base = get_knowledge_base()

    concept_ids = evaluate_rules(
        interpretation=interpretation,
        rules=knowledge_base["rules"],
    )

    retrieved_knowledge = retrieve_knowledge(
        concept_ids=concept_ids,
        concepts=knowledge_base["concepts"],
    )

    analysis_context = build_analysis_context(
        interpretation=interpretation,
        retrieved_knowledge=retrieved_knowledge,
    )

    return {
        "weapon_data": weapon_data,
        "interpretation": interpretation,
        "activated_concepts": concept_ids,
        "retrieved_knowledge": retrieved_knowledge,
        "analysis_context": analysis_context,
    }


def analyze_weapon(
    raw_data: dict[str, Any],
    *,
    parser: Callable[[dict[str, Any]], dict[str, Any]],
    interpreter: Callable[[dict[str, Any]], dict[str, Any]],
    prompt_builder: Callable[..., str],
    generator: Callable[[str], str],
) -> str:
    """
    Run the complete local RAG pipeline and return the model response.

    Expected prompt_builder signature:
        build_weapon_prompt(
            weapon_data=<dict>,
            analysis_context=<str>,
        ) -> str
    """
    prepared = prepare_weapon_analysis(
        raw_data,
        parser=parser,
        interpreter=interpreter,
    )

    prompt = prompt_builder(
        weapon_data=prepared["weapon_data"],
        analysis_context=prepared["analysis_context"],
    )

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("The prompt builder returned an empty prompt.")

    return generator(prompt)
