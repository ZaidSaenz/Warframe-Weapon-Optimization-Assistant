# Architecture

## 1. Objective

The project implements a local Warframe Cephalon specialized in weapon information.

The architecture intentionally separates deterministic computation from language generation.

The main rule is:

**Python = truth
LLM = interpretation**

Python calculates and retrieves facts.

Qwen interprets the user's intent, selects tools, combines observations, and explains the result naturally.

---

# 2. High-level flow

Warframe source data
↓
weapon_data_downloader.py
↓
ExportWeapons.json
↓
weapon_database.py
↓
weapons.json
↓
weapon_views.py
↓
Cephalon tools
↓
cephalon_agent.py
↓
Qwen3.5-4B
↓
warframe_localization.py
↓
user

---

# 3. Weapon database

Module:

modules/weapon_database.py

Responsibilities:

* read raw Warframe weapon data
* select supported weapon populations
* normalize fields
* preserve canonical statistics
* calculate derived deterministic values
* calculate population-relative values
* generate reports
* generate normalized output
* trigger weapon-view generation

The normalized database is the factual foundation of the project.

The language model does not calculate weapon statistics.

---

# 4. Weapon views

Module:

modules/weapon_views.py

The agent does not need the complete normalized database for every request.

Instead, deterministic views are generated for specific tasks.

Current views:

* weapon_lookup.json
* weapon_profiles.json
* weapon_compare.json
* weapon_search.json

Each view has a different purpose.

### Lookup

Used for exact weapon facts.

### Profile

Used for relative strengths and weaknesses.

### Compare

Used for deterministic comparison between exact weapons.

### Search

Used for deterministic candidate discovery.

This keeps analytical work in Python instead of asking the model to reconstruct relationships from raw data.

---

# 5. Tool layer

The Cephalon currently exposes four tools.

## get_weapon

Purpose:

Retrieve exact facts about one known weapon.

Typical information includes:

* damage
* critical chance
* critical multiplier
* status chance
* multishot
* trigger type
* fire rate
* magazine
* reload
* Riven disposition
* structured weapon mechanics

Example:

¿Cuánto crítico tiene Hek?

Expected behavior:

get_weapon("Hek")
→ answer

---

## get_weapon_profile

Purpose:

Retrieve deterministic relative characteristics for one weapon.

Examples:

* high critical chance
* low status chance
* large magazine
* slow reload
* unusually high fire rate

The classifications are calculated before the model sees them.

The model explains them but does not create them.

---

## compare_weapons

Purpose:

Prepare deterministic values for comparing exact weapon names.

Python prepares the factual comparison.

Qwen explains the relevant differences.

---

## search_weapons

Purpose:

Find weapons satisfying deterministic criteria.

Examples include:

* high critical chance
* large magazine
* high status chance

Filtering and ranking happen in Python.

The language model does not invent the candidate list or ranking.

---

# 6. Cephalon agent

Module:

modules/cephalon_agent.py

Current model:

Qwen3.5-4B

The Cephalon is a bounded tool-using agent.

For every user request the model can:

1. interpret the request;
2. choose a tool;
3. read the result;
4. decide whether another tool is necessary;
5. continue until enough information has been collected;
6. generate the final answer.

---

# 7. Sequential tool use

A compound question may require more than one tool.

Example:

¿Qué armas primarias tienen crítico alto y cargador grande, y cómo funciona la primera?

Observed behavior:

Step 1
search_weapons

Result
Amprex ranked first

Step 2
get_weapon("Amprex")

Result
exact Amprex facts

Final
natural-language answer

There is no Python rule saying:

after search_weapons, always call get_weapon

The model decides whether another step is necessary from the original request and the previous observation.

---

# 8. Agent bounds

The current maximum number of sequential tool rounds is:

MAX_TOOL_STEPS = 3

This provides limited autonomy while preventing uncontrolled loops.

Expected behavior:

Simple request:

get_weapon
→ answer

Compound request:

search
→ inspect candidate
→ answer

The model should stop as soon as the original question can be answered.

---

# 9. Native Qwen tool calls

