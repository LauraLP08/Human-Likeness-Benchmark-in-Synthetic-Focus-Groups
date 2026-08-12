# Statistical phase — completion report

**2026-07-31.** Automated evaluation complete. No further evaluator calls.
Governed by `STATISTICAL_ANALYSIS_PLAN.md` (finalised after automated results and
diagnostic inspections were available; **not a preregistration**).

---

## 1. Corpus — 35/35

| | |
|---|---|
| Human transcripts | **5 / 5** |
| Synthetic comparable windows | **30 / 30** |
| Replicates per FG × condition | **3**, indices [1,2,3] in all 10 cells |
| Unique Batch cache keys | **35** |
| Execution mode | `batch`, `gemini-3.5-flash`, `max_output_tokens=16384` |
| Quarantined | 1 first attempt (`macho_meals_fg5_run01`), superseded by an accepted retry; artifact preserved |

Every accepted result: `FinishReason.STOP`, 11/11 unique codebook ids in order, valid
schema, quotes verified literal against their cited turn, **0 moderator-sourced
quotes**, **0 excluded-content problems**.

---

## 2. Unit of analysis

**Five paired focus groups.** Each FG × condition value is the mean of its three
canonical replicates. Replicates estimate generator variability under a fixed
configuration — they are not independent focus groups. No test treats the 15 runs
per condition as independent.

---

## 3. Metrics

**Primary:** `tier1_subtheme_recall`, `tier1_matched_theme_precision`,
`tier1_participant_reach` (with its implementation caveat).
**Secondary:** `tier1_f1_secondary`, reported after recall and precision, never as
the headline.

All four are computed at full precision for signs, ties and differences; rounding to
4 dp happens only when artifacts are written (Amendments 1 and 2).

---

## 4. Descriptive results

### Per FG — difference (enriched − demographics-only)

| FG | recall | precision | reach | F1 *(sec.)* |
|---|---|---|---|---|
| fg1 | +0.0417 | 0.0000 *(tie)* | +0.2389 | +0.0566 |
| fg2 | **−0.0476** | −0.0833 | +0.2167 | −0.0606 |
| fg3 | +0.2667 | 0.0000 *(tie)* | +0.1056 | +0.3530 |
| fg4 | +0.2778 | +0.4222 | **−0.1704** | +0.3300 |
| fg5 | +0.0667 | +0.0500 | +0.1972 | +0.0685 |

### Across the five FGs

| Metric | mean Δ | median Δ | range | favours E / D / tie |
|---|---|---|---|---|
| recall | +0.1210 | +0.0667 | −0.0476 … +0.2778 | **4 / 1 / 0** |
| precision | +0.0778 | 0.0000 | −0.0833 … +0.4222 | **2 / 1 / 2** |
| reach | +0.1176 | +0.1972 | −0.1704 … +0.2389 | **4 / 1 / 0** |
| F1 *(sec.)* | +0.1495 | +0.0685 | −0.0606 … +0.3530 | 4 / 1 / 0 |

> **Reach — read this with the number, not after it.** The two conditions did not
> reach the floor equally: enriched runs had a forced-silence rate of **2.44%**,
> demographics-only **0.04%**. Reach counts distinct participants who contributed
> verified evidence, so it depends on who manages to speak. **The direction of the
> resulting bias is indeterminate** — fewer speakers could depress reach, while a
> silencing mechanism that removes weaker contributions could raise it. Reach is
> therefore **not a clean estimate of the effect of enrichment**. It remains a
> primary metric, as classified a priori; it has not been adjusted, and it is not
> invalid.

### Variability — two levels, never interchangeable

| Metric | condition | session-level SD (n=15) | study-replicate SD (n=3) |
|---|---|---|---|
| recall | enriched | 0.1769 | 0.0872 |
| recall | demographics-only | 0.2277 | 0.0343 |
| precision | enriched | 0.2640 | 0.0365 |
| precision | demographics-only | 0.4010 | 0.0361 |
| reach | enriched | 0.1334 | 0.1227 |
| reach | demographics-only | 0.2125 | 0.0114 |

Session-level SD mixes between-FG and within-FG replicate variation. Study-replicate
SD rests on three values and is an unstable estimate. Neither substitutes for the
other; neither is quoted without its level and n.

Context: `length_ratio_synthetic_to_human` spans **0.82× – 5.19×** (median 2.08×).

---

## 5. Exploratory inference and its limits

**No confirmatory p-values.** The exact paired sign test is exploratory and was
chosen after the results were seen. Its ceiling follows `n_effective`, not `n_total`:

| Metric | n_eff | ties | assignments | p (two-sided) | min attainable p |
|---|---|---|---|---|---|
| recall | 5 | 0 | 32 | 0.375 | 0.0625 |
| precision | **3** | **2** | **8** | 1.000 | **0.25** |
| reach | 5 | 0 | 32 | 0.375 | 0.0625 |
| F1 *(sec.)* | 5 | 0 | 32 | 0.375 | 0.0625 |

**None of these tests can reach p < .05 at any effect size.** The floor already
exceeds .05 in every case.

