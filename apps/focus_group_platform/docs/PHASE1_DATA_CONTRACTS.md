# Phase 1 — Data contracts

**Status: SPECIFICATION.** Every schema below is expressed as a Pydantic-style field
list. `?` marks optional. Unless stated otherwise, absent means `null`, and `null`
means **undefined** — never zero, never an empty string, never a default value
invented by the application.

---

## 1. Vocabulary

| Term | Meaning |
|---|---|
| `undefined` | The value does not exist for this object. Propagates to exports as `null` and to figures as an omitted point. Never coerced. |
| `replicate_label` | A label for an independent execution (`r1`, `r2`, …). **Not a seed.** The provider exposes no seed. |
| `panel_sampling_seed` | A genuine RNG seed controlling *which agents are drawn* from a population. Reproducible. Unrelated to generation determinism. |
| `frozen` | Belongs to the thesis corpus. Read-only for this application. |

---

## 2. Project

```
Project
  project_id            str    slug, generated, [a-z0-9_-]{1,64}
  name                  str
  description?          str
  created_at            datetime (UTC)
  updated_at            datetime (UTC)
  schema_versions       SchemaVersions          see §9
  demo_mode             bool
  default_pricing_table_version  str
  audit_log_path        str    relative to the project root
```

Storage: `workspace/<project_id>/project.json`. All other project paths derive from
`project_id` through the single `safe_path()` helper.

---

## 3. Study definition → session config

The application composes a `SessionConfig` dict whose keys are exactly those read by
`core/orchestrator.py::_build_state_from_config` (line 90). No key is invented; no
key is renamed.

```
StudyDefinition
  study_name            str
  description?          str
  research_objective    str          → session_config.research_objective
  topic_domain          str          → session_config.topic_domain
  participant_collective_identity str → same key
  moderator_knowledge_brief str      → same key
  researcher_notes?     str          → same key
  participant_model     str
  moderator_model       str          → session_config.moderator_model
  temperature           float        → session_config.temperature
  participant_response_max_tokens? int → same key
  participation_mode    enum(orchestrated|emergent) → same key
  episodic_depth        str          → session_config.participant_episodic_depth
  episodic_since_last_n int          → same key
  episodic_recent_k     int          → same key
  moderator_context_mode enum(full|summarized) → same key
  moderator_reflection_enabled bool  → same key
  moderator_restraint_prompt bool    → same key
  time_budget_tracking_enabled bool  → same key
  n_focus_groups        int
  n_replicates          int
  condition_labels      list[str]    e.g. ["enriched","demographics-only"]
  max_turns             int          → CLI --max-turns, not a config key
```

`session_id` is generated as
`<project_slug>__<condition>__<fg>__<replicate_label>` and must be unique across the
project. This matters operationally: `run_parallel_sessions.py` documents that
`log_dir` derives purely from `session_id`, so two runs sharing an id would collide.

`run_label` is written as the human-readable run description. The application must
not present it as a determinism control; it has no functional effect
(`core/orchestrator.py` lines 111–125).

---

## 4. Profiles

```
ProfileSet
  profile_set_id        str
  source                enum(upload|repository|twin2k500)
  source_reference      str          upload storage name, or repo path, or population id
  condition_label?      str
  n_profiles            int
  profiles              list[ProfileRecord]
  validation            ProfileSetValidation
  sensitive_scan        SensitiveScanResult

ProfileRecord
  agent_id              str          unique within the set
  storage_path          str          under uploads/ or a repository path
  accepted_by_architecture bool      load_agent_from_json succeeded
  field_provenance      map[str, enum(from_file|transformed|undefined)]
  transformations       list[{field, rule, from_value, to_value}]
  undefined_fields      list[str]
  raw_payload_hash      sha256

ProfileSetValidation
  schema_ok             bool
  duplicate_ids         list[str]
  missing_required      list[{agent_id, field}]
  missing_optional      list[{agent_id, field}]
  count_ok              bool
  blocking              bool         true if any blocking problem exists

SensitiveScanResult
  scanned_fields        int
  findings              list[{agent_id, field, pattern, excerpt_masked}]
  reviewed_by_researcher bool
```

