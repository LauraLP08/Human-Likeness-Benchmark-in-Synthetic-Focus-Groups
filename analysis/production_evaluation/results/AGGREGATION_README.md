# Result tables — schema fixed, populated

Generated 2026-07-31T07:35:46.424385+00:00 by `scripts/aggregate_production_results.py`.

## Levels

| Level | Table | Unit |
|---|---|---|
| 1 | `per_run_metrics.csv` | one synthetic run vs its paired human transcript |
| 2 | `per_group_condition_summary.csv` | FG x condition over 3 canonical replicates |
| 2b | `group_level_paired_effects.csv` | enriched - demographics-only, per FG |
| 3 | `study_replication_summary.csv` | five-group realisation by replication index |
| 4 | `condition_level_summary.csv` | across the 3 study replicates, per condition |
| 4b | `condition_comparison.csv` | enriched vs demographics-only, across the 5 FGs |
| long | `thematic_code_presence_long.csv`, `thematic_reach_long.csv` | one row per code per result |
| long | `structural_interaction_metrics_long.csv` | one row per structural/interaction metric per result |
| long | `structural_distributions_long.csv` | the raw vectors behind the structural summaries |
| evidence | `emergent_and_missed_theme_evidence.json` | not-observed and missed themes |

**10 CSV tables in total**, plus the JSON evidence file.

## `structural_distributions_long.csv`

The registry does not accept a bare summary statistic: `words_per_turn_median` must
be reported "with IQR and the full distribution, never the mean alone", both Gini
coefficients must carry "the raw per-participant vector", and `chain_depth` must
report "the distribution and the maximum, not only the mean". This table holds
those raw vectors so every summary above can be recomputed by hand.

| `distribution_id` | one row per | supports |
|---|---|---|
| `words_per_turn` | participant turn | `words_per_turn_median`, `words_per_turn_iqr` |
| `participant_turn_counts` | participant | `turn_balance_gini` |
| `participant_word_counts` | participant | `word_balance_gini` |
| `chain_depth` | uninterrupted participant chain | `chain_depth` |

`element_label` is `Participant N` by order of first appearance, never a speaker
name: the human transcripts carry pseudonyms and an audit table is the wrong place
to reintroduce them.

## Metrics NOT produced here

`structural_interaction_metrics_long.csv` marks each row `registry` or
`derived_support`, so a frozen measure is distinguishable from a convenience count.
Of the 28 frozen `AUTOMATIC_*` metrics, 20 are computed here. The rest:

* 5 `_full_run_operational` metrics live in `run_readiness_audit.csv` and
  `api_failure_and_fallback_audit.csv` (artifact and column verified by test);
* 1 D2 diagnostic (`tier1_coverage_by_word_count_curve`) comes from
  `scripts/d2_length_diagnostics.py`, which is written and tested but **has not been
  run** — it needs Tier-1 results. Accounting for a metric is not having computed it.

`tier1_length_matched_recall` / `_precision` are **`DEFERRED_NOT_IMPLEMENTED`** and
are therefore no longer in the `AUTOMATIC_*` set at all. They require each excerpt to
be coded independently (~300 further evaluator calls, not scheduled). The offline
`evidence_localized_length_matched_*` metrics are a **different estimand**, not an
approximation of them, are classified `EXPLORATORY`, and a test forbids the deferred
names from appearing in any proxy output. See frozen_evaluation_spec.md Amendment A1
(2026-07-30).

## Hard completeness gate

Aggregation refuses to run unless the result set has exactly
5 human transcripts,
3 runs per FG x condition,
5 FGs per study replicate and
3 study replicates per condition.
A partial batch would otherwise produce a mean over 2 replicates that reads exactly
like a mean over 3.

## Rules encoded in the schema

* Replicate values are retained in `*_values` columns — the mean never replaces them.
* The F1 column is `tier1_f1_secondary`; recall and precision precede it everywhere.
* Every reach row carries `reach_implementation_caveat`, and `participants_n` is the
  explicit denominator.
* `within_cell_sd_pooled` is the variance-weighted pooled SD with df; the
  standardised effect is omitted when it is undefined or zero.
* `n_fgs_favouring_enriched` lives in `condition_comparison.csv`, because it is a
  comparison between conditions, not a property of one.
* `namespace` is an explicit column; `_full_run_operational` metrics stay in
  `api_failure_and_fallback_audit.csv` and are never joined here.
* `tier1_salience_hierarchy` uses only codes that are present, quote-verified and
  carry a non-null reach on both sides. A missing reach is never read as 0.0; the
  excluded counts and an explicit undefinition reason are separate columns.
* Interpretive metrics have no column until the gold standard returns.
* A synthetic-only theme is recorded as `synthetic_only_not_observed_in_human`.