> **These p-values are not evidence that no effect exists.** A test that cannot
> return a significant result under any data cannot provide evidence of absence.
> They are reported only to be explicit about how little the design can support
> inferentially — the per-FG effects and the qualitative reading carry the argument.

No confidence intervals on n=15 independent observations are produced.

---

## 6. FG4 — included, with an open question

FG4 demographics-only shows **subtheme recall 0 and precision 0 across all three
replicates, with `synthetic_present_n` > 0**.

This is **zero overlap, not zero coding**: every run returned quote-verified codes at
reach 1.0. At parent-theme granularity the same runs show **theme-level recall
0.25–0.50 with precision 1.00**. The zero is specific to subtheme granularity.

**FG4 is not excluded.** There is no technical failure to justify it. A
with/without-FG4 sensitivity is emitted for every metric, flagged
`justified: false`.

**Open item `FG4-DEMO-R01-A1`.** In `macho_meals_fg4_demoonly_run01`, subtheme A.1
is the run's only asserted code, supported by three verified quotes — two of which
reference household planning and domestic division of labour rather than the
speaker's own food choice. Whether that evidence supports A.1 is a **human coding
judgement**. No code was changed automatically; `human_review_verdict` is `null` and
the item is **OPEN**. No conclusion about this cell should be finalised before it is
resolved.

---

## 7. Post-result decisions — explicitly flagged

Chosen after the results were available, therefore **exploratory, not confirmatory**:
the sign test; the two-level SD presentation; the FG4-excluded sensitivity; the FG4
zero-overlap qualitative audit; the SD ratios.

Fixed **before** any Tier-1 result existed: recall/precision primary; F1 secondary;
no composite human-likeness score; three replicates retained; FG-level comparison;
interpretive metrics withheld; no concatenation of the 15 sessions.

---

## 8. Withheld and deferred

**WITHHELD** — all interpretive metrics (agreement, disagreement, challenge,
neutral elaboration, specificity, substantive-vs-superficial elaboration, profile
continuity/consistency, hyper-exactness). They require a completed human gold
standard, which does not exist. The coder exercise is a
**PARTIAL_EMERGENT_HUMAN_REVIEW** over 7 shared units.

**DEFERRED_NOT_IMPLEMENTED** — `tier1_length_matched_recall` / `_precision`. They
require each excerpt coded independently (~300 further evaluator calls, not
scheduled). The `evidence_localized_length_matched_*` metrics are a **different
estimand**, classified EXPLORATORY, and must never be reported under the deferred
names.

---

## 9. Definitive files

**Plan and closure**
`STATISTICAL_ANALYSIS_PLAN.md` · `STATISTICAL_PHASE_COMPLETION_REPORT.md`

**Effects**
`results/primary_effects_by_fg.csv` · `results/primary_effects_summary.csv` ·
`primary_effects_fg_level.json`

**Aggregates (10 tables)**
`results/per_run_metrics.csv` (30) · `per_group_condition_summary.csv` (10) ·
`group_level_paired_effects.csv` (15) · `study_replication_summary.csv` (6) ·
`condition_level_summary.csv` (2) · `condition_comparison.csv` (3) ·
`thematic_code_presence_long.csv` (385) · `thematic_reach_long.csv` (125) ·
`structural_interaction_metrics_long.csv` (665) ·
`structural_distributions_long.csv` (2156)

**D2 (exploratory)**
`results/d2_coverage_by_word_count_curve.csv` (1852) ·
`d2_evidence_localized_excerpts.csv` (291) · `d2_evidence_localized_summary.csv` (60)

**Provenance**
`evaluator_cache/` (35 batch entries) · `evaluator_cache_legacy/` ·
`quarantine/batch_macho_meals_fg5_run01.json` ·
`batch_corpus_manifest.json` · `batch_job_corpus.json` ·
`batch_job_retry_macho_meals_fg5_run01.json` · `batch_capability_check.json` ·
`snapshots/per_run_metrics_prefix_window_counts.csv`

**FG4**
`fg4_demographics_only_qualitative_report.json` ·
`fg4_demoonly_zero_overlap_flag.json`

**Human review**
`partial_emergent_human_review_audit.json` ·
`partial_emergent_clustering/Clustering_U01_U07.xlsx` ·
`partial_emergent_clustering/CLUSTERING_GUIDE.md` ·
`gold_standard_sealed/partial_emergent_pooled_authorship.json`

---

## 10. Decisions still pending

1. **`FG4-DEMO-R01-A1`** — human verdict on whether the A.1 evidence supports that
   subtheme. Blocks any final reading of the FG4 demographics-only cell.
2. **Clustering adjudication of U01–U07** — must be done by a person. Until then no
   agreement statistic, no saturation assessment and no codebook comparison exist.
3. **P034 / P040 centrality** — MISSING pending Coder B. Not imputed.
4. **Whether to commission the ~300 calls** for the genuine length-matched metrics,
   or leave them deferred.
5. **Whether to request further coded units** beyond U01–U07 — a decision that
   depends on the clustering outcome, not on the statistics.
6. **Engagement-path asymmetry** between conditions remains a known confound on
   reach, recorded as operational metadata and not adjusted for.
