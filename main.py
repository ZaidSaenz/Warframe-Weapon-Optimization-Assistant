"""Minimal web interface for selecting and analyzing normalized Warframe weapons.

Weapon definitions are loaded from ``data/normalized/weapons.json``. The
interface contains no editable weapon-stat fields.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from modules.ai import analyze_weapon
from modules.weapon_database import (
    DEFAULT_OUTPUT,
    WeaponDatabaseError,
    load_normalized_database,
)


app = Flask(__name__)


HTML_TEMPLATE = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <title>Warframe Weapon Analyzer</title>

    <style>
        :root {
            color-scheme: dark;
            font-family:
                Inter,
                system-ui,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;

            background: #0b0d10;
            color: #e8eaed;
        }

        * {
            box-sizing: border-box;
        }

        body {
            min-height: 100vh;
            margin: 0;
            display: grid;
            place-items: center;
            padding: 24px;
            background:
                radial-gradient(
                    circle at top,
                    rgba(78, 116, 158, 0.12),
                    transparent 35%
                ),
                #0b0d10;
        }

        main {
            width: min(100%, 680px);
            padding: 32px;
            border: 1px solid #252a31;
            border-radius: 16px;
            background: rgba(17, 20, 24, 0.96);
            box-shadow: 0 24px 70px rgba(0, 0, 0, 0.35);
        }

        h1 {
            margin: 0 0 8px;
            font-size: clamp(1.7rem, 4vw, 2.3rem);
        }

        .subtitle {
            margin: 0 0 28px;
            color: #9da4ad;
            line-height: 1.5;
        }

        form {
            display: grid;
            gap: 16px;
        }

        label {
            display: grid;
            gap: 8px;
            font-size: 0.92rem;
            color: #bcc2ca;
        }

        select,
        button {
            width: 100%;
            min-height: 48px;
            border-radius: 10px;
            font: inherit;
        }

        select {
            padding: 0 14px;
            border: 1px solid #30363d;
            background: #0d1117;
            color: #f0f3f6;
        }

        select:focus {
            outline: 2px solid #5b8cc0;
            outline-offset: 2px;
        }

        button {
            border: 0;
            padding: 0 18px;
            background: #d7e8f7;
            color: #101418;
            font-weight: 700;
            cursor: pointer;
        }

        button:hover {
            filter: brightness(1.05);
        }

        button:disabled {
            cursor: wait;
            opacity: 0.65;
        }

        .database-note {
            margin: -12px 0 22px;
            color: #727b86;
            font-size: 0.84rem;
        }

        .status,
        .result,
        .error {
            margin-top: 20px;
            padding: 16px;
            border-radius: 10px;
            white-space: pre-wrap;
            line-height: 1.55;
        }

        .status {
            display: none;
            border: 1px solid #2f4858;
            background: #111b22;
            color: #b8d8eb;
        }

        .result {
            display: none;
            border: 1px solid #2d4937;
            background: #111a14;
            color: #d5eadb;
        }

        .error {
            display: none;
            border: 1px solid #59383b;
            background: #211416;
            color: #f2c7cb;
        }
    </style>
</head>

<body>
    <main>
        <h1>Weapon Analyzer</h1>

        <p class="subtitle">
            Selecciona un arma de la base normalizada para analizar sus
            estadísticas mediante el pipeline local.
        </p>

        <p class="database-note">
            {{ weapons|length }} armas disponibles.
        </p>

        <form id="weapon-form">
            <label for="weapon">
                Arma

                <select id="weapon" name="weapon" required>
                    <option value="">Selecciona un arma</option>

                    {% for weapon in weapons %}
                        <option value="{{ weapon.id }}">
                            {{ weapon.label }}
                        </option>
                    {% endfor %}
                </select>
            </label>

            <button id="submit-button" type="submit">
                Analizar arma
            </button>
        </form>

        <section id="status" class="status">
            Analizando arma...
        </section>

        <section id="result" class="result"></section>

        <section id="error" class="error"></section>
    </main>

    <script>
        const form = document.getElementById("weapon-form");
        const button = document.getElementById("submit-button");
        const statusBox = document.getElementById("status");
        const resultBox = document.getElementById("result");
        const errorBox = document.getElementById("error");

        function resetOutput() {
            statusBox.style.display = "none";
            resultBox.style.display = "none";
            errorBox.style.display = "none";

            resultBox.textContent = "";
            errorBox.textContent = "";
        }

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            resetOutput();

            const weaponId = document
                .getElementById("weapon")
                .value
                .trim();

            if (!weaponId) {
                errorBox.textContent = "Selecciona un arma.";
                errorBox.style.display = "block";
                return;
            }

            button.disabled = true;
            statusBox.style.display = "block";

            try {
                const response = await fetch("/analyze", {
    method: "POST",
    headers: {
        "Content-Type": "application/json"
    },
    body: JSON.stringify({
        weapon_id: weaponId
    })
});

const rawResponse = await response.text();

let data;

try {
    data = rawResponse
        ? JSON.parse(rawResponse)
        : {};
} catch {
    throw new Error(
        "El servidor devolvió una respuesta inválida."
    );
}

if (!response.ok) {
    throw new Error(
        data.error
        || `Error del servidor (${response.status}).`
    );
}

if (!data.analysis) {
    throw new Error(
        "El servidor no devolvió un análisis."
    );
}

resultBox.textContent = data.analysis;
resultBox.style.display = "block";

} finally {
                button.disabled = false;
                statusBox.style.display = "none";
            }
        });
    </script>
</body>
</html>
"""