**Provenance mapping.** Existing payloads carry `field_provenance` with values
`observed`, `derived`, `observed_transcript_intro`. The loader maps
`observed`/`observed_transcript_intro` → `from_file`, `derived` → `transformed`, and
any required field absent from the map → `undefined`. The original value is retained
alongside the mapped one; the mapping is never lossy.

---

## 5. Guides

```
GuideArtifact
  guide_id              str
  source_yaml_path      str          uploads/ — never rewritten
  source_yaml_sha256    str
  compiled_json_path    str          derived/
  compiled_json_sha256  str
  compiler_version      str          semver of the guide compiler
  compiled_at           datetime
  section_count         int
  validation            GuideValidation
  correspondence_ok     bool         recompiling the YAML reproduces compiled_json_sha256

GuideValidation
  errors                list[{section_index, field, message}]
  warnings              list[...]
  phases_used           list[str]    against core.session_state.SectionPhase
  unmapped_phases       list[str]
```

`correspondence_ok == false` blocks execution (ADR-003).

---

## 6. GenerationJob

```
GenerationJob
  job_id                str
  project_id            str
  session_id            str
  condition             str
  focus_group           str
  replicate_label       str          "r1" | "r2" | …  — NOT a seed
  config_path           str          the compiled session config actually passed to the CLI
  config_sha256         str
  guide_id              str
  profile_set_id        str
  process_id            int?         OS pid; null before launch and after reaping
  status                enum(pending|launching|running|completed|failed|cancelled|orphaned|unknown)
  started_at            datetime?
  completed_at          datetime?
  output_directory      str          output/session_logs/<session_id> (read-only to the app)
  exit_code             int?
  operational_interruptions list[OperationalInterruption]
  token_usage           TokenUsage
  estimated_cost        CostEstimate
  error_message         str?
  cost_consent          {granted_at: datetime, estimate_shown: CostEstimate, pricing_table_version: str}
  code_content_hash     str          §9

OperationalInterruption
  at                    datetime
  kind                  enum(api_error|rate_limit|truncation|forced_silence|user_stop|process_died)
  detail                str
  source_artifact       str          e.g. api_calls.jsonl line number

TokenUsage
  input_tokens          int
  output_tokens         int
  total_tokens          int
  by_model              map[str, {input_tokens, output_tokens, calls}]
  source                literal "api_calls.jsonl"
  complete              bool         false while the run is in progress
```

**Status derivation is from disk, never from memory.** On UI restart, each job is
re-derived: the record exists and `completed_at` is set → terminal status from
`exit_code`; the record exists, no `completed_at`, and `process_id` is alive and owns
the expected command line → `running`; the pid is dead or belongs to another process
→ `orphaned` if the output directory has grown since the last observation, otherwise
`failed`; the output directory is absent → `unknown`. `orphaned` is a first-class
state, surfaced to the user with the partial artefacts intact — never silently
retried.

**Progress** is read from `output/session_logs/<session_id>/`: highest
`state_turn_N.json` for turn count, `transcript.json` for the active speaker,
`api_calls.jsonl` for tokens, `launcher_stdout.log` for operational lines. The app
opens these read-only.

---

## 7. Canonical transcript

The normalisation target. Independent of the current human/synthetic divergence, and
a hard precondition of Level 2 (PHASE0 §10, C-1).

