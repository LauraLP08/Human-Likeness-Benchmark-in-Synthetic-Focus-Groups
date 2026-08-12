# Session logs

46 session directories. **30 are the canonical experiment**; the other 12 are excluded,
aborted or pilot runs, kept so the operational record is complete rather than tidy.

The authoritative list is `analysis/production_evaluation/canonical_experiment_manifest.csv`
(`physical_run` column), which also carries a SHA-256 for each run's transcript, config,
agent set, guide and moderator prompt. **Never infer condition, focus group or replicate
index from a directory name** — `macho_meals_fg4_run04` is enriched replicate 2, not
replicate 4.

## The 30 canonical runs

| Condition | Focus group | Directories |
|---|---|---|
| `enriched` | fg1, fg2, fg3 | `macho_meals_fg{1,2,3}_run0{1,2,3}` |
| `enriched` | fg4, fg5 | `macho_meals_fg{4,5}_run01`, `_run03`, `_run04` |
| `demographics-only` | fg1–fg5 | `macho_meals_fg{1..5}_demoonly_run0{1,2,3}` |

`fg4_run02` and `fg5_run02` were superseded by `run04` and are **not** in the canonical
30; their logs are present below.

## The 12 non-canonical runs

| Directory | What it is |
|---|---|
| `macho_meals_fg4_run02`, `macho_meals_fg5_run02` | Superseded enriched replicates |
| `macho_meals_fg1_run01__failed_auth_attempt` | Aborted on an authentication failure |
| `macho_meals_fg1_run01_killed_2026-07-27` | Terminated manually |
| `macho_meals_fg1_run01_nobudget_2026-07-27` | Run without the time-budget feature |
| `macho_meals_fg1_run01_partial_2026-07-26` | Incomplete run |
| `macho_meals_fg1_run01_presynthesisfix_pilot_2026-07-28` | Pilot before the moderator-synthesis fix |
| `macho_meals_emergent_full_run_01`, `_02` | Early full-session emergent-mode runs |
| `macho_meals_test_001`, `macho_meals_validation_run`, `macho_meals_validation_run_01` | Machinery checks |

`macho_meals_emergent_full_run_01` is an empty directory in the source repository; it
carries a README so git can represent the path, which
`apps/focus_group_platform/frozen_sessions.json` lists as protected.

The twin-population arm's 7 session logs are **not** here. They are in
`transferability/census_built_personas/output/session_logs/`, deliberately kept out of this
directory because several analysis scripts enumerate runs by listing it and would fold
that arm into the enriched condition mean.

## What each directory contains

| File | What it is |
|---|---|
| `transcript.json`, `transcript.txt` | The session transcript |
| `moderator_log.json` | Every moderator decision, including turns where it chose not to speak, and any validation fallback |
| `api_calls.jsonl` | One record per model call: timestamp, role, model, input/output tokens, parse and validation outcome, error type, and the head of the raw response. This is the source for cost and duration. |
| `session_state_initial.json` | The state the session started from |
| `state_turn_N.json` | A **cumulative** snapshot after turn N. The highest-numbered file supersedes the rest; the series is kept so a run can be replayed turn by turn. |
| `launcher_stdout.log` | The launcher's console output, where a parallel runner produced one |

`api_calls.jsonl` contains no credentials — only token counts, model names and response
prefixes.
