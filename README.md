# Where human similarity holds and where it breaks

**A benchmark for evaluating the fidelity of synthetic (LLM-generated) focus groups
against matched human focus groups.**

This repository contains the complete simulation architecture, the evaluation
framework, the raw session data and every analysis artefact behind the dissertation
*Where human similarity holds and where it breaks: Evaluating the fidelity of
synthetic focus groups* (MSc Social Cognition: Research & Applications, UCL).

It is published for two audiences:

- **Researchers who want to run this themselves** — on their own population, topic,
  model or architecture. Start at [§2 Running a simulation](#2-running-a-simulation)
  and the companion [UI_README.md](UI_README.md).
- **Readers who want to audit a claim in the dissertation** — every reported number
  resolves to a file. Start at
  [CLAIM_TO_ARTEFACT_MAP.md](CLAIM_TO_ARTEFACT_MAP.md).

---

## Contents

1. [What the study did](#1-what-the-study-did)
2. [Running a simulation](#2-running-a-simulation)
3. [Running the evaluation](#3-running-the-evaluation)
4. [Repository layout](#4-repository-layout)
5. [Reproducing the reported figures](#5-reproducing-the-reported-figures)
6. [What is *not* here, and why](#6-what-is-not-here-and-why)
7. [Data provenance and licence](#7-data-provenance-and-licence)
8. [Citation](#8-citation)
9. [Authorship and AI assistance](#9-authorship-and-ai-assistance)

---

## 1. What the study did

Five human focus groups from the **Macho Meals** study (Hankins et al., 2025 — UK men
discussing food choice, masculinity and plant-based eating) were each re-simulated
**three times** under **two persona conditions**, giving **30 synthetic sessions**:

| Condition | Persona content | Agent payloads |
|---|---|---|
| `enriched` | All available participant metadata: demographics, dietary habits, masculinity and meat-consumption psychographics | `agents/macho_meals/` |
| `demographics-only` (the dissertation's "basic" condition) | Demographics only | `agents/macho_meals_demoonly/` |

Participants were generated with **Claude Haiku 4.5**, the moderator with
**Claude Sonnet 4.6**. Thematic coding of both sides was done blind by a
**different model family** (`gemini-3.5-flash`) to avoid circularity between the
generator and the evaluator.

The comparison is always **at the group level**, and the focus group is the unit of
analysis (**n = 5 pairs**). The three replicates estimate *generator* variability under
a fixed configuration; they are never treated as five extra focus groups. Human
transcripts set the benchmark — each indicator expresses a *gap* to the human side, not
performance against an absolute quality standard.

### Headline findings

| Level | Finding |
|---|---|
| **1 · Thematic fidelity** | Synthetic groups recovered part of the human repertoire and what they produced was largely accurate — mean recall 39.1% (enriched) / 27.0% (demographics-only), precision 78.8% / 71.0%. Themes that *did* appear spread across far more participants than in the human groups (reach 77.1% vs 58.9% human). |
| **2 · Interaction process** | The largest divergence. Human participant turns had a per-group median of 48.9 words; synthetic medians were around 240. The shortest synthetic turn in all 30 sessions was 55 words, while 34.4% of human turns were under 25. Human groups varied widely between sessions (CV 51.0%); synthetic groups did not (CV ≈ 5–14%). |
| **3 · Speaker distinctiveness** | Human participants were linguistically attributable well above chance (46.8% against a 25.5% chance level; permutation *p* < .001, all five sessions individually above chance). The enriched condition was indistinguishable from its own chance level (32.5% against 31.2%, *p* = .34); the basic condition exceeded its own chance level modestly (37.7% against 30.9%, *p* = .01), though not when each session was treated as a single observation. Humans outperformed the enriched condition (*p* = .011, Cliff's δ = .76); humans versus basic was unresolved at these sample sizes. Enrichment gave no advantage. Tests in [`ATTRIBUTION_SIGNIFICANCE_TESTS.md`](analysis/production_evaluation/agent_fidelity/ATTRIBUTION_SIGNIFICANCE_TESTS.md). |

Full numbers, with their denominators and caveats, are in
[`analysis/production_evaluation/final/FINAL_INTEGRATED_RESULTS_REPORT.md`](analysis/production_evaluation/final/FINAL_INTEGRATED_RESULTS_REPORT.md).

**The benchmark is twelve indicators across these three levels**, set out one by one in
[`docs/evaluation_framework_summary.md`](docs/evaluation_framework_summary.md) with the
operational rule and evidence source for each, following the dissertation's Appendix D.
Saturation sits inside Level 1, as indicator 3. `metric_registry.csv` has 51 rows because it
is an operational ledger rather than the benchmark; the crosswalk at the top of
[CLAIM_TO_ARTEFACT_MAP.md](CLAIM_TO_ARTEFACT_MAP.md) maps the two.

---

## 2. Running a simulation

### Install

```bash
pip install -r requirements.txt
```

Developed and run on **Python 3.14**. `datetime.UTC` puts the floor at 3.11; no lower
version was tested. Set `ANTHROPIC_API_KEY` in your environment.
Copy `.env.example` to `.env` for the *evaluator* keys — those are read only by the
post-hoc analysis scripts, never by the generation path.

### Run one session

The 30 reported sessions were run to **natural guide completion**, not to a fixed turn
count:

```bash
py scripts/run_full_session.py --config configs/experiment/macho_meals_fg1_run01.json --max-turns 90
```

`run_session.py --config <path> --turns N` is the lower-level stepper: it runs exactly
N iterations regardless of guide state, which is useful for inspection but wastes calls
on a full session.

Either is a **live, billed** call to the Anthropic API. In this study a session cost a
median of USD 2.54 and took a median of 23.3 minutes. Cost grows with roughly the
*square* of the turn count, because every turn re-sends the transcript so far, and the
moderator dominates the bill — not the participants.

### Run several in parallel

Each child is an ordinary `run_full_session.py` process; distinct `session_id`s cannot
collide, because the log directory is derived from the id alone.

```bash
py scripts/run_parallel_sessions.py \
  --config configs/experiment/macho_meals_fg1_run01.json \
  --config configs/experiment/macho_meals_fg1_run02.json \
  --config configs/experiment/macho_meals_fg1_run03.json \
  --max-turns 90
```

Sessions write to `output/session_logs/<session_id>/`: `transcript.json`,
`transcript.txt`, `moderator_log.json`, `api_calls.jsonl`, `session_state_initial.json`
and a cumulative `state_turn_N.json` per turn.

### How the architecture works

Three roles (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/system_operation/`](docs/system_operation/)):

- **Participant agents** (`core/participant_agent.py`) — one per real participant, built
  from a JSON profile that `core/prompt_renderer.py` turns into natural language just
  before the agent speaks. A participant's "memory" is not a private store: it is its
  own prior turns plus the conversation since it last spoke.
- **Moderator** (`core/moderator_brain.py`) — follows the discussion guide without
  reciting it, choosing at each turn between a fixed action set (probe, address a
  participant, advance a section, or stay out). It keeps running notes and sees the full
  transcript of the *open* guide section; closed sections are compressed to a summary.
- **Orchestrator** (`core/orchestrator.py`) — not an agent and makes no model calls. It
  assembles the transcript, tracks turns and runs the **turn auction**: each participant
  privately scores its own urgency to speak (0–1) against the last 6 transcript entries;
  anyone above `URGENCY_THRESHOLD = 0.55` enters, highest urgency wins, ties break toward
  whoever has spoken least. Being named by a peer or addressed by the moderator adds a
  bounded bonus; a single named participant bypasses the auction entirely; after 6
  consecutive participant turns control returns to the moderator.

**All 30 reported sessions ran in `participation_mode: "emergent"`** — the turn auction
described above. The code also implements an `orchestrated` mode (code-driven round
robin), and **that is the default when a config omits the field**
(`core/orchestrator.py:101`). The study never used it, every config here sets `emergent`
explicitly, and a session run in `orchestrated` mode is not the architecture the
dissertation evaluates. `docs/ARCHITECTURE.md` and `docs/operational_flow.md` document
both modes because both exist in the code; only one produced the results.

**A deliberate design constraint:** no response length, disagreement rate, turn-taking
distribution or linguistic style was hard-coded. Verbosity, internalised contrast and
reduced voice differentiation are informative results *precisely because* they were not
programmed. The trade-off — portability across models is untested — is stated in the
dissertation's limitations.

Prompts live in `prompts/`. Note that the 30 production runs used the moderator override
`prompts/sandbox/01_MODERATOR_SYSTEM_PROMPT_MINIMAL.md`; this is recorded per run in
`analysis/production_evaluation/run_readiness_audit.csv` (`moderator_prompt_override`,
with a SHA-256).

---

## 3. Running the evaluation

The evaluation never touches the generation path. `scripts/thematic_coding.py` is the
only module that reads the codebook, and it runs strictly after transcripts exist.

**Order of operations, and the script for each:**

| Step | Script | Output |
|---|---|---|
| Derive the human-comparable analytical window | `scripts/build_comparable_window.py` | `analysis/production_evaluation/comparable_transcripts/` |
| Freeze the evaluator's inputs (SHA-256 per document) | `scripts/freeze_evaluator_inputs.py` | `analysis/production_evaluation/frozen_evaluator_inputs.json` |
| Validate the evaluator against three gates | `scripts/validate_thematic_measure.py`, `scripts/run_evaluator_comparison.py` | `analysis/coding_frame/validation_stage1_gemininext.json` |
| Code both sides blind (Level 1 · thematic) | `scripts/production_eval_pipeline.py` → `scripts/thematic_coding.py` | `analysis/production_evaluation/evaluator_cache/` |
| Aggregate to run / FG / condition | `scripts/aggregate_production_results.py`, `scripts/build_primary_effects_tables.py` | `analysis/production_evaluation/results/*.csv` |
| Theme saturation, also Level 1 (Fig. 5) | `scripts/saturation_analysis.py` | `analysis/production_evaluation/final/saturation_analysis.json` |
| Structural + interaction metrics (Level 2 · interaction process) | `scripts/consensus_dynamics_events.py`, `scripts/consensus_dynamics_metrics.py`, `scripts/consensus_intraturn_dispersion.py`, `scripts/consensus_specificity_gliner.py` | `analysis/production_evaluation/consensus_dynamics/` |
| Speaker distinctiveness (Level 3) | `scripts/agent_fidelity_corpus.py`, `scripts/agent_fidelity_stylometry.py` | `analysis/production_evaluation/agent_fidelity/` |
| Recompute every reported figure from source | `scripts/structural_traceability.py`, `scripts/build_final_products.py` | `analysis/production_evaluation/final/RESULTS_TRACEABILITY_INDEX.md` |

**The evaluator gates.** Before any coding, `gemini-3.5-flash` had to pass three checks
(`analysis/coding_frame/validation_stage1_gemininext.json`):

- *Reproducibility* — identical decisions across five codings of the same transcript
  (observed 1.00, threshold 0.85). `gemini-2.5-flash` failed this and was discarded.
- *Discrimination* — a matched human–synthetic pair must score higher than a
  deliberately mismatched one (observed margin **+0.1111**).
- *Citation validity* — every code must carry a verbatim quotation found in the
  transcript (observed 1.00). Codes without verifiable evidence are discarded.

The evaluator was then benchmarked against a **blind human coder**
(`analysis/coding_frame/human_anchor/`) and against the **original Macho Meals research
team's own coding** (`analysis/production_evaluation/gold_standard_*`): 47 of 55
theme-by-group decisions agreed, κ = 0.670.

**Registry.** `analysis/production_evaluation/metric_registry.csv` is the authority on
what each of the 51 registered metrics measures, its unit of analysis, and its evidence
class (`AUTOMATIC_VALIDATED`, `AUTOMATIC_DIAGNOSTIC`, `EXPLORATORY`,
`REPORTED_VIA_AUTOMATIC_PRODUCER`, `NOT_IN_REPORTED_INSTRUMENT`,
`DEFERRED_NOT_IMPLEMENTED`, `RETIRED_NOT_FOR_FIDELITY`). Read it before quoting any number. Rows marked
`NOT_IN_REPORTED_INSTRUMENT` are operationalisations that were designed and **not
adopted**: the benchmark measures those constructs with deterministic automatic
producers instead, so that it transfers to another corpus without a coding exercise of
its own. `CLAIM_TO_ARTEFACT_MAP.md` tabulates each adopted measure against its
alternative.

### Tests

```bash
py -m pytest tests -q
```

962 pass, 86 skip. The skips are documented in `tests/conftest.py`: they assert against
the QESB / PHIND human-baseline corpora, which are third-party data not redistributed
here (see [§7](#7-data-provenance-and-licence)).

---

## 4. Repository layout

```
core/                      Simulation architecture. Orchestrator, moderator, participant
                           agent, prompt renderer, session state, API logging and retry.
prompts/                   Moderator system prompt, user template, opening prompt, phase
                           modifiers, restraint block, reflection prompt, sandbox variants.
configs/
  experiment/              The 30 canonical run configs (plus the two superseded
                           replicates, fg4_run02 and fg5_run02, kept for transparency).
  guides/                  The Macho Meals discussion guide (YAML).
agents/
  macho_meals/             22 enriched persona payloads + manifest.
  macho_meals_demoonly/    The same 22 personas, demographics only.
run_session.py             CLI entry point for one session.
scripts/                   91 scripts: generation runners, the evaluation pipeline,
                           validation gates, audits and final product builders.
assessment/                Earlier generic session-QA layer (mechanical integrity, flags,
                           recommendation rules). Not used by the reported Level 1–3
                           results; retained because its unit tests document the lineage.
data/
  datasets_transcripts/standardized/macho_meals/    The 5 human transcripts, standardised.
output/session_logs/       46 session directories: the 30 canonical runs plus 12 excluded,
                           aborted or pilot runs, kept so the operational record is complete.
analysis/
  coding_frame/            Codebook, evaluator validation gates, blind human coder package,
                           the full Gemini call log and the quote-match audit.
  production_evaluation/   Every evaluation artefact — see below.
  figures/                 Figure render scripts and their PNG/CSV outputs.
docs/                      Architecture, operational flowcharts and truth tables, the
                           evaluation framework, and dated findings notes.
exploratory/               Analyses that were run and produced results but are not reported
                           in detail in the dissertation. See exploratory/README.md.
transferability/           Two strands testing how far the apparatus and the persona
                           construction reach beyond this corpus: another discussion guide
                           and domain, and agents built from census statistics. See
                           transferability/README.md.
apps/focus_group_platform/ The researcher-facing UI. See UI_README.md.
tests/                     68 test modules over the architecture and the evaluation.
```

### `analysis/production_evaluation/` — the evaluation record

| Path | What it holds |
|---|---|
| `canonical_experiment_manifest.csv` | The 30 runs, with SHA-256 of transcript, config, agents, guide and moderator prompt |
| `run_readiness_audit.csv` | Per-run operational audit: turns, words, roster match, forced silences, comparability warnings, verdict |
| `frozen_evaluation_spec.md`, `frozen_evaluator_inputs.json` | The pre-registered evaluation spec and the hashed inputs the evaluator was allowed to see |
| `metric_registry.csv` | All 51 metrics with definition, unit, aggregation and evidence class |
| `comparable_transcripts/` | The 30 comparable analytical windows |
| `comparable_window_boundaries.md`, `comparable_window_audit.csv` | How each window was cut, and the audit of the cuts |
| `evaluator_cache/` | The evaluator's raw responses, keyed by request hash |
| `results/` | The aggregated tables: per run, per FG, per condition, paired effects, code presence, reach, structural distributions |
| `final/` | The integrated report, the traceability index, the claim matrix, `FINAL_RESULTS_TABLES.xlsx`, saturation and lexical analyses |
| `consensus_dynamics/` | Level 2 (interaction process): response acts, intra-turn dispersion, specificity (GLiNER), frozen spec with dictionary hashes |
| `agent_fidelity/` | Level 3 (speaker distinctiveness): stylometry, attribution trials, permutation significance tests and specification sensitivity |
| `salience_absence_audit/` | Blinded cross-model audit of all 260 absence decisions, plus the salience sensitivity treatments |
| `open_coding_adjudication/` | The targeted blinded human coding review of FG4 demographics-only A.1 |
| `gold_standard_*` | The comparison against the original Macho Meals researchers' coding |
| `mator_comparable/` | External benchmark against Mator et al. (2025) Table 4 — exploratory, but registered, so it lives here |

---

## 5. Reproducing the reported figures

The dissertation's figures are produced by scripts in `analysis/figures/`:

| Dissertation figure | Script | Output |
|---|---|---|
| Codebook (11 themes) | `plot_macho_meals_codebook.py` | `macho_meals_codebook.png` |
| Fig. 4 — theme presence across human and synthetic sets | `render_thematic_salience_heatmap.py` | `thematic_salience_heatmap.png` |
| Fig. 5 — theme saturation by replicate | `render_repertoire_saturation_by_replicate.py` | `repertoire_saturation_by_replicate.png` |
| Fig. 6 — recall, precision and reach by focus group | `plot_level1_thematic_fidelity.py` | `level1_thematic_fidelity_by_focus_group.png` |
| Fig. 7 — distribution of participant turn length | `render_interaction_verbosity_distribution.py` | `interaction_verbosity_distribution.png` |
| Fig. 7 — illustrative structure of participant turns | `render_interaction_verbatims.py` | `interaction_turn_structure_verbatims.png` |
| Fig. 8 — specific detail density | `render_interaction_specificity.py` | `interaction_specificity_density.png` |
| Level 3 — attribution lift | `render_agent_fidelity_attribution_lift.py` | `agent_fidelity_attribution_lift.png` + `.csv` |
| Level 3 — lexical distinctiveness | `render_agent_fidelity_lexical_distinctiveness.py` | `agent_fidelity_lexical_distinctiveness.png` + `.csv` |

```bash
py analysis/figures/plot_level1_thematic_fidelity.py
```

The remaining scripts in that directory render variants and sensitivity views that are
not in the dissertation; they are kept because they were built from the same sources.

**Every reported number traces to a source artefact.** See
[CLAIM_TO_ARTEFACT_MAP.md](CLAIM_TO_ARTEFACT_MAP.md) for the claim-by-claim map, and
`analysis/production_evaluation/final/RESULTS_TRACEABILITY_INDEX.md` for the machine-built
index of 119 figures, each recomputed from source rather than transcribed.

---

## 6. What is *not* here, and why

- **Two large third-party datasets.** The Twin-2K-500 corpus and the ONS Census 2021
  microdata (~2.5 GB combined) were downloaded for a persona-grounding arm that is not
  part of the reported results. Their ETL scripts are in
  `transferability/census_built_personas/`; the raw data is not redistributed.
- **The QESB and PHIND human corpora.** Standardised during the framework's development
  and used to calibrate the earlier Stage-7 assessment layer. Third-party transcripts,
  not redistributed. The standardisation and verification tooling is in `scripts/`.
- **The earlier FastAPI + React generation UI.** Superseded by the Streamlit platform in
  `apps/focus_group_platform/`; see [UI_README.md](UI_README.md).
- **Prompts, configs and metrics that were tried and abandoned** without bearing on the
  experiment. Analyses that *were* run and *did* produce results, but are not reported in
  detail in the dissertation, are preserved in `exploratory/` rather than discarded.
- **API keys.** `.env` is not included; `.env.example` documents which keys each layer
  needs. The generation path uses `ANTHROPIC_API_KEY` from the environment; the evaluator
  keys are read only by analysis scripts.
- **The blind human coder's provenance key.** `analysis/coding_frame/human_anchor/`
  ships the transcripts, worksheets and results, but the file mapping each labelled
  transcript to its real/synthetic origin is marked researcher-only in the source
  repository and is withheld here pending an explicit decision to publish it.

---

## 7. Data provenance and licence

**Human transcripts.** `data/datasets_transcripts/standardized/macho_meals/` contains
the five Macho Meals focus groups in standardised form. The source files were already
anonymised and cleaned by the original research team (Hankins et al., 2025) before they
reached this project; participant names are pseudonyms. The raw `.docx` originals are
**not** redistributed here. `MACHO_MEALS_STANDARDIZATION_REPORT.md` in that directory
records exactly what the standardisation did and what it could not verify — in
particular, that the available raw files are themselves edited versions, so the
faithfulness check runs against the edited raw, not an original recording.

Anyone reusing the human transcripts should cite the original study and check its own
terms of use. This repository does not grant rights over that data.

**Agent profiles.** The 22 persona payloads in `agents/` are derived from the
participant-level metadata published with the original study. No biographical detail was
invented; see `scripts/build_fg_agents.py` for the construction.

**Synthetic transcripts and all analysis artefacts** were generated by this project.

**Code** is released for inspection, adaptation and re-testing. Add the licence of your
choice before making the repository public — there is currently no `LICENSE` file, and
without one the default is *all rights reserved*.

---

## 8. Citation

If you use this benchmark, please cite the dissertation and this repository, and cite
Hankins et al. (2025) for the human corpus.

---

## 9. Authorship and AI assistance

**Software.** The simulation and evaluation code was developed with AI-assisted
programming tools, as the dissertation's Implementation section records. Every output was
reviewed and tested before being incorporated. This is stated for transparency about the
software, not as a warrant of its correctness.

**Documentation.** The Markdown documentation in this repository was assembled with AI
assistance under the author's direction. Files written by a script are programmatic output;
the generating script and line can be recovered by searching the code for the filename.
Every other Markdown file was reviewed by the author, who set the questions, directed the
analysis, took each methodological decision and validated the reported figures against the
underlying data before inclusion. The dissertation text is the author's own.

**Models used in the study itself.** Participants were generated with Claude Haiku 4.5,
the moderator with Claude Sonnet 4.6, and thematic coding was performed by
Gemini-3.5-flash; their selection, validation and limitations are documented in
`analysis/production_evaluation/frozen_evaluation_spec.md`.

**The author's own.** The research questions, study design, choice of corpus, analytical
decisions, interpretation of results and the dissertation text.