Qwen3.5 may emit native tool-call markup rather than structured llama.cpp tool calls.

Example:

<tool_call>
<function=get_weapon>
<parameter=weapon_name>
Hek </parameter> </function>
</tool_call>

cephalon_agent.py contains a fallback parser that converts this representation into the internal tool-call structure used by the application.

This allows the current Qwen GGUF chat template to work reliably with the agent loop.

---

# 10. Tool-call history

Qwen3.5's native chat template expects tool arguments inserted into conversation history to be mappings.

Tool execution may use serialized JSON arguments internally.

Before a tool call is returned to the model history, the arguments are converted back into a dictionary.

This distinction prevents errors inside the Qwen Jinja chat template.

---

# 11. Visible reasoning

Qwen3.5 may produce internal reasoning before the final response.

When the output contains a reasoning section ending in:

</think>

the application removes that section before presenting the final response.

Only the final user-facing answer is shown.

---

# 12. Spanish localization

Module:

modules/warframe_localization.py

Sources:

data/raw/dict.en.json
data/raw/dict.es.json

Both dictionaries use the same internal Warframe localization keys.

Python crosses those keys and builds an English → Spanish localization index.

---

# 13. Exact localization

When an English string exists in both localization dictionaries, the Spanish version can be recovered deterministically.

Example:

Electricity
→ Electricidad

Weapon descriptions can also be resolved this way.

Example:

official_description
→ English localized description

official_description_es
→ corresponding Spanish localized description

The original English field remains intact.

---

# 14. Technical fallback glossary

Some internal analytical labels do not exist as exact standalone Warframe localization strings.

For those cases a small explicit fallback glossary is used.

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

Fallback values are distinguished internally from exact dictionary matches.

The project should never silently claim that a manually defined fallback came directly from the Warframe localization files.

---

# 15. Context strategy

The complete localization dictionaries are not sent to Qwen.

Instead:

large localization dataset
↓
Python lookup
↓
compact relevant terminology
↓
Qwen

This preserves context space.

The same principle should eventually be applied to large tool results.

If a question only needs critical chance, the ideal future tool observation should not need to include every unrelated weapon field.

---

# 16. Model configuration

Current tested model:

Qwen_Qwen3.5-4B-Q4_K_M.gguf

Current tested configuration:

* context: 4096
* threads: 4
* GPU layers: 0
* llama-cpp-python: 0.3.35

These values describe the current development environment and should not be treated as permanent architectural requirements.

---

# 17. Responsibility boundaries

## Python owns

* canonical facts
* normalization
* calculations
* population statistics
* filtering
* ranking
* comparison values
* localization lookup
* tool execution
* deterministic classifications

## Qwen owns

* intent recognition
* tool selection
* small multi-step planning
* deciding when enough information has been gathered
* natural-language explanation
* conversational response generation

## Qwen should not own

* canonical weapon statistics
* percentile calculations
* ranking algorithms
* deterministic filtering
* database truth

---

# 18. Why this architecture

Previous versions of the project experimented with more explicit interpretation pipelines, rule engines, knowledge retrieval, structured analysis contracts, and heavy prompt preparation.

The current design intentionally reduces those layers.

Instead, the project uses:

verified data
+
small deterministic tools
+
a capable local language model

This keeps the system easier to understand, test, and maintain.

The language model gains limited navigation freedom without gaining authority over factual data.

---

# 19. Legacy modules

Some modules from previous project iterations may still exist in the repository.

Examples may include older interpretation, prompt-construction, rule-engine, AI-generation, or pipeline modules.

They are not automatically part of the current Cephalon execution path.

The current primary architecture is:

weapon_database
→ weapon_views
→ cephalon_agent
→ warframe_localization

Legacy components should be removed only after confirming that no active code depends on them.

---

# 20. Future extension

Possible future domains include:

* mods
* Warframes
* enemies
* resources
* game mechanics
* lore

Each new domain should expose small deterministic tools.

The Cephalon can then choose between them.

A multi-agent architecture is not currently necessary.

The preferred future direction is:

one capable local agent
+
more reliable tools

rather than:

many specialized agents