def _database_weapons() -> Mapping[str, Any]:
    database = load_normalized_database(
        DEFAULT_OUTPUT
    )

    weapons = database.get("weapons")

    if not isinstance(weapons, Mapping):
        raise WeaponDatabaseError(
            "The normalized database does not contain weapons."
        )

    return weapons


def list_weapon_options() -> list[dict[str, str]]:
    weapons = _database_weapons()
    options: list[dict[str, str]] = []

    for weapon_id, weapon in weapons.items():
        if not isinstance(weapon, Mapping):
            continue

        classification = weapon.get(
            "classification"
        )

        if not isinstance(
            classification,
            Mapping,
        ):
            classification = {}

        display_name = str(
            weapon.get("display_name")
            or weapon.get("name_key")
            or weapon_id
        ).strip()

        category = str(
            classification.get("category")
            or "unknown"
        ).strip()

        weapon_class = str(
            classification.get("weapon_class")
            or ""
        ).strip()

        mastery_rank = classification.get(
            "mastery_rank"
        )

        details = [
            category,
        ]

        if weapon_class:
            details.append(weapon_class)

        if mastery_rank is not None:
            details.append(
                f"MR {mastery_rank}"
            )

        label = (
            f"{display_name} — "
            + " · ".join(details)
        )

        options.append(
            {
                "id": str(weapon_id),
                "name": display_name,
                "label": label,
            }
        )

    options.sort(
        key=lambda item: item["name"].casefold()
    )

    return options


def get_weapon_data(
    weapon_id: str,
) -> dict[str, Any]:
    weapons = _database_weapons()
    weapon = weapons.get(weapon_id)

    if not isinstance(weapon, Mapping):
        raise ValueError(
            f"Arma no encontrada: {weapon_id}"
        )

    return dict(weapon)


@app.get("/")
def index() -> str | tuple[str, int]:
    try:
        weapons = list_weapon_options()
    except (FileNotFoundError, WeaponDatabaseError) as error:
        app.logger.exception(
            "No se pudo cargar la base normalizada."
        )

        return render_template_string(
            HTML_TEMPLATE,
            weapons=[],
        ), 500

    return render_template_string(
        HTML_TEMPLATE,
        weapons=weapons,
    )


@app.post("/analyze")
def analyze() -> tuple[Any, int] | Any:
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            {
                "error": (
                    "La solicitud debe contener "
                    "un objeto JSON."
                ),
            }
        ), 400

    weapon_id = payload.get("weapon_id")

    if (
        not isinstance(weapon_id, str)
        or not weapon_id.strip()
    ):
        return jsonify(
            {
                "error": (
                    "El campo weapon_id es "
                    "obligatorio."
                ),
            }
        ), 400

    normalized_weapon_id = weapon_id.strip()

    try:
        weapon_data = get_weapon_data(
            normalized_weapon_id
        )

        analysis = analyze_weapon(
            weapon_data
        )

        return jsonify(
            {
                "weapon_id": normalized_weapon_id,
                "weapon_name": weapon_data.get(
                    "display_name"
                ),
                "analysis": analysis,
            }
        )

    except ValueError as error:
        return jsonify(
            {
                "error": str(error),
            }
        ), 404

    except (
        FileNotFoundError,
        WeaponDatabaseError,
    ) as error:
        app.logger.exception(
            "No se encontró o no se pudo leer "
            "la base normalizada."
        )

        return jsonify(
            {
                "error": (
                    "No fue posible cargar la base "
                    f"normalizada: {error}"
                ),
            }
        ), 500

    except Exception:
        app.logger.exception(
            "Error inesperado durante el análisis."
        )

        return jsonify(
            {
                "error": (
                    "Ocurrió un error interno "
                    "durante el análisis."
                ),
            }
        ), 500


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False,
    )