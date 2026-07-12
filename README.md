
# Warframe Weapon Optimization Assistant

This project is a local AI-powered assistant designed to help players optimize weapons in **Warframe**.

The application uses a **SmolLM2-1.7B-Instruct-Q4_K_M.** language model running locally and a carefully engineered system prompt that defines the AI's role as a weapon optimization expert. Instead of generating random advice, the model analyzes structured weapon statistics provided by the user and returns practical recommendations based on established Warframe build principles.

The assistant focuses on:

* Evaluating a weapon's strengths and weaknesses.
* Identifying the most valuable stats to improve.
* Recommending which attributes should be prioritized.
* Explaining the reasoning behind each recommendation.
* Providing general guidance on possible build directions.

The AI is not intended to replace build calculators or community resources. Instead, it acts as an intelligent advisor that interprets weapon data and offers understandable recommendations for both new and experienced players.

The project is designed around structured inputs rather than free-form conversations. Users provide weapon statistics through a form, and the application constructs a specialized prompt that is sent to the local Qwen 3B model. The response is then formatted into a clear evaluation with priorities, explanations, and optimization suggestions.

Although this version focuses on **Warframe**, the overall architecture is generic enough to support other games or optimization problems by replacing the system prompt and adapting the input fields.

## Main Features

* Local inference using Qwen 3B.
* No internet connection required.
* Structured weapon analysis.
* Prompt-engineered expert system.
* Explainable recommendations instead of simple scores.
* Easy to extend with new rules and future game updates.

## Goal

The primary goal of this project is to demonstrate how a small local language model can be transformed into a specialized expert system through prompt engineering, providing consistent, explainable, and useful recommendations without requiring model fine-tuning.
