# Audit handoff and continuation guide

Last updated: 2026-08-05 (Phase 3F closed; 3-session pilot run; two adversarial review passes)  
Repository: `my_qualitative_project`  
Application: `apps/focus_group_platform`

## 1. Purpose of this document

This document is the continuity record for another model or researcher who must
continue auditing and guiding development of the synthetic focus-group platform.
It records the product objective, methodological boundaries, architecture already
built, decisions that must not be reversed casually, verified strengths, open
defects, and the recommended order of work.

Do not treat delivery reports as proof by themselves. For every new phase, inspect
the implementation, tests, persisted contracts, and frozen artefacts. Distinguish:

- what the code actually enforces;
- what a test demonstrates;
- what a delivery report merely claims;
- what remains a methodological decision rather than a software fact.

## 2. Product objective

The platform should make the thesis architecture usable by other researchers
without modifying or weakening the existing agent architecture. It should support:

1. generating synthetic focus groups from uploaded agent profiles or a locally
   available Twin2K source;
2. supplying and validating a YAML discussion guide;
3. running multiple focus groups and independent replicates through the existing
   public CLI;
4. importing human and synthetic transcripts;
5. defining comparable analytical windows with explicit researcher review;
6. calculating and exporting the benchmark metrics supported by the available
   evidence;
7. preserving provenance, denominators, undefined values, methodological status,
   token use, and cost where defensibly calculable;
8. remaining transferable across studies and models.

The platform must not hard-code the content or length of participant responses.
The architecture may explain focus-group behaviour, construct memory, and organise
participation, while leaving response content and appropriate length to the model.
This is a substantive methodological principle of the thesis, not merely a UI
preference.

## 3. Non-negotiable methodological boundaries

- LLM generation replicates are independent executions. They are not shared seeds.
- Never pool all synthetic sessions as independent observations when the design is
  hierarchical.
- Missing or undefined values remain null; they are never converted to zero.
- New uploads may not silently use the frozen Macho Meals human reference.
- Structural comparability does not imply thematic fidelity.
- A user-supplied codebook identifier alone does not constitute a validated coding
  procedure.
- Primary coding and sensitivity analyses remain separate.
- Full transcripts and comparable windows are different analytical namespaces.
- Only locked, fresh comparable windows may enter comparative aggregation.
- Window-length differences are diagnostics, not automatic exclusion criteria;
  verbosity and interaction length may themselves be outcomes.
- Do not infer conditions, focus groups, replicates, or matching from filenames.
- Do not claim inferential significance when the design only supports descriptive
  comparison.
- Metrics marked withheld, deferred, diagnostic, derived, or exploratory must not
  be presented as validated primary results.

## 4. Frozen study structure

The thesis benchmark contains:

- five human focus groups;
- two synthetic conditions: enriched and demographics-only;
- three independent synthetic executions per focus group and condition;
- 30 synthetic analytical sessions and five human analytical documents.

Two synthetic aggregation routes are intentionally distinct:

1. **Focus-group route:** three executions within each FG × condition cell.
2. **Study-replicate route:** replicate index `k` groups the `k`-labelled execution
   across FG1–FG5. The index does not imply a common random seed.

Never flatten 15 sessions from one condition into a single independent sample.

## 5. Implemented architecture through Phase 3D

### 5.1 Offline core

Implemented and tested components include:

- safe project paths, atomic writes, provenance, manifests, profile and guide
  validation;
- transcript schema detection and per-turn normalisation;
- separate historical human and synthetic Level 2 producers;
- frozen-compatible structural metrics;
- hierarchical structural aggregation;
- offline Level 1 thematic readers over frozen coded artefacts;
- explicit study designs and transcript assignments;
- hash-linked validation and Level 2 results;
- versioned comparable windows for both human and synthetic transcripts;
- analysis-input identity based on transcript and window hashes;
- a Streamlit interface with benchmark, evaluation, windows, coverage, comparison,
  export, and generation views.

### 5.2 Level 1

The offline thematic layer currently supports frozen-study views of:

- recall;
- precision;
- secondary F1;
- participant reach;
- shared-only reach;
- thematic recurrence;
- thematic-order agreement;
- inductive theme accumulation;
- separate sensitivity views.

Guide coverage is deferred because no validated definition, producer, and frozen
artefact exist. Do not infer it from recall.

### 5.3 Level 2

The frozen structural path reproduces the seven published structural values. The
new-corpus path supports per-session results and design-driven Route A and Route B.
Counts such as total words and participant turns are labelled as producer counts,
not silently promoted to registry-validated metrics.

### 5.4 Windows

For new corpora, both human and synthetic sides require reviewed analytical windows.
Locked windows are immutable and versioned. Superseding a window retains the old
artefact and makes dependent results stale. Full-run results remain descriptive and
cannot enter matched aggregation.

### 5.5 Generation boundary

Generation is integrated through a subprocess calling the public CLI:

```text
scripts/run_full_session.py --config <path> --max-turns N --mode <mode>
```