```
CanonicalTranscript
  transcript_id         str
  source_file           str          path as uploaded or referenced
  source_sha256         str
  transcript_type       enum(human|synthetic)
  condition             str?         undefined for human
  focus_group           str
  replicate_label       str?         undefined for human
  model?                str          undefined for human
  normalisation         NormalisationRecord
  turns                 list[CanonicalTurn]

CanonicalTurn
  turn_id               str          stable within the transcript
  original_speaker_id   str          verbatim from the source
  canonical_speaker_id  str          REQUIRED — Level 2 raises KeyError without it
  speaker_role          enum(moderator|participant|unknown)
  text                  str          verbatim; never re-wrapped, re-cased or re-punctuated
  guide_question        str?         guide section id when confidently attributable, else undefined
  provenance            TurnProvenance

TurnProvenance
  source_field_map      map[str,str]   canonical field → source field it came from
  derived_fields        list[str]      fields this application computed
  undefined_fields      list[str]
  notes?                str

NormalisationRecord
  normaliser_version    str
  input_schema_detected enum(standardized_human|synthetic_session_log)
  # NOT generic_json and NOT csv. Both were listed here and neither is accepted:
  # the importer refuses any transcript that is not one of the two standardized
  # shapes, because a speaker's role cannot be inferred from position in a file.
  # A researcher who read this enum wrote a generic JSON file and had it refused
  # with no worked example anywhere to correct it. See README.md section 3.1.
  writes_to             literal "derived/"   uploads are never rewritten
  unmapped_source_fields list[str]           retained, not discarded
  warnings              list[str]
```

Known source schemas, from the audit:

* standardized human — `turn, speaker_id, canonical_speaker_id, speaker_name,
  speaker_role, content, source_type, source_file, original_file_type, page,
  paragraph_indices, standardization_confidence, requires_review`
* synthetic session log — `turn, speaker_id, speaker_name, content, timestamp,
  selection_mode`

For the synthetic schema `canonical_speaker_id` does not exist and is **derived** from
`speaker_id`; `speaker_role` is derived by the rule *speaker_id == "MODERATOR" →
moderator, else participant*. Both derivations are recorded in `derived_fields`. This
mirrors what `scripts/lexical_analysis.py::_synth_session` already does, and is
documented as derived from it.

---

## 8. Comparable window and matching

```
ComparableWindow
  window_id             str
  transcript_id         str
  status                enum(proposed|under_review|locked|rejected)
  derivation_rule       str          human-readable rule that produced the proposal
  start                 Boundary
  end                   Boundary
  unambiguous           bool         false → review queue, execution blocked
  reviewed_by?          str
  reviewed_at?          datetime
  researcher_note?      str
  locked_sha256?        str          hash of the retained text, set when status=locked
  positional_fallback_used bool      true only if a researcher explicitly chose one

Boundary
  turn_id               str
  char_offset           int?         sub-entry offset; null means the whole entry
  matched_text          str          the text the boundary sits at, for display
  confidence            enum(exact|heuristic|manual)
```

```
MatchingRow
  file                  str
  transcript_type       enum(human|synthetic)
  condition             str?
  focus_group           str?
  replicate_label       str?
  guide_id              str?
  human_referent        str?         transcript_id of the paired human file
  status                enum(OK|AMBIGUOUS|MISSING_REFERENT|CONFLICT|UNUSED)
  resolution_note?      str
```

`AMBIGUOUS` and `CONFLICT` block the benchmark. `MISSING_REFERENT` does not block:
it downgrades that file's comparative metrics to
`NOT_APPLICABLE_MISSING_HUMAN_REFERENCE` and leaves independent descriptive metrics
runnable (decision 6).

---

## 9. Provenance, versioning and cost

```
ProvenanceBlock                      embedded in every result, figure and export
  application_version   str          semver of this application
  code_content_hash     str          §9.1
  metric_registry_hash  sha256       of analysis/production_evaluation/metric_registry.csv
  guide_compiler_version str
  pricing_table_version str
  profile_schema_version str
  transcript_schema_version str
  metric_id             str
  metric_version        str          from the catalogue, not the registry row's text
  inputs                list[{path, sha256, role}]
  parameters            map[str, Any]
  exclusions            list[{what, why, n}]
  denominator           {value: int|null, definition: str}
  aggregation_path      str          e.g. "run → focus group → study replicate"
  executed_at           datetime
  evaluator_model?      str
  evaluator_config?     map
  human_intervention    bool
  human_decisions       list[review_item_id]
  result_class          enum(primary|sensitivity|exploratory)
  status                MetricStatus   see ADR-004
  demo_mode             bool
```

### 9.1 `code_content_hash` — versioning without git

