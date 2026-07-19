#modules/weapon_data_profiler.py

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "raw" / "ExportWeapons.json"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "reports" / "weapon_behaviours_profile.json"


def load_weapon_export(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Weapon dataset not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise TypeError(
            f"Expected a JSON object, received {type(data).__name__}."
        )

    return {
        weapon_id: weapon
        for weapon_id, weapon in data.items()
        if isinstance(weapon, dict)
    }


def flatten_paths(
    value: Any,
    prefix: str = "",
) -> set[str]:
    paths: set[str] = set()

    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            paths.update(flatten_paths(child, path))

    elif isinstance(value, list):
        for child in value:
            path = f"{prefix}[]"
            paths.add(path)
            paths.update(flatten_paths(child, path))

    return paths


def get_behaviour_signature(behaviour: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(flatten_paths(behaviour)))


def normalize_reference(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    return text or None


def collect_damage_keys(value: Any) -> set[str]:
    damage_keys: set[str] = set()

    if isinstance(value, dict):
        for key, child in value.items():
            if key.startswith("DT_"):
                damage_keys.add(key)

            damage_keys.update(collect_damage_keys(child))

    elif isinstance(value, list):
        for child in value:
            damage_keys.update(collect_damage_keys(child))

    return damage_keys


def build_behaviour_profile(
    weapons: dict[str, dict[str, Any]],
    *,
    max_examples_per_signature: int = 5,
) -> dict[str, Any]:
    weapons_with_behaviours = 0
    weapons_without_behaviours = 0

    behaviour_count_distribution: Counter[int] = Counter()
    top_level_fields: Counter[str] = Counter()
    nested_paths: Counter[str] = Counter()
    state_names: Counter[str] = Counter()
    damage_types: Counter[str] = Counter()
    product_categories: Counter[str] = Counter()
    signature_counts: Counter[tuple[str, ...]] = Counter()

    signature_examples: dict[
        tuple[str, ...],
        list[dict[str, Any]],
    ] = defaultdict(list)

    suspicious_behaviours: list[dict[str, Any]] = []
    duplicate_behaviour_groups: list[dict[str, Any]] = []

    for weapon_id, weapon in weapons.items():
        category = str(weapon.get("productCategory", "missing"))
        product_categories[category] += 1

        behaviours = weapon.get("behaviours")

        if not isinstance(behaviours, list) or not behaviours:
            weapons_without_behaviours += 1
            behaviour_count_distribution[0] += 1
            continue

        weapons_with_behaviours += 1
        behaviour_count_distribution[len(behaviours)] += 1

        serialized_behaviours: dict[str, list[int]] = defaultdict(list)

        for index, behaviour in enumerate(behaviours):
            if not isinstance(behaviour, dict):
                suspicious_behaviours.append(
                    {
                        "weapon_id": weapon_id,
                        "weapon_name": weapon.get("name"),
                        "reason": "behaviour_is_not_object",
                        "behaviour_index": index,
                        "value_type": type(behaviour).__name__,
                    }
                )
                continue

            top_level_fields.update(behaviour.keys())

            paths = flatten_paths(behaviour)
            nested_paths.update(paths)

            signature = get_behaviour_signature(behaviour)
            signature_counts[signature] += 1

            examples = signature_examples[signature]

            if len(examples) < max_examples_per_signature:
                examples.append(
                    {
                        "weapon_id": weapon_id,
                        "weapon_name": weapon.get("name"),
                        "product_category": category,
                        "behaviour_index": index,
                        "behaviour": behaviour,
                    }
                )

            state_name = normalize_reference(
                behaviour.get("stateName")
            )

            if state_name:
                state_names[state_name] += 1

            damage_types.update(collect_damage_keys(behaviour))

            serialized = json.dumps(
                behaviour,
                sort_keys=True,
                ensure_ascii=False,
            )
            serialized_behaviours[serialized].append(index)

            has_known_component = any(
                field in behaviour
                for field in (
                    "impact",
                    "projectile",
                    "chargedProjectile",
                    "burst",
                )
            )

            if not has_known_component:
                suspicious_behaviours.append(
                    {
                        "weapon_id": weapon_id,
                        "weapon_name": weapon.get("name"),
                        "product_category": category,
                        "reason": "no_known_damage_component",
                        "behaviour_index": index,
                        "behaviour": behaviour,
                    }
                )

        duplicate_sets = [
            indexes
            for indexes in serialized_behaviours.values()
            if len(indexes) > 1
        ]

        if duplicate_sets:
            duplicate_behaviour_groups.append(
                {
                    "weapon_id": weapon_id,
                    "weapon_name": weapon.get("name"),
                    "product_category": category,
                    "duplicate_index_groups": duplicate_sets,
                }
            )

    signatures = []

    for signature, count in signature_counts.most_common():
        signatures.append(
            {
                "count": count,
                "paths": list(signature),
                "examples": signature_examples[signature],
            }
        )

    return {
        "summary": {
            "weapon_count": len(weapons),
            "weapons_with_behaviours": weapons_with_behaviours,
            "weapons_without_behaviours": weapons_without_behaviours,
            "unique_behaviour_signatures": len(signature_counts),
            "weapons_with_exact_duplicate_behaviours": len(
                duplicate_behaviour_groups
            ),
            "suspicious_behaviour_count": len(suspicious_behaviours),
        },
        "behaviour_count_distribution": dict(
            sorted(behaviour_count_distribution.items())
        ),
        "product_categories": dict(
            product_categories.most_common()
        ),
        "top_level_behaviour_fields": dict(
            top_level_fields.most_common()
        ),
        "nested_behaviour_paths": dict(
            nested_paths.most_common()
        ),
        "state_names": dict(
            state_names.most_common()
        ),
        "damage_types": dict(
            damage_types.most_common()
        ),
        "behaviour_signatures": signatures,
        "duplicate_behaviour_groups": duplicate_behaviour_groups,
        "suspicious_behaviours": suspicious_behaviours,
    }


def find_weapon_matches(
    weapons: dict[str, dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    normalized_query = query.casefold()
    matches: list[dict[str, Any]] = []

    for weapon_id, weapon in weapons.items():
        searchable_values = (
            weapon_id,
            weapon.get("name"),
            weapon.get("parentName"),
            weapon.get("description"),
        )

        searchable_text = " ".join(
            str(value)
            for value in searchable_values
            if value is not None
        ).casefold()

        if normalized_query in searchable_text:
            matches.append(
                {
                    "weapon_id": weapon_id,
                    **weapon,
                }
            )

    return matches


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Profile behaviour structures in ExportWeapons.json "
            "before normalization."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Path to ExportWeapons.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT,
        help="Path for the generated profile report.",
    )
    parser.add_argument(
        "--weapon",
        help=(
            "Optional weapon text to search for. "
            "Prints matching raw entries."
        ),
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=5,
        help="Maximum examples saved for each behaviour signature.",
    )

    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    weapons = load_weapon_export(args.input)

    if args.weapon:
        matches = find_weapon_matches(
            weapons,
            args.weapon,
        )

        print(
            json.dumps(
                matches,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    profile = build_behaviour_profile(
        weapons,
        max_examples_per_signature=args.examples,
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            profile,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            profile["summary"],
            ensure_ascii=False,
            indent=2,
        )
    )
    print()
    print(f"Full report saved to: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())