# Phase 1 — Acceptance test plan

**Status: SPECIFICATION.** Nothing here is implemented yet. The plan is written so
that each criterion is mechanically checkable; a criterion that can only be judged by
reading is marked as a review step, not a test.

---

## 1. Levels of testing

| Level | Scope | Runs in CI-equivalent (`py -m pytest`) |
|---|---|---|
| L1 unit | Pure functions in `platform_core/` — compilers, validators, hashers, normalisers, cost maths | yes, offline |
| L2 contract | Schemas round-trip; the compiled session config is accepted by the architecture's own reader | yes, offline |
| L3 integration | Generation subprocess lifecycle with a stub runner; evaluation over fixtures | yes, offline |
| L4 acceptance | Macho Meals read-only replication | yes, offline (no API — uses frozen coded outputs) |
| L5 safety | Frozen-corpus immutability, path traversal, secret leakage | yes, offline |
| L6 review | Visual inspection of the seven sections; documentation walkthrough | manual, checklisted |

**The existing suite is the outer guard.** `py -m pytest tests/` must remain at its
current 1,858 passing / 1 skipped. Any drop is a failure of this project regardless
of what the application's own tests say.

---

## 2. L4 — Macho Meals read-only acceptance

The strongest available check: the application must reproduce numbers the thesis
already froze.

### 2.1 Design

1. **Import.** Register the five standardized human transcripts
   (`data/datasets_transcripts/standardized/macho_meals/fg{1..5}/transcript.json`)
   and the thirty synthetic runs (`output/session_logs/macho_meals_fg{1..5}[_demoonly]_run0{1..3}/`)
   as an *external read-only corpus*. The application copies nothing into
   `workspace/` except hashes and derived artefacts; it opens every source file in
   read mode only.
2. **Reconstruct comparable units.** For this corpus the windows already exist
   (`comparable_transcript.json`). The test asserts that the application **reads**
   them rather than re-deriving them, and that the retained-text hash matches
   `freeze_evaluator_inputs.py`'s recorded hash. Re-derivation is a failure: the
   frozen window is the artefact of record.
3. **Compute only what the catalogue permits.** Metrics with status
   `AVAILABLE_VALIDATED` or `AVAILABLE_EXPLORATORY` **and** an existing frozen
   counterpart. Level 1 uses the frozen coded outputs — no evaluator call is made, so
   the acceptance run costs nothing and is deterministic.
4. **Compare against frozen artefacts.**

| Application output | Frozen counterpart |
|---|---|
| Level 2 structural + interaction, per run | the frozen human values embedded in `structural_metrics_transportability._frozen_human_values` and the values behind `analysis/production_evaluation/final/FINAL_RESULTS_TABLES.xlsx` sheet `3_Structural_Interaction` |
| Level 3 lexical diversity, between-speaker similarity | `analysis/production_evaluation/final/lexical_analysis.json` |
| Level 3 attribution, chance-corrected | `analysis/production_evaluation/agent_fidelity/agent_fidelity_stylometry.json` |
| Level 1 recall / precision / F1 / reach | `analysis/production_evaluation/results/primary_effects_by_fg.csv` |
| Accumulation | `analysis/production_evaluation/final/saturation_analysis.json` |

### 2.2 Tolerances

| Quantity | Tolerance | Reason |
|---|---|---|
| Counts (turns, words, participants, denominators) | **exact** | an off-by-one is a definition change |
| Proportions and ratios stored rounded to 4 dp | `abs(a-b) <= 5e-5` | the frozen artefacts round at 4 dp |
| Gini, IQR, medians | `abs(a-b) <= 1e-6` | computed in one pass from the same input |
| Similarity/cosine/Jensen–Shannon | `abs(a-b) <= 1e-9` | pure float arithmetic, no sampling |
| Any metric involving subsampling (`lexical_analysis` budgeted overlap) | exact, **with the sampling parameters pinned** | the routine is deterministic given its offsets; if it cannot be pinned, the metric is excluded from L4 and that exclusion is recorded |
| `null` / undefined | identity — `null` must equal `null` | the whole point of the undefined rule |

A tolerance is a property of the comparison, declared in the test, never widened to
make a failing case pass. Widening a tolerance requires a documented reason in the
test file and a note in the delivery.

### 2.3 Hard failure conditions

The suite fails, loudly and without partial credit, if any of these change relative
to the frozen record:

* a **denominator** — value or definition;
* an **exclusion** — which items were dropped, why, or how many;
* the **aggregation hierarchy** — anything other than run → focus group → study
  replicate;
* a **metric status** — for example a metric moving out of
  `NOT_IN_REPORTED_INSTRUMENT`;
* the **number of focus groups, runs or replicates** entering any figure;
* a value moving from `null` to a number, or a number to `null`.

### 2.4 Immutability proof

Before the run, record `(path, size, mtime_ns, sha256)` for every file under
`core/`, `agents/`, `configs/`, `prompts/`, `output/session_logs/`,
`data/datasets_transcripts/standardized/` and `analysis/`. After the run, recompute
and assert identity. The test fails on the first difference and names the file.

