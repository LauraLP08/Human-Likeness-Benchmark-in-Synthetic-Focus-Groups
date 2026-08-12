# Macho Meals — Frozen Evaluation Specification

**Status:** PROPOSED — D1 and D3 resolved; ready to freeze on approval. All decisions logged in §14.
**Date:** 2026-07-30
**Design:** mixed methods, qualitative-dominant with embedded descriptive quantification (`QUAL + quan`).
**Primary comparative unit:** the focus group. **Secondary:** the five-group study.
**Companion file:** `metric_registry.csv` (44 metrics: 3 primary, 29 secondary incl. 1 complementary, 6 exploratory, 5 operational, 1 retired — each with evidence class, namespace, numerator, denominator, aggregation and caveats).

> **No automated evaluation has been run.** This document specifies what will be
> run. Nothing in `output/session_logs/` is modified by anything described here.

---

## 1. Research question

> To what extent does enriching agent profiles with the study's available metadata
> improve thematic, interactional and group-level correspondence with the paired
> human focus group, relative to agents configured with demographic information only?

The evaluation estimates correspondence with the **five observed human sessions**
and the **incremental effect of profile enrichment**. It does not estimate
population representativeness, and it does not attempt to reproduce any individual
participant.

---

## 2. Evaluator — frozen, effective configuration

| | |
|---|---|
| Model | **`gemini-3.5-flash`** |
| Temperature | **not transmitted** (unsupported; omitted from the request) |
| Thinking configuration | **not transmitted** — effective value is the model default, explicitly **unpinned** |
| Config | `EVALUATOR_CONFIGS["gemininext"]`, key `GEMINI_API_KEY_NEXT` |
| Basis | `docs/findings/2026-07-18_evaluator_model_comparison.md` — 2.5-flash scored 81.8% worst pairwise Gate-1 agreement against an 85% threshold and is **disqualified**; 3.5-flash scored 100% agreement, 100% quote verification, 100% code preservation; both +0.111 discrimination margin |

Not to be reopened, and not silently substituted with 2.5.

### 2.1 `thinking_level` — resolved

`EVALUATOR_CONFIGS["gemininext"]` carries `thinking_level: "medium"`. **That is a
logging label, not a request parameter.** `thematic_coding.py` attaches a
`thinking_config` only when `"2.5" in model`, so nothing is sent for
`gemini-3.5-flash`.

The SDK *can* pin it — `google-genai 2.10.0` exposes
`ThinkingConfig(thinking_level=ThinkingLevel.MEDIUM)`. It is nonetheless recorded
here as **unpinned**, because the evaluator-selection validation
(`validation_stage1_gemininext.json`) ran through this same unpinned path: **the
100% Gate-1 result that qualified this model was obtained under the model default,
not under a pinned MEDIUM.** Pinning now would run production under a configuration
that has never been validated.

The effective request configuration, which is what the cache key encodes:

```json
{"model": "gemini-3.5-flash", "temperature_transmitted": false, "temperature": null,
 "thinking_config_transmitted": false, "thinking_level_effective": "model_default_unpinned",
 "thinking_level_label_in_config": "medium"}
```

**Historical documentation correction.** Any earlier statement — in this spec, in
`PHASE0_READINESS_REPORT.md`, or in `EVALUATOR_CONFIGS` commentary — describing
`thinking_level=medium` as an effective request parameter is **incorrect** and is
superseded by this section. The recorded label in
`validation_stage1_gemininext.json` should likewise be read as a label, not as
evidence that MEDIUM was transmitted during evaluator selection.

**Residual risk, accepted:** because the value is the model default, a
provider-side change to that default would silently change evaluator behaviour
without changing the cache key. Recorded, not mitigated.

**Guard requirement.** `thematic_coding._MODEL` still defaults to the disqualified
`gemini-2.5-flash`, and `validate_tier1_reach_tier2.py` defaults to
`--evaluator gemini25`. The production pipeline must pass the frozen config
explicitly on every call and **refuse to run** if the resolved model is not
`gemini-3.5-flash`.

---

## 3. Evaluator inputs — frozen

