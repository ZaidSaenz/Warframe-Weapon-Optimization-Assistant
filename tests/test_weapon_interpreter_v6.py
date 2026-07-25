from __future__ import annotations

from modules.weapon_interpreter import interpret_weapon


def _ranged_weapon(
    *,
    trigger_type: str = "automatic",
    tags: list[str] | None = None,
    modes: list[dict] | None = None,
    description: str = "",
) -> dict:
    return {
        "display_name": "Test weapon",
        "display_description": description,
        "classification": {
            "category": "primary",
            "weapon_class": "rifle",
        },
        "shared_stats": {
            "magazine_size": 30,
            "reload_time": 2.0,
            "multishot": 1,
            "trigger_type": trigger_type,
            "compatibility_tags": tags or [],
        },
        "root_stats": {
            "critical_chance_percent": 20,
            "critical_multiplier": 2.0,
            "status_chance_percent": 20,
            "fire_rate": 5.0,
        },
        "attack_modes": modes or [
            {
                "mode_id": "mode_1",
                "trigger_type": trigger_type,
                "fire_iterations": 1,
                "damage_components": [
                    {
                        "component_type": "direct",
                        "damage": {
                            "impact": 10,
                        },
                    }
                ],
                "fire_rate": 5.0,
                "critical_chance_percent": 20,
                "critical_multiplier": 2.0,
                "status_chance_percent": 20,
            }
        ],
    }


def test_interpreter_returns_v6_contract() -> None:
    result = interpret_weapon(
        _ranged_weapon()
    )

    assert result["interpretation_version"] == 6
    assert isinstance(result["signals"], dict)
    assert isinstance(result["flat_signals"], dict)
    assert isinstance(result["mode_profiles"], list)
    assert isinstance(result["records"], dict)

    assert (
        result["signals"]["weapon_category"]["value"]
        == "primary"
    )
    assert (
        result["flat_signals"]["weapon_category"]
        == "primary"
    )


def test_radial_creates_structured_multi_target_record() -> None:
    weapon = _ranged_weapon(
        tags=["aoe", "projectile"],
        modes=[
            {
                "mode_id": "mode_1",
                "trigger_type": "semi_automatic",
                "fire_iterations": 1,
                "damage_components": [
                    {
                        "component_type": "projectile_direct",
                        "damage": {
                            "impact": 10,
                        },
                    },
                    {
                        "component_type": "projectile_radial",
                        "damage": {
                            "blast": 100,
                        },
                    },
                ],
                "fire_rate": 2.0,
                "critical_chance_percent": 20,
                "critical_multiplier": 2.0,
                "status_chance_percent": 20,
            }
        ],
    )

    result = interpret_weapon(
        weapon
    )

    assert (
        result["flat_signals"]["has_radial_component"]
        is True
    )
    assert (
        result["flat_signals"][
            "multi_target_mechanic_records_present"
        ]
        is True
    )

    records = result["records"]["multi_target_mechanics"]

    assert any(
        record["mechanic_type"] == "radial"
        for record in records
    )

    assert (
        result["flat_signals"][
            "special_mechanic_records_present"
        ]
        is False
    )


def test_beam_tag_does_not_imply_multi_target() -> None:
    result = interpret_weapon(
        _ranged_weapon(
            trigger_type="continuous",
            tags=["beam"],
        )
    )

    assert (
        result["flat_signals"]["uses_beam_delivery"]
        is True
    )
    assert (
        result["flat_signals"]["delivery_path"]
        == "beam"
    )
    assert (
        result["flat_signals"][
            "multi_target_mechanic_records_present"
        ]
        is False
    )
    assert (
        result["records"]["multi_target_mechanics"]
        == []
    )


def test_multiple_instances_do_not_imply_multi_target() -> None:
    result = interpret_weapon(
        _ranged_weapon(
            modes=[
                {
                    "mode_id": "mode_1",
                    "trigger_type": "semi_automatic",
                    "fire_iterations": 8,
                    "damage_components": [
                        {
                            "component_type": "direct",
                            "damage": {
                                "impact": 10,
                            },
                        }
                    ],
                    "fire_rate": 2.0,
                    "critical_chance_percent": 20,
                    "critical_multiplier": 2.0,
                    "status_chance_percent": 20,
                }
            ],
        )
    )

    assert (
        result["flat_signals"]["base_instance_count"]
        == 8
    )
    assert (
        result["flat_signals"][
            "multi_target_mechanic_records_present"
        ]
        is False
    )
    assert (
        result["records"]["multi_target_mechanics"]
        == []
    )


def test_description_chaining_is_validated_but_not_structured() -> None:
    result = interpret_weapon(
        _ranged_weapon(
            trigger_type="continuous",
            tags=["beam"],
            description=(
                "A continuous beam that arcs among nearby enemies."
            ),
        )
    )

    assert (
        result["flat_signals"]["has_chaining"]
        is True
    )
    assert (
        result["signals"]["has_chaining"]["confidence"]
        == "validated_description"
    )
    assert (
        result["flat_signals"][
            "multi_target_mechanic_records_present"
        ]
        is True
    )

    records = result["records"]["multi_target_mechanics"]

    assert any(
        record["mechanic_type"] == "chaining"
        and record["confidence"] == "validated_description"
        for record in records
    )


def test_missing_beam_evidence_remains_unknown() -> None:
    result = interpret_weapon(
        _ranged_weapon(
            trigger_type="continuous",
            tags=[],
        )
    )

    assert (
        result["flat_signals"]["uses_beam_delivery"]
        is None
    )
    assert (
        result["signals"]["uses_beam_delivery"]["confidence"]
        == "unavailable"
    )


def test_melee_heavy_fields_create_capability_evidence_only() -> None:
    weapon = {
        "display_name": "Test melee",
        "classification": {
            "category": "melee",
            "weapon_class": "melee",
        },
        "shared_stats": {
            "range": 2.5,
            "heavy_attack_damage": 800,
            "heavy_attack_wind_up": 0.6,
            "slam_attack_damage": 500,
            "slam_radial_damage": 300,
            "slam_radius": 7,
        },
        "root_stats": {
            "critical_chance_percent": 25,
            "critical_multiplier": 2.0,
            "status_chance_percent": 20,
            "fire_rate": 1.1,
        },
        "attack_modes": [
            {
                "mode_id": "mode_1",
                "trigger_type": None,
                "fire_iterations": 1,
                "damage_components": [
                    {
                        "component_type": "direct",
                        "damage": {
                            "slash": 100,
                        },
                    }
                ],
                "fire_rate": 1.1,
                "critical_chance_percent": 25,
                "critical_multiplier": 2.0,
                "status_chance_percent": 20,
            }
        ],
    }

    result = interpret_weapon(
        weapon
    )

    assert (
        result["flat_signals"]["weapon_category"]
        == "melee"
    )
    assert (
        result["flat_signals"][
            "melee_attack_records_present"
        ]
        is True
    )
    assert (
        result["flat_signals"][
            "preparation_friction_present"
        ]
        is True
    )
    assert (
        result["flat_signals"][
            "positioning_friction_present"
        ]
        is True
    )
    assert (
        result["flat_signals"][
            "multi_target_mechanic_records_present"
        ]
        is False
    )
