# Moderator Over-Intervention: n=10 × 3-Condition Experiment

**Date:** 2026-06-30
**Purpose:** Establish a properly-replicated (n=10) baseline for moderator turn-share and participant-to-participant adjacency, post-dedup-fix, then test restraint language (A) and the reflection mechanism incrementally and attributably against it. The prior two-run estimates (turn-share 42-44%, adjacency 25-31%) were explicitly flagged as not yet trustworthy magnitudes — this experiment replaces them.
**Mechanism reference:** `docs/changes/2026-06-30_moderator_dedup_A_reflection.md`.
**Diagnostic reference:** `docs/changes/2026-06-30_moderator_overintervention_diagnostic.md` (Candidates A, B, C).

---

## 1. Configuration

- **Agents:** Set A — David, Isaiah, Amir, Ibrahim (`agents/macho_meals/mm_fg1_*.json`), all FG1-derived. Same set used throughout the prior memory-dedup and moderator-review tasks.
- **Guide:** the standard Macho Meals plant-based-masculinity guide (7 sections), identical across all 30 runs.
- **Mode:** emergent, `inject_participant_intro: false`, `participant_episodic_depth: full`.
- **Turn budget:** 14 turns per run, identical across all 30 runs.
- **All runs post-dedup-fix** (Part 1 of the mechanism doc) — there is no separate pre-fix condition in this experiment; the dedup fix is folded into Baseline, per instructions.
- **Replication, not seeding:** the system has no functional seed (confirmed 2026-06-29); "n=10" means 10 runs under identical configuration, not 10 seeded runs.

| Condition | `moderator_restraint_prompt` | `moderator_reflection_enabled` | n |
|---|---|---|---|
| **Baseline** | OFF | OFF | 10 |
| **+A** | ON | OFF | 10 |
| **+A+Reflection** | ON | ON | 10 |

All 30 configs: `examples/overint_{baseline,plusA,plusA_reflection}_r{1..10}.json`. All 30 run logs: `output/session_logs/overint_*_r{1..10}/`.

---

## 2. Metrics (defined once, computed identically everywhere)

1. **Moderator turn-share** = moderator visible turns / total visible turns, computed from each run's final `transcript` (entries with `speaker_id != "MODERATOR"` vs `== "MODERATOR"`). Same definition used for the real human transcripts.
2. **Participant-to-participant adjacency** = of all participant turns, the fraction immediately preceded in `transcript` by *another* participant turn (vs. preceded by the moderator). The first transcript entry, if a participant, is excluded from the denominator (no preceding entry to classify).

---

## 3. Real-human baseline, per group — corrected

The original instructions for this task characterized the human comparator groups as "prompt-only-moderated FG2/FG5 vs verbally-moderated FG1/FG3." **This is corrected here against the actual standardization record** (`data/datasets_transcripts/standardized/macho_meals/MACHO_MEALS_STANDARDIZATION_REPORT.md`, §5): FG1, FG3, and FG5 all have genuine verbal/chat moderator turns (probes, redirects, session management); **FG2 and FG4** are the prompt-only groups — their "moderator" entries are exclusively scripted `Question N.` prompts with no active facilitation at all. The pairing in the instructions had FG5 and FG4 swapped.

| Group | Moderator style | n (total turns) | Turn-share | Adjacency |
|---|---|---|---|---|
| **FG1** | Verbal (matched — synthetic agents are FG1-derived) | 64 | **9.4%** | **89.7%** |
| FG3 | Verbal | 104 | 5.8% | 93.9% |
| FG5 | Verbal | 128 | 3.9% | 95.9% |
| FG2 | Prompt-only (not a meaningful comparator for an active AI moderator) | 33 | 15.2% | 82.1% |
| FG4 | Prompt-only (not a meaningful comparator for an active AI moderator) | 44 | 11.4% | 87.2% |

**FG1 is the primary comparator** throughout this analysis (matched agents). FG3 and FG5 are reported as additional verbally-moderated reference points — all three cluster in the same range (turn-share 3.9-9.4%, adjacency 89.7-95.9%), reinforcing that the prior review's "4-15%/82-96%" range describes genuine active moderation, not an artifact of one group. FG2/FG4's higher turn-share and lower adjacency reflect the *absence* of a human moderator probing or redirecting, not restrained moderation — they are reported for completeness but are not used as a target.

---

## 4. Results — per condition, n=10

### 4.1 Distribution (the data is effectively 3-level discrete)

