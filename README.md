# Warframe Weapon Optimization Assistant

A local Warframe Cephalon for querying, comparing, and explaining weapon data using deterministic Python tools and a small local language model.

The project follows one central principle:

**Python is responsible for truth.
The language model is responsible for interpretation.**

Weapon statistics, filtering, rankings, comparisons, and localization are handled deterministically before the model produces a response.

The language model is not used as the source of weapon facts.

---

## Current state

The current prototype uses:

* Qwen3.5-4B Q4_K_M
* llama-cpp-python
* Local GGUF inference
* Normalized Warframe weapon data
* Deterministic weapon views
* Tool-based agent behavior
* Maximum of 3 sequential tool steps
* English → Spanish Warframe localization

The current supported domain is:

**Warframe weapons**

---

## Architecture

Warframe export data
↓
weapon_database.py
↓
normalized weapon database
↓
weapon_views.py
↓
Cephalon tools
↓
Qwen3.5-4B
↓
Spanish localization
↓
natural-language response

The current primary execution path is:

weapon_database
→ weapon_views
→ cephalon_agent
→ warframe_localization

---

## Cephalon tools

The agent currently has four weapon tools.

### get_weapon

Returns exact information about one weapon.

Example:

¿Cuánto crítico tiene Hek?

Expected flow:

get_weapon("Hek")
→ answer

---

### get_weapon_profile

Returns deterministic relative characteristics for one weapon.

Example:

¿Cuáles son las fortalezas de Soma Prime?

---

### compare_weapons

Compares two or more exact weapon names.

Example:

Compara Hek y Soma Prime.

---

### search_weapons

Finds weapons satisfying deterministic criteria.

Example:

¿Qué armas primarias tienen crítico alto y cargador grande?

---

## Sequential tool use

The Cephalon can use multiple tools when one tool is not enough.

Example:

¿Qué armas primarias tienen crítico alto y cargador grande, y cómo funciona la primera?

Observed flow:

search_weapons
→ Amprex ranked first
→ get_weapon("Amprex")
→ final answer

The sequence is not hardcoded in Python.

Qwen decides whether another tool is required after reading the previous tool result.

The current safety limit is:

MAX_TOOL_STEPS = 3

---

## Spanish localization

Spanish localization is handled by:

modules/warframe_localization.py

The system uses:

data/raw/dict.en.json
data/raw/dict.es.json

The two dictionaries are crossed using their shared internal Warframe localization keys.

Exact Warframe localization is preferred whenever it is available.

Example:

Electricity
→ Electricidad

Weapon descriptions can also be localized directly from the dictionaries.

A small fallback glossary is used for technical field names that do not exist as exact standalone localization entries.

Examples:

Critical Chance
→ Probabilidad crítica

Fire Rate
→ Cadencia de fuego

Reload
→ Recarga

Status Chance
→ Probabilidad de estado

Riven Disposition
→ Disposición Riven

The complete localization dictionaries are never inserted into the model context.

---

## Model

Current target model:

Qwen3.5-4B

Expected local file:

models/Qwen_Qwen3.5-4B-Q4_K_M.gguf

Current tested configuration:

* Context: 4096
* Threads: 4
* GPU layers: 0
* Quantization: Q4_K_M
* llama-cpp-python: 0.3.35

The GGUF model is not committed to the repository.

---

## Build the weapon database

Run:

python -m modules.weapon_database build

This generates the normalized weapon database and deterministic views used by the Cephalon.

---

## Inspect a weapon

Example:

python -m modules.weapon_database inspect "Soma Prime"

---

## Run the Cephalon

Example:

python -m modules.cephalon_agent --threads 4 --n-ctx 4096 ask "¿Cuánto crítico tiene Hek?"

Debug mode:

python -m modules.cephalon_agent --threads 4 --n-ctx 4096 --debug ask "¿Cuánto crítico tiene Hek?"

---

## Current project structure

data/

* normalized/
* raw/
* reports/
* views/

docs/

* ARCHITECTURE.md
* PROJECT_STATUS.md

models/

* Qwen_Qwen3.5-4B-Q4_K_M.gguf

modules/

* cephalon_agent.py
* warframe_localization.py
* weapon_data_downloader.py
* weapon_database.py
* weapon_views.py

README.md
requirements.txt

---

## Legacy code

Older experimental modules may still exist in the repository.

They belong to previous versions of the project and are not necessarily part of the current execution path.

They will be reviewed separately instead of being removed while the new architecture is still being validated.

---

## Current limitations

The Cephalon currently supports weapons only.

Response quality in Spanish is still being refined.

Some tools return more information than a question strictly requires, so context efficiency can still be improved.

The current 4096-token context has been sufficient for one- and two-tool tests.

---

## Development philosophy

Prefer:

* simple modules
* deterministic calculations
* small tools
* measurable tests
* local execution
* clear responsibility boundaries

Avoid unnecessary complexity such as:

* multi-agent systems
* large semantic rule engines
* unbounded tool loops
* LLM-generated weapon statistics
* large framework dependencies without demonstrated need

The goal is not to make the model responsible for everything.

The goal is to give the model reliable tools and let it explain verified results.

---

## Documentation

Technical architecture:

docs/ARCHITECTURE.md

Current implementation status and next priorities:

docs/PROJECT_STATUS.md

---

## Disclaimer

This is an independent fan project and is not affiliated with or endorsed by Digital Extremes.

Warframe and its related names, assets, and data are property of their respective owners.

Weapon statistics and mechanics may change through game updates.

---

## License

This project is distributed under the MIT License.

See LICENSE for details.
