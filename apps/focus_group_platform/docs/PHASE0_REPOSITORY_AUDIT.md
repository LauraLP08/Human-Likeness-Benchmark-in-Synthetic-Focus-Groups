# Phase 0 — Repository audit for the transferable focus-group platform

**Status: AUDIT ONLY. No existing file was modified. No code was written.**
Date: 2026-08-04. Every claim below cites a path and, where behaviour is asserted,
the function or line that establishes it. Nothing here is taken from documentation
alone; where documentation and code disagree, the code is reported as authoritative
and the disagreement is flagged.

---

## 0. Five findings that change the brief

These contradict or qualify premises in the request. They are listed first because
they affect the design, not just the implementation.

### 0.1 The YAML guide is NOT what executes

The brief asks for a guide "compatible con el formato YAML utilizado por el
proyecto". YAML guides exist — `configs/guides/*.yaml`, 8 files — but they are an
**authoring** format, not the runtime source of truth.

`configs/guides/macho_meals_plant_based_masculinity_uk.yaml` says so in its own
header (lines 4–13):

> AUTHORITY (2026-07-28): this file is NOT the source of truth for synthetic runs.
> The canonical guide is the inlined `discussion_guide` array in
> `configs/experiment/macho_meals_fg1_run01.json`, which is what actually executes —
> nothing in `core/` or `scripts/run_full_session.py` reads this YAML at runtime.

The code agrees: `core/orchestrator.py::_build_state_from_config` (line 90) reads
`session_config["discussion_guide"]`, an inline array in the JSON config. Two
converters turn YAML into that array:

* `scripts/run_batch.py::_load_guide_sections` (line 79) — "Load and convert the
  YAML guide to the session-config section format."
* `scripts/twin2k500_sample.py::build_session_config` (line 124) — panel spec YAML
  + guide YAML → ready-to-run session config JSON.

The same header records that the two representations **drifted apart** historically
and had to be re-synchronised. That is the risk the app must design against: it must
treat the compiled JSON config as the executed artefact, keep the YAML beside it,
and record the hash of both.

### 0.2 A UI already exists, and it is partly stale

`ui/backend/api.py` (1,092 lines, FastAPI, dated 2026-05-27) plus `ui/frontend`
(React 19 + Vite + Tailwind, `ui/frontend/package.json`). It drives the orchestrator
directly and streams over SSE.

I checked whether its integration points survive: `run_opening`,
`run_conversation_step`, `_run_full_turn_streaming`, `save_transcript` and
`save_moderator_log` all still exist in `core/orchestrator.py` (lines 459, 829, 756,
1021, 1036). So it is not dead — but:

* it binds to `_run_full_turn_streaming`, a **private** method (leading underscore),
  which is precisely the coupling the brief forbids;
* it predates three months of orchestrator change (`core/orchestrator.py` last
  modified 2026-07-27; the UI 2026-05-27) and no test imports it — `grep -rln
  "ui.backend|ui/backend" tests/ scripts/` returns nothing;
* it hunts for directories that may not exist (`SESSION_DIR_CANDIDATES` lists five
  candidate paths, `GUIDES_DIR_CANDIDATES` three), which is a symptom of having been
  written against a layout that has since moved.

It is **prior art to learn from, not a foundation to extend**. Its SSE event shapes
(`_entry_to_event`, `_build_state_update`) are a useful reference for what a live
session view needs to show.

### 0.3 There is no git repository

`ls -d .git` → absent. The brief asks each run to record "versión del código o
commit cuando esté disponible". It is not available. The app needs a fallback:
a content hash over the files that actually determined behaviour (`core/*.py`, the
compiled config, the agent payloads), recorded per run. This must be designed in,
not discovered at Phase 3.

### 0.4 Nothing in the generation path computes cost

`grep -rln "cost_usd|estimated_cost|price_per|USD" core/*.py scripts/run_*.py`
returns nothing. What exists is token accounting: `core/api_logging.py::append_api_log`
writes `api_calls.jsonl` per run with `input_tokens`, `output_tokens`,
`total_tokens`, `model`, `stop_reason`, `max_tokens`, `response_truncated`.

