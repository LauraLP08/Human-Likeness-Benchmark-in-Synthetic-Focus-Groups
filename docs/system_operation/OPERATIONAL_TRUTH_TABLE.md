# Operational Truth Table

This table lists specific claims about a live session and exactly how to verify them using canonical disk artifacts.

| Claim | Verification Method |
|-------|---------------------|
| 1. "The run used all five participants." | Check canonical `session_state_initial.json` for 5 entries under `participants`, and verify all 5 IDs appear in `transcript.json` under `speaker_id`. |
| 2. "The run completed the guide naturally." | Check the final `state_turn_*.json`. The `discussion_guide` array must show `completed: true` for the final section. |
| 3. "The run used Claude Sonnet everywhere." | Parse `api_calls.jsonl`. Verify `"model"` key equals `claude-sonnet-4-6` for all rows. Confirm via `model_usage_audit.csv`. |
| 4. "Transcript json and txt are perfectly synced." | Count entries in canonical `transcript.json` and count blocks in canonical `transcript.txt`. They must match exactly. |
| 5. "Moderator prompt audits were saved." | Check `rendered_prompt_index.csv` for rows with `call_type == "moderator_turn"`, and verify corresponding files exist in the `rendered_prompts/moderator/` folder. |
| 6. "The run didn't stall due to consecutive silence." | Check `moderator_log.json` or `state_turn_*.json` for `group_state.consecutive_silent_turns`. It should rarely hit 2 or 3. |
| 7. "Emergent mode logic selected the speaker." | Verify `api_calls.jsonl` contains `participant_engagement_assessment` events immediately prior to a `participant_response_generation` event. |
| 8. "The transcript is UI-compatible." | Verify canonical `transcript.txt` exists, is non-empty, and has standard `[TURN X] SPEAKER:` formatting. |
| 9. "Moderator fallbacks did not fire constantly." | Parse `api_calls.jsonl`. Ensure `"validation_fallback": true` is rare or absent. |
| 10. "Token limits were not breached." | Parse `api_calls.jsonl`. Check that `stop_reason` is not `max_tokens` (or if it is, that it was intended behavior). |
| 11. "No stale state contaminated the run." | Verify that `session_meta.total_turns` in the final `state_turn_*.json` precisely matches the number of turns in the transcript, with no skipped numbers. |
| 12. "Participant profiles were loaded correctly." | Check `session_state_initial.json` to ensure `profile_summary` strings contain expected demographics. |
| 13. "Moderator actions adhered to schema." | Open `moderator_log.json`. Verify all `action` values map to the `ModeratorAction` enum (e.g., `direct_probe`, `stay_silent`). |
| 14. "Participant hooks were passed to generation." | Inspect `rendered_prompts/participant/` files (if auditing is on) to see if "You feel particularly compelled to speak because: [hook]" is present. |
| 15. "Consensus risk was tracked." | Check `state_turn_*.json` over time to see `group_state.consensus_risk` fluctuating between 0.0 and 1.0. |
| 16. "Follow-up intensity was captured." | Check `moderator_log.json`. Where `action` is `direct_probe`, verify `follow_up_intensity` is not null. |
| 17. "The testing folder is a true copy of the canonical run." | Run `diff` or a hash check between `output/session_logs/{session_id}/` and `docs/testing/{validation_folder}/live_run_outputs/`. They must be identical. |
| 18. "Participants interacted with each other." | Check `transcript.txt` for participants using each other's names, or check `api_calls.jsonl` engagement assessments for non-null `addressed_to` fields. |
| 19. "The run did not crash due to DNS errors." | `api_calls.jsonl` contains successful generation events through the end of the guide without abrupt truncation. |
| 20. "No qualitative evaluation claims are made." | Read `MACHO_MEALS_EMERGENT_RUN_REPORT.md` and `ARCHITECTURE.md`. Ensure only structural and architectural feasibility is claimed, per user instructions. |
