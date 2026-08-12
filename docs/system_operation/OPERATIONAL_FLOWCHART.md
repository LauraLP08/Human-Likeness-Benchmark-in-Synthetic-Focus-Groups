# Operational Flowchart

## A. Executive Summary

When a focus group session is run, the system initializes by loading a session configuration, the `DiscussionGuideSection` definitions, and the participant `agent_payload` JSONs. It constructs a `SessionState` to track all variables.

The session starts with the moderator reading the `SessionState` and generating an opening message. From there, the system enters the "Emergent Loop." In this loop, instead of calling on people sequentially, the system asks *every* participant simultaneously to assess their engagement (`wants_to_speak`, `urgency`). The participant with the highest urgency score (modified by code-enforced bonuses) gets to speak next. After the participant speaks, the moderator model is called again to decide whether to intervene (e.g., probe, transition sections) or `stay_silent`. 

As the session progresses, a transcript grows linearly. Outputs are strictly saved to canonical disk paths (`output/session_logs/{session_id}/`). The session ends only when the moderator transitions into and completes the final closing section of the discussion guide.

## B. High-Level Flowcharts

The detailed sequence diagrams are located in `docs/system_operation/diagrams/`:
- [Full Session Lifecycle](diagrams/full_session_lifecycle.mmd)
- [Emergent Mode Loop](diagrams/emergent_mode_loop.mmd)
- [Moderator Call Lifecycle](diagrams/moderator_call_lifecycle.mmd)
- [Participant Response Lifecycle](diagrams/participant_response_lifecycle.mmd)
- [Engagement Assessment Lifecycle](diagrams/engagement_assessment_lifecycle.mmd)
- [Output Persistence Lifecycle](diagrams/output_persistence_lifecycle.mmd)
- [Prompt Rendering & Visibility](diagrams/prompt_rendering_visibility.mmd)

## C. Step-by-Step Operational Trace

1. **Session Config is Resolved:** `orchestrator.py:_build_state_from_config()`. Deterministic Code.
2. **Guide is Loaded:** YAML definitions become `DiscussionGuideSection` objects. Deterministic Code.
3. **Agents are Loaded:** `participant_agent.py:load_agent_from_json()`. Deterministic Code.
4. **SessionState Initialized:** Saved to `session_state_initial.json`. Deterministic Code.
5. **Opening Moderator Prompt Rendered:** `prompt_renderer.py:render_opening_message()`. Deterministic Code.
6. **Opening Moderator API Call:** `moderator_brain.py:call_moderator()`. Model-decided.
7. **Opening Response Applied:** State updated. Deterministic Code.
8. **Emergent Step Begins:** `orchestrator.py:run_conversation_step()`. Deterministic Code.
9. **Engagement Assessment:** `participant_agent.py:assess_engagement()`. Model-decided (JSON response).
10. **Speaker Selection:** `orchestrator.py:run_conversation_step()`. Mixed (Model scores urgency, Code applies bonuses and thresholds).
11. **Participant Prompt Rendered:** `participant_agent.py:build_participant_system_prompt()`. Deterministic Code.
12. **Participant Response:** `participant_agent.py:call_participant()`. Model-decided.
13. **Moderator Prompt Rendered:** `prompt_renderer.py:render_turn_message()`. Deterministic Code.
14. **Moderator Decision Generated:** `moderator_brain.py:call_moderator()`. Model-decided.
15. **Moderator Response Validated:** `moderator_brain.py:_try_parse()`. Deterministic Code.
16. **State Updated:** `session_state.py:apply_moderator_response()`. Deterministic Code.
17. **Outputs Saved:** `orchestrator.py:save_transcript()`. Deterministic Code.
18. **Loop Continues:** Until guide completes.

## D. Code-vs-Model Responsibility Matrix

| System Behavior | Type | Responsible File/Function | Input Used | Output Produced | Failure Mode | Audit Artifact |
|-----------------|------|---------------------------|------------|-----------------|--------------|----------------|
| Guide Loading | Code | `orchestrator.py:_build_state_from_config()` | Config Dict | `SessionState.discussion_guide` | Missing keys raise exceptions | `session_state_initial.json` |
| Agent Loading | Code | `participant_agent.py:load_agent_from_json()` | Agent JSON | `ParticipantState` | JSON decode error | `session_state_initial.json` |
| Moderator Opening | Model | `moderator_brain.py:call_moderator()` | Session meta | `ModeratorAPIResponse` | API timeout | `moderator_log.json` |
| Engagement Assessment | Model | `participant_agent.py:assess_engagement()` | Recent transcript | `wants_to_speak`, `urgency` | Returns default `stay_silent` | `api_calls.jsonl` |
| Speaker Selection | Mixed | `orchestrator.py:run_conversation_step()` | Assessments | Selected `participant_id` | Nobody volunteers (Silence fallback) | Transcript Speaker |
| Participant Response | Model | `participant_agent.py:call_participant()` | Recent transcript, hook | Text utterance | API timeout | `transcript.json` |
| Moderator Action | Model | `moderator_brain.py:call_moderator()` | `SessionState`, `TriggerEvent` | `ModeratorAPIResponse` JSON | Schema validation error | `moderator_log.json` |
| Section Transition | Mixed | `session_state.py:apply_moderator_response()` | `ModeratorAction.TRANSITION_SECTION` | Advances index in state | Index out of bounds | `state_turn_*.json` |
| Output Saving | Code | `orchestrator.py:save_transcript()` | `SessionState` | File writes | Disk I/O error | `transcript.json` |
| Fallback Logic | Mixed | `moderator_brain.py:call_moderator()` | Validation error | `ModeratorAPIResponse` | Code substitutes safe fallback | `api_calls.jsonl` |