So "consumo de tokens y costo estimado" is: tokens are **read from the artefact**,
cost is **computed by the app** from a rate table the app owns. The rate table is
app configuration and must be dated and versioned, because it goes stale.

### 0.5 Twin2K profiles are not built in this checkout

`agents/twin2k500/` **does not exist**. `data/twin2k500/` does. The ETL that would
populate it (`scripts/twin2k500_etl.py`) depends on `datasets>=2.18`, which is in
`requirements-twin2k500.txt` — a **separate** file from `requirements.txt`.

So Flow 1B's "seleccionar perfiles procedentes de Twin2K" is a two-step feature: the
app can offer it, but it must first detect whether the local agent index exists and,
if not, say so and point at the ETL rather than failing opaquely.

---

## 1. Map of the existing architecture

### 1.1 Generation core — `core/` (9 modules, 21 files)

| Module | Lines | Role | Public surface the app would touch |
|---|---|---|---|
| `core/orchestrator.py` | 50,786 B | Session driver | `FocusGroupOrchestrator(session_config: dict)`; `run_opening()` 459, `run_participant_turn()` 543, `run_moderator_turn()` 592, `run_full_turn()` 691, `run_conversation_step()` 829, `save_transcript()` 1021, `save_moderator_log()` 1036 |
| `core/session_state.py` | 52,807 B | Pydantic state model | `SessionMeta`, `SessionState`, `ParticipantState`, `SectionPhase` enum |
| `core/participant_agent.py` | 50,181 B | Persona prompt + participant call | `load_agent_from_json(path)`, `build_participant_system_prompt(participant, session_meta, has_other_participants=True)` (line 279) |
| `core/moderator_brain.py` | 21,332 B | Moderator decisions | driven via orchestrator |
| `core/prompt_renderer.py` | 21,929 B | Prompt assembly | internal |
| `core/api_logging.py` | 3,451 B | Per-call JSONL log | `append_api_log(log_dir, ...)` |
| `core/api_retry.py` | 5,845 B | Rate-limit/backoff | internal |
| `core/config.py` | 949 B | Model constants | read-only |

**The integration contract is one dict.** `_build_state_from_config(session_config)`
(line 90) is the whole entry surface. Required keys: `session_id`,
`research_objective`, `topic_domain`, `participant_collective_identity`,
`moderator_knowledge_brief`, `participants`, `discussion_guide`. Roughly twenty
optional keys with documented defaults (`temperature` 1.0,
`participant_response_max_tokens`, `participation_mode` `"orchestrated"`,
`moderator_model` `"claude-sonnet-4-6"`, episodic-memory depth controls, moderator
restraint/reflection toggles, `moderator_context_mode`, `time_budget_tracking_enabled`).

Participants accept exactly one of three shapes (line ~157, enforced with a
`ValueError` on conflict): `agent_payload_path`, inline `agent_payload`, or legacy
`id`/`name`/`profile_summary`.

**`run_label` is not a seed.** The comment block at lines 111–125 is explicit:
the field was renamed from `generation_seed` on 2026-06-29 "because the Anthropic
API has no seed parameter, so the old name falsely implied a determinism control",
and it "has zero functional effect ... never read elsewhere in `core/`". This
already encodes the brief's rule. The app must not reintroduce the word.

**One real seed does exist, and it is a different thing.**
`scripts/twin2k500_sample.py --seed` (line 207) seeds *panel sampling* — which
agents get drawn from the population. That is genuinely reproducible and should be
recorded. Conflating it with generation determinism would be an error.

### 1.2 Execution entry points — `scripts/`

