# Prompt Architecture — README
# File: prompts/00_README.md

---

## Overview

This directory contains four prompt files that together constitute the full system prompt
architecture for the AI focus group moderator. They are designed to work as a layered system,
not as standalone prompts.

---

## File Map

| File | Role | Changes during session? | Passed as |
|---|---|---|---|
| `01_MODERATOR_SYSTEM_PROMPT.md` | Permanent identity, philosophy, action vocabulary, language rules | Never | `system` parameter |
| `02_USER_MESSAGE_TEMPLATE.md` | Dynamic per-turn wrapper that injects session state | Every turn | `messages[-1]` (user role) |
| `03_SESSION_OPENING_PROMPT.md` | First-turn only: initialise session plan + produce welcome | Once, at session start | `messages[-1]` (user role) |
| `04_PHASE_MODIFIERS_AND_SPECIAL_CASES.md` | Condition-triggered injections appended to user message | When conditions are met | Appended to `02` |

---

## How a Turn is Constructed

### Turn 0 (Session Start)

```python
messages = [
    {
        "role": "user",
        "content": render_template("03_SESSION_OPENING_PROMPT.md", {
            "SESSION_CONFIG": session_config_json
        })
    }
]

response = anthropic_client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1500,
    system=load_file("01_MODERATOR_SYSTEM_PROMPT.md"),
    messages=messages
)
```

### Turns 1+ (Every Subsequent Turn)

```python
# 1. Determine active special-case injections
injections = []
if session_state["group_state"]["consensus_risk"] >= 0.65:
    injections.append(render_injection("consensus_risk", session_state))
if has_participation_imbalance(session_state):
    injections.append(render_injection("participation_imbalance", session_state))
# ... etc

# 2. Build the user message
user_message = render_template("02_USER_MESSAGE_TEMPLATE.md", {
    "SESSION_STATE": json.dumps(session_state, indent=2),
    "TRIGGER_EVENT": json.dumps(trigger_event, indent=2),
    "FOLLOW_UP_COUNT": follow_up_count,
    "SECTION_PHASE": session_state["session_meta"]["section_phase"],
    "PHASE_MODIFIER": get_phase_modifier(session_state["session_meta"]["section_phase"]),
})
user_message += "\n\n".join(injections)

# 3. Build messages array — FULL HISTORY for context
# The conversation history IS the context window — do not truncate
messages = conversation_history + [{"role": "user", "content": user_message}]

# 4. Call the API
response = anthropic_client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1500,
    system=load_file("01_MODERATOR_SYSTEM_PROMPT.md"),
    messages=messages
)

# 5. Parse the decision JSON from the response
decision = json.loads(response.content[0].text)

# 6. Update session state from decision
update_session_state(session_state, decision, trigger_event)

# 7. Append to conversation history
conversation_history.append({"role": "user", "content": user_message})
conversation_history.append({"role": "assistant", "content": response.content[0].text})
```

---

## Key Architectural Principles

### Why the system prompt never changes
The system prompt is the moderator's stable identity and capability set. It must be completely
consistent across all turns so the model doesn't receive contradictory instructions.
Everything that changes belongs in the user message.

### Why the full session state is injected every turn
The model has no persistent memory between API calls. The session state JSON is the memory.
Every turn gets the full picture so the model can reason from complete context — this is the
core advantage over one-shot prompting.

### Why the decision JSON comes before the utterance
Forcing the model to complete the reasoning block before generating the utterance ensures
that the utterance is actually driven by a reasoning process. Without this ordering,
the model tends to generate a fluent utterance and then rationalise it in the decision block —
which defeats the purpose of the internal audit trail.

### Why phase modifiers are injected rather than baked in
The system prompt can't know what phase you're in. Phase modifiers let the same permanent
identity adjust its behaviour based on the current section without duplicating the whole
system prompt for each phase. They also make it easy to add new phases (e.g. a debrief phase)
without touching the core system prompt.

### Why special-case injections are separate
Conditions like consensus_risk, participation_imbalance, and conflict are not predictable
in advance. They need to fire exactly when detected and not fire when not needed.
Baking them into the phase modifier would fire them constantly regardless of state.

---

## Session State Update Logic (orchestrator responsibility)

After each moderator API call, the orchestrator must update these fields:

```python
def update_session_state(state: dict, decision: dict, trigger_event: dict) -> None:

    # 1. Increment participant turn count
    if trigger_event["speaker_id"]:
        pid = trigger_event["speaker_id"]
        state["participants"][pid]["turn_count"] += 1

    # 2. Update participation balance
    total_turns = sum(p["turn_count"] for p in state["participants"].values())
    for pid, p in state["participants"].items():
        state["group_state"]["participation_balance"][pid] = p["turn_count"] / total_turns

    # 3. Update silent_participants list
    avg = total_turns / len(state["participants"])
    state["group_state"]["silent_participants"] = [
        pid for pid, p in state["participants"].items()
        if p["turn_count"] / total_turns < 0.15 and state["session_meta"]["section_phase"] != "intro"
    ]

    # 4. Append to moderator_log
    state["moderator_log"].append({
        "turn": trigger_event["turn_number"],
        "trigger": decision["moderator_decision"]["dominant_signal"],
        "situation_assessment": decision["moderator_decision"]["situation_assessment"],
        "action": decision["moderator_decision"]["action"],
        "target": decision["moderator_decision"]["target"],
        "utterance": decision["utterance"]
    })

    # 5. Handle section transition
    if decision["moderator_decision"]["action"] == "section_transition":
        state["session_meta"]["current_section_index"] += 1
        state["session_meta"]["section_phase"] = get_next_phase(state)
        state["session_meta"]["current_question_index"] = 0

    # 6. Consensus risk: recalculate externally or let model flag it
    # (Your orchestrator can compute this via embedding similarity of recent responses
    #  or accept the model's own consensus_risk_assessment)
```

---

## Conversation History Management

For long sessions (60+ turns), the raw conversation history may approach context window limits.
When this happens, compress older turns by replacing detailed moderator_decision blocks
with a summarised entry, while keeping the utterance and the participant response intact.

Do NOT compress:
- The 10 most recent turns (full fidelity)
- Any turn containing a flagged contradiction or tension that is unresolved
- Any turn where a section transition occurred

DO compress (to summary):
- Earlier turns where the moderator_decision reasoning is no longer actionable
- Keep: turn number, action, target, utterance, participant response
- Drop: full situation_assessment prose from old turns

This preserves the transcript while managing token usage.
