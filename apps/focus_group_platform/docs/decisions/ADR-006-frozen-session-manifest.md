# ADR-006 — Protection is an explicit manifest, not a directory root

* **Status:** Accepted (2026-08-04)
* **Supersedes:** `PHASE1_PRODUCT_SPECIFICATION.md` §7 and
  `PHASE1_ACCEPTANCE_TEST_PLAN.md` §2.4, which treated all of
  `output/session_logs/` as frozen

## Context

Phase 1 listed `output/session_logs/` among the frozen paths. That was an error with
a concrete consequence: **the architecture writes new sessions there**.
`core/orchestrator.py` sets `log_dir` to `output/session_logs/<session_id>`, and
`run_parallel_sessions.py` documents that this is derived purely from `session_id`.
Freezing the root would have made the application unable to generate anything — the
guard would have fired on the very first legitimate run.

The real requirement is narrower: the thesis corpus must not change. That is a set of
specific directories, not a tree.

## Decision

Protection is defined by an explicit manifest, `frozen_sessions.json`, listing:

* the **30 canonical Macho Meals sessions** —
  `macho_meals_fg{1..5}_run0{1..3}` and `macho_meals_fg{1..5}_demoonly_run0{1..3}`,
  flagged `acceptance: true`;
* the **12 non-canonical Macho Meals run directories** (emergent, killed, partial,
  presynthesisfix, failed-auth, `fg4_run04`), flagged `acceptance: false` — they are
  history and are protected, but the acceptance test does not read them;
* the **5 standardized human transcript sets**;
* any other path a future acceptance manifest declares.

Everything else under `output/session_logs/` is unprotected and writable by the
architecture, as it must be.

### Launching a new session

Before any launch the application resolves the exact destination and refuses on any
of three grounds:

1. `session_id` is not project-prefixed (`<project_slug>__…`);
2. a directory already exists at the destination — **any** directory, frozen or not;
3. the destination appears in the frozen manifest.

The application never overwrites and never auto-resumes an existing run directory. A
rerun is a new `session_id`, always.

After a run, the application may copy manifests and derived artefacts into the
project's data directory, and must record the original directory as their provenance,
so a copy can always be traced back to the run that produced it.

### Macho Meals is not a project

The corpus is registered as a **read-only external acceptance corpus**. It is not
created as a project, not copied into user space, and not included in any external
distribution. It is visible in the interface only under
`FOCUS_GROUP_PLATFORM_DEV_REFERENCE=1`, in a panel labelled as a developer reference
rather than a project. User demo mode uses `fixtures/` only.

### The immutability test has three outcomes

| Observation | Verdict |
|---|---|
| A manifest path changed, in content, size, mtime, or existence | **FAIL** |
| A new directory under `output/session_logs/`, project-prefixed, unique, absent from the manifest | **PASS** — an authorised run |
| A new directory that is not project-prefixed, or that collides with a manifest entry | **FAIL** |
| Any change under `core/`, `agents/`, `configs/`, `prompts/`, `data/datasets_transcripts/standardized/`, `analysis/` | **FAIL** |

## Consequences

**Positive.** Generation works. Protection is precise and auditable — the manifest is
a file a reviewer can read, not a rule buried in code. New corpora can be frozen by
adding entries.

**Negative.** The manifest must be maintained: a session that should be protected but
is not listed is unprotected. Mitigation — the manifest is generated from a documented
pattern and its own hash is recorded, so a silent edit is detectable.

**Residual risk.** A directory outside the manifest and outside the project prefix
could still be written by something else in the repository. The application does not
police the whole tree; it polices its own writes and verifies the manifest.
