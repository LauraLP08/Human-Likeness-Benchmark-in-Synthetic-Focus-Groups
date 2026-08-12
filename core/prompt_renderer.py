"""
Renders prompt templates into strings ready for Anthropic API calls.
Reads prompt files from disk on every call so edits take effect without restart.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from core.session_state import DominantSignal, SectionPhase, SessionState, TriggerEvent, count_words

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _read_prompt(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text(encoding="utf-8")


def load_system_prompt(restraint_enabled: bool = False, prompt_override_filename: str | None = None) -> str:
    """
    Return 01_MODERATOR_SYSTEM_PROMPT.md with comment-header lines stripped.

    restraint_enabled (default False, matching session_meta.moderator_restraint_prompt's
    default): when True, splices in 05_MODERATOR_RESTRAINT_BLOCK.md's content
    immediately before the "## YOUR TWO-LAYER OUTPUT" heading. When False
    (the default), the returned text is byte-identical to before this
    parameter existed — 05_MODERATOR_RESTRAINT_BLOCK.md is never even read.

    prompt_override_filename (default None, matching session_meta.
    moderator_prompt_override's default — INSTRUCTIONS_SANDBOX_MINIMAL_
    MODERATOR_PILOT.md): when given, read that filename from prompts/
    instead of 01_MODERATOR_SYSTEM_PROMPT.md, applying the same
    comment-header stripping and restraint-block splicing logic. When None
    (every existing call site), behavior is byte-identical to before this
    parameter existed.
    """
    source_filename = prompt_override_filename or "01_MODERATOR_SYSTEM_PROMPT.md"
    lines = _read_prompt(source_filename).splitlines()
    # Strip lines that begin with '#' (the file-level comment header block at the top)
    # Stop stripping once we hit the first non-comment, non-blank line that isn't a header
    content_lines: list[str] = []
    in_header = True
    for line in lines:
        stripped = line.strip()
        if in_header and (stripped.startswith("#") or stripped == "" or stripped == "---"):
            continue
        in_header = False
        content_lines.append(line)
    base = "\n".join(content_lines)

    if not restraint_enabled:
        return base

    # The restraint block's own body starts with a markdown "##" heading, so the
    # generic comment-header stripper above (which treats ANY '#'-prefixed line as
    # header, including markdown headings) cannot be reused here — it would strip
    # the heading along with the real file-level comment block. Split on the first
    # '---' separator instead: everything before it is the file-level comment
    # header (Usage/rationale notes), everything after is the actual block.
    restraint_raw = _read_prompt("05_MODERATOR_RESTRAINT_BLOCK.md")
    _, _, restraint_body = restraint_raw.partition("\n---\n")
    restraint_block = restraint_body.strip()

    anchor = "## YOUR TWO-LAYER OUTPUT"
    if anchor not in base:
        # Defensive fallback: anchor heading missing (e.g. system prompt restructured) —
        # append at the end rather than silently dropping the restraint block.
        return base + "\n\n---\n\n" + restraint_block
    head, _, tail = base.partition(anchor)
    return head + restraint_block + "\n\n---\n\n" + anchor + tail


def render_opening_message(
    session_config: dict[str, Any],
    opening_prompt_override_filename: str | None = None,
) -> str:
    """
    Render 03_SESSION_OPENING_PROMPT.md with SESSION_CONFIG substituted.

    opening_prompt_override_filename (default None, matching session_meta.
    moderator_opening_prompt_override's default — INSTRUCTIONS_SANDBOX_
    MINIMAL_MODERATOR_PILOT.md): when given, read that filename from
    prompts/ instead of 03_SESSION_OPENING_PROMPT.md. When None (every
    existing call site), behavior is byte-identical to before this
    parameter existed.
    """
    source_filename = opening_prompt_override_filename or "03_SESSION_OPENING_PROMPT.md"
    template = _read_prompt(source_filename)
    config_json = json.dumps(session_config, indent=2)
    return template.replace("{SESSION_CONFIG}", config_json)


def render_reflection_message(substitutions: dict[str, str]) -> str:
    """
    Render 06_MODERATOR_REFLECTION_PROMPT.md with the given {PLACEHOLDER: value}
    substitutions. Only ever called when session_meta.moderator_reflection_enabled
    is True (core/orchestrator.py decides cadence; core/moderator_brain.py
    builds the substitutions and calls this).
    """
    template = _read_prompt("06_MODERATOR_REFLECTION_PROMPT.md")
    rendered = template
    for key, value in substitutions.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


# ---------------------------------------------------------------------------
# Phase modifier and special-case block parsing
# ---------------------------------------------------------------------------

def _parse_phase_modifiers() -> dict[str, str]:
    """
    Parse 04_PHASE_MODIFIERS_AND_SPECIAL_CASES.md and return a dict of
    { block_name -> block_text } extracted from fenced code blocks under
    each ### header that contains a backtick-delimited name.

    Uses a line-by-line approach so Windows vs Unix line endings don't matter.
    """
    raw = _read_prompt("04_PHASE_MODIFIERS_AND_SPECIAL_CASES.md")
    lines = raw.splitlines()

    blocks: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # Look for ### headers that have a backtick-delimited name
        if line.startswith("### ") and "`" in line:
            name_match = re.search(r"`([^`]+)`", line)
            if name_match:
                name = name_match.group(1).strip()
                # Scan forward to find the opening ``` fence
                j = i + 1
                while j < len(lines) and not lines[j].startswith("```"):
                    j += 1
                if j < len(lines):
                    # j is on the opening fence line — collect content lines
                    j += 1
                    content_lines: list[str] = []
                    while j < len(lines) and not lines[j].startswith("```"):
                        content_lines.append(lines[j])
                        j += 1
                    blocks[name] = "\n".join(content_lines)
                    i = j  # resume after closing fence
                    continue
        i += 1

    return blocks


# Cache-free: re-parsed on each call per the constraint "read from disk at call time"
def _get_phase_modifier(phase: SectionPhase) -> str:
    blocks = _parse_phase_modifiers()
    return blocks.get(phase.value, "")


def _get_injection_block(condition_key: str) -> str:
    blocks = _parse_phase_modifiers()
    # Try direct match first, then partial match
    if condition_key in blocks:
        return blocks[condition_key]
    for key, val in blocks.items():
        if condition_key in key:
            return val
    return ""


# ---------------------------------------------------------------------------
# Variable substitution helpers for special-case injections
# ---------------------------------------------------------------------------

def _build_consensus_injection(state: SessionState) -> str:
    block = _get_injection_block("consensus_risk >= 0.65")
    score = state.group_state.consensus_risk
    summary = ", ".join(state.group_state.group_has_agreed_easily_on) or "recent discussion topics"
    block = block.replace("{CONSENSUS_RISK_SCORE}", str(score))
    block = block.replace("{CONSENSUS_SUMMARY}", summary)
    return block.strip()


def _pick_silent_participant(state: SessionState) -> str | None:
    """
    Choose WHICH under-participating participant the moderator gets nudged
    toward. Returns None when there are no silent participants.

    Previously this was simply `silent_participants[0]`, and that list is
    built in config insertion order (session_state.py's silent_participants
    update), so the config-first participant under the 15% threshold was
    named every single time — regardless of whether someone else in the same
    list had spoken even less. Same bug class as the emergent tie-break fixed
    in run_conversation_step().

    Now: lowest turn_count wins, which is the actual signal we care about.
    A genuine tie on turn_count is broken with a seeded random pick rather
    than list position, so ties don't quietly reintroduce config-order bias.
    Seeding on (session_id, total_turns) keeps a run reproducible; the
    ":silent_pick" suffix keeps this stream independent of the speaker-
    selection shuffle that uses the same two values.

    Note `random.Random(str)` seeds from the string's bytes, not from the
    per-process-randomised hash(), so this is stable across processes.
    """
    candidates = list(state.group_state.silent_participants)
    if not candidates:
        return None

    def _turn_count(pid: str) -> int:
        participant = state.participants.get(pid)
        return participant.turn_count if participant else 0

    fewest = min(_turn_count(pid) for pid in candidates)
    tied = [pid for pid in candidates if _turn_count(pid) == fewest]
    if len(tied) == 1:
        return tied[0]

    # Sort the tied set so the choice depends only on WHICH participants are
    # tied, never on the order they happened to arrive in the list.
    tied.sort()
    rng = random.Random(
        f"{state.session_meta.id}:{state.session_meta.total_turns}:silent_pick"
    )
    return rng.choice(tied)


def _build_participation_injection(state: SessionState) -> str:
    block = _get_injection_block("participation_imbalance")
    pid = _pick_silent_participant(state)
    if pid is None:
        return ""
    participant = state.participants.get(pid)
    name = participant.name if participant else pid
    turn_count = participant.turn_count if participant else 0
    total = sum(p.turn_count for p in state.participants.values())
    avg = round(total / len(state.participants), 1) if state.participants else 0
    block = block.replace("{SILENT_PARTICIPANT_NAME}", name)
    block = block.replace("{SILENT_TURN_COUNT}", str(turn_count))
    block = block.replace("{AVERAGE_TURNS}", str(avg))
    return block.strip()


def _build_contradiction_injection(
    state: SessionState, trigger_event: TriggerEvent
) -> str:
    block = _get_injection_block("unresolved_contradiction_due")
    speaker_id = trigger_event.speaker_id
    if not speaker_id:
        return ""
    for tension in state.group_state.unresolved_tensions:
        if (
            not tension.resolved
            and tension.participant_id == speaker_id
            and (trigger_event.turn_number - tension.flagged_at_turn) >= 3
        ):
            participant = state.participants.get(speaker_id)
            name = participant.name if participant else speaker_id
            b = block.replace("{PARTICIPANT_NAME}", name)
            b = b.replace("{FLAGGED_TURN}", str(tension.flagged_at_turn))
            b = b.replace("{CONTRADICTION_DESCRIPTION}", tension.description)
            return b.strip()
    return ""


def _build_over_probe_injection(
    state: SessionState, trigger_event: TriggerEvent
) -> str:
    block = _get_injection_block("over_probe_warning")
    speaker_id = trigger_event.speaker_id
    participant = state.participants.get(speaker_id) if speaker_id else None
    name = participant.name if participant else (speaker_id or "the participant")
    count = trigger_event.follow_up_count_this_question
    block = block.replace("{PARTICIPANT_NAME}", name)
    block = block.replace("{FOLLOW_UP_COUNT}", str(count))
    return block.strip()


def _build_emotional_injection(
    state: SessionState, trigger_event: TriggerEvent
) -> str:
    block = _get_injection_block("emotional_register_elevated")
    speaker_id = trigger_event.speaker_id
    if not speaker_id:
        return ""
    participant = state.participants.get(speaker_id)
    name = participant.name if participant else speaker_id
    signal = (participant.emotional_signal if participant else None) or "elevated emotional content"
    block = block.replace("{PARTICIPANT_NAME}", name)
    block = block.replace("{EMOTIONAL_SIGNAL_SUMMARY}", signal)
    return block.strip()


def _build_section_transition_injection(state: SessionState) -> str:
    block = _get_injection_block("section_transition_check")
    label = state.current_section.section_label
    block = block.replace("{SECTION_LABEL}", label)
    return block.strip()


def _build_section_budget_status(state: SessionState) -> str:
    """
    Render the {SECTION_BUDGET_STATUS} line's content (without the leading
    "- " bullet marker — render_turn_message owns that). Only ever called
    when session_meta.time_budget_tracking_enabled is True.

    Sandbox mechanism (INSTRUCTIONS_SANDBOX_MINIMAL_MODERATOR_PILOT.md §4):
    reports this section's words/turns used against the budget the
    moderator itself produced at session open
    (session_meta.initial_session_plan["time_budget"]), plus an
    elapsed-minutes estimate. The elapsed-minutes rate is DERIVED from the
    model's own plan (total_word_budget / total_minutes) rather than a
    hardcoded Python constant — this is "the same rate used for planning"
    regardless of which words-per-minute figure the active opening prompt
    (production ~100/min vs sandbox ~112/min) used to produce that plan, so
    the two can never drift out of sync.
    """
    plan = state.session_meta.initial_session_plan
    time_budget = plan.get("time_budget") if isinstance(plan, dict) else None
    if not isinstance(time_budget, dict):
        return "(time budget not yet available)"

    total_minutes = time_budget.get("total_minutes")
    total_word_budget = time_budget.get("total_word_budget")
    per_section = time_budget.get("per_section") or []
    section_entry = next(
        (s for s in per_section if s.get("section_index") == state.session_meta.current_section_index),
        None,
    )
    word_budget = section_entry.get("word_budget") if section_entry else None
    turn_budget = section_entry.get("turn_budget") if section_entry else None
    label = state.current_section.section_label

    words_used = sum(state.group_state.section_word_counts.values())
    turns_used = sum(state.group_state.section_turn_counts.values())
    session_total_words = sum(count_words(entry.get("content", "")) for entry in state.transcript)

    if total_minutes and total_word_budget:
        rate = total_word_budget / total_minutes
        elapsed_min = round(session_total_words / rate, 1) if rate > 0 else 0.0
    else:
        elapsed_min = 0.0

    return (
        f"This section ('{label}') has used {words_used}/{word_budget} words "
        f"across {turns_used}/{turn_budget} turns. Session total: ~{elapsed_min} "
        f"of {total_minutes} minutes estimated elapsed."
    )


def _build_reflection_injection(state: SessionState) -> str:
    """
    Render the MOST RECENT reflection summary (if any) as a compact block,
    placed BEFORE the full transcript in the rendered message (abstraction
    before detail — see render_turn_message). Only ever non-empty when
    moderator_reflection_enabled=True AND at least one section/question
    boundary has produced a reflection — see core/orchestrator.py for the
    cadence.

    ONLY called when session_meta.moderator_context_mode == "full" (see
    render_turn_message) — in "summarized" mode (2026-06-30 cost fix, Part
    1), ALL accumulated section_summaries already reach the moderator via
    {SESSION_STATE}'s completed_section_summaries key
    (SessionState.to_prompt_json), so this block would be a duplicate
    delivery of the same content and is skipped entirely in that mode.

    One-channel rule: deliberately renders ONLY the two LLM summaries
    (discussion_summary, strategy_summary) — no coverage, no participation
    balance (both already reach the moderator via other fields elsewhere in
    the same prompt; restating them here would be duplication). Moderator
    turn-share is also not rendered here — it travels with the other
    GroupState participation fields inside {SESSION_STATE}, not in this block.
    """
    summaries = state.group_state.section_summaries
    if not summaries:
        return ""
    refl = summaries[-1]
    lines = [
        "## YOUR LAST REFLECTION (read this first, before the transcript below)",
        "",
        "(Two short, freshly-regenerated summaries from your last pause-and-reflect step — not a record of what was said. They will be refreshed at the next section boundary.)",
        "",
        f"- Discussion so far (thematic): {refl.discussion_summary}",
        f"- Your approach so far: {refl.strategy_summary}",
    ]
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_turn_message(
    state: SessionState,
    trigger_event: TriggerEvent,
    compress_before_turn: int | None = None,
) -> str:
    """Render 02_USER_MESSAGE_TEMPLATE.md with full substitutions + injections."""
    template = _read_prompt("02_USER_MESSAGE_TEMPLATE.md")

    phase = state.session_meta.section_phase
    phase_modifier = _get_phase_modifier(phase)

    rendered = template
    rendered = rendered.replace("{SESSION_STATE}", state.to_prompt_json(compress_before_turn))
    rendered = rendered.replace("{TRIGGER_EVENT}", trigger_event.model_dump_json(indent=2))
    rendered = rendered.replace("{FOLLOW_UP_COUNT}", str(trigger_event.follow_up_count_this_question))
    rendered = rendered.replace("{SECTION_PHASE}", phase.value)
    rendered = rendered.replace("{PHASE_MODIFIER}", phase_modifier)

    # {SECTION_BUDGET_STATUS}: sandbox mechanism, default off. When disabled
    # (every existing config), the whole bullet line — marker, placeholder,
    # and its own newline — is removed, not just the placeholder text, so
    # there is no leftover empty bullet and output is byte-identical to
    # before this feature existed. See INSTRUCTIONS_SANDBOX_MINIMAL_
    # MODERATOR_PILOT.md §4.
    if state.session_meta.time_budget_tracking_enabled:
        budget_status = _build_section_budget_status(state)
        rendered = rendered.replace("- {SECTION_BUDGET_STATUS}\n", f"- {budget_status}\n")
    else:
        rendered = rendered.replace("- {SECTION_BUDGET_STATUS}\n", "")

    # Build active special-case injections in defined order
    injections: list[str] = []

    if state.group_state.consensus_risk >= 0.65:
        injections.append(_build_consensus_injection(state))

    if (
        len(state.group_state.silent_participants) > 0
        and state.session_meta.section_phase != SectionPhase.INTRO
    ):
        injections.append(_build_participation_injection(state))

    contradiction_block = _build_contradiction_injection(state, trigger_event)
    if contradiction_block:
        injections.append(contradiction_block)

    if trigger_event.follow_up_count_this_question >= 3:
        injections.append(_build_over_probe_injection(state, trigger_event))

    if (
        trigger_event.speaker_id is not None
        and trigger_event.speaker_id in state.participants
        and state.participants[trigger_event.speaker_id].emotional_signal is not None
    ):
        injections.append(_build_emotional_injection(state, trigger_event))

    # section_transition_check: all participants have turn_count > 0 in current section
    section_counts = state.group_state.section_turn_counts
    all_spoken_in_section = all(
        section_counts.get(pid, 0) > 0 for pid in state.participants
    )
    if all_spoken_in_section and state.session_meta.current_question_index > 0:
        injections.append(_build_section_transition_injection(state))

    if state.group_state.consecutive_silent_turns >= 4:
        block = _get_injection_block("consecutive_silent_turns >= 4")
        injections.append(block.strip())

    emotional_signal_count = sum(1 for p in state.participants.values() if p.emotional_signal is not None)
    if (state.moderator_log and state.moderator_log[-1].trigger == DominantSignal.CONFLICT_DETECTED) or emotional_signal_count >= 2:
        block = _get_injection_block("conflict_detected")
        if block:
            injections.append(block.strip())

    if injections:
        rendered += "\n\n" + "\n\n".join(injections)

    # Reflection prefix: PREPENDED, not appended — per spec, the moderator
    # reads the two summaries FIRST, then the full transcript (abstraction
    # before detail), so this goes before the entire rendered message
    # (which contains {SESSION_STATE}, and the full transcript inside it),
    # not into the trailing injections block above. Only ever non-empty
    # when moderator_reflection_enabled=True AND a reflection has run
    # (state.group_state.section_summaries is non-empty). When the toggle is
    # off, section_summaries stays empty and this is a no-op, so
    # render_turn_message's output is byte-identical to before this
    # feature existed.
    #
    # ONLY fires in moderator_context_mode="full" (2026-06-30 cost fix, Part
    # 1). In "summarized" mode, ALL accumulated section_summaries already
    # reach the moderator via {SESSION_STATE}'s completed_section_summaries
    # key (already inside `rendered` via to_prompt_json) — prepending this
    # block too would deliver the same content twice.
    if (
        state.session_meta.moderator_reflection_enabled
        and state.session_meta.moderator_context_mode == "full"
    ):
        reflection_block = _build_reflection_injection(state)
        if reflection_block:
            rendered = reflection_block + "\n\n---\n\n" + rendered

    return rendered
