# Phase 1 — Product specification

**Status: SPECIFICATION, written before the software and superseded in part by it.**
The original line here read *"No functional module exists yet"* — true when written,
false since Phase 2A, and left standing long enough that the document as a whole kept
reading as a forward-looking plan rather than a stale one. See the banner below and
Appendix 3.
Companion documents: `PHASE1_DATA_CONTRACTS.md`, `PHASE1_METRIC_CAPABILITY_MATRIX.md`,
`PHASE1_ACCEPTANCE_TEST_PLAN.md`, `PHASE1_WIREFRAMES.md`, `decisions/ADR-001..004`.
Evidence base: `PHASE0_REPOSITORY_AUDIT.md` (including its §10 corrections).

---

> ## ⚠️ THIS DOCUMENT DESCRIBES A DESIGN, NOT THE SOFTWARE AS BUILT
>
> It is written in the present tense throughout, and several things it describes were
> never implemented. A researcher who read it as a user guide found roughly half of a
> feature list that does not exist — and it was the only user-facing document, so
> there was nothing to correct the impression.
>
> **Section A3 is the register of what is not built.** Every affected section below
> also carries an inline marker. Nothing has been deleted: a design decision that was
> made and not yet built is a different thing from one that was withdrawn, and the
> record of both is worth keeping.
>
> **For what the tool actually does today, read `README.md`.**


## 1. What this application is, and what it is not

**Is.** A single-researcher desktop tool that (a) composes and launches synthetic
focus-group runs using the repository's existing architecture, and (b) scores human
and synthetic transcripts against the benchmark developed in this research,
producing traceable, exportable results.

**Is not.** A re-implementation of the architecture; a multi-user service; a place
where new metrics are invented; a way to compute metrics the research withheld; or
anything that writes to the frozen corpus.

**The governing constraint.** The experimental architecture is not modified. The
application consumes it through a service layer (`platform_core/`) and, for
generation, through separate OS processes running the existing public scripts
(ADR-002).

---

## 2. Directory structure

Adopted as proposed, with two documented adjustments.

> **SUPERSEDED IN FULL by A2.2.** The tree below is the original sketch. The entry
> point, the view layout, the package layout and the workspace location all differ
> from it, and `pages/`, `fixtures/` and `workspace/` do not exist here at all.
> Read A2.2 instead.

```
apps/focus_group_platform/
├── app.py                       Streamlit entry point
├── requirements.txt             app-only dependencies; the root file is never edited
├── README.md
├── pages/                       one file per UI section; thin, no analysis logic
│   ├── 1_Projects.py
│   ├── 2_Generate_focus_groups.py
│   ├── 3_Evaluate_transcripts.py
│   ├── 4_Results.py
│   ├── 5_Human_review_queue.py
│   ├── 6_Exports.py
│   └── 7_Configuration_and_provenance.py
├── platform_core/               pure Python, importable and testable headless
│   ├── projects/
│   ├── profiles/
│   ├── guides/
│   ├── generation/
│   ├── transcripts/             normalisation + comparable window
│   ├── matching/
│   ├── evaluation/
│   ├── reporting/
│   ├── provenance/
│   ├── costs/
│   └── catalog/                 ADJUSTMENT 1 — see below
├── docs/
│   └── decisions/
├── tests/
├── fixtures/                    ADJUSTMENT 2 — see below
└── workspace/                   per-project data; git-ignored; never committed
    └── <project_id>/
        ├── project.json
        ├── uploads/             exactly as uploaded, never rewritten
        ├── derived/             normalised transcripts, compiled guides, windows
        ├── runs/                generation job records + symlink-free copies of manifests
        ├── cache/               evaluator response cache, keyed by content hash
        ├── exports/
        └── trash/               recoverable project deletion
```

**Adjustment 1 — `platform_core/catalog/`.** The metric catalogue is neither
evaluation logic nor reporting: it is the read-only projection of
`analysis/production_evaluation/metric_registry.csv` plus this application's status
model. It is consulted by the UI (to render the catalogue), by `evaluation/` (to
refuse withheld metrics) and by `reporting/` (to stamp status onto every figure). A
shared read-only module is the honest home; burying it inside `evaluation/` would
imply the catalogue is an output of evaluation rather than its gate.

