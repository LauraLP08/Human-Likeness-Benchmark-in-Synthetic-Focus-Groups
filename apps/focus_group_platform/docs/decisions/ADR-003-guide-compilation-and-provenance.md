# ADR-003 — YAML is the editable source; compiled JSON is what executes

* **Status:** Accepted (2026-08-04)
* **Decides:** the guide contract, and how the application avoids repeating a drift
  the project has already suffered once

## Context

The audit established that the YAML guide is **not** what runs. The header of
`configs/guides/macho_meals_plant_based_masculinity_uk.yaml` (lines 4–13) states it:

> AUTHORITY (2026-07-28): this file is NOT the source of truth for synthetic runs.
> The canonical guide is the inlined `discussion_guide` array in
> `configs/experiment/macho_meals_fg1_run01.json`, which is what actually executes —
> nothing in `core/` or `scripts/run_full_session.py` reads this YAML at runtime.

The code agrees: `core/orchestrator.py::_build_state_from_config` reads
`session_config["discussion_guide"]`. Two converters exist —
`scripts/run_batch.py::_load_guide_sections` and
`scripts/twin2k500_sample.py::build_session_config`.

The same header records that the two representations **drifted apart** and had to be
resynchronised on 2026-07-28: section 0's scripted question was 241 characters
shorter in the YAML, and section 1 carried the wrong phase. A guide can therefore
look right and execute wrong. That is the failure this ADR exists to prevent.

## Decision

The application treats the researcher's YAML as the **editable project source** and
the compiled JSON as the **executed artefact**, with a correspondence check that
blocks execution.

Eight obligations, all of them enforced before a run can start:

1. **Validate** the YAML: required fields, section ordering, phase names against
   `core.session_state.SectionPhase`, and the Krueger-format phase mapping the
   project already documents (`opening → intro`, `introductory → context`,
   `transition → context`, `key → main_topic`, `stimulus task → stimulus`,
   `ending/closing → closing`). An unmapped phase is an error, never a silent
   default.
2. **Compile deterministically** to the `discussion_guide` array. Deterministic
   means: fixed key order, no timestamps, no locale-dependent formatting, no
   dictionary-iteration order leaking into the output. Compiling the same bytes twice
   in two processes must give the same hash.
3. **Preview** the compiled result — sections, phases, scripted questions,
   transitions, probes, moderation rules — as it will execute, not as authored.
4. **Store the original YAML** unchanged in `uploads/`.
5. **Store the compiled JSON** in `derived/`.
6. **Hash both** (sha256), recording `source_yaml_sha256` and
   `compiled_json_sha256`.
7. **Record the compiler version** (`guide_compiler_version`, semver) on the artefact
   and in every provenance block.
8. **Block execution** when the two do not correspond. Correspondence is verified by
   recompiling the stored YAML and comparing to the stored compiled hash. Failure
   sets `correspondence_ok = false` and disables the run control with the reason
   shown. A warning is not sufficient — a warning is what the project already had.

## The frozen corpus is exempt

This does not change the source of truth for the Macho Meals experiment. For that
corpus the existing `configs/experiment/*.json` remain the executed artefacts and are
read as-is. The application:

* does not recompile them,
* does not compare them against `configs/guides/*.yaml`,
* does not write to `configs/`.

Pointing the application at a frozen config uses its `discussion_guide` array
verbatim. The compile-and-check contract applies to guides the researcher authors in
a project, not to history.

## Panel sampling seeds

Where a future Twin2K integration samples a panel, `panel_sampling_seed` is recorded
as a genuine reproducibility control — `scripts/twin2k500_sample.py --seed` selects
*which agents are drawn*. It must never be presented alongside `replicate_label`, and
the interface must not let the two share a control, a label or a tooltip. One is
reproducible; the other is not, and conflating them is the error the repository
already corrected once when it renamed `generation_seed` to `run_label`.

## Consequences

**Positive.** The artefact that executes is the artefact that is hashed, previewed
and stored. Drift between authored and executed guides becomes impossible rather than
merely discouraged.

**Negative.** An extra explicit step for the researcher, and two artefacts to keep
rather than one. Editing the compiled JSON by hand is not supported — it will fail
correspondence, by design.
