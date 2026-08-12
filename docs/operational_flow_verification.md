# Operational Flow Verification — Evidence Appendix

> **Note:** This is the evidence appendix for `docs/operational_flow.md`, which is the authoritative operational reference. The verification findings here have been folded into that document as `[observed]`, `[static]`, and `[dormant]` status tags. This file is retained as a dated historical record of the verification evidence.

**Verified against:** `docs/operational_flow.md`
**Date:** 2026-06-25 (original); 2026-06-26 (multi-target check appended)
**Methods:** (1) Static call-graph trace from `run_session.py` through emergent path; (2) Instrumented 25-step live run.

---

## 1. Status Table

### Anomaly Claims (Section 12 of `operational_flow.md`)

| # | Claim | Status | Method | Evidence |
|---|-------|--------|--------|----------|
| A1 | `record_participant_utterance` called inside `run_moderator_turn`, not `run_participant_turn`, producing shared turn numbers | **Confirmed** | Static + Live | Static: only call site is `orchestrator.py:326` inside `run_moderator_turn`. `run_participant_turn` (lines 274–304) has no call to it. Live: transcript shows shared turn numbers (e.g. turn 6: Sam + Moderator; turn 7: Isaiah + Moderator; turn 8: Will + Moderator). |
| A2 | Turn-number gaps in transcript (e.g. 1 → 3, no turn 2) | **Confirmed** | Live | Transcript jumps from turn 1 (Moderator opening) to turn 3 (David). Turn 2 was consumed by a moderator `observe` (no visible utterance). |
| A3 | No `next_speaker` field in `ModeratorDecisionResponse` | **Confirmed** | Static | Grep for `next_speaker` in `core/session_state.py` returned zero matches. No such field, no such validator. |
| A4 | `_get_requested_next_speaker` defined but never called on emergent path | **Confirmed** | Static | Defined at `orchestrator.py:447`. Grep for `_get_requested_next_speaker` in the entire `core/` directory shows only the definition line — zero call sites. `run_conversation_step()` (lines 456–577) does not reference it. |
| A5 | Moderator-directed selection is a soft +0.15 bonus, not a hard override | **Confirmed** | Static + Live | Static: `orchestrator.py:500–502` applies `MODERATOR_INVITE_BONUS` (0.15 from `config.py:5`) as an urgency bump, not a forced selection. Live: at turn 19, moderator fired `invite_to_speak` targeting Will. At turn 20, Will's post-bonus urgency was 0.800 (plausibly 0.65 raw + 0.15 bonus), Will was selected `voluntary`. The invite did not bypass urgency-based selection — it boosted urgency within it. |
| A6 | `psychological_profile` render path unreachable (removed) | **Confirmed** | Static | The Layer 3 render block was removed from `build_participant_system_prompt()`. The only reference to `psychological_profile` in `participant_agent.py` is in the generic-fallback skip list (line 178). `_score_to_instruction` (lines 78–96) is dead code — no caller exists. |
| A7 | No "2–5 sentences" instruction in `_BEHAVIOUR_INSTRUCTIONS` | **Confirmed** | Static | Grep for "2.5 sentences", "2-5 sentences", "Keep your response" (case-insensitive) across all files in `core/` returned zero matches. |
| A8 | "Never populated" fields ARE populated at runtime | **Confirmed** | Live | Final state (turn 18): `last_response_quality` set (David=adequate, Isaiah=adequate, Sam=rich, Will=adequate); `engagement_signal` set (all=active); `topics_covered` populated (David=3, Isaiah=14, Sam=9, Will=9); `emergent_themes`=23 entries; `easy_agreements`=2 entries. Code paths at `session_state.py:636–643` and `683–688` populate these from the moderator's decision. |
| A9 | Opening-turn validation fallback (truncated JSON at 1500 max_tokens) | **Confirmed** | Live | Live run reproduced the same failure: two parse errors ("Unterminated string starting at..."), then `[RESEARCH ALERT] Turn 0: Moderator validation fallback fired`. The opening welcome came from the next call (turn 1, `ask_initial_to_group`). |
| A10 | Phase modifiers and conflict injection DO fire (contra stale ARCHITECTURE claims) | **Confirmed** | Static | `{PHASE_MODIFIER}` placeholder exists in `02_USER_MESSAGE_TEMPLATE.md`. `render_turn_message` substitutes it (`prompt_renderer.py:211`). The `### \`conflict_detected\`` header is parseable by `_parse_phase_modifiers`. |
| A11 | `run_session.py` exit code 1 after successful session completion | **Confirmed** | Live | The session completed all 25 steps and wrote transcript/moderator_log/state files. Exit code 1 was caused by `run_session.py:134–135`: `entry.action.value` raises `AttributeError` when `action` is `None` (observe/yield turns). The session data is intact; only the summary statistics printing crashed. |

