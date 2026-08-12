# Emergent Mode Mechanics

This document focuses on the execution of the emergent mode loop, detailing engagement assessment, urgency scoring, participant self-selection, and fallback logic. It grounds all claims in the actual implementation (`core/orchestrator.py` and `core/participant_agent.py`).

## 1. Overview of Emergent Step

The emergent mode logic is driven by the `run_conversation_step()` function in `core/orchestrator.py`. Instead of the moderator calling on participants sequentially, participants self-select based on categorical intents and calculated urgency.

**File/Function Reference:** `core/orchestrator.py:run_conversation_step()`

## 2. Engagement Assessment

At the start of each emergent step, the orchestrator loops over all participants and invokes `assess_engagement()`.

**File/Function Reference:** `core/participant_agent.py:assess_engagement()`

- **What the Participant Sees:** The participant receives their profile summary, the recent transcript (last 6 entries), and a history of their own past utterances.
- **Model Call:** A lightweight model call (defaulting to a fast model unless specified in the simulation config) is made with a JSON-only prompt.
- **Returned JSON:** The model returns a `ParticipantEngagementAssessment` containing:
  - `wants_to_speak`: boolean
  - `urgency`: float (0.0 to 1.0)
  - `hook`: string (what they want to say)
  - `addressed_to`: name of specific participant (or null)
  - `intent`: categorical string (`respond`, `challenge`, `affirm_and_elaborate`, `introduce_new_angle`, `stay_silent`)

### Failure Handling
If the API call fails, the JSON fails to parse, or Pydantic validation fails, the code defaults to a `stay_silent` intent with `urgency=0.0`. This ensures a single failed assessment does not crash the session.

## 3. Urgency Scoring and Contextual Bonuses

Once all assessments are collected, `run_conversation_step()` dynamically adjusts the raw urgency scores to factor in conversation context.

**File/Function Reference:** `core/orchestrator.py:run_conversation_step()`

- **Peer Address Bonus:** If the last speaker explicitly addressed this participant, they receive a bonus (`PEER_ADDRESS_BONUS`).
- **Moderator Invite Bonus:** If the moderator's last action was `INVITE_TO_SPEAK` targeting this participant, they receive a bonus (`MODERATOR_INVITE_BONUS`).
- **Consensus Risk Preference:** If the group consensus risk is high (>= 0.65) and the participant's intent is `challenge`, they receive a bonus (`CONSENSUS_RISK_CHALLENGE_PREFERENCE`).

The final urgency is capped at 1.0.

## 4. Participant Self-Selection and Thresholds

After bonuses are applied, the code selects the next speaker:

1. **Filtering:** Participants are filtered to those where `wants_to_speak` is true, `intent` is not `stay_silent`, and `urgency >= URGENCY_THRESHOLD`.
2. **Sorting:** Eligible participants are sorted descending by `urgency`, and ties are broken by `turn_count` (participants with fewer turns are prioritized).
3. **Selection:** The top participant is chosen.

### Silence Fallback
If no participant meets the `URGENCY_THRESHOLD`:
- The system checks `self.state.group_state.consecutive_silent_turns`.
- If there have been 2 or more consecutive silent turns, the threshold is lowered. The system looks for any participant with an intent other than `stay_silent` and an urgency > 0.2.
- If still nobody is eligible, a "Silence or Forced Trigger" is passed to the moderator (`TriggerEventType.SILENCE_DETECTED`), forcing the moderator to speak.

### Consecutive Turns Limit
To prevent a single participant from monologuing, the system checks `MAX_CONSECUTIVE_PARTICIPANT_TURNS`. If a participant volunteers but the max limit has been reached, their selection is overridden. The system nullifies the participant selection and forces moderator intervention (`selection_mode = "moderator_forced_by_consecutive_turns"`).

## 5. Participant Response Generation

If a participant is selected, `run_participant_turn()` is invoked.

**File/Function Reference:** `core/orchestrator.py:run_participant_turn()` calling `core/participant_agent.py:call_participant()`

- The participant's motivation (`hook`) is passed to the generation prompt to anchor their response to their earlier assessment.
- A full text response is generated via `claude-sonnet-4-6` (as configured in the Macho Meals agent payloads).
- The text is appended to the transcript.

## 6. API Call Volume and Costs

Because every emergent step requires an engagement assessment for *every* participant, the number of API calls per step scales linearly with the group size.
- **Assessments:** N calls (where N = number of participants) per step.
- **Generation:** 1 call for the selected participant (or 0 if silent).
- **Moderator:** 1 call (with possible 1 retry).

In the Macho Meals run (5 agents), each participant step required 5 assessment calls + 1 generation call + 1 moderator call = 7 API calls. A full session of ~50 turns results in hundreds of API calls.

## 7. Code vs Model Boundary Summary

- **Deterministic Code:** Applying contextual bonuses, sorting by urgency, enforcing the `URGENCY_THRESHOLD`, falling back to lower thresholds, enforcing `MAX_CONSECUTIVE_PARTICIPANT_TURNS`, generating the silence trigger, substituting default values on validation failures.
- **Model-Decided:** The raw `urgency` score, `wants_to_speak` boolean, `intent`, the text of the `hook`, the name of the peer being addressed, and the final spoken utterance.
- **Mixed:** Next speaker selection (model provides scores, but code applies rules and limits).

*Disclaimer: Model decisions are inferred from structured outputs and prompts; private chain-of-thought is not captured or exposed.*
