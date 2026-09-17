"""
Warframe localization helper.

Crosses English and Spanish localization dictionaries using
their shared internal localization keys.

The language model receives only a compact glossary, never the
multi-megabyte dictionaries themselves.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


ENGLISH_DICTIONARY_PATH = Path(
    "data/raw/dict.en.json"
)

SPANISH_DICTIONARY_PATH = Path(
    "data/raw/dict.es.json"
)


# ------------------------------------------------------------
# These are fallbacks only.
#
# Whenever an exact English term exists in the Warframe
# localization dictionaries, the dictionary translation wins.
# ------------------------------------------------------------

FALLBACK_TERMS: dict[str, str] = {
    "Critical Chance":
        "Probabilidad crítica",

    "Critical Multiplier":
        "Multiplicador crítico",

    "Status Chance":
        "Probabilidad de estado",

    "Fire Rate":
        "Cadencia de fuego",

    "Magazine":
        "Cargador",

    "Reload":
        "Recarga",

    "Damage":
        "Daño",

    "Multishot":
        "Multidisparo",

    "Riven Disposition":
        "Disposición Riven",

    "Impact":
        "Impacto",

    "Puncture":
        "Perforación",

    "Slash":
        "Corte",

    "Electricity":
        "Electricidad",

    "Heat":
        "Calor",

    "Cold":
        "Frío",

    "Toxin":
        "Toxina",

    "Blast":
        "Explosión",

    "Corrosive":
        "Corrosivo",

    "Gas":
        "Gas",

    "Magnetic":
        "Magnético",

    "Radiation":
        "Radiación",

    "Viral":
        "Viral",
}


def load_dictionary(
    path: Path,
) -> dict[str, str]:
    if not path.exists():
        return {}

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        raw = json.load(file)

    if not isinstance(
        raw,
        dict,
    ):
        return {}

    result: dict[
        str,
        str,
    ] = {}

    for key, value in raw.items():
        if (
            isinstance(key, str)
            and isinstance(value, str)
        ):
            result[key] = value

    return result


class WarframeLocalization:

    def __init__(
        self,
        english_path: Path = ENGLISH_DICTIONARY_PATH,
        spanish_path: Path = SPANISH_DICTIONARY_PATH,
    ) -> None:
        self.english = load_dictionary(
            english_path
        )

        self.spanish = load_dictionary(
            spanish_path
        )

        self.shared_keys = (
            self.english.keys()
            & self.spanish.keys()
        )

        self._english_to_spanish: dict[
            str,
            str,
        ] = {}

        for key in self.shared_keys:
            english_text = (
                self.english[key]
                .strip()
            )

            spanish_text = (
                self.spanish[key]
                .strip()
            )

            if (
                not english_text
                or not spanish_text
            ):
                continue

            normalized = (
                english_text.casefold()
            )

            self._english_to_spanish.setdefault(
                normalized,
                spanish_text,
            )

    def translate_exact(
        self,
        english_text: str,
    ) -> str | None:
        """
        Translate an exact localized English string using
        the corresponding Warframe localization entry.
        """

        if not isinstance(
            english_text,
            str,
        ):
            return None

        normalized = (
            english_text
            .strip()
            .casefold()
        )

        if not normalized:
            return None

        return self._english_to_spanish.get(
            normalized
        )

    def translate_term(
        self,
        english_term: str,
    ) -> tuple[
        str | None,
        str,
    ]:
        """
        Returns:
            (translation, source)

        source:
            "warframe_dictionary"
            "fallback"
            "missing"
        """

        translated = (
            self.translate_exact(
                english_term
            )
        )

        if translated:
            return (
                translated,
                "warframe_dictionary",
            )

        fallback = FALLBACK_TERMS.get(
            english_term
        )

        if fallback:
            return (
                fallback,
                "fallback",
            )

        return (
            None,
            "missing",
        )

    def glossary(
        self,
    ) -> dict[
        str,
        dict[str, str],
    ]:
        result: dict[
            str,
            dict[str, str],
        ] = {}

        for english_term in (
            FALLBACK_TERMS
        ):
            translation, source = (
                self.translate_term(
                    english_term
                )
            )

            if translation is None:
                continue

            result[
                english_term
            ] = {
                "es":
                    translation,

                "source":
                    source,
            }

        return result

    def prompt_context(
        self,
    ) -> str:
        """
        Compact terminology context for the language model.
        """

        lines = [
            (
                "Warframe Spanish terminology:"
            ),
            (
                "When answering in Spanish, preserve Warframe "
                "proper names and prefer these translations:"
            ),
        ]

        for (
            english_term,
            data,
        ) in self.glossary().items():

            lines.append(
                f"- {english_term} -> "
                f"{data['es']}"
            )

        lines.extend(
            [
                (
                    "- Keep the term 'Riven' spelled exactly as Riven."
                ),
                (
                    "- Do not translate weapon names unless an official "
                    "localized name is explicitly provided."
                ),
                (
                    "- Translate technical fields by their gameplay meaning, "
                    "not by loose synonyms."
                ),
            ]
        )

        return "\n".join(
            lines
        )

    def localize_tool_result(
        self,
        result: dict[
            str,
            Any,
        ],
    ) -> dict[
        str,
        Any,
    ]:
        """
        Add exact Spanish localization where it can be resolved
        deterministically.

        Original canonical English fields remain untouched.
        """

        localized = copy.deepcopy(
            result
        )

        weapon = localized.get(
            "weapon"
        )

        if not isinstance(
            weapon,
            dict,
        ):
            return localized

        description = weapon.get(
            "official_description"
        )

        if isinstance(
            description,
            str,
        ):
            translated = (
                self.translate_exact(
                    description
                )
            )

            if (
                translated
                and translated != description
            ):
                weapon[
                    "official_description_es"
                ] = translated

        return localized

    def summary(
        self,
    ) -> dict[
        str,
        int,
    ]:
        return {
            "english_entries":
                len(
                    self.english
                ),

            "spanish_entries":
                len(
                    self.spanish
                ),

            "shared_keys":
                len(
                    self.shared_keys
                ),

            "exact_translation_index":
                len(
                    self._english_to_spanish
                ),
        }


DEFAULT_LOCALIZATION = (
    WarframeLocalization()
)

SPANISH_LOCALIZATION_GUIDE = (
    DEFAULT_LOCALIZATION
    .prompt_context()
)


def localize_tool_result(
    result: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:
    return (
        DEFAULT_LOCALIZATION
        .localize_tool_result(
            result
        )
    )