### Hardcoded vs Model-Decided Claims (Section 9 of `operational_flow.md`)

| # | Decision point | Claimed determination | Status | Evidence |
|---|----------------|----------------------|--------|----------|
| H1 | Who speaks next (emergent) | Code sorting on model-produced urgency | **Confirmed** | Static: `orchestrator.py:514–521` — filter `urgency >= 0.55`, sort `(-urgency, turn_count)`. Live: turn 8 had David 0.650, Sam 0.650, Will 0.700 → Will selected (highest urgency). |
| H2 | Urgency threshold = 0.55 | Code (`config.py:3`) | **Confirmed** | Static: `URGENCY_THRESHOLD: Final[float] = 0.55`. Live: all selections were `voluntary` (above threshold). |
| H3 | Bonuses: peer +0.15, invite +0.15, challenge +0.10, cap 0.30 | Code | **Confirmed (static), Invite confirmed (live)** | Static: `config.py:4–6`, applied at `orchestrator.py:493–510`, cap at line 505 (`min(bonus, 2*0.15)`). Live: invite bonus confirmed (Will 0.800 after +0.15 invite, selected at turn 20). Peer and challenge bonuses not exercised in this run. |
| H4 | Lowered bar: >0.2 after 2 consecutive silent turns | Code | **Not exercised** | Static: `orchestrator.py:526–534`. Live: max consecutive observe/yield was 3, but no turn triggered the lowered-bar path (all steps had at least one willing participant). |
| H5 | Max consecutive participant turns = 6 → moderator forced | Code | **Not exercised** | Static: `config.py:7`, gate at `orchestrator.py:537`. Live: max consecutive observe/yield was 3 (well below 6). |
| H6 | Tie-break: lowest turn_count | Code | **Confirmed** | Static: sort key `(-a.urgency, self.state.participants[a.participant_id].turn_count)` at line 521. Live: at turn 8, David (tc=1) and Sam (tc=1) tied at 0.650; Will won at 0.700 so tie-break wasn't needed, but the sort order is confirmed. |
| H7 | Moderator temperature hardcoded 1.0 | Code | **Confirmed** | Static: `moderator_brain.py:60` — `temperature=1.0` in `_call_api`. Not read from `session_meta.temperature`. |
| H8 | Participant temperature from config | Config | **Confirmed** | Static: `participant_agent.py:544` — `temperature = session_meta.temperature`. |
| H9 | Moderator model hardcoded | Code | **Confirmed + finding** | Static: `moderator_brain.py:26` — `_MODEL = "claude-sonnet-4-20250514"`. Live: this model returned HTTP 404 ("model: claude-sonnet-4-20250514" not found). Patched to `claude-sonnet-4-6` for the live run (see Section 2). |
| H10 | Participant model from agent JSON | Agent JSON | **Confirmed** | Static: `participant_agent.py:537` — `model = sim_cfg.get("model", _DEFAULT_MODEL)`. Live: `api_calls.jsonl` shows `participant_engagement_assessment` and `participant_response_generation` both used `claude-haiku-4-5-20251001` (from agent files). |
| H11 | Moderator max_tokens = 1500 | Code | **Confirmed** | Static: `moderator_brain.py:27`. Live: opening truncation consistent with 1500-token ceiling. |
| H12 | Participant max_tokens = 400 (default) | Code/agent JSON | **Confirmed** | Static: `participant_agent.py:21` (`_DEFAULT_MAX_TOKENS = 400`), overridable by `session_meta.participant_response_max_tokens` (line 538). Live: `api_calls.jsonl` confirms `max_tokens=400`. |
| H13 | Engagement max_tokens = 250 | Code | **Confirmed** | Static: `participant_agent.py:371`. Live: `api_calls.jsonl` engagement entries show `max_tokens` not logged separately, but all engagement calls completed within budget. |
| H14 | Session ends at fixed step count (run_session.py) | Code | **Confirmed** | Live: `--turns 25` ran exactly 25 steps (turns 0–26 including opening+fallback). |
| H15 | Section transition model-decided | Model | **Confirmed** | Live: section transitions at turns 8, 14, 23 — all `action=section_transition` in moderator log. No code forced them. |
| H16 | Section depth ≥3 is prompt-only, not code-enforced | Model (prompt) | **Confirmed** | Live: section transitions occurred after 5, 5, and 8 participant turns respectively (all ≥3). The code has no minimum-turn guard before `section_transition` — the moderator chose to wait. |
| H17 | Silent-participant flag: <15% of total turns | Code | **Confirmed** | Static: `session_state.py:652–667`. Live: moderator fired `reactivate_silent` 4 times (turns 6, 7, 12, 13) when Isaiah and Will fell below 15%. |
| H18 | Retry count: exactly 1 retry then fallback | Code | **Confirmed** | Static: `moderator_brain.py:213–268`. Live: turn 0 had 1 attempt + 1 retry → fallback. `api_calls.jsonl` shows `moderator_decision_attempt` (1) + `moderator_decision_retry_attempt` (1) + `moderator_decision_fallback` (1). |

