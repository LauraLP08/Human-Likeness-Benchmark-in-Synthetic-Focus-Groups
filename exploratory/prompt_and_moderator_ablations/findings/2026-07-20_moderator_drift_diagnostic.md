# Moderator Drift, Guide Adherence, and Repetition — Diagnostic

**Date:** 2026-07-20  
**Evaluator (LLM steps):** `gemini-3.5-flash`  
**Note:** Structural metrics (Parts 2, 3a, 5b) are authoritative. LLM-assisted metrics (Parts 3b, 4, and drift-episode count) are EXPLORATORY — they have not yet passed repeatability or human-anchor gates.

**Transcripts used:**
- Human: FG1–FG5 (real focus groups, standardised transcripts)
- Synthetic: costfix\_validation\_fg1 (Synth FG1), costfix\_validation\_fg5 (Synth FG5)

---

## Part 2 — Interactional Structural Metrics

### 2.1 Verbosity and participation

| Transcript | N turns | N ptk | Median words | IQR | ≤20w frac |
|-----------|---------|-------|-------------|-----|-----------|
| human_fg1 | 64 | 58 | 38.5 | 60.5 | 41.4% |
| human_fg2 | 33 | 28 | 89.5 | 81.8 | 3.6% |
| human_fg3 | 104 | 98 | 47.5 | 111.8 | 35.7% |
| human_fg4 | 44 | 39 | 47.0 | 129.5 | 35.9% |
| human_fg5 | 128 | 123 | 22.0 | 78.5 | 49.6% |
| synth_fg1 | 130 | 100 | 216.0 | 60.0 | 4.0% |
| synth_fg5 | 101 | 76 | 263.0 | 51.2 | 0.0% |

### 2.2 Participation balance

| Transcript | N ptk | Entropy (norm) | Gini turns | Gini words | Mod turn% | Mod word% |
|-----------|-------|--------------|-----------|-----------|----------|----------|
| human_fg1 | 5 | 0.926 | 0.269 | 0.196 | 9.4% | 4.4% |
| human_fg2 | 5 | 0.989 | 0.100 | 0.200 | 15.2% | 3.0% |
| human_fg3 | 5 | 0.923 | 0.269 | 0.218 | 5.8% | 1.3% |
| human_fg4 | 3 | 0.963 | 0.154 | 0.283 | 11.4% | 2.6% |
| human_fg5 | 4 | 0.957 | 0.185 | 0.281 | 3.9% | 1.3% |
| synth_fg1 | 5 | 0.997 | 0.056 | 0.051 | 23.1% | 9.3% |
| synth_fg5 | 4 | 0.997 | 0.039 | 0.027 | 24.8% | 8.4% |

### 2.3 Adjacency P→P and reference density

| Transcript | P→P frac | Reference density |
|-----------|---------|-----------------|
| human_fg1 | 0.897 | 0.034 |
| human_fg2 | 0.821 | 0.107 |
| human_fg3 | 0.939 | 0.061 |
| human_fg4 | 0.872 | 0.103 |
| human_fg5 | 0.951 | 0.187 |
| synth_fg1 | 0.670 | 0.400 |
| synth_fg5 | 0.684 | 0.868 |

### 2.4 Chain depth (consecutive participant runs without moderator)

| Transcript | Mean chain | Max chain | Frac in chain≥3 | Frac in chain≥5 |
|-----------|-----------|----------|----------------|----------------|
| human_fg1 | 9.670 | 17 | 98.3% | 98.3% |
| human_fg2 | 5.600 | 7 | 100.0% | 100.0% |
| human_fg3 | 16.330 | 31 | 99.0% | 99.0% |
| human_fg4 | 7.800 | 12 | 100.0% | 100.0% |
| human_fg5 | 24.600 | 36 | 100.0% | 100.0% |
| synth_fg1 | 3.450 | 5 | 91.0% | 55.0% |
| synth_fg5 | 3.170 | 5 | 81.6% | 72.4% |

---

## Part 3 — Moderator Steering

### 3a. Decision-log action breakdown (synthetic sessions only)

