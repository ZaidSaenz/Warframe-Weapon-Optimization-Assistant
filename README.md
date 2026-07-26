# Warframe Weapon Optimization Assistant

A local, evidence-aware weapon analysis system for **Warframe**.

The project transforms raw weapon export data into normalized statistics, auditable interpretation signals, relevant domain knowledge, and concise AI-generated recommendations.

Rather than asking a language model to understand an entire weapon from unstructured data, the application performs most analytical work deterministically before generation:

```text
Warframe export data
→ normalization
→ evidence-aware interpretation
→ rule-based concept retrieval
→ compact prompt construction
→ local language model
→ validated JSON analysis
```

The language model is primarily responsible for contextual synthesis and explanation. It is not expected to invent weapon mechanics, reconstruct missing statistics, or make unsupported build claims.

---

## Project status

**Active prototype — under continued refinement**

The deterministic analysis pipeline is functional and covered by automated tests. The current interpretation contract uses version 6 and preserves:

* Structured and derived signals
* Confidence levels
* Source paths
* Per-mode profiles
* Description-derived mechanic records
* Multi-target mechanic records
* Operational friction records
* Activated knowledge concepts
* Valid improvement parameters

The main remaining experimentation is concentrated in the final generation layer:

* Refining `modules/prompt_builder.py`
* Refining validation and repair behavior in `modules/ai.py`
* Comparing local language models
* Deciding whether to keep the current Qwen model, use a larger model, or perform targeted fine-tuning
* Improving the separation between factual weapon data and AI recommendations in the interface

Some files, especially `main.py`, `modules/ai.py`, and parts of the testing organization, should still be considered provisional.

This repository should not yet be treated as a stable release or finalized public API.

---

## What the project does

The assistant can:

* Normalize structured Warframe weapon data
* Separate weapon statistics from inferred behavior
* Identify relevant attack modes and damage-delivery patterns
* Detect supported mechanics such as beam delivery, chaining, radial application, and reload behavior
* Evaluate critical and status profiles without treating individual statistics as universal verdicts
* Retrieve only the knowledge concepts relevant to the selected weapon
* Produce concise Spanish-language analysis
* Suggest a primary practical role
* Identify supported strengths and limitations
* Recommend valid improvement parameters
* Separate operational comfort from combat function
* Validate the generated JSON before presenting it

The project is designed around traceable evidence. Deterministic conclusions retain their source fields and confidence classification.

---

## What the project does not do

The assistant is not intended to:

* Calculate real DPS
* Replace Warframe build calculators
* Generate complete mod configurations
* Recommend Warframes, companions, Arcanes, Rivens, or external loadouts
* Infer mechanics from weapon names
* Invent missing statistics
* Treat community popularity as weapon quality
* Declare weapons meta, obsolete, useless, or overpowered
* Guarantee optimal recommendations for every game mode or enemy type
* Replace practical testing or established community research

The current goal is to explain a weapon's supported behavior and improvement directions, not to produce a complete endgame build.

---

## Current architecture

### 1. Weapon database and normalization

`modules/weapon_database.py`

Processes Warframe export data and converts eligible weapons into a consistent normalized schema.

The normalized representation preserves information such as:

* Classification
* Weapon class
* Shared statistics
* Root statistics
* Attack modes
* Damage components
* Trigger behavior
* Critical and status values
* Magazine and reload information
* Structured mechanics when available
* Description references
* Normalization warnings

Raw source files and generated normalized datasets may be excluded from the public repository and rebuilt locally.

### 2. Deterministic interpretation

`modules/weapon_interpreter.py`

Converts normalized weapon data into an auditable interpretation contract.

The version 6 output includes:

```text
signals
flat_signals
mode_profiles
records
```

Each full signal may contain:

```json
{
  "value": true,
  "confidence": "derived",
  "source_paths": [
    "attack_modes[].damage_components"
  ],
  "reason": null
}
```

Supported confidence categories include:

* `structured`
* `normalized`
* `derived`
* `validated_description`
* `heuristic`
* `unavailable`

Unknown evidence is not automatically treated as false.

### 3. Rule evaluation

`modules/rule_engine.py`

Evaluates the interpretation signals against the local retrieval rules.

Rules determine which knowledge concepts are relevant to the current weapon. They can evaluate values and confidence requirements without delegating concept selection to the language model.

Example flow:

```text
confirmed beam delivery
→ retrieve beam_behavior

confirmed chaining
→ retrieve multi_target_delivery

critical chance and multiplier present
→ retrieve critical_profile
```

### 4. Knowledge library

`knowledge/concepts/`

Contains reusable Warframe weapon-analysis concepts.

Current concept areas include:

* Primary job selection
* Improvement selection
* Critical profile
* Status application
* Attack rhythm
* Damage delivery
* Description evidence
* Reload friction
* Sustained damage
* Beam behavior
* Multi-target delivery
* Multi-instance delivery
* Multi-mode behavior
* Operational comfort
* Melee behavior
* Ammunition pressure
* Special mechanics

