# ADR-001 — Streamlit for the MVP, with all logic in `platform_core/`

* **Status:** Accepted (2026-08-04)
* **Decides:** the interface technology and the boundary between interface and logic

## Context

The application must be reusable by other researchers, run on a single machine, and
consume an architecture written in Python. The repository declares no web framework
in `requirements.txt` (only `anthropic`, `pydantic`, `google-genai`, `openpyxl`,
`sentence-transformers`). A prior attempt exists — `ui/backend/api.py` (FastAPI,
1,092 lines, 2026-05-27) with `ui/frontend` (React 19 / Vite 8 / Tailwind 4 /
TypeScript 6). No test imports it, it binds to a private orchestrator method, and it
searches five candidate directories for session logs, indicating drift from a layout
that has since moved.

The audience that determines this choice is a researcher who must *install and run*
the tool, not maintain it.

## Decision

Streamlit for the MVP. All non-interface logic lives in `platform_core/`, which is
importable and testable without Streamlit.

The boundary is enforced, not merely intended:

1. `pages/*.py` may call `platform_core` and Streamlit. They may not compute a
   metric, build a path, parse a transcript, or call a subprocess.
2. `platform_core/**` may not import `streamlit`. A test asserts this by scanning
   imports.
3. Every user-visible operation is a function in `platform_core` with a typed
   signature and its own unit test; the page is the caller.

## Consequences

**Positive.** One dependency and one command (`streamlit run app.py`); no Node
toolchain; no build step; no second process. `st.data_editor` covers the matching
table; live progress is a polling read over artefacts the pipeline already writes
(ADR-002), so Streamlit's rerun model is an advantage rather than an obstacle — the
UI holds no state that cannot be rebuilt from disk. The service layer is testable
with the repository's existing `pytest`.

**Negative.** Coarser layout control than React. Weak multi-user concurrency — this
is a single-researcher desktop tool. No HTTP API for headless reuse.

**Reversible.** Because `platform_core` is Streamlit-free, a FastAPI surface can be
added later over the same functions without touching analysis code. That is the
migration path if hosting for several simultaneous users becomes a requirement.

## Alternatives considered

**FastAPI + React, extending `ui/`.** Rejected for the MVP. It offers real streaming
and an HTTP API, but the streaming advantage is largely moot — the artefacts are
already on disk and incrementally written — while the cost is two processes, a
JavaScript toolchain a lone researcher will not track, and roughly double the code
for the same features. It also re-invites coupling to orchestrator internals, which
the brief forbids.

**CLI plus static HTML reports.** Rejected: the brief requires an interface, and the
matching assistant and review queue are inherently interactive.

## Notes

`ui/` is left untouched as prior art. Its SSE event shapes (`_entry_to_event`,
`_build_state_update`) are a useful reference for what a live session view must show,
and are cited as such rather than imported.