| Session | allow | guide_question | probe | redirect_refocus | reflect_summarize | other | Redirect rate |
|---------|-------|--------------|-------|-----------------|-----------------|-------|--------------|
| synth_fg1 | 72 | 9 | 13 | 7 | 1 | 0 | 6.9% |
| synth_fg5 | 53 | 9 | 7 | 9 | 0 | 0 | 11.5% |
| human_fg1 | — (no log) | | | | | | |
| human_fg2 | — (no log) | | | | | | |
| human_fg3 | — (no log) | | | | | | |
| human_fg4 | — (no log) | | | | | | |
| human_fg5 | — (no log) | | | | | | |

### 3b. LLM moderator-turn function labels (EXPLORATORY)

| Transcript | allow | guide_q | probe | redirect | reflect | Redirect rate |
|-----------|-------|--------|-------|---------|--------|--------------|
| human_fg1 | 1 | 5 | 0 | 0 | 0 | 0.0% |
| human_fg2 | 0 | 5 | 0 | 0 | 0 | 0.0% |
| human_fg3 | — | — | — | — | — | — |
| human_fg4 | 0 | 5 | 0 | 0 | 0 | 0.0% |
| human_fg5 | 0 | 4 | 0 | 1 | 0 | 20.0% |
| synth_fg1 | 0 | 7 | 20 | 0 | 3 | 0.0% |
| synth_fg5 | 0 | 7 | 17 | 0 | 1 | 0.0% |

### 3c. Un-redirected drift episodes (EXPLORATORY)

Drift episode = ≥3 consecutive off-guide participant turns.
Redirected = moderator issued redirect\_refocus within next 2 moderator turns.

| Transcript | Drift episodes | Redirected | Rate | Researcher hypothesis |
|-----------|--------------|-----------|------|----------------------|
| human_fg1 | 0 | 0 | n/a | |
| human_fg2 | 0 | 0 | n/a | |
| human_fg3 | 0 | 0 | n/a | |
| human_fg4 | 0 | 0 | n/a | |
| human_fg5 | 0 | 0 | n/a | |
| synth_fg1 | 0 | 0 | n/a | |
| synth_fg5 | 0 | 0 | n/a | |

---

## Part 4 — Guide Adherence and Off-Guide Drift (EXPLORATORY)

| Transcript | Participant turns | Off-guide | Off-guide % |
|-----------|-----------------|---------|-----------|
| human_fg1 | 58 | 0 | 0.0% |
| human_fg2 | 28 | 0 | 0.0% |
| human_fg3 | 98 | 0 | 0.0% |
| human_fg4 | 39 | 0 | 0.0% |
| human_fg5 | 123 | 0 | 0.0% |
| synth_fg1 | 100 | 0 | 0.0% |
| synth_fg5 | 76 | 0 | 0.0% |

### 4a. Emergent themes cross-referenced to guide

Tier-2 open themes from the discrimination run (gemini-2.5-flash, gemini25 evaluator).
All flagged as emergent (absent from real FG1). Those that are also off-guide by LLM
labeling are the quantitative fingerprint of confessional/therapy drift.

**Synth FG1 emergent themes:**
- Lack of Motivation to Change Eating Habits (participants=4)
- Impact of Geographic Location on Food Access (participants=2)
- Unacknowledged Social Pressure and Conformity (participants=3)

**Synth FG5 emergent themes:**
- Impact of Rural Living on Food Choices (participants=2)
- Physical Signals and Dietary Adjustment (participants=3)
- The Cost of Pretending vs. Acknowledging Change (participants=3)
- Aging and the Urgency of Change (participants=3)
- Practicality and Consistency in Sustaining Change (participants=2)

Note: 'Unacknowledged Social Pressure', 'The Cost of Pretending', and 'Aging and Urgency'
are the themes most consistent with a confessional/therapy register not present in real groups.

---

## Part 5 — Repetition

### 5a. Cross-run Tier-2 theme novelty (real FG1, from existing validation data)

| Run | Themes extracted | New themes added | Cumulative unique |
|-----|-----------------|-----------------|-----------------|
| Run 1 | 4 | (baseline) | 4 |
| Run 2 | 5 | 1 | 5 |
| Run 3 | 4 | 1 | 6 |

Cross-run saturation reached by run 3 (no new themes). 1 new theme(s) added in run 2.

