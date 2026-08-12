# Full-Session Token Growth: A Blocking Cost/Latency Issue Discovered During the Thematic-Fidelity Smoke Test

**Date:** 2026-06-30
**Status:** Issue documented, NOT resolved. The full-session batch (`docs/findings/2026-06-30_thematic_fidelity_macho_meals.md`, Part 3) is paused pending a researcher decision on how to address this.
**Trigger:** a smoke test of the new full-natural-completion session runner (`scripts/run_full_session.py`), run on `fidelity_fg5_r1` (FG5 roster, restraint ON, reflection ON, 90-turn safety cap). The researcher stopped the run mid-session (turn 70 of a cap of 90, 6 of 7 guide sections completed) specifically to halt further API spend once the growth pattern below became visible.

---

## What was observed

Every per-turn API call in this run grew **larger as the session progressed**, in three independent places, all driven by the same root cause: unbounded context accumulation.

### Moderator decision calls — the dominant cost

| Turn | input_tokens |
|---|---|
| 0 | 4,478 |
| 10 | 15,939 |
| 20 | 27,623 |
| 30 | 38,335 |
| 40 | 53,482 |
| 50 | 67,958 |
| 60 | 80,287 |
| 70 | 93,505 |

Near-perfectly linear: **~1,272 additional input tokens every single turn**, with no ceiling. Extrapolating to a plausible natural-completion point (~turn 85, based on how close the session was to finishing section 6 when stopped) projects to **~112,600 input tokens for the final moderator call alone** — roughly 25× the size of the opening call.

### Participant response generation

844 tokens (first call) → 27,347 tokens (last call before the run was stopped) — a **~32× increase**.

### Participant engagement assessment

285 tokens → 7,977 tokens — a **~28× increase**, despite this call being designed around a nominally fixed 6-entry recent-transcript window (see root cause below for why it still grows).

### The reflection mechanism (built earlier today) — worst slope of all

2,175 tokens (1st reflection, turn ~6) → 32,655 tokens (6th reflection, turn ~66) — **~15× growth over just 6 calls**, because each reflection call sends the *entire* transcript-so-far by design.

### Run total (partial — the session never finished)

**5,589,170 input tokens and 107,238 output tokens consumed by turn 70 of an incomplete run.** This is for FG5, the *smallest* roster (4 participants) and the run was not yet done — it had ~6/7 sections complete and still needed several more turns to close out.

---

## Root cause — three independent unbounded-context mechanisms, all by deliberate prior design

This is not a bug in the sense of broken code — each mechanism is working exactly as designed and documented. The problem is that all three designs were calibrated against **short, truncated sessions (14-26 turns)**, and this is the first task to actually run sessions to **natural full completion** (intentionally, per the thematic-fidelity instructions), which is precisely the regime where the calibration breaks down.

1. **The moderator always sees the full, untrimmed transcript.** Established and confirmed in `docs/changes/2026-06-30_moderator_review.md` (Part 3): `SessionState.to_prompt_json()` never trims `transcript` — only `moderator_log` is windowed (to 3 entries). At the time, this was identified as a *strength* (the moderator is not context-starved on the conversation). At full-session length, the same design means **every single moderator call re-sends the entire conversation so far**, growing linearly forever. This is the single largest contributor (1,272 tokens/turn, dominating the total).

2. **`participant_episodic_depth: full`** (the default since the 2026-06-29 dedup fix) sends each participant "every transcript entry since they last spoke," uncapped. Its own field description states the rationale explicitly: *"Default is 'full' because current sessions are short (~15-22 turns)."* A 70+ turn full session is well outside that calibration — a participant skipped over for 10+ turns while others talk accumulates a correspondingly huge incremental slice next time they're called.

3. **Engagement assessment's growth, despite a fixed 6-entry transcript window**, comes from a second input to the same call: `participant_own_turns`, capped at 15 entries (`_MAX_PARTICIPANT_HISTORY`) — by late session a participant has accumulated their full 15-turn history, and those turns themselves tend to be longer once the discussion has built up context. Smaller contributor than #1/#2, but not zero.

