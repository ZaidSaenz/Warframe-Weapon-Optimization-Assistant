# modules/weapon_pipeline.py

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from modules.knowledge import (
    load_knowledge_base,
    retrieve_knowledge,
)
from modules.prompt_builder import build_analysis_context
from modules.rule_engine import evaluate_rules
from modules.weapon_interpreter import interpret_weapon


REQUIRED_INTERPRETATION_KEYS = {
    "interpretation_version",
    "signals",
    "flat_signals",
    "mode_profiles",
    "records",
}


@lru_cache(maxsize=1)
def get_knowledge_base() -> dict[str, Any]:
    """
    Cache the local knowledge base so JSON files are not reloaded per request.

    Call `get_knowledge_base.cache_clear()` during development after editing
    concept or rule files.
    """
    return load_knowledge_base()


def _validate_normalized_weapon(
    weapon_data: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Validate the minimum structure expected from the normalized database.

    This function does not normalize or reinterpret source data. It only
    verifies that the selected entry resembles the database schema.
    """
    if not isinstance(
        weapon_data,
        Mapping,
    ):
        raise TypeError(
            "weapon_data must be a Mapping."
        )

    required_sections = (
        "classification",
        "root_stats",
        "shared_stats",
        "attack_modes",
    )

    missing_sections = [
        section
        for section in required_sections
        if section not in weapon_data
    ]

    if missing_sections:
        raise ValueError(
            "Normalized weapon data is missing required sections: "
            + ", ".join(missing_sections)
            + "."
        )

    for section in (
        "classification",
        "root_stats",
        "shared_stats",
    ):
        if not isinstance(
            weapon_data.get(section),
            Mapping,
        ):
            raise ValueError(
                f"{section} must be a Mapping."
            )

    attack_modes = weapon_data.get(
        "attack_modes"
    )

    if not isinstance(
        attack_modes,
        list,
    ):
        raise ValueError(
            "attack_modes must be a list."
        )

    if not attack_modes:
        raise ValueError(
            "attack_modes cannot be empty."
        )

    invalid_modes = [
        index
        for index, mode
        in enumerate(attack_modes)
        if not isinstance(mode, Mapping)
    ]

    if invalid_modes:
        raise ValueError(
            "Every attack mode must be a Mapping. "
            "Invalid indexes: "
            + ", ".join(
                str(index)
                for index in invalid_modes
            )
            + "."
        )

    return dict(weapon_data)


def _validate_interpretation(
    interpretation: Any,
) -> dict[str, Any]:
    if not isinstance(
        interpretation,
        dict,
    ):
        raise TypeError(
            "The weapon interpreter must return a dictionary."
        )

    missing_keys = sorted(
        REQUIRED_INTERPRETATION_KEYS
        - interpretation.keys()
    )

    if missing_keys:
        raise ValueError(
            "Weapon interpretation is missing required keys: "
            + ", ".join(missing_keys)
            + "."
        )

    if not isinstance(
        interpretation["signals"],
        Mapping,
    ):
        raise ValueError(
            "interpretation.signals must be a Mapping."
        )

    if not isinstance(
        interpretation["flat_signals"],
        Mapping,
    ):
        raise ValueError(
            "interpretation.flat_signals must be a Mapping."
        )

    if not isinstance(
        interpretation["mode_profiles"],
        list,
    ):
        raise ValueError(
            "interpretation.mode_profiles must be a list."
        )

    if not isinstance(
        interpretation["records"],
        Mapping,
    ):
        raise ValueError(
            "interpretation.records must be a Mapping."
        )

    return interpretation


def prepare_weapon_analysis(
    weapon_data: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Execute every deterministic stage before prompting the language model.

    Flow:
    normalized weapon
    -> auditable signal derivation
    -> rule evaluation
    -> concept retrieval
    -> analysis-context construction
    """
    normalized_weapon = (
        _validate_normalized_weapon(
            weapon_data
        )
    )

    interpretation = (
        _validate_interpretation(
            interpret_weapon(
                normalized_weapon
            )
        )
    )

    knowledge_base = get_knowledge_base()

    concept_ids = evaluate_rules(
        interpretation=interpretation,
        rules=knowledge_base["rules"],
    )

    retrieved_knowledge = (
        retrieve_knowledge(
            concept_ids=concept_ids,
            concepts=(
                knowledge_base[
                    "concepts"
                ]
            ),
        )
    )

    analysis_context = (
        build_analysis_context(
            interpretation=interpretation,
            retrieved_knowledge=(
                retrieved_knowledge
            ),
        )
    )

    if not isinstance(
        analysis_context,
        str,
    ):
        raise TypeError(
            "build_analysis_context must return a string."
        )

    return {
        "weapon_data": normalized_weapon,
        "interpretation": interpretation,
        "signals": interpretation["signals"],
        "flat_signals": interpretation[
            "flat_signals"
        ],
        "records": interpretation["records"],
        "activated_concepts": concept_ids,
        "retrieved_knowledge": (
            retrieved_knowledge
        ),
        "analysis_context": analysis_context,
    }