The application must never import the orchestrator or use its private methods. Job
and progress state is intended to be reconstructed from disk rather than held in
Streamlit session state.

## 6. Important design decisions already made

- Streamlit is a thin presentation layer; business logic belongs in
  `platform_core` services.
- The frozen benchmark and user projects are separate contexts.
- New-corpus structural comparison requires an explicit human–synthetic matching
  declaration.
- Study design is configurable; 5 FGs × 3 replicates is not hard-coded as the
  universal design.
- Transcript IDs are collision-safe and imports are versioned or rejected rather
  than overwritten silently.
- Validation, canonical transcripts, windows, metrics, assignments, and exports are
  linked by hashes.
- Generation uses `shell=False`, argument lists, and separate processes.
- API keys must not be stored, logged, exported, or rendered.
- Generated outputs are not automatically declared comparable, windowed, or
  assigned.

## 6b. Phase 3E status of the Section 7 findings

All four P0 and four P1 findings below were addressed. Verified by inspection and by
`tests/test_phase3e_reliability.py` (39 tests):

| Finding | Status | Where |
|---|---|---|
| P0 completion inferred from `transcript.json` | CLOSED | `generation/worker.py`, `generation/terminal.py`; `observe()` requires a TerminalRecord. A transcript alone yields REQUIRES_RECOVERY. |
| P0 config integrity not rechecked at launch | CLOSED | `generation/preflight.py` (11 checks) plus the worker re-hashing the config in its own process before spawning the CLI. |
| P0 mutable profile paths | CLOSED | `generation/bundle.py`; profiles are copied byte-for-byte and the config carries INLINE `agent_payload`. |
| P0 importer copies before collision resolution | CLOSED | `generation/importer.py`; unique atomic staging, `import_service` owns persistence. |
| P1 CLI defaults drift | CLOSED | `generation/effective_config.py`; every behavioural value resolved WITH its value, pinned by `architecture_code_manifest_hash`. |
| P1 `.env` existence accepted as credentials | CLOSED | `generation/credentials.py`; per-provider, per-variable, non-empty, value never read. |
| P1 concurrency is a UI cap | CLOSED | `generation/queue.py`; durable queue with explicit scheduler ticks. |
| P1 `psutil` optional | CLOSED | declared in `requirements.txt`; the launcher raises rather than degrading to pid-only. |

Remaining risks are listed in section 15.

## 7. Phase 3D audit findings requiring correction

These findings come from direct code inspection after the Phase 3D delivery. Treat
them as higher priority than adding thematic evaluation or visual polish.

### P0 — completion is inferred from the existence of `transcript.json`

`generation/launcher.py::observe()` currently marks a dead process as COMPLETED when
`transcript.json` exists. The architecture may write transcripts incrementally, so a
crashed or capped run can leave this file behind. File existence is not terminal
success evidence.

Required correction:

- introduce a durable terminal record written by a small worker/wrapper around the
  public CLI;
- record exit code, start/end time, config hash, command hash, and terminal reason;
- mark COMPLETED only when the worker records exit code 0 and required final
  artefacts validate;
- distinguish FAILED, CANCELLED, ORPHANED, and incomplete/capped runs;
- never use transcript existence alone as proof of completion.

### P0 — config integrity is not rechecked at launch

The plan records a config hash, but the launcher should verify the bytes immediately
before process creation. A config changed after dry-run must invalidate confirmation.

Required correction:

- hash config at build, confirmation, and launch;
- block launch on any mismatch;
- verify guide and profile snapshot hashes as dependencies;
- write an immutable launch manifest.

### P0 — profile paths remain mutable external dependencies

Configs may contain absolute `agent_payload_path` values. The pointed file can change
after validation, and the config is not portable between machines.

Required correction:

- copy exact profile bytes into an immutable plan bundle inside the project;
- verify raw-byte hashes;
- use bundled paths or exact inline payloads supported by the public contract;
- export the bundle with a rebaseable manifest;
- do not rewrite profile content.

### P0 — importer copies before collision resolution

`generation/importer.py` writes a copied transcript with `write_bytes()` before the
normal import collision policy completes. This is non-atomic and can overwrite the
workspace copy even if the subsequent import is rejected.

Required correction:

- remove the preliminary write or use a unique atomic staging path;
- let `import_service` own collision resolution and final persistence;
- verify job, config, terminal record, and transcript hashes before import.

### P1 — CLI defaults are deliberately allowed to drift

The current effective-config strategy omits some public defaults so future CLI
changes alter later executions. That improves inheritance but weakens reproducibility:
the same plan/config hash can produce a different effective instrument after an
architecture update.

Required correction:

- freeze every behaviourally relevant public parameter at plan confirmation, or
  record a complete resolved effective configuration plus architecture code hash;
- explicitly record moderator and participant model resolution, temperature, mode,
  memory settings, and token caps where applicable;
- this does not mean imposing a fixed response word length.

### P1 — credential detection accepts any `.env` file