Recorded with hashes in **`frozen_evaluator_inputs.json`**. The evaluator receives
**only** these 35 documents:

| Side | n | Input | Window |
|---|---:|---|---|
| Human | 5 | `data/datasets_transcripts/standardized/macho_meals/fg{1..5}/transcript.json` | **complete** — already begins at "Question 1." with no introduction or closing |
| Synthetic | 30 | `analysis/production_evaluation/comparable_transcripts/<run>/comparable_transcript.json` | **`q1_ask_to_end_of_last_substantive_section`** |

### 3.1 The comparable window

Approved at boundary sign-off. Algorithm `anchor_and_extend_v1`: anchor on the
latest sentence-aligned suffix of the Q1 boundary entry that still poses Question 1,
then extend backward only across residue-free sentences positively identified as
part of the ask. Retained text is a **verbatim character slice** — never
paraphrased, normalised, reconstructed, or replaced with the scripted question.

Excluded: all material before the Q1 ask (moderator introduction, instructions,
confidentiality text, participant name/location round, presentation summaries) and
the entire closing section.

Verified by a hard-fail gate of **335 checks** re-read from disk: hashes, verbatim
slices, byte-identical subsequent entries, exact closing boundary, per-run and
corpus word reconciliation. All 30 `AUTO_TRIMMED`, 0 requiring review.

**Exclusion accounting. Denominator = total words in the full source transcripts of
all 30 canonical runs = 298,006.**

| | words | % |
|---|---:|---:|
| included in window | 256,413 | 86.0% |
| excluded — pre-Q1 | 15,995 | 5.4% |
| excluded — closing | 25,598 | 8.6% |
| **total excluded** | **41,593** | **14.0%** |

### 3.2 Corpus

30 canonical sessions; `canonical_replication_index` is independent of the physical
run suffix.

| Condition | FG | rep 1 | rep 2 | rep 3 |
|---|---|---|---|---|
| enriched | FG1–FG3 | run01 | run02 | run03 |
| enriched | **FG4** | run01 | **run04** | run03 |
| enriched | FG5 | run01 | **run03** | **run04** |
| demographics-only | FG1–FG5 | demoonly_run01 | demoonly_run02 | demoonly_run03 |

Excluded, visible in the readiness audits, absent from the manifest:
`macho_meals_fg4_run02` (`ARCHIVED_TECHNICAL_OUTLIER`) and `macho_meals_fg5_run02`
(`ARCHIVED_LOST_REFLECTION_CYCLE`).

---

## 4. Cache keys and provenance

```
cache_key = sha256( transcript_sha256 | tier | codebook_sha256
                    | evaluator_prompt_sha256 | model_config_json )
```

Reuse requires an **exact** match on every component. The synthetic side keys on
the **comparable-window hash**, never the full-transcript hash, so no full-session
artefact can satisfy a comparable-window lookup.

| Component | Value |
|---|---|
| codebook | `f343ebb1ead2b969…` (11 subthemes) |
| Tier-1 prompt | `321ffd6274a26c3c…` |
| Tier-2 prompt | `46410770193daa69…` |
| Tier-2 judge prompt | `c3b1433c6b99cc8a…` |
| model config | the **effective request configuration** in §2.1 — records that neither temperature nor thinking config is transmitted, so a key can never claim a parameter that was not sent |

**No existing artefact is reusable.** Everything in `analysis/coding_frame/` was
produced with `gemini-2.5-flash` (pilot/historical) except
`validation_stage1_gemininext.json`, which is 3.5-flash evaluator-*selection*
evidence over different material and fails the transcript-hash component.
Production Tier 1 is coded fresh.

---

## 5. Metric namespaces — never pooled

| Namespace | Contents | Rule |
|---|---|---|
| `_comparable_window` | every human-comparable metric | the only namespace admissible in any human-vs-synthetic comparison |
| `_full_run_operational` | forced silences, API errors, retries, truncation, full-run word counts | operational metadata about generation |

**These two namespaces are never pooled, averaged, tabulated in the same column, or
plotted on the same axes.** A full-run word count is not comparable to a human word
count and must never be presented as if it were.