**Adjustment 2 — `fixtures/`.** Demo mode needs a small, synthetic, committed corpus
that is unmistakably not research data. It cannot live in `workspace/` (git-ignored,
per-project) and must not live in `tests/` (demo mode is a product feature, not a
test). Three fabricated participants, one 12-turn transcript pair, one guide.

---

## 3. The seven sections

### 3.1 Projects

Create, open, rename, duplicate settings, delete (recoverable to `trash/`), export a
project bundle. A project is the unit of isolation: every path the application writes
is under `workspace/<project_id>/`. Listing shows name, created date, counts of
profile sets, guides, runs, evaluations, and the last activity timestamp.

Deletion moves the directory to `workspace/<project_id>/../trash/<project_id>_<ts>/`
and requires typing the project name. Permanent deletion is a second, separate
action. No cascade ever reaches outside `workspace/`.

### 3.2 Generate focus groups

Four steps, each gated on the previous validating.

**A. Define the study.** Name, description, research objective, topic domain,
participant collective identity, moderator knowledge brief; model and generation
parameters; number of focus groups; number of replicates per group; condition
labels; output directory (fixed inside the project). Every field maps to a session
config key — see `PHASE1_DATA_CONTRACTS.md` §3.

Replicates are rendered as **independent runs with a label**
(`replicate_label`: `r1`, `r2`, `r3`). The UI never uses the word *seed* for them,
and shows a persistent note: *"Replicates are independent executions. The provider
API exposes no seed; two runs of the same configuration will differ."* This follows
the repository's own correction (`core/orchestrator.py` lines 111–125).

Panel *sampling* seeds are a different thing and, when Twin2K arrives, are recorded
as `panel_sampling_seed` (ADR-003 §5).

**B. Incorporate participants.** Three sources:

1. Upload own profiles — JSON at MVP (the schema the architecture already reads);
   CSV and YAML deferred to a post-MVP mapping layer, because a tabular file cannot
   express `field_provenance` and the application must not invent it.
2. Twin2K — **contract specified, integration deferred** (decision 5). The page
   shows the source, detects whether `agents/twin2k500/` exists, and if not explains
   the two prerequisites (`requirements-twin2k500.txt`, `scripts/twin2k500_etl.py`)
   instead of failing opaquely.
3. Project profiles already in the repository — `agents/` currently holds five
   populations.

Validation before any run, reported as a table, never as a silent pass:
schema conformance; unique `agent_id`; participant count against the guide's
expectations; missing required fields; missing optional fields, listed by name;
architecture compatibility (does `load_agent_from_json` accept it); a
personal-data scan (free-text fields matching email, phone, postcode, national-ID
patterns, plus any field name matching a configurable sensitive-terms list); and an
enriched-vs-demographics-only diff showing which fields differ between the two sets.

**Three-way provenance is mandatory and is displayed per field**: `from_file`,
`transformed` (with the transformation named), `undefined`. The application never
fills an absent attribute. `undefined` stays `undefined` all the way into the run
manifest. The existing agent payloads already carry a `field_provenance` map
(`observed` / `derived` / `observed_transcript_intro`), which the loader maps onto
this vocabulary and preserves.

**C. Incorporate the discussion guide.** Upload YAML, edit through a form, preview,
download the validated YAML, and — new, and mandatory — **compile** it to the
`discussion_guide` JSON array the orchestrator consumes. The full contract is
ADR-003. The preview renders sections, phases, scripted questions, transitions,
probes and moderation rules, and lists compile-time errors before execution is
possible.