Deterministic, over an **explicit ordered file list** stored as
`platform_core/provenance/code_manifest.txt`. Algorithm: for each path in list
order, hash `relative_posix_path + "\0" + sha256(file_bytes)`; concatenate; sha256
the concatenation; render as `cch:<first 16 hex>`.

The initial list: every `core/*.py`; the scripts a result actually depends on
(`structural_metrics_transportability.py`, `thematic_coding.py`,
`build_comparable_window.py`, `lexical_analysis.py`, `agent_fidelity_stylometry.py`,
`saturation_analysis.py`, `salience_hierarchy.py`, `run_full_session.py`); every
`platform_core/**/*.py`; `metric_registry.csv`.

Rules: a missing file is a hard error, not a skipped entry. The list is versioned
with the application. The hash is **never** rendered as, or labelled, a commit — the
UI shows `code content hash (no git repository present)`.

### 9.2 Pricing table

```
PricingTable
  version               str          e.g. "2026-08-04.1"
  effective_date        date
  source_note           str          where the rates came from and when they were read
  rates                 list[{model: str, mode: enum(standard|batch),
                              input_usd_per_mtok: float, output_usd_per_mtok: float}]

CostEstimate
  input_tokens          int
  output_tokens         int
  by_model              map[str, {input_tokens, output_tokens, usd}]
  total_usd             float
  pricing_table_version str
  is_estimate           literal true
  basis                 literal "api_calls.jsonl token counts × local rate table"
  unpriced_models       list[str]    models with no rate row; their cost is undefined, not zero
```

A model absent from the table yields an `undefined` cost for that portion and a
visible warning. The total is then reported as a **lower bound**, explicitly labelled.

---

## 10. Evaluation result

```
MetricResult
  metric_id             str
  status                MetricStatus
  scope                 enum(turn|focus_group|study_replicate|run|excerpt|chain|guide_section)
  condition?            str
  focus_group?          str
  replicate_label?      str
  value                 float|int|list|null      null means undefined
  denominator           {value: int|null, definition: str}
  n_excluded            int
  exclusions            list[{what, why, n}]
  human_referent?       str
  provenance            ProvenanceBlock
  warnings              list[str]
  review_items          list[str]
```

`value == null` with `status == NOT_APPLICABLE_MISSING_HUMAN_REFERENCE` is a normal,
exportable outcome. Nothing downstream substitutes zero. Aggregators skip nulls and
report the reduced denominator rather than imputing.


---

# AMENDMENT 1 - Phase 1 conditional approval (2026-08-04)

The decisions below **supersede** the text above where they conflict. Superseded text
is left in place so the review history stays legible.

## A1.1 Data directory (ADR-005)

`workspace/<project_id>/` is no longer inside the repository. Resolution order:
`FOCUS_GROUP_PLATFORM_DATA_DIR` -> OS local application-data directory -> an
explicitly injected directory (tests only). Every path in this document that reads
`workspace/...` now means `<resolved_data_dir>/projects/<project_id>/...`.

```
DataDirResolution
  path                  Path
  source                enum(env_var|os_app_data|injected)
  env_var_name          literal "FOCUS_GROUP_PLATFORM_DATA_DIR"
  exists                bool
  created_by_this_call  bool     always false unless ensure=True was passed
```

Resolution never creates anything. Creation is a separate, explicit call.

## A1.2 Profiles accept JSON and YAML (correction A)

`ProfileSet.source` gains `upload_yaml`; `ProfileRecord` gains:

```
  source_format         enum(json|yaml)
  original_sha256       str      hash of the uploaded bytes, whichever format
  canonical_sha256      str      hash of the canonical JSON serialisation
```

Canonicalisation is `json.dumps(payload, sort_keys=True, ensure_ascii=False,
separators=(",", ":"))`. **Contract:** a JSON file and a YAML file carrying the same
information produce the same `canonical_sha256`. Both keep the original file
unchanged, validate against the same schema, preserve `field_provenance`, and leave
absent attributes undefined.

CSV stays out of the MVP: a flat table cannot carry per-field provenance without an
added column-mapping layer, which is a separate contract.

## A1.3 Derived agent payloads (ADR-007)

