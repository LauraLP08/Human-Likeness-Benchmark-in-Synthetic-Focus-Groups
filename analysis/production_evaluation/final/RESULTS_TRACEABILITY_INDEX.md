# Results traceability index

Built 2026-08-02. Every figure quoted in the final report resolves to a source artefact here: **16 headline figures**, **13 exploratory transportability figures**, **47 structural and per-FG exception figures**, and **43 exploratory Level 2 coverage-accumulation and lexical figures** — 119 in total. The build refuses to publish a number that two files disagree about.

Each entry records its value, source artefact, column or calculation rule, unit of analysis and namespace. The structural figures are **recomputed from source by `scripts/structural_traceability.py`**, not transcribed from the report, so a discrepancy between the two would surface as a failing figure rather than a silent agreement.

## Sealed artefacts (verified unchanged at build time)

| Artefact | SHA-256 | Verified |
|---|---|---|
| `Clustering_U01_U07.xlsx` | `d5dd0c452287387182b8dada…` | yes |
| `Emergent_Matching_Q3_RESEARCHER_V2.xlsx` | `4113068f044f52d628dd7955…` | yes |
| `Transportability_Emergent_SingleCoder.xlsx` | `c508cea736f558e070e0e424…` | yes |
| `supplementary_human_reference.json` | `076eb723b00c85479b9576ef…` | yes |

## Figure provenance

| Figure | Value | Source | Note |
|---|---|---|---|
| `deductive.recall.mean_difference` | 0.121 | `results/primary_effects_summary.csv` | FG-level, n=5 pairs |
| `deductive.precision.mean_difference` | 0.0778 | `results/primary_effects_summary.csv` | FG-level, n=5 pairs |
| `deductive.reach.mean_difference` | 0.1176 | `results/primary_effects_summary.csv` | FG-level, n=5 pairs |
| `deductive.f1_secondary.mean_difference` | 0.1495 | `results/primary_effects_summary.csv` | FG-level, n=5 pairs |
| `emergent.n_human_instances` | 44 | `matching_derivation_q3.json` |  |
| `emergent.n_machine_themes` | 30 | `matching_derivation_q3.json` |  |
| `emergent.recall` | 30/44 = 0.6818 | `bplus_evaluation_q3.json` |  |
| `emergent.strict_precision` | 24/30 = 0.8000 | `bplus_evaluation_q3.json` |  |
| `emergent.literal_evidence_quotations` | 58 | `extraction_results_q3.json` | counted from source, not copied |
| `crossmodel.corroborated` | 17/24 | `cross_model_analysis_q3.json` |  |
| `crossmodel.exact_agreement` | 0.6666666666666666 | `cross_model_analysis_q3.json` | 6/9 stable cases |
| `crossmodel.instability_rate` | 0.35714285714285715 | `cross_model_analysis_q3.json` | 5/14 |
| `crossmodel.non_verbatim_quotes` | 8/315 | `cross_model_quote_audit_q3.json` |  |
| `transportability.n_units` | 6 | `supplementary_human_reference.json` |  |
| `transportability.n_themes` | 18 | `supplementary_human_reference.json` |  |
| `cost.actual_list_batch_usd` | 1.79 | `cross_model_quote_audit_q3.json` | recomputed from token counts |

## Reconciliation checks performed

- FG-level mean differences in `primary_effects_summary.csv` recomputed from the five per-FG rows in `primary_effects_by_fg.csv`.
- The same means and direction counts cross-checked against `condition_comparison.csv`.
- Human instance count cross-checked against `human_reference_q3.json`.
- Machine theme count recomputed from `extraction_results_q3.json`.
- 58 quotations counted from source rather than copied.
- Cross-model corroborated + unresolved verified to sum to the case total.
- Supplementary theme count verified against its own per-unit denominators.
- Cost recomputed from measured token counts at the published Batch rate.

**Result: ALL FIGURES RECONCILED** — 16 figures, no contradictions found.

## Cost record

- Pre-run estimate: $1.22 (`cross_model_cost_basis.json`, retained as historical record only)
- Measured: 338,638 input + 75,551 output tokens
- Formula: `(actual_input_tokens / 1e6 * batch_input_rate) + (actual_output_tokens / 1e6 * batch_output_rate)`
- Worked: (338638/1e6 x 2.5) + (75551/1e6 x 12.5) = 0.8466 + 0.9444
- **Calculated at list Batch rate: $1.79** (`cross_model_cost_actual.json`)
- The estimate was low by $0.57 (31.8% of actual). the pre-run figure used a ~4-characters-per-token heuristic over the rendered prompts; measured input was ~53% higher than that heuristic predicted.
- This is a calculated list-rate cost, **not necessarily the amount charged**; negotiated rates are not exposed by any API endpoint.

## `EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK` — S01–S06

Exploratory check, **not a validation**. Denominators are never pooled with U01–U07/Q3, with the deductive results, or with the enriched vs demographics-only comparison. Source artefacts: `transportability_sample/hybrid_evaluation/`.