This is stronger than checking the application's own writes, because it also catches
an imported module writing a cache or a `.pyc`-adjacent artefact into a frozen tree.
`__pycache__` is excluded from the comparison by an explicit, documented rule.

### 2.5 What L4 cannot prove

Stated so nobody over-reads a green suite: L4 shows the application reproduces the
thesis pipeline **on the corpus the pipeline was written for**. It says nothing about
correctness on a new corpus, nothing about the withheld metrics, and nothing about
the evaluator, which L4 deliberately does not call.

---

## 3. L1–L3 — acceptance criteria by capability

### 3.1 Guides
* A valid YAML compiles; recompiling the same bytes reproduces the same
  `compiled_json_sha256` (determinism).
* Compiling twice in different processes gives the same hash (no dict-ordering or
  timestamp leakage).
* An invalid phase name fails compilation with the section index and the offending
  value; it does not fall back to a default phase.
* Mutating the compiled JSON on disk sets `correspondence_ok = false` and **blocks
  execution** — the test asserts the run button's guard, not just a warning.
* The frozen Macho Meals configs are never recompiled: pointing the application at
  `configs/experiment/macho_meals_fg1_run02.json` uses the existing
  `discussion_guide` array as-is.

### 3.2 Profiles
* A payload accepted by `load_agent_from_json` is accepted by the application, and
  vice versa — no divergent validation.
* Duplicate `agent_id` blocks.
* A missing optional field appears in `undefined_fields` and is **absent** from the
  compiled config; no default is inserted.
* `field_provenance` round-trips: `observed` → `from_file`, `derived` →
  `transformed`, absent → `undefined`.
* The sensitive-data scan flags a planted email, phone and postcode in a fixture, and
  masks them in the report.

### 3.3 Generation boundary (ADR-002)
* The runner constructs a command line invoking `scripts/run_full_session.py` and
  **never** imports `core.orchestrator`. Asserted by inspecting
  `platform_core/generation/` sources for the string `orchestrator` and for any
  underscore-prefixed attribute access.
* With a stub script standing in for `run_full_session.py`, the full lifecycle is
  exercised: launch → running → completed, and launch → killed → `orphaned`.
* Restarting the application re-derives every job status from disk; a job launched
  before the restart is not lost and is not relaunched.
* Two jobs with the same `session_id` are refused before launch.
* Cost consent is required before launch; the recorded estimate and pricing version
  are present in the job record.
* Demo mode makes launch impossible — the test asserts an exception, not a disabled
  button.

### 3.4 Transcript normalisation and windows
* Both known source schemas normalise; unmapped source fields are retained in
  `unmapped_source_fields`, not dropped.
* Normalisation writes only under `derived/`; the uploaded bytes are unchanged
  (hash equality after the operation).
* Synthetic `canonical_speaker_id` and `speaker_role` appear in `derived_fields`.
* A transcript missing `canonical_speaker_id` after normalisation makes Level 2
  resolve to `NOT_APPLICABLE_MISSING_INPUT` with that reason — **not** a `KeyError`
  surfacing to the user.
* An ambiguous window boundary produces `unambiguous = false`, a review-queue item,
  and a blocked benchmark.
* A positional boundary is only ever recorded with
  `positional_fallback_used = true` and a researcher id.

### 3.5 Matching and status
* `AMBIGUOUS` or `CONFLICT` in any row blocks execution.
* `MISSING_REFERENT` does not block; the affected comparative metrics resolve to
  `NOT_APPLICABLE_MISSING_HUMAN_REFERENCE` with `value = null`, and independent
  descriptive metrics still produce values.
* A withheld metric has no code path to a value: a test attempts to force one through
  the evaluation API and asserts it raises.
* `specificity` and `reference_density` never appear in the same table column, figure
  series or caption — asserted on the rendering layer's output structures.

### 3.6 Exports and provenance
* Every exported row and figure carries a complete `ProvenanceBlock`; a missing field
  fails the test.
* `code_content_hash` is stable across runs on unchanged files and changes when any
  listed file changes; a missing listed file raises rather than being skipped.
* No export, log or manifest contains a string matching an API-key pattern — asserted
  by scanning every produced artefact, with a planted key in the environment.
* A model absent from the pricing table yields `undefined` cost and a lower-bound
  label, not zero.

### 3.7 Safety (L5)
* Path traversal: `../`, absolute paths, symlinks and drive-letter changes are
  rejected by `safe_path()` for every entry point that accepts a filename.
* Uploaded filenames never reach the filesystem; storage names are generated.
* A write attempted anywhere under a frozen path raises from the guard module.
* Project deletion moves to `trash/` and touches nothing outside `workspace/`.

---

## 4. L6 — manual review checklist

Not automatable, so it is a checklist with named reviewers and a date:

1. Each of the seven sections renders with fixture data and no traceback.
2. Every metric shown carries a status badge and, where not
   `AVAILABLE_VALIDATED`, a visible reason.
3. Replicates are never described as seeds anywhere in the interface text.
4. The three figure colours match decision 3 exactly.
5. Figures show dispersion across groups and replicates; no bar chart hides
   variability.
