# Dynamic User Message Template
# File: prompts/02_USER_MESSAGE_TEMPLATE.md
#
# Usage: This is the USER message sent on EVERY turn.
#        It is constructed programmatically by orchestrator.py.
#        The system prompt (01) never changes; this changes on every turn.
#        It carries the full session state so the model has complete context.
#
# In Python: rendered via a Jinja2 template or f-string substitution.
# The full session_state dict is serialised to JSON and injected at the SESSION_STATE placeholder below.
# The trigger_event dict is injected at the TRIGGER_EVENT placeholder below.

---

## CURRENT SESSION STATE

The following JSON object represents the complete current state of this focus group session. Read it in full before producing your decision.

*Key group dynamic fields to monitor in the state:*
- `group_has_agreed_easily_on`: Topics where the group converged without sufficient tension.
- `current_question_index`: The index of the current question in the discussion guide.
- `consecutive_participant_turns`: How many times participants have spoken without your intervention.

```json
{SESSION_STATE}
```

---

## WHAT JUST HAPPENED

```json
{TRIGGER_EVENT}
```

The `trigger_event` object will always contain:

```json
{
  "type": "participant_response | session_start | stimulus_presented | silence_detected",
  "speaker_id": "P1 | null",
  "speaker_name": "...",
  "content": "The raw text of what was just said, or a description of what happened.",
  "turn_number": 12,
  "follow_up_count_this_question": 2
}
```

---

## YOUR TASK

Read the session state and the trigger event carefully. Then produce your response in the following JSON structure and nothing else. Do not add explanatory prose outside the JSON block.

```json
{
  "moderator_decision": {
    "situation_assessment": "Relative to the current section's guide question, assess whether the recent contributions are answering it (directly or by building on someone's answer), whether they add useful and novel information about it, or whether they have drifted to the general topic / are repeating. State what the discussion needs next. This assessment is the basis for your intervention_mode.",

    "intervention_mode": "observe | yield | speak",

    "dominant_signal": "The single most important signal driving your next action. Choose from: [response_needs_probing | participation_imbalance | consensus_risk | contradiction_pending | section_complete | emotional_register | guide_question_pending | silence_detected | conflict_detected]",

    "action": "One of the typed actions from your action vocabulary.",

    "target": "participant_id if targeting one person, or 'group' if addressing everyone.",

    "probe_type": null,

    "follow_up_intensity": null,

    "queued_next_action": null,

    "new_easy_agreements": [
      "Any topics the group converged on without tension this turn."
    ]
  },

  "utterance": "The exact words you will say in the session. This must be natural, conversational, and consistent with the language and register rules in your system prompt. Do not include moderation meta-commentary (e.g. do not say 'as your moderator' or 'I'd like to probe that'). Just speak."
}
```

**Field instructions for nullable fields — use JSON `null` (not the string `"null"`):**

**`probe_type`** — No longer used to classify probes. Always set to JSON `null`, for `direct_probe` as for every other action.

```json
"action": "direct_probe",
"probe_type": null,
"follow_up_intensity": "medium"
```

```json
"action": "redirect_to_group",
"probe_type": null,
"follow_up_intensity": null
```

**`follow_up_intensity`** — Set to `"light"`, `"medium"`, or `"deep"` when `action` is `"direct_probe"`, `"reflect_contradiction"`, or `"synthesize_and_challenge"`. Set to JSON `null` for all other actions.

**`queued_next_action`** — Set to the object when you want to plan ahead. Set to JSON `null` when you have no queued plan. If you provide the object, all four fields are required:

```json
"queued_next_action": {
  "action": "direct_probe",
  "target": "P2",
  "rationale": "P2 gave a vague reference — worth following up after the group responds.",
  "condition": "P2 does not volunteer more in the next turn."
}
```

```json
"queued_next_action": null
```

---

## CONSTRAINTS ON THIS TURN

- The current section phase is `{SECTION_PHASE}`.
- {SECTION_BUDGET_STATUS}
{PHASE_MODIFIER}
- If `dominant_signal` is `participation_imbalance`, weigh `reactivate_silent` against whether the group is still actively working through the current guide question — see your `reactivate_silent` guidance in the system prompt. It is not an automatic override of a planned action.
- Produce valid JSON only. No markdown, no prose outside the JSON block.