### 5b. Intra-transcript embedding redundancy

Mean max cosine similarity of each participant turn to ALL earlier turns in the same transcript.
Model: paraphrase-multilingual-mpnet-base-v2.
Flag threshold: ≥0.7 = near-duplicate idea.

| Transcript | N turns | Mean max sim | Frac ≥0.7 |
|-----------|---------|-------------|---------|
| human_fg1 | 58 | 0.658 | 47.4% |
| human_fg2 | 28 | 0.632 | 22.2% |
| human_fg3 | 98 | 0.671 | 39.2% |
| human_fg4 | 39 | 0.613 | 21.1% |
| human_fg5 | 123 | 0.635 | 32.0% |
| synth_fg1 | 100 | 0.747 | 73.7% |
| synth_fg5 | 76 | 0.711 | 64.0% |

---

## Summary by observation

### Observation 1: Does the moderator under-steer and let chains run?

**Structural finding: refutes the simple version of the hypothesis.**
Chain turn counts are SHORTER in synthetic than in human groups (mean 3.2–3.5 vs human range 5.6–24.6; max 5 vs human max 36). The synthetic moderator intervenes between turns more frequently, not less.

However, individual synthetic turns are 5–10× longer (median 216–263 words vs human median 22–90 words). A synthetic chain of 3 × 216 words ≈ 648 words — comparable in content depth to a human chain of 17 × 38 words ≈ 646 words. The moderator is not letting long peer-chains play out; it is allowing very long individual monologues to complete before intervening.

Moderator log confirms: 70–68% of logged actions are "allow/observe"; redirect_refocus = 6.9% (FG1) and 11.5% (FG5) of all logged actions. The LLM function labels (exploratory, FG3 missing) are inconsistent with the log — likely because long probes were coded as guide_questions — and should not be relied on.

**Net: the moderator does not let peer chains run; it lets monologues run. The depth effect is within-turn, not between-turn.**

### Observation 2: Do synthetic sessions drift off-guide into confessional register?

**LLM off-guide metric: 0% everywhere — metric FAILED.**
The labeling prompt was too permissive; content broadly related to food, masculinity, or social context scored on-guide regardless of register. Zero drift episodes were detected in both human and synthetic groups. This metric needs a stricter prompt calibrated to the confessional register before it can be used.

**Best available signal: Tier-2 emergent themes and reference density.**
- Synth FG5: emergent themes include "The Cost of Pretending vs. Acknowledging Change" and "Aging and the Urgency of Change" — both indicate an introspective/confessional register absent from real FG5.
- Synth FG1: emergent theme "Unacknowledged Social Pressure and Conformity" sits on the fringe of the same register.
- Reference density: Synth FG5 = 0.868 (87% of participant turns explicitly name another participant by name), vs human range 0.034–0.187. This abnormally high mutual-naming rate is a structural correlate of participants performing mutual validation rather than independent elaboration.

**Net: the LLM guide-adherence metric gives no signal; the Tier-2 emergent theme content and extreme reference density (Synth FG5: 87%) are consistent with a therapy-register undercurrent. Quantification of register (vs topic) requires a purpose-built prompt with register-specific calibration — the current off-guide metric cannot distinguish confessional register from on-topic discussion.**

### Observation 3: Are synthetic sessions more repetitive within-run?

**Yes — the clearest and most consistent finding.**

| Group | Mean max sim | Frac ≥0.7 |
|-------|-------------|---------|
| Human FG1–FG5 (range) | 0.613–0.671 | 21.1–47.4% |
| Synth FG1 | **0.747** | **73.7%** |
| Synth FG5 | **0.711** | **64.0%** |

Synth FG1 has 73.7% of participant turns with cosine similarity ≥0.7 to an earlier turn in the same session — 26 percentage points above the human maximum (47.4%). Synth FG5 is 17–43 pp above the human range. This quantifies the "same idea over and over with variations" observation.

Cross-run novelty (real FG1, authoritative): themes near-saturate after run 1 — only 1 new theme added in run 2, 1 more in run 3 from a base of 4. This is good saturation behavior for the deductive codebook and is unrelated to within-session repetition.

_Auto-generated by `scripts/moderator_drift_diagnostic.py`._