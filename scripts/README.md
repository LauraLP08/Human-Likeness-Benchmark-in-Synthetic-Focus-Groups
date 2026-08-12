# Scripts

91 scripts, grouped below by what they do. All are run from the **repository root**:

```bash
py scripts/<name>.py --help
```

Scripts belonging to exploratory strands are not here — see `exploratory/README.md`.
Every script's own docstring is the authority on what it does and refuses to do; several
of them state the failure mode they exist to prevent, and those are worth reading before
changing anything.

---

## Generation

| Script | Purpose |
|---|---|
| `run_full_session.py` | Run one session to **natural guide completion** with a `--max-turns` safety cap. This is what produced the 30 reported sessions. |
| `run_parallel_sessions.py` | Launch N sessions as independent OS processes. Process management only — each child is an ordinary `run_full_session.py`. |
| `run_batch.py` | Sequential batch runner (older; other workflows depend on it) |
| `run_live_pilot.py` | Short controlled live pilot against the real API |
| `build_fg_agents.py` | Build persona payloads from participant metadata |
| `build_macho_meals_fg3_agents.py` | FG3-specific agent build |
| `standardize_focus_group_guide.py` | Turn a discussion guide into the YAML the configs embed |

## Preparing the human side

| Script | Purpose |
|---|---|
| `extract_focus_group_transcript_text.py` | Pull raw text out of `.docx` / `.pdf` transcripts |
| `standardize_human_focus_group_transcript.py` | The parser. Turns extracted text into `transcript.json` with per-turn speaker roles and `canonical_speaker_id`. Dataset-specific branches — this is one of the three components that did not port to a new domain. |
| `compare_raw_to_standardized_transcripts.py` | Raw-vs-standardised consistency audit |
| `verify_human_baseline_standardization.py` | 12-check verification (C01–C12); exits non-zero on a blocking finding |
| `process_human_baselines_claude_v1.py` | Pipeline driver for the human-baseline standardisation |
| `audit_human_baseline_standardization.py`, `package_and_verify_standardized_claude_v1.py` | Audit and packaging for the same |

The last four were built for the QESB and PHIND corpora, which are **not redistributed
here**. The parser itself is what produced
`data/datasets_transcripts/standardized/macho_meals/`.

## Run readiness and pre-evaluation audits

| Script | Purpose |
|---|---|
| `phase0_macho_meals_readiness_audit.py` | Produces `run_readiness_audit.csv`: per-run turns, words, roster match, section completion, forced silences, hashes, verdict |
| `phase1_condition_manipulation_audit.py` | Confirms the two conditions really differ in the agent payloads |
| `build_comparable_window.py` | Derives the human-comparable analytical window — one rule for all 30 runs |
| `comparable_window_boundary.py` | Boundary derivation and audit for those windows |
| `freeze_evaluator_inputs.py` | Hashes every document the evaluator is allowed to see, so later work can prove it read the same bytes |
| `migrate_cache_effective_config.py` | Cache-key migration to record *effective* rather than *labelled* request configuration |

## Level 1 — thematic coding and aggregation

| Script | Purpose |
|---|---|
| `thematic_coding.py` | The coding library. **The only place the codebook is read**, and it runs strictly after transcripts exist. |
| `production_eval_pipeline.py` | The pipeline. Hard-guards the evaluator to `gemini-3.5-flash`, because a forgotten argument elsewhere would silently select the disqualified model. |
| `tier1_completeness.py` | Rejects truncated evaluator output. Absence is never inferred from a response that stopped early. |
| `aggregate_production_results.py` | Rolls Tier-1 results up at session, group, paired-effect and study level |
| `build_primary_effects_tables.py` | Primary effects at the frozen unit of analysis — the focus group, n=5 pairs |
| `collapse_metric.py` | Replicate-to-FG collapse used throughout |
| `salience_hierarchy.py`, `salience_hierarchy_outputs.py` | Participant-breadth and across-group recurrence hierarchy |
| `render_salience_heatmap.py` | Salience heatmap |
| `batch_capability_check.py`, `batch_corpus_manifest.py`, `batch_retry_single.py`, `preflight_*.py` | Batch-API capability probes, corpus manifests, retries and preflight checks |

## Level 1 — validation and audit