`StudyDefinition.participant_model` is **removed** as a session-config field. The
participant model lives at `agent_payload.simulation_config.model`
(`core/participant_agent.py` lines 951, 964). Selecting a model produces a derived
copy:

```
DerivedProfile
  derived_id            str
  source_profile_path   str      original, unchanged
  source_sha256         str
  derived_path          str      <project>/derived/profiles/<agent_id>.json
  derived_sha256        str
  run_transformations   list[RunTransformation]
  field_provenance      map[str, enum(from_file|transformed|undefined)]

RunTransformation
  field_path            str      e.g. "simulation_config.model"
  rule                  str      e.g. "study.participant_model applied"
  from_value            Any
  to_value              Any
  applied_at            datetime
```

`field_provenance["simulation_config.model"]` becomes `transformed`. The session
config points at `derived_path`. Nothing under `agents/` or `uploads/` is written.

`participant_response_max_tokens` is documented as a **technical ceiling**, not a
target length and not a uniformity instruction.

## A1.4 Session destination (ADR-006)

```
SessionDestinationPlan
  session_id            str      "<project_slug>__<condition>__<fg>__<replicate>"
  resolved_path         Path     output/session_logs/<session_id>
  collision             bool     any existing directory at that path
  frozen                bool     path is in frozen_sessions.json
  allowed               bool     not collision and not frozen
  refusal_reason        str?
```

Resolved before launch. A collision or a frozen match refuses; the application never
overwrites and never auto-resumes.

## A1.5 Figure provenance sidecar (correction E)

A figure carries only `metric_id`, the exploratory/withheld status when applicable,
and the essential unit or denominator. The full `ProvenanceBlock` is written to
`<figure_stem>.provenance.json` beside the image and included in the export bundle.

## A1.6 New runtime status

`NOT_APPLICABLE_INSTRUMENT_UNAVAILABLE` - the metric's instrument (a specific
evaluator model version) is not available. Level 1 does not run; no substitute model
is used.


---

# AMENDMENT 2 - Phase 2A.1 hardening (2026-08-04)

Findings from an independent security review of the Phase 2A code. These supersede the
text above where they conflict; the superseded text stays so the review history is
legible.

## A2.1 Identifiers are untrusted input (ADR-008)

`ProfileRecord` gains `storage_name`; `CompiledGuide` gains `storage_name`. Both hold
the validated path component. `agent_id`, `guide_id`, `session_id` and `project_id`
must satisfy the safe-component contract (ASCII letters, digits, dot, underscore,
hyphen; 1-128; no separators; not a reserved device name). Spaces and Unicode are
refused by documented decision. An invalid identifier is a localised error, never a
silent rewrite.

`SessionDestinationPlan` now refuses before touching the filesystem: `project_slug` and
`session_id` are validated as components and the destination is built with `safe_path`
BEFORE collision or frozen state is consulted. A refused plan carries
`resolved_path.name == "<refused>"`.

## A2.2 Project root is derived, not stored (ADR-009)

`Project.root` written into `project.json` is a record, not an authority. On load the
root is derived from `<resolved_data_dir>/projects/<validated_project_id>`; a recorded
root must match it exactly or the load is refused.

## A2.3 Atomic writes (ADR-010)

`atomic_write_text(target, text, on_exists, verify)` replaces direct writes for
`project.json`, derived profiles and compiled guides. `on_exists` defaults to `FAIL`
for derived artefacts; `project.json` uses `REPLACE` explicitly.

## A2.4 Injected data directory (ADR-005 amended)

`resolve_data_dir(injected=..., ensure=False, allow_repo_for_tests=False)`. A path
inside the repository is refused **even when injected**, unless a test passes
`allow_repo_for_tests=True` explicitly. Production code, the future Streamlit layer and
any future API never set it.

## A2.5 Canonical transcript, corrected field list

`CanonicalTurn` carries `original_index` (the source array coordinate) alongside
`original_turn_id`, and the transcript carries `source_file` + `source_sha256`. An
unresolved `speaker_role` or `canonical_speaker_id` leaves the turn UNRESOLVED, creates
a `ReviewItem`, and blocks the metrics that need that field. No value is assigned by
position.
