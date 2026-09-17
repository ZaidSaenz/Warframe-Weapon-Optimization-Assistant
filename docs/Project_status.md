# Project Status

## Current phase

The project has reached a functional:

**Cephalon Agent v1**

The core weapon-agent architecture is working.

The current focus can move away from large architectural changes and toward:

* response quality
* regression testing
* context efficiency
* UI integration

---

# Working components

## Weapon database

Status:

**WORKING**

The database normalizes the supported Warframe weapon population and generates the information required by the deterministic views.

Current approximate populations:

* LongGuns: 194
* Melee: 224
* Pistols: 147

Exact counts may change when upstream Warframe data changes.

---

## Weapon views

Status:

**WORKING**

Current generated views:

* weapon_lookup.json
* weapon_profiles.json
* weapon_compare.json
* weapon_search.json

These provide the factual layer used by the Cephalon tools.

---

## Qwen3.5-4B

Status:

**WORKING**

Current model:

Qwen_Qwen3.5-4B-Q4_K_M.gguf

Tested with:

llama-cpp-python 0.3.35

The model is currently running locally through llama.cpp.

---

## Simple tool routing

Status:

**VALIDATED**

Test:

¿Cuánto crítico tiene Hek?

Observed flow:

get_weapon("Hek")
→ final answer

The agent correctly stopped after one tool call.

No unnecessary second lookup was performed.

---

## Sequential tool use

Status:

**VALIDATED**

Test:

¿Qué armas primarias tienen crítico alto y cargador grande, y cómo funciona la primera?

Observed flow:

Step 1
search_weapons

Step 2
get_weapon("Amprex")

Final
answer

This confirms that Qwen can compose multiple tools without a hardcoded Python workflow.

---

## Agent stopping behavior

Status:

**VALIDATED**

Observed behavior:

simple question
→ 1 tool

compound request
→ 2 tools

Current safety limit:

3 tool steps

The agent currently stops when the information gathered is sufficient for the original request.

---

## Native Qwen tool-call fallback

Status:

**WORKING**

Qwen3.5 may return native XML-like tool calls rather than llama.cpp structured tool calls.

The fallback parser successfully converts them into the internal representation used by the agent.

---

## Tool history compatibility

Status:

**WORKING**

Qwen's native Jinja chat template expects tool arguments in conversation history to be mappings.

The agent now converts them correctly before reinserting tool calls into model history.

This resolved the previous template error.

---

## Visible reasoning cleanup

Status:

**WORKING**

Qwen may generate visible reasoning ending in:

</think>

The application removes this portion before presenting the final response.

---

# Spanish localization

Status:

**WORKING**

Current localization files:

dict.en.json
dict.es.json

Measured test:

* English entries: 35859
* Spanish entries: 35865
* Shared keys: 35859
* Exact translation index: 34437

---

## Exact localization

Status:

**VALIDATED**

Example:

Electricity
→ Electricidad

Source:

Warframe localization dictionary

---

## Fallback terminology

Status:

**WORKING**

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

These entries currently come from the project's explicit fallback glossary when no exact standalone localization entry is found.

---

## Localized weapon descriptions

Status:

**VALIDATED**

The Amprex test successfully produced:

official_description_es

The Spanish description came from the localization dictionaries rather than being generated freely by Qwen.

This confirms that exact localized text can be inserted deterministically into the tool result.

---

# Known issues

## Spanish response quality

The model still occasionally produces awkward Spanish or untranslated words.

Examples observed during testing include:

* rounds
* continuo haz
* arce
* Raven
* récargo
* racha

The underlying facts were generally correct.

This is currently considered a response-style problem rather than a database or agent-architecture problem.

---

## Tool-result size

get_weapon currently returns more information than many questions require.

Example:

¿Cuánto crítico tiene Hek?

The model only needs the critical fields, but the tool may also receive:

* damage
* status
* mechanics
* Riven
* behaviours
* handling
* description

This consumes context unnecessarily.

A future optimization may introduce more compact observations or field projections.

---

## Context window

A 2048-token context was insufficient once tool history and complete tool results were included.

The current 4096-token context successfully handles the tested one- and two-tool flows.

Current policy:

first reduce unnecessary context

then increase n_ctx only if measurements show it is necessary

Simply increasing context should not be the default solution.

---

# Regression benchmark

The following six questions should be used as a small regression suite.

## Test 1

¿Cuánto crítico tiene Hek?

Expected:

get_weapon

---

## Test 2

¿Cuáles son las fortalezas de Soma Prime?

Expected:

get_weapon_profile

---

## Test 3

Compara Hek y Soma Prime.

Expected:

compare_weapons

---

## Test 4

¿Qué primarias tienen crítico alto y cargador grande?

Expected:

search_weapons

---

## Test 5

¿Qué primarias tienen crítico alto y cargador grande y cómo funciona la primera?

Expected:

search_weapons
→ get_weapon

---

## Test 6

¿Cómo funciona el disparo de Trumna?

Expected:

get_weapon

---

# Next priorities

## Priority A — Response quality

Improve:

* Spanish terminology
* grammar
* conciseness
* grounding
* natural explanation

The preferred first approach is prompt/style guidance.

Avoid creating a large text-replacement system.

Avoid adding a dedicated style-correction tool unless testing demonstrates that it is actually necessary.

---

## Priority B — Regression testing

Run the six benchmark questions and record:

* selected tool
* number of tool calls
* factual correctness
* localization quality
* response quality

This should become the baseline before making further agent changes.

---

## Priority C — Context efficiency

Measure context growth for:

* one-tool requests
* two-tool requests
* three-tool requests

If context becomes a problem, compact tool results before increasing the context window.

---

## Priority D — UI integration

Once response quality is stable, connect the validated Cephalon execution path to the UI.

The UI should consume the Cephalon output instead of reimplementing weapon logic.

---

# Not currently recommended

Do not add yet:

* multi-agent architecture
* LangGraph
* large RAG systems
* vector databases
* a style-correction tool
* a second editing model
* large semantic rule engines

The project has not demonstrated a need for these systems.

---

# Legacy architecture

Older project versions used a more complex pipeline involving elements such as:

* interpretation contracts
* rule engines
* concept libraries
* prompt builders
* structured AI analysis
* repair and validation layers

Some of those modules may still exist in the repository.

They should now be treated as legacy or experimental unless the current Cephalon execution path explicitly depends on them.

They should not be presented as the current architecture.

---

# Current definition of the project

The project is currently best described as:

**A local tool-using Warframe Cephalon backed by a deterministic weapon database.**

The current architecture is considered sufficiently stable for continued testing.

Further work should now prioritize answer quality, testing, efficiency, and UI integration rather than another large redesign.