Dry-run currently treats repository `.env` existence as credential availability.
An unrelated or empty `.env` can pass.

Required correction:

- determine required providers from resolved models;
- inspect only whether the corresponding key names have non-empty values in the
  environment or parsed `.env`;
- never store or display secret values;
- report missing credential by provider.

### P1 — concurrency is a UI cap, not a durable queue

The interface launches only a selected subset, but no persisted scheduler starts the
next session when a slot opens. A full study therefore requires manual batches and
the declared concurrency limit is not an end-to-end scheduling guarantee.

Required correction:

- persisted queue with PENDING jobs;
- scheduler tick derives active slots from confirmed processes;
- starts at most `concurrency_limit` jobs;
- never automatically retries terminal jobs;
- survives UI restart.

### P1 — process identity depends on optional `psutil`

Without `psutil`, jobs fail safe but may appear orphaned. Either make `psutil` an
explicit application dependency or implement a tested platform-specific process
identity mechanism. Do not weaken identity to PID-only.

## 8. Phase 3D strengths to preserve

- No direct provider or orchestrator imports in the application generation path.
- Commands use argument arrays and `shell=False`.
- Session IDs are path-safe and collision-checked.
- Dry-run does not call external services.
- Launch requires explicit plan confirmation.
- Cancellation requires explicit session confirmation and keeps partial artefacts.
- Monitoring avoids rendering prompts and redacts likely secrets.
- Generated outputs are not automatically comparable or windowed.
- Assignment from a generation plan remains a proposal until researcher confirmation.
- Twin2K is detected locally and is not downloaded implicitly.

## 9. Recommended next phase: 3E

Phase 3E should be a generation-reliability closure, not thematic evaluation yet.
Recommended order:

1. durable worker terminal record and correct completion semantics;
2. launch-time config/dependency hash verification;
3. immutable portable generation bundle for profiles, guide, config, and manifest;
4. atomic output import after terminal validation;
5. persisted concurrency queue;
6. provider-specific credential preflight;
7. token ledger consolidation and optional user-supplied versioned pricing table;
8. one explicitly authorised real smoke run with a single session and conservative
   limits.

Do not make live pricing or thematic evaluation the first task. A wrong completion
state or changed config can corrupt the corpus; a missing currency figure cannot.

## 10. Cost policy

- Token usage from `api_calls.jsonl` is observed usage.
- Currency cost is only actual when computed from observed usage and a versioned rate
  table that identifies provider, model, effective date, currency, and source.
- Pre-run cost is always an estimate.
- If no defensible token expectation or rate exists, display unavailable rather than
  inventing a number.
- Never fetch or silently update pricing during a run.
- A user-supplied or administrator-maintained rate table is acceptable if versioned
  and included in provenance.

## 11. Later roadmap

After Phase 3E:

1. real one-session smoke test, only with explicit user approval;
2. small multi-session queue test;
3. packaging and portability test on a second path/machine;
4. Level 1 evaluation for new corpora, requiring a study-specific codebook,
   evaluator configuration, locked windows, cache identity, quote verification, and
   human referent;
5. Agent Fidelity only for metrics whose sampling and producer problems are resolved;
6. deployment/authentication only after local single-user correctness.

## 12. Audit procedure for the next model

For each delivery:

1. read the delivery report;
2. inspect all new domain contracts and service entry points;
3. trace one datum from user input to persisted artefact to result to export;
4. trace one failure and one stale-input scenario;
5. verify the UI does not bypass service gates;
6. inspect tests for changed intent, not just test counts;
7. verify frozen hashes and golden results remain unchanged;
8. identify claims in the report that are not enforced by code;
9. prefer a small blocking fix over a broad speculative framework;
10. update this handoff document with verified changes and remaining risks.

## 13. Files to inspect first

- `platform_core/generation/contracts.py`
- `platform_core/generation/config_builder.py`
- `platform_core/generation/planner.py`
- `platform_core/generation/launcher.py`
- `platform_core/generation/monitor.py`
- `platform_core/generation/importer.py`
- `platform_core/services/structural_service.py`
- `platform_core/services/window_service.py`
- `platform_core/services/design_service.py`
- `app/views/generate.py`
- `docs/decisions/ADR-002-subprocess-generation-boundary.md`
- `docs/PHASE1_DATA_CONTRACTS.md`
- `docs/PHASE1_METRIC_CAPABILITY_MATRIX.md`

## 14. Current stop/go decision

> **Superseded by section 17.** Kept as a dated position, not as current guidance.
> Its "do not yet run a multi-session study" reads as a deferral of something planned.
> Nothing of the sort is planned — see the scope correction in section 17.

**Go:** the generation reliability gate is met. See
`docs/PHASE3E_REAL_RUN_CHECKLIST.md`.  
**Do not yet:** run a multi-session study, or begin new-corpus thematic evaluation.  
**Gate for a real run:** MET in code — durable terminal evidence, launch-time hash
verification, atomic import — but the real path has never executed. One authorised
single-session smoke run is the next step, with the checklist above.

