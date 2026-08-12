# Claim → artefact map

Every quantitative claim in the dissertation, and the file it comes from. Paths are
relative to the repository root. `PE/` abbreviates
`analysis/production_evaluation/`.

Three claims in the dissertation have **no frozen artefact** in this repository; they
are marked **⚠ derived outside the repository** below, with the raw data that would let
you recompute them. Everything else resolves to a file.

A machine-built index of 119 figures — each recomputed from source rather than
transcribed from the report — is at `PE/final/RESULTS_TRACEABILITY_INDEX.md`. The
build refuses to publish a number that two files disagree about.

---

## Naming crosswalk

The dissertation presents **three levels and twelve indicators** (Appendix D), and this
repository follows that labelling throughout — in `docs/evaluation_framework_summary.md`,
in `docs/evaluation_framework.md` and in this file. Saturation sits inside Level 1, as
indicator 3.

| Dissertation level | Indicators (Appendix D) | Registry `tier` |
|---|---|---|
| **Level 1 · Thematic fidelity** | 1 thematic repertoire coverage · 2 theme recurrence across focus groups · 3 theme coverage accumulation · 4 thematic recall · 5 thematic precision · 6 participant reach | `Tier 1`, `Tier 2` |
| **Level 2 · Interaction process** | 7 turn-length distribution · 8 between-focus-group variation in turn length · 9 internally resolved contrast · 10 contextual-reference density | `structural`, `interaction`, `interpretive` |
| **Level 3 · Speaker distinctiveness** | 11 cross-question speaker attribution · 12 within-question lexical similarity | `interpretive`, `exploratory` |

Appendix D carries one footnote: consensus — the proportion of responses to another
participant expressing agreement, disagreement or neither — is noted there as a further
indicator to measure where feasible. It is not among the twelve and no value for it is
reported.

**`metric_registry.csv` has 51 rows, not 12, and that is not a contradiction.** The registry
is an operational ledger rather than a statement of the benchmark: besides the twelve
indicators it carries operational diagnostics (API error rate, forced silences, truncation),
length proxies, the five Mator comparability rows, and retired or superseded entries. Each
row's `evidence_class` says what it is: `AUTOMATIC_VALIDATED`, `AUTOMATIC_DIAGNOSTIC`,
`EXPLORATORY`, `AUTOMATIC_PROXY_EXPLORATORY`, `REPORTED_VIA_AUTOMATIC_PRODUCER`,
`NOT_IN_REPORTED_INSTRUMENT`, `DEFERRED_NOT_IMPLEMENTED` or `RETIRED_NOT_FOR_FIDELITY`.

---

## Design and corpus

| Claim | Value | Artefact |
|---|---|---|
| 22 persona agents from the 5 Macho Meals focus groups | 22 | `agents/macho_meals/` (+ `_manifest.json`), `agents/macho_meals_demoonly/` |
| 5 human focus groups, 373 turns, 22 participants matched to 22 agents | FG1 64, FG2 33, FG3 104, FG4 44, FG5 128 | `data/datasets_transcripts/standardized/macho_meals/MACHO_MEALS_STANDARDIZATION_REPORT.md`; per-focus-group pairing in each `identity_reconciliation.json`. FG3's pairing is a random 1:1 assignment of genuine FG3 survey rows to speaker names, so FG3 supports group-level comparison only — §7.1 of that report. The reported analyses are group-level. |
| 30 synthetic sessions (5 FG × 2 conditions × 3 replicates) | 30 | `PE/canonical_experiment_manifest.csv` — with SHA-256 of each run's transcript, config, agents, guide and moderator prompt |
| Per-run operational audit (turns, words, roster match, forced silences, verdict) | 30 rows | `PE/run_readiness_audit.csv` |
| Two enriched replicates superseded (fg4_run02, fg5_run02) | — | `PE/canonical_experiment_manifest.csv` (`physical_run` uses run01/run03/run04 for fg4 and fg5); the superseded logs are in `output/session_logs/` |
| Condition manipulation is real (enriched carries fields demographics-only does not) | — | `PE/condition_manipulation_audit.md`, `PE/agent_condition_difference_matrix.csv` |
| **⚠ Median session cost USD 2.54 (range 1.39–3.98), total USD 75.38** | — | **Derived outside the repository** from token counts in `output/session_logs/<run>/api_calls.jsonl` (fields `input_tokens`, `output_tokens`, `model`) priced at list rates. No aggregate table is stored. |
| **⚠ Median duration 23.3 min (13.1–42.2), 28 of 30 sessions with valid timing** | — | **Derived outside the repository** from `timestamp` fields in the same `api_calls.jsonl` files. The two excluded sessions are excluded from the timing calculation only. |

