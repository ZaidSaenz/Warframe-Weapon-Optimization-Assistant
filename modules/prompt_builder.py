# modules/prompt_builder.py

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from modules.logger import get_logger


logger = get_logger(__name__)


JOB_KEYS = (
    "sustained_damage",
    "focused_damage",
    "group_clear",
    "area_control",
    "status_application",
    "precision_attacks",
    "heavy_attacks",
    "general_use",
)

COMFORT_KEYS = (
    "comfortable",
    "manageable",
    "demanding",
    "undetermined",
)

IMPROVEMENT_DIRECTIONS = (
    "reinforce",
    "correct_friction",
    "none",
)

RANGED_CATEGORIES = {
    "primary",
    "secondary",
    "companion",
    "archgun",
    "amp",
    "special",
}

MELEE_CATEGORIES = {
    "melee",
    "archmelee",
    "drifter_melee",
}

ALLOWED_SIGNAL_CONFIDENCE = {
    "structured",
    "normalized",
    "derived",
    "validated_description",
}

PROMPT_SIGNAL_ORDER = (
    "weapon_category",
    "trigger_type",
    "delivery_path",
    "spatial_application",
    "uses_beam_delivery",
    "critical_chance",
    "critical_multiplier",
    "critical_profile_present",
    "status_chance",
    "status_profile_present",
    "base_instance_count",
    "multishot",
    "has_radial_component",
    "has_chaining",
    "has_repeatable_attack_cycle",
    "mechanical_application_continuity_present",
    "recovery_model",
    "reload_time",
    "preparation_friction_present",
    "interruption_friction_present",
    "handling_friction_present",
    "positioning_friction_present",
    "tracking_friction_present",
    "attack_mode_records_count",
    "multi_target_mechanic_records_present",
    "special_mechanic_records_present",
)

CONCEPT_SIGNAL_PREFERENCES = {
    "ammo_consumption": (
        "ammo_reserve_model",
        "ammo_regeneration_present",
        "ammo_cost_per_consumption_event",
    ),
    "attack_rhythm": (
        "trigger_type",
        "has_spool_up_evidence",
        "has_press_release_evidence",
        "has_secondary_activation_evidence",
    ),
    "beam_behavior": (
        "uses_beam_delivery",
        "delivery_path",
    ),
    "critical_profile": (
        "critical_profile_present",
    ),
    "damage_delivery": (
        "delivery_path",
        "spatial_application",
    ),
    "description_evidence": (
        "validated_description_mechanic_present",
    ),
    "improvement_selection": (),
    "melee_behavior": (
        "weapon_category",
        "melee_attack_records_present",
    ),
    "multi_instance_delivery": (
        "base_instance_count",
        "multishot",
        "distributed_instance_profile_present",
    ),
    "multi_mode_behavior": (
        "attack_mode_records_count",
        "has_mode_state_evidence",
    ),
    "multi_target_delivery": (
        "has_radial_component",
        "has_chaining",
        "multi_target_mechanic_records_present",
    ),
    "operational_comfort": (
        "operational_friction_records_present",
        "preparation_friction_present",
        "interruption_friction_present",
        "handling_friction_present",
        "positioning_friction_present",
        "tracking_friction_present",
    ),
    "primary_job_selection": (),
    "reload_friction": (
        "recovery_model",
        "reload_time",
        "interruption_friction_present",
    ),
    "special_mechanic_review": (
        "special_mechanic_records_present",
        "structured_special_mechanic_present",
    ),
    "status_application": (
        "status_profile_present",
        "status_chance",
        "eligible_status_opportunity_profile_present",
    ),
    "sustained_damage": (
        "has_repeatable_attack_cycle",
        "mechanical_application_continuity_present",
        "sustained_cycle_profile_present",
    ),
}


SYSTEM_PROMPT = """
You are a technical Warframe weapon analyst.

Use only:
1. normalized weapon data supplied by the application;
2. deterministic evidence records;
3. retrieved knowledge concepts;
4. exact generation constraints.

Do not reconstruct mechanics from the weapon name.
Do not invent missing statistics, builds, mods, external equipment, enemies,
missions, damage calculations, or unsupported operational problems.
Do not treat unavailable or heuristic evidence as confirmed.
Separate combat function from operational comfort.
Explain relationships instead of listing raw values.
Answer explanatory fields in clear, concise Spanish.

Select exactly one primary job:
- sustained_damage
- focused_damage
- group_clear
- area_control
- status_application
- precision_attacks
- heavy_attacks
- general_use

Use improvement parameters only from allowed_improvement_parameters.
Use "none" only as the sole improvement with direction "none".
Do not recommend changing intrinsic mechanics.

Return only one valid JSON object:

{
  "behavior_summary_es": "one or two Spanish sentences",
  "primary_job": "one exact primary-job enum value",
  "job_reason_es": "one or two Spanish sentences",
  "strengths_es": [
    "zero to three short Spanish items"
  ],
  "limitations_es": [
    "zero to three short Spanish items"
  ],
  "improvement_priorities": [
    {
      "parameter": "one exact allowed parameter or none",
      "direction": "reinforce, correct_friction, or none",
      "reason_es": "short Spanish reason grounded in supplied evidence"
    }
  ],
  "comfort": {
    "rating": "comfortable, manageable, demanding, or undetermined",
    "reason_es": "one or two Spanish sentences"
  }
}
""".strip()