> **SUPERSEDED — the dialog exists and DELIBERATELY REFUSES to estimate.** The only
> quantity available before a run is `--max-turns`, which is a ceiling, not a
> prediction; pricing a ceiling produces a figure that reads as a forecast and is not
> one. What the dialog actually shows: the session count, the models, the config and
> architecture hashes, and a stated refusal in place of the number. Real cost is priced
> from the session's own call ledger afterwards, and is left `Undefined` — or bounded —
> where the ledger cannot support a figure. The "estimated cost so far" in the live
> view below is likewise the *observed* cost so far. See A3.

**D. Run.** An explicit cost-consent dialog precedes any paid call: estimated calls,
estimated tokens, the pricing table version, the resulting estimate, and the
sentence *"This is an estimate computed from a local rate table, not a quotation."*
Consent is recorded in the run manifest with a timestamp.

Runs execute as separate OS processes (ADR-002). The live view shows session id,
condition, focus group, replicate label, active speaker or moderator, turns
completed, elapsed time, tokens consumed, estimated cost so far, and any operational
interruption. Progress is read from the artefacts the pipeline already writes
incrementally; the UI holds no run state that cannot be rebuilt from disk, so
closing or reloading the browser never orphans a job.

The application imposes none of: response content, the position a participant should
take, exact words per turn, a predetermined consensus, or themes that must appear.
Configurable qualitative style instructions are exposed only where the architecture
already exposes them (moderator restraint and reflection toggles, episodic depth,
participation mode), and each carries the architecture's own description.

### 3.3 Evaluate transcripts

Usable without generating anything.

Inputs: one or more human transcripts; one or more synthetic transcripts; the
corresponding guide; the deductive codebook when one exists; synthetic profiles when
required by a selected metric; a correspondence file or manual mapping; and metadata
for condition, focus group, replicate and model.

**Study context and comparison instructions** — a free-text box, stored verbatim in
the evaluation manifest and reproduced in the report. It is explicitly labelled:
*"Context for the reader and for your own record. It does not set metadata, does not
change any denominator, and is not parsed."* Structured metadata is the only thing
that drives computation.

**The pipeline is a five-step ladder, each step reviewable** (ADR-003 §6 for guides,
§4 below for transcripts):

```
raw transcript → normalised transcript → proposed comparable window
   → researcher review → locked comparable window → benchmark
```

**Matching assistant.** An editable table with one row per file: file, type
(human/synthetic), condition, focus group, replicate label, associated guide,
associated human referent, validation status. Statuses: `OK`, `AMBIGUOUS`,
`MISSING_REFERENT`, `CONFLICT`, `UNUSED`. The benchmark button is disabled while any
row is `AMBIGUOUS` or `CONFLICT`. `MISSING_REFERENT` does not block — it downgrades
that file's comparative metrics to `NOT_APPLICABLE_MISSING_HUMAN_REFERENCE`
(decision 6) and leaves independent descriptive metrics available.

### 3.4 Results

> **PARTLY BUILT.** The results surfaces exist inside the *New evaluation* view rather
> than as a separate Results section, and they are tables. The figure work in the last
> paragraph — the fixed palette, points-plus-range distribution plots — is **NOT
> BUILT**: the application renders one Altair bar chart (words-per-turn bins) and
> otherwise presents numbers as tables. See A3.

Summary panel; per-focus-group results; study-level results; human–synthetic
comparison; synthetic-condition comparison. Every figure and table carries the
metric status badge and, where the status is not `AVAILABLE_VALIDATED`, the reason.

Aggregation hierarchy is fixed and visible: **run → focus group → study replicate**.
Replicates are never pooled into a single sample. Synthetic turns are never treated
as independent observations. Undefined values render as `undefined`, never as 0, and
are excluded from denominators rather than counted as failures.

No inferential test is offered where the number of groups cannot support it; the
interface states the group count beside every study-level figure.

Figure palette for all new artefacts (decision 3): Human `#52525B`, Enriched
`#176B87`, Demographics-only `#D27D2D`. Distribution across groups and replicates is
shown as points plus range; bar charts that hide variability are not used. The
existing thesis figures keep their own palette and are not touched.

### 3.5 Human review queue