## E. JSON/YAML Rendering Map

- **Guide YAML:** Parsed into `DiscussionGuideSection`. Section purposes and probes are visible to the Moderator. Participants do not see the guide.
- **Agent JSON:** Transformed into `profile_summary` (visible to all models). The deep behavior attributes (`food_consumption`, etc.) are only visible to the Participant's generation prompt.
- **Session Config:** Sets temperature and participation mode.
- **SessionState:** Sent as a massive JSON block to the Moderator on every turn. Participants do not see it.

## F. Prompt Rendering Inventory

| Prompt | Source File/Function | Injections | Model Used | Expected Output | Audit Location |
|--------|----------------------|------------|------------|-----------------|----------------|
| Moderator System | `prompts/01_MODERATOR_SYSTEM_PROMPT.md` | None | Sonnet | N/A | `rendered_prompts/moderator/` |
| Moderator Turn | `prompts/02_USER_MESSAGE_TEMPLATE.md` | `SessionState`, `TriggerEvent`, `Phase Modifiers` | Sonnet | `ModeratorAPIResponse` JSON | `rendered_prompts/moderator/` |
| Participant System | `participant_agent.py:build_participant_system_prompt()` | Identity, Diet, Behavior | Default / Config | N/A | `rendered_prompts/participant/` |
| Participant User | `participant_agent.py:_format_recent_transcript()` | Recent 6 transcript lines, hook | Default / Config | Text Utterance | `rendered_prompts/participant/` |
| Engagement Assessment | `participant_agent.py:assess_engagement()` | Basic demographics, own turns, recent transcript | Default / Config | Engagement JSON | `api_calls.jsonl` (tokens only unless audited) |

## G. Empirical Examples (Macho Meals Run)

From `docs/testing/macho_meals_emergent_run_validation/live_run_outputs/`:

- **Moderator Turn Prompt Example:** Found in `rendered_prompts/moderator/turn_4_prompt.txt`. Contains massive `"{SESSION_STATE}"` JSON injection tracking the exact progress of the current question. Deterministic Code rendered the JSON; Model parsed it to return `{ "action": "stay_silent" }`.
- **Participant System Prompt Example:** Found in `rendered_prompts/participant/Amir_turn_5.txt`. Contains: `"You are Amir, a 34-year-old Male participant in a focus group... Your diet: Halal."` Code generated the identity block; Model decided the output text.
- **Engagement Assessment Prompt:** Asked the model to return `{"wants_to_speak": true/false}`. Model generated `{ "wants_to_speak": true, "urgency": 0.8, "intent": "affirm_and_elaborate" }`.

## H. Emergent Participation Logic

Detailed thoroughly in [EMERGENT_MODE_MECHANICS.md](EMERGENT_MODE_MECHANICS.md). The key logic is:
1. `assess_engagement()` returns a score for everyone.
2. Code applies bonuses (e.g. `PEER_ADDRESS_BONUS`).
3. Code filters out scores below `URGENCY_THRESHOLD`.
4. Code overrides the speaker if they hit `MAX_CONSECUTIVE_PARTICIPANT_TURNS`.

## I. Moderator Decision Logic

- **Input:** Full `SessionState` + `TriggerEvent`.
- **Vocabulary:** Enum `ModeratorAction` (`observe`, `direct_probe`, `transition_section`, etc).
- **Validation:** Pydantic (`ModeratorAPIResponse`). Errors trigger an automatic LLM retry. Repeated failures trigger a deterministic code fallback (substitutes a dummy `observe` action).
- **State Updates:** If the model outputs `consensus_risk: 0.8`, the code directly mutates `SessionState.group_state.consensus_risk = 0.8`.

## J. Output File Map

Detailed thoroughly in [OUTPUT_AND_AUDIT_GUIDE.md](OUTPUT_AND_AUDIT_GUIDE.md). **Canonical files in `output/session_logs/{session_id}/` are the absolute source of truth.** Testing copies and reports must be verified against them.

## K. Verbosity Map

Detailed thoroughly in [VERBOSITY_CONTROL_MAP.md](VERBOSITY_CONTROL_MAP.md). Verbosity stems from `max_tokens` settings in code, instruction strings in `participant_agent.py`, and emergent threshold constants in `core/config.py`. **No verbosity settings have been changed yet.**

## L. Known Operational Caveats

- **Chain of Thought:** Private LLM reasoning is not captured.
- **Contamination:** Reused session IDs will corrupt `state_turn_*.json` outputs.
- **Architectural Mismatches:** `ARCHITECTURE.md` claims some behaviors are model-driven that are actually heavily guarded by deterministic code thresholds (see `CODE_ARCHITECTURE_CONSISTENCY_AUDIT.md`).
- **Transcript Truth:** Final `state_turn_*.json` is the sole proof of guide completion.
