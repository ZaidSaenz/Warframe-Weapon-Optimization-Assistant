from __future__ import annotations

import webbrowser
from threading import Timer

from flask import Flask, jsonify, render_template_string, request

from modules.ai import analyze_weapon


app = Flask(__name__)

PORT = 5001


HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>Warframe Weapon Optimization Assistant</title>

    <style>
        :root {
            color-scheme: dark;

            --background: #080b10;
            --panel: #111722;
            --panel-soft: #161e2b;
            --border: #293548;
            --text: #eef3f8;
            --muted: #9caabd;
            --accent: #61d7d0;
            --accent-dark: #318f8c;
            --danger: #ff8181;
            --success: #88e0a1;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            font-family:
                Inter,
                ui-sans-serif,
                system-ui,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;
            color: var(--text);
            background:
                radial-gradient(circle at top, rgba(55, 121, 135, 0.20), transparent 34rem),
                linear-gradient(180deg, #0b1018 0%, var(--background) 100%);
        }

        button,
        input,
        select {
            font: inherit;
        }

        .page {
            width: min(1180px, calc(100% - 32px));
            margin: 0 auto;
            padding: 42px 0 70px;
        }

        .header {
            margin-bottom: 26px;
        }

        .eyebrow {
            margin: 0 0 8px;
            color: var(--accent);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }

        h1 {
            margin: 0;
            max-width: 780px;
            font-size: clamp(2rem, 4vw, 3.35rem);
            line-height: 1.05;
        }

        .subtitle {
            max-width: 760px;
            margin: 16px 0 0;
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.65;
        }

        .layout {
            display: grid;
            grid-template-columns: minmax(0, 1.45fr) minmax(310px, 0.75fr);
            gap: 24px;
            align-items: start;
        }

        .panel {
            border: 1px solid var(--border);
            border-radius: 18px;
            background: rgba(17, 23, 34, 0.94);
            box-shadow: 0 24px 70px rgba(0, 0, 0, 0.25);
        }

        .form-panel {
            padding: 24px;
        }

        .result-panel {
            position: sticky;
            top: 22px;
            min-height: 370px;
            padding: 24px;
        }

        .section {
            padding: 21px 0;
            border-bottom: 1px solid var(--border);
        }

        .section:first-child {
            padding-top: 0;
        }

        .section:last-of-type {
            border-bottom: 0;
        }

        .section-title {
            margin: 0 0 6px;
            font-size: 1.05rem;
        }

        .section-description {
            margin: 0 0 18px;
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.5;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 16px;
        }

        .grid-three {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }

        .field {
            min-width: 0;
        }

        .field.full {
            grid-column: 1 / -1;
        }

        label {
            display: block;
            margin-bottom: 7px;
            color: #dce5ef;
            font-size: 0.86rem;
            font-weight: 700;
        }

        .required::after {
            content: " *";
            color: var(--accent);
        }

        input,
        select {
            width: 100%;
            min-height: 44px;
            border: 1px solid var(--border);
            border-radius: 10px;
            outline: none;
            padding: 10px 12px;
            color: var(--text);
            background: var(--panel-soft);
            transition:
                border-color 160ms ease,
                box-shadow 160ms ease;
        }

        input:focus,
        select:focus {
            border-color: var(--accent-dark);
            box-shadow: 0 0 0 3px rgba(97, 215, 208, 0.11);
        }

        .checkbox-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin-top: 16px;
        }

        .checkbox-field {
            display: flex;
            align-items: center;
            gap: 10px;
            min-height: 44px;
            margin: 0;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px 12px;
            background: var(--panel-soft);
            cursor: pointer;
        }

        .checkbox-field input[type="checkbox"] {
            width: 18px;
            min-height: 18px;
            height: 18px;
            margin: 0;
            padding: 0;
            accent-color: var(--accent);
        }

        small {
            display: block;
            margin-top: 6px;
            color: var(--muted);
            font-size: 0.76rem;
            line-height: 1.4;
        }

        .damage-list {
            display: grid;
            gap: 10px;
        }

        .damage-row {
            display: grid;
            grid-template-columns: minmax(0, 1fr) 150px 42px;
            gap: 10px;
            align-items: end;
        }

        .icon-button {
            width: 42px;
            height: 44px;
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--muted);
            background: var(--panel-soft);
            cursor: pointer;
        }

        .icon-button:hover {
            color: var(--danger);
            border-color: rgba(255, 129, 129, 0.45);
        }

        .secondary-button {
            margin-top: 12px;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px 14px;
            color: var(--text);
            background: transparent;
            cursor: pointer;
        }

        .secondary-button:hover {
            border-color: var(--accent-dark);
            color: var(--accent);
        }

        .conditional-group {
            display: none;
        }

        .conditional-group.visible {
            display: block;
        }

        .submit-button {
            width: 100%;
            margin-top: 8px;
            border: 0;
            border-radius: 12px;
            padding: 14px 18px;
            color: #031414;
            background: linear-gradient(135deg, var(--accent), #9de9c4);
            font-weight: 900;
            cursor: pointer;
        }

        .submit-button:hover {
            filter: brightness(1.06);
        }

        .submit-button:disabled {
            cursor: wait;
            opacity: 0.55;
        }

        .result-title {
            margin: 0 0 8px;
            font-size: 1.15rem;
        }

        .result-help {
            margin: 0 0 20px;
            color: var(--muted);
            font-size: 0.88rem;
            line-height: 1.55;
        }

        .result-box {
            min-height: 245px;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 17px;
            color: #dce5ef;
            background: #0b1018;
            white-space: pre-wrap;
            line-height: 1.65;
            overflow-wrap: anywhere;
        }

        .result-placeholder {
            color: #718096;
        }

        .error {
            color: var(--danger);
        }

        .success {
            color: var(--success);
        }

        .scope {
            margin-top: 18px;
            padding: 14px;
            border: 1px solid rgba(97, 215, 208, 0.17);
            border-radius: 12px;
            color: var(--muted);
            background: rgba(97, 215, 208, 0.05);
            font-size: 0.79rem;
            line-height: 1.55;
        }

        @media (max-width: 920px) {
            .layout {
                grid-template-columns: 1fr;
            }

            .result-panel {
                position: static;
            }
        }

        @media (max-width: 620px) {
            .page {
                width: min(100% - 20px, 1180px);
                padding-top: 26px;
            }

            .form-panel,
            .result-panel {
                padding: 18px;
            }

            .grid,
            .grid-three,
            .checkbox-grid {
                grid-template-columns: 1fr;
            }

            .damage-row {
                grid-template-columns: 1fr 110px 42px;
            }
        }
    </style>
</head>

<body>
    <main class="page">
        <header class="header">
            <p class="eyebrow">Local AI · Statistical analysis</p>

            <h1>Warframe Weapon Optimization Assistant</h1>

            <p class="subtitle">
                Captura las estadísticas base del arma, sin mods, Arcanos,
                Rivens ni mejoras externas, para obtener una evaluación de su
                tendencia, fortalezas y limitaciones.
            </p>
        </header>

        <div class="layout">
            <section class="panel form-panel">
                <form id="weaponForm">
                    <div class="section">
                        <h2 class="section-title">Clasificación del arma</h2>

                        <p class="section-description">
                            La categoría determina qué estadísticas adicionales
                            deben capturarse.
                        </p>

                        <div class="grid">
                            <div class="field">
                                <label class="required" for="weaponCategory">
                                    Categoría
                                </label>

                                <select id="weaponCategory" required>
                                    <option value="primary">Primaria</option>
                                    <option value="secondary">Secundaria</option>
                                    <option value="melee">Melee</option>
                                </select>
                            </div>
                        </div>

                        <div id="rangedClassification" class="conditional-group">
                            <div class="grid" style="margin-top: 16px;">
                                <div class="field">
                                    <label class="required" for="firingMode">
                                        Modo de disparo
                                    </label>

                                    <select id="firingMode">
                                        <option value="automatic">Automático</option>
                                        <option value="semi_automatic">Semiautomático</option>
                                        <option value="burst">Ráfaga</option>
                                        <option value="charge">Carga</option>
                                        <option value="continuous">Continuo</option>
                                    </select>
                                </div>

                                <div class="field">
                                    <label class="required" for="damageDelivery">
                                        Entrega del daño
                                    </label>

                                    <select id="damageDelivery">
                                        <option value="hitscan">Hitscan</option>
                                        <option value="projectile">Proyectil</option>
                                        <option value="beam">Haz</option>
                                    </select>
                                </div>
                            </div>

                            <div class="checkbox-grid">
                                <label class="checkbox-field" for="hasMultiplePellets">
                                    <input id="hasMultiplePellets" type="checkbox">
                                    Múltiples perdigones
                                </label>

                                <label class="checkbox-field" for="isExplosive">
                                    <input id="isExplosive" type="checkbox">
                                    Daño explosivo en área
                                </label>
                            </div>
                        </div>
                    </div>

                    <div class="section">
                        <h2 class="section-title">Daño base</h2>

                        <p class="section-description">
                            Introduce los valores absolutos de daño base que muestra
                            el arma sin mods. El programa calculará el daño total y
                            su distribución porcentual.
                        </p>

                        <div id="damageList" class="damage-list"></div>

                        <button
                            class="secondary-button"
                            id="addDamageButton"
                            type="button"
                        >
                            Agregar tipo de daño
                        </button>
                    </div>

                    <div class="section">
                        <h2 class="section-title">Estadísticas generales</h2>

                        <div class="grid grid-three">
                            <div class="field">
                                <label class="required" for="criticalChance">
                                    Probabilidad crítica (%)
                                </label>

                                <input
                                    id="criticalChance"
                                    type="number"
                                    min="0"
                                    step="any"
                                    required
                                >
                            </div>

                            <div class="field">
                                <label class="required" for="criticalMultiplier">
                                    Multiplicador crítico
                                </label>

                                <input
                                    id="criticalMultiplier"
                                    type="number"
                                    min="1"
                                    step="any"
                                    required
                                >
                            </div>

                            <div class="field">
                                <label class="required" for="statusChance">
                                    Probabilidad de estado (%)
                                </label>

                                <input
                                    id="statusChance"
                                    type="number"
                                    min="0"
                                    step="any"
                                    required
                                >
                            </div>
                        </div>
                    </div>

                    <div id="rangedSection" class="section conditional-group">
                        <h2 class="section-title">Estadísticas de arma a distancia</h2>

                        <div class="grid">
                            <div class="field">
                                <label class="required" for="fireRate">
                                    Cadencia de fuego
                                </label>

                                <input
                                    id="fireRate"
                                    type="number"
                                    min="0.01"
                                    step="any"
                                >
                            </div>

                            <div class="field">
                                <label class="required" for="multishot">
                                    Multidisparo
                                </label>

                                <input
                                    id="multishot"
                                    type="number"
                                    min="0.01"
                                    step="any"
                                    value="1"
                                >
                            </div>

                            <div class="field">
                                <label class="required" for="magazineSize">
                                    Tamaño del cargador
                                </label>

                                <input
                                    id="magazineSize"
                                    type="number"
                                    min="1"
                                    step="1"
                                >
                            </div>

                            <div class="field">
                                <label class="required" for="reloadTime">
                                    Tiempo de recarga (s)
                                </label>

                                <input
                                    id="reloadTime"
                                    type="number"
                                    min="0.01"
                                    step="any"
                                >
                            </div>
                        </div>
                    </div>

                    <div id="meleeSection" class="section conditional-group">
                        <h2 class="section-title">Estadísticas melee</h2>

                        <div class="grid">
                            <div class="field">
                                <label class="required" for="attackSpeed">
                                    Velocidad de ataque
                                </label>

                                <input
                                    id="attackSpeed"
                                    type="number"
                                    min="0.01"
                                    step="any"
                                >
                            </div>

                            <div class="field">
                                <label class="required" for="range">
                                    Alcance
                                </label>

                                <input
                                    id="range"
                                    type="number"
                                    min="0"
                                    step="any"
                                >
                            </div>

                            <div class="field">
                                <label for="heavyAttackDamage">
                                    Daño de ataque pesado
                                </label>

                                <input
                                    id="heavyAttackDamage"
                                    type="number"
                                    min="0"
                                    step="any"
                                >

                                <small>Opcional. Permite evaluar ataques pesados.</small>
                            </div>

                            <div class="field">
                                <label for="heavyAttackWindUp">
                                    Preparación de ataque pesado (s)
                                </label>

                                <input
                                    id="heavyAttackWindUp"
                                    type="number"
                                    min="0"
                                    step="any"
                                >

                                <small>Opcional. Permite evaluar ataques pesados.</small>
                            </div>
                        </div>
                    </div>

                    <div id="burstFields" class="section conditional-group">
                        <h2 class="section-title">Datos de ráfaga</h2>

                        <div class="grid">
                            <div class="field">
                                <label class="required" for="burstCount">
                                    Disparos por ráfaga
                                </label>

                                <input
                                    id="burstCount"
                                    type="number"
                                    min="1"
                                    step="1"
                                >
                            </div>
                        </div>
                    </div>

                    <div id="pelletFields" class="section conditional-group">
                        <h2 class="section-title">Datos de perdigones</h2>

                        <div class="grid">
                            <div class="field">
                                <label class="required" for="pelletCount">
                                    Cantidad de perdigones
                                </label>

                                <input
                                    id="pelletCount"
                                    type="number"
                                    min="1"
                                    step="1"
                                >
                            </div>
                        </div>
                    </div>

                    <div id="chargeFields" class="section conditional-group">
                        <h2 class="section-title">Datos de carga</h2>

                        <div class="grid">
                            <div class="field">
                                <label class="required" for="chargeTime">
                                    Tiempo de carga (s)
                                </label>

                                <input
                                    id="chargeTime"
                                    type="number"
                                    min="0.01"
                                    step="any"
                                >
                            </div>
                        </div>
                    </div>

                    <div id="projectileFields" class="section conditional-group">
                        <h2 class="section-title">Datos de proyectil</h2>

                        <div class="grid">
                            <div class="field">
                                <label for="projectileSpeed">
                                    Velocidad del proyectil
                                </label>

                                <input
                                    id="projectileSpeed"
                                    type="number"
                                    min="0"
                                    step="any"
                                >

                                <small>Campo opcional durante el MVP.</small>
                            </div>
                        </div>
                    </div>

                    <div id="explosiveFields" class="section conditional-group">
                        <h2 class="section-title">Datos de explosión</h2>

                        <div class="grid">
                            <div class="field">
                                <label for="explosionRadius">
                                    Radio de explosión
                                </label>

                                <input
                                    id="explosionRadius"
                                    type="number"
                                    min="0"
                                    step="any"
                                >

                                <small>Campo opcional durante el MVP.</small>
                            </div>
                        </div>
                    </div>

                    <div id="beamFields" class="section conditional-group">
                        <h2 class="section-title">Datos de haz</h2>

                        <div class="grid">
                            <div class="field">
                                <label for="beamRange">
                                    Alcance del haz
                                </label>

                                <input
                                    id="beamRange"
                                    type="number"
                                    min="0"
                                    step="any"
                                >

                                <small>Campo opcional durante el MVP.</small>
                            </div>
                        </div>
                    </div>

                    <button id="analyzeButton" class="submit-button" type="submit">
                        Analizar arma
                    </button>
                </form>
            </section>

            <aside class="panel result-panel">
                <h2 class="result-title">Resultado del análisis</h2>

                <p class="result-help">
                    La respuesta debe identificar la tendencia del arma,
                    fortalezas, debilidades, estilo recomendado y estadísticas
                    que conviene o no conviene priorizar.
                </p>

                <div id="resultBox" class="result-box result-placeholder">
                    Completa el formulario y ejecuta el análisis.
                </div>

                <div class="scope">
                    Alcance del MVP: recomendaciones estadísticas generales.
                    No se solicitan mods concretos, polaridades, Formas, Arcanos,
                    Rivens ni configuraciones completas.
                </div>
            </aside>
        </div>
    </main>

    <script>
        const damageTypes = [
            ["impact", "Impacto"],
            ["puncture", "Perforación"],
            ["slash", "Corte"],
            ["heat", "Calor"],
            ["cold", "Frío"],
            ["electricity", "Electricidad"],
            ["toxin", "Toxina"],
            ["blast", "Explosión"],
            ["corrosive", "Corrosivo"],
            ["gas", "Gas"],
            ["magnetic", "Magnético"],
            ["radiation", "Radiación"],
            ["viral", "Viral"],
            ["void", "Vacío"]
        ];

        const form = document.getElementById("weaponForm");
        const weaponCategory = document.getElementById("weaponCategory");
        const firingMode = document.getElementById("firingMode");
        const damageDelivery = document.getElementById("damageDelivery");
        const hasMultiplePellets = document.getElementById("hasMultiplePellets");
        const isExplosive = document.getElementById("isExplosive");
        const resultBox = document.getElementById("resultBox");
        const analyzeButton = document.getElementById("analyzeButton");
        const damageList = document.getElementById("damageList");

        const conditionalSections = {
            rangedClassification: document.getElementById("rangedClassification"),
            rangedSection: document.getElementById("rangedSection"),
            meleeSection: document.getElementById("meleeSection"),
            burst: document.getElementById("burstFields"),
            pellets: document.getElementById("pelletFields"),
            charge: document.getElementById("chargeFields"),
            projectile: document.getElementById("projectileFields"),
            explosive: document.getElementById("explosiveFields"),
            beam: document.getElementById("beamFields")
        };

        const conditionalInputs = {
            rangedClassification: ["firingMode", "damageDelivery"],
            rangedSection: ["fireRate", "multishot", "magazineSize", "reloadTime"],
            meleeSection: ["attackSpeed", "range"],
            burst: ["burstCount"],
            pellets: ["pelletCount"],
            charge: ["chargeTime"]
        };

        function setSectionVisibility(section, visible) {
            section.classList.toggle("visible", visible);
        }

        function setRequired(ids, required) {
            ids.forEach((id) => {
                document.getElementById(id).required = required;
            });
        }

        function updateVisibleFields() {
            const isMelee = weaponCategory.value === "melee";
            const isRanged = !isMelee;

            setSectionVisibility(conditionalSections.rangedClassification, isRanged);
            setSectionVisibility(conditionalSections.rangedSection, isRanged);
            setSectionVisibility(conditionalSections.meleeSection, isMelee);

            setRequired(conditionalInputs.rangedClassification, isRanged);
            setRequired(conditionalInputs.rangedSection, isRanged);
            setRequired(conditionalInputs.meleeSection, isMelee);

            const isBurst = isRanged && firingMode.value === "burst";
            const isCharge = isRanged && firingMode.value === "charge";
            const usesProjectiles = isRanged && damageDelivery.value === "projectile";
            const usesBeam = isRanged && damageDelivery.value === "beam";
            const usesPellets = isRanged && hasMultiplePellets.checked;
            const usesExplosion = isRanged && isExplosive.checked;

            setSectionVisibility(conditionalSections.burst, isBurst);
            setSectionVisibility(conditionalSections.charge, isCharge);
            setSectionVisibility(conditionalSections.projectile, usesProjectiles);
            setSectionVisibility(conditionalSections.beam, usesBeam);
            setSectionVisibility(conditionalSections.pellets, usesPellets);
            setSectionVisibility(conditionalSections.explosive, usesExplosion);

            setRequired(conditionalInputs.burst, isBurst);
            setRequired(conditionalInputs.charge, isCharge);
            setRequired(conditionalInputs.pellets, usesPellets);
        }

        function createDamageRow(type = "", damage = "") {
            const row = document.createElement("div");
            row.className = "damage-row";

            const typeField = document.createElement("div");
            typeField.className = "field";

            const typeLabel = document.createElement("label");
            typeLabel.textContent = "Tipo de daño";

            const typeSelect = document.createElement("select");
            typeSelect.className = "damage-type";

            damageTypes.forEach(([value, label]) => {
                const option = document.createElement("option");
                option.value = value;
                option.textContent = label;
                option.selected = value === type;
                typeSelect.appendChild(option);
            });

            typeField.append(typeLabel, typeSelect);

            const damageField = document.createElement("div");
            damageField.className = "field";

            const damageLabel = document.createElement("label");
            damageLabel.textContent = "Daño base";

            const damageInput = document.createElement("input");
            damageInput.className = "base-damage";
            damageInput.type = "number";
            damageInput.min = "0";
            damageInput.step = "any";
            damageInput.value = damage;

            damageField.append(damageLabel, damageInput);

            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = "icon-button";
            removeButton.title = "Eliminar tipo de daño";
            removeButton.textContent = "×";

            removeButton.addEventListener("click", () => {
                if (damageList.children.length > 1) {
                    row.remove();
                }
            });

            row.append(typeField, damageField, removeButton);
            damageList.appendChild(row);
        }

        function numberValue(id) {
            const rawValue = document.getElementById(id).value;

            if (rawValue === "") {
                return null;
            }

            return Number(rawValue);
        }

        function buildBaseDamage() {
            const baseDamage = {};

            damageList.querySelectorAll(".damage-row").forEach((row) => {
                const type = row.querySelector(".damage-type").value;
                const rawDamage = row.querySelector(".base-damage").value;

                if (rawDamage === "") {
                    return;
                }

                const damage = Number(rawDamage);

                if (!Number.isFinite(damage) || damage <= 0) {
                    return;
                }

                baseDamage[type] = (baseDamage[type] || 0) + damage;
            });

            return baseDamage;
        }

        function buildWeaponData() {
            const category = weaponCategory.value;

            const weaponData = {
                weapon_category: category,
                base_damage: buildBaseDamage(),
                critical_chance_percent: numberValue("criticalChance"),
                critical_multiplier: numberValue("criticalMultiplier"),
                status_chance_percent: numberValue("statusChance")
            };

            if (category === "primary" || category === "secondary") {
                weaponData.firing_mode = firingMode.value;
                weaponData.damage_delivery = damageDelivery.value;
                weaponData.has_multiple_pellets = hasMultiplePellets.checked;
                weaponData.is_explosive = isExplosive.checked;
                weaponData.fire_rate = numberValue("fireRate");
                weaponData.multishot = numberValue("multishot");
                weaponData.magazine_size = numberValue("magazineSize");
                weaponData.reload_time = numberValue("reloadTime");

                if (firingMode.value === "burst") {
                    weaponData.shots_per_burst = numberValue("burstCount");
                }

                if (firingMode.value === "charge") {
                    weaponData.charge_time = numberValue("chargeTime");
                }

                if (hasMultiplePellets.checked) {
                    weaponData.pellet_count = numberValue("pelletCount");
                }

                if (damageDelivery.value === "projectile") {
                    const projectileSpeed = numberValue("projectileSpeed");

                    if (projectileSpeed !== null) {
                        weaponData.projectile_speed = projectileSpeed;
                    }
                }

                if (isExplosive.checked) {
                    const explosionRadius = numberValue("explosionRadius");

                    if (explosionRadius !== null) {
                        weaponData.explosion_radius = explosionRadius;
                    }
                }

                if (damageDelivery.value === "beam") {
                    const beamRange = numberValue("beamRange");

                    if (beamRange !== null) {
                        weaponData.beam_range = beamRange;
                    }
                }
            }

            if (category === "melee") {
                weaponData.attack_speed = numberValue("attackSpeed");
                weaponData.range = numberValue("range");

                const heavyAttackDamage = numberValue("heavyAttackDamage");
                const heavyAttackWindUp = numberValue("heavyAttackWindUp");

                if (heavyAttackDamage !== null) {
                    weaponData.heavy_attack_damage = heavyAttackDamage;
                }

                if (heavyAttackWindUp !== null) {
                    weaponData.heavy_attack_wind_up = heavyAttackWindUp;
                }
            }

            return weaponData;
        }

        function validateBaseDamage() {
            const baseDamage = buildBaseDamage();

            if (Object.keys(baseDamage).length === 0) {
                throw new Error("Introduce al menos un valor de daño base mayor que cero.");
            }
        }

        async function submitAnalysis(event) {
            event.preventDefault();

            resultBox.className = "result-box";
            resultBox.textContent = "Analizando estadísticas...";
            analyzeButton.disabled = true;
            analyzeButton.textContent = "Analizando...";

            try {
                validateBaseDamage();

                const response = await fetch("/analyze", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(buildWeaponData())
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || "No fue posible completar el análisis.");
                }

                const result = data.result;

                resultBox.className = "result-box success";
                resultBox.textContent = typeof result === "string"
                    ? result
                    : JSON.stringify(result, null, 2);

            } catch (error) {
                resultBox.className = "result-box error";
                resultBox.textContent = error.message;

            } finally {
                analyzeButton.disabled = false;
                analyzeButton.textContent = "Analizar arma";
            }
        }

        document
            .getElementById("addDamageButton")
            .addEventListener("click", () => createDamageRow("impact", ""));

        weaponCategory.addEventListener("change", updateVisibleFields);
        firingMode.addEventListener("change", updateVisibleFields);
        damageDelivery.addEventListener("change", updateVisibleFields);
        hasMultiplePellets.addEventListener("change", updateVisibleFields);
        isExplosive.addEventListener("change", updateVisibleFields);
        form.addEventListener("submit", submitAnalysis);

        createDamageRow("impact", "");
        createDamageRow("puncture", "");
        createDamageRow("slash", "");

        updateVisibleFields();
    </script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(HTML)


@app.post("/analyze")
def analyze():
    weapon_data = request.get_json(silent=True)

    if not isinstance(weapon_data, dict):
        return jsonify({
            "error": "No se recibieron datos válidos del arma."
        }), 400

    try:
        result = analyze_weapon(weapon_data)
        return jsonify({
            "result": result
        })

    except Exception:
        app.logger.exception("Error al analizar el arma.")
        return jsonify({
            "error": "No fue posible completar el análisis."
        }), 500


def open_browser() -> None:
    webbrowser.open_new(f"http://127.0.0.1:{PORT}")


def main() -> None:
    Timer(1, open_browser).start()

    app.run(
        host="127.0.0.1",
        port=PORT,
        debug=False,
        threaded=False,
        use_reloader=False
    )


if __name__ == "__main__":
    main()