> **NOT BUILT.** There is no queue page and no queue artefact. The conditions listed
> below are all detected, and each is surfaced where it arises — a blocked job says so
> in the job table, an ambiguous assignment blocks the coverage matrix, an undefined
> metric states its reason beside itself — but nothing collects them into one list, and
> the per-item record of *what was proposed, who decided, and why* exists only for
> window decisions and for import/replace acts, through the audit log. See A3.

The queue is the application's honest exit from automation. Items enter it when:

* a comparable window cannot be derived unambiguously;
* a matching row is `AMBIGUOUS` or `CONFLICT`;
* a metric returns `REQUIRES_RESEARCHER_ADJUDICATION` (for example
  `reference_density` when the corpus produces unrepresentable or collapsed speaker
  labels — the function already reports `reference_density_valid`);
* a quote fails verbatim verification;
* a run ends with a non-zero exit code or truncated responses.

Each item records what was proposed, what the researcher decided, who decided, when,
and a free-text justification. Decisions are versioned and are part of provenance.
Nothing in the queue is auto-resolved by re-running the model.

### 3.6 Exports

> **PARTLY BUILT.** What exists: CSV tables, a structured results JSON, an embedded
> provenance block, and a study export package. What does **NOT** exist: XLSX, PNG and
> SVG figures, the HTML report, the per-figure provenance sidecar (see A1.7, which
> describes a format nothing writes), and the human-review list (there is no queue —
> see 3.5). See A3.

CSV and XLSX tables; PNG and SVG figures; an HTML report (PDF/DOCX post-MVP); a
structured results JSON; a provenance record per figure; a warnings-and-undefined
register; and the human-review list. Every export embeds the provenance block from
`PHASE1_DATA_CONTRACTS.md` §9. No export ever contains an API key.

### 3.7 Configuration and provenance

Model and evaluator configuration; the pricing table with its version and date;
the metric registry hash; schema versions; the code content hash; the demo-mode
switch; storage locations and disk usage; and a full audit log of the project.

API keys are read from the environment or `.env` and are **displayed only as
`sk-…{last4}`**. They are never written to project files, logs, manifests or
exports.

---

## 4. Transcript normalisation and the comparable window

Normalisation writes to `derived/`; uploads in `uploads/` are never rewritten
(`PHASE1_DATA_CONTRACTS.md` §5).

The canonical schema is not cosmetic. `structural_metrics_transportability.compute`
requires `speaker_role`, `content` and `canonical_speaker_id` and raises `KeyError`
without them (PHASE0 §10, C-1). Level 2 is therefore unavailable until normalisation
succeeds, and the UI states that dependency rather than presenting an empty result.

Window derivation proposes boundaries and shows them **as text, in context**, with
the rule that produced them and a confidence flag. Where the start of the substantive
first question cannot be located unambiguously inside its entry, the item goes to the
review queue. Positional truncation ("drop the first N turns") is never applied
silently; if a researcher chooses a positional boundary, that choice is recorded as a
researcher decision, not as a derivation.

The frozen Macho Meals corpus is exempt: its windows already exist
(`comparable_transcript.json`) and are read, not recomputed (ADR-003 §7).

---

## 5. Demo mode

> **NOT BUILT.** `demo_mode` survives as a boolean field on the project record and in
> the provenance block, and it is written and read faithfully — but nothing consumes
> it. There is no `fixtures/` directory, no banner, no `DEMO_` filename prefix, and
> setting the flag does **not** prevent an API call. **Do not rely on it as a safety
> mechanism.** What actually prevents accidental spending is that generation lives on
> its own screen, requires typing the plan id, and passes a launch-time check. See A3.

A switch in Configuration. When on: no external API call is possible (the generation
runner refuses to launch and the evaluator client is replaced by a fixture reader),
every screen is populated from `fixtures/`, and a persistent banner reads
*"Demo mode — fabricated data, no API calls."* Exports produced in demo mode are
stamped `demo_mode: true` in their provenance block and their filenames carry a
`DEMO_` prefix.

---

## 6. Metric explanations

