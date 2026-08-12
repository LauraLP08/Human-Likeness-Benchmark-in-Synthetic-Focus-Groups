"""
Regression tests for site 3 of the config-order bias class:
which under-participating participant the moderator gets nudged toward.

THE BUG:
    _build_participation_injection() named
    state.group_state.silent_participants[0]. That list is built in config
    insertion order (core/session_state.py, the silent_participants update),
    so among everyone below the 15% participation threshold the config-first
    participant was named every time — even when someone else in the same
    list had spoken strictly less. The repeated-nudge bias is the same family
    as the emergent tie-break bug fixed in run_conversation_step().

THE FIX (core/prompt_renderer.py, _pick_silent_participant):
    Lowest turn_count wins. A genuine tie on turn_count is broken with a
    seeded random pick over the SORTED tied set, so the outcome depends on
    which participants are tied, never on their position in the list.
    Seeded on (session_id, total_turns, "silent_pick") for reproducibility.

silent_participants itself stays a plain list in config order — it is read
elsewhere (a truthiness check in _build_section_transition_injection) and the
saved state/logs are easier to read in a stable order. Only the "who do we
name" decision is special-cased, at the point of use.

Pure function tests over hand-built state. Zero network calls, zero API calls.
"""

from __future__ import annotations

from collections import Counter

from core.prompt_renderer import _build_participation_injection, _pick_silent_participant
from core.session_state import (
    DiscussionGuideSection,
    GroupState,
    ParticipantState,
    SectionPhase,
    SessionMeta,
    SessionState,
)

# Deliberately non-alphabetical so a failure distinguishes "config order" from
# "alphabetical order".
PIDS = ["p_zeta", "p_alpha", "p_mike", "p_bravo", "p_yankee"]
NAMES = {"p_zeta": "Zeta", "p_alpha": "Alpha", "p_mike": "Mike",
         "p_bravo": "Bravo", "p_yankee": "Yankee"}


def _state(
    turn_counts: dict[str, int],
    silent: list[str],
    session_id: str = "silent_pick_test",
    total_turns: int = 0,
    pid_order: list[str] | None = None,
) -> SessionState:
    order = pid_order or PIDS
    return SessionState(
        session_meta=SessionMeta(
            id=session_id,
            research_objective="test",
            topic_domain="test",
            participant_collective_identity="test participants",
            moderator_knowledge_brief="",
            total_turns=total_turns,
        ),
        discussion_guide=[
            DiscussionGuideSection(
                section_index=0,
                section_label="Intro",
                section_phase=SectionPhase.INTRO,
                section_purpose="test",
                scripted_question="test?",
            )
        ],
        participants={
            pid: ParticipantState(id=pid, name=NAMES[pid], turn_count=turn_counts[pid])
            for pid in order
        },
        group_state=GroupState(silent_participants=list(silent)),
    )


# ---------------------------------------------------------------------------
# Lowest turn_count wins, regardless of list position
# ---------------------------------------------------------------------------

def test_picks_lowest_turn_count_not_first_listed():
    """The quietest participant is named even when listed last."""
    counts = {"p_zeta": 5, "p_alpha": 4, "p_mike": 3, "p_bravo": 2, "p_yankee": 1}
    state = _state(counts, silent=["p_zeta", "p_alpha", "p_mike", "p_bravo", "p_yankee"])

    assert _pick_silent_participant(state) == "p_yankee"


def test_pick_is_invariant_to_silent_list_order():
    """
    Same participants, same turn counts, list reversed — same answer.
    Pre-fix this returned whichever pid happened to sit at index 0.
    """
    counts = {"p_zeta": 5, "p_alpha": 4, "p_mike": 3, "p_bravo": 2, "p_yankee": 1}
    forward = ["p_zeta", "p_alpha", "p_mike", "p_bravo", "p_yankee"]

    a = _pick_silent_participant(_state(counts, silent=forward))
    b = _pick_silent_participant(_state(counts, silent=list(reversed(forward))))

    assert a == b == "p_yankee"


def test_only_considers_participants_in_the_silent_list():
    """
    Someone quieter but NOT flagged silent must not be picked — the 15%
    threshold decision stays where it is, in session_state.
    """
    counts = {"p_zeta": 9, "p_alpha": 8, "p_mike": 0, "p_bravo": 7, "p_yankee": 6}
    # p_mike has the fewest turns overall but is not in the silent list.
    state = _state(counts, silent=["p_zeta", "p_yankee"])

    assert _pick_silent_participant(state) == "p_yankee"


def test_empty_silent_list_returns_none_and_injection_is_blank():
    state = _state({pid: 3 for pid in PIDS}, silent=[])

    assert _pick_silent_participant(state) is None
    assert _build_participation_injection(state) == ""


