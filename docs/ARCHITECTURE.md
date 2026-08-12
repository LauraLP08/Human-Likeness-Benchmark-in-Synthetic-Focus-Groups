# System Architecture — AI Focus Group Moderator
## Technical Audit Document

**Project:** Synthetic qualitative focus group simulation  
**Language:** Python 3.14  
**External dependencies:** `anthropic >= 0.40`, `pydantic >= 2.0`  
**Last updated:** 2026-06-27  
**Status:** Active development. Remaining implementation gaps are documented explicitly in Section 12. Several gaps from the previous version have been closed — see change log in each section.

---

## Table of Contents

1. System Purpose
2. Architecture Overview
3. File Structure
4. Data Model — Complete Field Reference
5. Prompt Architecture — Four-File System
6. Control Flow — Turn-by-Turn
7. API Configuration
8. Agent Loading from External JSON
9. State Mutation Rules
10. Prompt Injection Logic
11. Output Files and Logging
12. Known Gaps Between Design and Implementation
13. Audit Trail Completeness
14. Design Decisions and Rationale
15. Research Quality Risks
16. Appendix A — Pydantic Validation Chain
17. Appendix B — Agent JSON Schema

---

## 1. System Purpose

This system simulates a focus group discussion using multiple AI agents. There are two distinct agent roles:

- **The Moderator** — a single instance of `claude-sonnet-4-6` (configurable via `session_meta.moderator_model`) operating with a fixed persona and action vocabulary. Its goal is to generate rich qualitative data by probing participant responses, managing group dynamics, and following a structured discussion guide.
- **Participants** — one API call per participant per turn, using persona-based system prompts. They can be defined inline in the session config or loaded from external platform JSON files with demographic, behavioural, and psychological data.

The system supports two participation modes:

- **Orchestrated mode** — the orchestrator controls turn order, cycling through participants by ascending `turn_count`. Every participant speaks once per round.
- **Emergent mode** — participants self-select based on an urgency assessment. Each step calls `assess_engagement()` for all participants, then selects the participant with the highest urgency above a threshold (or falls back to moderator intervention if nobody wants to speak).

The system is designed for dissertation research in qualitative social science. It is **not** a production system and has not been used with real human participants.

---

## 2. Architecture Overview

### Orchestrated Mode (`run_full_turn`)

```
[session_config.json]
        |
        v
[FocusGroupOrchestrator]  ← orchestrator.py
        |
        |── initialises ──> [SessionState]  ← session_state.py (Pydantic)
        |
        |── run_opening()
        |       |
        |       └──> call_moderator(is_opening_turn=True)  ← moderator_brain.py
        |               ├── load_system_prompt()            ← prompt_renderer.py
        |               ├── _state_to_session_config(state) ← moderator_brain.py
        |               ├── render_opening_message()        ← prompt_renderer.py
        |               ├── Anthropic API (claude-sonnet-4-20250514)
        |               ├── ModeratorAPIResponse (Pydantic validated)
        |               └── apply_moderator_response()      ← session_state.py
        |                       + capture initial_session_plan from raw JSON
        |
        |── run_full_turn()  [loop per participant, ordered by turn_count ASC]
        |       |
        |       └── for each participant:
        |               |
        |               |── _recent_transcript() → last 6 entries
        |               |
        |               |── run_participant_turn(pid, recent_transcript, hook="")
        |               |       └──> call_participant()  ← participant_agent.py
        |               |               ├── build_participant_system_prompt()
        |               |               ├── _format_recent_transcript()
        |               |               ├── Anthropic API (model from agent_payload)
        |               |               └── plain text response
        |               |
        |               |── record_participant_utterance()  ← session_state.py
        |               |
        |               └──> run_moderator_turn()
        |                       └──> call_moderator()  ← moderator_brain.py
        |                               ├── render_turn_message()  ← prompt_renderer.py
        |                               │       (SESSION_STATE excludes agent_payload)
        |                               ├── Anthropic API
        |                               └── apply_moderator_response()  ← session_state.py
        |                                       + feedback loop (typed fields → state)
        |
        └── save_transcript() / save_moderator_log()
```

### Emergent Mode (`run_conversation_step`)

```
[FocusGroupOrchestrator.run_conversation_step()]
        |
        |── 1. For each participant:
        |       _get_participant_own_turns(pid) → list[str] (≤15 most recent own utterances)
        |       assess_engagement(participant, session_meta, recent,
        |                         participant_own_turns=own_turns)  ← participant_agent.py
        |           (max_tokens=250; explicit JSON instruction; logs WARNING on failure)
        |       └── store results in group_state.last_engagement_round
        |
        |── 2. Check moderator direct-address override:
        |       _resolve_moderator_targets(last_mod.target)
        |       Single target  → hard floor-handoff (bypass auction)
        |       Multi-target   → bonus each (+0.15), run auction (dormant under current prompting)
        |       No target/"group" → normal auction
        |
        |── 3. Apply urgency bonuses (peer +0.15, consensus-challenge +0.10, cap 0.30)
        |       Select participant with urgency >= URGENCY_THRESHOLD (0.55)
        |       (sorted by -urgency, then turn_count ASC)
        |
        |── 4. If participant selected:
        |       ├── run_participant_turn(pid, recent_transcript, hook=assessment.hook)
        |       ├── _build_trigger_event(pid, response_text)
        |       └── run_moderator_turn(trigger)
        |           record_participant_utterance() called inside run_moderator_turn
        |           └── returns "participant_led" or "moderator_direct_address"
        |
        |── 5. If nobody above threshold AND consecutive_silent_turns >= 2:
        |       Lower bar to urgency > 0.2; pick highest
        |       └── same flow as step 4
        |
        └── 6. If still nobody:
                Fire TriggerEvent(type=SILENCE_DETECTED)
                └── run_moderator_turn() only
                    └── returns "moderator_intervention"
```

**Conversation histories** — Only per-participant conversation histories are maintained:

| History | Scope | Content |
|---------|-------|---------|
| `orchestrator.participant_histories[pid]` | Per-participant | That participant's turns only; the participant is the assistant |

---

## 3. File Structure

```
project/
├── core/
│   ├── session_state.py       Data models and all state mutation functions
│   ├── prompt_renderer.py     Reads prompt files; renders all templates
│   ├── moderator_brain.py     Moderator API call + JSON validation + retry
│   ├── participant_agent.py   Participant API calls + persona prompt building
│   │                          + assess_engagement() for emergent mode
│   ├── orchestrator.py        Session loop; owns all history lists;
│   │                          run_full_turn() + run_conversation_step()
│   └── __init__.py
├── prompts/
│   ├── 00_README.md           Prompt architecture documentation
│   ├── 01_MODERATOR_SYSTEM_PROMPT.md   Permanent moderator identity (system param)
│   ├── 02_USER_MESSAGE_TEMPLATE.md     Per-turn user message template
│   ├── 03_SESSION_OPENING_PROMPT.md    First-turn only: session init + welcome
│   └── 04_PHASE_MODIFIERS_AND_SPECIAL_CASES.md  Condition-triggered injections
├── examples/
│   └── sample_session_config.json
├── output/
│   └── session_logs/{session_id}/      Created at runtime
└── run_session.py             CLI entrypoint (--mode orchestrated|emergent)
```

---

## 4. Data Model — Complete Field Reference

All models are in `core/session_state.py` and use Pydantic v2. No model is defined or modified elsewhere.

### 4.1 Enumerations

| Enum | Values | Used in |
|------|--------|---------|
| `SectionPhase` | `intro`, `context`, `main_topic`, `stimulus`, `closing` | `SessionMeta`, `DiscussionGuideSection`, phase modifier selection |
| `ProbingDepthCeiling` | `light`, `medium`, `deep` | `DiscussionGuideSection` |
| `ModeratorAction` | `ask_initial_to_group`, `direct_probe`, `redirect_to_group`, `invite_dissent`, `synthesize_and_challenge`, `reactivate_silent`, `reflect_contradiction`, `introduce_stimulus`, `section_transition`, `stay_silent` | `ModeratorDecisionResponse`, `ModeratorLogEntry` |
| `ProbeType` | `specificity`, `emotional_depth`, `behavioural_grounding`, `contradiction_surface`, `trade_off_exploration`, `social_influence`, `meaning_clarification` | `ModeratorDecisionResponse` (required when action = `direct_probe`) |
| `FollowUpIntensity` | `light`, `medium`, `deep` | `ModeratorDecisionResponse` (valid only for probe actions; silently stripped for others — see Section 4.7) |
| `DominantSignal` | `response_needs_probing`, `participation_imbalance`, `consensus_risk`, `contradiction_pending`, `section_complete`, `emotional_register`, `guide_question_pending`, `silence_detected`, `conflict_detected` | `ModeratorLogEntry` |
| `TriggerEventType` | `participant_response`, `session_start`, `stimulus_presented`, `silence_detected` | `TriggerEvent` — `silence_detected` now used in emergent mode step 6 |
| `ResponseQuality` | `rich`, `adequate`, `shallow`, `incomplete` | `ParticipantState.last_response_quality` (set via feedback loop — §12.1 FIXED) |
| `EngagementSignal` | `active`, `moderate`, `passive`, `withdrawn` | `ParticipantState.engagement_signal` (set via feedback loop — §12.1 FIXED) |

### 4.2 SessionMeta

| Field | Type | Default | Source | Notes |
|-------|------|---------|--------|-------|
| `id` | `str` | required | config `session_id` | Used as log directory name |
| `research_objective` | `str` | required | config | Sent to moderator |
| `topic_domain` | `str` | required | config | Sent to moderator |
| `participant_collective_identity` | `str` | required | config | Sent to moderator. **No longer injected into participant system prompts** (line removed). |
| `moderator_knowledge_brief` | `str` | required | config | Sent to moderator; explicitly excludes researcher hypotheses |
| `researcher_notes` | `str` | `""` | config optional | Sent to moderator |
| `temperature` | `float` | `1.0` | config optional | Applied to ALL participant API calls AND to `assess_engagement()` calls. Does NOT apply to moderator (hardcoded `1.0` in `moderator_brain._call_api`) |
| `participation_mode` | `str` | `"orchestrated"` | config optional | `"orchestrated"` or `"emergent"`. Can be overridden by `--mode` CLI flag. Not validated as an enum — any string is accepted. |
| `initial_session_plan` | `dict \| None` | `None` | runtime | Populated from the model's opening response JSON; extracted by `run_opening()` after `apply_moderator_response`. Stored in state but has no downstream effect on moderation decisions. |
| `current_section_index` | `int` | `0` | runtime | Index into `discussion_guide` |
| `section_phase` | `SectionPhase` | first section's phase | runtime | Set from guide on init; updated on section transition |
| `current_question_index` | `int` | `0` | runtime | **Never incremented — see Section 12** |
| `total_turns` | `int` | `0` | runtime | Incremented by `apply_moderator_response` for every moderator call (including `stay_silent`) |
| `session_started_at` | `datetime` | `utcnow()` | runtime | |
| `inject_participant_intro` | `bool` | `False` | config optional | When true, include each intro-eligible agent's `opening_intro.text` in their system prompt |
| `run_label` | `str \| None` | `None` | config optional | Recording-only label for organizing replicated runs (e.g. a replication group tag). No effect on generation — the Anthropic API has no seed parameter. Renamed from `generation_seed` 2026-06-29 (the old name falsely implied a determinism control). |
| `moderator_model` | `str` | `"claude-sonnet-4-6"` | config optional | Model for all moderator API calls. Overridable per session config. |

### 4.3 ParticipantState

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `id` | `str` | required | e.g. `P1`, or `agent_id` from JSON |
| `name` | `str` | required | |
| `profile_summary` | `str` | `""` | Plain-text profile for inline participants; ignored if `agent_payload` present |
| `agent_payload` | `dict` | `{}` | Full raw agent JSON. **Excluded from moderator-facing state JSON (`to_prompt_json()`). Still present in Python object and state snapshots on disk.** |
| `turn_count` | `int` | `0` | Incremented by `apply_moderator_response` when trigger has `speaker_id` |
| `topics_covered` | `list[str]` | `[]` | Extended from `decision.new_topics_covered` via feedback loop (§12.1 FIXED) |
| `last_response_quality` | `ResponseQuality \| None` | `None` | Set from `decision.participant_response_quality` via feedback loop (§12.1 FIXED) |
| `engagement_signal` | `EngagementSignal` | `MODERATE` | Set from `decision.participant_engagement_signal` via feedback loop (§12.1 FIXED) |
| `emotional_signal` | `str \| None` | `None` | Set by the feedback loop in `apply_moderator_response()` from the moderator's `emotional_signals` list. If the moderator includes an `EmotionalSignalItem` for this participant, `emotional_signal` is set to `item.signal`. Multiple participants can have their signal updated in a single turn. Overwrites any previous value. Triggers `emotional_register_elevated` injection on subsequent turns for this participant. |
| `dominant_tendency` | `bool` | `False` | **Never updated** |
| `follow_up_count_current_question` | `int` | `0` | Set by `apply_moderator_response` to the trigger's `follow_up_count_this_question`. **Never increments above 0 in practice — see Section 12** |