Every metric shows a one-sentence plain-language gloss beside its technical
definition, never instead of it. The gloss is stored in the catalogue with an
`explanation_source` field so it is auditable, and the technical definition is the
registry's own text, quoted rather than paraphrased.

---

## 7. Security and privacy

| Requirement | Specification |
|---|---|
| Local-first storage | ⚠️ **PATH SUPERSEDED by A1.1** — projects live in the user application-data directory, OUTSIDE the repository, not under `apps/focus_group_platform/workspace/`. The requirement itself holds: no network storage, no telemetry. |
| Project separation | All paths derive from `workspace/<project_id>/`; `project_id` is a generated slug, never user-supplied free text. |
| Path validation | Every resolved path must be `Path.resolve()`-relative to the project root; `..`, absolute paths, symlinks and drive changes are rejected. One shared `safe_path(project, *parts)` helper; no module builds paths by concatenation. |
| File-type validation | Extension **and** content sniffing (JSON parses, YAML parses, CSV has a header). Size cap per upload. Archive uploads rejected at MVP. |
| Path traversal | Uploaded filenames are replaced by a generated storage name; the original name is metadata only and is never used to build a path. |
| Secret handling | Keys from environment/`.env` only; masked in the UI; excluded from manifests, logs and exports by an allowlist serialiser, not a denylist. |
| Personal-data warnings | ⚠️ **PARTLY BUILT — see A3.** `profiles.scan_sensitive()` runs on every profile set and its findings reach `ProfileSet.sensitive_findings`. **No view renders them**, so no warning reaches the researcher, and **transcript uploads are not scanned at all**. As written this row describes a control that does not operate. |
| Recoverable deletion | Two-step, via `trash/`. |
| Paid-call confirmation | ⚠️ **SUPERSEDED — see 3.2D and A3.** The dialog exists, requires typing the plan id, and records the act in the append-only audit log. It carries NO estimate, by decision: the only pre-run quantity is a turn ceiling, and pricing a ceiling produces a forecast that is not one. |
| Frozen corpus | A single read-only guard module holds the frozen path list (`core/`, `agents/`, `configs/`, `output/session_logs/`, `data/datasets_transcripts/standardized/`, `analysis/`). Any write attempt raises. The guard is asserted in tests, not merely documented. |

---

## 8. Out of scope for the MVP

CSV/YAML profile import; Twin2K operational integration; PDF and DOCX export;
multi-user access; scheduling; the deferred `tier1_length_matched_*` metrics; and any
computation of `NOT_IN_REPORTED_INSTRUMENT` metrics — which is a permanent
exclusion, not a deferral.


---

# AMENDMENT 1 — Phase 1 conditional approval (2026-08-04)

Phase 1 was approved conditionally. The decisions below **supersede** the text above
where they conflict. The superseded text is deliberately left in place: it records
what was proposed and reviewed, and rewriting it would erase the review.

## A1.1 Workspace moves out of the repository (ADR-005)

§2 placed user data at `apps/focus_group_platform/workspace/`. **Superseded.** The
data directory is external and resolved in this order:

1. `FOCUS_GROUP_PLATFORM_DATA_DIR`, when set;
2. the operating system's local application-data directory
   (`%LOCALAPPDATA%\FocusGroupPlatform` on Windows,
   `$XDG_DATA_HOME/focus-group-platform` or `~/.local/share/focus-group-platform` on
   Linux, `~/Library/Application Support/FocusGroupPlatform` on macOS);
3. an explicitly injected directory, used only by tests.

No user data is created at install time, at package import, or during tests. Directory
creation is an explicit act (`ensure=True`), never a side effect of resolution.
`apps/focus_group_platform/workspace/` is no longer a destination and is not created.

## A1.2 Macho Meals is an acceptance corpus, not a project (ADR-006)

§3.1's wireframe showed a "Macho Meals (RO)" project row. **Superseded.** The corpus
is: (a) the internal read-only acceptance corpus, and (b) optionally visible as a
reference only under an explicit developer flag
(`FOCUS_GROUP_PLATFORM_DEV_REFERENCE=1`). It never appears as an ordinary project, is
never copied into user space, and is excluded from any external distribution. User
demo mode uses `fixtures/` only.

