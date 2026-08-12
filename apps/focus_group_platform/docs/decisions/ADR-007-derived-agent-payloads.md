# ADR-007 — Changing a participant model produces a derived payload

* **Status:** Accepted (2026-08-04)
* **Supersedes:** `PHASE1_DATA_CONTRACTS.md` §3, which carried
  `StudyDefinition.participant_model` as a session-config field

## Context

Phase 1 put `participant_model` in the study form and implied it flowed through the
session config, alongside `moderator_model`. That is true for the moderator and false
for participants.

`core/participant_agent.py` line 951 states it plainly — *"model and max_tokens come
from the participant's `agent_payload.simulation_config`"* — and line 964 reads
`participant.agent_payload.get("simulation_config", {})`. The participant model is a
property of the **profile**, not of the session.

So "let the researcher choose a participant model" has exactly two implementations:
mutate the profile, or copy it. Mutating profiles under `agents/` is forbidden, and
mutating an upload would destroy the artefact the researcher supplied.

## Decision

Selecting a participant model creates a **derived profile** inside the project.

1. The loaded profile is kept unchanged — the file in `agents/` or in the project's
   `uploads/` is never written.
2. A derived copy is written to `<project>/derived/profiles/<agent_id>.json`.
3. The selected model is applied there, at `simulation_config.model`.
4. The change is recorded twice: `field_provenance["simulation_config.model"]`
   becomes `transformed`, and a `RunTransformation` entry records the field path, the
   rule, the previous value, the new value and the timestamp.
5. The session config's `agent_payload_path` points at the derived copy.
6. Both hashes are recorded: `source_sha256` of the original and `derived_sha256` of
   the copy.

The same mechanism serves any future run-time override of a profile field. Nothing
else in the payload is touched — a derived profile differs from its source only in the
fields listed in `run_transformations`, and a test asserts exactly that.

## `participant_response_max_tokens` is a ceiling

Clarified because it is easy to misread as a length target, and because misreading it
would push the application toward exactly the hard-coding the brief forbids.

It is a **technical maximum on output length**. It is not a target, not a minimum,
and not an instruction to make responses uniform. The interface label reads:
*"Maximum output tokens per participant turn. A ceiling, not a target — it does not
ask for longer or more uniform answers."*

The distinction is not academic: `api_calls.jsonl` records `response_truncated`, and
a run where responses hit the ceiling is a run whose lengths were shaped by the
ceiling rather than by the model. The application surfaces the truncation rate rather
than letting a ceiling quietly become a length policy.

## Consequences

**Positive.** Originals are provably untouched — the test compares the source hash
before and after. Every executed run points at a payload whose differences from its
source are enumerated. A reviewer can answer "what did this run actually send?" from
the derived file alone.

**Negative.** Storage duplication, one derived payload per profile per project, and a
second artefact to keep consistent. Mitigated by writing derived payloads only when a
transformation is actually requested — if the researcher keeps each profile's own
model, no derived copy is created and the session config points at the original path.

**Consequence for the interface.** The model control belongs in the participants step,
not the study step, because it acts on profiles. It is moved there, with a note
stating that choosing a model writes derived copies inside the project.