4. **The reflection mechanism (new today) compounds the problem rather than mitigating it.** `run_moderator_reflection()` (`core/moderator_brain.py`) deliberately sends the full `state.transcript` every time it fires, by design (so each summary is "regenerated fresh," not built from stale prior reasoning — a correct and deliberate choice at the time it was built and tested at 14-turn scale). At full-session scale, this means the *summary mechanism meant to give the moderator a cheap, compact sense of the discussion* is itself one of the most expensive individual calls in the entire run (32,655 tokens for the 6th reflection — larger than entire early-session moderator decisions).

**This was invisible until now** because every prior experiment in this dissertation — the verbosity baseline, the participant/moderator dedup fixes, the over-intervention diagnostic, the n=10×3 restraint/reflection experiment — used 14-26 turn sessions, where linear growth from a few hundred to a few thousand tokens never reached a magnitude anyone would notice as a problem. Running to **natural full completion** (all 7 guide sections, generally 60-90+ turns based on this one data point) is qualitatively different territory that none of those designs were tested against.

---

## Implications for the planned thematic-fidelity experiment

The original Part 3 plan was 25 full natural-completion sessions (FG1 ×5, FG2 ×5, FG5 ×5 primary, plus FG1 ×5, FG5 ×5 reflection-OFF arms). Based on this one data point:

- FG5 (4 participants, the smallest roster) needed 70+ turns and 5.59M+ input tokens and **still wasn't finished**.
- FG1 and FG2 (5 participants each) will plausibly need *more* turns to round-robin through everyone across 7 sections, and therefore an even larger token total — the per-turn growth rate compounds with however many more turns a larger group needs.
- Across 25 such runs, the **aggregate token cost and wall-clock time would be very large**, and the cost is heavily back-loaded — the second half of every session costs far more than the first half, by construction.
- The reflection-ON arms (15 of the 25 planned runs) carry the additional reflection-call cost on top of the moderator/participant growth already described.

This issue is **separable by mechanism**, which matters for choosing a fix:

| Mechanism | Could be capped without contradicting prior design intent? |
|---|---|
| Participant `episodic_depth` | Yes — `since_last_n` already exists as a built, tested option (added 2026-06-29), just not the default. Switching it for full-session runs is a config change, not new code. |
| Reflection's transcript input | Yes, fairly easily — its job was always "a compact synthesis," not a full-transcript dump; sending only the entries since the last reflection (rather than the whole session) would likely serve the same purpose at a fraction of the cost, though it wasn't tested that way today. |
| Moderator's full transcript | Harder — this was explicitly identified as a *desirable* property in the 2026-06-30 moderator review (not context-starved). Capping it would reopen a design question that was deliberately resolved in the other direction one task ago. Any fix here needs to weigh fidelity (the moderator's stated reason for needing full context) against the now-demonstrated cost at session lengths beyond ~25 turns. |

