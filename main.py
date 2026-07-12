"""Minimal web interface for selecting and analyzing saved Warframe weapons.

The interface contains no editable weapon-stat fields. Weapon definitions are
loaded from JSON files stored in ``weapons/``. For backwards compatibility,
``weapon_test.json`` in the project root is also included when present.
"""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from threading import Timer
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from modules.ai import analyze_weapon


APP_ROOT = Path(__file__).resolve().parent
WEAPONS_DIR = APP_ROOT / "weapons"
LEGACY_WEAPON_FILE = APP_ROOT / "weapon_test.json"

HOST = "127.0.0.1"
PORT = 5001

app = Flask(__name__)


PAGE = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Warframe Weapon Analyzer</title>

    <style>
        :root {
            color-scheme: dark;
            font-family:
                Inter, ui-sans-serif, system-ui, -apple-system,
                BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #090b10;
            color: #edf1f7;
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
                radial-gradient(circle at top, #18202f 0, transparent 42%),
                #090b10;
        }

        main {
            width: min(720px, 100%);
        }

        header {
            margin-bottom: 24px;
        }

        h1 {
            margin: 0 0 8px;
            font-size: clamp(1.8rem, 5vw, 2.8rem);
            line-height: 1;
            letter-spacing: -0.04em;
        }

        p {
            margin: 0;
            color: #98a3b5;
        }

        .panel {
            padding: 20px;
            border: 1px solid #252d3a;
            border-radius: 16px;
            background: rgba(15, 18, 25, 0.92);
            box-shadow: 0 24px 70px rgba(0, 0, 0, 0.35);
        }

        .controls {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 12px;
        }

        select,
        button {
            min-height: 48px;
            border-radius: 10px;
            font: inherit;
        }

        select {
            width: 100%;
            padding: 0 14px;
            border: 1px solid #303949;
            background: #10141c;
            color: inherit;
            outline: none;
        }

        select:focus {
            border-color: #7aa2ff;
        }

        button {
            padding: 0 22px;
            border: 0;
            background: #edf1f7;
            color: #0b0e14;
            font-weight: 700;
            cursor: pointer;
        }

        button:hover:not(:disabled) {
            background: #cfd8e8;
        }

        button:disabled {
            cursor: wait;
            opacity: 0.55;
        }

        .status {
            min-height: 24px;
            margin-top: 16px;
            color: #98a3b5;
        }

        .status.error {
            color: #ff8f8f;
        }

        .result {
            display: none;
            margin: 16px 0 0;
            padding: 18px;
            overflow-wrap: anywhere;
            white-space: pre-wrap;
            border: 1px solid #252d3a;
            border-radius: 12px;
            background: #0b0e14;
            color: #dfe6f1;
            font: inherit;
            line-height: 1.6;
        }

        .result.visible {
            display: block;
        }

        @media (max-width: 560px) {
            .controls {
                grid-template-columns: 1fr;
            }

            button {
                width: 100%;
            }
        }
    </style>
</head>

<body>
    <main>
        <header>
            <h1>Weapon Analyzer</h1>
            <p>Selecciona un arma guardada y ejecuta el análisis local.</p>
        </header>

        <section class="panel">
            {% if weapons %}
                <div class="controls">
                    <select id="weapon-select" aria-label="Seleccionar arma">
                        {% for weapon in weapons %}
                            <option value="{{ weapon.id }}">
                                {{ weapon.name }}
                            </option>
                        {% endfor %}
                    </select>

                    <button id="analyze-button" type="button">
                        Analizar
                    </button>
                </div>

                <div id="status" class="status"></div>
                <pre id="result" class="result"></pre>
            {% else %}
                <p>
                    No se encontraron armas. Agrega archivos JSON dentro de
                    <code>weapons/</code>.
                </p>
            {% endif %}
        </section>
    </main>

    {% if weapons %}
    <script>
        const selector = document.querySelector("#weapon-select");
        const button = document.querySelector("#analyze-button");
        const status = document.querySelector("#status");
        const result = document.querySelector("#result");

        function setLoading(isLoading) {
            selector.disabled = isLoading;
            button.disabled = isLoading;
            button.textContent = isLoading ? "Analizando…" : "Analizar";
        }

        button.addEventListener("click", async () => {
            const weaponId = selector.value;

            status.className = "status";
            status.textContent = "El modelo local está procesando el arma…";
            result.classList.remove("visible");
            result.textContent = "";
            setLoading(true);

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

                const payload = await response.json();

                if (!response.ok) {
                    throw new Error(
                        payload.error || "No fue posible completar el análisis."
                    );
                }

                status.textContent = "";
                result.textContent = payload.result;
                result.classList.add("visible");
            } catch (error) {
                status.className = "status error";
                status.textContent = error.message;
            } finally {
                setLoading(false);
            }
        });
    </script>
    {% endif %}
</body>
</html>
"""


def _read_weapon_file(path: Path) -> dict[str, Any] | None:
    """Read one weapon JSON file.

    Invalid files are skipped and recorded in the Flask log so one malformed
    test case does not prevent the interface from opening.
    """

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        app.logger.exception("Could not load weapon file: %s", path)
        return None

    if not isinstance(data, dict):
        app.logger.error("Weapon file root must be an object: %s", path)
        return None

    return data


def load_weapon_catalog() -> dict[str, dict[str, Any]]:
    """Load all selectable weapons from disk.

    Files in ``weapons/`` are preferred. ``weapon_test.json`` remains available
    to keep the current project structure working while the catalog is created.
    """

    files: list[Path] = []

    if WEAPONS_DIR.is_dir():
        files.extend(sorted(WEAPONS_DIR.glob("*.json")))

    if LEGACY_WEAPON_FILE.is_file():
        files.append(LEGACY_WEAPON_FILE)

    catalog: dict[str, dict[str, Any]] = {}

    for path in files:
        data = _read_weapon_file(path)
        if data is None:
            continue

        base_id = path.stem
        weapon_id = base_id
        suffix = 2

        while weapon_id in catalog:
            weapon_id = f"{base_id}-{suffix}"
            suffix += 1

        display_name = str(
            data.get("weapon_name")
            or data.get("name")
            or path.stem.replace("_", " ").replace("-", " ").title()
        ).strip()

        catalog[weapon_id] = {
            "name": display_name or path.stem,
            "data": data,
            "source_path": str(path),
        }

    return catalog


@app.get("/")
def index() -> str:
    catalog = load_weapon_catalog()

    weapons = [
        {
            "id": weapon_id,
            "name": entry["name"],
        }
        for weapon_id, entry in catalog.items()
    ]

    weapons.sort(key=lambda item: item["name"].casefold())

    return render_template_string(
        PAGE,
        weapons=weapons,
    )


@app.post("/analyze")
def analyze():
    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify({"error": "Solicitud inválida."}), 400

    weapon_id = str(payload.get("weapon_id") or "").strip()
    catalog = load_weapon_catalog()
    selected = catalog.get(weapon_id)

    if selected is None:
        return jsonify({"error": "El arma seleccionada no existe."}), 404

    try:
        result = analyze_weapon(selected["data"])
    except Exception:
        app.logger.exception(
            "Could not analyze weapon from %s",
            selected["source_path"],
        )
        return jsonify(
            {"error": "No fue posible completar el análisis local."}
        ), 500

    return jsonify(
        {
            "weapon": selected["name"],
            "result": result,
        }
    )


def open_browser() -> None:
    """Open the local application after Flask starts."""

    webbrowser.open_new(f"http://{HOST}:{PORT}")


def main() -> None:
    """Start the local single-user application."""

    Timer(1.0, open_browser).start()

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        threaded=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()