## A1.3 YAML profiles are in the MVP

§3.2 excluded YAML alongside CSV. **Superseded, and the original reasoning was
wrong.** YAML is not tabular; it expresses the same nested schema as JSON, including
`field_provenance`. JSON and YAML are both accepted at MVP and must produce identical
canonical representations from identical information. **CSV remains out** until an
explicit column-mapping and provenance layer exists — that reasoning stands, because a
flat table genuinely cannot carry per-field provenance without an added mapping.

## A1.4 Frozen protection is a manifest, not a root (ADR-006)

§7 listed `output/session_logs/` as a frozen path. **Superseded, and it was an
error**: the architecture writes new sessions there, so freezing the root would break
generation. Protection now applies to an explicit manifest of frozen session
directories (`frozen_sessions.json`). New sessions are permitted under
`output/session_logs/` provided the `session_id` is project-prefixed and unique.

Before any launch the application resolves the exact destination, rejects a collision
with **any** existing directory, rejects any destination in the frozen manifest, and
never overwrites or auto-resumes an existing directory.

## A1.5 Participant model is not a session-level field (ADR-007)

§3.2 implied the participant model is chosen in the study form and flows through the
session config. **Superseded.** `core/participant_agent.py` line 951 states that
"model and max_tokens come from the participant's agent_payload.simulation_config",
and line 964 reads it there. Selecting a participant model therefore requires a
**derived copy** of each profile inside the project's artefacts, with the model
applied there and the transformation recorded. Originals in `agents/` and in
`uploads/` are never modified.

`participant_response_max_tokens` is clarified in the interface as a **technical
ceiling on output length, not a target length and not an instruction to make
responses uniform**. The label reads: *"Maximum output tokens per participant turn. A
ceiling, not a target — it does not ask for longer or more uniform answers."*

## A1.6 Level 1 refuses to substitute an evaluator (ADR-004 amendment)

The evaluator model version is part of the instrument. If the required model is
unavailable, Level 1 does not run; its metrics take the runtime status
`NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE`; an explicit message names the required model
and why no substitute is used. No alternative model is added without new documented
validation.

## A1.7 Figure provenance is a sidecar

Figures carry only `metric_id`, the exploratory or withheld status when applicable,
and the essential unit or denominator. The complete `ProvenanceBlock` is written to a
sidecar JSON beside the figure and included in the export bundle.


---

# AMENDMENT 2 - Phase 2A.1 hardening (2026-08-04)

Findings from an independent security review of the Phase 2A code. These supersede the
text above where they conflict; the superseded text stays so the review history is
legible.

## A2.1 Security corrections

Four hardening decisions now bind the specification: identifiers from files are
untrusted input (ADR-008); `project.json` is data, never path authority (ADR-009);
derived artefacts are written atomically and never overwritten by default (ADR-010);
and an injected data directory inside the repository is refused unless a test opts in
explicitly (ADR-005 amended).

## A2.2 Directory structure, as built

**Revised 2026-08-05.** The previous version of this amendment was itself stale — it
said `generation/` did not exist, and it is now the largest package in the application.
It also corrected only the `platform_core/` half of the tree in section 2, leaving the
interface half reading as fact. The whole of section 2's tree is superseded by this.

**Interface.** `app/streamlit_app.py` is the entry point (not `app.py`), and the views
live in `app/views/` as four modules — `home.py`, `frozen_benchmark.py`,
`new_evaluation.py`, `generate.py` — plus `windows_tab.py`, which is a tab inside
*New evaluation* rather than a view. There is **no `pages/` directory and no numbered
page files**; in particular there is no `4_Results.py`, no `5_Human_review_queue.py`
and no `6_Exports.py` — results, exports and window review are tabs inside the two
project views, and the review queue does not exist at all (see 3.5 and A3).