| Script | Contract | Notes |
|---|---|---|
| `scripts/run_full_session.py` | `--config <json> --max-turns 90 [--mode orchestrated\|emergent]` | Canonical single run. Stops when every guide section is `completed`, with a safety cap. Loads `.env` via `dotenv` if present. |
| `scripts/run_parallel_sessions.py` | `--config PATH` (repeatable) `--max-turns` | Launches each config as a **separate OS process** running `run_full_session.py`. Its docstring records the concurrency safety proof: `log_dir` is `output/session_logs/<session_id>`, derived purely from `session_id` with no timestamp, no module-level file handle, lockfile or shared counter anywhere in `core/`. Distinct `session_id`s cannot collide. |
| `scripts/run_batch.py` | `--fg N --runs N --participant-model M [--dry-run]` | Sequential; reads the YAML guide and builds configs in memory. Macho-Meals-specific paths. |
| `scripts/twin2k500_sample.py` | `--panel <yaml> --guide <yaml> --out <json>` | Panel spec + guide → ready-to-run config, plus a manifest. |

**This is the single most useful fact for the app's design.** `run_parallel_sessions.py`
already proves that launching sessions as subprocesses is safe and requires no
knowledge of orchestrator internals. Combined with the fact that artefacts are
written **incrementally** (below), the app can drive generation without importing
`core/` at all in the generation path.

### 1.3 Run artefacts — `output/session_logs/<session_id>/`

Verified against `output/session_logs/macho_meals_fg1_run02/`:

```
transcript.json          list of {turn, speaker_id, speaker_name, content, timestamp, selection_mode}
transcript.txt
moderator_log.json
session_state_initial.json
state_turn_0.json … state_turn_N.json     written per turn
api_calls.jsonl                            one line per API call, with token counts
launcher_stdout.log
```

`state_turn_N.json` and `api_calls.jsonl` accumulate **during** the run. A UI can
therefore render live progress by tailing files, with no streaming protocol and no
in-process coupling.

### 1.4 Evaluation — two distinct systems, only one of which is the benchmark

**`assessment/` is legacy and is NOT the thesis benchmark.** 12 modules dated
2026-05-25/27. `assessment/metrics.py::compute_topic_metrics` defaults to
`topic: str = "grocery_delivery"` (line 511) — it is the Stage-3 grocery-pilot
scorecard. Do not wire it to the benchmark UI.

**The benchmark is `scripts/` + `analysis/production_evaluation/`.** The spec is
`analysis/production_evaluation/frozen_evaluation_spec.md`; the metric definitions
are `analysis/production_evaluation/metric_registry.csv` (46 rows).

Registry composition, counted from the file:

| tier | evidence_class | n |
|---|---|---|
| Tier 1 | AUTOMATIC_VALIDATED | 4 |
| Tier 1 | AUTOMATIC_DIAGNOSTIC | 3 |
| Tier 1 | DEFERRED_NOT_IMPLEMENTED | 2 |
| Tier 1 | LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC | 1 |
| Tier 2 | EXPLORATORY | 5 |
| Tier 2b | RETIRED_NOT_FOR_FIDELITY | 1 |
| structural | AUTOMATIC_VALIDATED | 7 |
| structural | AUTOMATIC_DIAGNOSTIC | 3 |
| interaction | AUTOMATIC_VALIDATED | 2 |
| interaction | AUTOMATIC_DIAGNOSTIC | 1 |
| interpretive | NOT_IN_REPORTED_INSTRUMENT | 9 |
| operational | AUTOMATIC_DIAGNOSTIC | 5 |
| D2 proxy / exploratory | EXPLORATORY | 3 |

The nine `interpretive` rows carry the closure status recorded on 2026-08-04:
`NOT_IN_REPORTED_INSTRUMENT`. The app must surface that status rather than
compute those metrics.

### 1.5 The evaluation input contract

Human and synthetic transcripts **do not share a schema**:

* synthetic `transcript.json` entry: `turn, speaker_id, speaker_name, content, timestamp, selection_mode`
* standardized human `data/datasets_transcripts/standardized/macho_meals/fg1/transcript.json` entry: `turn, speaker_id, canonical_speaker_id, speaker_name, speaker_role, content, source_type, source_file, original_file_type, page, paragraph_indices, standardization_confidence, requires_review`

And the benchmark does not score raw synthetic transcripts. It scores a derived
window: `scripts/build_comparable_window.py` produces `comparable_transcript.json`,
because "the five standardized human transcripts begin directly at the moderator's
Question 1 and contain no general introduction, no participant name/location round,
and no formal closing section. A synthetic run has all three. Comparing a whole
synthetic transcript against a human transcript therefore compares unlike things."