**No fix has been applied.** This document records the finding; the path forward (cap episodic depth for full runs, cap reflection's input, accept the cost as a known characteristic of full-session work and budget for it, or something else) is the researcher's call before the full-session batch resumes.

---

## What exists on disk from this smoke test

`output/session_logs/fidelity_fg5_r1/` — an **incomplete, killed-mid-run session** (70 of an eventual ~80-90 turns, 6 of 7 sections done). `transcript.json`, `transcript.txt`, and `moderator_log.json` were reconstructed after the fact from the last saved snapshot (`state_turn_70.json`'s embedded `.transcript`/`.moderator_log` fields — the orchestrator's normal `save_transcript()`/`save_moderator_log()` calls never ran, since those live in a `finally` block that a hard process kill bypasses). This run is **not usable as an experimental data point** — it never reached its closing section and was deliberately terminated — but is preserved as the evidence base for this finding.

---

## Verification addendum (2026-06-30, read-only) — exact inputs, exact caps, exact attribution

Per `INSTRUCTIONS_VERIFY_ENGAGEMENT_AND_MODERATOR_CONTEXT.md`. Everything below is either a direct code citation or a number reconstructed from `fidelity_fg5_r1`'s actual saved snapshots, measured with the Anthropic SDK's `count_tokens` endpoint (exact counts, not estimates) — nothing here is implemented or changed; read-only.

### Q1 — The engagement-assessment call: every input, exact caps, exact attribution

**Every input to `assess_engagement()`** (`core/participant_agent.py:288-366`):

| Input | Source | Bound |
|---|---|---|
| `system_prompt` (identity line: name/age/gender/location/diet) | `participant.agent_payload` demographics, lines 301-326 | Static, tiny (~50-80 tokens), does not grow |
| `recent_lines` | `_format_recent_transcript(recent_transcript)`, line 336; `recent_transcript` is `self._recent_transcript()` from the caller | **Fixed at ≤6 entries** — `core/orchestrator.py:44`, `_RECENT_TRANSCRIPT_WINDOW = 6`; sliced at `core/orchestrator.py:248`, `self.state.transcript[-_RECENT_TRANSCRIPT_WINDOW:]` |
| `own_history` | `participant_own_turns` numbered list, lines 338-349; built from `self._get_participant_own_turns(pid)` | **Fixed at ≤15 entries** — `core/orchestrator.py:45`, `_MAX_PARTICIPANT_HISTORY = 15`; sliced at `core/orchestrator.py:265`, `[-_MAX_PARTICIPANT_HISTORY:]` — but each of the (up to) 15 entries is the participant's **full, unbounded utterance text** (`entry["content"]`, no per-entry truncation) |
| Fixed JSON-schema instructions (closing block) | Lines 356-366 | Static |

Call site confirmed: `core/orchestrator.py:606` (`recent = self._recent_transcript()`, computed once per round) and `:625-632` (`own_turns = self._get_participant_own_turns(pid)`, per participant), both passed into `assess_engagement(...)`.

**Which input drives the growth — exact attribution, reconstructed for Fletcher (FG5) at turn 5 vs turn 69 of the killed run**, measured with `count_tokens`:

| | Early (after turn 5) | Late (after turn 69) | Growth |
|---|---|---|---|
| `recent_window_tokens` (≤6 entries) | 579 (4 entries — session too young for 6 yet) | 1,718 (6 entries) | **~3.0×** |
| `own_history_tokens` (≤15 entries) | 60 (1 own turn) | 4,454 (15 own turns) | **~74×** |

**Answer: `own_history` (the `participant_own_turns` block) is the dominant driver** — 4,454 of the late-session total, vs the window's 1,718. Late-session, own-history is roughly **72% of the combined recent+own total** measured here.

**Q1.3 — is the 6-entry window genuinely fixed, or mislabelled?** **Genuinely fixed in entry count** — confirmed both by the code (`[-6:]`, a hard slice) and empirically (4 entries early because the session hadn't yet produced 6 transcript entries; exactly 6 late). It is **not fixed in token size**: 579→1,718 tokens (~3×) for the same 6-entry cap, because later transcript entries (participant turns) are individually longer than earlier ones — a real, secondary, separate effect from the `own_turns` cap not being entry-count-bound in length. The finding doc's original framing ("driven by a recent-transcript window (nominally 6) PLUS `participant_own_turns` capped at 15") was directionally correct but did not attribute the *share* — this addendum supplies that: own_turns dominates (~74× growth) over the window's secondary, smaller (~3×) growth.

**Q1.4 — what each input is for (so a cap doesn't blindly break the function):** `recent_lines` gives the participant immediate awareness of what just happened, needed to react authentically to the latest exchange. `own_history` is explicitly used by the system prompt's own instruction — *"If what you wanted to say has already been said, your urgency should be low"* (`core/participant_agent.py:333`) — i.e. it exists specifically to suppress redundant re-raising of points the participant already made. A naive cap on `own_history` (fewer entries, or truncated entries) risks the participant "forgetting" something they said many turns ago and re-raising it, undermining the exact function this field serves. No cap value is proposed here.

### Q2 — The moderator transcript mechanism

**Q2.1 — confirmed: `transcript` is sent in full, every moderator call, never sliced.** `SessionState.to_prompt_json()` (`core/session_state.py:536-606`): `data = self.model_dump(mode="json")` (line 543) captures the complete state including `transcript`. The function modifies `data["participants"]` (strips `agent_payload`, lines 545-555) and `data["moderator_log"]` (windows + strips `utterance` + optionally compresses, lines 557-588) — **`data["transcript"]` is never referenced, sliced, or modified anywhere in the function.** Confirmed reaching every moderator call: `core/prompt_renderer.py:280`, `rendered.replace("{SESSION_STATE}", state.to_prompt_json(compress_before_turn))`, inside `render_turn_message()`, called from `core/moderator_brain.py:189` inside `call_moderator()` — the function invoked for every non-opening moderator decision.

**Q2.2 — confirmed: `moderator_log` is the only windowed part, window = 3.** `core/session_state.py:482`, `_MODERATOR_LOG_LIVE_WINDOW = 3`; applied at line 564, `data["moderator_log"] = data["moderator_log"][-_MODERATOR_LOG_LIVE_WINDOW:]`. This is the moderator's own-reasoning log (`situation_assessment`/`justification`/etc.), a **different list from `transcript`** — confirmed empirically below that it does not grow.

**Q2.3 — confirmed: the dominant moderator-call growth is the transcript re-send**, attributed precisely by reconstructing the actual `{SESSION_STATE}` JSON at turn 5 vs turn 69 and measuring each top-level key separately with `count_tokens`:

| Component | Early (turn 5) | Late (turn 69) | Growth | Entries early→late |
|---|---|---|---|---|
| `transcript` | 911 | **33,434** | **~36.7×** | 4 → 89 |
| `moderator_log` | 615 | 746 | ~1.2× (flat) | 3 → 3 (unchanged) |
| `participants` | 442 | 4,154 | ~9.4× | — (grows via accumulating `topics_covered`, not entry count) |
| everything else (`group_state`, `session_meta`, `discussion_guide`) | 2,591 | 7,036 | ~2.7× | — |
| **Total `{SESSION_STATE}`** | **4,559** | **45,370** | **~9.95×** | |

`transcript` alone accounts for **~80% of the total growth** in the session-state JSON (+32,523 of the +40,811 total token increase between these two snapshots). `moderator_log` stays essentially flat, confirming the window is doing its job — the growth is unambiguously the transcript, not the log, not demographics. (`participants` and "everything else" grow too, from accumulating list fields like `topics_covered` and `emergent_themes`, but are minor next to `transcript`.)

Run-wide totals (whole partial 70-turn run, by `event_type`, summed `input_tokens` from `api_calls.jsonl`): `moderator_decision_attempt` = 3,361,759 (**60.1%** of the run's 5,589,170 total input tokens); `participant_engagement_assessment` = 1,233,596 (22.1%); `participant_response_generation` = 890,530 (15.9%); `moderator_reflection` = 97,281 (1.7%). Moderator-side calls combined (decision attempts + retries + reflection) = 62.0% of total run cost — consistent with (and confirming) the "~61%" figure referenced in the verification instructions.

**Q2.4 — confirmed: the reflection mechanism also sends the full, unsliced transcript.** `core/moderator_brain.py:333`, inside `run_moderator_reflection()`: `"TRANSCRIPT": json.dumps(state.transcript, indent=2, default=str)` — the complete `state.transcript`, no slicing, no since-last-reflection filter. Confirmed against the run's actual reflection calls: 2,175 tokens (1st reflection) → 32,655 tokens (6th reflection), tracking the same growing-transcript-length pattern as the moderator's regular decision calls (consistent: by the 6th reflection near turn 66, the transcript had ~85 entries, close to the 89 measured at turn 69 above).

**Feasibility of since-last-reflection input instead (not implemented):** reflection fires 1:1 with `SECTION_TRANSITION` actions (`core/orchestrator.py:449-451`, `just_transitioned = last_log.action == ModeratorAction.SECTION_TRANSITION`). The orchestrator already has everything needed to compute a "since the previous reflection-triggering boundary" slice — `moderator_log` records every past `section_transition`'s `turn` number, so the prior boundary is derivable without new state (though an explicit `last_reflection_turn` marker would make this more direct than re-scanning `moderator_log` each time — `GroupState` currently has no such field, only the *content* of the last reflection in `last_reflection`, not its *position*). One real caveat: if only sliced since-last-reflection content were sent, the model would lose awareness of everything before that boundary unless the **prior summary text were also fed back in** alongside the new slice — currently `run_moderator_reflection()`'s prompt does not do this (it receives only `TRANSCRIPT`, no prior-summary placeholder), so feasibility holds, but only if paired with carrying the previous summary forward, not transcript-slicing alone.

### Q3/Q4 — Section-boundary summaries: confirmed to exist; confirmed additive, not currently a compression substrate

**Confirmed: the summaries exist, contain exactly two fields, and are overwritten (not accumulated) each time.** `ModeratorReflection` (`core/session_state.py`, the model returned by `run_moderator_reflection()`) has exactly `discussion_summary` and `strategy_summary`. Stored at `core/orchestrator.py:453`, `self.state.group_state.last_reflection = reflection` — a **direct overwrite**, not an append. Verified empirically across the killed run's snapshots: `discussion_summary` text differs at every reflection-bearing snapshot checked (turns 6, 17, 30, 42, 49, 66 each have distinct content), and turn 70 (no new reflection since turn 66) still shows the turn-66 text — confirming only the single most recent summary is ever live in `GroupState` at any point; earlier section summaries are not retained anywhere in the live state once superseded (they remain individually recoverable only from historical `state_turn_N.json` snapshots, not from current state or from `api_calls.jsonl`, which logs only token counts, not content).

**Confirmed: currently additive, not a substitute for the full transcript.** `core/prompt_renderer.py:343-346`: when reflection is enabled, the two-summary block is **prepended** to the rendered message (`rendered = reflection_block + "\n\n---\n\n" + rendered`) — `rendered` at that point still contains `{SESSION_STATE}` with the complete, untrimmed `transcript` inside it. The summaries currently supplement the full transcript ("read this first, then the verbatim record"); they do not replace or shrink it. This is exactly why `moderator_reflection` calls add their own growing cost (Q2.4) on top of, not instead of, the already-growing per-turn moderator-decision cost.

**Feasibility of using the summaries as the moderator's decision-call compression substrate (not implemented):** the content exists and is already computed at the right cadence (section boundaries) for this purpose. Two gaps would need addressing, not now: (a) only the *latest* summary is retained — an accumulating list (one summary pair per completed section) would be needed to compress *all* prior sections, not just the most recent; (b) the regular per-turn moderator decision call (`render_turn_message`, distinct from the reflection call) does not currently have any mechanism to *replace* its `{SESSION_STATE}`-embedded full transcript with a recent-verbatim-window + accumulated-summaries combination — today summaries only ever reach the reflection call's *output*, then get prepended as extra context, never substituted for the transcript send itself.

### Q5 — Anything the original finding doc got wrong or imprecise

Nothing found to be factually wrong. Two places where this addendum adds precision the original finding lacked (written immediately after the run was killed, before this detailed attribution work):
1. The engagement-growth explanation named both candidate inputs (window + own_turns) but did not attribute the *share* between them — now quantified (own_turns ~74× growth, dominant; window ~3× growth, secondary but non-zero).
2. The "~1,272 tokens/turn" moderator growth rate was reported as a fact but not previously decomposed by source — now attributed: ~80% of the session-state growth between two measured points is `transcript` specifically, with `moderator_log` confirmed flat (3 entries throughout) and `participants`/`group_state` contributing the rest.

No fix values are proposed in this addendum, per instructions.
