# Output and Audit Guide

This document explains the file artifacts produced during a session, the source-of-truth hierarchy, and how to verify session completeness and integrity.

## 1. Source-of-Truth Hierarchy

**CRITICAL RULE:** The canonical `output/session_logs/{session_id}/` folder is the **absolute source of truth** for any session.

- **Canonical Artifacts:** Files in `output/session_logs/{session_id}/` represent the actual state and history of the session.
- **Audit Copies:** Folders under `docs/testing/` (like `docs/testing/macho_meals_emergent_run_validation/live_run_outputs/`) are mere mirrors or audit copies. They must match the canonical artifacts.
- **Reports:** Markdown reports (e.g., `MACHO_MEALS_EMERGENT_RUN_REPORT.md`) are interpretations. They must be checked against disk artifacts to ensure they are not based on stale in-memory counters.
- **In-Memory Counters:** Not sufficient evidence of success if the process crashes before saving to disk.

## 2. Output File Map

### Canonical Session Logs
**Location:** `output/session_logs/{session_id}/`

| File | Created By | Contents | UI-Visible | Source of Truth |
|------|------------|----------|------------|-----------------|
| `transcript.json` | `orchestrator.save_transcript()` | Raw list of dicts for each turn (speaker, content, turn number). | Yes | **Yes** |
| `transcript.txt` | `orchestrator.save_transcript()` | Human-readable formatted transcript matching the JSON entries. | Yes | **Yes** |
| `moderator_log.json` | `orchestrator.save_moderator_log()` | Array of `ModeratorAPIResponse` objects detailing every moderator decision, including silent turns. | No | **Yes** |
| `api_calls.jsonl` | `api_logging.append_api_log()` | JSONL log of every LLM API call (input/output tokens, models, success/failure). | No | **Yes** |
| `session_state_initial.json` | `orchestrator.__init__()` | Snapshot of `SessionState` immediately after configuration load. | No | **Yes** |
| `state_turn_*.json` | `orchestrator.run_moderator_turn()` | Snapshot of `SessionState` at the end of each turn. | No | **Yes** |

### Testing and Audit Outputs
**Location:** `docs/testing/{validation_folder}/`

| File/Folder | Purpose |
|-------------|---------|
| `live_run_outputs/` | A direct copy of the canonical session logs for testing stability. |
| `rendered_prompts/` | Directories containing full text of rendered user/system prompts sent to the LLM (if prompt interception is enabled). |
| `rendered_prompt_index.csv` | Index mapping prompt file names to session turns, roles, and call types. |
| `model_usage_audit.csv` | A generated summary of API calls detailing model types and token counts. |
| `failed_runs/` | Archive of contaminated or incomplete runs moved out of the canonical directory to prevent state corruption. |

## 3. How to Verify a Run

### A. Verifying Run Completion
Do not rely on the run script exiting without a traceback. A run is only complete if it successfully closed the discussion guide.
1. Open the highest-numbered `state_turn_*.json`.
2. Inspect the `discussion_guide` array.
3. Verify that `completed: true` is set for the final section (e.g., "Closing remarks").

### B. Verifying Transcript Consistency
1. Compare `transcript.json` and `transcript.txt` in the canonical folder.
2. They must contain the exact same number of turns and align perfectly. A truncated `.txt` file indicates a failure during saving.

### C. Verifying Model Usage
1. Open `api_calls.jsonl`.
2. Check the `"model"` key for all `participant_response_generation` and `moderator_decision` events. For the successful Macho Meals run (`macho_meals_emergent_full_run_02`), this must exclusively list `claude-sonnet-4-6` or its exact deployment string.

## 4. Known Caveats & Limitations

- **Contamination Risk:** Reusing a `session_id` can overwrite or contaminate state files (e.g., leaving a higher-numbered `state_turn_45.json` in the folder during a run that crashes at turn 12). Always use a unique session ID or completely wipe the folder before rerunning.
- **Missing Models:** Private model chain-of-thought is not captured and should not be requested. We infer behavior strictly from the structured JSON responses and `api_calls.jsonl`.
- **Prompt Visibility:** Participant and engagement prompt captures only exist when prompt audit/interception is explicitly enabled during the run.

## 5. Code vs Model Boundary Summary

- **Deterministic Code:** File paths, creation of JSON/TXT files, iteration over state lists to generate reports, prompt auditing loops.
- **Model-Decided:** None in this domain. Output persistence is strictly code-driven.

*Disclaimer: Model compliance with prompts is not guaranteed by documentation alone; it must be verified through transcript analysis.*