class PromptBuilderError(ValueError):
    """Raised when prompt input is missing or malformed."""


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _is_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _mapping(value: Any) -> Mapping[str, Any]:
    return (
        value
        if isinstance(value, Mapping)
        else {}
    )


def _clean_text_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    return [
        item.strip()
        for item in value
        if isinstance(item, str)
        and item.strip()
    ]


def _concept_id(
    concept: Mapping[str, Any],
) -> str:
    value = concept.get("id")
    return (
        str(value).strip()
        if value
        else ""
    )


def _signal_record(
    interpretation: Mapping[str, Any],
    field: str,
) -> Mapping[str, Any]:
    signals = interpretation.get("signals")

    if not isinstance(signals, Mapping):
        return {}

    record = signals.get(field)

    return (
        record
        if isinstance(record, Mapping)
        else {}
    )


def _signal_value(
    interpretation: Mapping[str, Any],
    field: str,
) -> Any:
    record = _signal_record(
        interpretation,
        field,
    )

    if "value" in record:
        return record.get("value")

    flat_signals = interpretation.get(
        "flat_signals"
    )

    if isinstance(flat_signals, Mapping):
        return flat_signals.get(field)

    return None


def _signal_is_prompt_safe(
    record: Mapping[str, Any],
) -> bool:
    value = record.get("value")
    confidence = record.get("confidence")

    return (
        value is not None
        and confidence
        in ALLOWED_SIGNAL_CONFIDENCE
    )


def _compact_signals(
    interpretation: Mapping[str, Any],
) -> dict[str, Any]:
    compact: dict[str, Any] = {}

    for field in PROMPT_SIGNAL_ORDER:
        record = _signal_record(
            interpretation,
            field,
        )

        if not _signal_is_prompt_safe(
            record
        ):
            continue

        compact[field] = {
            "value": record.get("value"),
            "confidence": record.get(
                "confidence"
            ),
        }

    return compact


def _legacy_interpretation_lines(
    interpretation: Mapping[str, Any],
) -> list[str]:
    """
    Preserve the previous readable context surface for legacy tests and tools.

    This compatibility view is only used when the interpretation does not
    contain the v6 `signals` contract.
    """
    if isinstance(
        interpretation.get("signals"),
        Mapping,
    ):
        return []

    lines: list[str] = []

    for key, value in interpretation.items():
        if (
            key == "evidence"
            or not _is_present(value)
        ):
            continue

        readable_key = (
            str(key)
            .replace("_", " ")
            .capitalize()
        )

        lines.append(
            f"{readable_key}: {value}"
        )

    return lines


def _compact_records(
    interpretation: Mapping[str, Any],
) -> dict[str, Any]:
    records = interpretation.get("records")

    if not isinstance(records, Mapping):
        return {}

    compact: dict[str, Any] = {}

    for key in (
        "description_claims",
        "multi_target_mechanics",
        "special_mechanics",
        "operational_friction",
    ):
        value = records.get(key)

        if isinstance(value, list) and value:
            compact[key] = value

    return compact


def _candidate_signal_fields(
    concept: Mapping[str, Any],
) -> tuple[str, ...]:
    concept_id = _concept_id(concept)
    candidates: list[str] = []

    signal_fields = concept.get(
        "signal_fields"
    )

    if isinstance(signal_fields, list):
        candidates.extend(
            str(field).strip()
            for field in signal_fields
            if isinstance(field, str)
            and field.strip()
        )

    candidates.extend(
        CONCEPT_SIGNAL_PREFERENCES.get(
            concept_id,
            (),
        )
    )

    return tuple(
        dict.fromkeys(candidates)
    )