## 15. Risks open after Phase 3E

1. **The real launch path has never run.** Every test uses a fake worker. The first
   real run is itself the test of `worker.py`.
2. **Completion quality is parsed from CLI stdout.** `GUIDE_COMPLETED` and
   `MAX_TURNS_REACHED` come from matching two printed strings. If the CLI's wording
   changes, quality degrades to PARTIAL_OUTPUT — safe, but it will look like a fault.
3. **The scheduler needs a caller.** `queue.tick()` is explicit; nothing calls it on
   a timer, so a finished session frees a slot only when someone opens the page.
4. **Inline payloads make configs large.** Four personas inline is fine; forty would
   produce a heavy config, and the bundled-path fallback is less exercised.
5. **Outputs still land in `output/session_logs/` in the repository**, because the
   orchestrator decides that. The platform copies into the project but does not own
   the original.
6. **The architecture pin is coarse.** Any edit to any of the eight pinned files
   invalidates every plan, including a comment change.

## 16. First real smoke run — 2026-08-05

The authorised real path has now executed. Two attempts produced:

| Attempt | Outcome | Billed calls | Input tokens | Output tokens | Calculated cost |
|---|---:|---:|---:|---:|---:|
| `smoke_smoke_fg1_r01` | failed | 5 | 4,247 | 1,736 | USD 0.0308 |
| `smoke2_smoke_fg1_r01` | completed | 55 | 163,273 | 13,806 | USD 0.4723 |
| Total | — | 60 | 167,520 | 15,542 | USD 0.5032 |

Direct inspection of both `api_calls.jsonl` files confirmed the totals. The
successful attempt contained:

- moderator / Claude Sonnet 4.6: 11 calls, 85,620 input and 6,880 output tokens;
- participants / Claude Haiku 4.5: 44 calls, 77,653 input and 6,926 output tokens;
- zero cache-creation and cache-read tokens.

At standard first-party API rates of USD 3/15 per MTok for Sonnet 4.6 and USD 1/5
per MTok for Haiku 4.5, the arithmetic is internally consistent. This is calculated
API cost, not invoice reconciliation. Discounts, tax, marketplace billing and
data-residency multipliers may change an invoice.

The failed attempt left a parseable 1,012-byte `transcript.json`, but the durable
record correctly classified it as exit code 1, `NONZERO_EXIT`, `PARTIAL_OUTPUT`,
unusable and not importable. This directly validates the Phase 3E terminal gate.

The successful final state contains two discussion-guide sections and both carry
`completed: true`; the run ended below the safety cap. Terminal quality is still
derived primarily from a stdout marker. The structured final state should become the
authority and stdout should become corroboration only.

Four defects were found during the exercise and reportedly received regression
tests:

1. queued jobs initially omitted their effective-config hash;
2. profile validation accepted a shape the architecture rejected;
3. cost attribution read `action` rather than billed rows' `model` and `role`;
4. cache-token categories were absent.

### Updated priorities

1. Determine guide completion from `discussion_guide[*].completed` in the final
   state; use stdout only as secondary evidence.
2. Add a durable queue-supervisor process. Streamlit reruns are not a reliable
   background scheduler for `queue.tick()`.
3. Replace manually duplicated profile-shape checks with a public consumer-side
   config validation contract when possible.
4. Distinguish 5-minute cache writes, 1-hour cache writes and cache reads. If the
   operation is not identifiable, monetary cost remains undefined.
5. Reconcile ledger totals manually with the Anthropic Console by timestamp and
   model, recording only totals and discrepancy.
6. Define an explicit retention/archive policy for repository session logs; never
   delete them automatically.

### Updated stop/go decision

> **Superseded by section 17.** The hardening phase is done. The 30-session line is
> withdrawn entirely: those sessions belong to the frozen benchmark and already exist.
> The `USD 14.17` figure also assumed a two-section throwaway guide and understates a
> real session several-fold — see section 18.

**Go:** one short hardening phase for structured completion and an external queue
supervisor. Manual single-session runs remain possible with explicit approval.

**Do not yet:** launch the 30-session study. `30 × USD 0.4723 ≈ USD 14.17` is a
scenario under one observed workload, not a budget estimate. One successful session
does not estimate cost or duration variability.


## 17. Phase 3F closure — 2026-08-05

Every §16 updated priority except 5 and 6 is now implemented. Priority 5 is a manual
act that only the account holder can perform; the platform now provides the record it
should be written into. Priority 6 is a retention decision, not code, and the smoke
manifest is the first half of it.

### What changed

| §16 priority | Where it landed |
|---|---|
| 1. Completion from the structured state | `terminal.inspect_final_state()`, mirrored in `worker.py`; stdout became `CompletionEvidence` |
| 2. Durable queue supervisor | `generation/queue_supervisor.py`, a separate process with a per-project lock and a heartbeat |
| 3. One public profile validator | `profiles.architecture_shape_problems()`; `profiles_source` now imports it |
| 4. Cache writes split by TTL | `RateRow.cache_write_5m_rate` / `cache_write_1h_rate` / `cache_read_rate`, plus `CACHE_WRITE_TTL_UNKNOWN` |
| 5. Reconciliation with the console | `pricing_ledger.reconcile()` → `ReconciliationRecord`; the figures are recorded, never adjusted |
| 6. Retention of repository session logs | `generation/smoke_manifest.py` and `docs/SMOKE_RUNS_MANIFEST.json` |