**Core.** `platform_core/` holds flat modules — `aggregate.py`, `analysis_window.py`,
`atomic.py`, `catalog.py`, `config.py`, `design.py`, `design_aggregate.py`,
`frozen.py`, `guides.py`, `level2.py`, `paths.py`, `pricing.py`, `profiles.py`,
`projects.py`, `provenance.py`, `thematic.py`, `theme.py`, `transcripts.py`,
`windows.py` — plus two subpackages that grew large enough to need one:
`platform_core/generation/` (the whole run path: planner, bundle, launcher, worker,
terminal, queue, queue_supervisor, importer, preflight, credentials, pricing_ledger,
monitor, effective_config, config_builder, profiles_source, smoke_manifest) and
`platform_core/services/` (audit, benchmark, design, import, window, context).
`matching/`, `evaluation/` and `reporting/` were never created; that work lives in
`design.py`, `level2.py`/`thematic.py`, and the export services respectively.

**Workspace.** Not under the application at all — see A1.1. Projects live in the user's
application-data directory, outside the repository.

**Also present and not in section 2's tree:** `README.md` (the researcher-facing guide,
written 2026-08-05), `.claude/launch.json` (dev-server config), and
`platform_core/code_manifest.txt` (the architecture pin). `fixtures/` does not exist —
see A3.

---

# Appendix 3 — Implementation status register

Written 2026-08-05, after a researcher-perspective review found that this document
reads as a promise the software does not keep. Each row states what section 1–8
describes, what exists instead, and whether the gap is *unbuilt* (still intended) or
*superseded* (deliberately not built, with the reason).

| Described in | Status | What exists instead |
|---|---|---|
| §3.5 Human review queue | **Unbuilt** | Every trigger condition is detected and surfaced where it arises; nothing aggregates them. Window and import decisions are recorded with researcher, timestamp and note in the append-only audit log. |
| §3.6 XLSX / PNG / SVG / HTML exports | **Unbuilt** | CSV and JSON only. |
| §3.4 figure palette, points-plus-range plots | **Unbuilt** | One Altair bar chart (words-per-turn bins, explicitly ordered); everything else is a table. |
| §5 Demo mode | **Unbuilt** | The `demo_mode` flag is stored and reported but has no effect. It does not prevent an API call. |
| A1.7 Figure provenance sidecar | **Unbuilt** | Follows from the absence of figure exports. The format is specified; nothing writes it. |
| §7 personal-data scan surfaced to the researcher | **Partly built** | `profiles.scan_sensitive()` runs on every profile set and its findings reach `ProfileSet.sensitive_findings` — but **no view renders them**, so a researcher never sees the result. A scan whose output nobody reads is not a control. |
| §3.2 cost-consent dialog with an estimate | **Superseded** | The dialog exists and refuses to estimate. The only figure available before a run is `--max-turns`, which is a ceiling; pricing a ceiling produces something that reads as a forecast and is not one. The dialog shows what will run, the config hashes, and a stated refusal. Real cost is priced from the ledger afterwards. |
| §2 directory structure: `README.md` | **Now built** | Written 2026-08-05. It, not this document, is the user-facing guide. |
| §2 directory structure: `fixtures/` | **Unbuilt** | Follows from demo mode. |

## A3.1 What this means for reading sections 1–8

The **methodological** commitments in this document are all implemented and are the
part worth trusting: undefined never becomes zero, replicates are never pooled,
comparability is declared rather than assumed, nothing is inferred from a filename,
and no metric is presented above the status its evidence supports. Those are enforced
in code and covered by tests.

The **interface inventory** is where the drift is. Read sections 3.4 to 3.6, section 5,
and A1.7 as intent, and this register as fact.

## A3.2 Why the drift happened, so it does not repeat

This document was written before the application and never revised as the application
diverged from it. The amendments in Appendix 1 correct *decisions* that changed; there
was no mechanism for recording *features that were specified and not built*, so the
unbuilt ones kept reading as present-tense fact. This register is that mechanism. A
feature that is specified and then not built gets a row here at the moment that becomes
true — not at the next audit.