| Script | Purpose |
|---|---|
| `validate_thematic_measure.py` | The three evaluator gates: reproducibility, discrimination, citation validity |
| `run_evaluator_comparison.py` | Head-to-head comparison of candidate evaluator models |
| `validate_tier1_reach_tier2.py` | Validation of the reach and Tier-2 measures |
| `generate_human_anchor.py`, `human_anchor_score.py` | Build the blind human coder's package and score it |
| `gold_standard_workbooks.py`, `build_gold_standard_package.py`, `score_gold_standard.py`, `build_coder_b_workbook.py` | The two-coder gold-standard exercise. `score_gold_standard.py`'s docstring lists what it refuses to do — read it. |
| `absence_audit_*.py` | Blinded cross-model audit of all 260 absence decisions, in stages, with an explicit rules module |
| `salience_sensitivity_final.py`, `combined_sensitivity.py` | LOWER / MID / UPPER sensitivity treatments and their combination with the human coding review |
| `oca_integration.py`, `build_fg4_a1_adjudication_form.py` | The targeted blinded human coding review of FG4 demographics-only, subtheme A.1 |
| `tier2b_segmentation.py` | Guide-question segmentation utility. Its own strand is retired (`exploratory/tier2b_guide_question/`), but the gold-standard package builder imports it. |

## Level 2 — interaction process (and the Level 1 saturation analysis)

| Script | Purpose |
|---|---|
| `saturation_analysis.py` | **Level 1**, Figure 5. Coverage-accumulation curves per study replicate × condition, over all 120 orderings of FG1–FG5. Not code saturation — read the estimand caveat in the docstring. |
| `lexical_analysis.py` | Budget-equalised lexical diagnostics. Exists because an unadjusted vocabulary-overlap comparison measures how much each speaker said. |
| `consensus_dynamics_events.py` | Response acts (participant → participant) under a frozen contrastive-marker dictionary |
| `consensus_dynamics_metrics.py` | Metrics over those acts |
| `consensus_intraturn_dispersion.py` | Intra-turn semantic dispersion — a geometric instrument, independent of the dictionary |
| `consensus_specificity_gliner.py` | Specificity via GLiNER, with entity types written from the study's own definition and frozen |
| `consensus_specificity_place_split.py` | Splits out stated-origin geography, which is excluded from all conditions |
| `consensus_specificity_proxy.py` | The earlier regex proxy, superseded by the GLiNER version |
| `d2_length_diagnostics.py` | Coverage-by-word-count curve and length-matched proxies (exploratory; see `exploratory/length_matched_diagnostics/`) |
| `structural_metrics_transportability.py` | Structural metrics over an arbitrary corpus. Used by the platform UI. |

## Level 3 — speaker distinctiveness

| Script | Purpose |
|---|---|
| `agent_fidelity_corpus.py` | Builds the standardised-length fragments the tests run on |
| `agent_fidelity_stylometry.py` | The attribution test and the lexical distinctiveness measures. Its docstring is explicit about what these do **not** show. |
| `agent_fidelity_preflight.py` | Preflight gates |
| `agent_fidelity_audit_packages.py`, `agent_fidelity_audit_v2.py` | Blinded audit packages for the interpretive indicators |
| `agent_fidelity_hx_repair.py`, `agent_fidelity_hx_score.py` | Hyper-exactness items and scoring |
| `agent_fidelity_pc_score.py` | Profile-consistency scoring |
| `agent_fidelity_registry_diff.py` | Proposed registry rows, diffed before any registry change |

The two speaker-distinctiveness indicators are the automatic stylometric ones: attribution
lift and lexical distinctiveness. The registry's `NOT_IN_REPORTED_INSTRUMENT` rows record alternative operationalisations that
would need a coding exercise per corpus; the benchmark measures these constructs with the
automatic producers above.

## External benchmark (exploratory, registry-declared)

`mator_bertscore_metrics.py`, `mator_agreement_strict.py`, `mator_completeness.py`,
`mator_comparison_table.py`, `mator_registry_rows.py` — see
`exploratory/mator_external_benchmark/README.md`.

`mator_bertscore_metrics.py::load_units` is the pattern to copy when writing anything
that enumerates runs: it reads the run list from `frozen_evaluator_inputs.json`,
SHA-256-verifies every input, and reports anything on disk that is not in the frozen file
as **explicitly excluded** rather than silently skipped.

## Final products

| Script | Purpose |
|---|---|
| `structural_traceability.py` | **Recomputes** every structural figure from its source artefact rather than transcribing it from the report, so a discrepancy surfaces as a failure |
| `build_final_products.py` | Assembles `FINAL_RESULTS_TABLES.xlsx` and `RESULTS_TRACEABILITY_INDEX.md`, reading every figure from its source artefact |

## Legacy session assessment

`assess_session.py`, `assess_session_batch.py`, `assess_human_baseline.py` drive the
`assessment/` package — an earlier generic session-QA layer (mechanical integrity, flags,
recommendation rules). It produced **no reported result**; it is kept because its unit
tests document how the framework developed.