### 4.4 GroupState

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `participation_balance` | `dict[str, float]` | `{}` | Recomputed by `validate_participation_balance` model validator on every save; sum = 1.0 |
| `silent_participants` | `list[str]` | `[]` | PIDs where `turn_count / total < 0.15`; updated by `apply_moderator_response`; not tracked in intro phase |
| `consensus_risk` | `float [0,1]` | `0.0` | Set by the feedback loop from `decision.consensus_risk_assessment` (a typed `float | None` field). Updated on every turn where the moderator returns a non-null value. Rounded to 3 decimal places by the `validate_consensus_risk` field validator when state is re-validated. |
| `dominant_voices` | `list[str]` | `[]` | PIDs with >50% of section turns; updated by `apply_moderator_response` |
| `emergent_themes` | `list[str]` | `[]` | Extended from `decision.new_emergent_themes` via feedback loop (§12.1 FIXED) |
| `unresolved_tensions` | `list[UnresolvedTension]` | `[]` | **Updated by the feedback loop** (creation) and by `apply_moderator_response` step 5a (resolution). New entries created from the moderator's `new_contradictions` list (`ContradictionItem` objects). Resolved when `surface_count >= 2` after repeated `reflect_contradiction` targeting the same participant. See field definition below. |
| `group_has_agreed_easily_on` | `list[str]` | `[]` | Extended from `decision.new_easy_agreements` via feedback loop (§12.1 FIXED) |
| `section_turn_counts` | `dict[str, int]` | `{}` | Counts per participant within CURRENT section; reset to `{}` on section transition |
| `consecutive_silent_turns` | `int` | `0` | Incremented when moderator chooses `stay_silent`; reset to 0 on any other action |
| `last_speaker_id` | `str \| None` | `None` | Set to participant ID by `record_participant_utterance`; set to `"MODERATOR"` by `apply_moderator_response` for non-silent actions |
| `last_engagement_round` | `list[ParticipantEngagementAssessment]` | `[]` | Updated at the start of each `run_conversation_step()` call. Contains one entry per participant. Only the MOST RECENT round is kept — previous rounds are overwritten. |

**`UnresolvedTension` model** — element type of `unresolved_tensions`:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `participant_id` | `str` | required | Participant ID the tension is associated with |
| `flagged_at_turn` | `int` | required | Turn number when the tension was first added by the feedback loop |
| `description` | `str` | required | `ContradictionItem.description` as supplied by the moderator. No truncation applied. |
| `resolved` | `bool` | `False` | Set to `True` when `surface_count >= 2` via a `reflect_contradiction` action |
| `resolved_at_turn` | `int \| None` | `None` | Turn number when `resolved` was set to `True` |
| `surfaced` | `bool` | `False` | Set to `True` on the first `reflect_contradiction` targeting this participant |
| `surface_count` | `int` | `0` | Incremented each time `reflect_contradiction` targets this participant while `resolved=False` |

### 4.5 ParticipantEngagementAssessment

New model added for emergent mode. Represents a single participant's self-assessed readiness to speak.

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `participant_id` | `str` | required | Matches a key in `state.participants` |
| `wants_to_speak` | `bool` | required | Whether the participant assessed themselves as wanting to contribute |
| `urgency` | `float [0,1]` | required | How strongly they want to speak. Validated by Pydantic (`ge=0.0, le=1.0`). |
| `hook` | `str` | `""` | What in the conversation is prompting them. Empty if `wants_to_speak=False`. Passed to `call_participant()` as a motivating prefix to the user message. |

**On API failure:** `assess_engagement()` emits a `logging.WARNING` via `logging.getLogger(__name__)` (message includes participant ID, exception text, and `getattr(e, 'raw', 'unavailable')`), then returns `ParticipantEngagementAssessment(participant_id=pid, wants_to_speak=False, urgency=0.0, hook="")`. No exception is raised to the caller.

### 4.6 DiscussionGuideSection

| Field | Type | Notes |
|-------|------|-------|
| `section_index` | `int` | 0-based; must match position in list |
| `section_label` | `str` | Human-readable name |
| `section_phase` | `SectionPhase` | Controls which phase modifier is injected |
| `section_purpose` | `str` | Sent to moderator as context |
| `scripted_question` | `str` | The researcher's verbatim question; moderator rewrites into natural language |
| `probing_depth_ceiling` | `ProbingDepthCeiling` | Required field. Instruction in prompt only; not enforced in code. Set by `ui/server.py` from `_PHASE_DEPTH` at session start and at guide save time — the frontend never sends this field. |
| `stimulus` | `StimulusConfig \| None` | Optional indirect probing device |
| `completed` | `bool` | `False` | Set to `True` by `apply_moderator_response` when action = `section_transition` |
| `suggested_probes` | `list[str]` | `[]` | Optional researcher-configured follow-up prompts for this section. Correctly populated from session config by `_build_state_from_config()` — bug fixed, see §12.11. Included in the full state JSON sent to the moderator via `to_prompt_json()` on turns 1 onwards, since `discussion_guide` is not filtered. **Not present in the opening turn prompt**: `_state_to_session_config()` (used only for the opening turn) does not serialise this field. See §8.3. |

### 4.7 TriggerEvent

The trigger event is constructed by the orchestrator and passed to the moderator on each turn. It represents what just happened.

| Field | Value in orchestrated mode | Value in emergent mode |
|-------|---------------------------|------------------------|
| `type` | `participant_response` (always in `run_full_turn`); `session_start` in `run_opening` | `participant_response` when a participant speaks; `silence_detected` when nobody volunteers (step 6) |
| `speaker_id` | Participant ID string | Participant ID string, or `None` for silence trigger |
| `speaker_name` | Participant's name | Participant's name, or `None` for silence trigger |
| `content` | The participant's raw response text | Same, or `"No participant volunteered to speak."` for silence trigger |
| `turn_number` | `total_turns + 1` at time of creation | `total_turns` (not `+1`) for silence trigger; `total_turns + 1` for participant trigger |
| `follow_up_count_this_question` | Always `participant.follow_up_count_current_question` (= 0 in practice) | Same |

**Note on silence trigger:** In step 6 of `run_conversation_step()`, the silence trigger uses `turn_number=self.state.session_meta.total_turns` (not `+1`) because no participant has spoken. This is a minor inconsistency with participant triggers.

### 4.8 ModeratorDecisionResponse — Fields and Validators

All fields the model must return:

| Field | Type | Notes |
|-------|------|-------|
| `situation_assessment` | `str` | 2-4 sentence honest summary of what the moderator observed this turn |
| `dominant_signal` | `DominantSignal` | Single most important signal driving the action |
| `action` | `ModeratorAction` | The typed action chosen |
| `target` | `str` | Participant ID or `"group"` |
| `justification` | `str` | Audit trail of decision rationale |
| `probe_type` | `ProbeType \| None` | Required for `direct_probe`; must be `null` for all other actions |
| `follow_up_intensity` | `FollowUpIntensity \| None` | Valid only for `direct_probe`, `reflect_contradiction`, `synthesize_and_challenge`. **Silently stripped to `null` for all other actions** |
| `group_dynamic_flags` | `list[str]` | Free-text audit field. Logged verbatim in `moderator_log.json`. **Not parsed for state updates** — state is updated from the typed fields below. |
| `consensus_risk_assessment` | `float \| None` | Moderator's assessment of consensus risk this turn (0.0–1.0). Required on every turn; null is accepted by Pydantic but the system prompt instructs the model to always provide a value. Written directly to `group_state.consensus_risk` by the feedback loop. |
| `emotional_signals` | `list[EmotionalSignalItem]` | Zero or more emotional signals detected this turn. Each item has `participant_id` and `signal` (participant's own words). Written to `participant.emotional_signal` for each participant listed. |
| `new_contradictions` | `list[ContradictionItem]` | Zero or more newly detected contradictions. Each item has `participant_id` and `description`. Creates a new `UnresolvedTension` if none already exists for that participant. |
| `queued_next_action` | `QueuedNextActionResponse \| None` | Planned next action; stored in log but not enforced |

**Supporting models for the new typed fields:**

`ContradictionItem`:
| Field | Type | Description |
|-------|------|-------------|
| `participant_id` | `str` | Exact participant ID as it appears in session state (e.g. `"P1"`) |
| `description` | `str` | Brief description of the contradiction using the participant's own words |

`EmotionalSignalItem`:
| Field | Type | Description |
|-------|------|-------------|
| `participant_id` | `str` | Exact participant ID as it appears in session state (e.g. `"P1"`) |
| `signal` | `str` | Description of the emotional signal using the participant's own words, not the moderator's interpretation |

**Pre-validation normalisation (`_normalize_decision` in `moderator_brain.py`):**

Before `model_validate()` is called, the raw dict is normalised:
- `"null"`, `"none"`, `"n/a"`, and `""` string values on `probe_type`, `follow_up_intensity`, and `queued_next_action` are coerced to JSON `null`.
- `probe_type` is forced to `null` for every action other than `direct_probe`. This upstream coercion replaces the former `validate_probe_type_consistency` validator (see §12.15).
- `follow_up_intensity` is forced to `null` for every action outside `{direct_probe, reflect_contradiction, synthesize_and_challenge}`, mirroring what `validate_follow_up_intensity_consistency` already does inside Pydantic.

**Validators on `ModeratorDecisionResponse`:**

1. ~~`validate_probe_type_consistency`~~ — **Removed.** Replaced by upstream normalisation in `_normalize_decision()`. See §12.15.
2. `validate_follow_up_intensity_consistency`: For non-probe actions, silently sets `follow_up_intensity = None` rather than raising. **This is now redundant for the common case** (normalisation already set it to `null`), but retained as a belt-and-suspenders guard for edge cases.

**Note on `probe_type` for `direct_probe`:** The normalization does NOT set `probe_type` to a default for `direct_probe` actions. If the model returns `direct_probe` without a `probe_type`, Pydantic will accept `null` (since the field has `default=None`). This means a missing `probe_type` on `direct_probe` passes validation silently — it no longer triggers a retry. See §12.15 for the full rationale.

### 4.9 ModeratorAPIResponse — Validators

**`utterance_strip` (field validator):** Strips leading/trailing whitespace from the utterance string.

**`validate_utterance_by_action` (model validator):** If action = `stay_silent`, forces `utterance = ""` regardless of what the model returned. For all other actions, rejects an empty utterance (raises `ValueError` → triggers retry).

**`validation_fallback: bool = False`** — Internal flag set by `call_moderator` when the system fallback response was substituted after two consecutive validation failures. Not part of the API response payload; set programmatically in Python before returning. `apply_moderator_response` reads this field and copies it to `ModeratorLogEntry.validation_fallback` so fallback turns are identifiable in `moderator_log.json`.

**Validator execution order:** Field validators run first (strip), then model validators. Pydantic v2 validates nested models before the parent model validator, so `ModeratorDecisionResponse` is fully validated (probe_type, follow_up_intensity) before `validate_utterance_by_action` runs.

### 4.10 ModeratorLogEntry

Persisted record of every moderator decision, including silent turns.

| Field | Type | Notes |
|-------|------|-------|
| `turn` | `int` | Turn number from trigger event |
| `timestamp` | `datetime` | `datetime.utcnow()` at time of appending to log |
| `trigger` | `DominantSignal` | Copied from `decision.dominant_signal` |
| `situation_assessment` | `str` | Full text; may be compressed to empty string by `to_prompt_json()` |
| `action` | `ModeratorAction` | |
| `target` | `str` | |
| `probe_type` | `ProbeType \\| None` | |
| `follow_up_intensity` | `FollowUpIntensity \\| None` | Will always be null for non-probe actions after validator correction |
| `brief_justification` | `str \\| None` | Short rationale for the intervention. |
| `justification` | `str` | May be compressed; always preserved in on-disk snapshots |
| `group_dynamic_flags` | `list[str]` | Raw free-text strings from the moderator; logged verbatim as an audit trail. No longer parsed for state updates. |
| `queued_next_action` | `QueuedNextAction \| None` | Stored but not enforced |
| `utterance` | `str` | Empty string for `stay_silent` |
| `compressed` | `bool` | Always `False` in the live model; set to `True` in the temporary dict inside `to_prompt_json()` only |
| `validation_fallback` | `bool` | `True` when this turn's response was a system fallback (both API attempts failed validation). Visible in `moderator_log.json`. Researcher must identify and exclude or annotate these turns in analysis. |
| `selection_mode` | `str \\| None` | Indicates how the speaker was selected (e.g. `urgency_self_selection`, `addressed_by_peer`, `moderator_invited`, `silence_fallback`, `orchestrated_round_robin`, `moderator_intervention`). |

---

## 5. Prompt Architecture — Four-File System

All prompt files are read from disk on every call. There is no module-level caching. Edits to prompt files take effect on the next API call without restarting.

### 5.1 File 01 — Moderator System Prompt

**File:** `prompts/01_MODERATOR_SYSTEM_PROMPT.md`  
**Role:** Permanent moderator identity. Passed as the `system` parameter in every moderator API call.  
**Content:**
- Philosophical contract (depth without pressure; challenge without coercion; specificity without suggestion; structure without over-control)
- Complete action vocabulary: 11 typed actions (including `invite_to_speak`)
- Response quality assessment framework (when to probe / when not to)
- Group dynamic rules (participation equity, consensus risk, dominant speaker, section depth)
- Language and register rules
- Knowledge boundary declaration

**Loaded by:** `prompt_renderer.load_system_prompt()`, which strips file-level comment header lines (lines starting with `#`, blank lines, and `---` separators before the first content line).

**Applied to:** Every moderator API call, including the opening turn.

### 5.2 File 02 — Per-Turn User Message Template

**File:** `prompts/02_USER_MESSAGE_TEMPLATE.md`  
**Role:** Dynamic wrapper injected as the user message on every non-opening moderator turn.  
**Placeholders substituted:**

| Placeholder | Value | Source |
|-------------|-------|--------|
| `{SESSION_STATE}` | Session state as JSON | `state.to_prompt_json(compress_before_turn)` — **agent_payload excluded** |
| `{TRIGGER_EVENT}` | Trigger event as JSON | `trigger_event.model_dump_json(indent=2)` |
| `{FOLLOW_UP_COUNT}` | Integer | `trigger_event.follow_up_count_this_question` (always 0 in practice) |
| `{SECTION_PHASE}` | String | `state.session_meta.section_phase.value` |
| `{PHASE_MODIFIER}` | Phase-specific behaviour text | Substituted by `render_turn_message()` from file 04 (§12.3 FIXED) |

**Special-case injections** are appended after template substitution. See Section 10.

### 5.3 File 03 — Session Opening Prompt

**File:** `prompts/03_SESSION_OPENING_PROMPT.md`  
**Role:** Replaces file 02 on the first API call only. Has two jobs: produce an initial session plan and generate the welcome utterance.  
**Placeholder:** `{SESSION_CONFIG}` — substituted with `json.dumps(session_config, indent=2)`.

**The config dict is NOT the original JSON file.** It is reconstructed from `SessionState` by `_state_to_session_config()` in `moderator_brain.py`. Participants appear only as `{id, name, profile_summary}` — no `agent_payload`. See Section 8.3.

**Expected output schema:**
```json
{
  "initial_session_plan": {
    "thematisation_approach": "...",
    "priority_research_areas": [...],
    "participant_notes": [...],
    "known_risk_conditions": [...],
    "directivity_plan": "..."
  },
  "moderator_decision": { ... },
  "utterance": "..."
}
```

`initial_session_plan` is an extra field not in `ModeratorAPIResponse`. Pydantic v2 silently ignores extra fields (default `extra = "ignore"`). However, `run_opening()` now explicitly extracts `initial_session_plan` from the raw assistant message in `conversation_history` after `apply_moderator_response` returns, and writes it to `state.session_meta.initial_session_plan`. **This is a change from the previous version where the plan was discarded entirely.**

**Limitation:** The `initial_session_plan` is stored in `SessionMeta` and therefore appears in state snapshots and in the state JSON sent to the moderator on every subsequent turn. It has no programmatic effect on moderation decisions — there is no code that reads it to influence action selection.

### 5.4 File 04 — Phase Modifiers and Special-Case Injections

**File:** `prompts/04_PHASE_MODIFIERS_AND_SPECIAL_CASES.md`  
**Role:** Named text blocks extracted at runtime by `_parse_phase_modifiers()`.  
**Parsing:** Line-by-line scan for `### ` headers containing backtick-delimited names, followed by triple-backtick fenced blocks.

**Currently parsed blocks (12 total):**

| Block Name | Type | Trigger Condition | Fires in practice? |
|------------|------|-------------------|--------------------|
| `intro` | Phase modifier | `section_phase == intro` | **Yes** — substituted via `{PHASE_MODIFIER}` (§12.3 FIXED) |
| `context` | Phase modifier | `section_phase == context` | **Yes** |
| `main_topic` | Phase modifier | `section_phase == main_topic` | **Yes** |
| `stimulus` | Phase modifier | `section_phase == stimulus` | **Yes** |
| `closing` | Phase modifier | `section_phase == closing` | **Yes** |
| `consensus_risk >= 0.65` | Injection | `group_state.consensus_risk >= 0.65` | **Can fire** — populated from `decision.consensus_risk_assessment` (typed float) |
| `participation_imbalance` | Injection | `len(silent_participants) > 0` AND `phase != intro` | Yes — fires when turn distribution falls below 15% threshold |
| `unresolved_contradiction_due` | Injection | Any `UnresolvedTension` with `resolved=False`, flagged ≥3 turns ago, matching current speaker | **Can fire** — tensions created from `decision.new_contradictions` (typed list) |
| `over_probe_warning` | Injection | `follow_up_count_this_question >= 3` | **No — always 0 in practice (see Section 12)** |
| `emotional_register_elevated` | Injection | `participant.emotional_signal is not None` | **Can fire** — set from `decision.emotional_signals` (typed list) |
| `section_transition_check` | Injection | All participants spoken AND `current_question_index > 0` | **No — index never increments (see Section 12)** |
| `consecutive_silent_turns >= 4` | Injection | `group_state.consecutive_silent_turns >= 4` | Yes — fires in both modes when moderator stays silent ≥4 times |

**Conflict handling injection:** The `conflict_detected` block is parseable (it has a `### \`conflict_detected\`` header with backticks) and can fire when `DominantSignal.CONFLICT_DETECTED` is the trigger or ≥2 participants have `emotional_signal` set. See §12.12 (FIXED).

---

## 6. Control Flow — Turn-by-Turn

### 6.1 Session Initialisation (`__init__`)

```
1. _build_state_from_config(session_config)
   - Creates SessionMeta (reads: temperature, participation_mode from config)
   - Creates list[DiscussionGuideSection], dict[str, ParticipantState]
   - Sets section_phase from the first guide section

2. Create log directory: output/session_logs/{session_id}/

3. Initialise participant_histories = {pid: [] for pid in participants}

4. Save session_state_initial.json
```

### 6.2 Opening Turn (`run_opening`)

```
1. Create TriggerEvent(type=SESSION_START, turn_number=0)

2. call_moderator(is_opening_turn=True)
   a. load_system_prompt()  — reads file 01, strips header
   b. _state_to_session_config(state)  — reconstructs reduced config dict (no agent_payload)
   c. render_opening_message(config_dict)  — substitutes {SESSION_CONFIG} into file 03
   d. Append user message to conversation_history
   e. Anthropic API call (claude-sonnet-4-20250514, max_tokens=1500, temp=1.0)
   f. _try_parse(raw_text)
      - strip_markdown_fences()   — public since 2026-07-27; shared with run_opening()
      - json.loads()  → if fails: returns (None, JSON-specific correction message)
      - _normalize_decision() — coerces null-strings; forces probe_type/follow_up_intensity rules
      - ModeratorAPIResponse.model_validate() → if fails: returns (None, Pydantic-specific correction message)
   g. If parse fails: append targeted correction (JSON error vs. schema error), retry once
   h. If retry also fails: substitute `_build_fallback_response()`, log [RESEARCH ALERT] warning, continue session
   i. Append assistant message to conversation_history
   j. Log to api_calls.jsonl

3. apply_moderator_response(state, api_response, trigger)
   - total_turns += 1  (becomes 1)
   - speaker_id is None → no participant count update
   - consecutive_silent_turns = 0  (opening is ask_initial_to_group)
   - last_speaker_id = "MODERATOR"
   - Append to moderator_log
   - Append moderator utterance to transcript
   - Revalidate state

4. Extract initial_session_plan from conversation_history[-1]["content"]
   - Parses the raw JSON of the last assistant message
   - If "initial_session_plan" key is present and is a dict, writes to state.session_meta.initial_session_plan
   - On any exception (JSON parse failure, missing key, wrong type): silently passes, initial_session_plan stays None

5. Save state_turn_0.json
   (Note: file is named "0" but total_turns is already 1 at this point)

6. Return utterance string
```

### 6.3 Orchestrated Full Turn (`run_full_turn`)

```
For each participant, ordered by (turn_count ASC, id ASC):

  A. PARTICIPANT SPEAKS
     1. _recent_transcript()  → last 6 entries from state.transcript
     2. run_participant_turn(pid, recent_transcript=recent, hook="")
        a. Get last moderator utterance from moderator_log[-1].utterance
           (fallback: "Please share your thoughts.")
        b. call_participant(participant, session_meta, moderator_utterance,
                            conversation_history, recent_transcript, hook="")
           - build_participant_system_prompt()  (layered if agent_payload present)
           - Constructs user_message:
             * If recent_transcript: _format_recent_transcript(entries, name)
             * else: moderator_utterance
             * hook is "" in orchestrated mode — no prefix added
           - Anthropic API (model/max_tokens from agent_payload or defaults; temp from session_meta)
           - Returns plain text
        c. Create TriggerEvent(turn_number=total_turns+1, ...)
        d. record_participant_utterance(state, trigger)
           - state.group_state.last_speaker_id = participant_id
           - Append to state.transcript
        e. Return response_text

  B. MODERATOR ASSESSES (immediately after each participant, not after all have spoken)
     3. Create fresh TriggerEvent (same data as step 2c)
        Note: two TriggerEvent objects created with identical data — one for transcript
        recording, one for moderator assessment. Redundant but harmless.
     4. run_moderator_turn(trigger)
        a. Compute compress_before_turn: if total_turns > 40, compress before (total_turns - 20)
        b. call_moderator(is_opening_turn=False)
           - render_turn_message() → SESSION_STATE (agent_payload excluded), TRIGGER_EVENT, etc.
           - Anthropic API call
           - Parse + validate (follow_up_intensity silently stripped if wrong action)
        c. apply_moderator_response(state, api_response, trigger)
           → See Section 9.1 for full mutation sequence including feedback loop
        d. Save state_turn_{total_turns}.json
        e. Return utterance (empty string if stay_silent)

     5. Record moderator event in round_moderator_events list

End of participant loop.

6. Return summary dict:
   {turn_number, participant_responses, moderator_action, moderator_utterance, moderator_events}
   - moderator_action/utterance: last non-silent event (or last event if all silent)

Note: `record_participant_utterance()` is called inside `run_moderator_turn()`,
not inside `run_participant_turn()`. Both utterances get the same turn number.
```

### 6.4 Emergent Conversation Step (`run_conversation_step`)

```
Module constants (config.py / orchestrator.py):
  URGENCY_THRESHOLD = 0.55
  PEER_ADDRESS_BONUS = 0.15
  MODERATOR_INVITE_BONUS = 0.15
  CONSENSUS_RISK_CHALLENGE_PREFERENCE = 0.10
  MAX_CONSECUTIVE_PARTICIPANT_TURNS = 6
  _MAX_PARTICIPANT_HISTORY = 15

1. recent = _recent_transcript()  → last 6 entries

2. For each (pid, participant):
   a. own_turns = _get_participant_own_turns(pid)
      Walks state.transcript in order; keeps entries where speaker_id == pid;
      returns the last _MAX_PARTICIPANT_HISTORY (15) content strings.
      Empty list [] if the participant has not spoken yet.
   b. assess_engagement(participant, session_meta, recent,
                        participant_own_turns=own_turns)
      User message contains:
        - _format_recent_transcript(recent) — last 6 entries
        - If own_turns non-empty: numbered list under "What you have already said"
        - If own_turns empty: "You have not spoken yet in this session."
        - Closing question: "do you feel genuinely compelled to speak right now?"
      → Returns ParticipantEngagementAssessment(wants_to_speak, urgency, hook)
      → On any exception: returns silent default (wants_to_speak=False, urgency=0.0)
   → Stored in state.group_state.last_engagement_round (overwrites previous round)

3. Direct-address check (_resolve_moderator_targets):
   - If last moderator action was "speak" with a target:
     * Single resolved target → hard floor-handoff (next_pid set, auction bypassed)
     * Multiple resolved targets → bonus each +0.15, continue to auction
                                   (currently dormant: prompt constrains target to single)
     * "group" or None → proceed to normal auction

4. Apply urgency bonuses (if not hard-handed):
   - Peer address bonus: +0.15 if the previous speaker addressed this participant
   - Consensus risk challenge: +0.10 if consensus_risk ≥ 0.65 and intent == "challenge"
   - Bonuses capped at 0.30; urgency clamped to 1.0
   
   Select speaker:
   - Filter: willing = [a for a if a.wants_to_speak and intent != "stay_silent"
             and a.urgency >= 0.55]
   - Sort: by (-urgency, turn_count ASC)
   - next_pid = willing[0].participant_id (or None if no willing participants)

5. If next_pid is set:
   - hook = assessment.hook for this participant (or "" for hard-handoff)
   - response_text = run_participant_turn(next_pid, recent_transcript=recent, hook=hook)
   - trigger = _build_trigger_event(next_pid, response_text)
   - utterance = run_moderator_turn(trigger)
     (record_participant_utterance called inside run_moderator_turn)
   - Return {"step_type": "participant_led", "selection_mode": ..., ...}

6. If next_pid is None AND consecutive_silent_turns >= 2:
   - all_sorted by (-urgency, turn_count ASC), excluding stay_silent
   - If all_sorted[0].urgency > 0.2: use that participant
   - Same flow as step 5
   - Return {"step_type": "participant_led", "selection_mode": "low_threshold", ...}

7. If still no participant (or MAX_CONSECUTIVE_PARTICIPANT_TURNS reached):
   - silence_trigger = TriggerEvent(type=SILENCE_DETECTED, speaker_id=None,
       content="No participant volunteered to speak...",
       turn_number=self.state.session_meta.total_turns)  ← uses current total, not +1
   - utterance = run_moderator_turn(silence_trigger)
   - Return {"step_type": "moderator_intervention", ...}

Note: _get_requested_next_speaker() is defined (orchestrator.py:447) but dormant —
never called. The direct-address mechanism in step 3 supersedes it.
```

---

## 7. API Configuration

### 7.1 Moderator

| Parameter | Value | Configurable? |
|-----------|-------|---------------|
| Model | `claude-sonnet-4-6` (default) | Yes — `session_meta.moderator_model` from session config; falls back to `_DEFAULT_MODERATOR_MODEL` in `moderator_brain.py` |
| `max_tokens` | `1500` | No — hardcoded |
| `temperature` | `1.0` | No — hardcoded. `session_meta.temperature` is NOT used here |
| `system` | File 01 content (stripped header) | Via prompt file edits |
| Retry | Once, with targeted correction message | JSON errors get a JSON-specific message; Pydantic errors include the exact field error |
| Fallback on retry failure | Returns `_build_fallback_response()` — `redirect_to_group` to `"group"`, `validation_fallback=True` | Session continues; `[RESEARCH ALERT]` warning emitted to server log; turn flagged in `moderator_log.json` |

### 7.2 Participants (call_participant)

| Parameter | Value | Configurable? |
|-----------|-------|---------------|
| Model | `agent_payload.simulation_config.model` via `.get()`, else `claude-haiku-4-5-20251001` | Per-agent via JSON |
| `max_tokens` | `agent_payload.simulation_config.max_tokens` via `.get()`, else `400` | Per-agent via JSON |
| `temperature` | `session_meta.temperature` (default `1.0`) | Session-level in config JSON |
| Retry | None | Any exception propagates up and terminates the session |
| User message | If `hook` non-empty: `"You feel particularly compelled to speak because: {hook}\n\n{base_message}"` | Via emergent mode assessment |

**Important asymmetry:** The researcher can control participant temperature via `session_config.temperature`, but the moderator temperature is hardcoded.

### 7.3 Engagement Assessment (assess_engagement)

| Parameter | Value | Configurable? |
|-----------|-------|---------------|
| Model | Same as participant model (`agent_payload.simulation_config.model` or `claude-haiku-4-5-20251001`) | Per-agent via JSON |
| `max_tokens` | `250` | No — hardcoded in `assess_engagement()` |
| `temperature` | `session_meta.temperature` | Session-level |
| Retry | None | On any exception: logs `WARNING` then returns silent default; session continues |
| Output format | JSON `{wants_to_speak, urgency, hook}` | Parsed with `json.loads()` after markdown fence stripping; user message now opens with explicit `{` instruction |
| Participant own turns | This participant's previous utterances from `state.transcript`, capped at `_MAX_PARTICIPANT_HISTORY = 15`. Extracted by `_get_participant_own_turns(pid)` from the orchestrator before calling. | Via orchestrator constant |
| `participant_histories` (multi-turn history) | Not passed — `assess_engagement` does not receive the per-participant conversation history used by `call_participant` | Not configurable |

**Note:** `assess_engagement` uses the same model as `call_participant` but with `max_tokens=250` (raised from 80 to prevent truncation mid-JSON when the model produces any preamble). The user message contains an explicit instruction that the first character must be `{`. It is a separate API call per participant per step and is not connected to `participant_histories`. The participant's own prior utterances are now supplied via `participant_own_turns` (extracted from the shared `state.transcript`), giving the model memory of what this participant has already said. What remains absent: the moderator's responses to the participant in conversational context, and the full multi-turn dialogue flow that `participant_histories` contains.

### 7.4 API Key

The Anthropic client is instantiated without an explicit key argument: `anthropic.Anthropic()`. This reads from the `ANTHROPIC_API_KEY` environment variable. No key is stored in the codebase.

### 7.5 Context Window Management

When `total_turns > 40`, `compress_before_turn = total_turns - 20` is passed to `to_prompt_json()`.

`to_prompt_json()` calls `self.model_dump(mode="json")` to produce a plain dict, then applies three transformations in order:

1. **Strips `agent_payload`** from every participant's dict (regardless of other transformations).
2. **Windows `moderator_log` to the last `_MODERATOR_LOG_LIVE_WINDOW` (3) entries.** Only the three most recent log entries are included in the JSON sent to the moderator. This is sufficient for: honouring or abandoning `queued_next_action` (most recent entry); short-term strategic awareness of recent moderation direction (preceding two entries); and fallback context when structured state fields have not been fully populated. `_MODERATOR_LOG_LIVE_WINDOW = 3` is a module-level constant in `session_state.py`. **This value should be reviewed once feedback loop reliability is confirmed in trials — at that point 1 may be sufficient.**
3. **Compresses old log entries** (those present in the windowed slice): removes `situation_assessment` and `justification` for entries where `turn < compress_before_turn` and `compressed` is falsy. Given a window of 3, the remaining entries are almost always recent enough that this step fires infrequently — but it is preserved for correctness.

**Important:** All three transformations work on a temporary `model_dump()` copy. The actual `SessionState` and its objects are never mutated. `moderator_log` is never shortened in the live Python object. `ModeratorLogEntry.compressed` remains `False` in the live model. `agent_payload` remains in `ParticipantState`. State snapshots on disk contain the full uncompressed, unwindowed state.

**`save_moderator_log()` is unaffected.** It reads directly from `self.state.moderator_log` (the full in-memory list) and writes the complete record to `moderator_log.json`. The windowing in `to_prompt_json()` never touches this path. The full log is preserved for research audit purposes.

The moderator API calls are stateless: the conversation history messages list contains only the single current turn's user message. The `{SESSION_STATE}` injected into the user message contains the structured state (with windowed moderator logs), avoiding O(N^2) token bloat.

---

## 8. Agent Loading from External JSON

### 8.1 Required Fields (raise `KeyError` if absent)

```
raw["agent_id"]
raw["persona"]["demographics"]["name"]
raw["persona"]["demographics"]["age"]
raw["persona"]["demographics"]["gender"]
```

### 8.2 Optional Fields (accessed via `.get()` with safe defaults)

```
raw["persona"]["demographics"].get("location", {})
  → location.get("urban_rural", "")
  → location.get("region", "")
  → location.get("country", "")
raw["persona"]["demographics"].get("diet")
raw["persona"].get("food_consumption", {})
raw["persona"].get("psychological_profile", {})
raw["simulation_config"].get("notes")
raw["simulation_config"].get("temperature")  ← READ but IGNORED
```

**Model and token budget** — accessed in `call_participant()` and `assess_engagement()`:

```python
sim_cfg = participant.agent_payload.get("simulation_config", {})
model = sim_cfg.get("model", _DEFAULT_MODEL)           # default: claude-haiku-4-5-20251001
max_tokens = sim_cfg.get("max_tokens", _DEFAULT_MAX_TOKENS)  # default: 400 (call_participant)
                                                              # 250 (assess_engagement — hardcoded)
```

`assess_engagement` uses the participant's model but ignores `max_tokens` from the agent JSON — it always uses 250.

### 8.3 `_state_to_session_config()` — Opening Prompt Config Reconstruction

Private function in `moderator_brain.py`. Converts `SessionState` to a reduced config dict used exclusively for the opening prompt.

Fields included:

| Field | Source |
|-------|--------|
| `session_id` | `session_meta.id` |
| `research_objective` | `session_meta.research_objective` |
| `topic_domain` | `session_meta.topic_domain` |
| `participant_collective_identity` | `session_meta.participant_collective_identity` |
| `moderator_knowledge_brief` | `session_meta.moderator_knowledge_brief` |
| `researcher_notes` | `session_meta.researcher_notes` |
| `participants` | list of `{id, name, profile_summary}` only — **no `agent_payload`** |
| `discussion_guide` | list of `{section_index, section_label, section_phase, section_purpose, scripted_question, probing_depth_ceiling, stimulus}` — **`suggested_probes` is NOT included**. This is a separate omission in `_state_to_session_config()` itself: the function was written without a `suggested_probes` key and has never been updated to add one. This is independent of the now-fixed propagation bug in `_build_state_from_config()` (see §12.11). Even with that bug fixed, the opening turn prompt still does not receive `suggested_probes`. Turns 1+ do see them via `to_prompt_json()`, which serialises the full `discussion_guide` without filtering. |

Fields NOT included: `temperature`, `participation_mode`, `initial_session_plan`, `total_turns`, `session_started_at`, `current_section_index`, `section_phase`, `current_question_index`, `group_state`, `moderator_log`, `transcript`, `agent_payload`.

### 8.4 Psychological Score Translation — **REMOVED**

The Layer 3 `psychological_profile` rendering block has been removed from `build_participant_system_prompt()`. The function `_score_to_instruction()` still exists as dead code but is never called. Focus-group agents (`fg_agents_v1`) store psychometric data in a top-level `psychometric_scores` block that the renderer does not read — scores are held out for analysis, not injected into the prompt.

### 8.5 `_BEHAVIOUR_INSTRUCTIONS` — Fixed Behavioural Block

Fixed string constant appended to every participant system prompt (both inline and agent_payload paths). Not configurable. Study-agnostic — no domain-specific references. A Spanish mirror (`_BEHAVIOUR_INSTRUCTIONS_ES`) is used when the agent's `language` field is `"es"`.

The block contains 9 bullet points covering: willingness to participate proportional to profile; respond as a real participant not an analyst; no polished essay style; resist automatic philosophical escalation; connect to concrete everyday experience only when natural; no stage directions or asterisks; never break character; natural silence when nothing new to add; when addressed directly by the moderator, respond — but a brief or deflecting answer is acceptable.

There is **no sentence-count instruction** in this block. Response length is governed by `max_tokens` only.

### 8.6 Agent Payload Visibility by Turn

| Turn | API call | agent_payload visible to model? |
|------|----------|--------------------------------|
| 0 (opening) | Moderator | No — `_state_to_session_config()` excludes it |
| 1+ (non-opening) | Moderator | No — `to_prompt_json()` strips it from every participant dict |
| Any | Participant (call_participant) | Yes — payload used to build system prompt (Layer 1: demographics; Layer 2: food_consumption / generic fallback; Layer 4: notes). Layer 3 (psychological_profile) is no longer rendered. |
| Any | Engagement (assess_engagement) | Partial — only `demographics` and `simulation_config.model` used |

**This is a change from the previous version** where `agent_payload` was included in all moderator-facing state JSON from turn 1 onward. The moderator now sees only the behavioural tracking fields listed in Section 4.3. Psychological dimension names, raw scores, and technical metadata are no longer exposed to the moderator model.

### 8.7 Path-based loading (added 2026-06-10)

Session configs may reference agent JSON files by path:

```json
"participants": [
  { "agent_payload_path": "agents/twin2k500/twin_574.json" }
]
```

When `agent_payload_path` is present, `_build_state_from_config` loads the
JSON, routes through the existing `load_agent_from_json()` in
`participant_agent.py`, and populates `ParticipantState.agent_payload`.
The existing inline path (`id`/`name`/`profile_summary`) is unchanged and
remains supported.

Validation rules enforced at config-load time:
- A participant entry must specify exactly one of (a) `agent_payload_path`,
  (b) inline `agent_payload`, or (c) legacy inline fields. Combinations
  raise `ValueError`.
- A missing file at `agent_payload_path` raises `FileNotFoundError`.
- Malformed JSON at `agent_payload_path` raises `ValueError`.

Rationale and verification: see CHANGELOG.md (2026-06-10) and
docs/changes/2026-06-10_agent_loading_wired.md.

---

## 9. State Mutation Rules

There are two authorised mutation functions in `session_state.py`. All other state changes must go through them.

### 9.1 `apply_moderator_response(state, response, trigger_event) -> SessionState`

Called after every moderator API call (including `stay_silent`). Performs all of the following in sequence:

1. `session_meta.total_turns += 1`
2. If `trigger_event.speaker_id` is set and valid:
   - `participant.turn_count += 1`
   - `participant.follow_up_count_current_question = trigger_event.follow_up_count_this_question`
   - `group_state.section_turn_counts[pid] += 1`
3. Recompute `group_state.dominant_voices` (>50% of section turns)
4. If section_phase != intro: recompute `group_state.silent_participants` (<15% of total turns)
5. If action == `section_transition`:
   - `current_section.completed = True`
   - Advance `current_section_index` if not at last section
   - Update `section_phase` from new current section
   - Reset `current_question_index = 0`
   - Reset `section_turn_counts = {}`
5a. If action == `reflect_contradiction` AND `decision.target` is a valid participant ID:
    Find the oldest `UnresolvedTension` where `participant_id == target` and `resolved=False`.
    If found: set `surfaced=True`, increment `surface_count += 1`.
    If `surface_count >= 2`: set `resolved=True`, `resolved_at_turn = trigger_event.turn_number`.
    If no matching tension exists: no-op (the action still fires, the moderator speaks; only the state update is skipped).
6. If action == `stay_silent`: `consecutive_silent_turns += 1`  
   Else: `consecutive_silent_turns = 0`, `last_speaker_id = "MODERATOR"`
7. Append `ModeratorLogEntry` to `moderator_log` (always, including stay_silent)
8. **Feedback loop — write moderator inferences directly from typed fields:**
   - **consensus_risk:** If `decision.consensus_risk_assessment is not None`, set `group_state.consensus_risk = decision.consensus_risk_assessment`. Rounded to 3 decimal places by the `validate_consensus_risk` field validator when state is re-validated at step 10.
   - **emotional_signals:** For each `EmotionalSignalItem` in `decision.emotional_signals`, if `item.participant_id` is a valid participant ID, set `state.participants[item.participant_id].emotional_signal = item.signal`. Multiple participants can be updated in one turn. Values are overwritten, not appended.
   - **new_contradictions:** For each `ContradictionItem` in `decision.new_contradictions`, if `item.participant_id` is a valid participant ID and no `UnresolvedTension` with `resolved=False` already exists for that participant, append a new `UnresolvedTension(participant_id=item.participant_id, flagged_at_turn=trigger.turn_number, description=item.description)`. The deduplication check is per-participant, not per-description.
9. Append utterance to `transcript` only if action != `stay_silent`
10. `SessionState.model_validate(state.model_dump())` — re-validates whole state; triggers `validate_participation_balance` to recompute `participation_balance`; triggers `validate_consensus_risk` to round `consensus_risk`

**Return:** A new `SessionState` instance (re-validated).

**Feedback loop design notes:**
- The feedback loop fires on every moderator turn, including `stay_silent`. A `stay_silent` turn can still update `consensus_risk`, `emotional_signals`, and `new_contradictions` if those fields are non-empty.
- `group_dynamic_flags` is a free-text audit field only. It is stored in the log but no longer parsed for any state update. Its prior role (providing consensus_risk and contradiction signals via regex) has been replaced by the three typed fields.
- `emotional_signal` per participant is overwritten on every turn the moderator includes that participant in `emotional_signals`. It always reflects the most recent signal; there is no history.
- Unresolved tensions are created by the feedback loop (step 8) from `new_contradictions` and resolved by the action handler (step 5a). Resolution requires two `reflect_contradiction` actions targeting the same participant while a tension is open. The first surfacing sets `surfaced=True, surface_count=1`; the second sets `resolved=True`. The two actions do not need to be consecutive.

### 9.2 `record_participant_utterance(state, trigger_event) -> SessionState`

Called before the moderator assessment. Performs only:

1. If `trigger_event.speaker_id` is set:
   - `group_state.last_speaker_id = speaker_id`
   - Append entry to `transcript`

Does NOT increment `turn_count`. Turn count is incremented by `apply_moderator_response` when the moderator processes the participant's trigger.

**Consequence:** A participant's turn count goes up when the moderator responds to them, not when they speak. In emergent mode there is an additional complication — see Section 12.7.

---

## 10. Prompt Injection Logic

Special-case injections are evaluated in `prompt_renderer.render_turn_message()` and appended to the rendered template text. They are appended in this fixed order:

| # | Injection name | Trigger condition | Fires in practice? |
|---|----------------|-------------------|--------------------|
| 1 | `consensus_risk >= 0.65` | `group_state.consensus_risk >= 0.65` | **Can fire** — set from `decision.consensus_risk_assessment` (typed float) |
| 2 | `participation_imbalance` | `len(silent_participants) > 0` AND `phase != intro` | Yes — when turn distribution falls below 15% |
| 3 | `unresolved_contradiction_due` | Any `UnresolvedTension` with `resolved=False`, age ≥3 turns, speaker matches | **Can fire** — tensions created from `decision.new_contradictions` (typed list) |
| 4 | `over_probe_warning` | `trigger.follow_up_count_this_question >= 3` | **No — always 0 in practice** |
| 5 | `emotional_register_elevated` | `participant.emotional_signal is not None` | **Can fire** — set from `decision.emotional_signals` (typed list) |
| 6 | `section_transition_check` | All in section have spoken AND `current_question_index > 0` | **No — index never increments** |
| 7 | `consecutive_silent_turns >= 4` | `group_state.consecutive_silent_turns >= 4` | Yes — in both modes |

**Injections 1, 3, and 5 activate** from typed fields in the moderator decision, not from string parsing:
- Injection 1: fires when `group_state.consensus_risk >= 0.65`; set from `decision.consensus_risk_assessment`
- Injection 3: fires when an `UnresolvedTension` with `resolved=False` exists and is old enough; created from `decision.new_contradictions`
- Injection 5: fires when `participant.emotional_signal is not None`; set from `decision.emotional_signals`

These injections no longer depend on specific phrasing in `group_dynamic_flags`. `group_dynamic_flags` is retained as a free-text audit field only.

---

## 11. Output Files and Logging

All output is written to `output/session_logs/{session_id}/`.

| File | Created | Content |
|------|---------|---------|
| `session_state_initial.json` | On `__init__` | Full state before any API call; includes `agent_payload` for all participants |
| `state_turn_0.json` | After `run_opening` | State after opening (total_turns = 1); includes `initial_session_plan` if parsed |
| `state_turn_{N}.json` | After each `run_moderator_turn` | Full state snapshot; N = `total_turns` after the turn; includes `agent_payload` and `last_engagement_round` |
| `api_calls.jsonl` | Appended per moderator call | `{turn, action, input_tokens, output_tokens}` per line |
| `transcript.json` | On `save_transcript()` | `list[{turn, speaker_id, speaker_name, content, timestamp, selection_mode}]`; excludes `stay_silent` turns |
| `transcript.txt` | On `save_transcript()` | Human-readable; `[TURN N] SPEAKER: content` per entry |
| `moderator_log.json` | On `save_moderator_log()` | Full `ModeratorLogEntry` list including stay_silent; includes `brief_justification` and `selection_mode` |

**Note:** `api_calls.jsonl` now also records `participant_engagement_assessment` and `participant_response_generation` events with per-call token accounting, model, and stop reason (`core/api_logging.py`).

**Timestamp source:** `datetime.utcnow()` (naive UTC). Python 3.12+ deprecates `utcnow()`.

**`save_transcript()` and `save_moderator_log()` are not called automatically.** They are called in `run_session.py`'s `finally` block; in any other entrypoint they must be called explicitly.

### 11.1 Post-Session Access via the UI (Past Sessions Routes)

The UI layer (`ui/server.py`) exposes four disk-based routes that operate directly on `output/session_logs/` without consulting the in-memory `_sessions` dict. These routes work after server restart and for sessions that were never registered in the current process:

| Route | Reads | Notes |
|-------|-------|-------|
| `GET /sessions` | All subdirs of `output/session_logs/` | Returns `[{session_id, started_at, total_turns, participant_count, has_transcript, has_moderator_log}]` sorted by `started_at` descending. `total_turns` = count of MODERATOR utterances in `transcript.json`. `started_at` = first `timestamp` in `moderator_log.json`. Dirs missing both files are skipped silently. |
| `GET /sessions/{session_id}/transcript` | `output/session_logs/{session_id}/transcript.json` | Returns file contents as JSON. HTTP 404 if absent. |
| `GET /sessions/{session_id}/moderator-log` | `output/session_logs/{session_id}/moderator_log.json` | Returns file contents as JSON. HTTP 404 if absent. |
| `DELETE /sessions/{session_id}` | `output/session_logs/{session_id}/` | Removes the entire directory (`shutil.rmtree`). HTTP 404 if absent. Returns `{deleted: true}`. |

**Path traversal protection:** `session_id` is validated against `^[a-zA-Z0-9_-]+$` before any filesystem access. Values that do not match receive HTTP 400 without touching the filesystem. This covers both UUID session IDs and human-readable IDs such as `session_remote_work_01`.

**In-memory / disk consistency:** Deleting via `DELETE /sessions/{session_id}` removes disk files only. If the session is currently registered in `_sessions` (same server process, same session), the in-memory orchestrator remains alive and the existing `/transcript/{session_id}` and `/moderator-log/{session_id}` routes (which read from memory, not disk) continue to work until the process restarts. After restart, the disk files are gone and none of the routes can serve that session.

**Module-level session state in `ui/server.py`:** Five dicts maintain live session state for the process lifetime. None have TTL or eviction:

| Dict | Key → Value | Purpose |
|------|-------------|---------|
| `_sessions` | `session_id → FocusGroupOrchestrator` | Live orchestrator instances |
| `_stop_flags` | `session_id → bool` | Signals the sync generator to halt |
| `_session_turns` | `session_id → int` | Turn limit passed at session start |
| `_active_streams` | `session_id → bool` | Concurrency mutex — prevents two SSE generators for the same session |
| `_session_errors` | `session_id → str` | Stores `"ExceptionType: message"` when a generator terminates with an exception. Any subsequent `GET /stream/{session_id}` call is immediately answered with a fatal `error` SSE, preventing a new generator from restarting a broken session. Fully documented in `UI_ARCHITECTURE.md §9.13`. |

---

## 12. Known Gaps Between Design and Implementation

### 12.1 Fields Still Never Updated by the Orchestrator

The following fields are defined in the data model, potentially shown to the moderator model in state JSON, but never set by any orchestrator code:

| Field | Location | Current behaviour | Impact |
|-------|----------|-------------------|--------|
| `participant.last_response_quality` | `ParticipantState` | **FIXED** — Set from moderator decision | Evaluated per-turn |
| `participant.engagement_signal` | `ParticipantState` | **FIXED** — Set from moderator decision | Evaluated per-turn |
| `participant.dominant_tendency` | `ParticipantState` | **FIXED** — Set from moderator decision | Evaluated per-turn |
| `participant.topics_covered` | `ParticipantState` | **FIXED** — Updated via decision | Reflected in state |
| `group_state.emergent_themes` | `GroupState` | **FIXED** — Appended via decision | Dynamic theme tracking |
| `group_state.group_has_agreed_easily_on` | `GroupState` | **FIXED** — Appended via decision | Dynamic consensus tracking |
| `session_meta.current_question_index` | `SessionMeta` | **FIXED** — Increments on ASK_INITIAL_TO_GROUP | section_transition_check can fire |

**Fields that were previously gaps and are now addressed:**
- `participant.emotional_signal` — set by the feedback loop from `decision.emotional_signals` (typed list). Fires for any participant the moderator includes in that list, regardless of `probe_type`. No longer tied to `emotional_depth` probe type.
- `group_state.consensus_risk` — set directly from `decision.consensus_risk_assessment` (typed float). Required on every turn by the system prompt; no longer depends on string format in `group_dynamic_flags`.
- `group_state.unresolved_tensions` — created from `decision.new_contradictions` (typed list). No longer depends on string format in `group_dynamic_flags`.

### 12.2 `follow_up_count_this_question` Never Increments — **FIXED**

The flow:
1. Trigger created with `follow_up_count_this_question = participant.follow_up_count_current_question` (= 0 initially)
2. `apply_moderator_response` sets `participant.follow_up_count_current_question = trigger.follow_up_count_this_question` (= 0)

No code increments the counter. The `over_probe_warning` injection (fires at `>= 3`) and the `{FOLLOW_UP_COUNT}` placeholder shown to the model both always show 0.

**To fix:** Track consecutive probes per participant per question in the orchestrator; increment and pass the counter in the trigger.

### 12.3 Phase Modifiers Are Never Delivered — **FIXED**

`{PHASE_MODIFIER}` now exists in `02_USER_MESSAGE_TEMPLATE.md` and is substituted by `render_turn_message()`. Phase modifiers from file 04 are delivered to the moderator. The conflict-handling injection (`conflict_detected` header) is also parseable and can fire when triggered.

### 12.5 Emergent Mode: No Double Transcript Recording (Corrected)

During implementation review, a potential double-recording bug was identified: `run_conversation_step()` calls `run_participant_turn()` (which internally calls `record_participant_utterance()`), then calls `_build_trigger_event()` and `run_moderator_turn()`.

Inspection of the final code confirms the bug does **not** exist. The sequence in `run_conversation_step()` is:

```python
response_text = self.run_participant_turn(next_pid, recent_transcript=recent, hook=hook)
trigger = self._build_trigger_event(next_pid, response_text)   # builds struct only
utterance = self.run_moderator_turn(trigger)                    # calls apply_moderator_response
```

`_build_trigger_event()` only constructs a `TriggerEvent` dataclass — it does not call `record_participant_utterance()`. The transcript entry is written exactly once per participant turn.

### 12.6 Moderator Temperature Not Researcher-Controlled

`session_meta.temperature` is applied to participant and engagement calls. The moderator temperature is hardcoded to `1.0` in `moderator_brain._call_api()`.

### 12.7 `assess_engagement` Has No Retry; `participant_histories` Still Not Passed

On any API failure, `assess_engagement()` now emits a `logging.WARNING` (participant ID, exception text, raw response if available via `getattr(e, 'raw', 'unavailable')`) before returning the silent default `wants_to_speak=False, urgency=0.0`. There is still no retry and no error signal to the orchestrator. A participant that consistently fails the engagement call will always appear disengaged, biasing turn selection in emergent mode. The warning makes failures visible in the server log instead of disappearing.

**Participant own utterances are now passed.** `_get_participant_own_turns(pid)` extracts this participant's previous contributions from `state.transcript` (capped at 15), and they are presented under a "What you have already said in this session" header. The closing question explicitly asks whether there is something genuinely new to add. This eliminates the prior cold-call limitation for the participant's own history.

**What is still not passed:** `participant_histories` — the full multi-turn conversation history maintained by `call_participant`. The engagement model does not see the moderator's responses to the participant, the participant's prior contributions in their full conversational context, or the complete dialogue flow. It sees: (1) the last 6 entries of the shared transcript via `_format_recent_transcript()`, and (2) a numbered flat list of this participant's own prior utterances.

### 12.8 Tension Resolution Requires Two Separate `reflect_contradiction` Actions

The feedback loop creates `UnresolvedTension` entries. Resolution is now possible but requires the moderator to fire `reflect_contradiction` targeting the same participant **twice**. One surfacing is not enough. In short sessions, or if the moderator never repeats the action, tensions will persist indefinitely and the `unresolved_contradiction_due` injection will continue to fire on every subsequent turn when that participant speaks.

**Edge case:** If `reflect_contradiction` fires against a participant who has no open `UnresolvedTension`, step 5a is a no-op — the action still executes (the moderator speaks) but no state is updated. The tension must have been created first by the feedback loop from a `ContradictionItem` in `decision.new_contradictions`.

**No partial-resolution signal:** There is no externally visible marker that a tension has been surfaced once (`surfaced=True, surface_count=1`) but not yet resolved. The audit log records the `reflect_contradiction` action in `moderator_log.json`, but the state snapshot is needed to check `surface_count`.

### 12.9 No Retry Logic for Participant API Calls

`call_participant()` now wraps the API call and response parsing in `try/except`. On failure it emits a `logging.WARNING` (participant ID, exception text, raw response if available) and then re-raises the exception. Any API exception still terminates the session; the warning makes the cause visible in the server log before termination.

### 12.10 Engagement Assessment: Last Round Only

`state.group_state.last_engagement_round` stores only the most recent assessment round. Previous rounds are overwritten. No history of urgency patterns across steps is persisted in state, making it impossible to retrospectively analyse how urgency changed over the session from state snapshots alone.

### 12.11 `suggested_probes` Silently Dropped at Session Creation — **FIXED (residual limitation remains)**

`DiscussionGuideSection` defines `suggested_probes: list[str] = Field(default_factory=list)`. The UI correctly includes researcher-configured probes in the `POST /start-session` body and the CLI path picks them up from the session config JSON.

**Note on guide persistence:** `suggested_probes` are preserved when guides are saved and loaded via `POST /PUT /GET /guides` in `ui/server.py`. However, saving was silently failing for any guide with at least one section until a separate UI-layer bug was fixed: `_validate_sections()` was not injecting `probing_depth_ceiling` before Pydantic validation (see `UI_ARCHITECTURE.md §9.11`). This is unrelated to the `core/` bug described below, but an auditor should be aware that guide persistence only became fully operational after both fixes were applied.

**Bug (now fixed):** `_build_state_from_config()` in `orchestrator.py` constructed each `DiscussionGuideSection` using explicit keyword arguments without passing `suggested_probes`, causing the field to default to `[]` in every session regardless of researcher input.

**Fix applied:** `suggested_probes=s.get("suggested_probes", [])` was added to the `DiscussionGuideSection(...)` constructor call in `_build_state_from_config()`. The corrected constructor is:

```python
guide.append(
    DiscussionGuideSection(
        section_index=s["section_index"],
        section_label=s["section_label"],
        section_phase=SectionPhase(s["section_phase"]),
        section_purpose=s["section_purpose"],
        scripted_question=s["scripted_question"],
        probing_depth_ceiling=ProbingDepthCeiling(s["probing_depth_ceiling"]),
        stimulus=stimulus,
        suggested_probes=s.get("suggested_probes", []),
    )
)
```

Researcher-configured probes are now correctly stored in session state and appear in the full state JSON delivered to the moderator via `to_prompt_json()` on turns 1 onwards (since `discussion_guide` is not filtered). State snapshots (`session_state_initial.json`, `state_turn_N.json`) now reflect the actual configured probes.

**Residual limitation — opening turn only:** `_state_to_session_config()` in `moderator_brain.py` (used only for the opening turn prompt) does not serialise `suggested_probes` in its `discussion_guide` output. This is a separate, independent omission in that function — it was never updated to include the field. The moderator's opening turn therefore does not see `suggested_probes`. All subsequent turns do. See §8.3 for details.

### 12.12 CONFLICT HANDLING INJECTION Never Fires — **FIXED**

The `conflict_detected` block in `04_PHASE_MODIFIERS_AND_SPECIAL_CASES.md` now has a parseable `### \`conflict_detected\`` header and is extracted by `_parse_phase_modifiers()`. The injection fires when `DominantSignal.CONFLICT_DETECTED` is the trigger or when ≥2 participants have a non-null `emotional_signal`.

### 12.13 `probe_type` Not Enforced for `direct_probe` After Validator Removal — **Known Gap**

### 12.14 Smoke Test Fixes Applied

During the smoke test execution of Model B, several bugs and schema gaps were identified and successfully resolved:
- **PromptRenderer Crash**: The DominantSignal enum was missing from the prompt_renderer.py imports, causing a NameError crash during state rendering. This has been fixed.
- **Session Opening Prompt Validation**: The hardcoded JSON template in prompts/03_SESSION_OPENING_PROMPT.md was missing the newly required intervention_mode and rief_justification fields, causing immediate validation fallbacks on turn 1. The template has been aligned with the Pydantic schema constraints.
- **Schema Gaps (Selection Mode)**: 
  - ModeratorLogEntry was missing rief_justification.
  - TranscriptEntry elements were missing selection_mode.
  - The orchestrator has been updated to pipe the resolved selection_mode directly to 
ecord_participant_utterance and pply_moderator_response, ensuring all state logs contain the correct mode tags for downstream auditing.


`validate_probe_type_consistency` was removed from `ModeratorDecisionResponse` (see §14.12) because it caused `ModeratorResponseError` when the model produced `probe_type` for non-`direct_probe` actions — a common model error that upstream normalisation now prevents. However, removing the validator also removed the check that `direct_probe` requires a non-null `probe_type`.

**Current behaviour:** If the model returns `direct_probe` without a `probe_type` (or with the null-string `"null"`), normalization does not alter it, and Pydantic accepts `null` (the field has `default=None`). The turn is accepted without a retry, and `moderator_log.json` records `probe_type: null` for a `direct_probe` action.

**Research quality impact:** The `probe_type` is part of the auditable moderator reasoning for probe turns. A null `probe_type` on `direct_probe` means the probe sub-type is unclassified in the research record. This is a data quality gap, not a session failure.

**Frequency:** Rare in practice. The normalization handles the common case (non-null probe_type on non-direct_probe). Missing probe_type on direct_probe was not observed before the validator was removed; the validator was most often triggered by probe_type set on non-probe actions.

---

## 13. Audit Trail Completeness

### What is fully recorded

| Event | Recorded where |
|-------|---------------|
| Every moderator decision | `moderator_log.json` — includes `situation_assessment`, `action`, `probe_type`, `follow_up_intensity`, `justification`, `group_dynamic_flags`, `queued_next_action`, `selection_mode`, utterance, turn number, timestamp |
| Stay_silent decisions | `moderator_log.json` — logged with empty utterance; NOT in transcript |
| Every participant utterance | `transcript.json` and `transcript.txt` |
| Every moderator utterance (non-silent) | `transcript.json` and `transcript.txt` |
| Session state after every moderator turn | `state_turn_{N}.json` — full Pydantic model dump including `agent_payload`, `last_engagement_round`, `initial_session_plan` |
| Moderator API token usage | `api_calls.jsonl` — input and output tokens per call |
| Initial session state | `session_state_initial.json` |
| Initial session plan | `state_turn_0.json` (via `session_meta.initial_session_plan`) |

### What is NOT recorded

| Event | Gap |
|-------|-----|
| Participant API token usage | Now logged in `api_calls.jsonl` (event types `participant_response_generation`, `participant_engagement_assessment`) |
| Engagement assessments per step | Only `last_engagement_round` in state snapshots; previous rounds permanently lost |
| Individual assess_engagement API failures | `logging.WARNING` emitted (visible in server log); no exception raised to orchestrator; no entry in session log files |
| Which recent_transcript entries were shown to which participant | Not recorded |
| Which participant_own_turns were passed to each assess_engagement call | Not recorded directly; reconstructable from state.transcript at the time of the call (the call uses entries up to that point, capped at 15) |
| The exact system prompt used for each participant | Reconstructable from state snapshot + `build_participant_system_prompt()`, but not logged directly |
| The raw prompt sent to the moderator | Reconstructable from state snapshot + `render_turn_message()`, but not logged directly |
| Retry attempts | Now logged in `api_calls.jsonl` as `moderator_decision_retry_attempt` events |
| Whether `follow_up_intensity` was silently stripped | Log shows `null`; no record that model returned a non-null value that was corrected |

---

## 14. Design Decisions and Rationale

### 14.1 Two-Layer Output (decision + utterance)

The model is required to produce a structured `moderator_decision` JSON block before the `utterance`. This forces reasoning before generation and creates an audit trail that is independent of what the model said.

### 14.2 Full Session State on Every Moderator Turn

The entire `SessionState` is serialised to JSON and injected into every moderator API call. This makes every decision independently interpretable. The cost is large prompt sizes, but the moderator calls themselves are stateless (using only the single turn's prompt) to avoid O(N^2) token bloat.

**Change from previous version:** `agent_payload` is now excluded from the serialised state (Section 4.3). This reduces prompt size and removes the hypothesis exposure risk, at the cost of the moderator not having access to the raw agent file contents (which it was not designed to interpret).

### 14.3 Single Mutation Point

All state changes go through `apply_moderator_response` and `record_participant_utterance`. The main exception is `_build_state_from_config` (in `orchestrator.py`) for initial construction, and the `initial_session_plan` write in `run_opening()` which directly mutates `state.session_meta.initial_session_plan` outside of these two functions.

### 14.4 Prompt Files as Live Configuration

All four prompt files are read from disk on every call. Researchers can edit prompt text without code changes.

### 14.5 Participant Temperature vs. Moderator Temperature

Participant and engagement assessment temperature (`session_meta.temperature`) is researcher-controlled. The moderator temperature is hardcoded at `1.0` because the moderator uses structured JSON output with strict validation.

### 14.6 `stay_silent` Logged but Not Transcribed

The moderator's silent decisions are logged with full reasoning in `moderator_log.json`. They do not appear in `transcript.json` because that file represents the observable conversation. A researcher can see every silent assessment in the log.

### 14.7 Feedback Loop via Typed Fields

The feedback loop uses three typed fields in `ModeratorDecisionResponse` rather than regex parsing of free-text strings. `consensus_risk_assessment` (float), `emotional_signals` (list of `EmotionalSignalItem`), and `new_contradictions` (list of `ContradictionItem`) are validated by Pydantic on receipt. If the model returns a malformed value for these fields, Pydantic will reject the response and trigger a retry — the same path as any other validation failure.

**Trade-off vs. the previous regex approach:** The typed approach is more robust (wrong types are caught, not silently ignored) and more informative (the model can report multiple emotional signals or contradictions in a single turn). The cost is that the output schema is larger and the system prompt now needs to explain three structured fields instead of one free-text list.

**`group_dynamic_flags` is retained** as an unstructured audit field for any other observations the moderator wants to record. It is never parsed for state updates.

### 14.8 Dual Participation Mode

**Orchestrated mode** (`run_full_turn`): guarantees every participant speaks once per round. Simpler, more reproducible, easier to audit. Appropriate for structured data collection.

**Emergent mode** (`run_conversation_step`): participants self-select based on urgency. Produces more naturalistic conversational dynamics where participants react to each other, some speak more, some stay silent. More realistic but less controlled.

The modes are implemented as entirely separate methods on `FocusGroupOrchestrator` and share all state. A session can switch modes between turns in principle (though the CLI does not expose this).

**Direct-address floor-handoff (emergent only):** When the moderator speaks and targets a single participant (any action with a resolved single target), the orchestrator bypasses the urgency auction and seats that participant as the next speaker. This applies to `direct_probe`, `reactivate_silent`, `invite_to_speak`, and any other single-target action. In orchestrated mode, targeting has no effect on turn order — `run_full_turn` always cycles all participants.

### 14.9 Urgency Threshold = 0.55

`URGENCY_THRESHOLD = 0.55` is a module constant in `orchestrator.py`. The choice of 0.55 distinguishes "genuinely wants to speak" from "might have something to say." Values of 0.0–0.29 are treated as disengaged; 0.30–0.54 as potentially interested but not strongly; above 0.55 as actively wanting to contribute. The threshold for the lower-bar fallback (step 5 of `run_conversation_step`) is hardcoded at `> 0.2`.

These thresholds are not empirically calibrated. They represent design assumptions about the engagement model's output distribution.

### 14.10 Participant History in Engagement Assessment

`assess_engagement()` previously made a cold call — the model knew only what it saw in the last 4 transcript entries. This meant it had no memory of what the participant had already contributed, creating a systematic risk that participants who had spoken recently would appear equally or more eager to speak again (since their previous contributions were invisible).

The fix adds `participant_own_turns` (from `_get_participant_own_turns()`, capped at `_MAX_PARTICIPANT_HISTORY = 15`), presented as a numbered list under "What you have already said in this session." The question is reframed to ask explicitly whether there is something **new** to add.

**Design choice for the cap:** 15 utterances is large enough to represent a full session for most participants (3 participants × 5 turns per round × 3 rounds = 15 total turns at most in a typical session), but prevents context bloat in longer runs. The cap is a named constant so it can be tuned without touching function bodies.

**What this does not fix:** The engagement model still does not receive `participant_histories` (the full multi-turn conversation history). Adding that would create a much larger prompt for each assessment call, multiplied by N participants per step. The current design trades completeness for token efficiency.

### 14.11 `follow_up_intensity` Silently Stripped

Changed from raising `ValueError` to silently setting `null` when the model returns `follow_up_intensity` for non-probe actions. This prevents retry failures on common model errors (e.g., setting `follow_up_intensity` on `redirect_to_group`). The cost is that the audit log cannot distinguish between "model correctly returned null" and "model returned a non-null value that was corrected."

### 14.12 `ModeratorResponseError` No Longer Fatal — **Changed**

Previously, two consecutive validation failures raised `ModeratorResponseError`, which propagated as an unhandled exception through the sync generator and terminated the session with a fatal error SSE. The researcher saw "ModeratorResponseError" in the error banner, had to restart, and lost any session progress.

The change: `call_moderator` now substitutes `_build_fallback_response()` instead of raising. The fallback is `redirect_to_group` to `"group"` with a fixed utterance ("Let's hear from the group on this — what are your thoughts?"). `validation_fallback=True` is set on the returned `ModeratorAPIResponse`, and `apply_moderator_response` copies it to `ModeratorLogEntry`, making the substitution visible in `moderator_log.json`.

**Research quality implications:** A fallback turn is AI-moderated in utterance only — the moderator did not exercise genuine judgment. The utterance was not derived from the session state. Any analysis that treats all moderator turns as valid decisions must first filter for `validation_fallback: true` entries. See §15.4.

---

## 15. Research Quality Risks

### 15.1 Feedback Loop Depends on Model Compliance with Typed Schema

The feedback loop (Section 9.1, Step 8) uses three typed fields: `consensus_risk_assessment`, `emotional_signals`, and `new_contradictions`. Pydantic validates types and value ranges on receipt — a float outside [0, 1] or an object missing a required field will reject the response and trigger a retry.

**Remaining compliance risk:** The system prompt instructs the model to provide `consensus_risk_assessment` on every turn, but this is enforced only by instruction — `float | None` accepts `null`. If the model consistently returns `null`, `consensus_risk` will stay at its previous value and injection 1 may never fire. Similarly, the model may under-report emotional signals or contradictions even when present.

**Improvement over the previous approach:** The previous regex-based feedback loop would silently fail if the model used different phrasing (e.g., `"consensus risk is elevated"` instead of `"consensus_risk 0.65"`). The typed approach fails loudly (Pydantic rejects malformed values) rather than silently. The remaining risk is omission (model doesn't populate the field) rather than mis-formatting.

### 15.2 Agent Payload No Longer Exposed to Moderator — But Proxy Information May Still Leak

The direct exposure of psychological dimension names (`masculinity_of_meat`, `vegetarianism_threat`) has been eliminated from the moderator's view. However:
- The `initial_session_plan` stored in `session_meta` contains the moderator's own strategic assessment, which may encode its inferences about participants' profiles
- The `situation_assessment` in each moderator log entry may reflect the moderator's synthesis of participant characteristics
- Both of these are included in the full state JSON sent to the moderator on every turn

### 15.3 Engagement Assessment May Not Reflect Genuine Conversational Urgency

`assess_engagement()` asks the participant model whether it feels compelled to speak. The user message now includes the last 6 transcript entries and a numbered list of this participant's own prior utterances (up to 15). The closing question asks whether there is something genuinely new to add that has not already been said.

**Remaining limitations:**
- `participant_histories` is still not passed — the model does not see the moderator's responses to the participant, the participant's contributions in their full dialogue context, or the back-and-forth flow. It has a flat list of its own prior utterances, not their conversational placement.
- The engagement model and the response model are the same underlying model but operate independently with different contexts. An urgency of 0.8 from `assess_engagement` and the actual response produced by `call_participant` in the same turn are generated by separate API calls with different prompts — there is no guarantee they are consistent.
- An urgency of 0.8 and an urgency of 0.3 from the same model run at different times may not represent meaningfully different levels of conversational readiness. The values are not calibrated against any external standard.
- The question framing ("something that has not already been said") may systematically suppress urgency in later turns when most content has already been covered, potentially silencing participants who would add genuine value through affirmation, elaboration, or emotional resonance rather than novel information.

### 15.4 Direct-Address Floor-Handoff in Emergent Mode

When the moderator addresses a single participant (any action with a resolved single-target), the system bypasses urgency selection and seats that participant regardless of their assessed engagement. This gives the moderator model partial control over turn order in emergent mode, which may reintroduce the orchestrated dynamic that emergent mode was designed to avoid. The addressed participant's behaviour instructions permit a brief or deflecting response.

### 15.5 Persona Faithfulness Is Not Verified

There is no mechanism to verify that participant responses are consistent with their demographic profile, food consumption patterns, or psychological scores. The feedback loop does not cross-check responses against the agent JSON.

### 15.6 Social Desirability in AI Participants

The `_BEHAVIOUR_INSTRUCTIONS` block explicitly instructs participants not to give socially ideal answers, and permits addressing each other by name and staying silent when nothing new to add. These instructions partially counteract RLHF-induced social desirability tendencies but cannot eliminate them. AI-generated "authentic ambivalence" may be systematically different from genuine human ambivalence.

### 15.7 Tension Resolution Requires Repeated Moderator Action

`UnresolvedTension` entries are resolved only after two `reflect_contradiction` actions targeting the same participant (Section 12.8). If the moderator fires the action only once — or not at all — the tension persists and the `unresolved_contradiction_due` injection continues to fire indefinitely. In short sessions this may never reach the two-action threshold, creating a systematic bias toward repeatedly prompting the same participant about the same unresolved contradiction.

### 15.8 No Cross-Session Consistency

Each session is independent. Participant agents start fresh from the agent JSON each session. There is no mechanism to ensure consistent persona expression across multiple runs.

### 15.9 Timestamp Accuracy

Transcript timestamps use `datetime.utcnow()` (naive UTC). Python 3.12+ deprecates `utcnow()`.

### 15.10 Validation Fallback Turns Are Not Genuine Moderation

When `call_moderator` exhausts its two attempts and fires `_build_fallback_response()`, the session continues but the turn is not AI-moderated in any meaningful sense. The utterance ("Let's hear from the group on this — what are your thoughts?") is a fixed string, not derived from the session state, participant responses, or research objective. The `moderator_decision` block reflects system metadata, not real moderator judgment.

**Analysis implication:** Any transcript or moderator log analysis that assumes all turns reflect genuine AI moderation must first filter for `validation_fallback: true` in `moderator_log.json`. A session with one or more fallback turns has a gap in its moderation record at those positions. Whether such a session is usable for research depends on where in the session the fallback occurred and how many fallback turns it contains.

**Detection:** `moderator_log.json` entries include `"validation_fallback": true`. Server log contains `[RESEARCH ALERT] Turn N: Moderator validation fallback fired.` The UI error banner does NOT show this event — the session appears to continue normally from the researcher's perspective.

---

## 16. Appendix A — Pydantic Validation Chain

**When `apply_moderator_response` calls `SessionState.model_validate(state.model_dump())`:**

1. `GroupState.validate_consensus_risk` field validator — rounds `consensus_risk` to 3 decimal places (runs even after feedback loop updates it)
2. `SessionState.validate_participation_balance` model validator — recomputes `participation_balance` from live `turn_count` values

**Before `ModeratorAPIResponse.model_validate()` is called (`_normalize_decision()`):**

0. `_normalize_decision(raw_dict)` — pre-validation normalisation (mutates the dict in place):
   - Null-string coercion: `"null"`, `"none"`, `"n/a"`, `""` → `None` on `probe_type`, `follow_up_intensity`, `queued_next_action`
   - `probe_type` forced to `None` for all actions except `"direct_probe"`
   - `follow_up_intensity` forced to `None` for all actions outside `{direct_probe, reflect_contradiction, synthesize_and_challenge}`

**When `ModeratorAPIResponse.model_validate()` runs:**

1. ~~`ModeratorDecisionResponse.validate_probe_type_consistency`~~ — **removed** (see §12.15); normalization handles this upstream
3. `ModeratorDecisionResponse.validate_follow_up_intensity_consistency` model validator — **silently sets `follow_up_intensity = None`** for non-probe actions. Belt-and-suspenders after normalisation; does NOT raise; does NOT trigger retry.
4. `ModeratorAPIResponse.utterance_strip` field validator — strips whitespace
5. `ModeratorAPIResponse.validate_utterance_by_action` model validator — forces `""` for `stay_silent`; raises `PydanticValidationError` for empty utterance on other actions → triggers retry with schema-specific correction message

**When `ParticipantEngagementAssessment` is constructed:**

1. Pydantic validates `urgency` against `ge=0.0, le=1.0`. If `assess_engagement()` returns a float outside this range, Pydantic raises `ValidationError` which is caught by the `except Exception` block, returning the silent default.

---

## 17. Appendix B — Agent JSON Schema

**Status as of 2026-06-11:** The Twin-2K-500 agent JSON schema (v1, `schema_version: "agents_v1"`)
has been retired along with the 2,058 generated agent files in `agents/twin2k500/`.
The ETL pipeline (`scripts/twin2k500_*.py`) and raw dataset (`data/twin2k500/`) are retained
for auxiliary and sensitivity-analysis use.

The native focus-group agent schema (`schema_version: "fg_agents_v1"`) is documented in
`docs/changes/2026-06-11_twin2k500_agents_retired.md` and will be defined in full once
approved. The renderer (`core/participant_agent.py`) reads from the paths listed in the
visibility matrix below; those paths are unchanged.

**Renderer-read paths (still current after schema transition):**

| Path in agent JSON | Renderer layer | Notes |
|---|---|---|
| `persona.demographics.name` | Layer 1 — identity | REQUIRED by `load_agent_from_json()` |
| `persona.demographics.age` | Layer 1 — identity | Now `int \| None`; omitted from prompt when null |
| `persona.demographics.gender` | Layer 1 — identity | Now `str \| None`; omitted from prompt when null |
| `persona.demographics.location.*` | Layer 1 — identity | Optional |
| `persona.demographics.diet` | Layer 1 — identity | Optional |
| `persona.food_consumption` | Layer 2 — consumption | Optional; any key→value pairs |
| `persona.psychological_profile` | Layer 3 — attitudes | Optional; score→instruction translation. **Not used by focus-group agents** — psychometric scores stored in `psychometric_scores` block instead |
| `simulation_config.notes` | Layer 4 — context | Optional |
| `opening_intro.text` | Intro gate | Injected only when `session_meta.inject_participant_intro=true` and `opening_intro.intro_eligible=true` |

**Visibility matrix (unchanged):**

| Data | Moderator sees | Participant prompt | assess_engagement |
|------|---------------|-------------------|-------------------|
| `agent_id` | No | No (becomes `ParticipantState.id`) | No |
| `demographics` | No (stripped from state JSON) | Yes — Layer 1 | Partial (name, age, gender, location, diet) |
| `food_consumption` | No | Yes — Layer 2 | No |
| `psychological_profile` | No | Yes — Layer 3 (focus-group agents: not used) | No |
| `psychometric_scores` | No | No (stored for analysis only) | No |
| `study_context` | No | No (stored for analysis only) | No |
| `opening_intro.text` | No | Yes — when toggle on | No |
| `simulation_config.notes` | No | Yes — Layer 4 | No |
| `simulation_config.model` | No | Used for API call | Used for API call |
| `simulation_config.max_tokens` | No | Used for API call | Ignored (hardcoded 250) |

## 18. Model B Validation & Smoke Test Findings (May 2026)

During the final validation phase of the Model B (Group Discussion) architecture, a comprehensive automated test suite was constructed (	ests/test_model_b_grocery.py) to verify the systemic robustness of the emergent turn-taking, consensus risk modifiers, and moderator discretization fail-safes.

**Verified Capabilities:**
1. **Emergent Turn Resolution:** The ssess_engagement urgency algorithms, including the PEER_ADDRESS_BONUS, are fully operational and correctly assign speaking turns.
1. **Emergent Turn Resolution:** The assess_engagement urgency algorithms, including the PEER_ADDRESS_BONUS, are fully operational and correctly assign speaking turns.
2. **Consensus Breakers:** The system successfully detects high consensus_risk (>0.60) and awards the CONSENSUS_RISK_CHALLENGE_PREFERENCE to participants with a "challenge" intent, successfully interrupting synthetic echo chambers.
3. **Discretionary Observation:** The intervention_mode="observe" response successfully bypasses transcript injection while preserving internal moderator states in the moderator_log.json.
4. **Validation Fail-safes:** The moderator_brain successfully intercepts Pydantic JSON validation errors (such as malformed tool payloads or structural omissions) and builds a safe fallback (intervention_mode="observe"). 

**Identified Architecture Quirks and Problems:**
1. **Mocking/Validation Disconnects:** During unit testing, we identified that Pydantic's strict tuple unfolding and the internal _call_api structure required careful handling of fallback structures. Fallback interventions default to observe and action=None, completely bypassing the moderator turn rather than forcing a clumsy intervention as originally hypothesized. 
2. **Double AI Call Drift:** An architectural reality of Model B is that assess_engagement and run_participant_turn are two distinct LLM calls for the same participant in the same turn. While assess_engagement may output high urgency and "intent": "challenge", there is no programmatic guarantee that the subsequent generative API call (run_participant_turn) actually issues a challenging statement. This drift introduces minor unpredictability into the simulation.

## 19. Assessment and Audit Hardening

The assessment pipeline is designed to rigorously evaluate and calibrate both human baselines and synthetic generation artifacts. Two critical metrics and gating mechanisms are implemented to ensure pipeline integrity:

### 19.1 Participant-to-Participant Edge Density

The `participant_to_participant_edge_density` metric (calculated in `assessment/interaction_graph.py`) quantifies the rate of cross-talk between participants, strictly excluding the moderator.

*   **Logic:** A participant-to-participant edge is defined as either (a) consecutive non-moderator turns (adjacent uptake) or (b) an explicit reference by one participant to another.
*   **Denominator:** The metric scales to a theoretical maximum using the total possible directed edges between `n` participants, defined as `n * (n - 1)`.
*   **Classification:** Because this metric is output directly by the `interaction_graph.py` pipeline, it matches exactly against expected generator output and acts as a `MAPPED_EXACT` metric during synthetic vs. human backtesting. The assessment reporting (`assessment/synthetic_backtest_human_calibration.py`) explicitly labels related unmapped outputs as `CALIBRATION_REFERENCE`.

### 19.2 Human Baseline Calibration Gate (Stage 7C.5)

The script `assessment/human_baseline_calibration.py` calibrates human baseline metrics and defines thresholds. To ensure the process is robust, strict per-baseline reconciliation has been added:

*   **Reconciliation Requirements:** The gate verifies that the baseline ID set precisely matches across the `transcripts` input and the `assessments` output. It also verifies that the `turn_count` for each corresponding baseline identically matches across both locations.
*   **Failure Modes:** If any mismatch occurs, the calibration gate emits a `BLOCKED` status, logs the specific discrepancies in the `blocking_issues` list, and writes a diagnostic CSV (`per_baseline_reconciliation_table.csv`).
*   **Enforcement:** This mechanism stops downstream comparisons of synthetic outputs against flawed human calibrations.

### 19.3 UI Work Paused

All frontend and backend presentation-layer development (Results Viewer, dashboard routing, etc.) is formally paused in favor of rigid pipeline validations and audit hardening.

### 19.4 Stage 7C.5 Current Verdict and Evidence

**Verdict:** COMPLETE
Stage 7C.5 enforces exact, per-baseline turn and ID reconciliation between input transcripts and generated assessments. 
**Caveat:** This is a process calibration only. It does not assess outcome validity, theme equivalence, or substantive quality. Thresholds derived from the human sample (n=7) remain soft, provisional process reference ranges.

### 19.5 Stage 7C.6 Current Verdict and Evidence

**Verdict:** COMPLETE
Stage 7C.6 executes the synthetic backtest and ensures derived interaction graph metrics (like `participant_to_participant_edge_density`) natively match expected `CALIBRATION_REFERENCE` inputs. All stale backlog constraints have been cleared.
**Caveat:** As with 7C.5, this is strictly a process alignment test and not a validation of synthetic conversational content.


### 19.6 Stage 7D Assessment Readiness Gate

**Verdict:** READY_FOR_STAGE_8A
Stage 7D acts as a structural contract and readiness gate. It establishes the required artifacts, metric registry, and corpus comparison manifests to move out of Stage 7C calibration.

**New Assessment Artifacts Created:**
* docs/testing/stage7d_assessment_readiness_gate/assessment_artifact_manifest.csv (and .md)
* docs/testing/stage7d_assessment_readiness_gate/assessment_metric_registry.csv (and .md)
* docs/testing/stage7d_assessment_readiness_gate/corpus_comparison_manifest.csv (and .md)
* docs/testing/stage7d_assessment_readiness_gate/ASSESSMENT_STAGE_ROADMAP.md
* docs/testing/stage7d_assessment_readiness_gate/STAGE7D_ASSESSMENT_READINESS_GATE_REPORT.md

**Current Status and Known Limitations:**
* Stages 7C.5 and 7C.6 are formally closed as **COMPLETE**. However, they are **process and audit calibrations only**.
* Stage 7D is a readiness gate, **not** a validity stage. The project is **READY_FOR_STAGE_8A** (Smoke Test Scorecard).
* **Missing Artifacts:** None required for process calibration. (State snapshots and explicit participant definitions are optional).
* **Caveat:** The project is **not yet allowed** to claim synthetic focus groups are equivalent to human focus groups, nor can it claim thematic equivalence or outcome validity. Stage 8A may proceed **only as a diagnostic smoke test**.
* UI work remains strictly paused.



### 19.7 Stage 8A Smoke Test Scorecard

**Verdict:** PARTIAL_READY
Stage 8A is a diagnostic smoke test designed to detect obvious or catastrophic quality failures in synthetic focus group outputs before deeper validity or thematic-equivalence stages are attempted.

**New Assessment Artifacts Created:**
* docs/testing/stage8a_smoke_test_scorecard/smoke_test_scorecard.csv (and .md)
* docs/testing/stage8a_smoke_test_scorecard/run_level_smoke_summary.csv (and .md)
* docs/testing/stage8a_smoke_test_scorecard/smoke_test_artifact_issue_log.csv
* docs/testing/stage8a_smoke_test_scorecard/smoke_test_thresholds.json (and .md)
* docs/testing/stage8a_smoke_test_scorecard/STAGE8A_SMOKE_TEST_SCORECARD_REPORT.md

**Current Status and Known Limitations:**
* **PARTIAL_READY**: Stage 8A reveals no blocking artifacts, but minor AMBER review items (e.g. low turn counts in stage6f_internal_reasoning_calibration_verification_01) exist.
* Stage 7C.5 and 7C.6 remain closed as process and audit calibrations only.
* Stage 7D remains the assessment readiness gate.
* **Caveat:** The project is **not** claiming synthetic focus groups are equivalent to human focus groups. It is **not** claiming thematic equivalence or outcome validity. GREEN diagnostics do not mean validated.
* UI work remains strictly paused.



**Limitations:**
This is purely an infrastructure and prompt-render audit. It does **not** validate human-likeness, thematic equivalence, outcome validity, or research quality. The goal was strictly run feasibility and traceability.

**Next Action:**
A manual review of the captured transcript and prompt-render text files is recommended to evaluate how the claude-sonnet-4-6 model behaves under these prompts.

### 19.8 Macho Meals Emergent Run Validation and Resolution (2026-06-24)

The synthetic-human evaluation pipeline (Stage 8B onwards) was paused to perform a strict feasibility validation on the macho_meals_plant_based_masculinity_uk focus group guide and the mm_fg1_ participant agent set using claude-sonnet-4-6. The user explicitly approved the inclusion of all 5 matching agents (Amir, David, Ibrahim, Isaiah, Will) instead of enforcing a 4-agent limit.

During initial testing (macho_meals_emergent_full_run_01), we discovered that network errors (specifically getaddrinfo DNS failures on API calls at turn 12) were being improperly masked by residual state files in the canonical log directory, leading to false completion reports.

To prevent this class of failure, we instituted a **strict disk-based reporting requirement**:
1. Every evaluation run must use a strictly unique session ID (e.g., macho_meals_emergent_full_run_02).
2. The alidate_macho_meals_emergent.py script must clear all stale testing mirrors before running.
3. The final report must be generated *exclusively* from disk-persisted artifacts, directly comparing 	ranscript.json and 	ranscript.txt turn lengths against the expected values.
4. If a run terminates prematurely, the verdict must be LIVE_RUN_FAILED or LIVE_RUN_INCOMPLETE_GUIDE_NOT_CLOSED.

**Resolution (macho_meals_emergent_full_run_02)**
Following these strict safeguards, the full focus group was rerun under session ID macho_meals_emergent_full_run_02.
The discussion successfully progressed to completion over 45 state turns, reaching and completing the final guide section ("Closing remarks"). The generated transcripts (	ranscript.json, 	ranscript.txt) were successfully flushed to disk and mirrored to the testing directories. 

**Key Validation Outcomes:**
1. **Network Stability:** The claude-sonnet-4-6 configuration successfully completed the multi-agent orchestration loop (~200 sequential API calls) without DNS timeouts.

## Documentation Map

- **ARCHITECTURE.md**: High-level technical architecture, logic goals, and historical decisions.
- **docs/system_operation/**: The primary runbook for understanding live session behavior, tracking exactly what happens during execution.
- **docs/testing/**: Audit outputs, performance reports, and historical run artifacts.

**Note on System Operation Documentation:**
A rigorous operational documentation package exists in `docs/system_operation/`. It is the primary runbook for understanding live session behavior. `ARCHITECTURE.md` remains the high-level technical audit document. Discrepancies between the original architecture goals and the actual current implementation are tracked in `docs/system_operation/CODE_ARCHITECTURE_CONSISTENCY_AUDIT.md`. Currently, verbosity controls have not been altered, and qualitative evaluation (Stage 8B) remains paused while structural validation concludes. No claims regarding human-likeness validation, thematic equivalence, or outcome validity are made at this time.

2. **Guide Flow:** The Moderator agent successfully advanced through all six sections of the Macho Meals guide based entirely on emergent conversation dynamics, ending the session organically.
3. **Audit Trails:** All API call configurations and prompt audits were accurately saved to their respective directories.
4. **Verdicts:** The strict validation test suite passed all assertions (LIVE_RUN_COMPLETED_CLEAN).

**Limitations:**
This is purely an infrastructure and prompt-render audit. It does **not** validate human-likeness, thematic equivalence, outcome validity, or research quality. The goal was strictly run feasibility and traceability. The structural evaluation of the emergent pipeline is complete. The next step is a **Manual Qualitative Review** of the captured artifact (the simulated transcript) to assess human-likeness and thematic robustness.
