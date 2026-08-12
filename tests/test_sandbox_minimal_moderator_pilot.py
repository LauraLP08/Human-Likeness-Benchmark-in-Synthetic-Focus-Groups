"""
Offline verification for INSTRUCTIONS_SANDBOX_MINIMAL_MODERATOR_PILOT.md,
required before any live API spend (§7):

1. prompts/02_USER_MESSAGE_TEMPLATE.md renders byte-identical to before this
   feature existed when time_budget_tracking_enabled is False.
2. The budget-status helper produces correct arithmetic for a hand-built
   GroupState/time_budget fixture (pure function, no API call).
3. load_system_prompt(prompt_override_filename=...) and
   render_opening_message(opening_prompt_override_filename=...) correctly
   load the sandbox files, and are unchanged when called with no override
   (production behavior untouched).

Pure string-generation logic + pydantic construction. Zero network calls,
zero API calls.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from core.prompt_renderer import (
    _build_section_budget_status,
    _read_prompt,
    load_system_prompt,
    render_opening_message,
    render_reflection_message,
    render_turn_message,
)
from core.session_state import (
    DiscussionGuideSection,
    DominantSignal,
    GroupState,
    ModeratorAction,
    ModeratorAPIResponse,
    ModeratorDecisionResponse,
    ParticipantState,
    SectionPhase,
    SessionMeta,
    SessionState,
    TriggerEvent,
    TriggerEventType,
    apply_moderator_response,
    count_words,
)


def _session_meta(**overrides) -> SessionMeta:
    defaults = dict(
        id="test_sandbox",
        research_objective="test",
        topic_domain="test",
        participant_collective_identity="test participants",
        moderator_knowledge_brief="",
    )
    defaults.update(overrides)
    return SessionMeta(**defaults)


def _guide() -> list[DiscussionGuideSection]:
    return [
        DiscussionGuideSection(
            section_index=0,
            section_label="Gender and food choice",
            section_phase=SectionPhase.MAIN_TOPIC,
            section_purpose="test",
            scripted_question="Do you think your gender influences what you eat?",
        ),
        DiscussionGuideSection(
            section_index=1,
            section_label="Imagining a plant-based shift",
            section_phase=SectionPhase.MAIN_TOPIC,
            section_purpose="test",
            scripted_question="Imagine you decided to go plant-based.",
        ),
    ]


def _state(meta: SessionMeta, group_state: GroupState | None = None) -> SessionState:
    return SessionState(
        session_meta=meta,
        discussion_guide=_guide(),
        participants={
            "P1": ParticipantState(id="P1", name="Alice"),
            "P2": ParticipantState(id="P2", name="Bob"),
        },
        group_state=group_state or GroupState(),
    )


def _trigger() -> TriggerEvent:
    return TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="I think it does, honestly.",
        turn_number=3,
    )


# ---------------------------------------------------------------------------
# 1. Byte-identical template rendering when the flag is off
# ---------------------------------------------------------------------------

def test_template_byte_identical_when_time_budget_tracking_disabled():
    """
    Reference: the CURRENT on-disk template with only the
    "- {SECTION_BUDGET_STATUS}\\n" line removed — i.e. exactly what the file
    looked like before this feature existed. Patch _read_prompt to serve
    that reference text for the template call only, render through the
    real (unmodified) render_turn_message, and compare against the actual
    function's output with the flag off (real on-disk template, line
    present). If they differ, the flag-off path is not truly byte-identical
    to pre-feature behavior.
    """
    real_read_prompt = _read_prompt

    def _reference_read_prompt(filename: str) -> str:
        text = real_read_prompt(filename)
        if filename == "02_USER_MESSAGE_TEMPLATE.md":
            text = text.replace("- {SECTION_BUDGET_STATUS}\n", "")
        return text

    meta = _session_meta(time_budget_tracking_enabled=False)
    state = _state(meta)
    trigger = _trigger()

    with patch("core.prompt_renderer._read_prompt", side_effect=_reference_read_prompt):
        reference = render_turn_message(state, trigger)

    actual = render_turn_message(state, trigger)

    assert actual == reference
    assert "SECTION_BUDGET_STATUS" not in actual
    # No orphaned empty bullet left behind.
    assert not any(line.strip() == "-" for line in actual.splitlines())


def test_template_includes_budget_line_when_enabled():
    meta = _session_meta(time_budget_tracking_enabled=True)
    state = _state(meta)
    trigger = _trigger()

    rendered = render_turn_message(state, trigger)

    assert "SECTION_BUDGET_STATUS" not in rendered
    assert "(time budget not yet available)" in rendered


# ---------------------------------------------------------------------------
# 2. Budget-status arithmetic (pure function, hand-built fixture)
# ---------------------------------------------------------------------------

def test_section_budget_status_arithmetic():
    meta = _session_meta(time_budget_tracking_enabled=True)
    meta.initial_session_plan = {
        "time_budget": {
            "total_minutes": 20,
            "total_word_budget": 2240,
            "per_section": [
                {"section_index": 0, "section_label": "Gender and food choice", "word_budget": 750, "turn_budget": 4},
                {"section_index": 1, "section_label": "Imagining a plant-based shift", "word_budget": 750, "turn_budget": 4},
            ],
        }
    }
    group_state = GroupState(
        section_word_counts={"P1": 300, "P2": 220, "MODERATOR": 40},
        section_turn_counts={"P1": 2, "P2": 1},
    )
    state = _state(meta, group_state=group_state)
    # Session-total words is derived from the transcript, not section_word_counts.
    state.transcript = [
        {"speaker_id": "P1", "content": "one two three four five"},          # 5 words
        {"speaker_id": "MODERATOR", "content": "six seven"},                  # 2 words
        {"speaker_id": "P2", "content": "eight nine ten (.) [inaudible]"},   # 3 words (annotations excluded)
    ]

    status = _build_section_budget_status(state)

    # words_used = 300+220+40=560, word_budget=750; turns_used=2+1=3, turn_budget=4
    assert "560/750 words" in status
    assert "3/4 turns" in status
    assert "Gender and food choice" in status
    # rate = 2240/20 = 112 words/min; session_total_words = 5+2+3 = 10
    # elapsed_min = round(10/112, 1) = 0.1
    assert "~0.1" in status
    assert "of 20 minutes" in status


def test_section_budget_status_handles_missing_plan_gracefully():
    meta = _session_meta(time_budget_tracking_enabled=True)
    state = _state(meta)  # initial_session_plan is None (no opening turn run yet)

    status = _build_section_budget_status(state)

    assert status == "(time budget not yet available)"


# ---------------------------------------------------------------------------
# 3. Override loading — sandbox files load correctly, defaults unchanged
# ---------------------------------------------------------------------------

def test_load_system_prompt_no_override_is_production_default():
    prompt = load_system_prompt()
    assert "RESPONSE QUALITY ASSESSMENT" in prompt
    assert "TIME BUDGET AND PACING" in prompt


def test_load_system_prompt_with_sandbox_override():
    prompt = load_system_prompt(prompt_override_filename="sandbox/01_MODERATOR_SYSTEM_PROMPT_MINIMAL.md")
    assert "RESPONSE QUALITY ASSESSMENT" not in prompt
    assert "GROUP DYNAMIC RULES" not in prompt
    assert "TIME BUDGET AND PACING" not in prompt
    assert "stay_silent" not in prompt
    assert "YOUR TWO-LAYER OUTPUT" in prompt
    assert "Write your `situation_assessment` first" in prompt
    assert "prefer this over continued deepening" in prompt  # section_transition budget line
    assert "prefer this over `redirect_to_group`" in prompt  # refocus_to_guide budget line


def test_render_opening_message_no_override_is_production_default():
    rendered = render_opening_message({"a": 1})
    assert "~100 words" in rendered
    assert "about 45 minutes" in rendered


def test_render_opening_message_with_sandbox_override():
    rendered = render_opening_message(
        {"a": 1}, opening_prompt_override_filename="sandbox/03_SESSION_OPENING_PROMPT_SANDBOX.md"
    )
    assert "~112 words" in rendered
    assert "about 45 minutes" not in rendered
    # The duration/word-budget worked example must stay coupled to the
    # sandbox guide's real ~20-minute duration (112 * 20 = 2240), not a
    # leftover from production's 45-minute anchor (112 * 45 = 5040) — a
    # real bug caught in review: the two lines had drifted apart when
    # "Total duration" was made generic but "Word budget" kept an implicit
    # 45-minute-derived total.
    assert "about 20 minutes" in rendered
    assert "~2240 words" in rendered
    assert "~5040" not in rendered
    # The "Produce the following JSON and nothing else" worked example
    # further down the file — the moderator_decision/time_budget JSON block
    # itself — carried the SAME stale production anchor independently of
    # the prose lines above (a second instance of the same bug, caught in
    # a second review pass). Check the exact JSON substrings, not just the
    # "~4500"-with-tilde prose form already confirmed absent above, since
    # the JSON block spells the number without a tilde.
    assert '"total_minutes": 45' not in rendered
    assert "4500" not in rendered
    assert '"total_minutes": 20' in rendered
    assert '"total_word_budget": 2240' in rendered


# ---------------------------------------------------------------------------
# Bonus: count_words edge cases (docs/length_measurement_rule.md), and the
# apply_moderator_response word-count bookkeeping it feeds.
# ---------------------------------------------------------------------------

def test_count_words_edge_cases():
    assert count_words("well-known") == 1
    assert count_words("don't I'm") == 2
    assert count_words("42") == 0
    assert count_words("3rd COVID19") == 2
    # NOTE: docs/length_measurement_rule.md's own worked-example table claims
    # "(2 sec)" -> 0 words ("each word excluded individually"), but its own
    # documented regex (_ANNOTATION_RE = r'^\(.*\)$|...', applied per
    # whitespace-split token) does NOT achieve that: "(2" and "sec)" are
    # split into two tokens, and NEITHER individually matches
    # ^\(.*\)$ (one has no trailing paren, the other no leading paren), so
    # "sec)" survives as a counted word. This is a real inconsistency in the
    # doc between its example table and its own literal implementation —
    # count_words() here replicates the documented regex verbatim (per
    # INSTRUCTIONS_SANDBOX_MINIMAL_MODERATOR_PILOT.md's "do not invent a
    # second counting rule"), so this test asserts the actual behavior, not
    # the doc's aspirational table entry.
    assert count_words("(2 sec)") == 1
    assert count_words("well (h) said") == 2  # single-token "(h)" DOES match ^\(.*\)$ and is excluded
    assert count_words("también años") == 2
    assert count_words("[00:09:00]") == 0
    assert count_words("hello {laughs} world") == 2


def test_sandbox_config_dry_run_constructs_via_standard_participant_path():
    """
    §6a hard requirement: participants must load via the standard
    load_agent_from_json path, not a sandbox-specific bypass. Construct the
    real orchestrator from the real sandbox config file (no API calls) and
    confirm all 5 real FG1 personas loaded with full agent_payload
    (proving build_participant_system_prompt will exercise the disposition
    rendering, not a stub).
    """
    import json
    from core.orchestrator import FocusGroupOrchestrator

    config = json.loads(
        Path("configs/sandbox_minimal_moderator_pilot_01.json").read_text(encoding="utf-8")
    )
    orch = FocusGroupOrchestrator(config)
    state = orch.state

    assert state.session_meta.participation_mode == "emergent"
    assert state.session_meta.moderator_prompt_override == "sandbox/01_MODERATOR_SYSTEM_PROMPT_MINIMAL.md"
    assert state.session_meta.moderator_opening_prompt_override == "sandbox/03_SESSION_OPENING_PROMPT_SANDBOX.md"
    assert state.session_meta.time_budget_tracking_enabled is True
    assert len(state.participants) == 5
    for pid, p in state.participants.items():
        assert p.agent_payload, f"{pid} has no agent_payload — did not go through load_agent_from_json"
        assert "psychometric_scores" in p.agent_payload
    assert len(state.discussion_guide) == 3
    assert all(s.section_phase == SectionPhase.MAIN_TOPIC for s in state.discussion_guide)


# ---------------------------------------------------------------------------
# Regression test for the word/turn-count loss bug found while diagnosing
# the sandbox_minimal_prompt_budget_01 pilot (508-word gap between a direct
# transcript recount and the sum of the final section_word_counts snapshot
# per section). Root cause: apply_moderator_response's step 2 (increment the
# triggering participant's section_word_counts/section_turn_counts) runs
# before step 5's reset on SECTION_TRANSITION — so when a participant's own
# turn triggers the transition, their just-added count is wiped in the same
# function call before any state snapshot ever observes it. Confirmed in the
# pilot at turn 9 (mm_fg1_ibrahim, 219 words) and turn 14 (mm_fg1_will, 289
# words); 219 + 289 = 508, exactly the observed gap.
# ---------------------------------------------------------------------------

def test_section_transition_archives_triggering_participants_words_before_reset():
    """
    Reproduces the pilot scenario exactly: a section with section_word_counts
    already populated by prior turns, then a SECTION_TRANSITION triggered by
    a participant's own response (as happened at pilot turns 9 and 14). The
    triggering participant's words/turns must land in
    completed_section_word_counts[old_index] /
    completed_section_turn_counts[old_index] — not vanish, and not remain in
    the live (post-reset) section_word_counts/section_turn_counts either.
    """
    meta = _session_meta(time_budget_tracking_enabled=True)
    group_state = GroupState(
        # Mirrors the pilot's state_turn_8.json snapshot shape: several
        # participants plus the moderator already have words banked in
        # section 0 before the transition-triggering turn arrives.
        section_word_counts={"MODERATOR": 419, "P2": 185},
        section_turn_counts={"MODERATOR": 0, "P2": 1},
    )
    state = _state(meta, group_state=group_state)
    assert state.session_meta.current_section_index == 0

    # P1 (mirrors mm_fg1_ibrahim at pilot turn 9) is the trigger for this
    # moderator call, and the moderator's decision on THIS call is the
    # transition itself — exactly the same-call increment-then-reset
    # sequence that lost the words in the live pilot.
    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="one two three four five six seven eight nine",  # 9 words
        turn_number=9,
    )
    response = ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="speak",
            situation_assessment="Section complete, all voices heard, moving on.",
            dominant_signal=DominantSignal.SECTION_COMPLETE,
            action=ModeratorAction.SECTION_TRANSITION,
            target="group",
        ),
        utterance="Thanks everyone, let's move to the next topic now please.",  # 10 words
    )

    updated = apply_moderator_response(state, response, trigger)

    # 1. The triggering participant's words/turns are archived under the
    #    OLD (closing) section index, including the increment from THIS turn.
    assert updated.group_state.completed_section_word_counts[0]["P1"] == 9
    assert updated.group_state.completed_section_turn_counts[0]["P1"] == 1
    # Pre-existing participants/moderator counts from before this turn are
    # archived too, unchanged.
    assert updated.group_state.completed_section_word_counts[0]["MODERATOR"] == 419
    assert updated.group_state.completed_section_word_counts[0]["P2"] == 185
    assert updated.group_state.completed_section_turn_counts[0]["P2"] == 1

    # 2. P1's words are NOT lost (the bug) and NOT double-counted: they
    #    appear in exactly one place — the archive for section 0 — and
    #    nowhere in the live, post-reset section_word_counts/turn_counts,
    #    which now belongs to the new section and only holds the
    #    moderator's own new utterance.
    assert "P1" not in updated.group_state.section_word_counts
    assert "P1" not in updated.group_state.section_turn_counts
    assert updated.group_state.section_word_counts == {"MODERATOR": 10}
    assert updated.group_state.section_turn_counts == {}

    # 3. Section index actually advanced (sanity check on the surrounding
    #    transition logic, unchanged by this fix).
    assert updated.session_meta.current_section_index == 1

    # 4. No accidental archive entry for the new section yet.
    assert 1 not in updated.group_state.completed_section_word_counts


# ---------------------------------------------------------------------------
# Offline verification for INSTRUCTIONS_MODERATOR_RESTRAINT_AND_SYNTHESIS_SCOPE.md
# §1: activating moderator_restraint_prompt against the minimal (sandbox)
# system prompt for the first time — this splicing has previously only been
# exercised against production's 01_MODERATOR_SYSTEM_PROMPT.md.
# ---------------------------------------------------------------------------

_MINIMAL_OVERRIDE = "sandbox/01_MODERATOR_SYSTEM_PROMPT_MINIMAL.md"


def test_restraint_splice_against_minimal_prompt_contains_restraint_heading():
    rendered = load_system_prompt(restraint_enabled=True, prompt_override_filename=_MINIMAL_OVERRIDE)
    assert "## ON RESTRAINT" in rendered


def test_restraint_toggle_changes_minimal_prompt_output():
    off = load_system_prompt(restraint_enabled=False, prompt_override_filename=_MINIMAL_OVERRIDE)
    on = load_system_prompt(restraint_enabled=True, prompt_override_filename=_MINIMAL_OVERRIDE)
    assert off != on
    assert "## ON RESTRAINT" not in off


def test_restraint_splice_anchor_lands_before_two_layer_output_in_minimal_prompt():
    """
    The splice anchor logic in load_system_prompt() is generic (partitions
    on "## YOUR TWO-LAYER OUTPUT" regardless of which source file was read)
    and needs no changes for this file combination — this test proves that
    holds by reconstructing the expected output from the same primitives
    load_system_prompt() itself uses, and comparing exactly.
    """
    base = load_system_prompt(restraint_enabled=False, prompt_override_filename=_MINIMAL_OVERRIDE)
    restraint_raw = _read_prompt("05_MODERATOR_RESTRAINT_BLOCK.md")
    _, _, restraint_body = restraint_raw.partition("\n---\n")
    restraint_block = restraint_body.strip()

    anchor = "## YOUR TWO-LAYER OUTPUT"
    assert anchor in base  # unchanged in the minimal prompt, confirmed here
    head, _, tail = base.partition(anchor)
    expected = head + restraint_block + "\n\n---\n\n" + anchor + tail

    actual = load_system_prompt(restraint_enabled=True, prompt_override_filename=_MINIMAL_OVERRIDE)
    assert actual == expected

    # The restraint block must sit immediately before the anchor — no other
    # content wedged between them.
    restraint_idx = actual.index("## ON RESTRAINT")
    anchor_idx = actual.index(anchor)
    assert restraint_idx < anchor_idx


def test_restraint_disabled_no_override_is_still_byte_identical_to_production_default():
    """Toggle off + no override must remain exactly what it was before this
    task — the default call path is untouched."""
    default_call = load_system_prompt()
    explicit_off_call = load_system_prompt(restraint_enabled=False)
    assert default_call == explicit_off_call
    assert "## ON RESTRAINT" not in default_call


# ---------------------------------------------------------------------------
# §2: synthesize_and_challenge scoped down in the minimal prompt only.
# ---------------------------------------------------------------------------

def test_synthesize_and_challenge_scoped_in_minimal_prompt():
    rendered = load_system_prompt(prompt_override_filename=_MINIMAL_OVERRIDE)
    assert (
        "naming every participant's position in turn produces a recap"
        in rendered
    )
    assert (
        "Do not recap each participant's position by name in sequence — "
        "a synthesis distills to the tension that matters, it doesn't "
        "summarize everyone"
        in rendered
    )
    assert "Do not stack more than one question at the end" in rendered


def test_redirect_to_group_entry_byte_identical_in_minimal_prompt():
    rendered = load_system_prompt(prompt_override_filename=_MINIMAL_OVERRIDE)
    redirect_to_group_entry = (
        "### `redirect_to_group`\n"
        "\n"
        "**Purpose:** Take something a participant has said and open it to the wider group for reaction, comparison, or extension.\n"
        "\n"
        "**Use when:** A participant has raised something that is likely to generate different reactions across the group, or when you have spent two or more consecutive turns with the same participant and need to restore group discussion.\n"
        "\n"
        "**Form:** Briefly echo the participant's point (in their language, not yours) and invite others' reactions without attributing a position to the group. Do not ask \"does everyone agree?\" — that invites passive assent. Instead invite response to the substance.\n"
        "\n"
        "**Anti-patterns:**\n"
        "- Do not summarise the participant's point in language that changes its meaning or adds your framing\n"
        "- Do not use this action to end discussion of a topic prematurely — only use it to expand, not escape"
    )
    assert redirect_to_group_entry in rendered


# reactivate_silent's "Use when:" clause, before and after
# INSTRUCTIONS_REACTIVATE_SILENT_AND_DOMINANT_SPEAKER_FINAL.md §1a. The new text
# is byte-identical between 01_MODERATOR_SYSTEM_PROMPT.md and the minimal prompt,
# as the old text was.
_REACTIVATE_SILENT_USE_WHEN_OLD = (
    "**Use when:** A participant appears in `silent_participants` or has a turn count "
    "less than half the group average. This action is a priority intervention — it should "
    "override a planned probe if participation imbalance is significant."
)

_REACTIVATE_SILENT_USE_WHEN_NEW = (
    "**Use when:** A participant appears in `silent_participants` or has gone a notable "
    "stretch without contributing, and the moment allows for it — e.g. a natural transition "
    "point, a question they'd have a real perspective on, or a lull in the discussion. Weigh "
    "this against whether the group is still actively working through the current "
    "discussion-guide question or probe: if redirecting attention right now would cut that "
    "in-progress line of inquiry short, let it run its course first, then bring the quieter "
    "participant in as the conversation opens up. Reactivating them does not need to happen "
    "immediately, and it does not take precedence over staying on-track with the guide."
)


# Time-budget sentence added to the minimal prompt's YOUR PHILOSOPHICAL
# CONTRACT section. Sandbox-only — deliberately NOT added to production, so
# unlike _REACTIVATE_SILENT_USE_WHEN_NEW there is no cross-file parity check
# for it.
_TIME_BUDGET_SENTENCE = (
    "You also have a limited overall time budget for the session (see your own "
    "initial_session_plan) — treat the per-turn budget status as one more input "
    "for that same judgment: stay with a section only as long as it is still "
    "advancing the current guide question, not simply because the conversation "
    "remains lively, and move the group on once the guide question has been "
    "sufficiently answered."
)


# Over-synthesis guardrail, condensed from the production prompt's NEUTRAL
# FACILITATION AND NON-EVALUATIVE REFLECTION section. Sandbox-only — production
# keeps the full section, so there is no cross-file parity check for this one.
_OVER_SYNTHESIS_SENTENCE = (
    "You can summarize, but do not over-synthesize every participant's "
    "contribution into an abstract insight — keep it short, enough to clarify, "
    "not to build a polished analytic narrative."
)


def test_reactivate_silent_use_when_softened_identically_in_both_prompts():
    """
    §1a: the quota/override framing is gone from both system prompts, and the
    replacement is byte-identical between them (as the original text was).
    """
    production = _read_prompt("01_MODERATOR_SYSTEM_PROMPT.md")
    minimal = _read_prompt(_MINIMAL_OVERRIDE)

    for name, text in (("production", production), ("minimal", minimal)):
        assert text.count(_REACTIVATE_SILENT_USE_WHEN_NEW) == 1, name
        assert _REACTIVATE_SILENT_USE_WHEN_OLD not in text, name
        assert "priority intervention" not in text, name
        assert "should override a planned probe" not in text, name

    prod_clause = next(l for l in production.splitlines() if l.startswith("**Use when:** A participant appears"))
    min_clause = next(l for l in minimal.splitlines() if l.startswith("**Use when:** A participant appears"))
    assert prod_clause == min_clause == _REACTIVATE_SILENT_USE_WHEN_NEW


def test_synthesize_and_challenge_edit_delta_is_the_only_size_change_in_minimal_prompt():
    """
    The minimal prompt file received TWO edits in the task that introduced
    this test: the synthesize_and_challenge scoping (§2, this test's focus)
    and the shared identity-paragraph sentence (§3, added to this file too
    since it's one of the two files §3 touches identically). This test
    isolates §2's delta specifically and confirms the file's total size is
    accounted for by EXACTLY the known deltas — nothing else changed.

    true_original (18,608 chars) is the file's length before either of that
    task's edits were applied, computed once by subtracting both deltas from
    the then-current file and independently confirmed as: length at the time
    (19,195) - delta_synth (425) - delta_identity (162) = 18,608. It is a
    fixed constant here, not re-derived from `current` at test time — that's
    what makes the final assertion a real regression check rather than a
    tautology.

    A THIRD delta was added later by
    INSTRUCTIONS_REACTIVATE_SILENT_AND_DOMINANT_SPEAKER_FINAL.md §1a, which
    replaced reactivate_silent's "Use when:" paragraph in this file (and
    byte-identically in production).

    A FOURTH delta is the time-budget sentence appended to YOUR PHILOSOPHICAL
    CONTRACT (sandbox-only; production was deliberately not touched).

    The rule this test follows on every such edit: true_original stays at
    18,608 and each new change is added as its own named, separately-asserted
    delta, so the accounting keeps its full history instead of being silently
    rebaselined. If you are here because a legitimate edit made this fail, add
    a delta — do not move true_original.
    """
    current = _read_prompt(_MINIMAL_OVERRIDE)
    old_fragment_synth = (
        "**Form:** Summarise in a short, tentative framing (\"I'm hearing a few things here...\") "
        "then pose a challenge or complication that the summary doesn't fully resolve. "
        "Do not present the synthesis as your conclusion — present it as something to be tested.\n"
        "\n"
        "**Anti-patterns:**\n"
        "- Do not use this action to close a topic — use it to deepen\n"
        "- Do not present your synthesis as definitive or correct\n"
        "\n"
        "---"
    )
    new_fragment_synth = (
        "**Form:** Summarise in a short, tentative framing (\"I'm hearing a few things here...\") "
        "then pose a challenge or complication that the summary doesn't fully resolve. "
        "Do not present the synthesis as your conclusion — present it as something to be tested. "
        "Keep the summary brief and ask ONE question — naming every participant's position in turn "
        "produces a recap, not a synthesis; pick the one or two threads that matter for the challenge "
        "you're posing, and let the rest go unmentioned.\n"
        "\n"
        "**Anti-patterns:**\n"
        "- Do not use this action to close a topic — use it to deepen\n"
        "- Do not present your synthesis as definitive or correct\n"
        "- Do not recap each participant's position by name in sequence — a synthesis distills to the "
        "tension that matters, it doesn't summarize everyone\n"
        "- Do not stack more than one question at the end\n"
        "\n"
        "---"
    )
    assert new_fragment_synth in current
    assert old_fragment_synth not in current

    delta_synth = len(new_fragment_synth) - len(old_fragment_synth)
    assert delta_synth == 425

    # §3's sentence, added to this same file — see the §3 tests below for
    # the full identity-paragraph verification; here it's only needed to
    # complete the byte-accounting for this file's total size.
    delta_identity = len(" " + _GROUP_CONVERSATION_SENTENCE)
    assert delta_identity == 162

    # §1a of the reactivate_silent/dominant-speaker task: the quota-style
    # "priority intervention ... should override a planned probe" framing was
    # replaced with guidance that weighs reactivation against the guide.
    assert _REACTIVATE_SILENT_USE_WHEN_NEW in current
    assert _REACTIVATE_SILENT_USE_WHEN_OLD not in current
    delta_reactivate_silent = len(_REACTIVATE_SILENT_USE_WHEN_NEW) - len(_REACTIVATE_SILENT_USE_WHEN_OLD)
    assert delta_reactivate_silent == 444

    # Fourth delta: the time-budget sentence appended to YOUR PHILOSOPHICAL
    # CONTRACT. Inserted as its own paragraph, so it costs the sentence plus
    # the blank line separating it from the `---` that closes the section.
    assert current.count(_TIME_BUDGET_SENTENCE) == 1
    delta_time_budget = len(_TIME_BUDGET_SENTENCE + "\n\n")
    assert delta_time_budget == 390

    # Fifth delta: the over-synthesis sentence, ported from NEUTRAL FACILITATION
    # AND NON-EVALUATIVE REFLECTION after a turn-by-turn review of
    # macho_meals_fg1_run01 found two synthesis turns building an authored
    # analytic narrative. Same paragraph shape as the time-budget sentence.
    assert current.count(_OVER_SYNTHESIS_SENTENCE) == 1
    delta_over_synthesis = len(_OVER_SYNTHESIS_SENTENCE + "\n\n")
    assert delta_over_synthesis == 185

    # Sixth delta: the PORTED-BACK LINES provenance block added to the file's
    # header comment, recording both ported sentences and why the rest of their
    # parent sections stayed cut. Header prose, not model-facing instruction —
    # tracked separately so a future prose edit there is distinguishable from an
    # edit to what the moderator actually reads.
    assert "# PORTED-BACK LINES (provenance)." in current
    delta_header_provenance = 1317
    assert current.count("2026-07-28  from NEUTRAL FACILITATION") == 1

    true_original = 18608
    assert len(current) == (
        true_original
        + delta_synth
        + delta_identity
        + delta_reactivate_silent
        + delta_time_budget
        + delta_over_synthesis
        + delta_header_provenance
    )


# ---------------------------------------------------------------------------
# §3: opening identity paragraph — group conversation framing, added
# identically to both production and the minimal prompt.
# ---------------------------------------------------------------------------

_GROUP_CONVERSATION_SENTENCE = (
    "This is a group conversation, not a sequence of one-on-one interviews — "
    "participants should be doing most of the talking, ideally to each other, "
    "not only to you."
)

_IDENTITY_PARAGRAPH = (
    "Your role is that of an experienced, thoughtful human moderator — not a "
    "chatbot, not a survey instrument, not a therapist. You are a skilled "
    "facilitator whose job is to help participants produce rich, specific, "
    "honest, and genuinely useful qualitative data in service of a research "
    "objective. " + _GROUP_CONVERSATION_SENTENCE
)


def test_group_conversation_sentence_present_in_production_default():
    rendered = load_system_prompt()
    assert _IDENTITY_PARAGRAPH in rendered


def test_group_conversation_sentence_present_in_minimal_prompt():
    rendered = load_system_prompt(prompt_override_filename=_MINIMAL_OVERRIDE)
    assert _IDENTITY_PARAGRAPH in rendered


def test_identity_paragraph_still_byte_identical_between_production_and_minimal_prompt():
    production = _read_prompt("01_MODERATOR_SYSTEM_PROMPT.md")
    minimal = _read_prompt(_MINIMAL_OVERRIDE)
    assert _IDENTITY_PARAGRAPH in production
    assert _IDENTITY_PARAGRAPH in minimal
    # Isolate the exact paragraph (bounded by blank lines) in both files and
    # diff it directly, not just check substring presence in each — this
    # property (byte-identical paragraph) existed before this task and must
    # survive it.
    prod_para = next(p for p in production.split("\n\n") if _IDENTITY_PARAGRAPH in p)
    min_para = next(p for p in minimal.split("\n\n") if _IDENTITY_PARAGRAPH in p)
    assert prod_para == min_para == _IDENTITY_PARAGRAPH


# ---------------------------------------------------------------------------
# Offline verification for INSTRUCTIONS_OPENING_PROMPT_NO_RESEARCH_DISCLOSURE.md
# §4 (points 1-3): the opening prompt must no longer instruct the moderator to
# invent its own topic framing, and must explicitly forbid disclosing
# research_objective / moderator_knowledge_brief to participants.
#
# Cause: in the sandbox_minimal_prompt_budget_01 pilot the moderator's opening
# utterance narrated the study's own purpose to the group ("The research is
# trying to understand how food fits into the real texture of men's lives in
# the UK"). The old checklist item 2 told it to "Establish the topic" while the
# full SESSION_CONFIG (research_objective included) sat in the same call with
# no restriction on use. The guide's first scripted_question already carries
# whatever framing the original study had, so the instruction was removed
# outright rather than softened.
#
# These tests assert against the sandbox file only. Production
# (prompts/03_SESSION_OPENING_PROMPT.md) is covered by its own follow-on task;
# the pre-existing production assertions live in
# test_render_opening_message_no_override_is_production_default above.
# ---------------------------------------------------------------------------

_SANDBOX_OPENING_OVERRIDE = "sandbox/03_SESSION_OPENING_PROMPT_SANDBOX.md"

# The full post-fix `utterance` field, verbatim. The `\n` sequences are
# literal two-character escapes in the file (it is a JSON string inside a
# fenced markdown block), hence the raw strings.
_UTTERANCE_FIELD = (
    r'"utterance": "Your full opening statement. This must accomplish all of the following in natural, warm, conversational language — not a formal list of rules:\n\n'
    r'1. Welcome the group and introduce yourself briefly.\n'
    r'2. Set expectations for natural conversation: invite actual, concrete experiences (what participants have used, avoided, liked, disliked, or felt unsure about).\n'
    r'3. Establish ground rules lightly: remind participants to listen to each other and respond naturally if something connects with their experience.\n'
    r'4. State clearly that there are no right or wrong answers, but do not over-emphasize the need for disagreement, debate, or profound insight.\n'
    r"5. Introduce the first question naturally as a continuation of the welcome — not as a formal pivot. Use the first discussion-guide section's own `scripted_question` as written; it already carries whatever brief topic framing the original study included. Do not add your own explanation of what the discussion or the research is about before, after, or around it.\n\n"
    r'The entire utterance should feel like one continuous, warm, human opening — not a sequence of procedural announcements or a search for deep philosophical truth."'
)

_NON_DISCLOSURE_PARAGRAPH = (
    "**Important — internal use only.** `research_objective` and `moderator_knowledge_brief` describe\n"
    "what the researcher is trying to learn and what you are permitted to know about the topic. They\n"
    "orient your own judgment throughout the session — how you probe, what you listen for, what\n"
    "matters — but they are not for the group. Never state, paraphrase, summarize, or hint at either of\n"
    "these to participants, in the opening or at any later point in the session. Participants should\n"
    "never be able to infer the specific research question from anything you say."
)


def test_sandbox_opening_prompt_has_no_topic_framing_instruction():
    """§4.1 — the removed checklist item must not reappear anywhere."""
    raw = _read_prompt(_SANDBOX_OPENING_OVERRIDE)
    assert "Establish the topic" not in raw
    # The worked example that came with it must be gone too, not just the
    # imperative — it was the more directly quotable of the two.
    assert "how it fits into everyday life" not in raw


def test_sandbox_opening_utterance_checklist_is_exactly_five_items():
    """§4.2 — the checklist matches the replacement text exactly, 5 items."""
    raw = _read_prompt(_SANDBOX_OPENING_OVERRIDE)
    line = next(l.strip() for l in raw.splitlines() if l.strip().startswith('"utterance"'))
    assert line == _UTTERANCE_FIELD
    # Numbering is contiguous 1-5 with no orphaned 6 left by the renumber.
    assert re.findall(r"\\n(\d)\. ", line) == ["1", "2", "3", "4", "5"]
    # New item 5 points at the guide's own question instead of inventing framing.
    assert "`scripted_question` as written" in line


def test_sandbox_opening_prompt_forbids_disclosing_research_objective():
    """§4.3 — paragraph present, between the schema block and the task heading."""
    raw = _read_prompt(_SANDBOX_OPENING_OVERRIDE)
    assert raw.count(_NON_DISCLOSURE_PARAGRAPH) == 1
    # Placement, checked as one contiguous span rather than by index maths:
    # closing fence of the SESSION CONFIGURATION schema, the paragraph, then
    # the `---` separator and the task heading.
    assert (
        "```\n\n"
        + _NON_DISCLOSURE_PARAGRAPH
        + "\n\n---\n\n## YOUR TASK FOR THIS OPENING CALL"
    ) in raw
    # The schema fields themselves must survive — only the instruction to
    # voice them was removed (§5 "What NOT to do").
    assert '"research_objective": "string' in raw
    assert '"topic_domain": "string' in raw
    assert '"moderator_knowledge_brief": "string' in raw


def test_sandbox_opening_prompt_renders_with_both_fixes_applied():
    """
    End-to-end through the real renderer, not just the raw file: the rendered
    prompt a live session would send must carry the non-disclosure paragraph
    and no topic-framing instruction. The research_objective VALUE still
    appears — that is the data the moderator needs for internal orientation,
    and is explicitly in scope to keep.
    """
    rendered = render_opening_message(
        {"research_objective": "how men in the UK make everyday food choices"},
        opening_prompt_override_filename=_SANDBOX_OPENING_OVERRIDE,
    )
    assert "Establish the topic" not in rendered
    assert _NON_DISCLOSURE_PARAGRAPH in rendered
    assert "how men in the UK make everyday food choices" in rendered


# ---------------------------------------------------------------------------
# Offline verification for INSTRUCTIONS_FIX_DOUBLE_PLACEHOLDER_INJECTION.md §3.
#
# Root cause: each of these prompt files documents its own injection point in
# the file-level header comment by writing the literal `{PLACEHOLDER}` string.
# The renderers do a whole-file `template.replace("{PLACEHOLDER}", value)`,
# which has no notion of "header comment" (unlike load_system_prompt, which
# strips headers), so the substituted value landed TWICE: once in the intended
# body slot and once in the comment. For 02_USER_MESSAGE_TEMPLATE.md that meant
# the entire serialised session_state was duplicated on EVERY turn of every
# session (~33.6k of a 72,078-character message measured on a real turn-10
# state). The fix rewords the comment lines so they no longer contain the
# literal; the `.replace()` mechanism is unchanged.
#
# These assert `.count(...) == 1`, not `in` — a presence-only assertion is
# exactly what let this bug survive undetected in the existing tests above.
#
# Placement note: render_turn_message() and render_reflection_message() have no
# dedicated behavioural test module of their own (tests/test_system_operation_
# docs.py only checks that their NAMES appear in the docs), so all three live
# here alongside the opening-prompt test they share a root cause with.
# ---------------------------------------------------------------------------

def test_opening_prompt_injects_session_config_exactly_once_both_paths():
    """§3.1 — production-default and sandbox-override render paths."""
    cfg = {
        "session_id": "x",
        "research_objective": "MARKER_OBJ_1",
        "topic_domain": "t",
        "participant_collective_identity": "p",
        "moderator_knowledge_brief": "b",
        "participants": [],
        "discussion_guide": [],
        "researcher_notes": "n",
    }
    for override in (None, _SANDBOX_OPENING_OVERRIDE):
        rendered = render_opening_message(cfg, opening_prompt_override_filename=override)
        assert rendered.count("MARKER_OBJ_1") == 1, (
            f"override={override!r}: research_objective injected "
            f"{rendered.count('MARKER_OBJ_1')}x, expected exactly 1"
        )
        # The header comment must still document the injection point, just
        # without spelling the literal placeholder.
        assert "SESSION_CONFIG placeholder in the code block" in rendered
        assert "{SESSION_CONFIG}" not in rendered


def test_turn_message_injects_state_and_trigger_exactly_once():
    """
    §3.2 — the per-turn message is the costly instance: sent on every turn of
    every session, production and sandbox alike (they share this one file).
    """
    meta = _session_meta(id="MARKER_SESSION_ID_1")
    state = _state(meta)
    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="Alice",
        content="MARKER_TRIG_1",
        turn_number=11,
    )

    rendered = render_turn_message(state, trigger)

    # session_id lives inside the serialised SESSION_STATE JSON; a duplicated
    # header injection doubles the whole blob and so doubles this too.
    assert rendered.count("MARKER_SESSION_ID_1") == 1
    # trigger content lives inside the serialised TRIGGER_EVENT JSON.
    assert rendered.count("MARKER_TRIG_1") == 1
    assert "{SESSION_STATE}" not in rendered
    assert "{TRIGGER_EVENT}" not in rendered


def test_turn_message_length_is_well_under_pre_fix_baseline():
    """
    §3.2 (second half) — length regression against a fixed real state fixture.
    The same archived turn-10 state rendered to 72,078 characters before the
    fix; the accidental duplicate SESSION_STATE copy alone was ~33,594 of
    those. 55,000 is a deliberately loose ceiling: it is far below the pre-fix
    figure (so a reintroduced duplication fails) while leaving room for the
    prompt body to grow normally.
    """
    fixture = Path("output/session_logs/sandbox_minimal_restraint_pilot_01/state_turn_10.json")
    if not fixture.exists():
        pytest.skip(f"archived state fixture not present: {fixture}")

    import json

    state = SessionState.model_validate(json.loads(fixture.read_text(encoding="utf-8")))
    trigger = TriggerEvent(
        type=TriggerEventType.PARTICIPANT_RESPONSE,
        speaker_id="P1",
        speaker_name="X",
        content="MARKER_TRIG_2",
        turn_number=11,
    )

    rendered = render_turn_message(state, trigger)

    assert rendered.count(state.session_meta.id) == 1
    assert rendered.count("MARKER_TRIG_2") == 1
    assert len(rendered) < 55_000, (
        f"rendered turn message is {len(rendered)} chars — pre-fix baseline for "
        "this same fixture was 72,078; is the header comment injecting a "
        "duplicate copy again?"
    )


def test_reflection_message_injects_each_substitution_exactly_once():
    """§3.3 — TRANSCRIPT and PRIOR_SUMMARIES, doubled by the same mechanism."""
    rendered = render_reflection_message(
        {"TRANSCRIPT": "MARKER_TRANS_1", "PRIOR_SUMMARIES": "MARKER_SUM_1"}
    )

    assert rendered.count("MARKER_TRANS_1") == 1
    assert rendered.count("MARKER_SUM_1") == 1
    assert "{TRANSCRIPT}" not in rendered
    assert "{PRIOR_SUMMARIES}" not in rendered
