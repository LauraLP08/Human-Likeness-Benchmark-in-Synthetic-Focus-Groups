"""
Main session loop. Connects prompt_renderer, moderator_brain, and participant_agent
into a complete focus group session.

run_full_turn() uses an event-driven model: each participant speaks, then the
moderator assesses and either intervenes or stays silent.  Participants receive
the recent conversation context so they can react to each other, not just to
the last moderator utterance.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from core.config import (
    CONSENSUS_RISK_CHALLENGE_PREFERENCE,
    MAX_CONSECUTIVE_PARTICIPANT_TURNS,
    MODERATOR_INVITE_BONUS,
    PEER_ADDRESS_BONUS,
    URGENCY_THRESHOLD,
)
from core.moderator_brain import call_moderator, run_moderator_reflection, strip_markdown_fences
from core.participant_agent import assess_engagement, call_participant, load_agent_from_json
from core.session_state import (
    DiscussionGuideSection,
    GroupState,
    ModeratorAction,
    ParticipantState,
    ProbingDepthCeiling,
    SectionPhase,
    SectionSummary,
    SessionMeta,
    SessionState,
    StimulusConfig,
    TriggerEvent,
    TriggerEventType,
    apply_moderator_response,
    record_participant_utterance,
    safe_enum_value,
)

_OUTPUT_ROOT = Path(__file__).parent.parent / "output" / "session_logs"

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parent.parent
_RECENT_TRANSCRIPT_WINDOW = 6  # entries passed to each participant
_MAX_PARTICIPANT_HISTORY = 15  # own utterances passed to assess_engagement()
# Cheap, local (no API call) chars-per-token approximation for
# _cap_by_token_budget — standard fast heuristic for English text, not exact
# (the validated, exact figure from real API count_tokens calls was ~4
# chars/token on this project's transcripts; see
# docs/findings/2026-06-30_full_session_token_growth_issue.md verification
# addendum). An approximation is acceptable here because the budget itself
# is a soft engineering target, not something requiring billing precision —
# spending a real API call on every one of hundreds of engagement
# assessments just to count tokens for capping would defeat the purpose.
_APPROX_CHARS_PER_TOKEN = 4


def _cap_by_token_budget(entries: list[str], max_tokens: int) -> list[str]:
    """
    2026-06-30 cost fix (Part 2). Given entries in chronological order,
    return the longest RECENCY-BIASED suffix that fits within max_tokens
    (approximated by char_count / _APPROX_CHARS_PER_TOKEN), always keeping
    at least the single most recent entry even if it alone exceeds the
    budget (never returns an empty list when entries is non-empty) —
    preserves the "have I already made this point" function for the
    points most likely to still be live in the discussion, at the cost of
    visibility into very old own-turns once a long session exceeds the
    budget. Order is preserved (oldest-kept-first), matching how the
    caller numbers them for the participant.
    """
    if not entries:
        return []
    kept: list[str] = []
    total_chars = 0
    for entry in reversed(entries):
        entry_chars = len(entry)
        if kept and (total_chars + entry_chars) / _APPROX_CHARS_PER_TOKEN > max_tokens:
            break
        kept.append(entry)
        total_chars += entry_chars
    kept.reverse()
    return kept


def _build_state_from_config(session_config: dict) -> SessionState:
    """Construct an initial SessionState from the raw config dict."""
    meta = SessionMeta(
        id=session_config["session_id"],
        research_objective=session_config["research_objective"],
        topic_domain=session_config["topic_domain"],
        participant_collective_identity=session_config["participant_collective_identity"],
        moderator_knowledge_brief=session_config["moderator_knowledge_brief"],
        researcher_notes=session_config.get("researcher_notes", ""),
        temperature=session_config.get("temperature", 1.0),
        participant_response_max_tokens=session_config.get("participant_response_max_tokens"),
        participation_mode=session_config.get("participation_mode", "orchestrated"),
        moderator_model=session_config.get("moderator_model", "claude-sonnet-4-6"),
        participant_episodic_depth=session_config.get("participant_episodic_depth", "full"),
        participant_episodic_since_last_n=session_config.get("participant_episodic_since_last_n", 10),
        participant_episodic_recent_k=session_config.get("participant_episodic_recent_k", 6),
        # inject_participant_intro and run_label (formerly generation_seed) were
        # defined on SessionMeta but never read here before the 2026-06-29 fix —
        # every prior run silently got the Pydantic defaults (False, None)
        # regardless of what the JSON config said. Confirmed empirically from
        # session_state_initial.json across multiple prior runs
        # (verbosity_baseline_A1, verify_handoff, etc.): both were always
        # False/None in the actually-constructed state. Wiring them here with
        # those same defaults is behavior-preserving when a config omits them.
        # run_label has zero functional effect regardless (confirmed: never read
        # elsewhere in core/ — it is a recording-only field per its own
        # description; renamed from generation_seed 2026-06-29 because the
        # Anthropic API has no seed parameter, so the old name falsely implied a
        # determinism control — see
        # docs/changes/2026-06-29_rename_seed_to_run_label.md).
        # inject_participant_intro defaulting to False matches what every prior
        # run actually used, so no prior finding is affected by this wiring.
        inject_participant_intro=session_config.get("inject_participant_intro", False),
        run_label=session_config.get("run_label"),
        # moderator_reflection_enabled / moderator_restraint_prompt (2026-06-30):
        # both default to False, matching the Pydantic field defaults, so a
        # config omitting them is behavior-preserving — identical to before
        # these toggles existed. See
        # docs/changes/2026-06-30_moderator_dedup_A_reflection.md.
        moderator_reflection_enabled=session_config.get("moderator_reflection_enabled", False),
        moderator_restraint_prompt=session_config.get("moderator_restraint_prompt", False),
        # moderator_context_mode (2026-06-30 cost fix, Part 1): defaults to
        # "full", matching the Pydantic field default, so a config omitting
        # it is behavior-preserving — every existing short-session config
        # (including the validated n=10x3 restraint/reflection experiment)
        # is unaffected. Only configs that explicitly set "summarized" opt
        # into the new, cheaper full-session behavior.
        moderator_context_mode=session_config.get("moderator_context_mode", "full"),
        # engagement_own_history_token_budget (2026-06-30 cost fix, Part 2):
        # defaults to None, matching the Pydantic field default — legacy
        # entry-count-only capping, behavior-preserving for every existing
        # config that doesn't explicitly opt in.
        engagement_own_history_token_budget=session_config.get("engagement_own_history_token_budget"),
        # Sandbox pilot mechanism (INSTRUCTIONS_SANDBOX_MINIMAL_MODERATOR_PILOT.md):
        # all three default to None/False, matching the Pydantic field
        # defaults, so a config omitting them is behavior-preserving —
        # every existing config is unaffected.
        moderator_prompt_override=session_config.get("moderator_prompt_override"),
        moderator_opening_prompt_override=session_config.get("moderator_opening_prompt_override"),
        time_budget_tracking_enabled=session_config.get("time_budget_tracking_enabled", False),
    )

    participants: dict[str, ParticipantState] = {}
    for p in session_config["participants"]:
        has_path = "agent_payload_path" in p
        has_inline = "agent_payload" in p and bool(p["agent_payload"])
        has_legacy = any(k in p for k in ("id", "name", "profile_summary"))

        if sum([has_path, has_inline, has_legacy]) > 1:
            raise ValueError(
                "Participant entry must specify exactly one of: "
                "(a) agent_payload_path, (b) inline agent_payload dict, "
                "or (c) legacy inline fields (id/name/profile_summary). "
                f"Got conflicting keys: {sorted(p.keys())}"
            )

        if has_path:
            raw_path = Path(p["agent_payload_path"])
            if not raw_path.is_absolute():
                raw_path = _REPO_ROOT / raw_path
            if not raw_path.is_file():
                raise FileNotFoundError(
                    f"agent_payload_path does not exist: {raw_path}"
                )
            try:
                json.loads(raw_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"agent_payload_path {raw_path} is not valid JSON: {exc}"
                ) from exc
            ps = load_agent_from_json(str(raw_path))
            if not ps.agent_payload:
                ps.agent_payload = json.loads(raw_path.read_text(encoding="utf-8"))
            participants[ps.id] = ps
            continue

        if has_inline:
            raw = p["agent_payload"]
            demographics = raw["persona"]["demographics"]
            name = demographics["name"]
            age = demographics["age"]
            gender = demographics["gender"]
            parts = [f"{name}, {age}, {gender}"]
            location = demographics.get("location", {})
            if location:
                loc_parts = [
                    location.get("urban_rural", ""),
                    location.get("region", ""),
                    location.get("country", ""),
                ]
                loc_str = ", ".join(q for q in loc_parts if q)
                if loc_str:
                    parts.append(loc_str)
            diet = demographics.get("diet")
            if diet:
                parts.append(diet)
            profile_summary = ". ".join(parts) + "."
            ps = ParticipantState(
                id=raw["agent_id"],
                name=name,
                profile_summary=profile_summary,
                agent_payload=raw,
            )
            participants[ps.id] = ps
            continue

        # Legacy inline path — unchanged
        ps = ParticipantState(
            id=p["id"],
            name=p["name"],
            profile_summary=p.get("profile_summary", ""),
        )
        participants[p["id"]] = ps

    guide: list[DiscussionGuideSection] = []
    for s in session_config["discussion_guide"]:
        stimulus = None
        if s.get("stimulus"):
            stimulus = StimulusConfig(**s["stimulus"])
        if s.get("probing_depth_ceiling") is not None:
            logger.warning(
                "[orchestrator] Section %s sets probing_depth_ceiling=%r; ignoring it. "
                "This parameter is pinned to None for all runs — see _build_state_from_config.",
                s.get("section_index"), s.get("probing_depth_ceiling"),
            )
        guide.append(
            DiscussionGuideSection(
                section_index=s["section_index"],
                section_label=s["section_label"],
                section_phase=SectionPhase(s["section_phase"]),
                section_purpose=s["section_purpose"],
                scripted_question=s["scripted_question"],
                # probing_depth_ceiling is deliberately never honoured — it is
                # pinned to None for every section of every run. The researcher
                # does not use per-section depth ceilings, and no system prompt
                # (production or sandbox/minimal) defines what a ceiling would
                # actually do, so a value here would steer nothing while looking
                # like a live setting.
                #
                # Ignored-with-a-warning rather than rejected, so historical
                # configs that set it (sandbox_minimal_moderator_pilot_01/_02,
                # smoke_test_grocery, the stage6d/6e/6f verification configs)
                # still load for replay and inspection. Their session_logs stay
                # as they were; only future runs are pinned.
                probing_depth_ceiling=None,
                stimulus=stimulus,
                suggested_probes=s.get("suggested_probes", []),
            )
        )

    meta.section_phase = guide[0].section_phase

    return SessionState(
        session_meta=meta,
        discussion_guide=guide,
        participants=participants,
        group_state=GroupState(),
    )


class FocusGroupOrchestrator:

    def __init__(self, session_config: dict) -> None:
        self.config = session_config
        self.state = _build_state_from_config(session_config)

        self.log_dir = _OUTPUT_ROOT / self.state.session_meta.id
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.participant_histories: dict[str, list[dict]] = {
            pid: [] for pid in self.state.participants
        }

        # Check for participant name collisions
        names = {}
        for pid, p in self.state.participants.items():
            name_lower = p.name.lower()
            if name_lower in names:
                raise ValueError(
                    f"Name collision detected: '{p.name}' is used by {pid} and {names[name_lower]}. "
                    "Participant names must be uniquely resolvable."
                )
            names[name_lower] = pid

        self._save_json(
            self.log_dir / "session_state_initial.json",
            self.state.model_dump(mode="json"),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_name_to_id(self, name: str | None) -> str | None:
        """
        Resolve a spoken name to a participant ID, or None if ambiguous/not found.

        Two passes, because a single substring pass resolved by config order:
        the old implementation returned the FIRST participant whose name merely
        contained the spoken name, so with a roster like Sam and Samuel, "Samuel"
        resolved to whichever was listed first in the config. The constructor's
        collision check only rejects exact case-insensitive duplicates, not
        containment, so nothing else caught it.

        1. Exact case-insensitive match wins outright — "Sam" is Sam, even
           though "Samuel" also contains it.
        2. Otherwise fall back to substring containment, but only commit when
           exactly one participant matches. Two or more is genuinely ambiguous,
           and this result feeds moderator direct-address targeting: guessing
           wrong hands the turn to the wrong person, whereas returning None
           falls back to the normal engagement auction. Warn and decline.
        """
        if not name:
            return None
        name_lower = name.lower()

        for pid, p in self.state.participants.items():
            if p.name.lower() == name_lower:
                return pid

        matches = [
            pid for pid, p in self.state.participants.items()
            if name_lower in p.name.lower()
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            candidates = ", ".join(
                sorted(self.state.participants[pid].name for pid in matches)
            )
            logger.warning(
                f"[orchestrator] Ambiguous participant name {name!r}: matches "
                f"{candidates}. Not guessing — falling back to the engagement "
                f"auction for this turn."
            )
        return None

    def _save_json(self, path: Path, data: object) -> None:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _save_state_snapshot(self, label: str) -> None:
        self._save_json(
            self.log_dir / f"{label}.json",
            self.state.model_dump(mode="json"),
        )

    def _next_turn_number(self) -> int:
        return self.state.session_meta.total_turns + 1

    def _recent_transcript(self) -> list[dict]:
        """Return the last N transcript entries for participant context."""
        return self.state.transcript[-_RECENT_TRANSCRIPT_WINDOW:]

    def _get_participant_own_turns(self, pid: str) -> list[str]:
        """
        Returns this participant's own previous utterances in
        session order, capped at _MAX_PARTICIPANT_HISTORY most
        recent. Used to give assess_engagement() memory of what
        this participant has already contributed.

        Unchanged by the episodic-memory de-duplication fix below —
        this function is read by assess_engagement() only and does not
        participate in call_participant()'s message assembly.

        2026-06-30 cost fix (Part 2): when
        session_meta.engagement_own_history_token_budget is set, a SECOND,
        inner cap is applied after the existing 15-entry slice — see
        _cap_by_token_budget(). Default (None) is the legacy
        entry-count-only behavior, unchanged.
        """
        entries = [
            entry["content"]
            for entry in self.state.transcript
            if entry.get("speaker_id") == pid
        ][-_MAX_PARTICIPANT_HISTORY:]

        budget = self.state.session_meta.engagement_own_history_token_budget
        if budget is not None:
            entries = _cap_by_token_budget(entries, budget)

        return entries

    def _get_participant_episodic_entries(self, pid: str) -> tuple[list[dict], bool, int]:
        """
        Returns (entries, use_accumulated_history, entries_dropped) for
        call_participant(), based on session_meta.participant_episodic_depth.

        entries_dropped is the count of entries silently excluded by the
        'since_last_n' cap this call — 0 in every other mode, and 0 whenever
        the gap since this participant's last turn did not exceed the cap.
        Recorded (not acted on) by call_participant() via append_api_log(), so
        the rate of real information loss is visible in api_calls.jsonl rather
        than invisible.

        This is the ONLY function that determines what a participant sees in
        their response-generation prompt. It is independent of
        _recent_transcript() and _get_participant_own_turns() (the
        assess_engagement() inputs), so changing this function cannot alter
        engagement assessment's inputs.

        Modes:
          full          — every transcript entry since this participant last
                          spoke (or since session start, if they have not yet
                          spoken), no cap. Combined with the accumulated
                          per-participant history, this gives full-session
                          episodic memory with no overlap: each new message
                          covers exactly the gap since the last one, because
                          the participant's own prior turn — the boundary —
                          is excluded by construction (the slice starts AFTER
                          it).
          since_last_n  — same incremental slice, capped to the most recent
                          participant_episodic_since_last_n entries if the gap
                          is larger.
          recent_k      — legacy sliding window: the last
                          participant_episodic_recent_k transcript entries,
                          REGARDLESS of when this participant last spoke.
                          Returned with use_accumulated_history=False (the
                          caller must pass an empty history) — there is no
                          accumulated history to overlap with, so this mode
                          is self-consistent despite not using the
                          since-last-spoke slice. Kept for depth-comparison
                          experiments; not the default.
        """
        depth = self.state.session_meta.participant_episodic_depth
        transcript = self.state.transcript

        if depth == "recent_k":
            k = self.state.session_meta.participant_episodic_recent_k
            return transcript[-k:], False, 0

        last_idx = -1
        for i, entry in enumerate(transcript):
            if entry.get("speaker_id") == pid:
                last_idx = i
        new_entries = transcript[last_idx + 1:]
        entries_dropped = 0

        if depth == "since_last_n":
            n = self.state.session_meta.participant_episodic_since_last_n
            if len(new_entries) > n:
                entries_dropped = len(new_entries) - n
                new_entries = new_entries[-n:]

        return new_entries, True, entries_dropped

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_opening(self) -> str:
        """Run the session opening turn. Returns the moderator's opening utterance."""
        trigger = TriggerEvent(
            type=TriggerEventType.SESSION_START,
            speaker_id=None,
            speaker_name=None,
            content="Session is starting. No participant has spoken yet.",
            turn_number=0,
            follow_up_count_this_question=0,
        )

        api_response, last_exchange = call_moderator(
            state=self.state,
            trigger_event=trigger,
            conversation_history=[],
            is_opening_turn=True,
            log_dir=self.log_dir,
        )

        self.state = apply_moderator_response(self.state, api_response, trigger)

        # Capture initial_session_plan from the raw assistant message.
        # ModeratorAPIResponse has no such field and Pydantic's default
        # extra='ignore' drops it, so the only way to recover it is to re-parse
        # the raw text that call_moderator stored in the history.
        #
        # This MUST use strip_markdown_fences() first. Until 2026-07-27 it
        # called json.loads() on the raw text directly, while _try_parse()
        # stripped fences before parsing the very same string — so whenever the
        # model wrapped its response in ```json fences, the decision parsed
        # fine and the plan was silently discarded. That asymmetry cost every
        # run in the project's history its time budget. See
        # docs/changes/2026-07-27_initial_session_plan_capture_fix.md.
        #
        # Failures here are logged loudly but never raised: the plan is
        # optional enrichment and a session runs correctly without it, so this
        # side channel must not be able to abort the opening turn. Loud, not
        # fatal — silence is what hid the original bug, not breadth of catch.
        if last_exchange:
            last_msg = last_exchange[-1]
            if last_msg.get("role") == "assistant":
                raw_content = last_msg.get("content") or ""
                try:
                    raw_data = json.loads(strip_markdown_fences(raw_content))
                    # Guard rather than rely on exception handling: a valid JSON
                    # array or scalar response would make .get() raise
                    # AttributeError, and at turn 0 that would kill the session.
                    plan = raw_data.get("initial_session_plan") if isinstance(raw_data, dict) else None
                    if isinstance(plan, dict):
                        self.state.session_meta.initial_session_plan = plan
                    else:
                        logger.warning(
                            "[orchestrator] Opening response parsed as valid JSON but carried no "
                            "initial_session_plan dict (found %s). Time-budget tracking will be "
                            "inert for this session.",
                            type(plan).__name__,
                        )
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "[orchestrator] initial_session_plan not captured: opening response was "
                        "not valid JSON even after fence-stripping (%s). raw_len=%d, "
                        "starts_with_fence=%s. Time-budget tracking will be inert for this session.",
                        exc, len(raw_content), raw_content.lstrip().startswith("```"),
                    )
                except Exception:
                    logger.exception(
                        "[orchestrator] Unexpected error capturing initial_session_plan; "
                        "continuing without it."
                    )

        # Config intent vs. reality: tracking switched on but no plan captured means
        # the whole mechanism is inert, and the session would otherwise run to
        # completion (~50 min, real API spend) before anyone noticed.
        if (self.state.session_meta.time_budget_tracking_enabled
                and not isinstance(self.state.session_meta.initial_session_plan, dict)):
            logger.warning(
                "[orchestrator] time_budget_tracking_enabled=True but no initial_session_plan was "
                "captured. Every turn will render '(time budget not yet available)' and the "
                "moderator will pace without a budget."
            )

        self._save_state_snapshot("state_turn_0")
        return api_response.utterance

    def run_participant_turn(
        self,
        participant_id: str,
        recent_transcript: list[dict] | None = None,
        hook: str = "",
    ) -> str:
        """
        Run one participant's turn. Records the utterance in the transcript.
        hook: motivation string from assess_engagement; forwarded to call_participant.

        The `recent_transcript` parameter is accepted for call-site compatibility
        but is NOT used to build the prompt — what the participant actually sees
        is computed by _get_participant_episodic_entries(), per
        session_meta.participant_episodic_depth. This eliminates the
        window-overlap and self-duplication sources documented in
        docs/changes/2026-06-29_participant_memory_review.md: each call now
        receives only the entries since this participant last spoke (or the
        legacy fixed window in 'recent_k' mode, stateless), never a re-included
        slice of what is already in their accumulated conversation_history.
        """
        participant = self.state.participants[participant_id]

        last_utterance = (
            self.state.moderator_log[-1].utterance
            if self.state.moderator_log
            else "Please share your thoughts."
        )

        episodic_entries, use_history, episodic_entries_dropped = self._get_participant_episodic_entries(participant_id)
        history_in = self.participant_histories[participant_id] if use_history else []

        response_text, returned_history = call_participant(
            participant=participant,
            session_meta=self.state.session_meta,
            moderator_utterance=last_utterance,
            conversation_history=history_in,
            recent_transcript=episodic_entries,
            hook=hook,
            log_dir=self.log_dir,
            episodic_entries_dropped=episodic_entries_dropped,
        )

        if use_history:
            self.participant_histories[participant_id] = returned_history
        # else (recent_k / stateless mode): discard returned_history — each
        # call starts fresh from an empty history, by design.

        return response_text

    def run_moderator_turn(self, trigger_event: TriggerEvent, selection_mode: str | None = None) -> str:
        """
        Run a moderator assessment turn.  Returns the utterance (empty string
        when the moderator chose stay_silent).  State snapshot is always saved.
        """
        total = self.state.session_meta.total_turns
        compress_before_turn: int | None = None
        if total > 40:
            compress_before_turn = total - 20

        api_response, _ = call_moderator(
            state=self.state,
            trigger_event=trigger_event,
            conversation_history=[],
            is_opening_turn=False,
            compress_before_turn=compress_before_turn,
            log_dir=self.log_dir,
        )

        if trigger_event.type == TriggerEventType.PARTICIPANT_RESPONSE:
            self.state = record_participant_utterance(self.state, trigger_event, selection_mode=selection_mode)

        self.state = apply_moderator_response(self.state, api_response, trigger_event, selection_mode=selection_mode)

        # Reflection cadence (2026-06-30, toggleable, OFF by default): fires
        # ONLY at section/question boundaries — when the moderator's action
        # this turn was SECTION_TRANSITION — not on a turn-count fallback.
        # A handful of calls per session. When the toggle is False this whole
        # block is skipped — section_summaries stays empty, and behavior is
        # unchanged from before this mechanism existed.
        #
        # No code-level queued_next_action lapsing: moderator_turn_share_overall/
        # _recent (computed unconditionally in apply_moderator_response, just
        # above) are now visible to the moderator's regular per-turn prompt
        # whenever this toggle is on (see SessionState.to_prompt_json), so the
        # moderator itself CAN weigh "I've already intervened a lot" against a
        # queued plan on its own next decision turn. Nothing here forces that
        # reconsideration or clears the plan — light touch, per spec.
        if self.state.session_meta.moderator_reflection_enabled:
            last_log = self.state.moderator_log[-1] if self.state.moderator_log else None
            just_transitioned = last_log is not None and last_log.action == ModeratorAction.SECTION_TRANSITION
            if just_transitioned:
                # 2026-06-30 cost-fix Part 3: feed the reflection call only the
                # turns SINCE the prior reflection-triggering boundary (the
                # section that just ended), not the full transcript — paired
                # with the prior accumulated summaries (Part 0) for continuity,
                # so the model isn't asked to re-discover earlier sections from
                # scratch. transition_turns[-1] is the boundary that JUST fired
                # (already in moderator_log, appended by apply_moderator_response
                # above); the boundary before that (if any) is where this
                # section's new content starts. First-ever reflection has no
                # prior boundary, so it covers everything since session start —
                # at that point "since last reflection" and "full transcript so
                # far" are identical, which is correct (nothing to compress yet).
                transition_turns = [
                    e.turn for e in self.state.moderator_log
                    if e.action == ModeratorAction.SECTION_TRANSITION
                ]
                prior_boundary_turn = transition_turns[-2] if len(transition_turns) >= 2 else -1
                since_last_reflection = [
                    e for e in self.state.transcript if e.get("turn", -1) > prior_boundary_turn
                ]

                reflection = run_moderator_reflection(
                    self.state,
                    transcript_slice=since_last_reflection,
                    log_dir=self.log_dir,
                )
                if reflection is not None:
                    # Part 0: APPEND, don't overwrite — find the section that
                    # was just marked completed (the highest-index completed
                    # section not yet represented in section_summaries; by this
                    # point apply_moderator_response has already advanced
                    # current_section_index, so we can't just read that field).
                    covered = {s.section_index for s in self.state.group_state.section_summaries}
                    just_completed = max(
                        (s for s in self.state.discussion_guide if s.completed and s.section_index not in covered),
                        key=lambda s: s.section_index,
                        default=None,
                    )
                    if just_completed is not None:
                        self.state.group_state.section_summaries.append(
                            SectionSummary(
                                section_index=just_completed.section_index,
                                section_label=just_completed.section_label,
                                discussion_summary=reflection.discussion_summary,
                                strategy_summary=reflection.strategy_summary,
                            )
                        )
                # On failure (returns None), section_summaries simply doesn't
                # gain an entry for this section — the next boundary tries again
                # for the section after it; this one's content remains visible
                # only via the (now-passed) verbatim slice at the time, not lost
                # from the transcript itself.

        turn_n = self.state.session_meta.total_turns
        self._save_state_snapshot(f"state_turn_{turn_n}")
        return api_response.utterance

    def run_full_turn(self) -> dict:
        """
        Event-driven round: participants speak in turn-count order; after each
        participant the moderator assesses and either intervenes (producing an
        utterance) or stays silent.  Each participant receives the last
        RECENT_TRANSCRIPT_WINDOW transcript entries so they can react to each
        other, not just to the moderator.

        Returns a summary dict with all participant responses and the last
        moderator intervention this round (empty string if the round ended
        on a stay_silent).
        """
        ordered_ids = sorted(
            self.state.participants.keys(),
            key=lambda pid: (self.state.participants[pid].turn_count, pid),
        )

        participant_responses: dict[str, str] = {}
        # Track every moderator event this round (silent or not) for the return dict
        round_moderator_events: list[dict] = []

        for pid in ordered_ids:
            # Participant speaks, informed by the recent conversation
            recent = self._recent_transcript()
            response_text = self.run_participant_turn(pid, recent_transcript=recent)
            participant_responses[pid] = response_text

            # Build trigger for the moderator assessment
            participant = self.state.participants[pid]
            trigger = TriggerEvent(
                type=TriggerEventType.PARTICIPANT_RESPONSE,
                speaker_id=pid,
                speaker_name=participant.name,
                content=response_text,
                turn_number=self._next_turn_number(),
                follow_up_count_this_question=participant.follow_up_count_current_question,
            )

            # Moderator assesses
            moderator_utterance = self.run_moderator_turn(trigger, selection_mode="orchestrated_round_robin")
            
            last_log = self.state.moderator_log[-1]
            action = last_log.action

            round_moderator_events.append({
                "after_participant": pid,
                "action": safe_enum_value(action),
                "utterance": moderator_utterance,
                "silent": action == ModeratorAction.STAY_SILENT,
            })

        # Summarise: find the last non-silent moderator event for the return value
        last_intervention = next(
            (e for e in reversed(round_moderator_events) if not e["silent"]),
            round_moderator_events[-1] if round_moderator_events else {},
        )

        return {
            "turn_number": self.state.session_meta.total_turns,
            "participant_responses": participant_responses,
            "moderator_action": last_intervention.get("action", ""),
            "moderator_utterance": last_intervention.get("utterance", ""),
            "moderator_events": round_moderator_events,
        }

    def _run_full_turn_streaming(self):
        """
        Streaming variant of run_full_turn(). Yields one exchange dict per
        participant-moderator pair so callers can emit utterances progressively.
        Keeps run_full_turn() unchanged for CLI compatibility.
        """
        ordered_ids = sorted(
            self.state.participants.keys(),
            key=lambda pid: (self.state.participants[pid].turn_count, pid),
        )
        for pid in ordered_ids:
            recent = self._recent_transcript()
            response_text = self.run_participant_turn(pid, recent_transcript=recent)
            participant = self.state.participants[pid]
            trigger = TriggerEvent(
                type=TriggerEventType.PARTICIPANT_RESPONSE,
                speaker_id=pid,
                speaker_name=participant.name,
                content=response_text,
                turn_number=self._next_turn_number(),
                follow_up_count_this_question=participant.follow_up_count_current_question,
            )
            moderator_utterance = self.run_moderator_turn(trigger, selection_mode="orchestrated_round_robin")
            last_log = self.state.moderator_log[-1]
            action = last_log.action
            yield {
                "participant_id": pid,
                "participant_name": participant.name,
                "participant_text": response_text,
                "moderator_action": safe_enum_value(action),
                "moderator_utterance": moderator_utterance,
                "silent": action == ModeratorAction.STAY_SILENT,
            }

    # ------------------------------------------------------------------
    # Emergent mode helpers
    # ------------------------------------------------------------------

    def _build_trigger_event(self, participant_id: str, response_text: str) -> TriggerEvent:
        participant = self.state.participants[participant_id]
        return TriggerEvent(
            type=TriggerEventType.PARTICIPANT_RESPONSE,
            speaker_id=participant_id,
            speaker_name=participant.name,
            content=response_text,
            turn_number=self._next_turn_number(),
            follow_up_count_this_question=participant.follow_up_count_current_question,
        )

    def _get_requested_next_speaker(self) -> str | None:
        if not self.state.moderator_log:
            return None
        last = self.state.moderator_log[-1]
        pid = getattr(last, "target", None)
        if pid and pid != "group" and pid in self.state.participants and last.action == ModeratorAction.INVITE_TO_SPEAK:
            return pid
        return None

    def _resolve_moderator_targets(self, target: str | None) -> list[str]:
        """Resolve a moderator target string to a list of participant IDs."""
        if not target or target.lower() == "group":
            return []
        parts = [t.strip() for t in target.split(",") if t.strip()]
        resolved = []
        for part in parts:
            if part in self.state.participants:
                resolved.append(part)
            else:
                pid = self._resolve_name_to_id(part)
                if pid:
                    resolved.append(pid)
        return list(dict.fromkeys(resolved))

    def run_conversation_step(self) -> dict:
        """
        Model B (Group Discussion) entry point.
        Participants self-select based on categorical intents, urgency, and contextual bonuses.
        The moderator intervenes only when a threshold is met or to shape the discussion.
        """
        recent = self._recent_transcript()
        
        # Save previous round to check peer address
        prev_assessments = self.state.group_state.last_engagement_round or []
        last_speaker_id = self.state.transcript[-1].get("speaker_id") if self.state.transcript else None
        
        last_speaker_addressed_id = None
        if last_speaker_id:
            for prev_a in prev_assessments:
                if prev_a.participant_id == last_speaker_id and prev_a.addressed_to:
                    last_speaker_addressed_id = self._resolve_name_to_id(prev_a.addressed_to)
                    break

        mod_log = self.state.moderator_log
        last_mod = mod_log[-1] if mod_log else None

        # Resolve moderator direct-address before the assessment loop so we can
        # skip N-1 assess_engagement calls when a single target is named.
        # See docs/changes/2026-07-23_single_target_assessment_optimization.md
        direct_target_pids = self._resolve_moderator_targets(
            last_mod.target if last_mod and getattr(last_mod, "intervention_mode", "speak") == "speak" else None
        )

        selection_mode = "voluntary"
        next_pid = None
        hook = ""

        if len(direct_target_pids) == 1:
            # Single named target → assess only the target (1 call), skip auction.
            # The assessment is needed solely to capture addressed_to for the next
            # step's peer-address bonus; urgency/intent are not used here.
            target_pid = direct_target_pids[0]
            target_participant = self.state.participants[target_pid]
            assessments = [assess_engagement(
                target_participant,
                self.state.session_meta,
                recent,
                participant_own_turns=self._get_participant_own_turns(target_pid),
                log_dir=self.log_dir,
            )]
            self.state.group_state.last_engagement_round = assessments
            next_pid = target_pid
            selection_mode = "moderator_direct_address"
        else:
            # 1. Assess all participants
            assessments = []
            for pid, participant in self.state.participants.items():
                own_turns = self._get_participant_own_turns(pid)
                assessment = assess_engagement(
                    participant,
                    self.state.session_meta,
                    recent,
                    participant_own_turns=own_turns,
                    log_dir=self.log_dir
                )
                assessments.append(assessment)
            self.state.group_state.last_engagement_round = assessments

            # Seeded, reproducible shuffle used ONLY to break ties fairly.
            # Does NOT mutate `assessments` — last_engagement_round keeps config order
            # for logs/state. Both selection branches below read from `selection_order`
            # instead: the sort keys stay exactly as they were, but because Python's
            # sort is stable, entries tied on (-urgency, turn_count) now retain a
            # seeded-random relative order rather than config insertion order. Seeding
            # on (session_id, total_turns) keeps a run byte-for-byte reproducible while
            # varying the winner across turns, so no participant holds a fixed
            # first-speaker advantage.
            selection_order = list(assessments)
            rng = random.Random(f"{self.state.session_meta.id}:{self.state.session_meta.total_turns}")
            rng.shuffle(selection_order)

            # Multi-target (soft bonus) or no target (unchanged) — run the auction

            # 2 & 3. Apply Contextual Urgency Bonuses & Dynamic Intent Adjustment
            for a in assessments:
                bonus = 0.0

                # Peer Address
                if last_speaker_addressed_id == a.participant_id:
                    bonus += PEER_ADDRESS_BONUS

                # Moderator Direct Address (multi-target bonus)
                if a.participant_id in direct_target_pids:
                    bonus += MODERATOR_INVITE_BONUS

                # Cap bonus
                bonus = min(bonus, 2 * PEER_ADDRESS_BONUS)
                a.urgency = min(1.0, a.urgency + bonus)

                # Consensus Risk Challenge Preference
                if self.state.group_state.consensus_risk >= 0.65 and a.intent == "challenge":
                    a.urgency = min(1.0, a.urgency + CONSENSUS_RISK_CHALLENGE_PREFERENCE)

            # 4. Select Speaker
            willing = [a for a in selection_order if a.wants_to_speak and a.intent != "stay_silent" and a.urgency >= URGENCY_THRESHOLD]

            if willing:
                willing.sort(key=lambda a: (-a.urgency, self.state.participants[a.participant_id].turn_count))
                next_pid = willing[0].participant_id
                hook = willing[0].hook
            else:
                # Nobody above threshold — lower bar after 2 consecutive silent steps
                if self.state.group_state.consecutive_silent_turns >= 2:
                    all_sorted = sorted(
                        [a for a in selection_order if a.intent != "stay_silent"],
                        key=lambda a: (-a.urgency, self.state.participants[a.participant_id].turn_count),
                    )
                    if all_sorted and all_sorted[0].urgency > 0.2:
                        next_pid = all_sorted[0].participant_id
                        hook = all_sorted[0].hook
                        selection_mode = "low_threshold"

        # 5. Check MAX_CONSECUTIVE_PARTICIPANT_TURNS gate
        if next_pid and self.state.group_state.consecutive_participant_turns >= MAX_CONSECUTIVE_PARTICIPANT_TURNS:
            # Force moderator intervention, overriding participant selection
            next_pid = None
            selection_mode = "moderator_forced_by_consecutive_turns"

        # 6. Check dominant_voices gate — same enforcement shape as the consecutive-turns
        # gate above, different signal: GroupState.dominant_voices is already recomputed every
        # turn (session_state.py, pure arithmetic — no LLM judgment involved) as the list of
        # participants who have taken >50% of the CURRENT SECTION's turns. It is currently
        # computed but never acted on. Require a minimum section sample before honoring it —
        # otherwise the very first speaker in a brand-new section is trivially "100% of turns
        # so far" and would force an intervention after a single turn, which is not the intent.
        section_total = sum(self.state.group_state.section_turn_counts.values())
        if (
            next_pid
            and section_total >= 4
            and next_pid in self.state.group_state.dominant_voices
        ):
            next_pid = None
            selection_mode = "moderator_forced_by_dominant_voice"

        # 7 & 8. Execute turn
        if next_pid:
            response_text = self.run_participant_turn(next_pid, recent_transcript=recent, hook=hook)
            trigger = self._build_trigger_event(next_pid, response_text)
            
            # Moderator decides to observe, yield, or speak
            utterance = self.run_moderator_turn(trigger, selection_mode=selection_mode)
            
            return {
                "step_type": "participant_led",
                "selection_mode": selection_mode,
                "speaker": next_pid,
                "participant_response": response_text,
                "moderator_action": safe_enum_value(self.state.moderator_log[-1].action) if self.state.moderator_log else "",
                "moderator_intervention_mode": getattr(self.state.moderator_log[-1], "intervention_mode", "observe"),
                "moderator_utterance": utterance or "(silent)",
            }
        else:
            # Complete silence or forced intervention — moderator must speak.
            # `selection_mode` may already hold a gate-specific reason, set above by the
            # MAX_CONSECUTIVE_PARTICIPANT_TURNS or dominant_voices gates. Only trust it when
            # it's one of those two known labels — any other value sitting in the variable at
            # this point (e.g. "voluntary", "low_threshold", left over from earlier in this
            # method before next_pid was nulled out) does not describe why intervention was
            # forced, so it must not leak into the log. If neither gate fired, this is genuine
            # silence (nobody volunteered) and the original generic label is correct.
            forced_label = (
                selection_mode
                if selection_mode in (
                    "moderator_forced_by_consecutive_turns",
                    "moderator_forced_by_dominant_voice",
                )
                else "silence_or_forced"
            )
            silence_trigger = TriggerEvent(
                type=TriggerEventType.SILENCE_DETECTED,
                speaker_id=None,
                speaker_name=None,
                content="No participant volunteered to speak, or intervention forced by max turns.",
                turn_number=self.state.session_meta.total_turns,
                follow_up_count_this_question=0,
            )
            utterance = self.run_moderator_turn(silence_trigger, selection_mode=forced_label)

            return {
                "step_type": "moderator_intervention",
                "selection_mode": forced_label,
                "moderator_action": safe_enum_value(self.state.moderator_log[-1].action) if self.state.moderator_log else "",
                "moderator_intervention_mode": getattr(self.state.moderator_log[-1], "intervention_mode", "speak"),
                "moderator_utterance": utterance,
            }

    def save_transcript(self) -> None:
        """Write transcript.json and transcript.txt to the session log directory."""
        self._save_json(self.log_dir / "transcript.json", self.state.transcript)

        lines: list[str] = []
        for entry in self.state.transcript:
            speaker = entry.get("speaker_name") or entry.get("speaker_id", "UNKNOWN")
            turn = entry.get("turn", "?")
            content = entry.get("content", "")
            lines.append(f"[TURN {turn}] {speaker.upper()}: {content}")

        (self.log_dir / "transcript.txt").write_text(
            "\n\n".join(lines), encoding="utf-8"
        )

    def save_moderator_log(self) -> None:
        """Write the full moderator log (including stay_silent entries) with all justifications."""
        log_data = [entry.model_dump(mode="json") for entry in self.state.moderator_log]
        self._save_json(self.log_dir / "moderator_log.json", log_data)
