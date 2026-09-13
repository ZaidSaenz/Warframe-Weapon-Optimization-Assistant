"""
Cephalon Agent

Minimal Warframe AI agent.

Responsibilities:
- Load and auto-index the canonical weapon database.
- Expose deterministic database tools to the language model.
- Let the model decide when it needs weapon information.
- Execute tool calls.
- Return tool results to the model.
- Produce the final natural-language response.

This module does NOT:
- calculate weapon statistics
- create semantic ratings
- interpret percentiles
- encode weapon relationships
- build weapon-specific prompts

Those responsibilities belong to the database or to the model itself.
"""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
from typing import Any

from llama_cpp import Llama


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_PATH = Path("data/normalized/weapons.json")

MODEL_PATH = Path(
    "models/Qwen2.5-3B-Instruct-Q4_K_M.gguf"
)

DEFAULT_N_CTX = 4096
DEFAULT_THREADS = 4
DEFAULT_GPU_LAYERS = 0

MAX_TOOL_ROUNDS = 4


SYSTEM_PROMPT = """
You are a Cephalon knowledgeable about Warframe.

You are analytical, concise, and slightly theatrical, like a Warframe Cephalon.

Answer in the same language used by the user.

When the user asks for factual information about a weapon, use the available
weapon database tool before answering.

Treat information returned by tools as the source of truth.

Analyze the retrieved information yourself.

Do not invent weapon statistics, mechanics, effects, or properties that are
not supported by the retrieved information.

If the database does not contain enough information to answer something,
say so clearly.
""".strip()


# ============================================================
# DATABASE
# ============================================================


def normalize_name(value: str) -> str:
    """
    Normalize a weapon name for deterministic lookup.
    """

    return " ".join(
        value.casefold().strip().split()
    )


class WeaponDatabase:
    """
    Loads weapons.json and creates an in-memory name index.

    With ~656 weapons this is intentionally simple.
    No vector database or persistent search index is necessary.
    """

    def __init__(self, path: Path = DATABASE_PATH):
        self.path = path

        if not self.path.exists():
            raise FileNotFoundError(
                f"Weapon database not found: {self.path}"
            )

        with self.path.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)

        self.weapons = self._extract_weapons(payload)

        if not self.weapons:
            raise ValueError(
                "The weapon database contains no usable weapons."
            )

        self.index: dict[str, dict[str, Any]] = {}

        for weapon in self.weapons:
            name = self._weapon_name(weapon)

            if not isinstance(name, str):
                continue

            key = normalize_name(name)

            if key:
                self.index[key] = weapon

        if not self.index:
            raise ValueError(
                "Could not create the weapon name index."
            )

    @staticmethod
    def _weapon_name(
        weapon: dict[str, Any],
    ) -> str | None:
        """
        Return the canonical display name of a weapon.

        Current database schema:
            weapon["identity"]["name"]
        """

        identity = weapon.get("identity")

        if isinstance(identity, dict):
            name = identity.get("name")

            if isinstance(name, str):
                return name

        # Compatibility fallback for simpler schemas.
        name = weapon.get("name")

        if isinstance(name, str):
            return name

        return None

    @staticmethod
    def _extract_weapons(
        payload: Any,
    ) -> list[dict[str, Any]]:
        """
        Extract canonical weapon records.

        Current weapons.json schema:

            {
                "schema_version": "...",
                "weapon_count": 656,
                "weapons": {
                    "<weapon_id>": {...},
                    ...
                }
            }
        """

        if isinstance(payload, list):
            return [
                item
                for item in payload
                if isinstance(item, dict)
            ]

        if isinstance(payload, dict):

            weapons = payload.get("weapons")

            # Current canonical database format.
            if isinstance(weapons, dict):
                return [
                    weapon
                    for weapon in weapons.values()
                    if isinstance(weapon, dict)
                ]

            # Compatibility with possible list format.
            if isinstance(weapons, list):
                return [
                    weapon
                    for weapon in weapons
                    if isinstance(weapon, dict)
                ]

        raise ValueError(
            "Unsupported weapons.json structure."
        )

    def get_weapon(
        self,
        weapon_name: str,
    ) -> dict[str, Any]:
        """
        Exact normalized lookup.

        If not found, return deterministic suggestions instead
        of silently guessing.
        """

        query = normalize_name(weapon_name)

        weapon = self.index.get(query)

        if weapon is not None:
            return {
                "found": True,
                "query": weapon_name,
                "weapon": weapon,
            }

        matches = difflib.get_close_matches(
            query,
            list(self.index.keys()),
            n=5,
            cutoff=0.55,
        )

        suggestions = [
            self._weapon_name(self.index[key])
            for key in matches
        ]

        return {
            "found": False,
            "query": weapon_name,
            "suggestions": suggestions,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "database": str(self.path),
            "weapons_loaded": len(self.weapons),
            "indexed_names": len(self.index),
        }


