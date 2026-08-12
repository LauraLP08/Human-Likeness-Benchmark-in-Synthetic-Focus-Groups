# ADR-009 - `project.json` is data, never path authority

* **Status:** Accepted (2026-08-04)
* **Decides:** where a project's root comes from when a project is loaded

## Context

`load_project()` read `root` out of `project.json` and used it to build every
subsequent path - uploads, derived artefacts, trash. The file is inside the user's data
directory and is trivially editable. Editing one string redirected every write the
application would later make, including deletion.

The stored file is an artefact the application wrote. Trusting it to say where it lives
is circular.

## Decision

The authoritative root is always derived:

    <resolved_data_dir>/projects/<validated_project_id>

Loading performs, in order:

1. validate the requested `project_id` as a safe component;
2. derive the expected root with `safe_path`;
3. read `project.json` from that derived path;
4. require the file's internal `project_id` to equal the requested one;
5. if the file records a `root`, require it to equal the derived path exactly;
6. construct the `Project` with the **derived** path, never the stored string.

Refused: an external root, a different internal `project_id`, a relative root, and a
root pointing at another project. `list_projects()` skips a project that fails these
checks rather than loading it degraded.

## Consequences

**Positive.** A tampered `project.json` cannot redirect a write; the failure is a
refusal to load, not a misdirected file. The check is cheap and runs on every load.

**Negative.** A project directory cannot be moved and reopened by editing its
`root` - it must be moved and opened under its new location's id. That is the correct
trade: relocation is a deliberate act, not a text edit.

**Note.** The same reasoning applies to any future manifest that records its own
location. A stored path is a hint for humans; the derivation is the authority.
