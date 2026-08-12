# Mator et al. (2025) external benchmark

Five metrics comparable to Table 4 of Mator et al. (2025), so this corpus can be placed
against a published external result rather than only against itself.

**Only the tests live here.** The producers and artefacts stayed in the main tree,
because `analysis/production_evaluation/metric_registry.csv` declares them (five rows,
namespace `_comparable_window`, evidence class `AUTOMATIC_PROXY_EXPLORATORY`) and an
integrity test checks that every declared producer and artefact exists:

- producers — `scripts/mator_bertscore_metrics.py`, `mator_agreement_strict.py`,
  `mator_completeness.py`, `mator_comparison_table.py`, `mator_registry_rows.py`
- artefacts — `analysis/production_evaluation/mator_comparable/`

Read `analysis/production_evaluation/mator_comparable/MATOR_REPLICATION_REPORT.md` before
citing anything from this layer. The short version, and the reason this strand is
exploratory rather than reported, is in `exploratory/README.md`: only two of Mator's five
rows carry information, and raw BERTScore "relevance" sits at its own unrelated-pair
baseline on both sides.
