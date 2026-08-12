# Prompt Rendering and Visibility

This document explains what information is exposed to each role in the system (Moderator, Participant, Engagement Assessment).

## 1. What the Moderator Sees

**File/Function Reference:** `core/prompt_renderer.py:render_turn_message()`

The moderator sees the full systemic state of the session.
- **System Prompt:** Static text from `prompts/01_MODERATOR_SYSTEM_PROMPT.md` defining their role, available actions, and constraints.
- **User Prompt:** Rendered from `prompts/02_USER_MESSAGE_TEMPLATE.md`.
- **Injected Data:**
  - Full `SessionState` JSON (including all participant profiles, previous logs, and current guide phase).
  - Current `TriggerEvent` JSON (who just spoke, what they said).
  - Private tracking metrics: `consensus_risk`, `unresolved_tensions`, `silent_participants`.
  - Conditional Special Cases: If consensus risk > 0.65, or someone is silent, additional text blocks are injected.

**What the Moderator DOES NOT See:**
- The private agent payloads (the raw simulation configs) are mostly abstracted away, but they do see `profile_summary`.

## 2. What the Participant Sees

**File/Function Reference:** `core/participant_agent.py:build_participant_system_prompt()` and `_format_recent_transcript()`

Participants see only what a human would see in a real room, plus their own internal identity.
- **System Prompt:** Constructed dynamically from their JSON payload. Includes demographics, dietary habits, and behavioral rules (e.g., "Do not speak in a polished essay style").
- **User Prompt:** A formatted window of the recent transcript (the last 6 entries).
- **Injected Hook:** If emergent assessment generated a specific motivation (`hook`), it is prepended to the user prompt.

**What the Participant DOES NOT See:**
- The full `SessionState`.
- The `discussion_guide` (they only hear the moderator's spoken questions).
- The full profiles or secret instructions of other participants.
- The moderator's private logic or action vocabulary.

## 3. What the Engagement Assessment Sees

**File/Function Reference:** `core/participant_agent.py:assess_engagement()`

The engagement assessment makes a rapid decision on whether the participant should speak.
- **System Prompt:** A very condensed version of the participant's identity (Name, Age, Gender, Location, Diet).
- **User Prompt:** The recent transcript window (last 6 entries) + a short history of the participant's *own* past utterances in the session.

**What the Engagement Assessment DOES NOT See:**
- The full, deep psychological profile used for actual text generation.
- The moderator's state.

## 4. Empirical Examples from Macho Meals

In the successful `macho_meals_emergent_full_run_02` (as found in `docs/testing/macho_meals_emergent_run_validation/live_run_outputs/rendered_prompts/`):

- **Moderator Turn Prompt:** The file reveals a massive JSON injection of `SessionState`, where the moderator sees the guide moving from `intro` to `exploration`, and tracks that David spoke 12 times while Will spoke 8 times.
- **Participant Response Prompt (e.g., Amir):** Only contains Amir's demographic traits (e.g., "34, Male, Halal diet"), the rule "NO ERES UN ASISTENTE DE IA", and the text of the last 6 lines of conversation.
- **Engagement Assessment Prompt:** Asked explicitly to return a JSON object with `wants_to_speak` and `intent`.

## 5. Code vs Model Boundary Summary

- **Deterministic Code:** The assembly of prompts, the parsing of templates, injecting variables, trimming the recent transcript to 6 entries.
- **Model-Decided:** None. Rendering is purely deterministic.

*Disclaimer: Prompt captures only exist when prompt audit/interception is explicitly enabled during the run. The model's internal processing of these prompts is opaque.*