### Completion evidence

`CompletionQuality` now answers *what happened*; `CompletionEvidence` answers *what
that rests on*:

- `STRUCTURED_STATE` — the final state decided it and stdout said nothing;
- `STDOUT_CORROBORATED` — both agree;
- `CONFLICTING_EVIDENCE` — they disagree, and the run is not usable;
- `STDOUT_ONLY_LEGACY` — a record written before this phase, never recomputed;
- `INSUFFICIENT_EVIDENCE` — no usable final state.

Applied to the two real runs with no stdout available at all:

| Run | Sections | Quality | Evidence | Coherent |
|---|---|---|---|---|
| `smoke_smoke_fg1_r01` | 0/2 | `PARTIAL_OUTPUT` | `STRUCTURED_STATE` | yes |
| `smoke2_smoke_fg1_r01` | 2/2 | `GUIDE_COMPLETED` | `STRUCTURED_STATE` | yes |

The successful run is now recognised as complete **without any stdout marker**, which
is exactly what §16 asked for.

### Transcript coherence

`transcript.json` and the final state's `transcript` are compared on turn, speaker id,
speaker name, content and order — not bytes, so re-serialisation and added fields are
not treated as disagreement. A mismatch fails the job. Which artefact is right is not
something the platform can decide, so neither is used.

### The supervisor

`py -m platform_core.generation.queue_supervisor --project <name> --interval <s>`.
Six states: `NOT_STARTED`, `RUNNING`, `PAUSED`, `STOPPED`, `CRASHED`, `UNRESPONSIVE`.
A lock file taken with `O_CREAT | O_EXCL` — not a status check — is what prevents two
schedulers launching into the same free slot; a lock held by a dead process is taken
over and the takeover is recorded. It stops itself after 12 hours. It never retries,
restarts or resurrects a terminal job, and stopping it does not kill running sessions.

### Cost

- Cache writes are billed by time-to-live and the ledger does not record which was
  requested. Where the two rates differ, the result is `CACHE_WRITE_TTL_UNKNOWN` with
  a **bound**, and `total_cost` stays Undefined. A bound is not a cost.
- `PricingContext` records whose rates these are and when they were true. The platform
  fetches nothing; every rate was typed in by a researcher.
- `ScenarioProjection` carries `SCENARIO_NOT_BUDGET` in the dataclass and in its
  serialised form. A projection from one session declares `single_observation` and no
  dispersion. An Undefined session cost is excluded, never counted as zero.

The §16 figure of `30 × USD 0.4723 ≈ USD 14.17` is exactly what this type models: one
observation, scaled, labelled a scenario.

### Durations

Four stages per job — `queue_wait_seconds`, `launch_duration_seconds`,
`run_duration_seconds`, `total_elapsed_seconds` — each `None` where its endpoints are
not both known. `monitor.plan_duration_summary()` marks any stage with one
observation `SINGLE_OBSERVATION`. A job that never ran contributes nothing rather
than a zero.

### Risks still open

Items 4, 5 and 6 of §15 are unchanged. Items 1, 2 and 3 are closed. New:

7. **The supervisor has never run as a real process.** Its loop is fully exercised
   in-process; `start()` spawning a detached process on Windows is not.
8. **Cache TTL cannot be recovered retrospectively.** The two smoke runs recorded no
   cache tokens, so this has never been exercised against real cache usage.
9. **Reconciliation depends on a figure only the account holder can read.** The
   platform cannot verify what it is given.

### Scope correction — the platform never runs a 30-session study

Sections 14 and 16 both end on "do not yet launch the 30-session study". That framing
was wrong and is withdrawn.

The 30 synthetic sessions (5 focus groups × 2 conditions × 3 replicates) are the
**frozen benchmark's own design**. They were generated before this platform existed,
they are thesis data, and they are frozen. Nothing here needs to reproduce them, and
regenerating them would be actively harmful: it would produce artefacts that resemble
the benchmark without being it.

What this platform is for is stated in section 2 — letting *another* researcher
generate and evaluate *their own* corpus against the frozen benchmark. The number of
sessions is therefore that researcher's decision, in their own project, with their own
budget. It is not a milestone of this project.

The deliverable is **working infrastructure**, and the only real runs this project
needs are the ones that prove the path works.

### Stop/go

**Done:** a 3-session pilot under the supervisor, concurrency 1 — see section 18.

**Not planned, by decision rather than by caution:** any bulk generation run. The
frozen benchmark is complete. Bulk generation is a capability the platform offers, not
a task it owes.

## 18. Phase 3F pilot — 3 sessions under the supervisor, 2026-08-05

