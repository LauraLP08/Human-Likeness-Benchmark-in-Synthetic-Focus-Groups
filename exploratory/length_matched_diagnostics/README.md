# Length-matched diagnostics

Is the human–synthetic thematic gap simply a consequence of synthetic turns being five
times longer? This strand built the coverage-by-word-count curve and evidence-localised
length-matched proxies to find out.

**Only the test lives here.** The producer and its outputs stayed in the main tree,
because `analysis/production_evaluation/metric_registry.csv` declares them and an
integrity test (`tests/test_aggregate_production_results.py`) checks that every declared
producer and artefact exists:

- producer — `scripts/d2_length_diagnostics.py`
- outputs — `analysis/production_evaluation/results/d2_coverage_by_word_count_curve.csv`,
  `d2_evidence_localized_summary.csv`, `d2_evidence_localized_excerpts.csv`

Registry status: `tier1_coverage_by_word_count_curve` is `AUTOMATIC_DIAGNOSTIC`;
`evidence_localized_length_matched_recall` and `..._precision` are `EXPLORATORY`.

The properly length-matched metrics the registry envisaged —
`tier1_length_matched_recall` and `tier1_length_matched_precision` — remain
**`DEFERRED_NOT_IMPLEMENTED`**. They were never built, and nothing here substitutes for
them.