`scripts/freeze_evaluator_inputs.py` then records hashes and emits a per-(input,
tier) **cache key**: "The synthetic side keys on the COMPARABLE-window hash, never
the full-transcript hash, so no full-session artefact can satisfy a comparable-window
lookup."

**Consequence for the app:** window derivation is a mandatory pre-step of Flow 2, not
an optional nicety, and it is the step most likely to need researcher judgement on a
new corpus.

---

## 2. Protected / frozen — do not modify

**Tier A — the experimental architecture (modification forbidden by the brief).**
`core/` (all 9 modules), `agents/` (115 files), `configs/experiment/` (51 JSON
configs), `configs/guides/` (8 YAML), `prompts/`, `output/session_logs/` (3,663
files), `data/datasets_transcripts/standardized/`.

**Tier B — thesis-producing scripts and their frozen outputs.** These declare their
own non-destructive or frozen status in-file:
`scripts/production_eval_pipeline.py`, `scripts/freeze_evaluator_inputs.py`,
`scripts/build_comparable_window.py`, `scripts/build_primary_effects_tables.py`,
`scripts/absence_audit_{build,rules,stage1,stage2}.py`,
`scripts/emergent_calibration_q3.py`, `scripts/inductive_{alignment,inventory}.py`,
`scripts/hybrid_metrics.py`, `scripts/oca_integration.py`,
`scripts/d2_length_diagnostics.py`, `scripts/consensus_dynamics_events.py`,
`scripts/agent_fidelity_registry_diff.py`, `scripts/persona_stress_test_v2.py`.

**Tier C — frozen result artefacts.**
`analysis/production_evaluation/final/` (FINAL_RESULTS_TABLES.xlsx,
RESULTS_TRACEABILITY_INDEX.md, FINAL_INTEGRATED_RESULTS_REPORT.md, figures),
`analysis/production_evaluation/metric_registry.csv`,
`analysis/production_evaluation/frozen_evaluation_spec.md`,
`analysis/production_evaluation/persona_stress_test/` (closed 2026-08-04).

**Tier D — the regression net.** `tests/` — 92 test modules, 1,858 passing. 24 of
them import `core/`. The app must leave this suite green; it is the only mechanical
proof that the architecture was not disturbed.

---

## 3. Reusable as-is (import, do not copy)

| Component | Why it is safe | Used for |
|---|---|---|
| `core.participant_agent.load_agent_from_json(path)` | pure loader, path in / state out | profile validation preview |
| `core.participant_agent.build_participant_system_prompt(p, meta, has_other_participants)` | pure renderer, no I/O | showing the researcher the prompt that will run |
| `core.session_state.SessionMeta` / `SessionState` / `SectionPhase` | Pydantic models — free schema validation for the guide and config forms | Flow 1A/1C validation |
| `scripts.structural_metrics_transportability.compute(turns, roster_names)` (line 134) | corpus-agnostic, but NOT schema-agnostic — see the correction below | Benchmark level 2 |
| `scripts.thematic_coding.to_blind_text(entries)` (161), `load_codebook()` (210), `verify_codes()` (400), `code_transcript_tier1()` (538), `compute_tier1_scores()` (643) | parameterised; the corpus binding lives in the *pipeline*, not these | Benchmark level 1 |
| `core.api_logging.append_api_log` | already the run's token ledger | token/cost panel |
| CLI subprocess: `scripts/run_full_session.py` | documented contract, proven concurrency-safe | Flow 1D execution |

## 4. Requires an adapter, or copy-with-provenance

