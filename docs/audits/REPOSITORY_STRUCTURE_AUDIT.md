# Repository Structure Audit (Stage 1 Freeze)

**Date of Audit:** 2026-05-22

## 1. Main Runtime Entrypoints
- `run_session.py`: The core CLI entrypoint at the root of the project to initialize and run focus group sessions using configurations.
- `ui/server.py` & `start_ui.bat`: Entrypoints for launching the UI server.

## 2. Testing Entrypoints
- `tests/test_model_b_grocery.py`: The single primary test suite for validating the Model B infrastructure.
- `pytest tests/test_model_b_grocery.py -v`: The command used to validate the deterministic mechanics.

## 3. Available Configuration Files
Found in the `configs/` directory:
- `configs/participant_pool.json`: Defines the available personas and demographic variables.
- `configs/session_remote_work.json`: Thematic config for a remote work discussion.
- `configs/smoke_test_grocery.json`: Thematic config used as the blueprint for the mocked tests regarding grocery delivery.

## 4. Output Directories & Artifact Storage
Output is stored within the `output/session_logs/<session_id>/` directory.
For each session, the following artifacts are saved:
- **Transcripts:** `transcript.txt` and `transcript.json`
- **Moderator Logs:** `moderator_log.json` (preserves silent actions and decision metrics)
- **API Records:** `api_calls.jsonl`
- **State Dumps:** Turn-by-turn state backups (e.g., `state_turn_0.json`) and the final `session_state.json`.

## 5. Live Pilot Runner Status
- A generic `run_session.py` script exists at the root level which executes sessions based on provided configurations. 
- However, there is no dedicated "live pilot harness" or `scripts/run_pilot.py` specifically configured to validate thematic and persona fidelity under live Anthropic conditions yet.

## 6. Model B Fields and Constants in Code
- **Thresholds (in `core/config.py`)**:
  - `URGENCY_THRESHOLD = 0.55`
  - `PEER_ADDRESS_BONUS = 0.15`
  - `CONSENSUS_RISK_CHALLENGE_PREFERENCE = 0.10`
  - `MAX_CONSECUTIVE_PARTICIPANT_TURNS = 6`
- **Enums & State Values (in `core/session_state.py` & `core/orchestrator.py`)**:
  - `intervention_mode`: `"speak"`, `"observe"`, `"yield"`
  - `selection_mode`: `"orchestrated_round_robin"`, `"voluntary"`, `"low_threshold"`, `"silence_or_forced"`, `"moderator_intervention"`
  - `intent` (ParticipantEngagementAssessment): `"respond"`, `"challenge"`, `"affirm_and_elaborate"`, `"introduce_new_angle"`, `"stay_silent"`
  - `addressed_to` (ParticipantEngagementAssessment): `str | None` tracking peer-to-peer addressing.
  - `validation_fallback` (ModeratorAPIResponse / ModeratorLogEntry): `bool` tracking auditable moderator fallbacks.

## 7. Discrepancies Between Documentation and Code
- **Scripts Folder:** Documentation requested inspection of a `scripts/` directory, but the project utilizes root-level files like `run_session.py` instead.
- **Forced Check-in Label:** The current implementation uses `silence_or_forced` for the forced check-in path. The `TEST_PROTOCOL.md` notes that a more specific label like `"moderator_forced_by_consecutive_turns"` could be implemented for auditability in the future.

## 8. Recommended Next Implementation Stage
**Stage 2: Live Pilot Harness Implementation**
The project is ready for Stage 2: controlled live pilot harness development. This readiness is based on mocked infrastructure validation, not on live LLM human-likeness, persona fidelity, thematic fidelity, or qualitative insight quality. The immediate next requirement is to build a controlled execution harness (e.g. `scripts/run_live_pilot.py` or enhancing `run_session.py`) that performs a 10-20 turn live pilot with Anthropic endpoints.