---

## 6. Outcomes

Full definitions with numerators, denominators and aggregation in
`metric_registry.csv`. **No single composite "human-likeness" index will be
constructed.** Results are reported as a convergent profile.

### 6.1 Primary — Tier 1, quote-verified

1. **`tier1_subtheme_recall`** — human subthemes reproduced by the synthetic window.
2. **`tier1_matched_theme_precision`** — synthetic subthemes also present in the human.
3. **`tier1_participant_reach`** — evidence-constrained group-level breadth, carrying the mandatory implementation caveat in §9.

**`tier1_f1` is NOT primary.** It is reclassified to **secondary/complementary**.
Recall and precision are reported **separately and ahead of** F1; F1 never
substitutes for either and is never a headline number.

Every Tier-1 "present" decision must be backed by a quote verified as a substring
of the blind text. Unverifiable codes are demoted and excluded, as in the existing
implementation.

### 6.2 Secondary — structural and interactional

Words per turn (median, IQR, full distribution), short-turn proportion, turn and
word balance, moderator turn and word share, participant–participant adjacency,
reference density, chain depth. All reported as rates **with explicit denominators
and retained raw counts**.

**D5 — short-turn threshold.** Fixed at **25 words**, pre-specified before any
scoring, and **always accompanied by the full words-per-turn distribution, median
and IQR** — never reported as a bare proportion. Sensitivity variants at **10 and
50 words** are also computed (`short_turn_proportion_10w`,
`short_turn_proportion_50w`); they are pure arithmetic over the same turn list, so
they add no cost.

### 6.3 Alternative operationalisations — `NOT_IN_REPORTED_INSTRUMENT`

Agreement, disagreement, challenge, neutral elaboration, specificity, substantive
vs superficial elaboration, group profile continuity, group profile consistency,
hyper-exactness.

**D6 — WITHHELD FROM SUBSTANTIVE REPORTING.** These may be generated in a technical
pilot to exercise the pipeline, but their results are **not interpreted, not
tabulated as findings and not reported as provisional** until the two-coder
gold-standard validation (§8) returns. There is no interim reporting of them in any
form.

### 6.4 Exploratory

Tier-2 open extraction over the comparable window; themes not observed in the
paired human transcript; missed themes; saturation and order sensitivity;
attribute–attitude relational fidelity (gated, §10).

### 6.5 Retired

**Tier 2b recall and precision are retired as fidelity evidence**, per
`docs/findings/2026-07-29_tier2b_cross_section_control.md`, which showed the matcher
tracks the guide question rather than group identity (0.0% same-group /
different-question against 41–57% same-question). Per-section theme lists may be
retained as quote-verified **description only**, and may not enter any outcome,
score, recommendation or fidelity claim.

---

## 7. Aggregation levels

**Group level.** Each synthetic run is compared to the single human transcript for
its FG. Per FG and condition, report the three canonical replicates
**individually**, then mean, median, SD, min–max, the `enriched − demographics-only`
difference, how many of the five FGs favour enriched, and the size of the condition
effect relative to between-run variation. Averaging summarises; it never replaces
the replicate values or their spread.

**Study level.** Three complete study replicates per condition, built by
`canonical_replication_index`:

- replicate 1 = FG1..FG5 rep 1
- replicate 2 enriched = FG1–FG3 run02 + **FG4 run04** + **FG5 run03**
- replicate 3 enriched = FG1–FG3 run03 + FG4 run03 + **FG5 run04**
- replicate 2/3 demographics-only = the corresponding demoonly run02 / run03

Run numbers imply no temporal, causal or shared-seed pairing. Each five-group
synthetic replicate is compared with the five-group human study. **The 15
transcripts of a condition are never concatenated and compared against 5 humans.**

---

## 8. Human gold standard — sampling plan

Purpose: validate a stratified sample of the LLM coding. Not to code all 30 runs,
and not to extrapolate validity to constructs outside the sample.

**Sample: one substantive guide question, 15 blind section units.**

