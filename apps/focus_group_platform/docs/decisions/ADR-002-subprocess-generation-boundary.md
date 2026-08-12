# ADR-002 — Generation runs as separate processes over the public CLI

* **Status:** Accepted (2026-08-04)
* **Decides:** how the application drives the simulation architecture

## Context

The brief forbids modifying the architecture and forbids depending on private methods
such as `_run_full_turn_streaming` — the exact coupling the prior UI took
(`ui/backend/api.py::_run_session_sync`).

Three facts from the audit make a cleaner boundary available:

1. `scripts/run_full_session.py` is a public, documented entry point:
   `--config <json> --max-turns N [--mode orchestrated|emergent]`.
2. `scripts/run_parallel_sessions.py` already launches sessions as separate OS
   processes and carries the safety proof in its docstring: `log_dir` is
   `output/session_logs/<session_id>`, derived purely from `session_id` with no
   timestamp component; there is no module-level file handle, lockfile or shared
   counter anywhere in `core/`; distinct `session_id`s cannot collide.
3. Artefacts are written **incrementally** during a run — `state_turn_N.json` per
   turn, `api_calls.jsonl` per call, plus `transcript.json` and
   `launcher_stdout.log`.

Together these mean live progress does not require in-process coupling.

## Decision

The application launches each run as a separate OS process invoking
`scripts/run_full_session.py`, and observes progress by reading that run's artefacts
read-only.

Rules:

1. `platform_core/generation/` **never imports `core.orchestrator`**. Asserted by a
   source scan in the test suite.
2. No underscore-prefixed attribute of any architecture object is accessed anywhere
   in the application.
3. The application writes the compiled session config into its own workspace and
   passes that path; it never writes into `configs/`.
4. `output/session_logs/<session_id>/` is opened read-only. The application copies
   what it needs into `workspace/<project>/runs/`.
5. `session_id` uniqueness is checked before launch, because uniqueness is what makes
   concurrency safe.

## Progress and restart

Job status is **derived from disk on every read**, never held in session memory:

| Observation | Status |
|---|---|
| record has `completed_at` | terminal, from `exit_code` |
| pid alive and owns the expected command line | `running` |
| pid dead, output directory grew since last observation | `orphaned` |
| pid dead, no growth | `failed` |
| output directory absent | `unknown` |

`orphaned` is a first-class state shown to the user with its partial artefacts
intact. The application never silently relaunches a job: a rerun is an explicit
action with a new `session_id`.

This is what makes UI restart safe. Closing the browser, reloading the page or
restarting Streamlit loses nothing, because there was nothing to lose — the process
is independent and the state is on disk.

## Consequences

**Positive.** Zero coupling to architecture internals; the architecture can evolve
without breaking the application as long as the CLI contract holds. Crashes in the UI
cannot corrupt a run. Concurrency is already proven safe. Cancellation is a signal to
a pid.

**Negative.** Progress granularity is bounded by how often artefacts are flushed —
turn-level, not token-level. Live token counts lag by up to one API call. A stale
pid could in principle be reused by the operating system, so the command line is
checked as well as the pid.

**Rejected alternative.** Importing the orchestrator and driving it in-process, as
the prior UI does. It gives token-level streaming, at the cost of the private-method
dependency the brief prohibits and a failure mode where a UI exception kills a paid
run mid-flight.
