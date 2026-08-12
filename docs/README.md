# Documentation index

## The architecture

| Document | What it covers |
|---|---|
| `ARCHITECTURE.md` | The full system reference: roles, state, memory, participation, moderation, prompt rendering, persistence. Long; use the index at the top. |
| `operational_flow.md`, `operational_flow_verification.md` | How a session actually proceeds, and the verification that the documented flow matches the code |
| `system_operation/SESSION_RUN_SEQUENCE.md` | Turn-by-turn sequence of a run |
| `system_operation/OPERATIONAL_TRUTH_TABLE.md` | Every moderator and orchestrator decision point with its inputs and outcomes |
| `system_operation/OPERATIONAL_FLOWCHART.md` | The same as a diagram |
| `system_operation/EMERGENT_MODE_MECHANICS.md` | The turn auction, urgency scoring, bonuses, tie-breaks and the forced return to the moderator |
| `system_operation/PROMPT_RENDERING_AND_VISIBILITY.md` | What each agent can actually see at each turn — the single most important document for judging what a result means |
| `system_operation/VERBOSITY_CONTROL_MAP.md` | Every place in the system that could influence response length, and what each one does |
| `system_operation/OUTPUT_AND_AUDIT_GUIDE.md` | What gets written to disk and how to read it |
| `system_operation/CODE_ARCHITECTURE_CONSISTENCY_AUDIT.md` | Audit of documentation against code |
| `system_operation/diagrams/*.mmd` | Mermaid sources for the lifecycle diagrams |
| `audits/REPOSITORY_STRUCTURE_AUDIT.md` | Early structural audit (May 2026). Historical — it predates `scripts/` and the production campaign. |

## The evaluation framework

| Document | What it covers |
|---|---|
| `evaluation_framework.md` | The full framework: the three levels, the two validity risks and their safeguards, the evaluator gates, and a technical appendix of formulas and pseudocode |
| `evaluation_framework_summary.md` | Short version: the three levels, the 18 reported indicators, and what each `evidence_class` in the registry means |
| `TABLE1_SYSTEM_PROMPTS.md` | Table 1 in the format of Zhang et al. (2024): every prompt that produced the 30 reported sessions, with its parameters and full content |
| `length_measurement_rule.md` | The project's uniform word-counting rule — and note that the frozen structural metrics use plain `str.split()` instead, recorded as a defect, not corrected |

The operational specification of the reported evaluation lives with the data, not here:
`analysis/production_evaluation/frozen_evaluation_spec.md`,
`metric_registry.csv` and `STATISTICAL_ANALYSIS_PLAN.md`.

## Dated findings

`findings/` holds the notes that informed reported decisions:

| Note | What it establishes |
|---|---|
| `2026-06-28_length_measurement_uniform_rule.md` | Why a single word-counting rule was needed and what it is |
| `2026-06-30_full_session_validation_summary.md` | Validation of full-session runs before the production campaign |
| `2026-07-01_metrics_comparison_table.md` | Comparison of candidate metrics |
| `2026-07-18_evaluator_model_comparison.md` | Why `gemini-3.5-flash` was selected and `gemini-2.5-flash` discarded |
| `2026-07-20_tier1reach_tier2.md` | Validation of the reach and Tier-2 measures |

Findings belonging to exploratory strands are filed with those strands, under
`exploratory/*/findings/`.

## Development history

`CHANGELOG.md` records the build history. `changes/` in the working repository holds the
per-change verification records; they are not reproduced here.

## Testing artefacts

`testing/` holds four small artefact sets from **Stage 7C.5, 7C.6, 7D and 8A** — an
earlier assessment layer, calibrated on the QESB and PHIND focus-group corpora rather
than on Macho Meals. They are kept because the test suite asserts against them and
because they document how the framework was developed. They contain aggregate statistics
only, no verbatim transcript text. The QESB and PHIND transcripts themselves are
third-party data and are not redistributed; see `tests/conftest.py` for which tests skip
as a result.

This layer did **not** produce any reported result. The dissertation's Level 1–3 metrics
come from `scripts/` and `analysis/production_evaluation/`.