| Stratum | n | Source |
|---|---:|---|
| Human | 5 | that question's section in each of FG1–FG5 |
| Enriched | 5 | canonical replication 2 — run02 for FG1–FG3, **run04 for FG4**, **run03 for FG5** |
| Demographics-only | 5 | demoonly run02 for FG1–FG5 |

Canonical replication 2 is **not** to be swapped for a better-scoring run. The FG4
and FG5 naming exceptions are archival, fixed before any outcome was seen.

Package: randomised unit IDs with a sealed mapping; instructions; codebook; an
independent worksheet per coder recording code presence/absence and supporting
quote; an adjudication worksheet; a scoring script for raw agreement and
Krippendorff's alpha; and evaluator-vs-human precision, recall and confusion matrix.

**Two independent coders.** No human results are fabricated or estimated before
both completed worksheets are returned.

---

## 9. Corpus-generation limitation — condition imbalance in forced silences

Recorded as a **limitation of the corpus**, not a defect in any run, and preserved
per run as operational metadata in `api_failure_and_fallback_audit.csv`.

The two conditions were generated by two versions of **one narrow code path**: the
handling of an invalid engagement assessment.

- earlier enriched pathway: invalid assessment → technical silence;
- later demographics-only / current pathway: retry once, silence only if the retry also fails.

Nothing else in the generation architecture, prompts, guide, models, memory or
moderator logic differed.

| Condition | engagement assessments | forced silences | rate |
|---|---:|---:|---:|
| enriched (14 earlier-path + fg4_run04) | 2,295 | 56 | **2.44%** |
| demographics-only (15 current-path) | 2,494 | 1 | **0.04%** |

14 of 15 enriched runs affected, range 1.39%–3.90%.

**Treatment, as ruled:** the 14 earlier-path runs are retained as canonical;
exposure is reported per run; **recall and precision remain primary descriptive
outcomes, with F1 secondary/complementary and never substituting for them**; reach
and interaction metrics are retained **with the implementation caveat attached
wherever they appear**.

**Direction of any thematic bias is indeterminate.** Suppressed turns reduce
opportunity to express codes (tending to lower recall) *and* to express codes
absent from the human transcript (tending to raise precision), and change who holds
the floor next. It must not be described as conservative. The code difference was
narrow; its downstream thematic consequence cannot be known exactly, because no
counterfactual transcript exists.

**D8 — DECLINED for this evaluation.** No forced-silence sensitivity analysis is
run. Forced-silence counts and rates are preserved **only** as
`_full_run_operational` metadata in `api_failure_and_fallback_audit.csv` and as the
documented limitation in this section. They are not used as a predictor, not
correlated against outcomes, and not reported as a finding.

**No claim will be made that denominator adjustment reconstructs the missing
counterfactual.**

---

## 10. Attribute–attitude relational fidelity — conceptual gate

Runs **only if** the gate is passed *before* results are seen:

1. Inventory the attributes actually available and how enriched renders them.
2. Fix a small, theoretically justified relation set a priori — e.g. meat
   attachment ↔ openness to reducing meat; masculinity-of-meat ↔ meat–masculinity
   association; vegetarianism threat ↔ rejection of vegetarianism; consumption
   habits ↔ stated practical difficulty of change.
3. Relations are **not** selected after observing which produce favourable results.
4. Derive per-FG attribute summaries and quote-grounded attitudinal outcomes.
5. Compare human / enriched / demographics-only by descriptive ranking, qualitative
   case contrast, and direction/coherence of pattern, with sensitivity **with and
   without FG3**.

In enriched, attributes are **inputs**: correspondence indicates preserved
conditioning, not held-out prediction. In demographics-only, any relation to
attributes never supplied is exploratory only.

**D7 — DEFERRED TO FUTURE WORK.** The attribute–attitude relational analysis is
**not attempted in this evaluation**. The gate above is retained as the standard any
future attempt must meet. Nothing attribute–attitude is computed, reported or
interpreted here.

This deferral is reinforced by an audit finding: the enriched prompt carries the
psychometric **construct names and scale-direction descriptors** themselves
(`condition_manipulation_audit.md` §4.1), so attribute–attitude correspondence would
be even more clearly preserved conditioning than previously stated.

