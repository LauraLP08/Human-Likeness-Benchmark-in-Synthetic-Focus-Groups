# Code Architecture Consistency Audit

This document compares the stated claims in `ARCHITECTURE.md` against the actual implementation found in the codebase.

| Topic | ARCHITECTURE.md Says | Current Code Does | Match / Mismatch / Unclear | Evidence File/Function | Practical Implication | Fix Needed? |
|-------|----------------------|-------------------|----------------------------|------------------------|-----------------------|-------------|
| **Engagement Assessment** | Model evaluates urgency out of 10. | Model evaluates urgency as float `0.0` to `1.0`. | **Mismatch** | `core/participant_agent.py:assess_engagement()` | Documentation in architecture is outdated. | Yes (Update ARCHITECTURE.md) |
| **Speaker Selection** | Next speaker is pure model choice. | Code strictly filters by `URGENCY_THRESHOLD`, applies hard-coded bonuses, and breaks ties by `turn_count`. | **Mismatch** | `core/orchestrator.py:run_conversation_step()` | System is much more deterministic than claimed. | Yes (Update ARCHITECTURE.md) |
| **Output Logs** | Mentions `transcript.json`. | Generates `transcript.json`, `transcript.txt`, `moderator_log.json`, `api_calls.jsonl`, and state snapshots. | **Mismatch** | `core/orchestrator.py:save_transcript()` | Actual output is richer and strictly canonical. | Yes (Update ARCHITECTURE.md) |
| **Moderator Fallback** | Moderator retries until success. | Retries once, then applies a hard-coded fallback `ModeratorAPIResponse` (`validation_fallback: True`). | **Mismatch** | `core/moderator_brain.py:call_moderator()` | System avoids endless loops, which is good, but undocumented. | Yes (Update ARCHITECTURE.md) |
| **Consecutive Participant Turns** | No explicit limit mentioned. | Code enforces `MAX_CONSECUTIVE_PARTICIPANT_TURNS` to force moderator intervention. | **Mismatch** | `core/orchestrator.py:run_conversation_step()` | Prevents endless participant monologuing. | Yes (Update ARCHITECTURE.md) |
| **API Logging** | Barely detailed. | Comprehensive JSONL logging via `append_api_log()` tracking tokens, models, and errors. | **Mismatch** | `core/api_logging.py:append_api_log()` | Model usage audit is highly reliable. | Yes (Update ARCHITECTURE.md) |
| **Model Version** | Uses `claude-3-opus-20240229` in old configs. | Hardcoded to `claude-sonnet-4-20250514` in `moderator_brain.py`. Participants use `claude-haiku-4-5-20251001` default, overridden by `claude-sonnet-4-6` in Macho Meals configs. | **Mismatch** | `core/moderator_brain.py` and `core/participant_agent.py` | Cost and latency are heavily impacted. | Yes (Update ARCHITECTURE.md) |

*Conclusion:* The `ARCHITECTURE.md` file contains several outdated claims regarding the exact mechanics of emergent mode and moderator boundaries. The codebase has evolved to be more robust, incorporating deterministic safety rails (fallbacks, limits) that are not fully described in the high-level architecture.
