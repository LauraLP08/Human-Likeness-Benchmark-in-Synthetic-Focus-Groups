# Session Run Sequence

This document provides a deeply detailed chronological trace of exactly what happens from the moment a session is launched until it ends.

## Phase 1: Initialization

**1. Session Config is Resolved:**
- **Function:** `orchestrator.py:_build_state_from_config()`
- **Action:** The system parses the session config dictionary.
- **Code/Model:** Deterministic Code.

**2. Guide is Loaded:**
- **Function:** `orchestrator.py:_build_state_from_config()`
- **Action:** The `DiscussionGuideSection` list is populated.

**3. Agents are Loaded:**
- **Function:** `participant_agent.py:load_agent_from_json()`
- **Action:** Participant JSON files are parsed, and `ParticipantState` objects are created. Demographics are flattened into a `profile_summary`.

**4. SessionState is Initialized:**
- **Function:** `orchestrator.py:__init__()`
- **Action:** The `SessionState` object is instantiated and saved to `output/session_logs/{session_id}/session_state_initial.json`.

## Phase 2: Session Opening

**5. Opening Moderator Prompt Rendered:**
- **Function:** `prompt_renderer.py:render_opening_message()`
- **Action:** The guide and initial parameters are formatted into `03_SESSION_OPENING_PROMPT.md`.

**6. Opening Moderator API Call:**
- **Function:** `moderator_brain.py:call_moderator(is_opening_turn=True)`
- **Action:** The API is called.
- **Code/Model:** Model-decided (Moderator response).

**7. Opening Response Parsed and Applied:**
- **Function:** `session_state.py:apply_moderator_response()`
- **Action:** The moderator's utterance is added to the transcript and `state_turn_0.json` is saved.

## Phase 3: Emergent Loop (Repeats until Guide Completes)

**8. Emergent Step Begins:**
- **Function:** `orchestrator.py:run_conversation_step()`

**9. Engagement Assessment Calls Sent:**
- **Function:** `participant_agent.py:assess_engagement()`
- **Action:** Every participant receives the recent transcript. The model evaluates whether they want to speak.
- **Code/Model:** Model-decided (`wants_to_speak`, `urgency`, `hook`).

**10. Speaker is Selected:**
- **Function:** `orchestrator.py:run_conversation_step()`
- **Action:** Code applies contextual bonuses (e.g., peer address), filters by `URGENCY_THRESHOLD`, and sorts. The top participant is selected. If nobody passes, silence fallback triggers.
- **Code/Model:** Mixed (Model scores, code applies rules).

**11. Participant Response Prompt Rendered:**
- **Function:** `participant_agent.py:build_participant_system_prompt()`
- **Action:** Full persona and recent transcript are formatted. The `hook` is injected.

**12. Participant Response Generated:**
- **Function:** `participant_agent.py:call_participant()`
- **Action:** Model generates the utterance. It is added to the transcript.
- **Code/Model:** Model-decided.

**13. Moderator Prompt Rendered:**
- **Function:** `prompt_renderer.py:render_turn_message()`
- **Action:** `TriggerEvent` (the participant's utterance) and `SessionState` are injected.

**14. Moderator Decision Generated:**
- **Function:** `moderator_brain.py:call_moderator()`
- **Action:** Model decides whether to `stay_silent`, `direct_probe`, `transition_section`, etc.
- **Code/Model:** Model-decided.

**15. Moderator Response Parsed/Validated:**
- **Function:** `moderator_brain.py:_try_parse()`
- **Action:** Pydantic validates the JSON. If it fails, an automated retry occurs. If both fail, code substitutes a safe fallback.
- **Code/Model:** Deterministic Code (validation).

**16. State is Updated:**
- **Function:** `session_state.py:apply_moderator_response()`
- **Action:** The moderator's action mutates the state (e.g., advancing the `current_question_index`).

**17. Outputs are Saved:**
- **Function:** `orchestrator.py:save_transcript()`, `save_moderator_log()`, `_save_state_snapshot()`
- **Action:** Canonical files on disk are updated.

**18. Loop Continues:**
- **Action:** Returns to Step 8 until the final section of the `discussion_guide` is marked `completed: true`.