**FG3 caveat** applies throughout: individual pseudonym↔survey linkage was resolved
by random 1:1 assignment after a PID error. FG3 may enter aggregate/group analyses,
is flagged `GROUP_LEVEL_ONLY_RANDOM_LINKAGE`, supports **no** individual
psychographic-fidelity claim, and every psychography-dependent metric is reported
with and without it.

---

## 11. Qualitative comparison procedures

Quantities answer *how much* and *how consistently*; the qualitative analysis
determines *what a difference means*.

1. **Matched / missed / not-observed themes** read against verified quotes, per FG
   and condition, with attention to whether a not-observed theme is plausible,
   contradictory, or methodologically uncertain.
2. **Case contrast** between the human transcript and each condition for the same
   FG, using verified quotes only.
3. **Interactional reading** of adjacency and chain structure — how disagreement is
   handled, whether elaboration builds or restates.
4. **Joint displays** (`qualitative_joint_display.md`) binding: qualitative finding
   · quantitative evidence · verified quotes · interpretation · condition and FG ·
   between-run variability · applicable limitation.

A theme absent from the paired human transcript is reported as **"not observed in
the paired human transcript"** — never as false, hallucinated or invalid.

---

## 12. Planned statistical analyses

- **FG is the primary comparative unit.** Runs are nested within FG × condition.
- Sections, turns, participants and themes are **dependent observations** and are
  never treated as independent samples.
- Report **difference sizes, direction across the five groups, and variability** —
  not significance tests as the headline.
- With n=5 groups, **no strong correlational inference**; no p-value-driven claim.
- **Absence of significance is never reported as equivalence.**
- No claim of human–synthetic equivalence, and no inference to population
  representativeness.
- Full denominators and distributions shown for every rate.
- Between-run variation is reported alongside every condition effect, because the
  discrimination work showed run-to-run spread can exceed group-level differences.

**Pre-specified descriptive comparisons:** per-FG `enriched − demographics-only`
for each primary outcome; count of FGs favouring enriched (0–5); condition effect
relative to within-cell SD across the three replicates; per-FG human-vs-synthetic
gap for each condition.

---

## 13. Known asymmetries carried into interpretation

**Volume.** Even after windowing, synthetic sessions are substantially longer than
their human counterparts:

| FG | human words | enriched mean | demographics-only mean | enriched / human |
|---|---:|---:|---:|---:|
| FG1 | 2,916 | 8,803 | 10,757 | **3.0×** |
| FG2 | 2,963 | 8,265 | 8,273 | **2.8×** |
| FG3 | 7,631 | 8,324 | 10,229 | 1.1× |
| FG4 | 3,440 | 7,417 | 6,893 | **2.2×** |
| FG5 | 6,495 | 8,577 | 7,932 | 1.3× |

More text is more opportunity to express a codeable theme. This can inflate recall
and deflate precision independently of fidelity, and the ratio varies 1.1×–3.0×
across FGs, so it is not a constant offset.

**D2 — approved as a reproducible automatic diagnostic.** Three metrics, all
`AUTOMATIC_DIAGNOSTIC`, none involving a selectively chosen excerpt:

1. **`length_ratio_synthetic_to_human`** — reported for **both** arms:
   **enriched/human and demographics-only/human**. The demographics-only ratios are
   the larger ones in FG1 (3.7×) and FG3 (1.3×), so reporting only the enriched
   ratio would understate the asymmetry.
2. **`tier1_coverage_by_word_count_curve`** — cumulative distinct quote-verified
   subthemes against words consumed from the start of the window. Fully
   deterministic, no sampling; shows directly whether a synthetic advantage is a
   length artefact.
3. **`tier1_length_matched_recall` / `tier1_length_matched_precision`** — recomputed
   on **K = 10 repeated, pre-specified length-matched excerpts** per run, each
   approximately the paired human word count, with deterministic start offsets
   (evenly spaced entry boundaries seeded by run id). **Mean and SD over the 10
   excerpts are reported.** Repeated pre-specified sampling, not one chosen excerpt.

   **Excerpts never cut an entry mid-turn.** Each excerpt begins at an entry
   boundary and ends at the **last complete entry whose inclusion does not exceed
   the target word count**; if the first entry alone already exceeds the target it
   is included whole, so an excerpt is never empty. Both the **target** and the
   **achieved** word count are recorded for every excerpt, and the achieved/target
   ratio is reported, so any residual length mismatch is visible rather than
   assumed away.