---

## The evaluation instrument

| Claim | Value | Artefact |
|---|---|---|
| 11-subtheme codebook from the original study | 11 (A.1–A.3, B.1–B.4, C.1–C.3, D) | `analysis/coding_frame/CodeBook_Macho Meals.xlsx`; machine-readable at `PE/gold_standard_sealed/codebook_reference.csv`; rendered by `analysis/figures/plot_macho_meals_codebook.py` |
| 51 registered metrics with unit, aggregation and evidence class | 51 | `PE/metric_registry.csv` |
| Pre-registered evaluation spec and hashed evaluator inputs | — | `PE/frozen_evaluation_spec.md`, `PE/frozen_evaluator_inputs.json` |
| Analytical window is comparable across sides | — | `PE/comparable_window_boundaries.md`, `PE/comparable_window_audit.csv`; producer `scripts/build_comparable_window.py` |
| **Gate 1 · reproducibility** — identical decisions across 5 codings (threshold 0.85) | 1.00 | `analysis/coding_frame/validation_stage1_gemininext.json → gate1_repeatability.all_way_agreement` |
| **Gate 2 · discrimination** — matched pair scores above mismatched pair | margin **+0.1111** (0.4444 vs 0.3333) | same file → `gate2_discrimination.recall_margin` |
| **Gate 3 · citation validity** — every code carries a verbatim quotation | 1.00 | same file → `gate3_quote_validity`; per-decision audit in `analysis/coding_frame/quote_match_audit.jsonl` |
| Gemini 2.5 failed reproducibility and was discarded | — | `analysis/coding_frame/validation_stage1_gemini25.json`; `docs/findings/2026-07-18_evaluator_model_comparison.md` |
| Blind human coder: agreement 15.2 pp higher with 3.5-flash than 2.5 | — | `analysis/coding_frame/human_anchor/human_anchor_results.json` (per-model `agreement`, `recall_vs_human`, `precision_vs_human` on each transcript); coder package and worksheets in the same directory |
| **⚠ Original researchers' coding: 47 of 55 theme × group decisions agreed, κ = 0.670** | 47/55 | **Derived outside the repository.** The evaluator's side of the comparison *is* here: the 55 human theme × FG cells are the `condition == 'human'` rows of `PE/results/thematic_code_presence_long.csv`. The original team's side comes from the published Macho Meals paper and is not stored as a file. |
| Every evaluator response retained, keyed by request hash | 37 entries | `PE/evaluator_cache/`; full call log at `analysis/coding_frame/gemini_calls.jsonl` |
| Truncated evaluator output is rejected, never read as absence | — | `scripts/tier1_completeness.py` |
| Evaluator model is hard-guarded to `gemini-3.5-flash` | — | `scripts/production_eval_pipeline.py` |

---

## Level 1 · Thematic fidelity

| Claim | Value | Artefact |
|---|---|---|
| Human transcripts cover all 11 themes | 11/11 | `PE/results/thematic_code_presence_long.csv`; `PE/final/saturation_analysis.json` |
| Enriched replicates cover 5.7 themes on average, demographics-only 4.7 | 5.6667 (range 4–7) / 4.6667 (range 4–6) | `PE/final/saturation_analysis.json`; index rows `saturation.across_replicates.*.final_total_range` |
| Two codes never observed in any synthetic session | `B.3`, `C.2` | `PE/results/thematic_code_presence_long.csv` |
| **Fig. 4** — theme presence across human and synthetic sets | — | `PE/final/salience_hierarchy.json`; rendered by `analysis/figures/render_thematic_salience_heatmap.py` → `thematic_salience_heatmap.png` |
| Mean recall — enriched vs demographics-only | **0.3906** vs **0.2695** (difference 0.121) | `PE/results/condition_level_summary.csv`; difference in `PE/results/primary_effects_summary.csv` |
| Mean precision | **0.7878** vs **0.7100** (difference 0.0778) | same |
| Mean participant reach — human, enriched, demographics-only | human 0.589, enriched 0.771, demo 0.654 (difference 0.1176) | `PE/results/thematic_reach_long.csv`; difference in `PE/results/primary_effects_summary.csv` |
| Per-focus-group effects, including the FG2 and FG4 exceptions | — | `PE/results/primary_effects_by_fg.csv` |
| FG4 demographics-only recorded zero recall and zero precision at subtheme level | 0.0 / 0.0, with theme-level recall 0.25–0.50 at precision 1.00 | `PE/results/per_run_metrics.csv`; `PE/fg4_demographics_only_qualitative_report.json`, `PE/fg4_demoonly_zero_overlap_flag.json` |
| **Fig. 6** — recall, precision and reach by focus group | — | `analysis/figures/plot_level1_thematic_fidelity.py` → `level1_thematic_fidelity_by_focus_group.png` |
| The n=5 sign test cannot reach p<.05 and does not replace the per-FG effects | — | `PE/results/primary_effects_summary.csv → inference_note`; `PE/STATISTICAL_ANALYSIS_PLAN.md` |