Authorised by the researcher. Three sessions, concurrency 1, a three-section guide on
commuting — a topic chosen because it has nothing to do with the thesis, so the
artefacts cannot be mistaken for study data. Recorded in
`docs/EXPLORATORY_RUNS_MANIFEST.json` as `EXPLORATORY_NOT_THESIS_DATA`.

### The supervisor did the thing it was built for

122 ticks. It launched session 1, waited, launched session 2 when the slot freed,
then session 3, then **stopped itself** with `every job in the queue reached a
terminal state`. Nobody opened the interface during the run. That is the defect from
section 15 item 3 closed by demonstration rather than by argument.

### Results

| Session | Completion | Evidence | Sections | Coherent | Run (s) |
|---|---|---|---|---:|---:|
| `..._r01` | GUIDE_COMPLETED | STDOUT_CORROBORATED | 3/3 | yes | 595 |
| `..._r02` | GUIDE_COMPLETED | STDOUT_CORROBORATED | 3/3 | yes | 490 |
| `..._r03` | GUIDE_COMPLETED | STDOUT_CORROBORATED | 3/3 | yes | 720 |

All three imported cleanly. Run duration mean 602 s over three observations —
min 490, max 720, so the spread is real and a single observation would have hidden it.
Wall clock for the plan: 2,004 s.

### Two defects the pilot found

1. **The supervisor died on its first real launch.** `supervisor_command()` passed
   `project.name` ("Pilot 3F commuting") where `load_project()` needs the
   `project_id`; the path-safety guard refused the display name and the process
   exited before its first tick. Nothing was launched and nothing was billed. Fixed,
   with the loadability of the identifier now asserted in a test. **Every test had
   passed** — because every test drove the loop in-process and none exercised the
   spawn path. This is the general shape of section 15 item 1.
2. **A cosmetic slice** in the heartbeat display cut an ISO timestamp's zone offset.

### Cache, and what it cost

Unlike the smoke runs, these sessions used prompt caching: 86,442 cache-write and
117,119 cache-read tokens. The ledger records the totals and **no time-to-live at
all**, so the Phase 3F design engaged exactly as intended:

- every session came back `CACHE_WRITE_TTL_UNKNOWN`;
- `total_cost` stayed Undefined and a **bound** was reported instead;
- `project_scenario()` then refused to project anything, because no session carries a
  determined cost and an Undefined cost is not counted as zero.

Observed bound for the three sessions: **USD 3.5171 to 3.5819** — a spread of 1.8%,
which is the entire consequence of not knowing the TTL. Per session, USD 1.17–1.19.

The refusal is correct and it is also inconvenient: any run that uses caching will
report a range rather than a figure until the architecture records which TTL it asked
for. The range is shown in the interface, so nothing is hidden — but a researcher who
wants a single number needs that field in `api_calls.jsonl`.

**Cost is dominated by the moderator**, not the participants: 836,326 of 921,217
input tokens across the three sessions were Sonnet moderator calls. Cheaper
participant models barely move the total.

### Risks closed and remaining

Closed: section 15 items 1, 2, 3, and new items 7 and 8 from section 17 — the spawn
path and the cache-TTL path have both now executed for real.

Remaining: item 9 (reconciliation still needs a figure only the account holder can
read), section 15 items 4, 5 and 6, and one new observation — **cost scales with the
square of the turn count**, because each turn re-sends the transcript. The moderator's
input grew from 2.3k to 10.6k tokens over eleven turns in the smoke run. Any estimate
made at one guide length does not transfer to another.

## 19. Adversarial review — five independent readers, 2026-08-05

Five review agents were run read-only over the Phase 3F modules, each asked to refute
rather than approve, and each given the real run data to check against. They returned
47 findings. **All 772 tests passed with every one of these defects present**, which is
the honest measure of what a self-written suite is worth.

### Fixed, with a regression test each (tests 38-48)

| # | Defect | Why it mattered |
|---|---|---|
| 1 | The manual "Scheduler tick" button was never disabled | One click while a supervisor ran gave two schedulers reading the same free slot. No race needed. |
| 2 | `O_CREAT\|O_EXCL` creates a zero-byte file before the JSON lands | Reading the lock in that window looked like "no owner", so a second supervisor stole it from a live one. |
| 3 | Concurrent takeover of a stale lock had no exclusion | Both claimants wrote and both continued. The winner is now decided by reading the lock back. |
| 4 | A holder with no recorded start time was assumed alive | A recycled pid running anything at all made a project permanently unschedulable. |
| 5 | The bound omitted rows carrying no rate | A one-character typo in a model name displayed `between 0.09 and 0.11 USD` for a session costing 1.16. |
| 6 | `cache_creation_5m/1h_input_tokens` read as a TTL flag, values discarded | 98.6% understatement, reported as determined. |
| 7 | A call using both TTLs billed entirely at one rate | 33% understatement, reported as determined. |
| 8 | The worker could die before writing its record | `null` in `transcript.json` left a paid session with no evidence it had run. |
| 9 | `max_turns` as a string raised in one copy and capped in the other | The two implementations disagreed at the COMPLETED/FAILED boundary. |
| 10 | An unreadable terminal record raised out of `observe()` | One corrupt file blanked every job in the project. |
| 11 | `"transcript_state_match": "no"` passed `is False` | The gate that stops an incoherent run being imported never fired. |
| 12 | `STDOUT_ONLY_LEGACY` still reached COMPLETED | The verdict this phase exists to distrust was being accepted as final. |
| 13 | Supervisor controls lived inside the launch-permission branch | A hash change mid-run removed Pause and Stop while the supervisor kept launching. |
| 14 | The job table rendered an absent ledger as `0 calls / 0 tokens` | Indistinguishable from a run that made none. The crashed smoke run made six. |
| 15 | Every supervisor death was recorded as a clean `STOPPED` | A disk-full crash at tick 40 of 120 read as "the queue finished". |