Every run had exactly 12 participant visible turns (the 14-turn budget's early-session structure — intro round-robin via `reactivate_silent` — proved highly consistent regardless of condition, since restraint language explicitly preserves the GROUP DYNAMIC RULES that drive it). The only source of variation across all 30 runs was the moderator's own turn count, which took exactly one of three values: **3, 4, or 5**.

| Condition | mod_turns distribution (n=10) | mean mod_turns |
|---|---|---|
| Baseline | {3: 2, 4: 2, **5: 6**} | 4.40 |
| +A | {**3: 5**, 4: 3, 5: 2} | 3.70 |
| +A+Reflection | {**3: 6**, 4: 2, 5: 2} | 3.60 |

Baseline is mode-5 (most common outcome: the moderator speaks 5 of 17 visible turns); both +A and +A+Reflection are mode-3 — a visible leftward shift in the distribution, not just a small mean change.

### 4.2 Turn-share and adjacency, summary statistics

| Condition | Turn-share mean | median | stdev | range | Adjacency mean | median | stdev | range |
|---|---|---|---|---|---|---|---|---|
| **Baseline** | 26.6% | 29.4% | 3.94pp | [20.0%, 29.4%] | 65.8% | 66.7% | 6.15pp | [58.3%, 75.0%] |
| **+A** | 23.4% | 22.5% | 3.91pp | [20.0%, 29.4%] | 70.0% | 75.0% | 7.03pp | [58.3%, 75.0%] |
| **+A+Reflection** | 22.9% | 20.0% | 4.00pp | [20.0%, 29.4%] | 71.7% | 75.0% | 5.83pp | [58.3%, 75.0%] |

### 4.3 Effect-vs-noise — median/spread (the established discipline)

Using max-min spread as the per-condition noise floor (consistent with the verbosity/collapse replication work):

- **Turn-share, Baseline → +A:** median shift = 29.4% − 22.5% = **6.9pp**. Within-condition spread ≈ 9.4pp (consistent across all three conditions). The median shift alone does **not** clearly exceed the spread — by this test alone, inconclusive.
- **Turn-share, +A → +A+Reflection:** median shift = 22.5% − 20.0% = **2.5pp**, well inside the 9.4pp spread. No detectable additional effect.
- **Adjacency, Baseline → +A:** median shift = 75.0% − 66.7% = **8.3pp**, inside the ≈16.7pp spread.
- **Adjacency, +A → +A+Reflection:** median shift = 0pp (same median).

By median-vs-spread alone, A's effect is suggestive but not clearly above the noise floor — **this is exactly why the median/max-min test is under-powered for n=10 discrete data with only 3 possible outcome values**, and why a second, complementary test was run.

### 4.4 Effect-vs-noise — pairwise dominance (rank-based, distribution-aware)

For each pair of conditions, the fraction of all 100 (10×10) cross-condition run pairs where one condition's value exceeds the other's (ties count as half) — a non-parametric effect size (probability of superiority) that uses the full distribution rather than just the median and the range:

| Comparison | Turn-share | Adjacency |
|---|---|---|
| Baseline > +A | **72.0%** | 32.0% (i.e. +A > Baseline 68.0% of the time) |
| +A > +A+Reflection | 54.0% (near chance) | 44.0% (near chance) |
| Baseline > +A+Reflection | **74.0%** | 24.5% (i.e. +A+Reflection > Baseline 75.5%) |

**This resolves the ambiguity from §4.3.** A 72-75% probability-of-superiority is a real, meaningfully-sized directional effect (50% would be pure chance) — restraint language (A) measurably reduces moderator turn-share and measurably increases participant-to-participant adjacency. The marginal step from +A to +A+Reflection is close to chance on both metrics (54%, 44%) — **reflection adds no detectable further effect on these two over-intervention metrics in this sample.**

**Conclusion: A is a real effect; reflection's marginal contribution to these specific metrics is not distinguishable from noise at n=10.**

---

## 5. Comparison to the human (FG1) baseline

| | Turn-share | Gap to FG1 (9.4%) | Adjacency | Gap to FG1 (89.7%) |
|---|---|---|---|---|
| Baseline (mean) | 26.6% | 17.3pp | 65.8% | 23.9pp |
| +A+Reflection (mean) | 22.9% | 13.5pp | 71.7% | 18.0pp |
| **Gap closed (mean-based)** | | **21.8%** | | **24.5%** |
| Baseline (median) | 29.4% | 20.0pp | 66.7% | 23.0pp |
| +A+Reflection (median) | 20.0% | 10.6pp | 75.0% | 14.7pp |
| **Gap closed (median-based)** | | **47.0%** | | **36.2%** |

A real, measurable narrowing of the gap toward the matched human baseline — but **the gap remains large under either summary statistic**, and the mean-based and median-based closure estimates disagree substantially (22% vs 47% for turn-share). This disagreement is itself informative: with only 3 possible discrete outcomes per run at this turn budget, the choice of summary statistic materially changes the headline number — a concrete illustration of why n=10 at this turn budget is not yet sufficient for a precise closure estimate, only a directionally confident one.

**A methodological note on the original two-run figures:** the prior diagnostic's 42-44% turn-share estimate (from `verification_emergent_25` and `macho_meals_emergent_full_run_02`, both pre-dating the moderator dedup fix and run at a different, longer turn budget) is **not directly comparable** to this experiment's ~22-29% Baseline figures — the difference reflects at minimum the dedup fix, the shorter 14-turn budget used here, and ordinary n=2 sampling noise, with no way to cleanly attribute the gap between them to any single cause. This is exactly the kind of imprecision the n=10 baseline was built to replace going forward; it should not be read as a 15-20 point "effect" of the dedup fix alone.

---

## 6. Overdetermination check

Per the instructions: if +A alone closes most of the gap, reflection may be redundant *for over-intervention specifically* (though still potentially valuable for the FocusAgent fidelity gap it was built to close). **This is what the data shows.** The pairwise-dominance test (§4.4) found A's effect substantial (72-75%) and reflection's marginal addition on top of A statistically indistinguishable from chance (54%/44%) on both turn-share and adjacency. Reflection was not redundant by design — Piece 1 (the turn-share signal) and Piece 2 (the section-boundary summaries) target the diagnostic's Candidate C directly, and the mechanism worked exactly as designed in the smoke test (the model explicitly reasoned about its own 33% turn-share and pulled back for three consecutive turns immediately afterward, in the pre-reconciliation draft's smoke test) — but at the scale tested here (14 turns, 1-2 reflection calls per run), its detectable *marginal* contribution to the aggregate turn-share/adjacency numbers, on top of restraint language already in place, was not measurable.

