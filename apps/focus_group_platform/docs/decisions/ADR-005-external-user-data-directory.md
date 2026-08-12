# ADR-005 — User data lives outside the repository

* **Status:** Accepted (2026-08-04)
* **Supersedes:** `PHASE1_PRODUCT_SPECIFICATION.md` §2, which placed `workspace/`
  inside `apps/focus_group_platform/`

## Context

The Phase 1 specification put per-project data at
`apps/focus_group_platform/workspace/`. That is convenient and wrong. It puts
research data — potentially containing personal data — inside a source tree that is
meant to be shared, copied and eventually distributed; it makes "clone the repo" and
"carry my projects" the same operation; and it invites a `.gitignore` to be the only
thing standing between a participant profile and a public repository.

The application must also be installable and testable without ever creating user
data as a side effect.

## Decision

The data directory is external and is resolved in this order:

1. **`FOCUS_GROUP_PLATFORM_DATA_DIR`**, when set and non-empty.
2. **The operating system's local application-data directory**:
   * Windows — `%LOCALAPPDATA%\FocusGroupPlatform`
   * Linux — `$XDG_DATA_HOME/focus-group-platform`, else
     `~/.local/share/focus-group-platform`
   * macOS — `~/Library/Application Support/FocusGroupPlatform`
3. **An explicitly injected directory**, used only by tests
   (`resolve_data_dir(injected=tmp_path)`).

`apps/focus_group_platform/workspace/` is never a destination and is never created.

### No data as a side effect

Three rules, each asserted by a test:

1. Importing `platform_core` creates nothing.
2. `resolve_data_dir()` creates nothing. Creation requires `ensure=True`, which is a
   separate, explicit act performed when a project is created — not at startup.
3. The test suite passes an injected temporary directory and never touches the real
   resolution result.

Resolution returns a record, not a bare path, so the interface can show *where* the
data lives and *why*:

```
DataDirResolution(path, source, env_var_name, exists, created_by_this_call)
```

`source` is one of `env_var`, `os_app_data`, `injected`.

## Consequences

**Positive.** A researcher's data survives a fresh clone and is never committed by
accident. Distribution of the application carries no user data by construction. Tests
cannot pollute a real installation. The resolution order lets a researcher put data
on an encrypted volume or a shared drive with one environment variable.

**Negative.** Data is no longer beside the code, so "where are my projects?" needs an
answer in the interface — hence the Configuration panel showing the resolved path and
its source. Backup becomes the researcher's responsibility, and the README must say
so.

**Rejected alternative.** A `--data-dir` flag only. Rejected because Streamlit's
invocation makes flags awkward to pass and easy to forget; an environment variable
plus a sane OS default is the pattern researchers already meet in other tools.
