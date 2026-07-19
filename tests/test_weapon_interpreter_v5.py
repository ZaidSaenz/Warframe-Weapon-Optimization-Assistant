from __future__ import annotations

from modules.weapon_interpreter import (
    interpret_weapon,
)


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
            "compatibility_tags": (
                tags or []
            ),
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
                            "impact": 10
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


def test_radial_is_structured_multi_target() -> None:
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
                            "impact": 10
                        },
                    },
                    {
                        "component_type": "projectile_radial",
                        "damage": {
                            "blast": 100
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

    assert result[
        "has_structured_multi_target_evidence"
    ] is True
    assert result[
        "mechanic_profile"
    ]["has_radial_component"] is True
    assert result[
        "special_mechanic_present"
    ] is False


def test_beam_tag_is_not_multi_target_by_itself() -> None:
    weapon = _ranged_weapon(
        trigger_type="continuous",
        tags=["beam"],
    )

    result = interpret_weapon(
        weapon
    )

    assert result["damage_delivery"] == "beam"
    assert result[
        "has_structured_multi_target_evidence"
    ] is False
    assert result[
        "target_profile"
    ] == "single_target"


def test_multiple_instances_do_not_imply_multi_target() -> None:
    weapon = _ranged_weapon(
        modes=[
            {
                "mode_id": "mode_1",
                "trigger_type": "semi_automatic",
                "fire_iterations": 8,
                "damage_components": [
                    {
                        "component_type": "direct",
                        "damage": {
                            "impact": 10
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

    result = interpret_weapon(
        weapon
    )

    assert result[
        "has_multi_instance_evidence"
    ] is True
    assert result[
        "target_profile"
    ] == "single_target"


def test_melee_heavy_fields_do_not_set_primary_damage_behavior() -> None:
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
                            "slash": 100
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

    assert result[
        "damage_behavior"
    ] == "sustained_melee"
    assert result[
        "has_heavy_attack_evidence"
    ] is True
    assert result[
        "melee_profile"
    ] == "mixed_melee"
    assert result[
        "has_structured_multi_target_evidence"
    ] is False