### The validator was refusing real work

`architecture_shape_problems` demanded `age` and `gender` because
`core.participant_agent.load_agent_from_json`'s **docstring** lists them as required.
Its **code** does `if age is not None` and builds the identity line without them.
Following the docstring made the platform refuse **44 of the 123 agent payloads in
this repository**, including an entire study arm — panels the architecture runs
perfectly well.

Now: `name` only, plus the shapes that genuinely crash. Two of those were missing and
are now checked — `persona.demographics.location` (`.get()` in three places, one of
them inside the loader that runs *before* the first billed call) and top-level
`psychometric_scores` (`.items()`, then `.get("value")`, then `float()`). Test 48
asserts that every real payload in `agents/` is accepted.

**The lesson, and it generalises: validate against what the consumer does, not against
what it says it does.** A validator that blocks work the architecture accepts is as
broken as one that admits work it rejects.

### Reported, not fixed — the researcher scoped this pass to money and figures

Ranked. None is known to be biting today.

1. `queue.tick()` writes the whole queue record back, so a pause set during a tick is
   silently reverted and the next tick launches.
2. `n_completed` counts any job with a `completed_utc`, which includes CANCELLED,
   ORPHANED and FAILED_TO_LAUNCH; `wall_clock_seconds` is reported for such plans with
   no note.
3. The coherence gate returns before the config-hash check, so a job that ran the
   **wrong configuration** is reported with a coherence message instead.
4. Nothing checks the state's own `discussion_guide` against the *planned* guide. A
   state carrying one section, all complete, yields GUIDE_COMPLETED for a three-section
   plan. This is the one confirmed route by which an incomplete session could be
   recorded as complete. The plan hash is already on the job; the check is cheap.
5. `launch_duration_seconds` spans two adjacent assignments and measures nothing — the
   pilot recorded 1e-5 s — yet renders as a distribution beside three real metrics.
6. A naive (offset-less) timestamp raises `TypeError` out of `observe()` and blanks the
   whole Generate view; the two `_parse_utc` copies also diverge on non-string input.
7. Cancelled and orphaned jobs never get durations at all, because `_apply_durations`
   is only called from `_apply_terminal_record`.
8. `CREATE_NEW_PROCESS_GROUP` does not detach on Windows — closing the console kills
   the supervisor and the paid sessions with it. `DETACHED_PROCESS` is needed.
9. An UNRESPONSIVE supervisor cannot be stopped or replaced from the interface; the
   caption advises a recovery the code cannot perform.
10. `ui/backend/api.py`'s `POST /start-session` accepts agent payloads straight from
    the HTTP body and never reaches the validator — a live paid entry point outside
    `platform_core`.
11. `ScenarioProjection` excludes bounded sessions, and the sessions that become
    bounded are the cache-heavy ones — so the exclusion is biased toward cheap
    sessions rather than missing at random.
12. `table_sha256` is not recomputed after an in-memory rate edit, so a report can name
    a table that did not price it.
13. Row currency is never checked against table currency; a mixed-currency table sums
    without a problem note.
14. `smoke_manifest` classifies without `max_turns` or stdout, so a capped run would be
    `PARTIAL_OUTPUT` in the manifest and `MAX_TURNS_REACHED` in its terminal record.
15. `start()` has no test at all — every supervisor test injects `spawn`. That is
    exactly why the first real launch died.

## 20. Second pass — auditing the fixes, 2026-08-05

Three agents were run read-only over the section 19 fixes, asked one question: is each
fix CORRECT, did it introduce a NEW defect, and did it break a case that used to work?
A wrong fix is worse than the bug, because everyone then believes it is handled.

They confirmed 12 of the 15 fixes correct — the pricing reviewer rebuilt reverted
variants of the module and verified that **every one of the six new cost tests fails
when its own fix is removed**, and that the real pilot bound (`1.1563 to 1.1776 USD`)
still holds exactly. Then they found 27 more problems, of which the following were
fixed, with tests 60-70.

### My own fix was insufficient, twice

