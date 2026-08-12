"""
Makes Anthropic API calls for the moderator and returns validated ModeratorAPIResponse objects.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic
from pydantic import ValidationError as PydanticValidationError

from core.prompt_renderer import (
    load_system_prompt,
    render_opening_message,
    render_reflection_message,
    render_turn_message,
)
from core.session_state import (
    DominantSignal,
    ModeratorAction,
    ModeratorAPIResponse,
    ModeratorDecisionResponse,
    ModeratorReflection,
    SessionState,
    TriggerEvent,
    safe_enum_value,
)
from core.api_logging import append_api_log
from core.api_retry import call_with_rate_limit_retry

_DEFAULT_MODERATOR_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1500
_OPENING_TURN_MAX_TOKENS = 4096
# How much of the opening turn's raw assistant text to keep in api_calls.jsonl.
# Enough to diagnose fences-vs-missing-key; NOT enough to reconstruct a full
# time_budget after the fact, so this is a diagnostic aid, not a backup.
_RAW_LOG_HEAD_CHARS = 2000
_REFLECTION_MAX_TOKENS = 700

logger = logging.getLogger(__name__)

# Strings the model sometimes produces instead of JSON null
_NULL_STRINGS: frozenset[str] = frozenset({"null", "none", "n/a", ""})
# Actions for which follow_up_intensity is meaningful
_PROBE_ACTIONS: frozenset[str] = frozenset({
    "direct_probe",
    "reflect_contradiction",
    "synthesize_and_challenge",
    "refocus_to_guide",
})


class ModeratorResponseError(Exception):
    """Raised when the moderator API response cannot be parsed or validated."""

    def __init__(self, message: str, raw_response: str = "") -> None:
        super().__init__(message)
        self.raw_response = raw_response


def _call_api(
    client: anthropic.Anthropic,
    system_prompt: str,
    messages: list[dict],
    model: str = _DEFAULT_MODERATOR_MODEL,
    max_tokens: int = _MAX_TOKENS,
    log_dir: Path | None = None,
) -> anthropic.types.Message:
    # Rate-limit retry wraps the raw call only. It sits strictly OUTSIDE the
    # JSON/Pydantic retry in call_moderator, which is unchanged.
    return call_with_rate_limit_retry(
        lambda: client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=1.0,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ],
            messages=messages,
        ),
        log_dir=log_dir,
        source_function="call_moderator",
        role="moderator",
        model=model,
    )


def strip_markdown_fences(text: str) -> str:
    """
    Strip leading/trailing markdown code fences that models sometimes add.

    Public because it is the project's canonical way to unwrap a raw model
    response before parsing it. Anything that re-parses a stored raw assistant
    message MUST go through this first — core/orchestrator.py::run_opening()
    did not, and the resulting asymmetry silently dropped
    initial_session_plan on every run in the project's history. See
    docs/changes/2026-07-27_initial_session_plan_capture_fix.md.
    """
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence line (```json or just ```)
        text = text[text.index("\n") + 1:] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return text.strip()


def _normalize_decision(raw_dict: dict) -> None:
    """Coerce null-string values and enforce action-specific field rules (mutates in place)."""
    decision = raw_dict.get("moderator_decision")
    if not isinstance(decision, dict):
        return

    # Replace common null-string variants with JSON null on nullable fields
    for field in ("probe_type", "follow_up_intensity", "queued_next_action"):
        if str(decision.get(field, "")).lower() in _NULL_STRINGS:
            decision[field] = None

    # Force probe_type=None for every action except direct_probe.
    # Do NOT default it for direct_probe — missing probe_type there must surface as a
    # validation failure and trigger a targeted retry (it is part of the audit record).
    if decision.get("action") != "direct_probe":
        decision["probe_type"] = None

    # Force follow_up_intensity=None for non-probing actions
    if decision.get("action") not in _PROBE_ACTIONS:
        decision["follow_up_intensity"] = None


def _try_parse(raw_text: str) -> tuple[ModeratorAPIResponse | None, str, str | None]:
    """
    Attempt to parse and validate a raw moderator API response.

    Returns (response, correction_message, error_type).
    On success: (response, "", None).
    On failure: (None, targeted correction message for the retry prompt, "json_parse_error" or "pydantic_validation_error").
    """
    cleaned = strip_markdown_fences(raw_text)

    try:
        raw_dict = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        print(f"[moderator_brain] JSON parse failed: {exc}", flush=True)
        return None, (
            "Your previous response was not valid JSON. "
            "Respond with only the JSON object, no additional text."
        ), "json_parse_error"

    _normalize_decision(raw_dict)

    try:
        return ModeratorAPIResponse.model_validate(raw_dict), "", None
    except PydanticValidationError as exc:
        print(f"[moderator_brain] Pydantic validation failed: {exc}", flush=True)
        return None, (
            f"Your previous response was valid JSON but failed schema validation. "
            f"The specific error was: {exc}. "
            f"Fix only the field(s) mentioned and return the complete corrected JSON object."
        ), "pydantic_validation_error"


def _build_fallback_response() -> ModeratorAPIResponse:
    """Construct a safe fallback response when both API attempts fail validation."""
    return ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="observe",
            situation_assessment="VALIDATION FALLBACK — moderator response failed validation after retry.",
            dominant_signal=None,
            action=None,
            target=None,
            probe_type=None,
            follow_up_intensity=None,
            consensus_risk_assessment=0.0,
            emotional_signals=[],
            new_contradictions=[],
            queued_next_action=None,
            new_easy_agreements=[]
        ),
        utterance="",
        validation_fallback=True,
    )


def call_moderator(
    state: SessionState,
    trigger_event: TriggerEvent,
    conversation_history: list[dict],
    is_opening_turn: bool = False,
    compress_before_turn: int | None = None,
    log_dir: Path | None = None,
) -> tuple[ModeratorAPIResponse, list[dict]]:
    """
    Call the moderator model and return a validated ModeratorAPIResponse
    plus the updated conversation_history (user + assistant messages appended).
    On persistent validation failure, returns a flagged fallback response rather
    than raising, so the session can continue.
    """
    client = anthropic.Anthropic()
    system_prompt = load_system_prompt(
        restraint_enabled=state.session_meta.moderator_restraint_prompt,
        prompt_override_filename=state.session_meta.moderator_prompt_override,
    )
    model = state.session_meta.moderator_model
    max_tokens = _OPENING_TURN_MAX_TOKENS if is_opening_turn else _MAX_TOKENS

    if is_opening_turn:
        user_message = render_opening_message(
            _state_to_session_config(state),
            opening_prompt_override_filename=state.session_meta.moderator_opening_prompt_override,
        )
    else:
        user_message = render_turn_message(state, trigger_event, compress_before_turn)

    # Construct a fresh history array containing ONLY this turn's prompt.
    # The `{SESSION_STATE}` injected inside `user_message` already contains
    # all required context, making this stateless and avoiding O(N^2) token bloat.
    history = [{"role": "user", "content": user_message}]

    # First attempt
    api_msg = _call_api(client, system_prompt, history, model=model, max_tokens=max_tokens)
    raw_text = api_msg.content[0].text
    api_response, correction, error_type = _try_parse(raw_text)
    
    if log_dir is not None:
        append_api_log(
            log_dir=log_dir,
            event_type="moderator_decision_attempt",
            role="moderator",
            model=model,
            input_tokens=api_msg.usage.input_tokens,
            output_tokens=api_msg.usage.output_tokens,
            validation_fallback=False,
            source_function="call_moderator",
            token_accounting=True,
            metadata={
                "turn": trigger_event.turn_number,
                "attempt_number": 1,
                "parse_success": api_response is not None or error_type == "pydantic_validation_error",
                "validation_success": api_response is not None,
                "error_type": error_type,
                "error_message": correction if correction else None,
                # Opening turn only: keep a truncated copy of the raw assistant
                # text. This is the evidence that was missing when
                # initial_session_plan turned out never to have been captured —
                # no run in the project's history persisted the raw response, so
                # "did the model emit fences, or omit the key?" could not be
                # answered from logs. The head of the response is enough to see
                # both (fences appear at char 0; the plan key is first in the
                # template). Deliberately NOT stored for ordinary turns, where it
                # would duplicate transcript.json on every call.
                **({"raw_response_head": raw_text[:_RAW_LOG_HEAD_CHARS],
                    "raw_response_total_chars": len(raw_text)}
                   if is_opening_turn else {}),
            }
        )

    if api_response is None:
        # Append the failed assistant turn so the retry prompt has context
        history.append({"role": "assistant", "content": raw_text})
        history.append({"role": "user", "content": correction})

        api_msg = _call_api(client, system_prompt, history, model=model, max_tokens=max_tokens, log_dir=log_dir)
        raw_text = api_msg.content[0].text
        api_response, retry_error, retry_error_type = _try_parse(raw_text)
        
        if log_dir is not None:
            append_api_log(
                log_dir=log_dir,
                event_type="moderator_decision_retry_attempt",
                role="moderator",
                model=model,
                input_tokens=api_msg.usage.input_tokens,
                output_tokens=api_msg.usage.output_tokens,
                validation_fallback=False,
                source_function="call_moderator",
                token_accounting=True,
                metadata={
                    "turn": trigger_event.turn_number,
                    "attempt_number": 2,
                    "parse_success": api_response is not None or retry_error_type == "pydantic_validation_error",
                    "validation_success": api_response is not None,
                    "error_type": retry_error_type,
                    "error_message": retry_error if retry_error else None
                }
            )

        if api_response is None:
            # Both attempts failed — substitute a safe fallback and flag the turn
            logger.warning(
                "[RESEARCH ALERT] Turn %d: Moderator validation fallback fired. "
                "Original error: %s. "
                "This turn's action was substituted and is flagged in moderator_log.json.",
                trigger_event.turn_number,
                retry_error,
            )
            api_response = _build_fallback_response()
            # Return history without appending the second bad response — the fallback
            # utterance represents what actually happened in the session record
            history.append({"role": "assistant", "content": api_response.utterance})
            if log_dir is not None:
                append_api_log(
                    log_dir=log_dir,
                    event_type="moderator_decision_fallback",
                    role="moderator",
                    moderator_action=safe_enum_value(api_response.moderator_decision.action),
                    intervention_mode=safe_enum_value(api_response.moderator_decision.intervention_mode),
                    validation_fallback=True,
                    source_function="call_moderator",
                    token_accounting=False,
                    metadata={"turn": trigger_event.turn_number}
                )
            return api_response, history

    history.append({"role": "assistant", "content": raw_text})

    if log_dir is not None:
        append_api_log(
            log_dir=log_dir,
            event_type="moderator_decision",
            role="moderator",
            model=model,
            moderator_action=safe_enum_value(api_response.moderator_decision.action),
            intervention_mode=safe_enum_value(api_response.moderator_decision.intervention_mode),
            validation_fallback=False,
            source_function="call_moderator",
            token_accounting=False,
            metadata={"turn": trigger_event.turn_number}
        )

    return api_response, history


def run_moderator_reflection(
    state: SessionState,
    transcript_slice: list[dict] | None = None,
    log_dir: Path | None = None,
) -> ModeratorReflection | None:
    """
    Run one moderator reflection call: two short, fresh LLM summaries
    (discussion_summary, strategy_summary — see ModeratorReflection),
    covering the section that just ended.

    Only ever invoked by the orchestrator when
    session_meta.moderator_reflection_enabled is True, and ONLY at
    section/question boundaries (core/orchestrator.py fires this when the
    moderator's action was SECTION_TRANSITION) — not on a turn-count
    cadence. A handful of calls per session.

    2026-06-30 cost fix (Part 3): transcript_slice is the orchestrator-computed
    since-last-reflection slice (entries since the PRIOR section-transition
    boundary, not the full session) — replacing the earlier full-`state.transcript`
    approach, which was the single worst per-call token-growth slope measured
    in docs/findings/2026-06-30_full_session_token_growth_issue.md (2,175 ->
    32,655 tokens over just 6 calls in the killed smoke test). transcript_slice
    defaults to None for backward compatibility; when None, falls back to the
    full state.transcript (the old behavior) so any external caller that
    hasn't been updated still works, but the orchestrator always passes the
    slice explicitly now.

    Continuity without re-reading: the PRIOR accumulated summaries
    (state.group_state.section_summaries, Part 0) are fed back in as their
    own block, so this call has continuity awareness of earlier sections
    without needing their verbatim text. The first-ever reflection has no
    prior summaries and no prior boundary, so its slice is "everything since
    session start" — identical to the old full-transcript behavior at that
    one point, which is correct (nothing to compress yet).

    One-channel rule: this call does NOT ask for or receive coverage or
    participation-balance — both already reach the moderator via
    DiscussionGuideSection.completed and GroupState's existing participation
    fields respectively (restating them here would be derived-signal
    duplication). It also does NOT receive moderator_log (the moderator's
    own past justifications) — only transcript content, so each summary is
    regenerated fresh rather than recycled from prior reasoning (that path
    was considered and abandoned — see docs/changes/2026-06-30_moderator_dedup_A_reflection.md).

    Moderator turn-share (Piece 1) is NOT computed or requested here — it is
    a deterministic GroupState field (session_state.py,
    apply_moderator_response) surfaced to the moderator's regular per-turn
    prompt independently of this call.

    Separate, lightweight, single-attempt call (not the main per-turn
    decision call): additive, not safety-critical. On any parse/validation
    failure this returns None and logs a warning rather than retrying or
    substituting a fallback — the calling turn proceeds with no reflection
    injected this cycle, exactly as if the boundary hadn't fired.
    """
    transcript_to_send = transcript_slice if transcript_slice is not None else state.transcript

    prior_summaries = state.group_state.section_summaries
    if prior_summaries:
        prior_summaries_text = "\n\n".join(
            f"Section {s.section_index} ({s.section_label}):\n"
            f"- Discussion: {s.discussion_summary}\n"
            f"- Moderator approach: {s.strategy_summary}"
            for s in prior_summaries
        )
    else:
        prior_summaries_text = "(None yet — this is the first section.)"

    user_message = render_reflection_message({
        "PRIOR_SUMMARIES": prior_summaries_text,
        "TRANSCRIPT": json.dumps(transcript_to_send, indent=2, default=str),
    })

    client = anthropic.Anthropic()
    model = state.session_meta.moderator_model

    try:
        api_msg = call_with_rate_limit_retry(
            lambda: client.messages.create(
                model=model,
                max_tokens=_REFLECTION_MAX_TOKENS,
                temperature=1.0,
                messages=[{"role": "user", "content": user_message}],
            ),
            log_dir=log_dir,
            source_function="run_moderator_reflection",
            role="moderator",
            model=model,
        )
        raw_text = strip_markdown_fences(api_msg.content[0].text)
        reflection = ModeratorReflection.model_validate(json.loads(raw_text))
    except Exception as exc:
        logger.warning(
            "[moderator reflection] call/parse failed, skipping this cycle: %s", exc
        )
        if log_dir is not None:
            append_api_log(
                log_dir=log_dir,
                event_type="moderator_reflection_failed",
                role="moderator",
                model=model,
                validation_fallback=False,
                source_function="run_moderator_reflection",
                token_accounting=False,
                metadata={"turn": state.session_meta.total_turns, "error": str(exc)},
            )
        return None

    for field_name in ("discussion_summary", "strategy_summary"):
        word_count = len(getattr(reflection, field_name).split())
        if word_count > 80:
            logger.warning(
                "[moderator reflection] %s exceeded the 80-word target (%d words) at turn %d — kept as-is, not truncated.",
                field_name, word_count, state.session_meta.total_turns,
            )

    if log_dir is not None:
        append_api_log(
            log_dir=log_dir,
            event_type="moderator_reflection",
            role="moderator",
            model=model,
            input_tokens=api_msg.usage.input_tokens,
            output_tokens=api_msg.usage.output_tokens,
            validation_fallback=False,
            source_function="run_moderator_reflection",
            token_accounting=True,
            metadata={
                "turn": state.session_meta.total_turns,
                "transcript_slice_entries": len(transcript_to_send),
                "prior_summaries_count": len(prior_summaries),
            },
        )

    return reflection


def _state_to_session_config(state: SessionState) -> dict:
    """Convert SessionState back into the session_config dict shape for the opening prompt."""
    meta = state.session_meta
    return {
        "session_id": meta.id,
        "research_objective": meta.research_objective,
        "topic_domain": meta.topic_domain,
        "participant_collective_identity": meta.participant_collective_identity,
        "moderator_knowledge_brief": meta.moderator_knowledge_brief,
        "researcher_notes": meta.researcher_notes,
        "participants": [
            {
                "id": p.id,
                "name": p.name,
                "profile_summary": p.profile_summary,
            }
            for p in state.participants.values()
        ],
        "discussion_guide": [
            {
                "section_index": s.section_index,
                "section_label": s.section_label,
                "section_phase": s.section_phase.value,
                "section_purpose": s.section_purpose,
                "scripted_question": s.scripted_question,
                # probing_depth_ceiling is deliberately omitted. It is pinned to
                # None for every run (see orchestrator._build_state_from_config),
                # so emitting it would show the moderator a documented parameter
                # that is always null and steers nothing.
                "stimulus": s.stimulus.model_dump() if s.stimulus else None,
            }
            for s in state.discussion_guide
        ],
    }