### Robustness checks behind Level 1

| Check | Result | Artefact |
|---|---|---|
| Blinded cross-model audit of all 260 absence decisions | 180 `AUDITOR_DID_NOT_FIND_EVIDENCE`, 64 unresolved, 16 contested, **0 corroborated** | `PE/salience_absence_audit/absence_audit_complete.json` |
| Concurrence control on originally-present cells | 121/125 concurred, 0 contradicted | same |
| Salience sensitivity under LOWER / MID / UPPER treatments | tau-b defined 27/30 → 30/30; 15 rows changed; movements in both directions | `PE/salience_absence_audit/salience_sensitivity_final.json` |
| Targeted blinded human coding review (FG4 demo-only, A.1) | verdict `DOES_NOT_SUPPORT_A1`; A.3 proposed but **exploratory**, not adjudicated | `PE/open_coding_adjudication/oca_integration.json` |

**None of these is a correction to the primary coding.** They are reported as separate
layers and never pooled — see the hierarchy-of-evidence table in
`PE/final/RESULTS_TRACEABILITY_INDEX.md`.

---

### Level 1 (cont.) · Theme saturation

The dissertation presents Figure 5 inside **Level 1**. The repository's framework
document and metric registry classify the same measure as its own level
("Nivel 2 — Saturación", registry tier `Tier 2`). Same numbers, different grouping —
see the naming crosswalk at the top of this file.

| Claim | Value | Artefact |
|---|---|---|
| **Fig. 5** — when each set stopped adding themes | — | `PE/final/saturation_analysis.json`; rendered by `analysis/figures/render_repertoire_saturation_by_replicate.py` |
| Human mean accumulation curve over all 120 orderings of FG1–FG5 | [7.2, 9.3, 10.1, 10.6, 11] | `PE/final/saturation_analysis.json` |
| Enriched replicate curves (R1/R2/R3 totals) | 6/11, 7/11, 4/11 | same |
| Demographics-only replicate curves | 6/11, 4/11, 4/11 | same |
| Producer | — | `scripts/saturation_analysis.py` |

**Estimand caveat, stated in the artefact itself.** The codebook is fixed a priori at 11
subthemes, so these are *coverage-accumulation* curves, not code emergence. They are not
equivalent to Guest et al. (2017) / Hennink et al. (2019) code saturation, and meaning
saturation is not assessed. A curve endpoint is the total observed for that replicate and
does not demonstrate a plateau. The plateau criterion inside
`saturation_analysis.json` is flagged `POST_HOC_ARBITRARY_NON_SUBSTANTIVE` and supports
no claim.

---

## Level 2 · Interaction process