| Figure | Value | Source |
|---|---|---|
| Total pairs adjudicated | **93** | `hybrid_universe.json` |
| — historical (`ORIGINAL_SCREENED_61`) | 61 | `claude_round1_results.json` |
| — complementary (`COMPLEMENT_32`) | 32 | `claude_complement_results.json` |
| Confirmed matches | **19** | `hybrid_universe.json → rows` |
| Confirmed non-correspondences | **60** | same |
| Unresolved pairs | **14** | same |
| Recall (confirmed) | **16/18 = 0.8889** | `hybrid_metrics.json → human_state` |
| Strict confirmed precision — *primary* | **18/30 = 0.6000** | `hybrid_metrics.json → machine_state` |
| Possible precision upper bound | **23/30 = 0.7667** | adds the 5 uncertain candidates |
| Machine themes possibly matched (uncertain) | **5** | `UNRESOLVED_POSSIBLY_MATCHED` |
| Corroborated novel (automated, **not** human-validated) | **11** | `machine_only` cases |
| Adjusted precision — *optimistic exploratory ceiling* | **29/30 = 0.9667** | 18 matched + 11 novel |
| Cumulative Claude cost | **USD 4.60** at list Batch rate | `hybrid_cost_actual.json` |

19 + 60 + 14 = 93. Recall and precision denominators (18 and 30) are internal to this check and are never added to the 44-instance Q3 denominator.

`FROZEN_RULE_CLASSIFICATION = DESCRIPTIVELY_COMPATIBLE_WITH_Q3`, reported only alongside `BALANCED_INTERPRETATION = Recall-compatible with Q3 under the frozen rule, but with lower strict precision and greater thematic proliferation; evidence of transportability is mixed across fidelity dimensions.`

**Recorded deviation.** `PROTOCOL_DEVIATION_01` — one round-1 request errored and was never resent. That pair belonged to `ORIGINAL_SCREENED_61`, was **not** re-examined in the complementary audit (which covered only the 32 omitted pairs), and remains `HYBRID_UNRESOLVED` with one completed repetition; it contributes to the precision uncertainty around `S06::M6`. The protocol defined four stopping points: **1–3 passed, 4 not applied as written**. `PROTOCOL_DEVIATION_02` records that the first computation used 61 of 93 pairs; see `PROTOCOL_DEVIATIONS.md`.

### Reconciliation checks performed for this check

- 93 = 61 + 32 verified by set equality against the exact within-unit cartesian, with zero duplicates and no pair crossing a unit boundary.
- 19 + 60 + 14 = 93 recounted from `hybrid_universe.json` rather than copied.
- Every human and candidate theme verified to have been adjudicated against its complete local universe; `CONFIRMED_NOT_RECOVERED` asserted only on that basis.
- The 61 historical decisions re-derived from the sealed round-1 results and compared; byte-identical response files confirmed by SHA-256.
- Cost recomputed from measured token counts across all three Batch jobs at the verified list rate.

**Result: ALL FIGURES RECONCILED** — 13 figures, no contradictions found.

## Structural figure provenance

47 figures, each **recomputed from its source artefact** by `scripts/structural_traceability.py` rather than copied from the report; the derivation is stored in `final/structural_traceability.json`.

Replicates collapse to their FG mean before any condition mean is taken, so the **focus group remains the comparative unit (n=5 pairs)** and the three replicates estimate generator variability rather than adding independent groups.

