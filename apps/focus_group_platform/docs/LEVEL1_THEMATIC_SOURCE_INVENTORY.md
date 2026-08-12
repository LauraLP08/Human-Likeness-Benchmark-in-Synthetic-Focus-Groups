# Level 1 (THEMATIC_FIDELITY) — source inventory

Registered before any adapter was written, and pinned in
`platform_core/thematic.py::SOURCES`. `verify_sources()` checks path, schema, row
count and sha256 on every run; a changed source is an error, not a different answer.

The platform never writes to any of these files.

## Sources

| artefact | producer | unit of analysis | rows | coding basis | sha256 (16) |
|---|---|---|---|---|---|
| `analysis/production_evaluation/results/per_run_metrics.csv` | `scripts/aggregate_production_results.py` | one synthetic run | 30 | PRIMARY | `7a013c0314ca8f38` |
| `analysis/production_evaluation/results/primary_effects_by_fg.csv` | `scripts/build_primary_effects_tables.py` | one FG × condition cell | 20 | PRIMARY | `e2f7cc55147eab71` |
| `analysis/production_evaluation/results/per_group_condition_summary.csv` | `scripts/aggregate_production_results.py` | one FG × condition cell | 10 | PRIMARY | `3d755a2270985276` |
| `analysis/production_evaluation/results/study_replication_summary.csv` | `scripts/aggregate_production_results.py` | one study replicate | 6 | PRIMARY | `1abf6fb6a8094f44` |
| `analysis/production_evaluation/results/thematic_code_presence_long.csv` | `scripts/aggregate_production_results.py` | one subtheme × run / human FG | 385 | PRIMARY | `1003c730c50adef3` |
| `analysis/production_evaluation/results/thematic_reach_long.csv` | `scripts/aggregate_production_results.py` | one **present** subtheme × run / human FG | 125 | PRIMARY | `af2424f5531aac8c` |
| `analysis/production_evaluation/final/salience_hierarchy_per_run.csv` | `scripts/salience_hierarchy_outputs.py` | one synthetic run | 30 | PRIMARY | `fd572c6a3c939f0f` |
| `analysis/production_evaluation/final/salience_hierarchy_by_fg_condition.csv` | `scripts/salience_hierarchy_outputs.py` | one FG × condition cell | 10 | PRIMARY | `77b8614a16cd786b` |
| `analysis/production_evaluation/final/salience_hierarchy_study_replicates.csv` | `scripts/salience_hierarchy_outputs.py` | one study replicate | 6 | PRIMARY | `82bf458536f0ff31` |
| `analysis/production_evaluation/salience_absence_audit/across_group_recurrence_sensitivity.csv` | `scripts/absence_audit_final.py` | one subtheme × condition × replicate | 77 | **BOTH** | `a8efbb0162446754` |
| `analysis/production_evaluation/salience_absence_audit/combined_recurrence_sensitivity.csv` | `scripts/combined_sensitivity.py` | one subtheme × condition × replicate | 77 | **BOTH** | `d8cb10a04732ce02` |
| `analysis/production_evaluation/salience_absence_audit/salience_sensitivity_final.json` | `scripts/salience_sensitivity_final.py` | one synthetic run × three treatments | — | **BOTH** | `90e8e77822e75fb0` |
| `analysis/figures/inductive_theme_accumulation_main.csv` | `analysis/figures/render_inductive_theme_accumulation_main.py` | one sequence position × realisation | 135 | PRIMARY | `db0831a5a3e2d3e7` |

### The three BOTH sources

They hold primary and sensitivity coding **in different columns of the same file**,
never in the same column. The adapters read one column per call and label the result:

- `across_group_recurrence_sensitivity.csv` — `n_fgs_original` is PRIMARY and is the
  golden for recurrence; `n_fgs_contested_as_present` is the adjudicated sensitivity.
- `combined_recurrence_sensitivity.csv` — `n_fgs_ORIGINAL` is PRIMARY;
  `n_fgs_CROSS_MODEL` and `n_fgs_COMBINED` are two sensitivity treatments.
- `salience_sensitivity_final.json` — declares `primary = ORIGINAL_LOWER` and
  `primary_unmodified = true`. The reader asserts that flag and refuses to return a
  table if it is ever false.

No function adds a primary and a sensitivity figure together.

## Golden sources by route

| route | golden | what it pins |
|---|---|---|
| per run | `per_run_metrics.csv` | recall, precision, reach, and the counts behind them |
| A — FG × condition | `primary_effects_by_fg.csv` | the three run values and the cell mean |
| A — range | `per_group_condition_summary.csv` | min, max, n per cell |
| B — study replicate | `study_replication_summary.csv` | the mean across FG1–FG5 |
| recurrence | `across_group_recurrence_sensitivity.csv#n_fgs_original` | 77 subtheme × cell counts |
| ordering agreement | `salience_hierarchy_by_fg_condition.csv` | median / min / max tau-b per cell |

## Not a source

`FINAL_RESULTS_TABLES.xlsx` sheet `3_Structural_Interaction` is Level 2 and is not
read here. `structural_interaction_metrics_long.csv` and
`structural_distributions_long.csv` likewise belong to INTERACTION_PROCESS.

## Deferred

`guide_coverage` — no definition, no producer, no artefact. Recorded as
`DEFERRED_NOT_IMPLEMENTED`; explicitly **not** inferred from thematic recall, whose
denominator is the human codebook rather than the guide.