`knowledge/rules/`

Contains deterministic retrieval rules that connect interpretation signals to relevant concepts.

The language model does not independently browse this library. Python selects the relevant concepts before generation.

### 5. Prompt construction

`modules/prompt_builder.py`

Builds a compact evidence package for the local model.

The prompt builder removes or avoids:

* `null` values
* Empty structures
* Unavailable evidence
* Heuristic evidence presented as confirmed
* Irrelevant negative flags
* Redundant normalized data
* Unrelated knowledge branches

The complete pipeline state remains available for auditing, while the model receives only the evidence needed for final synthesis.

### 6. Local AI generation

`modules/ai.py`

Loads the local GGUF model through `llama-cpp-python`, generates the final analysis, validates the JSON schema, checks selected semantic contradictions, and performs one optional repair attempt when generation fails validation.

The current development model is expected at:

```text
models/Qwen2.5-3B-Instruct-Q4_K_M.gguf
```

The model file is not included in the repository.

The current model is useful for development, but a slightly larger local model may provide more reliable reasoning while preserving the same deterministic architecture.

### 7. Pipeline orchestration

`modules/weapon_pipeline.py`

Coordinates the deterministic stages:

```text
normalized weapon
→ interpretation
→ activated concepts
→ retrieved knowledge
→ analysis context
```

The model is only invoked after this state has been prepared.

---

## Repository scope

This public repository contains the reproducible core of the project.

Some resources are intentionally excluded because they are large, generated, machine-specific, experimental, or not ready for publication.

Typical excluded resources include:

* Local GGUF models
* Other model binaries
* Virtual environments
* Environment-variable files
* Logs
* Python caches
* Test caches
* Coverage data
* IDE configuration
* Local Flask instance data
* Temporary files
* Generated datasets
* Generated analysis libraries
* Experimental outputs
* Provisional local tests

Their absence does not necessarily indicate that the project is broken or abandoned.

The intention is to publish the core implementation while keeping large and reproducible artifacts outside version control.

---

## Expected local paths

The current development structure expects paths similar to:

```text
Warframe-Weapon-Optimization-Assistant/
├── data/
│   ├── raw/
│   │   ├── ExportWeapons.json
│   │   ├── ExportWeapons.metadata.json
│   │   ├── ExportWeapons.profile.txt
│   │   └── dict.en.json
│   └── normalized/
│       └── weapons.json
├── knowledge/
│   ├── concepts/
│   └── rules/
├── models/
│   └── Qwen2.5-3B-Instruct-Q4_K_M.gguf
├── modules/
├── tests/
├── main.py
├── requirements.txt
└── README.md
```

Depending on the current branch and development stage, generated data directories may need to be created locally.

---

## Requirements

* Python 3.12 or compatible version
* A C/C++ build environment supported by `llama-cpp-python`
* Sufficient RAM for the selected GGUF model
* Optional NVIDIA GPU and CUDA-compatible `llama-cpp-python` build
* Warframe export data for rebuilding the local weapon database

The current Python dependencies are listed in:

```text
requirements.txt
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/ZaidSaenz/Warframe-Weapon-Optimization-Assistant.git
cd Warframe-Weapon-Optimization-Assistant
```

### 2. Create a virtual environment

Linux or macOS:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Installing `llama-cpp-python` with GPU acceleration may require a platform-specific installation command. The default requirements file does not guarantee CUDA acceleration on every system.

### 4. Add the local model

Create the model directory:

```bash
mkdir -p models
```

Place the expected GGUF model at:

```text
models/Qwen2.5-3B-Instruct-Q4_K_M.gguf
```

The configured model name and path can currently be changed in:

```text
modules/ai.py
```

Model files must not be committed to the repository.

### 5. Add the Warframe source data

Place the required source exports in:

```text
data/raw/
```

Expected source files may include:

```text
ExportWeapons.json
ExportWeapons.metadata.json
ExportWeapons.profile.txt
dict.en.json
```

The exact source set may change as normalization support evolves.

### 6. Generate the normalized database

Run the current normalization command:

```bash
python -m modules.weapon_database normalize
```

The expected output is:

```text
data/normalized/weapons.json
```

Review the normalization report for excluded, partial, fallback, or suspicious records before relying on the generated database.

---

## Running the tests

```bash
python -m pytest -q
```

The current test suite covers the interpretation contract, rule evaluation, knowledge retrieval, prompt construction compatibility, and pipeline integration.

Tests are still being reorganized. Some experimental or provisional tests may remain excluded until their structure is suitable for publication.

---

## Inspecting the deterministic pipeline

The deterministic pipeline can be tested without loading the language model.

Example:

```bash
python - <<'PY'
from pprint import pprint

from modules.weapon_database import find_weapons
from modules.weapon_pipeline import prepare_weapon_analysis

matches = find_weapons("Amprex")

if not matches:
    raise SystemExit("Weapon not found.")

state = prepare_weapon_analysis(matches[0])

print("Activated concepts:")
pprint(state["activated_concepts"])

print("\nFlat signals:")
pprint(state["flat_signals"])

print("\nRecords:")
pprint(state["records"])
PY
```

---

## Inspecting the generated prompt without AI

```bash
python - <<'PY'
from modules.prompt_builder import build_weapon_prompt
from modules.weapon_database import find_weapons
from modules.weapon_pipeline import prepare_weapon_analysis

matches = find_weapons("Amprex")

if not matches:
    raise SystemExit("Weapon not found.")

prepared = prepare_weapon_analysis(matches[0])

prompt = build_weapon_prompt(
    weapon_data=prepared["weapon_data"],
    analysis_context=prepared["analysis_context"],
)

print(prompt)
print(f"\nPrompt length: {len(prompt)} characters")
PY
```

This command prepares normalization-derived evidence, rule retrieval, and relevant knowledge without loading or calling the local model.

---

## Running a local analysis

```bash
python - <<'PY'
from modules.ai import analyze_weapon_state, format_analysis
from modules.weapon_database import find_weapons

matches = find_weapons("Amprex")

if not matches:
    raise SystemExit("Weapon not found.")

state = analyze_weapon_state(matches[0])

print(format_analysis(state["analysis"]))
PY
```

The first inference may take longer because the GGUF model is loaded lazily.

---

## Running the application

```bash
python main.py
```

The current Flask interface is provisional and may change significantly.

The planned interface direction is to separate:

### Factual weapon data

Displayed directly from the normalized database:

* Weapon category
* Weapon class
* Mastery rank
* Damage
* Critical statistics
* Status statistics
* Fire rate or attack speed
* Magazine
* Reload
* Multishot
* Trigger type
* Supported mechanics
* Riven disposition when preserved

### AI-generated analysis

Displayed separately:

* Primary practical role
* Reasoning
* Strengths
* Limitations
* Improvement priorities
* Operational comfort

This separation keeps factual data visible even when generation quality varies.

---

## Generated analysis library

A future stage of the project may generate and store validated analyses for all eligible weapons.

Planned flow:

```text
normalized weapon database
→ deterministic pipeline
→ local AI generation
→ validation
→ versioned analysis library
```

This would allow the user interface to read pre-generated results instead of loading the model for every request.

Stored records should eventually preserve:

* Weapon ID
* Weapon name
* Source schema version
* Interpretation version
* Knowledge version
* Prompt version
* Model ID
* Activated concepts
* Relevant signals
* Validation status
* Final analysis
* Prompt or evidence hash

This would support later filtering, comparison, dashboards, similarity searches, and model-regression testing.

---

## Development priorities

### Current

* Refine `modules/prompt_builder.py`
* Refine validation and repair in `modules/ai.py`
* Benchmark larger local models
* Evaluate targeted fine-tuning versus model replacement
* Preserve the stable deterministic pipeline
* Build a control set covering multiple weapon behaviors

### Next

* Separate factual data from recommendations in the interface
* Preserve and display Riven disposition
* Improve application configuration
* Add `.env.example` or `config.example`
* Document model-selection options
* Reorganize the test suite
* Add batch-generation tooling
* Version generated analysis results

### Later

* Build a complete offline weapon-analysis library
* Add weapon comparisons
* Add behavioral similarity searches
* Add filters by primary role, mechanics, friction, and improvement direction
* Add data-quality and confidence dashboards

---

## Provisional components

The following areas are expected to change:

### `main.py`

The current application entry point and UI are experimental.

### `modules/ai.py`

Model selection, generation parameters, semantic validation, and repair behavior remain under evaluation.

### `modules/prompt_builder.py`

The prompt is being refined to balance:

* Compactness
* Evidence coverage
* Output quality
* Small-model reliability
* Strict grounding

### Tests

The interpretation and rule contracts are covered, but test organization and the publication of broader weapon-control cases remain ongoing work.

### Model choice

The current Qwen 3B model is not necessarily the final model. Larger local models are being considered for more consistent evidence-based synthesis.

---

## Design principles

* Deterministic evidence before language generation
* Traceable conclusions
* Unknown does not mean false
* Mechanics are not improvement parameters
* Statistics are evidence, not universal verdicts
* Operational comfort is separate from combat function
* The language model should explain, not invent
* Generated recommendations must remain machine-validatable
* Large and reproducible artifacts should remain outside Git
* Public documentation should distinguish deliberate exclusions from missing work

---

## Disclaimer

This is an independent fan project and is not affiliated with or endorsed by Digital Extremes.

Warframe and its related names, assets, and data are property of their respective owners.

Weapon behavior, statistics, and disposition values may change through game updates. Generated analyses should be rebuilt when source data, interpretation rules, knowledge concepts, prompts, or models change.

---

## License

This project is distributed under the MIT License. See `LICENSE` for details.