Neither condition closes the gap to FG1 fully. The remaining gap (10.6-18.0 percentage points depending on metric and statistic) indicates **the cause is not fully explained by A and C alone** — consistent with the diagnostic's own framing of these as the two strongest candidates, not the only possible ones. Candidate B (the missing lightweight backchannel action) was explicitly out of scope for this task and remains untested; it may account for some of the residual gap, particularly given the diagnostic found participation-equity nudges (a B-relevant category) accounted for 10-32% of visible AI-moderator turns in the original two runs.

---

## 7. Honest summary

**What each change does, on this evidence:**
- **The duplication fix** removes a real, narrow, low-stakes redundancy in the moderator's own context. Its standalone behavioral effect (independent of A and reflection) was not isolated as a separate experimental condition — it is folded into Baseline, per instructions, and the prior two-run figures it should be compared against are not a clean reference point (see §5's methodological note).
- **Restraint language (A)** has a real, replicated, meaningfully-sized effect: it shifts the moderator's intervention-frequency distribution measurably toward less-frequent, more-permissive-of-participant-interaction behavior (72-75% pairwise dominance over Baseline on both metrics), without relaxing any existing safeguard.
- **The reflection mechanism** is correctly built, fires reliably (17/17 calls succeeded, zero parse failures across 10 runs), produces genuinely thematic (not recap) summaries under the 80-word target, and gives the moderator a real, structurally-grounded self-participation signal it previously entirely lacked. Its *marginal* effect on top of A, specifically on turn-share and adjacency at a 14-turn budget with 1-2 reflection firings per run, was not detectable above noise in this sample.

**What remains unexplained:** roughly 11-18 percentage points of turn-share/adjacency gap to the matched human baseline persists even with both changes on. This could reflect (a) Candidate B (the missing backchannel action), untested here; (b) a turn budget too short for reflection to compound meaningfully (only 1-2 firings per run); (c) a ceiling on how far prompt-level changes alone can move a structurally different format (synthetic emergent-mode group discussion vs a real moderator's non-verbal cues, pacing, and judgment); or (d) some combination. No single deeper cause is identified or claimed here — this finding should be read as "A and reflection help, measurably, but do not resolve the gap," not as evidence the cause is fully understood.

**What would need more runs or a different design:**
- A larger n (the median-vs-mean disagreement at n=10 on 3-level discrete data shows this sample size is at the edge of what supports precise closure estimates) before treating any exact percentage as stable.
- A longer turn budget specifically to let reflection fire more than 1-2 times per run, since its design (regenerate at every section boundary) is structurally under-exercised at 14 turns.
- A dedicated isolation condition (Baseline+Reflection-only, without A) — noted as optional in the instructions and not run here — would be needed to state reflection's effect independent of A, rather than only its marginal contribution on top of A.
- Candidate B (the lightweight backchannel action) as a fourth condition, to test whether it accounts for some of the residual gap that A+Reflection left unclosed.

---

## 8. Reproducibility

| Item | Value |
|---|---|
| Session configs | `examples/overint_{baseline,plusA,plusA_reflection}_r{1..10}.json` |
| Session logs | `output/session_logs/overint_{baseline,plusA,plusA_reflection}_r{1..10}/` |
| Turn budget | 14 (`--turns 14 --mode emergent`) |
| `run_label` | Not set in these configs (recording-only, no functional effect) |
| Reflection calls (total, +A+Reflection batch) | 17 across 10 runs (mean 1.7/run), 0 failures |