| Component | Problem | Treatment |
|---|---|---|
| `scripts/lexical_analysis.py` | corpus hard-wired: `_human_session(fg)`, `_synth_session(run)` and `_sessions()` (lines 94–118) glob `output/session_logs` with the regex `macho_meals_(fg\d)(_demoonly)?_run0(\d)` | **copy and parameterise** the corpus loader; keep every metric function byte-identical and record provenance |
| `scripts/agent_fidelity_stylometry.py` | same corpus binding | same |
| `scripts/saturation_analysis.py`, `scripts/salience_hierarchy.py` | consume frozen coded outputs | adapter that accepts a coded-result directory |
| `scripts/production_eval_pipeline.py` | whitelists exactly 35 frozen documents; hard evaluator guard | **do not reuse**. Write a new runner for arbitrary corpora that reuses `thematic_coding` functions and keeps the evaluator guard |
| `scripts/build_comparable_window.py` | Macho-Meals boundary rules | adapter exposing the boundary as researcher input, with the rule shown |
| `scripts/run_batch.py::_load_guide_sections`, `scripts/twin2k500_sample.py::build_session_config` | correct logic, embedded in CLIs | copy into one shared YAML→config compiler, documented as derived from both |
| `ui/backend/api.py` | depends on a private orchestrator method; stale paths | reference only |
| `assessment/*` | legacy grocery-pilot scorecard | do not wire |

---

## 5. Feasibility matrix

Legend: **A** available now · **P** partially available (adapter or researcher input
needed) · **N** not implementable without new research.

### Flow 1 — generation

| Requested | Verdict | Evidence / condition |
|---|---|---|
| Define study, model, N groups, N replicates, condition labels, output dir | **A** | all are keys of the session config; replicates = independent configs |
| Explicit cost consent before paid calls | **P** | no cost model exists (§0.4); app supplies the rate table |
| Load own profiles JSON | **A** | `load_agent_from_json`; `field_provenance` already distinguishes `observed` / `derived` |
| Load own profiles CSV / YAML | **P** | no CSV/YAML profile reader exists; new mapping layer, must not invent fields |
| Twin2K profiles | **P** | `agents/twin2k500/` absent; needs `requirements-twin2k500.txt` + ETL run first |
| Project profiles | **A** | `agents/` — 5 populations present |
| Validate schema, unique ids, missing vars, sensitive data | **P** | schema validation free via `twin2k500_schema_mirror.AgentPayload`; PII scan is new |
| Distinguish enriched vs demographics-only | **A** | separate directories; `field_provenance` per field |
| Load / edit / download / preview guide YAML | **A** | with §0.1 handled: YAML authored, JSON compiled, both hashed |
| Run using the real agent/memory/moderation flow | **A** | subprocess to `run_full_session.py` |
| Live status: session, group, replicate, active speaker, turns, elapsed | **A** | tail `state_turn_N.json` + `transcript.json` |
| Live tokens and cost | **P** | tokens from `api_calls.jsonl`; cost computed by app |
| Errors and interruptions | **A** | `launcher_stdout.log`, non-zero exit, `stop_reason` |
| Persist transcript, config, guide, profiles, model, timestamps, logs, tokens, ids | **A** | already written per run; app adds the run manifest |
| Persist code version / commit | **P** | no git (§0.3) — content hash fallback |

### Flow 2 — benchmark

| Level | Metric | Verdict | Condition |
|---|---|---|---|
| 1 | Thematic recall, precision, reach | **P** | needs Gemini key, codebook, comparable window; `AUTOMATIC_VALIDATED` |
| 1 | Salience / prominence | **P** | `scripts/salience_hierarchy.py`, consumes coded output |
| 1 | Guide coverage | **P** | `LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC` in the registry — label as such |
| 1 | Category accumulation across groups | **P** | `scripts/saturation_analysis.py`; needs ≥2 groups |
| 1 | `tier1_coverage_by_word_count_curve`, `tier1_length_matched_*` | **N** | registry says `DEFERRED_NOT_IMPLEMENTED` |
| 2 | Words/turn, participation, Gini, adjacency, chain depth, moderator share | **A** | `structural_metrics_transportability.compute`, once turns are normalised — see the correction below |
| 2 | Specificity, consensus/disagreement, elaboration | **N (withheld)** | 9 rows `NOT_IN_REPORTED_INSTRUMENT` + `NOT_IN_REPORTED_INSTRUMENT`. Show the status; do not compute |
| 3 | Lexical diversity (TTR/MATTR) | **P** | `lexical_analysis.py` after corpus parameterisation |
| 3 | Between-speaker differentiation | **P** | same |
| 3 | Voice recognisable across questions | **P** | `agent_fidelity_stylometry.py` |
| 3 | Hyper-exactness | **P** | numeral-density **proxy only**; registry says it does not discharge the indicator |
| 3 | Profile / position consistency | **N** | `Human` evidence class; no automatic implementation exists |
| 3 | Unresolved cases | **A** | already modelled in the audit artefacts |

