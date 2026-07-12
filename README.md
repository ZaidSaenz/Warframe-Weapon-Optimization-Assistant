
# Warframe Weapon Optimization Assistant

Warframe Weapon Optimization Assistant is a local AI-powered application designed to help players understand how a weapon behaves, identify its most plausible role, and determine which statistics may support that role.

The project currently uses **Qwen2.5-3B-Instruct-Q4_K_M**, running locally through `llama-cpp-python`. The model receives structured weapon data and analyzes it through several independent stages instead of attempting to generate a complete build from a single large prompt.

The assistant is not intended to calculate exact DPS, replace community guides, or determine a universally correct build. Warframe weapons frequently include unique mechanics, alternate firing modes, special effects, and interactions that cannot be reliably evaluated through rigid numerical thresholds alone.

Instead, the project explores a logical analysis approach based on weapon behavior, attack delivery, declared mechanics, and operational characteristics.

## Current Analysis Flow

The current pipeline separates the analysis into four stages:

1. **Weapon behavior**
   Describes how the weapon attacks, how it delivers its hits, and whether it has area effects, multiple hit instances, charged attacks, continuous fire, or declared special mechanics.

2. **Primary job**
   Suggests the most plausible role for the weapon, such as sustained damage, focused damage, group clearing, status application, precision attacks, or heavy attacks.

3. **Improvement directions**
   Identifies statistics that may reinforce the selected role or reduce an observable operational limitation.

4. **Operational comfort**
   Evaluates handling characteristics such as magazine size, reload time, firing rhythm, projectile speed, range, charge time, and other available usability parameters.

Each stage starts with a fresh model context. Only structured results selected by Python are passed between stages, preventing hidden conversation history from affecting later conclusions.

## Main Features

* Local inference using **Qwen2.5-3B-Instruct-Q4_K_M**.
* No internet connection required during normal operation.
* Structured weapon input instead of unrestricted conversation.
* Independent prompts for behavior, role, improvements, and comfort.
* Optional free-text field for unique weapon mechanics.
* JSON-formatted model responses.
* Terminal debugging for prompts, raw responses, parsed data, and analysis state.
* Progress indicators for each inference stage.
* Explainable recommendations instead of a single numerical score.
* Separation between objective weapon data and AI interpretation.

## Input Structure

The application accepts structured weapon information such as:

* Weapon category.
* Firing mode.
* Damage delivery type.
* Base damage distribution.
* Critical chance and critical multiplier.
* Status chance.
* Fire rate.
* Multishot.
* Magazine size.
* Reload time.
* Pellet count.
* Projectile speed.
* Beam range.
* Explosion radius.
* Melee range and attack speed.
* Heavy attack information.
* Optional unique or special mechanic description.

The unique mechanic field is optional. If it is empty, the model must not invent or infer a passive, alternate attack, transformation, or special effect from the weapon name.

## Architecture

```text
Structured weapon data
        ↓
weapon_parser.py
Validates and normalizes objective data
        ↓
prompt_builder.py
Selects the data required for each analysis stage
        ↓
weapon_interpreter.py
Coordinates the stages and validates model responses
        ↓
ai.py
Loads Qwen once and runs independent local inferences
        ↓
Structured analysis result
```

### `weapon_parser.py`

Responsible for:

* Validating required fields.
* Normalizing values.
* Separating ranged and melee data.
* Preserving optional special mechanics.
* Producing consistent structured input.

It should not decide whether a weapon is good, bad, critical-focused, status-focused, or suitable for a specific build.

### `prompt_builder.py`

Responsible for:

* Selecting only the relevant fields for each stage.
* Preventing unnecessary data repetition.
* Building compact stage-specific data prompts.

### `weapon_interpreter.py`

Responsible for:

* Running the stages in the correct order.
* Preserving structured results between stages.
* Parsing JSON responses.
* Validating allowed jobs, parameters, and comfort classifications.
* Handling retries when the model breaks the expected format.

### `ai.py`

Responsible for:

* Loading the local GGUF model once.
* Providing the stable Warframe reasoning context.
* Supplying stage-specific examples.
* Creating a fresh conversation for every stage.
* Executing local inference.
* Reporting stage progress in the terminal.

## Current Status

The current implementation is an experimental checkpoint.

Qwen2.5-3B follows the requested JSON format more consistently than the previous SmolLM2 model and identifies basic weapon roles more reliably. For example, an automatic hitscan weapon with repeated direct attacks and a large magazine can be recognized as a sustained-damage weapon.

However, several parts still require refinement:

* Behavioral descriptions may use imprecise wording.
* Operational relationships such as magazine duration and reload frequency need better preprocessing.
* Improvement suggestions may focus on correcting a weakness while overlooking an existing strength worth reinforcing.
* Comfort analysis may incorrectly treat fast fire rate as a usability problem.
* Missing accuracy, recoil, and ammunition information must be handled more explicitly.
* More contrasting weapon examples are needed to test the reasoning system.

The current output should therefore be treated as an analysis prototype, not as a final build recommendation system.

## Planned Improvements

The next development stage will focus on stabilizing the JSON input and expected output before modifying the user interface.

Planned module changes include:

### `modules/weapon_parser.py`

* Add objective operational facts.
* Estimate firing-window duration when the weapon type supports it.
* Estimate the relationship between firing time and reload interruption.
* Add optional ammunition, range, Punch Through, and weapon-class fields.
* Avoid calculations that are invalid for beams, batteries, shell reloads, or unique weapon mechanics.

### `modules/prompt_builder.py`

* Include derived operational facts in the appropriate stages.
* Pass newly supported optional fields.
* Reduce ambiguous or unnecessary data.

### `modules/weapon_interpreter.py`

* Improve response validation.
* Reject unsupported comfort conclusions.
* Prevent positive traits from being returned as frictions.
* Better separate reinforcement suggestions from corrections.

### `modules/ai.py`

* Refine few-shot examples.
* Improve behavioral terminology.
* Add clearer examples for sustained damage, focused damage, group clearing, status application, precision attacks, and heavy attacks.
* Improve rules for comfort and improvement analysis.

### User interface

The interface will be updated only after the input schema and analysis flow are stable.

Future interface changes may include:

* Optional unique-mechanic text area.
* Additional weapon fields.
* Separate output sections for behavior, role, improvements, and comfort.
* Better visibility of missing information and analysis uncertainty.

## Testing from the Terminal

Use the built-in sample:

```bash
python -m modules.ai --sample
```

Show the structured result:

```bash
python -m modules.ai \
  --sample \
  --show-state
```

Inspect prompts and raw model responses:

```bash
python -m modules.ai \
  --sample \
  --show-state \
  --show-prompts \
  --show-raw
```

Validate the input and inspect the first prompt without running inference:

```bash
python -m modules.ai \
  --sample \
  --no-ai
```

Analyze a custom JSON file:

```bash
python -m modules.ai \
  --input weapon_test.json \
  --show-state \
  --show-prompts \
  --show-raw
```

## Project Goal

The primary goal of this project is to explore how a small local language model can interpret structured game data through logical relationships and examples.

The project does not aim to create a rigid mathematical tier list or claim that every weapon has one correct use. Its goal is to provide a clear and explainable interpretation of:

* What the weapon does.
* What role its behavior may support.
* Which parameters may reinforce that role.
* What operational characteristics may affect its usability.

Although this implementation focuses on **Warframe**, the architecture can be adapted to other games or structured optimization problems by replacing the domain context, examples, input schema, and permitted analysis categories.