---

## 2. Resolved Model Question

**Normal `run_session.py` emergent run:**

| Role | Model | Source |
|------|-------|--------|
| Moderator | `claude-sonnet-4-20250514` | Hardcoded in `core/moderator_brain.py:26` — **but this model returns HTTP 404 from the current API key**. A normal `run_session.py` run will crash on the first moderator call unless the constant is updated. |
| Participant responses | `claude-haiku-4-5-20251001` | From agent JSON `simulation_config.model`; default `_DEFAULT_MODEL` in `participant_agent.py:20` |
| Engagement assessments | `claude-haiku-4-5-20251001` | Same model as participant responses (`participant_agent.py:363`) |

**Traced run (`macho_meals_emergent_full_run_02`):**

| Role | Model | Source |
|------|-------|--------|
| All roles | `claude-sonnet-4-6` | `scripts/validate_macho_meals_emergent.py` patches `moderator_brain._MODEL`, `participant_agent._DEFAULT_MODEL`, and each agent's `simulation_config.model` at runtime (lines 258–283). Restored in `finally` block (lines 449–450). |

**This verification run (`verification_emergent_25`):**

| Role | Model | Source |
|------|-------|--------|
| Moderator | `claude-sonnet-4-6` | Temporarily patched from `claude-sonnet-4-20250514` (which returned 404) |
| Participant responses | `claude-haiku-4-5-20251001` | From agent JSON (unchanged) |
| Engagement assessments | `claude-haiku-4-5-20251001` | Same as participant responses (unchanged) |

---

## 3. Claims That Remain Unverified

| Claim | Why |
|-------|-----|
| Lowered-bar fallback (urgency >0.2 after 2 silent turns) | Not exercised: no turn lacked a willing participant above 0.55 in 25 steps. |
| MAX_CONSECUTIVE_PARTICIPANT_TURNS gate (6 → forced moderator) | Not exercised: max consecutive observe/yield was 3. |
| Peer address bonus (+0.15) | Not exercised: no `addressed_to` fields pointing to other participants were observed in the engagement rounds that led to speaker selection. |
| Consensus risk challenge bonus (+0.10) | Not exercised: `consensus_risk` stayed at 0.2 (below the 0.65 threshold). |
| Bonus cap (0.30) | Not exercised: maximum bonus applied was 0.15 (invite only). |
| Tie-break (lowest turn_count) | Not exercised at the selection boundary: when ties occurred (e.g. turn 8: David and Sam both at 0.650), Will won at 0.700, so the tie-break code ran but didn't determine the outcome. |

These are all hardcoded code paths confirmed by static analysis (the code exists, the constants match). They were not triggered during the 25-turn run. Exercising them would require longer runs or specific conditions.

---

## 4. Instrumentation Confirmation

**Pre-instrumentation hashes (captured before any changes):**

```
e3b0c44298fc1c14  core\__init__.py
71c919902cc1eea6  core\api_logging.py
80e3e1195a9c093e  core\config.py
2a98047895fba9d1  core\moderator_brain.py
9f7162f880c5f6cf  core\orchestrator.py
c194d9fa9b90b8f1  core\participant_agent.py
27b9a6c22e55431d  core\prompt_renderer.py
9bbff51e07f65c99  core\session_state.py
```

