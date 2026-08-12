# Snapshots

## `per_run_metrics_prefix_window_counts.csv`

`per_run_metrics.csv` as emitted **before** the window-counts fix, captured from the
completed 35/35 Batch corpus. All 30 rows have `window_words`,
`window_participant_turns` and `window_moderator_turns` blank — this file *is* the
defect.

Kept so the no-change claim can be tested against a real historical artifact rather
than against a second run of the same code, which would only demonstrate determinism.

Do not regenerate or overwrite.