**Single human transcript per FG.** No within-group human variability can be
estimated, so a synthetic replicate's spread has no human comparator.

**Replicates are not independent groups.** The three replicates estimate generator
variability, not five additional focus groups.

---

## 14. Decision log — resolved

| # | Decision | Resolution |
|---|---|---|
| **D1** | Condition-manipulation and contamination audit | **APPROVED AND RUN.** `condition_manipulation_audit.md`, `agent_condition_difference_matrix.csv`, `psychometric_rendering_audit.csv`, `contamination_audit.json`. Manipulation operates as designed; no textual/verbatim contamination under the specified tests; one material qualification at §14.1. |
| **D2** | Length asymmetry | **APPROVED as a reproducible automatic diagnostic** — §13. Repeated pre-specified length-matched sampling (K=10, deterministic offsets, mean and SD) plus coverage-by-word-count curves. No selectively chosen excerpt. **Both** enriched/human and demographics-only/human ratios reported. |
| **D3** | `thinking_level` | **RESOLVED — §2.1.** Not transmitted; effective configuration explicitly unpinned/default. All 35 cache keys regenerated against the effective request configuration. Historical documentation corrected. |
| **D4** | Gold-standard question | **APPROVED — guide section 3, "Gender and food choice"**, conditional on auditing the 15 section boundaries **before** the coder package is prepared (§8). |
| **D5** | Short-turn threshold | **APPROVED at 25 words** as a pre-specified descriptive threshold with full distribution, median and IQR; 10- and 50-word sensitivity variants added — §6.2. |
| **D6** | Interpretive metrics | **WITHHELD** from substantive reporting until two-coder validation returns; technical-pilot generation permitted, no interpretation, no provisional reporting — §6.3. |
| **D7** | Attribute–attitude relational fidelity | **DEFERRED to future work** — §10. Not computed or reported in this evaluation. |
| **D8** | Forced-silence sensitivity analysis | **DECLINED** — §9. Forced silences retained only as operational metadata and a documented limitation. |
| — | Tier-1 F1 | **RECLASSIFIED** from primary to secondary/complementary — §6.1. |

### 14.1 Audit finding carried into interpretation

`condition_manipulation_audit.md` §4.1 verified psychometric rendering by
regenerating every disposition line with `_score_to_instruction`: **110/110 lines
reproduced verbatim, 0 raw score values leaked**. It also found that the
**construct names (70/110) and scale-direction descriptors (66/110) do reach the
prompt**, contrary to the renderer's own docstring.

This does not undermine the manipulation — those strings appear only in the enriched
arm. It does mean:

- The claim that psychometrics enter "only as latent dispositions, never as
  constructs" **must not be made.**
- Any attribute–attitude correspondence would be **preserved conditioning**, not
  held-out prediction — reinforcing D7's deferral and the §10 gate.

### 14.2 Remaining prerequisites before scoring

1. **D4 boundary audit** — the 15 section-3 units must be audited before the coder
   package is built.
2. **Guard implementation** — the pipeline must refuse any evaluator other than
   `gemini-3.5-flash` (§2.1).

---

## 15. What happens on approval

1. Freeze this document and `metric_registry.csv`.
2. (If D1 approved) run the condition-manipulation and contamination audit.
3. Build the non-destructive production pipeline: whitelist-driven, `--dry-run` and
   `--one-pair`, resumable, idempotent, non-overwriting, logging tokens/cost/retries
   /parse failures, refusing to run on any evaluator other than `gemini-3.5-flash`.
   `scripts/assess_session_batch.py` is **not** used — it globs the session-log root.
