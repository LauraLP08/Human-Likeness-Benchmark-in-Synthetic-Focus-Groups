# ADR-010 - Derived artefacts are written atomically, and never overwritten by default

* **Status:** Accepted (2026-08-04)
* **Decides:** how project files, derived profiles and compiled guides reach disk

## Context

Writes went straight to the destination with `write_text`. A process killed mid-write -
or a serialisation error halfway through - would leave a truncated JSON file that the
next run would read as the artefact of record. Worse, a second `derive_profile` call
silently replaced the first, destroying the file a previous run's provenance pointed at.

## Decision

**Atomic write.** Temporary file in the same directory (so `os.replace` is atomic on
the same filesystem) -> write -> flush -> `fsync` -> close -> optional verification ->
atomic replace -> remove the temporary on any error. The verification hook re-reads the
temporary and parses it, so a file that is not valid JSON never becomes the destination.

**Explicit overwrite policy.** `on_exists` is a parameter with three values and no
implicit default beyond refusal:

| value | meaning |
|---|---|
| `FAIL` | default for derived artefacts - raises `ArtifactExistsError` |
| `REPLACE` | caller-chosen, used for `project.json`, which is a mutable record |
| `SKIP` | leave the existing artefact untouched |

A derived profile or compiled guide therefore cannot be replaced by accident. The
caller must say so, and the message names the alternative (write to a new name).

## Consequences

**Positive.** A killed process leaves either the previous artefact or nothing - never a
half-file. A failed verification leaves the previous artefact byte-identical. No
temporary survives a failure; a helper enumerates any that did, and the tests assert
the directory is clean after each failure path.

**Negative.** Every write costs a temporary file and an `fsync`. On a project with
hundreds of profiles this is measurable but not material at this scale.

**Not covered.** Cross-filesystem atomicity. `os.replace` is atomic only within one
filesystem, which is why the temporary is created in the destination's own directory
rather than in the system temp area.
