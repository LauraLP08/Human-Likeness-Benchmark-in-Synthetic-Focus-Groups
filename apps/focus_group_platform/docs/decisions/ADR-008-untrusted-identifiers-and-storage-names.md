# ADR-008 - Identifiers from files are untrusted input

* **Status:** Accepted (2026-08-04)
* **Decides:** how `agent_id`, `guide_id`, `session_id` and `project_id` may reach the
  filesystem

## Context

An independent review found three places where an identifier read from a file decided
a path:

* `derive_profile()` built `out_dir / f"{record.agent_id}.json"`;
* `write_compiled()` used `guide_id` as a file name;
* `plan_session_destination()` did `root / session_id` and validated only the project
  prefix - so `pilot__../../outside` kept the prefix and still escaped.

All three take their value from a file a researcher uploaded. That file may be
malformed, copied from elsewhere, or hostile. An identifier is data, not a path.

## Decision

**Identity and storage name are separate concerns, and the identifier must satisfy the
storage contract.**

1. **Validate on load.** `agent_id` is checked the moment a profile is read;
   `guide_id` is checked before the guide compiles; `session_id` and `project_slug`
   are checked before a destination is resolved.
2. **Never rewrite silently.** An invalid identifier is a localised error naming the
   file, the field and the rule. The application does not sanitise an id into
   something that "works", because the substantive research identity would then differ
   from what the researcher supplied - and two different ids could collapse onto one
   storage name.
3. **Carry an explicit storage name.** `ProfileRecord.storage_name` and
   `CompiledGuide.storage_name` hold the validated component. Path construction reads
   the storage name, never the raw identifier. When the identifier is valid the two are
   equal; the separation exists so a future decision to allow richer identifiers
   (hashed storage names) is a change in one place rather than an audit of every join.
4. **`safe_path` is the only join.** No module concatenates.

### The contract

ASCII letters, digits, dot, underscore, hyphen; 1-128 characters; not `.` or `..`; no
separators; not a reserved Windows device name.

**Spaces and Unicode are refused, deliberately.** These identifiers travel into file
names, session ids and provenance keys across a pipeline that performs no Unicode
normalisation. Accepting `café` would let NFC and NFD spellings denote one directory on
macOS and two on Linux, and confusable scripts (Latin `a` vs Cyrillic `а`) would make
two distinct research identities indistinguishable in a file listing. The cost is that
a researcher with non-ASCII participant ids must supply an ASCII id and keep the
display name in the profile body, where it belongs.

**The reserved-name check is exact, not substring.** `CON` is refused; `pilot__CON` is
a legal directory name and is allowed. Over-refusing would reject valid research
identifiers for no security gain - a test pins this both ways.

## Consequences

**Positive.** No identifier reaches the filesystem unvalidated. A refusal happens
before any file is opened, so a rejected profile or guide leaves nothing behind.
Fifteen hostile identifiers are exercised against each of the four entry points.

**Negative.** Researchers with non-ASCII or spaced identifiers must rename them. That
is a real cost and the error message states the rule rather than merely refusing.

**Rejected alternative.** Silently slugifying an unsafe id. Rejected because two ids
can slugify to one name, and because the run manifest would then record an identity the
researcher never wrote.
