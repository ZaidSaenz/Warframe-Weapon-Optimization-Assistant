"""Minimal web interface for selecting and analyzing saved Warframe weapons.

The interface contains no editable weapon-stat fields. Weapon definitions are
loaded from JSON files stored in ``weapons/``. For backwards compatibility,
``weapon_test.json`` in the project root is also included when present.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, render_template_string, request

from modules.weapon_pipeline import analyze_weapon


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
            width: min(100%, 620px);
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
            Selecciona un arma para analizar sus estadísticas mediante
            el nuevo pipeline de interpretación y consulta de conocimiento.
        </p>

        <form id="weapon-form">
            <label for="weapon">
                Arma

                <select id="weapon" name="weapon" required>
                    <option value="">Selecciona un arma</option>

                    {% for weapon in weapons %}
                        <option value="{{ weapon.id }}">
                            {{ weapon.name }}
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

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.error || "No fue posible analizar el arma."
                    );
                }

                resultBox.textContent = data.analysis;
                resultBox.style.display = "block";
            } catch (error) {
                errorBox.textContent = error.message;
                errorBox.style.display = "block";
            } finally {
                button.disabled = false;
                statusBox.style.display = "none";
            }
        });
    </script>
</body>
</html>
"""


WEAPONS: list[dict[str, str]] = [
    {
        "id": "weapon_test",
        "name": "Arma de prueba",
    },
]


def get_weapon_data(weapon_id: str) -> dict[str, Any]:
    """
    Recupera los datos estructurados de un arma.

    Esta implementación es temporal. Posteriormente puede reemplazarse
    por un repositorio JSON, una base de datos o un módulo weapon_repository.
    """
    if weapon_id != "weapon_test":
        raise ValueError(f"Arma no encontrada: {weapon_id}")

    return {
        "name": "Weapon Test",
        "category": "primary",
        "fire_mode": "automatic",
        "delivery_type": "hitscan",
        "base_damage": {
            "impact": 1.2,
            "puncture": 4.8,
            "slash": 6.0,
        },
        "critical_chance": 30.0,
        "critical_multiplier": 3.0,
        "status_chance": 10.0,
        "fire_rate": 15.0,
        "multishot": 1.0,
        "magazine_size": 200,
        "reload_time": 3.0,
    }


@app.get("/")
def index() -> str:
    return render_template_string(
        HTML_TEMPLATE,
        weapons=WEAPONS,
    )


@app.post("/analyze")
def analyze() -> tuple[Any, int] | Any:
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            {
                "error": "La solicitud debe contener un objeto JSON.",
            }
        ), 400

    weapon_id = payload.get("weapon_id")

    if not isinstance(weapon_id, str) or not weapon_id.strip():
        return jsonify(
            {
                "error": "El campo weapon_id es obligatorio.",
            }
        ), 400

    try:
        weapon_data = get_weapon_data(weapon_id.strip())
        analysis = analyze_weapon(weapon_data)

        return jsonify(
            {
                "weapon_id": weapon_id,
                "analysis": analysis,
            }
        )

    except ValueError as error:
        return jsonify(
            {
                "error": str(error),
            }
        ), 404

    except FileNotFoundError as error:
        app.logger.exception("No se encontró un archivo requerido.")

        return jsonify(
            {
                "error": f"No se encontró un archivo requerido: {error}",
            }
        ), 500

    except Exception:
        app.logger.exception("Error inesperado durante el análisis.")

        return jsonify(
            {
                "error": "Ocurrió un error interno durante el análisis.",
            }
        ), 500


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False,
    )