6. Demo-mode banner is present and exports carry the `DEMO_` prefix.
7. The cost dialog states that the figure is an estimate and names the pricing table
   version.
8. Installation instructions work from a clean checkout on a machine with only
   `requirements.txt` installed.

---

## 5. Definition of done for Phase 5

All of: L1–L5 green; the repository suite still 1,858 passing / 1 skipped; the L4
immutability proof clean; the L6 checklist signed; and `README.md` sufficient for a
researcher who has never seen the repository to install, run demo mode, and score a
transcript pair without assistance.


---

# AMENDMENT 1 - Phase 1 conditional approval (2026-08-04)

The decisions below **supersede** the text above where they conflict. Superseded text
is left in place so the review history stays legible.

## A1.1 Immutability test - three outcomes, not two (ADR-006)

Section 2.4 compared every file under `output/session_logs/` and would now fail
spuriously, because the application legitimately creates new session directories
there. **Superseded.** The check classifies each observation:

| Observation | Verdict |
|---|---|
| A path in `frozen_sessions.json` changed in any way - content, size, mtime, or removal | **FAIL** |
| A new directory appeared under `output/session_logs/` whose `session_id` is project-prefixed, unique, and absent from the frozen manifest | **PASS** - an authorised new run |
| A new directory appeared that is not project-prefixed, or collides with a manifest entry | **FAIL** |
| Any change under `core/`, `agents/`, `configs/`, `prompts/`, `data/datasets_transcripts/standardized/`, `analysis/` | **FAIL** |

The frozen manifest is the authority; the session-log root is not.

## A1.2 Macho Meals is never a project (ADR-006)

The acceptance corpus is registered as a read-only external corpus, not a project. The
test asserts: no directory is created for it under the data directory, no file of it
is copied into user space, and it is invisible unless
`FOCUS_GROUP_PLATFORM_DEV_REFERENCE=1`.

## A1.3 Tests create no user data

Every test injects a temporary data directory. A test asserts that importing
`platform_core` creates nothing, and that resolution without `ensure=True` creates
nothing.

## A1.4 New acceptance criteria

* JSON and YAML profiles carrying the same information produce the same
  `canonical_sha256`.
* Applying a participant model creates a derived profile; the original file's hash is
  unchanged; the transformation is recorded.
* A session destination that collides with any existing directory, or matches the
  frozen manifest, is refused **before** any file is opened.
* Level 1 with the required evaluator absent yields
  `NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE` for every Level 1 metric and calls nothing.
* A figure emits a sidecar `.provenance.json`; the figure itself carries only
  `metric_id`, status and unit/denominator.


---

# AMENDMENT 2 - Phase 2A.1 hardening (2026-08-04)

Findings from an independent security review of the Phase 2A code. These supersede the
text above where they conflict; the superseded text stays so the review history is
legible.

## A2.1 The immutability proof is split in two

Section 2.4 and AMENDMENT 1 A1.1 are superseded. Three rejected shortcuts, named so
they are not reintroduced: taking the baseline *after* running the suite; silently
excluding `cross_model_manifest_q3.json`; accepting timestamp drift through a
tolerance. None is used.

**A. `platform_acceptance_immutability`** - `tests/test_platform_acceptance_immutability.py`.
Hash every protected file, run only the platform's own work, hash again. Any change,
removal or addition inside a protected path fails. The `output/session_logs/` directory
set must also be identical, because the platform created no run.

**B. `repository_regression`** - a separate check, not an immutability proof.
`tests/test_cross_model_audit_q3.py` regenerates
`analysis/production_evaluation/emergent_calibration_q3/cross_model_manifest_q3.json`
on every run; only its `built_utc` field changes. This is pre-existing repository
behaviour, unrelated to the platform. A fully clean repository check requires running
that suite in a disposable copy of the tree. Neither the test nor the artefact is
edited from this phase.

## A2.2 The acceptance set is read, not inferred

A naming pattern (`run0[1-3]`) is wrong: fg4 and fg5 enriched use **run01, run03,
run04**. The 30 acceptance runs are read from
`analysis/production_evaluation/results/structural_interaction_metrics_long.csv`,
column `physical_run`, cross-checked against the comparable-window directory. The
frozen manifest grew from 47 to **77 entries / 65 acceptance** (42 session directories
of which 30 are canonical, 30 comparable windows, 5 human transcript sets).

## A2.3 Phase 2A.1 criteria

* Fifteen hostile identifiers refused at each of four entry points, creating no file.
* A rejected guide writes no partial JSON.
* A tampered `project.json` produces no write.
* A collision overwrites neither a derived profile nor a compiled guide.
* A failed verification leaves the previous destination byte-identical.
* No temporary file survives a failure.
* The frozen manifest and the catalogue keep their counts.

## A2.4 Phase 2B golden criteria

The 5 human and 30 synthetic documents reproduce the frozen structural values at the
precision the frozen artefact stored, with counts compared exactly. Two producers are
routed by side, because the frozen values were produced by two different ones.