| Claim | Value | Artefact |
|---|---|---|
| **Fig. 7** — distribution of participant turn length | — | `PE/results/structural_distributions_long.csv` (`distribution_id == 'words_per_turn'`); rendered by `analysis/figures/render_interaction_verbosity_distribution.py` |
| Human per-group median turn length 48.9 words; synthetic medians ≈ 240 | — | `PE/results/structural_interaction_metrics_long.csv` (`words_per_turn_median`) |
| 34.4% of human turns under 25 words; **0.0%** in both synthetic conditions | human 0.3443, enriched 0.0, demo 0.0 | same (`short_turn_proportion_25w`); recomputed in `PE/final/structural_traceability.json` |
| Shortest synthetic turn in all 30 sessions was 55 words | — | `PE/results/structural_distributions_long.csv` (minimum over synthetic `words_per_turn`) |
| Human group medians varied widely (**between-group CV 51.0%**); synthetic did not (**5.6% enriched, 6.6% demo**) | human 50.98%, enriched 5.62%, demo 6.63% | `PE/results/structural_interaction_metrics_long.csv` (`words_per_turn_median`), CV over the five per-FG values, replicates averaged within FG, sample SD ÷ mean. **Between-group**, i.e. the quantity that varies group identity — not the within-group CV across replicates of one group (2.9–15.2% demo, 5.3–9.1% enriched), which holds group identity fixed and does not support a claim about group identity. |
| Moderator word share — human 0.0253, enriched 0.1079, demo 0.1157 | — | same; `PE/final/structural_traceability.json` |
| Chain depth — human 12.8, enriched 2.02, demo 2.02 | — | same |
| Turn-balance Gini — human 0.1954, enriched 0.0725, demo 0.0885 | — | same |
| 779 participant-to-participant response acts (319 human, 460 synthetic) | 779 | `PE/consensus_dynamics/FROZEN_SPEC.md`, `PE/consensus_dynamics/response_acts.csv` |
| Multi-position turns: **9.8% synthetic vs 0.3% human** (31×) | — | `PE/consensus_dynamics/INTRATURN_DISPERSION_RESULTS.md`; producer `scripts/consensus_dynamics_events.py` |
| The contrastive-marker dictionary is frozen and hashed (59 divergence, 37 alignment, 13 attenuator markers) | — | `PE/consensus_dynamics/FROZEN_SPEC.md` (SHA-256 of dictionary, producer script and `response_acts.csv`) |
| The opening-clause window was chosen before the comparison, and why | — | same file, §"Por qué la ventana de apertura" — the whole-turn variant gave 33.7% vs 5.0%, driven by mid-turn constructions that mark internal argument structure, not stance toward the previous speaker. No dictionary entry was removed. |
| **Fig. 7 (illustrative)** — structure of participant turns | — | `analysis/figures/render_interaction_verbatims.py` |
| **Fig. 8** — contextual reference density per 100 participant words | human **3.168**, enriched **1.674**, demo **1.273** | `PE/consensus_dynamics/specificity_gliner_by_act.csv`, `specificity_gliner_entities.csv`; frozen values and the place-exclusion correction in `PE/consensus_dynamics/SPECIFICITY_PLACE_CORRECTED.md`; rendered by `analysis/figures/render_interaction_specificity.py` |
| Named foods or dishes subset | human **2.016**, enriched **0.886**, demo **0.238** | same |
| Stated-origin geography excluded from all conditions | — | `PE/consensus_dynamics/place_gazetteer_frozen.json`, `SPECIFICITY_PLACE_CORRECTED.md`; producer `scripts/consensus_specificity_place_split.py` |
| Entity types are researcher-written prompts, frozen and listed in full | — | `PE/consensus_dynamics/specificity_gliner_spec.json`; producer `scripts/consensus_specificity_gliner.py` |

---

## Level 3 · Speaker distinctiveness

| Claim | Value | Artefact |
|---|---|---|
| Attribution accuracy — human 46.8% against a 25.5% chance baseline | 0.4681 vs 0.2553 (+21.3 pp) | `PE/agent_fidelity/agent_fidelity_stylometry.json`; tabulated in `analysis/figures/agent_fidelity_attribution_lift.csv` |
| Enriched 32.5%, demographics-only 37.7%, both near their own chance baselines | 0.3248 (chance 0.3120) / 0.3767 (chance 0.3094) | same |
| **Chance baselines differ by condition** and each accuracy is read against its own | — | same file — do not compare raw accuracies across conditions without them |
| Lexical similarity between participants on the same question — medians | human **0.179**, enriched **0.268**, demo **0.258** | `analysis/figures/agent_fidelity_lexical_distinctiveness.csv` (panel A, per focus group / run) |
| Humans exceeded chance; enriched did not; basic did so only on the trial-level test | permutation *p* < .001 / *p* = .34 / *p* = .012 (seed 20260808, 20 000 permutations) | `PE/agent_fidelity/ATTRIBUTION_SIGNIFICANCE_TESTS.md` §3; values in `agent_fidelity_attribution_inference.json` |
| Session-level test agrees for human and enriched, not for basic | Wilcoxon *p* = .0625 (floor at n = 5) / .68 / .14 | same, §4 — the human test cannot reach *p* < .05 at n = 5 and the floor is declared, not a null result |
| Humans outperformed the enriched condition; humans vs basic unresolved | Mann-Whitney *p* = .011, Cliff's δ = .76 (Holm .043) / *p* = .16 | same, §5 |
| **Basic condition is n = 14, not 15** — one session yielded no eligible fold | — | same, §6 — four of its five participants spoke in only two guide questions; recorded in the coverage block of `agent_fidelity_stylometry.json` |
| Per-trial data behind the attribution test | — | `PE/agent_fidelity/agent_fidelity_trials_long.csv`, `agent_fidelity_cell_tokens.csv`, `agent_fidelity_speaker_id_by_document.csv` |
| Specification sensitivity | — | `PE/agent_fidelity/agent_fidelity_stylometry_sensitivity.json` |
| Producers | — | `scripts/agent_fidelity_corpus.py`, `scripts/agent_fidelity_stylometry.py` |