def test_unknown_pid_in_silent_list_does_not_crash():
    """
    Defensive: the previous code tolerated a pid missing from participants
    (it used .get()). Preserve that — treat the missing one as 0 turns.
    """
    counts = {pid: 4 for pid in PIDS}
    state = _state(counts, silent=["p_zeta", "ghost_pid"])

    assert _pick_silent_participant(state) == "ghost_pid"   # 0 < 4


# ---------------------------------------------------------------------------
# Genuine ties resolve by seeded pick, not list position
# ---------------------------------------------------------------------------

_TIED = ["p_zeta", "p_alpha", "p_mike", "p_bravo", "p_yankee"]
TRIALS = 1000
LOWER_BAND, UPPER_BAND = 0.15, 0.25


def _tie_distribution(silent_order: list[str], n: int = TRIALS) -> Counter:
    counts = {pid: 1 for pid in PIDS}          # everyone equally quiet
    winners: Counter = Counter()
    for turn in range(n):
        state = _state(counts, silent=silent_order, total_turns=turn)
        winners[_pick_silent_participant(state)] += 1
    return winners


def test_turn_count_tie_distributes_uniformly():
    """A five-way tie must not always name the same person."""
    winners = _tie_distribution(_TIED)

    assert set(winners) == set(_TIED), f"someone was never picked: {winners}"
    for pid in _TIED:
        share = winners[pid] / TRIALS
        assert LOWER_BAND <= share <= UPPER_BAND, (
            f"{pid} picked {share:.1%} of {TRIALS} tied cases (expected ~20%); "
            f"distribution: {dict(winners)}"
        )


def test_tie_outcome_is_independent_of_list_order():
    """
    The regression test for this bug: reverse the silent_participants list and
    the distribution must be unchanged. Pre-fix, reversing moved 100% of the
    picks from one participant to another.
    """
    fwd = _tie_distribution(_TIED)
    rev = _tie_distribution(list(reversed(_TIED)))

    for pid in _TIED:
        assert LOWER_BAND <= fwd[pid] / TRIALS <= UPPER_BAND, (pid, dict(fwd))
        assert LOWER_BAND <= rev[pid] / TRIALS <= UPPER_BAND, (pid, dict(rev))

    # Stronger: the seeded pick sorts the tied set, so per-case answers match too.
    for turn in range(50):
        counts = {pid: 1 for pid in PIDS}
        a = _pick_silent_participant(_state(counts, silent=_TIED, total_turns=turn))
        b = _pick_silent_participant(
            _state(counts, silent=list(reversed(_TIED)), total_turns=turn)
        )
        assert a == b, f"turn {turn}: order changed the pick ({a} vs {b})"


def test_partial_tie_only_considers_the_lowest_group():
    """
    Two tied at the bottom, three above them — only the bottom two may ever
    be picked, and both should appear.
    """
    counts = {"p_zeta": 5, "p_alpha": 1, "p_mike": 4, "p_bravo": 1, "p_yankee": 3}
    winners: Counter = Counter()
    for turn in range(200):
        winners[_pick_silent_participant(_state(counts, silent=PIDS, total_turns=turn))] += 1

    assert set(winners) == {"p_alpha", "p_bravo"}, dict(winners)
    assert winners["p_alpha"] > 0 and winners["p_bravo"] > 0


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def test_same_seed_inputs_pick_the_same_participant():
    counts = {pid: 1 for pid in PIDS}
    for turn in (0, 7, 42):
        picks = {
            _pick_silent_participant(
                _state(counts, silent=_TIED, total_turns=turn, session_id="run_x")
            )
            for _ in range(5)
        }
        assert len(picks) == 1, f"turn {turn} was not reproducible: {picks}"


def test_session_id_changes_the_tie_outcome():
    """Two sessions must not share one fixed pecking order."""
    counts = {pid: 1 for pid in PIDS}
    a = [
        _pick_silent_participant(
            _state(counts, silent=_TIED, total_turns=t, session_id="run_a")
        )
        for t in range(60)
    ]
    b = [
        _pick_silent_participant(
            _state(counts, silent=_TIED, total_turns=t, session_id="run_b")
        )
        for t in range(60)
    ]
    assert a != b, "different session_ids produced identical pick sequences"


# ---------------------------------------------------------------------------
# The rendered block still names the participant that was picked
# ---------------------------------------------------------------------------

def test_injection_names_the_picked_participant():
    counts = {"p_zeta": 5, "p_alpha": 4, "p_mike": 3, "p_bravo": 2, "p_yankee": 1}
    state = _state(counts, silent=PIDS)

    block = _build_participation_injection(state)

    assert "Yankee" in block, block
    for other in ("Zeta", "Alpha", "Mike", "Bravo"):
        assert other not in block, f"named {other} as well: {block}"
    # turn_count substitution still tracks the participant actually named.
    assert "1" in block