4. Preflight: dry-run listing exactly 30 sessions with FG4 run01/run04/run03 and FG5
   run01/run03/run04 and both archived run02s absent; one paired preflight
   (human FG1 vs enriched FG1 rep 2, and vs demographics-only FG1 rep 2); schema,
   blinding, quote grounding, denominators, cache, provenance and no-overwrite
   checks; confirmation that Tier 2b fidelity metrics appear in no primary outcome
   and that F1 does not replace recall and precision; and the explicit confirmation
   that **no introduction, participant presentation or closing section reached the
   evaluator**, with `comparable_window_boundaries.md` embedded.
5. **Stop at Mandatory Human Stop 2** with `PRE_EVALUATION_GATE_REPORT.md`.

_The full 30-session batch is not run until that report is approved._

---

## Amendment A1 — 2026-07-30 — D2 length-matched metrics

**The original D2 decision above is unchanged and is not retracted.** It remains the
specification of what should be measured. This amendment records what is actually
being computed before the batch, and why the two are not the same.

### What changed

`tier1_length_matched_recall` and `tier1_length_matched_precision` as specified
require each of the K=10 excerpts to be **coded independently** — the coder sees the
excerpt and nothing else. That is what makes them a length-matched *recomputation*.

Implementing them means ~**30 runs x 10 excerpts = 300 further evaluator calls**.
Those calls are **not scheduled** and are recorded here as optional future analysis.
Both metrics are therefore reclassified in `metric_registry.csv` from
`AUTOMATIC_DIAGNOSTIC` to **`DEFERRED_NOT_IMPLEMENTED`**.

### What is computed instead, and why it is not the same thing

Two new metrics are added:

* `evidence_localized_length_matched_recall`
* `evidence_localized_length_matched_precision`

They are computed offline from the positions of **already-coded, quote-verified**
evidence: a subtheme counts as localised in excerpt *k* when one of its verified
quotes falls inside that excerpt's turn range.

**This is a different estimand, and the original specification did not ask for it.**
The distinction is not cosmetic:

| | Deferred metric | Offline proxy |
|---|---|---|
| Coder input | the excerpt alone | the whole window |
| Question answered | what would a coder find here? | where did the evidence the coder already cited fall? |
| Codes with no quote in the excerpt | may still be found | cannot appear |
| Codes cited from elsewhere in the window | not visible to the coder | correctly excluded from this excerpt |
| Context effects | absent by construction | fully present |

The proxy can only ever be as good as the evaluator's quote selection: a code the
evaluator supported with one quote from turn 4 is invisible in every excerpt that
excludes turn 4, even where an independent coder would have coded it. It is
classified `EXPLORATORY`, is excluded from the `AUTOMATIC_*` parity set, and must
never be reported under the deferred metrics' names.

### Excerpt construction — one defect corrected

The construction rule in §13 is unchanged in intent, with one correction. Start
offsets were selected by modular rotation over all entry boundaries, which allowed
starts near the **end** of the window; running forward only, those cannot reach the
target and produced excerpts substantially shorter than it. Wrapping the window end
back to its start was rejected — that would splice the tail onto the head and
produce an excerpt whose word order never occurred.

Starts are now selected only from boundaries that can build a contiguous excerpt
reaching an explicit tolerance:

* **`LENGTH_MATCH_TOLERANCE = 0.90`** — "approximately length-matched" means
  achieved/target >= 0.90. Declared, not discovered: tight enough that a 10%
  shortfall cannot pass as a length match, loose enough to survive one long turn
  straddling the boundary.
* K = 10 **where enough eligible starts exist**; otherwise K and the reason are both
  recorded on every row.
* `target_words`, `achieved_words` and `achieved_over_target` are retained per
  excerpt, and min / median / max of the ratio are reported per run.
* If the whole synthetic window is shorter than the target, the full window is used
  as a single excerpt and that exception is recorded.
* An oversized first entry is still included whole and flagged — the one case where
  achieved > target legitimately.

`tier1_coverage_by_word_count_curve` is **not** affected: the registry already
defined it as cumulative distinct quote-verified subthemes by words consumed, which
is exactly what quote positions provide. It keeps its id and its `AUTOMATIC_DIAGNOSTIC`
class.