---

## 6. Proposed architecture for the new application

```
apps/focus_group_platform/
├── README.md
├── requirements.txt              app-only deps; never edits the root file
├── app/                          UI layer (thin; no analysis logic)
│   ├── Home.py
│   └── pages/                    1_Projects … 7_Configuration_and_provenance
├── platform_core/                pure Python; importable and testable headless
│   ├── projects.py               project store, per-project directories
│   ├── profiles/                 loaders + validators (JSON now, CSV/YAML later)
│   ├── guides/                   YAML ⇄ config compiler (§0.1), validation
│   ├── generation/
│   │   ├── config_builder.py     builds a session config dict
│   │   ├── runner.py             subprocess launcher over run_full_session.py
│   │   └── monitor.py            tails state_turn_N.json / api_calls.jsonl
│   ├── benchmark/
│   │   ├── registry.py           reads metric_registry.csv — never redefines a metric
│   │   ├── window.py             comparable-window adapter
│   │   ├── level1_thematic.py    wraps thematic_coding functions
│   │   ├── level2_structural.py  wraps structural_metrics_transportability.compute
│   │   └── level3_agent.py       copied+parameterised lexical/stylometry
│   ├── matching.py               human ⇄ synthetic correspondence table
│   ├── provenance.py             content hashes, run manifests, metric versions
│   ├── costing.py                dated rate table; tokens → USD
│   └── exports/                  CSV, XLSX, PNG/SVG, HTML report, results JSON
├── tests/
└── data/                         per project: uploads/ derived/ cache/ exports/
                                  (secrets never written here)
```

Two rules make the isolation real:

1. **`platform_core/` may import from `core/` and `scripts/`, but never write to
   `output/session_logs/`, `agents/`, `configs/`, `data/` or `analysis/`.** All app
   output lives under `apps/focus_group_platform/data/<project>/`.
2. **Generation runs as a subprocess**, exactly as `run_parallel_sessions.py` does.
   The app therefore never touches orchestrator internals and cannot break them.

Figure colours are fixed by the brief and differ from the existing figures — see
question Q3.

---

## 7. Two technology options

### Option A — Streamlit (recommended)

One dependency, one command (`streamlit run app/Home.py`), pure Python, no Node
toolchain, no build step, no second process. `st.data_editor` covers the editable
matching table; `st.file_uploader` covers uploads; live progress is a polling loop
over the artefacts the pipeline already writes incrementally.

*Advantages.* Lowest barrier for another researcher — the audience that matters
here. The whole app stays in the language the architecture is written in, so the
service layer is directly testable with the existing `pytest` suite. No `node_modules`
(the repo already carries ~10,000 files under `ui/frontend`). Shareable as a folder
plus `pip install -r requirements.txt`.

*Limitations.* The rerun-on-interaction model needs care with long jobs — solved
here because runs are subprocesses and state lives on disk, not in session memory.
Layout control is coarser than React. No REST API for headless reuse unless one is
added. Multi-user concurrency is weak; it is a single-researcher desktop tool.

### Option B — FastAPI + React/Vite (reuse `ui/` as reference)

*Advantages.* Real streaming (SSE already prototyped in `ui/backend/api.py`), a
documented HTTP API that other tools could call, full layout control, and a
deployable multi-user surface.

*Limitations.* Two processes and a Node build to install, run and keep current;
`ui/frontend` already pins React 19 / Vite 8 / Tailwind 4 / TypeScript 6, which is a
maintenance surface a lone researcher will not track. Roughly double the code for
the same features, and the streaming advantage is largely moot because the artefacts
are already on disk. It also re-invites coupling to orchestrator internals, which
the brief forbids.