1. **The lock read-back did not serialise two takeovers.** `_save` is atomic but
   last-writer-wins, so A saving then re-reading, then B saving then re-reading, leaves
   BOTH believing they won — and both writing `supervisor_state.json`, so the interface
   shows one pid while two schedulers run. The correct shape is to remove the stale
   lock and race `O_CREAT | O_EXCL` again, letting the operating system decide. That is
   what it now does.
2. **The manual-tick gate was advice, not enforcement.** `disabled=supervisor_alive`
   reads a state file that can be an interval stale, and `queue.tick()` called directly
   bypasses it entirely. `tick()` now checks the lock itself and refuses to run beside
   a live supervisor. The button is still disabled — but the lock is what decides.

### The reordered config gate is a dead branch, and the test hid that

`worker.py` echoes the `config_sha256` the launcher passed it, so
`record.config_sha256 != job.config_sha256` is `H != H` for every record this codebase
writes. Reordering it changed nothing real, and test 50 hand-builds the only record
shape that can enter it — certifying confidence in a check that cannot fire.

What DOES detect a changed config is the worker re-verifying the hash in its own
process before spawning. That arrives as a `failure_reason` on a `PROCESS_LOST` record,
and it was being reported to the researcher as **"the session ended without writing a
transcript"** — true, and useless. The worker's own reason now outranks anything
inferred from the artefacts afterwards. The dead branch is kept, with a comment saying
what it is and is not.

### Also fixed

| Defect | Consequence |
|---|---|
| `force_release` had no liveness re-check and cleared the stop request | A supervisor that was merely slow could have its lock pulled by a click on a stale screen, and Abandon deleted the one instruction the abandoned process would still obey. It now refuses if the heartbeat is current, and SETS the stop instead of clearing it. |
| `_holder_is_live_supervisor` never used its `project` argument | It trusted the lock file's self-report, so a copied project directory could never take a supervisor. It also matched `--project alpha` against `alpha_beta`; the match is now whole-argument. |
| ORPHANED decayed to UNKNOWN on the next observation | UNKNOWN is in neither the queue's occupying nor its terminal set, so the queue could never reach COMPLETED and **the supervisor ran until its twelve-hour lifetime**. |
| A naive timestamp was read AS UTC | It manufactured a plausible number: from a UTC−5 machine, a queue wait 18,000 s too long, entering the mean unmarked. A naive stamp is now UNOBSERVED — `None` is a first-class outcome here and is reported as `n_missing`. |
| `n_terminal` counted `completed_utc` | A REQUIRES_RECOVERY job carries one and is explicitly not terminal. It now uses `JobRecord.terminal`. |
| The wall-clock note enumerated causes that excluded FAILED | The commonest outcome of a bad run was missing from a sentence a reader may transcribe. It now lists the statuses the plan actually had. |
| A corrupt token VALUE raised out of `consolidate` | `read_calls` tolerates a corrupt line; a corrupt value killed the whole cost report and the page. Values are now coerced defensively and the shortfall is reported. |
| A single-currency mismatch produced a real total with the wrong label | 3.00 GBP displayed as `3.0000 USD`. The figures come from the rows, so the label now does too. |
| `context_from_table` still used the stored hash | The provenance record named one table while the report named another — exactly what test 55 exists to prevent, one function away. |
| `report.problems` was rendered nowhere | Every warning the cost layer computes — mislabelled currency, corrupt value, failed call with no tokens — reached the reader as a clean figure. They are now shown above the job table. |
| `n_untokened_entries` was counted and surfaced nowhere | Same. It now becomes a problem line explaining that a parse failure after a billed call looks exactly like a decision summary. |

### Still open, and why

- **`ui/backend/api.py`'s `POST /start-session`** accepts agent payloads straight from
  the HTTP body and never reaches the validator. It is a separate application with its
  own entry point; it was not modified. The comment in `profiles.py` no longer claims
  repo-wide coverage.
- **A genuinely corrupt lock requires manual removal.** Refusing is the safe direction
  for money, but the instruction currently only reaches `supervisor.log`, which the
  interface does not show.
- **`compare_transcripts` treats `turn: 3` and `turn: "3"` as equal.** Intentional —
  serialisation is not identity — but undocumented in the contract.
- **`max(aggregate, five + hour)`** reconciles a self-contradictory ledger by taking the
  larger reading. It now records a problem when the two disagree, but no producer of
  the per-TTL fields exists in this repository, so the branch is exercised only by
  tests.
- **Tests write into the real `output/session_logs/`.** `build_job` hardcodes
  `REPO_ROOT`; redirecting it is a design change, not a fix. Each test now uses a
  distinct study id so they cannot collide, but a test that dies mid-run still leaves a
  directory that makes `build_job` refuse that session id afterwards.

### What this pass says about the method

Every defect in sections 19 and 20 was present while the suite was green. The tests
that found nothing were mine; the reviewers that found 74 problems were reading the
same code with instructions to refute it. Two of the four most serious findings were
in the fixes themselves, not the original code.