def _select_interpretation_branch(
    concept: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> tuple[str | None, Any, list[str]]:
    branches = concept.get(
        "interpretation"
    )

    if not isinstance(branches, Mapping):
        return None, None, []

    for field in _candidate_signal_fields(
        concept
    ):
        actual = _signal_value(
            interpretation,
            field,
        )

        if actual is None:
            continue

        branch = branches.get(
            str(actual)
        )

        if branch is None:
            branch = branches.get(actual)

        selected = _clean_text_items(
            branch
        )

        if selected:
            return field, actual, selected

    return None, None, []


def _select_conditional_exceptions(
    concept: Mapping[str, Any],
    interpretation: Mapping[str, Any],
) -> list[str]:
    conditional = concept.get(
        "conditional_exceptions"
    )

    if not isinstance(
        conditional,
        Mapping,
    ):
        return []

    selected: list[str] = []

    for field, branches in (
        conditional.items()
    ):
        if not isinstance(
            branches,
            Mapping,
        ):
            continue

        actual = _signal_value(
            interpretation,
            str(field),
        )

        branch = branches.get(
            str(actual)
        )

        selected.extend(
            _clean_text_items(branch)
        )

    return selected


def _build_knowledge_payload(
    interpretation: Mapping[str, Any],
    retrieved_knowledge: Sequence[
        Mapping[str, Any]
    ],
    *,
    max_principles_per_concept: int,
    max_exceptions_per_concept: int,
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    seen_text: set[str] = set()

    for concept in retrieved_knowledge:
        if not isinstance(
            concept,
            Mapping,
        ):
            continue

        concept_id = _concept_id(
            concept
        )

        if not concept_id:
            continue

        field, actual, branch_items = (
            _select_interpretation_branch(
                concept,
                interpretation,
            )
        )

        principles = _clean_text_items(
            concept.get("principles")
        )[:max_principles_per_concept]

        exceptions = (
            _clean_text_items(
                concept.get("exceptions")
            )
            + _select_conditional_exceptions(
                concept,
                interpretation,
            )
        )[:max_exceptions_per_concept]

        def unique(
            items: list[str],
        ) -> list[str]:
            result: list[str] = []

            for item in items:
                if item in seen_text:
                    continue

                seen_text.add(item)
                result.append(item)

            return result

        branch_items = unique(branch_items)
        principles = unique(principles)
        exceptions = unique(exceptions)

        concept_payload: dict[str, Any] = {
            "id": concept_id,
        }

        title = concept.get("title")

        if isinstance(title, str) and title.strip():
            concept_payload["title"] = (
                title.strip()
            )

        if field and branch_items:
            concept_payload[
                "selected_branch"
            ] = {
                "field": field,
                "value": actual,
                "guidance": branch_items,
            }

        if principles:
            concept_payload[
                "principles"
            ] = principles

        if exceptions:
            concept_payload[
                "constraints"
            ] = exceptions

        if len(concept_payload) > 1:
            payload.append(concept_payload)

    return payload


def build_analysis_context(
    interpretation: Mapping[str, Any],
    retrieved_knowledge: list[dict[str, Any]],
    *,
    max_principles_per_concept: int = 2,
    max_exceptions_per_concept: int = 2,
) -> str:
    """
    Build compact context from v6 evidence and activated knowledge only.

    Heuristic and unavailable signals are excluded from the prompt-facing
    signal payload. Full audit data remains available in the pipeline output.
    """
    if not isinstance(
        interpretation,
        Mapping,
    ):
        raise PromptBuilderError(
            "interpretation must be a Mapping."
        )

    if not isinstance(
        retrieved_knowledge,
        list,
    ):
        raise PromptBuilderError(
            "retrieved_knowledge must be a list."
        )

    compact_signals = _compact_signals(
        interpretation
    )
    compact_records = _compact_records(
        interpretation
    )
    knowledge_payload = (
        _build_knowledge_payload(
            interpretation,
            retrieved_knowledge,
            max_principles_per_concept=(
                max_principles_per_concept
            ),
            max_exceptions_per_concept=(
                max_exceptions_per_concept
            ),
        )
    )

    context_payload = {
        "deterministic_signals": (
            compact_signals
        ),
        "relevant_records": (
            compact_records
        ),
        "retrieved_knowledge": (
            knowledge_payload
        ),
    }

    legacy_lines = _legacy_interpretation_lines(
        interpretation
    )

    deterministic_section = (
        "\n".join(legacy_lines)
        if legacy_lines
        else _json(
            context_payload[
                "deterministic_signals"
            ]
        )
    )

    return (
        "DETERMINISTIC INTERPRETATION:\n"
        + deterministic_section
        + "\n\nRELEVANT RECORDS:\n"
        + _json(
            context_payload[
                "relevant_records"
            ]
        )
        + "\n\nRELEVANT KNOWLEDGE:\n"
        + _json(
            context_payload[
                "retrieved_knowledge"
            ]
        )
    )


def _primary_mode(
    weapon_data: Mapping[str, Any],
) -> Mapping[str, Any]:
    modes = weapon_data.get(
        "attack_modes"
    )

    if not isinstance(modes, list):
        return {}

    for mode in modes:
        if isinstance(mode, Mapping):
            return mode

    return {}


def available_improvement_parameters(
    weapon_data: Mapping[str, Any],
) -> tuple[str, ...]:
    parameters: list[str] = []

    classification = _mapping(
        weapon_data.get("classification")
    )
    shared_stats = _mapping(
        weapon_data.get("shared_stats")
    )
    root_stats = _mapping(
        weapon_data.get("root_stats")
    )
    mode = _primary_mode(
        weapon_data
    )

    core_parameter_map = (
        (
            "critical_chance_percent",
            "critical_chance",
        ),
        (
            "critical_multiplier",
            "critical_multiplier",
        ),
        (
            "status_chance_percent",
            "status_chance",
        ),
        (
            "total_damage",
            "base_damage",
        ),
    )

    for source_key, parameter_key in (
        core_parameter_map
    ):
        value = (
            mode.get(source_key)
            if _is_present(
                mode.get(source_key)
            )
            else root_stats.get(
                source_key
            )
        )

        if _is_present(value):
            parameters.append(
                parameter_key
            )

    category = classification.get(
        "category"
    )

    if category in RANGED_CATEGORIES:
        candidates = (
            (
                mode.get("fire_rate")
                if _is_present(
                    mode.get("fire_rate")
                )
                else root_stats.get(
                    "fire_rate"
                ),
                "fire_rate",
            ),
            (
                shared_stats.get(
                    "multishot"
                ),
                "multishot",
            ),
            (
                shared_stats.get(
                    "magazine_size"
                ),
                "magazine_size",
            ),
            (
                shared_stats.get(
                    "reload_time"
                ),
                "reload_time",
            ),
            (
                shared_stats.get(
                    "accuracy"
                ),
                "accuracy",
            ),
            (
                shared_stats.get(
                    "range"
                ),
                "range",
            ),
        )

    elif category in MELEE_CATEGORIES:
        candidates = (
            (
                mode.get("fire_rate")
                if _is_present(
                    mode.get("fire_rate")
                )
                else root_stats.get(
                    "fire_rate"
                ),
                "attack_speed",
            ),
            (
                shared_stats.get(
                    "range"
                ),
                "melee_range",
            ),
            (
                shared_stats.get(
                    "heavy_attack_damage"
                ),
                "heavy_attack_damage",
            ),
            (
                shared_stats.get(
                    "heavy_attack_wind_up"
                ),
                "heavy_attack_wind_up",
            ),
        )

    else:
        candidates = ()

    for value, parameter_key in candidates:
        if _is_present(value):
            parameters.append(
                parameter_key
            )

    return tuple(
        dict.fromkeys(parameters)
    )


def available_operational_fields(
    weapon_data: Mapping[str, Any],
) -> tuple[str, ...]:
    fields: list[str] = []

    classification = _mapping(
        weapon_data.get("classification")
    )
    shared_stats = _mapping(
        weapon_data.get("shared_stats")
    )
    root_stats = _mapping(
        weapon_data.get("root_stats")
    )
    mode = _primary_mode(
        weapon_data
    )

    category = classification.get(
        "category"
    )

    if category in RANGED_CATEGORIES:
        field_map = (
            (
                mode.get("trigger_type")
                or shared_stats.get(
                    "trigger_type"
                ),
                "trigger_type",
            ),
            (
                mode.get("fire_rate")
                if _is_present(
                    mode.get("fire_rate")
                )
                else root_stats.get(
                    "fire_rate"
                ),
                "fire_rate",
            ),
            (
                shared_stats.get(
                    "magazine_size"
                ),
                "magazine_size",
            ),
            (
                shared_stats.get(
                    "reload_time"
                ),
                "reload_time",
            ),
            (
                shared_stats.get(
                    "accuracy"
                ),
                "accuracy",
            ),
            (
                shared_stats.get(
                    "range"
                ),
                "range",
            ),
            (
                shared_stats.get(
                    "noise"
                ),
                "noise",
            ),
        )

    elif category in MELEE_CATEGORIES:
        field_map = (
            (
                mode.get("fire_rate")
                if _is_present(
                    mode.get("fire_rate")
                )
                else root_stats.get(
                    "fire_rate"
                ),
                "attack_speed",
            ),
            (
                shared_stats.get(
                    "range"
                ),
                "melee_range",
            ),
            (
                shared_stats.get(
                    "heavy_attack_wind_up"
                ),
                "heavy_attack_wind_up",
            ),
        )

    else:
        field_map = ()

    for value, field_name in field_map:
        if _is_present(value):
            fields.append(field_name)

    return tuple(
        dict.fromkeys(fields)
    )


def absent_operational_fields(
    weapon_data: Mapping[str, Any],
) -> tuple[str, ...]:
    relevant_fields = {
        "accuracy",
        "recoil",
        "charge_time",
        "projectile_speed",
        "beam_range",
        "ammo_capacity",
        "ammo_pickup",
        "ammo_cost_per_damage_tick",
    }

    present = set(
        available_operational_fields(
            weapon_data
        )
    )

    return tuple(
        sorted(
            relevant_fields - present
        )
    )


def _safe_weapon_data(
    weapon_data: Mapping[str, Any],
) -> dict[str, Any]:
    classification = dict(
        _mapping(
            weapon_data.get(
                "classification"
            )
        )
    )
    shared_stats = dict(
        _mapping(
            weapon_data.get(
                "shared_stats"
            )
        )
    )
    root_stats = dict(
        _mapping(
            weapon_data.get(
                "root_stats"
            )
        )
    )

    modes: list[dict[str, Any]] = []

    raw_modes = weapon_data.get(
        "attack_modes"
    )

    if isinstance(raw_modes, list):
        for raw_mode in raw_modes:
            if isinstance(
                raw_mode,
                Mapping,
            ):
                modes.append(
                    dict(raw_mode)
                )

    safe = {
        "weapon_name": (
            weapon_data.get(
                "display_name"
            )
        ),
        "classification": (
            classification
        ),
        "shared_stats": shared_stats,
        "root_stats": root_stats,
        "attack_modes": modes,
    }

    description = weapon_data.get(
        "display_description"
    )

    if _is_present(description):
        safe[
            "description_reference"
        ] = description

    return {
        key: value
        for key, value in safe.items()
        if _is_present(value)
    }


def build_weapon_prompt(
    weapon_data: Mapping[str, Any],
    analysis_context: str,
) -> str:
    """
    Build the single prompt used by the local generation stage.
    """
    if not isinstance(
        weapon_data,
        Mapping,
    ):
        raise PromptBuilderError(
            "weapon_data must be a Mapping."
        )

    context = str(
        analysis_context or ""
    ).strip()

    if not context:
        raise PromptBuilderError(
            "analysis_context cannot be empty."
        )

    safe_weapon_data = (
        _safe_weapon_data(
            weapon_data
        )
    )

    allowed_parameters = list(
        available_improvement_parameters(
            weapon_data
        )
    )

    operational_fields = list(
        available_operational_fields(
            weapon_data
        )
    )

    absent_fields = list(
        absent_operational_fields(
            weapon_data
        )
    )

    generation_constraints = {
        "allowed_primary_jobs": list(
            JOB_KEYS
        ),
        "allowed_comfort_ratings": list(
            COMFORT_KEYS
        ),
        "allowed_improvement_directions":
            list(
                IMPROVEMENT_DIRECTIONS
            ),
        "allowed_improvement_parameters": [
            *allowed_parameters,
            "none",
        ],
        "available_operational_fields":
            operational_fields,
        "absent_operational_fields":
            absent_fields,
        "unavailable_evidence_is_not_false":
            True,
        "heuristic_evidence_is_not_confirmed":
            True,
        "intrinsic_mechanics_are_not_improvement_parameters":
            True,
    }

    prompt = (
        "Analyze the following normalized weapon.\n\n"
        "NORMALIZED WEAPON DATA:\n"
        f"{_json(safe_weapon_data)}\n\n"
        f"{context}\n\n"
        "GENERATION CONSTRAINTS:\n"
        f"{_json(generation_constraints)}\n\n"
        "TASK:\n"
        "Produce the exact JSON object required by the system prompt. "
        "Use only supplied normalized data, deterministic evidence, and "
        "retrieved knowledge. Every improvement parameter must exactly match "
        "one allowed_improvement_parameters value. Do not discuss absent "
        "operational fields. Do not turn unknown evidence into a negative "
        "claim. Select the primary job that best describes the complete "
        "practical attack pattern."
    )

    logger.info(
        "Weapon prompt built | characters=%d "
        "| context_characters=%d "
        "| allowed_parameters=%s "
        "| absent_operational_fields=%s",
        len(prompt),
        len(context),
        (
            ",".join(
                allowed_parameters
            )
            or "none"
        ),
        (
            ",".join(absent_fields)
            or "none"
        ),
    )

    return prompt