**What this level does not claim.** The measured property is whether a participant's text
can be told apart from that of their fellow participants and recognised across questions.
That is all. Lexical diversity, MATTR, TTR and vocabulary overlap are not evidence of an
individual identity — the producer's own docstring says so.

---

## How each construct is measured

The benchmark is built from **deterministic, automatic producers**: an instrument that needs
its own coding exercise for every corpus does not transfer to another population, topic,
model or architecture, which is what this benchmark exists to enable. Several constructs
admit more than one operationalisation; the table records which one the benchmark uses.

| Construct | Measured by |
|---|---|
| Contrast between participants (indicator 9) | Response acts under a frozen, hash-anchored contrastive-marker dictionary, plus intra-turn semantic dispersion — `scripts/consensus_dynamics_events.py`, `consensus_intraturn_dispersion.py` |
| Contextual reference density (indicator 10) | Entity extraction under a frozen entity-type spec, with stated-origin geography excluded — `scripts/consensus_specificity_gliner.py` |
| Speaker distinctiveness (indicators 11, 12) | Attribution lift and lexical distinctiveness, offline — `scripts/agent_fidelity_stylometry.py` |
| Elaboration depth | `chain_depth` and `participant_participant_adjacency`, from turn structure |

`metric_registry.csv` also carries rows marked `NOT_IN_REPORTED_INSTRUMENT`. These are
alternative operationalisations of the same constructs — turn-level LLM coding rather than an
automatic producer — kept in the ledger so that the choice of instrument is on the record.
The benchmark does not use them.

**Figure 8 is the specificity measure the benchmark uses**, not a stand-in for something
absent: an automatic producer whose frozen entity-type list and place-exclusion rule are
published alongside it.

---

## Claims about the design itself

| Claim | Where it is substantiated |
|---|---|
| No response length, disagreement rate, turn-taking distribution or linguistic style was hard-coded | `prompts/` (all six prompt files plus `prompts/sandbox/`), `core/config.py` (the only numeric behavioural constants are the auction thresholds), `docs/system_operation/VERBOSITY_CONTROL_MAP.md` |
| The verbosity difference persisted across prompt versions that substantially reduced verbosity | `exploratory/prompt_and_moderator_ablations/findings/2026-06-27_verbosity_baseline.md`, `2026-06-28_length_by_section_and_position.md` |
| The moderator's action set is fixed; its content is generated | `core/moderator_brain.py`, `prompts/04_PHASE_MODIFIERS_AND_SPECIAL_CASES.md`, `docs/system_operation/OPERATIONAL_TRUTH_TABLE.md` |
| Turn auction thresholds | `core/config.py` — `URGENCY_THRESHOLD = 0.55`, `PEER_ADDRESS_BONUS = 0.15`, `CONSENSUS_RISK_CHALLENGE_PREFERENCE = 0.10`, `MAX_CONSECUTIVE_PARTICIPANT_TURNS = 6` |
| Moderator memory: full transcript of the open guide section, summary of closed ones | `core/moderator_brain.py`, `docs/system_operation/EMERGENT_MODE_MECHANICS.md` |
| Participant memory: own prior turns plus conversation since last spoke | `core/participant_agent.py`; per-run settings `participant_episodic_depth`, `participant_episodic_since_last_n` in each `configs/experiment/*.json` |
| Generation and evaluation are separated; the codebook is never read by the generation path | `scripts/thematic_coding.py` docstring (quarantine note), `PE/contamination_audit.json` |

---

## Known defects and deviations, recorded rather than fixed

| Item | Where |
|---|---|
| Six participant speaking opportunities in `macho_meals_fg1_run01` were suppressed by a technical fault, not a modelled choice (rate 0.0291) | `PE/run_readiness_audit.csv → finding_detail` (`FORCED_SILENCES_PRESENT`) |
| The enriched and demographics-only conditions executed different engagement-retry paths, so participation-dependent metrics are not like-for-like across conditions in the affected runs | same (`ENGAGEMENT_RETRY_PATH_ABSENT`) — a `MATERIAL_COMPARABILITY_WARNING`, printed per run |
| API failures and fallbacks during the run campaign | `PE/api_failure_and_fallback_audit.csv` |
| Frozen structural metrics count words with plain `str.split()`, not the project's documented uniform rule | `docs/length_measurement_rule.md`, `docs/findings/2026-06-28_length_measurement_uniform_rule.md` |
| Protocol deviations in the exploratory transportability check | `exploratory/transportability_within_domain/analysis/production_evaluation/transportability_sample/hybrid_evaluation/PROTOCOL_DEVIATIONS.md` |