**Post-revert hashes (after removing all instrumentation):**

```
e3b0c44298fc1c14  core\__init__.py
71c919902cc1eea6  core\api_logging.py
80e3e1195a9c093e  core\config.py
2a98047895fba9d1  core\moderator_brain.py
9f7162f880c5f6cf  core\orchestrator.py
c194d9fa9b90b8f1  core\participant_agent.py
27b9a6c22e55431d  core\prompt_renderer.py
9bbff51e07f65c99  core\session_state.py
```

**All 8 files: byte-identical.** SHA-256 prefix matches on every file.

Instrumentation consisted of:
- `orchestrator.py`: 3 `print()` blocks (raw urgency, post-bonus urgency, threshold/selection logging), all marked `# TEMP-INSTRUMENTATION` / `# END TEMP-INSTRUMENTATION`. Reverted.
- `moderator_brain.py`: `_MODEL` constant temporarily changed from `"claude-sonnet-4-20250514"` to `"claude-sonnet-4-6"` (the original model returned HTTP 404). Reverted. This was a necessary deviation from the logging-only rule to enable the run; the 404 itself is documented as a finding.

---

## 5. Run Details

| Parameter | Value |
|-----------|-------|
| Session config | `examples/verification_emergent_25.json` |
| Session ID | `verification_emergent_25` |
| Log directory | `output/session_logs/verification_emergent_25/` |
| Participants | David (FG1), Isaiah (FG1), Sam (FG2), Will (FG1) |
| Mode | emergent |
| Steps | 25 (total_turns reached 26 including opening) |
| `inject_participant_intro` | false |
| Temperature | 1.0 |
| `run_label` (formerly `generation_seed`) | null (not set) |
| Moderator model (patched) | `claude-sonnet-4-6` |
| Participant model | `claude-haiku-4-5-20251001` |
| Validation fallbacks | 1 (turn 0, opening truncation) |
| Section transitions | 3 (turns 8, 14, 23) — 3 of 5 sections completed |
| Exit code | 1 (summary printing bug; data intact) |

---

## 6. Statements in `operational_flow.md` That Need Correction

The following are for the later reconciliation task — not acted on here.

1. **Moderator model constant:** The document states the model is `claude-sonnet-4-20250514`. This is correct as written in code, but this model returns HTTP 404 from the current API key. The document should note the accessibility issue and that a future run requires updating the constant.

2. **Section 11 (Worked example) — model identity:** States "The code hardcodes `claude-sonnet-4-20250514` for the moderator." This is correct. The document already flags the mismatch with the traced run, but should additionally note the 404.

3. **Section 12, A11 (new finding):** The `run_session.py` summary printing code crashes with `AttributeError` when `entry.action` is `None` (observe/yield turns). This should be added to the anomalies section. Exit code 1 is a post-completion printing bug, not a session failure.

4. **Minor: the "≥3 substantive responses" claim (H16)** is correctly stated as prompt-only. The live run confirmed this — all section transitions occurred after ≥3 turns, but this was the model's choice, not a code-enforced rule.

---

## 7. Multi-Target Addressing — Static Check (2026-06-26)

**Classification: Reachable-but-unprompted.**

The multi-target bonus branch added in the 2026-06-26 direct-address change is structurally sound but cannot fire under current prompting.

| Layer | Permits multi-target? | Evidence |
|-------|----------------------|----------|
| Schema | Yes (technically) | `target: str \| None` (`session_state.py:483`) — accepts any string including comma-separated |
| Parser | Yes | `_resolve_moderator_targets` splits on commas, resolves each part by PID or name |
| Prompt | **No** | `02_USER_MESSAGE_TEMPLATE.md:69` instructs: `"participant_id if targeting one person, or 'group' if addressing everyone"` — explicitly singular. No multi-value example anywhere in the prompt or system prompt. |

**Implication:** The moderator model will produce either a single participant ID or `"group"` — never a comma-separated list of names. The multi-target branch is decorative unless the prompt is changed.

**To make it reachable** (not implemented): change the prompt target description to include `"comma-separated ids if targeting two or more"` and add one example. No schema or code changes needed.

This closes the "Multi-target bonus: Not exercised" item from Section 3 — the reason it was not exercised is that it *cannot* be exercised under current prompting, not that it simply didn't happen by chance.

---

*End of verification report.*