**Recommendation: A.** Choose B only if the platform must be hosted for several
simultaneous users, or if a machine-readable API is a requirement rather than a
convenience. The decision is reversible: if `platform_core/` holds all logic and the
Streamlit pages stay thin, a FastAPI surface can be added later over the same
service layer without touching the analysis code.

---

## 8. Incremental plan with acceptance criteria

**Phase 1 — Specification.** User flows, JSON schemas for project/run/matching
manifests, wireframes for the seven sections, the interface↔architecture contract,
the test plan.
*Accept when:* every screen maps to a named function in `platform_core/`, and every
metric in the feasibility matrix maps to a registry row or is marked unavailable.

**Phase 2 — Isolated skeleton.** Projects, uploads, validation, demo mode with
fixtures. No external API call.
*Accept when:* the app runs end-to-end on fixtures; `pytest tests/` still 1,858
passing; a filesystem diff proves nothing outside `apps/` was written.

**Phase 3 — Generation integration.** Config compiler, subprocess runner, live
monitor, cost consent, persistence.
*Accept when:* a config built by the app is byte-comparable in structure to
`configs/experiment/macho_meals_fg1_run02.json`; a real 2-turn run produces the full
artefact set; replicates are labelled and never called seeds; killing the app
mid-run leaves the subprocess artefacts intact and resumable.

**Phase 4 — Benchmark integration.** Window adapter, matching assistant, level 1–3
runners, provenance, warnings.
*Accept when:* the matching table blocks execution while any row is ambiguous;
undefined values stay undefined in every export; withheld metrics render as
`NOT_IN_REPORTED_INSTRUMENT` and are not computed.

**Phase 5 — Verification.** Unit + integration tests; **replication of frozen
numbers**; invalid-input and partial-run tests; visual review; install docs.
*Accept when:* re-scoring the frozen Macho Meals corpus through the app reproduces
`structural_metrics_transportability` and `lexical_analysis` values exactly, and any
divergence is explained rather than absorbed.

---

## 9. Open questions

Listed in the response that accompanies this document.


---

## 10. Corrections applied after Phase 0 review (2026-08-04)

Recorded here rather than silently edited, so the audit trail survives.

**C-1 — `structural_metrics_transportability.compute` is corpus-agnostic but not
schema-agnostic.** Phase 0 called it "already generic: takes a turn list and a
roster". Verified by direct probe: passing turns keyed `speaker` / `role` / `text`
raises `KeyError: 'speaker_role'` at line 136. The function requires the
**standardized human transcript keys** — `speaker_role`, `content`,
`canonical_speaker_id`, and `speaker_name` or `speaker_id`. It is therefore reusable
across corpora *only after* turns are normalised to that schema. This raises the
canonical transcript schema from a convenience to a hard precondition of Level 2,
and fixes `canonical_speaker_id` as a required field.

**C-2 — `tier1_coverage_by_word_count_curve` is not `DEFERRED_NOT_IMPLEMENTED`.**
Phase 0 grouped it with the deferred metrics. The registry classes it
`AUTOMATIC_DIAGNOSTIC`; its producer exists but was never run. Only
`tier1_length_matched_recall` and
`tier1_length_matched_precision` carry `DEFERRED_NOT_IMPLEMENTED`. Corrected in
`PHASE1_METRIC_CAPABILITY_MATRIX.md`.

**C-3 — `reference_density` and `specificity` are two different metrics** and were
blurred in the Phase 0 feasibility matrix. The registry separates them: 
`reference_density` is `interaction` / `AUTOMATIC_DIAGNOSTIC`, computed
automatically; `specificity` is `interpretive` /
`NOT_IN_REPORTED_INSTRUMENT`, withheld. See ADR-004 and the capability
matrix.

**C-4 — status vocabulary.** The A/P/N shorthand used above is superseded by the
seven-value status model in `decisions/ADR-004-evaluation-status-model.md`. Read the
capability matrix, not the Phase 0 shorthand, when deciding what the application may
compute.
