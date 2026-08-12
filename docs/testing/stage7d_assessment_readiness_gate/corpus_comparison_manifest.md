# Corpus Comparison Manifest

Important: Human baselines and synthetic grocery runs may be used as soft process references, but topic/content differences must be explicitly documented. Do not allow theme-equivalence claims between unrelated topics.

| corpus_or_run_id | corpus_type | topic_domain | source_stage | artifact_path | comparable_to | comparison_level_allowed | comparison_level_not_allowed | reason | caveats |
|---|---|---|---|---|---|---|---|---|---|
| human_baseline_* | Human | Remote Work / Employment | Stage 7C.0 | data/transcripts/human_baseline_standardization_claude_v1/* | Synthetic (Process) | PROCESS_BACKTEST_SOFT_REFERENCE | OUTCOME_THEME_NOT_ALLOWED_YET | Outcome requires thematic equivalence | Do not allow theme-equivalence claims across unrelated topics |
| stage6* | Synthetic | Grocery / Various | Stage 6 | docs/testing/stage6* | Human (Process) | PROCESS_SHAPE_ONLY | OUTCOME_THEME_NOT_ALLOWED_YET | Topic mismatch, outcome requires specific coding | Do not allow theme-equivalence claims across unrelated topics |