# ============================================================
# TOOL DEFINITIONS
# ============================================================


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weapon",
            "description": (
                "Retrieve verified canonical information "
                "about a specific Warframe weapon from the "
                "local weapon database."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "weapon_name": {
                        "type": "string",
                        "description": (
                            "The name of the Warframe weapon "
                            "to retrieve, for example "
                            "'Soma Prime'."
                        ),
                    }
                },
                "required": [
                    "weapon_name"
                ],
                "additionalProperties": False,
            },
        },
    }
]


# ============================================================
# TOOL EXECUTION
# ============================================================


def parse_tool_arguments(
    raw_arguments: Any,
) -> dict[str, Any]:

    if isinstance(raw_arguments, dict):
        return raw_arguments

    if not isinstance(raw_arguments, str):
        raise ValueError(
            "Tool arguments must be JSON."
        )

    try:
        value = json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid tool arguments: {raw_arguments}"
        ) from exc

    if not isinstance(value, dict):
        raise ValueError(
            "Tool arguments must decode to an object."
        )

    return value


def execute_tool(
    database: WeaponDatabase,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:

    if tool_name == "get_weapon":

        weapon_name = arguments.get(
            "weapon_name"
        )

        if not isinstance(weapon_name, str):
            return {
                "error": (
                    "get_weapon requires a string "
                    "'weapon_name'."
                )
            }

        return database.get_weapon(
            weapon_name
        )

    return {
        "error": f"Unknown tool: {tool_name}"
    }


# ============================================================
# CEPHALON AGENT
# ============================================================


class CephalonAgent:

    def __init__(
        self,
        database: WeaponDatabase,
        model_path: Path = MODEL_PATH,
        n_ctx: int = DEFAULT_N_CTX,
        n_threads: int = DEFAULT_THREADS,
        n_gpu_layers: int = DEFAULT_GPU_LAYERS,
        debug: bool = False,
    ):

        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {model_path}"
            )

        self.database = database
        self.debug = debug

        self.llm = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            n_gpu_layers=n_gpu_layers,

            # Qwen 2.5 uses ChatML-style conversations.
            # llama-cpp-python provides this generic format
            # specifically for tool/function calling.
            chat_format="chatml-function-calling",

            verbose=False,
        )

    def ask(
        self,
        user_message: str,
    ) -> str:
        """
        Two-phase tool workflow.

        Phase 1:
            The model may decide to call a tool.

        Phase 2:
            After tool results are available, tools are disabled
            and the model must answer using the retrieved data.

        This deliberately avoids recursive tool loops while we
        validate Qwen 2.5 3B's ability to retrieve and understand
        canonical weapon data.
        """

        # ====================================================
        # PHASE 1 — Decide whether information is needed
        # ====================================================

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ]

        response = self.llm.create_chat_completion(
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=256,
        )

        message = response["choices"][0]["message"]

        tool_calls = (
            message.get("tool_calls")
            or []
        )

        # ----------------------------------------------------
        # Model answered directly.
        # ----------------------------------------------------

        if not tool_calls:

            content = message.get("content")

            if content:
                return content.strip()

            return (
                "The model returned neither "
                "a tool call nor a response."
            )

        # ====================================================
        # Execute requested tools
        # ====================================================

        retrieved_results: list[dict[str, Any]] = []

        for tool_call in tool_calls:

            function = tool_call.get(
                "function",
                {},
            )

            tool_name = function.get(
                "name",
                "",
            )

            raw_arguments = function.get(
                "arguments",
                "{}",
            )

            try:

                arguments = parse_tool_arguments(
                    raw_arguments
                )

                if self.debug:
                    print(
                        "\n[CEPHALON TOOL CALL]"
                    )
                    print(
                        json.dumps(
                            {
                                "tool": tool_name,
                                "arguments": arguments,
                            },
                            indent=2,
                            ensure_ascii=False,
                        )
                    )

                result = execute_tool(
                    database=self.database,
                    tool_name=tool_name,
                    arguments=arguments,
                )

            except Exception as exc:

                arguments = {}

                result = {
                    "error": str(exc)
                }

            if self.debug:
                print(
                    "\n[TOOL RESULT]"
                )
                print(
                    json.dumps(
                        result,
                        indent=2,
                        ensure_ascii=False,
                    )
                )

            retrieved_results.append(
                {
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result,
                }
            )

        # ====================================================
        # PHASE 2 — Analyze retrieved information
        #
        # IMPORTANT:
        # No tools are available during this phase.
        # The model therefore cannot request the same tool again.
        # ====================================================

        tool_payload = json.dumps(
            retrieved_results,
            ensure_ascii=False,
        )

        final_system_prompt = (
            SYSTEM_PROMPT
            + "\n\n"
            + "A verified local database lookup has already "
              "been completed for this turn. "
              "No tools are available during this phase. "
              "Answer the user's original question using the "
              "retrieved information below. "
              "Do not invent unsupported facts."
        )

        final_messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": final_system_prompt,
            },
            {
                "role": "user",
                "content": user_message,
            },
            {
                "role": "user",
                "content": (
                    "Verified database result:\n"
                    "<tool_response>\n"
                    + tool_payload
                    + "\n</tool_response>\n\n"
                    "Now answer the original question."
                ),
            },
        ]

        final_response = self.llm.create_chat_completion(
            messages=final_messages,

            # Explicitly disable tool calling.
            tools=None,
            tool_choice="none",

            temperature=0.1,
            max_tokens=512,
        )

        final_message = (
            final_response["choices"][0]["message"]
        )

        content = final_message.get(
            "content"
        )

        if content:
            return content.strip()

        return (
            "The model received the database result "
            "but produced no final answer."
        )