| Figure | Value | Source | Column / rule | Unit of analysis | Namespace |
|---|---|---|---|---|---|
| `structural.total_words.human` | 4689.0 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'total_words' and condition == 'human'; mean of the per-FG means (replicates collapse to their FG mean first, so the FG stays t… | focus group (n=5) | `_comparable_window` |
| `structural.total_words.enriched` | 8277.2667 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'total_words' and condition == 'enriched'; mean of the per-FG means (replicates collapse to their FG mean first, so the FG stay… | focus group (n=5) | `_comparable_window` |
| `structural.total_words.demographics_only` | 8816.9333 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'total_words' and condition == 'demographics-only'; mean of the per-FG means (replicates collapse to their FG mean first, so th… | focus group (n=5) | `_comparable_window` |
| `structural.total_words.enriched_minus_demo` | -539.6667 | `results/structural_interaction_metrics_long.csv` | `value` — exact enriched mean minus exact demographics-only mean, rounded once at the end. NOT the difference of the two rounded means printed above — subtra… | focus group (n=5) | `_comparable_window` |
| `structural.total_words.n_fg_enriched_closer_to_human` | 3/5 | `results/structural_interaction_metrics_long.csv` | `value` — per FG, count where |enriched_fg_mean - human_fg_mean| < |demo_fg_mean - human_fg_mean|. A small-n directional count: it is not a test and does not… | focus group (n=5) | `_comparable_window` |
| `structural.participant_turns.human` | 69.2 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'participant_turns' and condition == 'human'; mean of the per-FG means (replicates collapse to their FG mean first, so the FG s… | focus group (n=5) | `_comparable_window` |
| `structural.participant_turns.enriched` | 32.1333 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'participant_turns' and condition == 'enriched'; mean of the per-FG means (replicates collapse to their FG mean first, so the F… | focus group (n=5) | `_comparable_window` |
| `structural.participant_turns.demographics_only` | 33.4667 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'participant_turns' and condition == 'demographics-only'; mean of the per-FG means (replicates collapse to their FG mean first,… | focus group (n=5) | `_comparable_window` |
| `structural.participant_turns.enriched_minus_demo` | -1.3333 | `results/structural_interaction_metrics_long.csv` | `value` — exact enriched mean minus exact demographics-only mean, rounded once at the end. NOT the difference of the two rounded means printed above — subtra… | focus group (n=5) | `_comparable_window` |
| `structural.participant_turns.n_fg_enriched_closer_to_human` | 2/5 | `results/structural_interaction_metrics_long.csv` | `value` — per FG, count where |enriched_fg_mean - human_fg_mean| < |demo_fg_mean - human_fg_mean|. A small-n directional count: it is not a test and does not… | focus group (n=5) | `_comparable_window` |
| `structural.words_per_turn_iqr.human` | 96.45 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'words_per_turn_iqr' and condition == 'human'; mean of the per-FG means (replicates collapse to their FG mean first, so the FG … | focus group (n=5) | `_comparable_window` |
| `structural.words_per_turn_iqr.enriched` | 70.5 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'words_per_turn_iqr' and condition == 'enriched'; mean of the per-FG means (replicates collapse to their FG mean first, so the … | focus group (n=5) | `_comparable_window` |
| `structural.words_per_turn_iqr.demographics_only` | 52.75 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'words_per_turn_iqr' and condition == 'demographics-only'; mean of the per-FG means (replicates collapse to their FG mean first… | focus group (n=5) | `_comparable_window` |
| `structural.words_per_turn_iqr.enriched_minus_demo` | 17.75 | `results/structural_interaction_metrics_long.csv` | `value` — exact enriched mean minus exact demographics-only mean, rounded once at the end. NOT the difference of the two rounded means printed above — subtra… | focus group (n=5) | `_comparable_window` |
| `structural.words_per_turn_iqr.n_fg_enriched_closer_to_human` | 3/5 | `results/structural_interaction_metrics_long.csv` | `value` — per FG, count where |enriched_fg_mean - human_fg_mean| < |demo_fg_mean - human_fg_mean|. A small-n directional count: it is not a test and does not… | focus group (n=5) | `_comparable_window` |
| `structural.short_turn_proportion_25w.human` | 0.3443 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'short_turn_proportion_25w' and condition == 'human'; mean of the per-FG means (replicates collapse to their FG mean first, so … | focus group (n=5) | `_comparable_window` |
| `structural.short_turn_proportion_25w.enriched` | 0.0 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'short_turn_proportion_25w' and condition == 'enriched'; mean of the per-FG means (replicates collapse to their FG mean first, … | focus group (n=5) | `_comparable_window` |
| `structural.short_turn_proportion_25w.demographics_only` | 0.0 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'short_turn_proportion_25w' and condition == 'demographics-only'; mean of the per-FG means (replicates collapse to their FG mea… | focus group (n=5) | `_comparable_window` |
| `structural.short_turn_proportion_25w.enriched_minus_demo` | 0.0 | `results/structural_interaction_metrics_long.csv` | `value` — exact enriched mean minus exact demographics-only mean, rounded once at the end. NOT the difference of the two rounded means printed above — subtra… | focus group (n=5) | `_comparable_window` |
| `structural.short_turn_proportion_25w.n_fg_enriched_closer_to_human` | 0/5 | `results/structural_interaction_metrics_long.csv` | `value` — per FG, count where |enriched_fg_mean - human_fg_mean| < |demo_fg_mean - human_fg_mean|. A small-n directional count: it is not a test and does not… | focus group (n=5) | `_comparable_window` |
| `structural.turn_balance_gini.human` | 0.1954 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'turn_balance_gini' and condition == 'human'; mean of the per-FG means (replicates collapse to their FG mean first, so the FG s… | focus group (n=5) | `_comparable_window` |
| `structural.turn_balance_gini.enriched` | 0.0725 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'turn_balance_gini' and condition == 'enriched'; mean of the per-FG means (replicates collapse to their FG mean first, so the F… | focus group (n=5) | `_comparable_window` |
| `structural.turn_balance_gini.demographics_only` | 0.0885 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'turn_balance_gini' and condition == 'demographics-only'; mean of the per-FG means (replicates collapse to their FG mean first,… | focus group (n=5) | `_comparable_window` |
| `structural.turn_balance_gini.enriched_minus_demo` | -0.016 | `results/structural_interaction_metrics_long.csv` | `value` — exact enriched mean minus exact demographics-only mean, rounded once at the end. NOT the difference of the two rounded means printed above — subtra… | focus group (n=5) | `_comparable_window` |
| `structural.turn_balance_gini.n_fg_enriched_closer_to_human` | 2/5 | `results/structural_interaction_metrics_long.csv` | `value` — per FG, count where |enriched_fg_mean - human_fg_mean| < |demo_fg_mean - human_fg_mean|. A small-n directional count: it is not a test and does not… | focus group (n=5) | `_comparable_window` |
| `structural.chain_depth.human` | 12.8 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'chain_depth' and condition == 'human'; mean of the per-FG means (replicates collapse to their FG mean first, so the FG stays t… | focus group (n=5) | `_comparable_window` |
| `structural.chain_depth.enriched` | 2.0218 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'chain_depth' and condition == 'enriched'; mean of the per-FG means (replicates collapse to their FG mean first, so the FG stay… | focus group (n=5) | `_comparable_window` |
| `structural.chain_depth.demographics_only` | 2.0178 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'chain_depth' and condition == 'demographics-only'; mean of the per-FG means (replicates collapse to their FG mean first, so th… | focus group (n=5) | `_comparable_window` |
| `structural.chain_depth.enriched_minus_demo` | 0.0039 | `results/structural_interaction_metrics_long.csv` | `value` — exact enriched mean minus exact demographics-only mean, rounded once at the end. NOT the difference of the two rounded means printed above — subtra… | focus group (n=5) | `_comparable_window` |
| `structural.chain_depth.n_fg_enriched_closer_to_human` | 4/5 | `results/structural_interaction_metrics_long.csv` | `value` — per FG, count where |enriched_fg_mean - human_fg_mean| < |demo_fg_mean - human_fg_mean|. A small-n directional count: it is not a test and does not… | focus group (n=5) | `_comparable_window` |
| `structural.moderator_word_share.human` | 0.0253 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'moderator_word_share' and condition == 'human'; mean of the per-FG means (replicates collapse to their FG mean first, so the F… | focus group (n=5) | `_comparable_window` |
| `structural.moderator_word_share.enriched` | 0.1079 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'moderator_word_share' and condition == 'enriched'; mean of the per-FG means (replicates collapse to their FG mean first, so th… | focus group (n=5) | `_comparable_window` |
| `structural.moderator_word_share.demographics_only` | 0.1157 | `results/structural_interaction_metrics_long.csv` | `value` — filter metric_id == 'moderator_word_share' and condition == 'demographics-only'; mean of the per-FG means (replicates collapse to their FG mean fir… | focus group (n=5) | `_comparable_window` |
| `structural.moderator_word_share.enriched_minus_demo` | -0.0077 | `results/structural_interaction_metrics_long.csv` | `value` — exact enriched mean minus exact demographics-only mean, rounded once at the end. NOT the difference of the two rounded means printed above — subtra… | focus group (n=5) | `_comparable_window` |
| `structural.moderator_word_share.n_fg_enriched_closer_to_human` | 4/5 | `results/structural_interaction_metrics_long.csv` | `value` — per FG, count where |enriched_fg_mean - human_fg_mean| < |demo_fg_mean - human_fg_mean|. A small-n directional count: it is not a test and does not… | focus group (n=5) | `_comparable_window` |
| `deductive.recall.fg2.difference_enriched_minus_demo` | -0.0476 | `results/primary_effects_by_fg.csv` | `difference_enriched_minus_demo` — row metric == 'recall' and fg == 'fg2'; the exception noted in the report narrative | focus group (mean of 3 replicates per cell) | `_comparable_window` |
| `deductive.recall.fg4.difference_enriched_minus_demo` | 0.2778 | `results/primary_effects_by_fg.csv` | `difference_enriched_minus_demo` — row metric == 'recall' and fg == 'fg4'; the exception noted in the report narrative | focus group (mean of 3 replicates per cell) | `_comparable_window` |
| `deductive.precision.fg2.difference_enriched_minus_demo` | -0.0833 | `results/primary_effects_by_fg.csv` | `difference_enriched_minus_demo` — row metric == 'precision' and fg == 'fg2'; the exception noted in the report narrative | focus group (mean of 3 replicates per cell) | `_comparable_window` |
| `deductive.precision.fg4.difference_enriched_minus_demo` | 0.4222 | `results/primary_effects_by_fg.csv` | `difference_enriched_minus_demo` — row metric == 'precision' and fg == 'fg4'; the exception noted in the report narrative | focus group (mean of 3 replicates per cell) | `_comparable_window` |
| `deductive.reach.fg2.difference_enriched_minus_demo` | 0.2167 | `results/primary_effects_by_fg.csv` | `difference_enriched_minus_demo` — row metric == 'reach' and fg == 'fg2'; the exception noted in the report narrative | focus group (mean of 3 replicates per cell) | `_comparable_window` |
| `deductive.reach.fg4.difference_enriched_minus_demo` | -0.1704 | `results/primary_effects_by_fg.csv` | `difference_enriched_minus_demo` — row metric == 'reach' and fg == 'fg4'; the exception noted in the report narrative | focus group (mean of 3 replicates per cell) | `_comparable_window` |
| `deductive.f1_secondary.fg2.difference_enriched_minus_demo` | -0.0606 | `results/primary_effects_by_fg.csv` | `difference_enriched_minus_demo` — row metric == 'f1_secondary' and fg == 'fg2'; the exception noted in the report narrative | focus group (mean of 3 replicates per cell) | `_comparable_window` |
| `deductive.f1_secondary.fg4.difference_enriched_minus_demo` | 0.33 | `results/primary_effects_by_fg.csv` | `difference_enriched_minus_demo` — row metric == 'f1_secondary' and fg == 'fg4'; the exception noted in the report narrative | focus group (mean of 3 replicates per cell) | `_comparable_window` |
| `deductive.fg4_demographics_only.subtheme_recall` | 0.0 | `results/per_run_metrics.csv` | `tier1_subtheme_recall` — rows fg == 'fg4' and condition == 'demographics-only'; column 'tier1_subtheme_recall' across the three replicates. Reported to qualify the subtheme… | run (3 replicates of one FG cell) | `_comparable_window` |
| `deductive.fg4_demographics_only.subtheme_precision` | 0.0 | `results/per_run_metrics.csv` | `tier1_matched_theme_precision` — rows fg == 'fg4' and condition == 'demographics-only'; column 'tier1_matched_theme_precision' across the three replicates. Reported to qualify the … | run (3 replicates of one FG cell) | `_comparable_window` |
| `deductive.fg4_demographics_only.theme_level_recall` | 0.25-0.5 | `results/per_run_metrics.csv` | `tier1_theme_level_recall` — rows fg == 'fg4' and condition == 'demographics-only'; column 'tier1_theme_level_recall' across the three replicates. Reported to qualify the subth… | run (3 replicates of one FG cell) | `_comparable_window` |
| `deductive.fg4_demographics_only.theme_level_precision` | 1.0 | `results/per_run_metrics.csv` | `tier1_theme_level_precision` — rows fg == 'fg4' and condition == 'demographics-only'; column 'tier1_theme_level_precision' across the three replicates. Reported to qualify the su… | run (3 replicates of one FG cell) | `_comparable_window` |

**On the `n_fg_enriched_closer_to_human` rows.** Each is a count of focus groups in which the enriched mean is nearer the human mean than the demographics-only mean is. These are small-n directional counts. They do not provide conclusive evidence of a consistent structural advantage, and they are not a statistical test. No test against a chance baseline was performed, so no claim about chance may be made from them in either direction.

**On rounding.** Every value is rounded once, for presentation only. Differences are computed from the exact condition means and the `closer_to_human` counts compare exact per-FG means, so no figure here is derived by operating on an already-rounded number.

**On the FG4 theme-level rows.** They are recorded to qualify the subtheme-level zeros: the same three runs return theme-level recall 0.25–0.50 at precision 1.00. This shows the result depends on the operational level of the codebook. It does **not** establish that granularity causally produced the result.

## Level 2 coverage accumulation and lexical provenance

**EXPLORATORY.** Derived from existing artefacts by `scripts/saturation_analysis.py` and `scripts/lexical_analysis.py`. No API call, no new human coding, no embeddings. The general indicators appear in the original methodology, but these operationalisations were finalised **after the main results were known** and are not pre-registered in this form.

**Estimand caveat.** The Tier 1 codebook is fixed a priori at 11 subthemes, so these are *coverage-accumulation* curves, not code emergence. They are **not** equivalent to Guest et al. (2016) / Hennink et al. (2019) code saturation. Meaning saturation is **not assessed in this study and cannot be inferred from fixed-codebook coverage counts**. A curve endpoint is the total observed for that replicate and does **not** demonstrate a plateau. A plateau criterion (mean increment to every later focus group below 0.5 subthemes) exists in `saturation_analysis.json` for audit only and is flagged **POST_HOC_ARBITRARY_NON_SUBSTANTIVE**. It is deliberately absent from the Results and Discussion drafts and supports no claim.

**Unit.** Accumulation runs per **study replicate × condition** — one complete pass over FG1–FG5 at a single replication index. Order bias is controlled exhaustively over all 120 orderings of the five focus groups.

| Figure | Value | Source | Rule | Unit | Namespace |
|---|---|---|---|---|---|
| `saturation.accumulation.human.mean_curve` | [7.2, 9.3, 10.1, 10.6, 11] | `results/thematic_code_presence_long.csv` | mean cumulative distinct subthemes over all 120 orderings of FG1–FG5 within this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.human.final_total_codes` | 11/11 | `results/thematic_code_presence_long.csv` | distinct subthemes observed anywhere in this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.enriched.R1.mean_curve` | [3.6, 4.2, 4.8, 5.4, 6] | `results/thematic_code_presence_long.csv` | mean cumulative distinct subthemes over all 120 orderings of FG1–FG5 within this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.enriched.R1.final_total_codes` | 6/11 | `results/thematic_code_presence_long.csv` | distinct subthemes observed anywhere in this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.enriched.R2.mean_curve` | [4, 4.9, 5.7, 6.4, 7] | `results/thematic_code_presence_long.csv` | mean cumulative distinct subthemes over all 120 orderings of FG1–FG5 within this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.enriched.R2.final_total_codes` | 7/11 | `results/thematic_code_presence_long.csv` | distinct subthemes observed anywhere in this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.enriched.R3.mean_curve` | [2.8, 3.3, 3.6, 3.8, 4] | `results/thematic_code_presence_long.csv` | mean cumulative distinct subthemes over all 120 orderings of FG1–FG5 within this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.enriched.R3.final_total_codes` | 4/11 | `results/thematic_code_presence_long.csv` | distinct subthemes observed anywhere in this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.demographics-only.R1.mean_curve` | [2.8, 4.1, 5, 5.6, 6] | `results/thematic_code_presence_long.csv` | mean cumulative distinct subthemes over all 120 orderings of FG1–FG5 within this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.demographics-only.R1.final_total_codes` | 6/11 | `results/thematic_code_presence_long.csv` | distinct subthemes observed anywhere in this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.demographics-only.R2.mean_curve` | [2.4, 3.1, 3.5, 3.8, 4] | `results/thematic_code_presence_long.csv` | mean cumulative distinct subthemes over all 120 orderings of FG1–FG5 within this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.demographics-only.R2.final_total_codes` | 4/11 | `results/thematic_code_presence_long.csv` | distinct subthemes observed anywhere in this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.demographics-only.R3.mean_curve` | [2.2, 2.8, 3.2, 3.6, 4] | `results/thematic_code_presence_long.csv` | mean cumulative distinct subthemes over all 120 orderings of FG1–FG5 within this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.accumulation.demographics-only.R3.final_total_codes` | 4/11 | `results/thematic_code_presence_long.csv` | distinct subthemes observed anywhere in this study replicate | study replicate (5 FGs) | `_comparable_window` |
| `saturation.across_replicates.enriched.final_total_range` | 4-7 (mean 5.6667) | `results/thematic_code_presence_long.csv` | min–max of the three study-replicate totals; replicates summarised as mean and range, never as independent FGs | study replicate | `_comparable_window` |
| `saturation.enriched.CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS` | 9/11 | `results/thematic_code_presence_long.csv` | union over 5 FGs × 3 replicates. **NOT a study replicate's repertoire** and must never be reported as one | 15 sessions | `_comparable_window` |
| `saturation.across_replicates.demographics-only.final_total_range` | 4-6 (mean 4.6667) | `results/thematic_code_presence_long.csv` | min–max of the three study-replicate totals; replicates summarised as mean and range, never as independent FGs | study replicate | `_comparable_window` |
| `saturation.demographics-only.CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS` | 6/11 | `results/thematic_code_presence_long.csv` | union over 5 FGs × 3 replicates. **NOT a study replicate's repertoire** and must never be reported as one | 15 sessions | `_comparable_window` |
| `saturation.human.final_total_codes` | 11/11 | `results/thematic_code_presence_long.csv` | distinct subthemes in the five human focus groups | study (5 FGs) | `_comparable_window` |
| `saturation.codes_never_observed_in_any_synthetic_session` | ['B.3', 'C.2'] | `results/thematic_code_presence_long.csv` | present in the human reference, absent from all 30 synthetic runs | subtheme | `_comparable_window` |
| `saturation.theme_recurrence` | per subtheme × per study replicate | `results/thematic_code_presence_long.csv` | number of FGs (of 5) containing each subtheme, reported separately for human, enriched R1–R3 and demographics-only R1–R3 | subtheme × study replicate | `_comparable_window` |
| `saturation.prevalence.human_prevalence_per_code` | code by code | `results/thematic_code_presence_long.csv` | FGs (of 5) containing each subtheme in the human reference; 4/4/3 terciles withdrawn because they split tied codes alphabetically; tie-preserving bands retained as exploratory | subtheme | `_comparable_window` |
| `lexical.unadjusted_jaccard.content_min3_nostop` | human 0.1676, enriched 0.3174, demo 0.3155 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | mean pairwise vocabulary overlap between participants; **CONFOUNDED by unequal speaker output** | focus group (n=5) | `_comparable_window` |
| `lexical.unadjusted_jaccard.content_min1_nostop` | human 0.1674, enriched 0.3186, demo 0.3169 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | mean pairwise vocabulary overlap between participants; **CONFOUNDED by unequal speaker output** | focus group (n=5) | `_comparable_window` |
| `lexical.unadjusted_jaccard.all_min3_withstop` | human 0.2381, enriched 0.3811, demo 0.3794 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | mean pairwise vocabulary overlap between participants; **CONFOUNDED by unequal speaker output** | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.content_min3_nostop@100::jaccard` | human 0.1138, enriched 0.1628, demo 0.1571 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.content_min3_nostop@100::jensen_shannon_distance` | human 0.8703, enriched 0.8184, demo 0.825 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.content_min3_nostop@100::cosine_similarity` | human 0.28, enriched 0.3918, demo 0.3769 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.content_min1_nostop@100::jaccard` | human 0.1127, enriched 0.1636, demo 0.1575 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.content_min1_nostop@100::jensen_shannon_distance` | human 0.8716, enriched 0.8181, demo 0.8251 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.content_min1_nostop@100::cosine_similarity` | human 0.277, enriched 0.3912, demo 0.3757 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.all_min3_withstop@100::jaccard` | human 0.1686, enriched 0.2045, demo 0.1988 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.all_min3_withstop@100::jensen_shannon_distance` | human 0.8007, enriched 0.7664, demo 0.772 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.all_min3_withstop@100::cosine_similarity` | human 0.4241, enriched 0.4898, demo 0.4804 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.all_min3_withstop@200::jaccard` | human 0.2014, enriched 0.2536, demo 0.2472 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.all_min3_withstop@200::jensen_shannon_distance` | human 0.7376, enriched 0.6871, demo 0.695 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.budget_equalised.all_min3_withstop@200::cosine_similarity` | human 0.5661, enriched 0.6492, demo 0.6326 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | equal per-participant token budget, up to 10 deterministic offsets each used exactly once; decisive (n_fg = 5 in every condition) | focus group (n=5) | `_comparable_window` |
| `lexical.sensitivity_verdict` | 12/12 decisive specifications agree; 9 excluded as thin | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | a specification is decisive only when all three conditions retain 5 focus groups at that budget | focus group (n=5) | `_comparable_window` |
| `lexical.diversity.mattr_w50` | human 0.7496, enriched 0.8203, demo 0.8145 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | MATTR is **less** length-sensitive than raw TTR, not length-insensitive; a diversity diagnostic, NOT evidence about voice | focus group (n=5) | `_comparable_window` |
| `lexical.diversity.mattr_w100` | human 0.6373, enriched 0.708, demo 0.7023 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | MATTR is **less** length-sensitive than raw TTR, not length-insensitive; a diversity diagnostic, NOT evidence about voice | focus group (n=5) | `_comparable_window` |
| `lexical.diversity.mattr_w200` | human 0.5225, enriched 0.5758, demo 0.5708 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | MATTR is **less** length-sensitive than raw TTR, not length-insensitive; a diversity diagnostic, NOT evidence about voice | focus group (n=5) | `_comparable_window` |
| `lexical.diversity.ttr` | human 0.173, enriched 0.12, demo 0.1148 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | MATTR is **less** length-sensitive than raw TTR, not length-insensitive; a diversity diagnostic, NOT evidence about voice | focus group (n=5) | `_comparable_window` |
| `lexical.numeral_proxy_per_1000_words` | human 1.1927, enriched 0.0489, demo 0.2157 | `comparable_transcripts/` + `datasets_transcripts/standardized/macho_meals/` | descriptive PROXY; does **not** discharge the registry hyper-exactness indicator, which remains `LLM_CODED_HUMAN_VALIDATION_REQUIRED` | focus group (n=5) | `_comparable_window` |

**Reconciliation.** Source is 35 documents (5 human focus groups + 30 synthetic runs) × 11 subthemes = 385 rows. Total word counts for all 30 synthetic runs in `lexical_analysis.json` match `results/structural_interaction_metrics_long.csv` exactly, confirming both analyses use the same comparable window. Verified by `tests/test_saturation_and_lexical.py`.

---

<!-- BEGIN GENERATED: cross-model audit and human coding review -->

## Cross-model absence audit, salience sensitivity and human coding review

### Hierarchy of evidence

| Layer | Analysis | Status |
|---|---|---|
| **1 · PRIMARY** | `ORIGINAL_GEMINI` / `ORIGINAL_LOWER` | the reported result |
| **2 · CROSS-MODEL SENSITIVITY** | 16 `ABSENCE_CONTESTED` cells under MID/UPPER and `CONTESTED_AS_PRESENT` | sensitivity input |
| **3 · HUMAN-CODING SENSITIVITY** | `OCA_REMOVE_A1_ONLY` — the explicit A.1 verdict | sensitivity input |
| **4 · EXPLORATORY VARIANT** | `OCA_REMOVE_A1_ADD_PROPOSED_A3` — the proposed alternative | exploratory only |

These layers are **never pooled**, and no sensitivity result is presented as corrected ground truth. The three strands of evidence — the Gemini primary coding, the blinded cross-model audit and the targeted blinded human coding review — are reported separately throughout.

### Absence audit — all 260 Gemini absence decisions

| Outcome | n |
|---|---:|
| `AUDITOR_DID_NOT_FIND_EVIDENCE` | 180 |
| `ABSENCE_UNRESOLVED` | 64 |
| `ABSENCE_CONTESTED` | 16 |
| `ABSENCE_CORROBORATED` | **0** |

Concurrence control: **121 of 125** originally-present cells concurred, with **0** flatly contradicted. Repetition agreement **349/385**. Evidence-gate failures **2/770** assessments.

**`AUDITOR_DID_NOT_FIND_EVIDENCE` records only that the auditor searched and reported nothing.** It is never a confirmed absence and is not paraphrased as one. Contested cells are sensitivity inputs; none was recoded.

### Thematic-salience sensitivity

| Treatment | tau-b defined | Changed vs primary |
|---|---:|---:|
| ORIGINAL / LOWER (**primary**) | 27/30 | — |
| MID | 30/30 | 15 |
| UPPER | 30/30 | 15 |

The three FG4 demographics-only runs move from undefined (`SYNTHETIC_SIDE_CONSTANT`) to **defined and negative**. The "6 undefined → defined" figure is **three runs under two sensitivity treatments, not six distinct runs.** There are 0 transitions in the other direction.

MID and UPPER differ in **one** run only. Movements occur in **both directions**, so the sensitivity does not uniformly favour either condition. The 64 unresolved cells **enter no treatment**.

### Targeted blinded human coding review

A targeted blinded human coding review of **FG4 demographics-only run01**, subtheme **A.1**, returned the verdict **`DOES_NOT_SUPPORT_A1`** with **A.3** proposed as the better fit. Reviewer LCLP, 2026-08-03. **The review is complete and its verdict is recorded**; it is carried into the results as a sensitivity analysis, not as a change to the primary coding.

**Removing A.1 is the explicit human verdict.** **Adding A.3 is exploratory**, because the form did not explicitly adjudicate A.3 as present. The A.3 reach of 3/3 is **inferred** from the three cited turns and is **not human-validated reach**.

| Layer | Variant | Recall | Precision | F1 |
|---|---|---|---|---|
| 1 · primary | `ORIGINAL_GEMINI` | 0.0 | 0.0 | **0.0** |
| 3 · human-coding sensitivity | `OCA_REMOVE_A1_ONLY` | 0.0 | **undefined** | **undefined** |
| 4 · exploratory | `OCA_REMOVE_A1_ADD_PROPOSED_A3` | 0.0 | 0.0 | **0.0** |

A complete mismatch between two non-empty code sets is a **measured zero**, so F1 is 0.0 in layers 1 and 4. Under layer 3 the synthetic side asserts nothing, the precision denominator is empty, and precision and F1 are **undefined** — the only place a blank is correct.

**Defined and undefined denominators, reported separately** — FG4 demographics-only:

| Variant | Precision defined | Precision undefined | F1 defined | F1 undefined |
|---|---:|---:|---:|---:|
| `ORIGINAL_GEMINI` | 3 | 0 | 3 | 0 |
| `OCA_REMOVE_A1_ONLY` | 2 | 1 | 2 | 1 |

No condition-level or FG-level mean moves; the denominator behind the FG4 demographics-only mean drops from 3 to 2 and is printed rather than absorbed.

### Combined sensitivity: A.1 → A.3 reclassification

For FG4 demographics-only R1 the combined treatment applies the reclassification the targeted blinded human coding review adjudicated: **A.1 removed, A.3 added**. It is a sensitivity analysis derived from independent human review, **not a modification of the primary deductive result**.

| Subtheme | ORIGINAL | CROSS-MODEL | COMBINED |
|---|---:|---:|---:|
| A.1 | 5 | 5 | **4** |
| A.3 | 2 | 3 | **3** |

**Counts are distinct focus groups.** The blinded auditor contested A.3 in this same run, and the human review proposes A.3 for it as well — the two independent reviews **converge on one focus group**, which is therefore counted **once**. A.3 accordingly moves 2 → 3, not 2 → 4; A.1 moves 5 → 4. Across the table, **15** recurrence rows change under the combined treatment.

### Traceability

Internal item identifier: **`OCA-001` / `FG4-DEMO-R01-A1`** — the join key to the artefacts below. Reader-facing prose names the review, not the ticket.

| Figure | Source artefact |
|---|---|
| 260 absence outcomes, 121/125, 349/385, 2/770 | `salience_absence_audit/absence_audit_complete.json` |
| tau-b 27/30, 30/30, 30/30; 15 changed; 6 transitions over 3 runs | `salience_absence_audit/salience_sensitivity_final.json` |
| 14 cross-model recurrence rows changed | `salience_absence_audit/across_group_recurrence_sensitivity.csv` |
| 15 combined recurrence rows changed; A.1 5→4, A.3 2→3 | `salience_absence_audit/combined_recurrence_sensitivity.csv` |
| 16 contested cells, LOWER/MID/UPPER | `salience_absence_audit/participant_breadth_bounds.csv` |
| human coding review verdict, integrity, 90/90 source match | `open_coding_adjudication/oca_integration.json` |
| Stage-1 and Stage-2 raw responses | `salience_absence_audit/stage{1,2}_raw_responses.json` |
| combined sensitivity figure | `analysis/figures/render_thematic_salience_sensitivity_heatmap.py` |

---

<!-- END GENERATED: cross-model audit and human coding review -->