# ============================================================
# CLI
# ============================================================


def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Minimal Warframe Cephalon "
            "with weapon database tools."
        )
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DATABASE_PATH,
    )

    parser.add_argument(
        "--model",
        type=Path,
        default=MODEL_PATH,
    )

    parser.add_argument(
        "--n-ctx",
        type=int,
        default=DEFAULT_N_CTX,
    )

    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULT_THREADS,
    )

    parser.add_argument(
        "--gpu-layers",
        type=int,
        default=DEFAULT_GPU_LAYERS,
    )

    parser.add_argument(
        "--debug",
        action="store_true",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    tool_parser = subparsers.add_parser(
        "tool",
        help=(
            "Test the weapon database tool "
            "without loading the language model."
        ),
    )

    tool_parser.add_argument(
        "weapon_name"
    )

    ask_parser = subparsers.add_parser(
        "ask",
        help=(
            "Ask the Cephalon a question."
        ),
    )

    ask_parser.add_argument(
        "message"
    )

    subparsers.add_parser(
        "database",
        help=(
            "Show database/index status."
        ),
    )

    return parser


def main() -> None:

    parser = build_parser()
    args = parser.parse_args()

    database = WeaponDatabase(
        args.database
    )

    # --------------------------------------------------------
    # Database status
    # --------------------------------------------------------

    if args.command == "database":

        print(
            json.dumps(
                database.summary(),
                indent=2,
                ensure_ascii=False,
            )
        )

        return

    # --------------------------------------------------------
    # Direct tool test
    # --------------------------------------------------------

    if args.command == "tool":

        result = database.get_weapon(
            args.weapon_name
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

        return

    # --------------------------------------------------------
    # Agent test
    # --------------------------------------------------------

    if args.command == "ask":

        agent = CephalonAgent(
            database=database,
            model_path=args.model,
            n_ctx=args.n_ctx,
            n_threads=args.threads,
            n_gpu_layers=args.gpu_layers,
            debug=args.debug,
        )

        answer = agent.ask(
            args.message
        )

        print("\nCEPHALON")
        print("========")
        print(answer)

        return


if __name__ == "__main__":
    main()
