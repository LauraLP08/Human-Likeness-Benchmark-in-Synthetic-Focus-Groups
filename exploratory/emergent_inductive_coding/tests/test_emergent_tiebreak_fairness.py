"""
Regression tests for the config-order tie-break bias in
FocusGroupOrchestrator.run_conversation_step() (Model B / "emergent" mode).

THE BUG (confirmed against real pilot data before the fix):
    Both speaker-selection branches sort assessments by (-urgency, turn_count).
    Python's sort is stable, so whenever two or more participants tied exactly
    on BOTH keys, the winner was whoever appeared first in the list being
    sorted — which was built by iterating self.state.participants.items(),
    i.e. config insertion order. The first-listed participant in the config
    won every perfect tie, silently and permanently.

    Real evidence from output/session_logs/macho_meals_fg1_run01:
      - state_turn_2.json  (introductions round): all five participants
        returned urgency 0.80 with turn_count 0 — a five-way exact tie.
      - state_turn_7.json  ("favourite place" question): Amir and David both
        0.80 with turn_count 1 — a two-way tie at the top.
    Amir, listed first in configs/experiment/macho_meals_fg1_run01.json, won
    both. He had no urgency edge in either round.

    This matters beyond fairness: whoever speaks first frames the question the
    others react to (in state_turn_8.json all four others carry
    addressed_to: "Amir"). Across replicate runs the same participant would
    frame every tied round, so replicates would not be independent.

THE FIX:
    A seeded shuffle of a COPY of the assessments list, used only for
    selection. Sort keys are unchanged; the shuffle only changes what stable
    sort falls back to when the keys tie. Seeded on
    (session_id, total_turns) so a run stays reproducible.

Offline only — assess_engagement, call_participant and call_moderator are all
mocked. Zero network calls, zero API calls.
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter

import pytest
from unittest.mock import MagicMock

from core.config import URGENCY_THRESHOLD
from core.orchestrator import FocusGroupOrchestrator
from core.session_state import (
    ModeratorAPIResponse,
    ModeratorDecisionResponse,
    ParticipantEngagementAssessment,
)

# Five participants, deliberately NOT in alphabetical order, so that a test
# failure can distinguish "config order" from "alphabetical order" — the FG1
# config happened to be alphabetical, which made the two indistinguishable in
# the real run.
PIDS = ["p_zeta", "p_alpha", "p_mike", "p_bravo", "p_yankee"]
NAMES = {"p_zeta": "Zeta", "p_alpha": "Alpha", "p_mike": "Mike",
         "p_bravo": "Bravo", "p_yankee": "Yankee"}

TRIALS = 1000
LOWER_BAND, UPPER_BAND = 0.15, 0.25   # expected 0.20 each for 5 participants


def _config(pids: list[str], session_id: str = "tiebreak_test") -> dict:
    return {
        "session_id": session_id,
        "research_objective": "Test",
        "topic_domain": "Test",
        "participation_mode": "emergent",
        "temperature": 1.0,
        "participant_collective_identity": "test participants",
        "moderator_knowledge_brief": "brief",
        "researcher_notes": "",
        "participants": [
            {"id": pid, "name": NAMES[pid], "profile_summary": ""} for pid in pids
        ],
        "discussion_guide": [
            {
                "section_index": 0,
                "section_label": "Intro",
                "section_phase": "intro",
                "section_purpose": "Test",
                "scripted_question": "Test question?",
                "probing_depth_ceiling": "light",
                "stimulus": None,
            }
        ],
    }


def _silent_moderator() -> MagicMock:
    """Moderator that observes and stays silent — minimises state churn."""
    return MagicMock(return_value=(ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(
            intervention_mode="observe",
            situation_assessment="Test",
            dominant_signal="response_needs_probing",
            action="stay_silent",
            target="group",
            probe_type=None,
            follow_up_intensity=None,
            next_speaker=None,
            queued_next_action=None,
        ),
        utterance="",
        validation_fallback=False,
    ), []))


def _build(pids, monkeypatch, tmp_path, session_id="tiebreak_test"):
    """Orchestrator with all LLM entry points mocked and logs sent to tmp_path."""
    monkeypatch.setattr("core.orchestrator._OUTPUT_ROOT", tmp_path)
    orch = FocusGroupOrchestrator(_config(pids, session_id))
    monkeypatch.setattr(
        "core.orchestrator.call_participant",
        MagicMock(return_value=("Mocked participant response.", [])),
    )
    monkeypatch.setattr("core.orchestrator.call_moderator", _silent_moderator())
    return orch


def _reset(orch, total_turns: int, turn_counts: dict[str, int] | None = None):
    """
    Return the orchestrator to a clean pre-selection state and set total_turns,
    which (with session_id) is the shuffle seed. Resetting between trials keeps
    every trial an identical tie situation, so the only thing varying is the
    seed.
    """
    orch.state.session_meta.total_turns = total_turns
    orch.state.transcript = []
    orch.state.moderator_log = []
    gs = orch.state.group_state
    gs.last_engagement_round = []
    gs.consecutive_silent_turns = 0
    gs.consecutive_participant_turns = 0
    gs.section_turn_counts = {}
    gs.section_word_counts = {}
    gs.dominant_voices = []
    for pid, p in orch.state.participants.items():
        p.turn_count = (turn_counts or {}).get(pid, 0)


def _assessor(urgencies: dict[str, float], wants: bool = True):
    """assess_engagement stand-in returning a fixed urgency per participant."""
    def mock_assess(participant, *args, **kwargs):
        return ParticipantEngagementAssessment(
            participant_id=participant.id,
            wants_to_speak=wants,
            urgency=urgencies[participant.id],
            hook="",
            addressed_to=None,
            intent="respond",
        )
    return mock_assess


def _run_trials(orch, monkeypatch, urgencies, n=TRIALS, wants=True,
                turn_counts=None, silent_turns=0) -> Counter:
    monkeypatch.setattr("core.orchestrator.assess_engagement",
                        _assessor(urgencies, wants=wants))
    winners: Counter = Counter()
    for t in range(n):
        _reset(orch, total_turns=t, turn_counts=turn_counts)
        orch.state.group_state.consecutive_silent_turns = silent_turns
        result = orch.run_conversation_step()
        assert result["step_type"] == "participant_led", (
            f"trial {t}: expected a participant to be selected, got {result}"
        )
        winners[result["speaker"]] += 1
    return winners


# ---------------------------------------------------------------------------
# (a) Uniformity under a total tie — the primary branch
# ---------------------------------------------------------------------------

def test_total_tie_distributes_uniformly(monkeypatch, tmp_path):
    """
    All five identical on urgency AND turn_count. No participant should win
    materially more than 1/5 of the time. Pre-fix this was 100% for p_zeta.
    """
    orch = _build(PIDS, monkeypatch, tmp_path)
    winners = _run_trials(orch, monkeypatch, {pid: 0.8 for pid in PIDS})

    assert set(winners) == set(PIDS), f"some participant never won: {winners}"
    for pid in PIDS:
        share = winners[pid] / TRIALS
        assert LOWER_BAND <= share <= UPPER_BAND, (
            f"{pid} won {share:.1%} of {TRIALS} tied selections "
            f"(expected ~20%); full distribution: {dict(winners)}"
        )


# ---------------------------------------------------------------------------
# (b) Config-order independence — THE regression test for this bug
# ---------------------------------------------------------------------------

def test_winner_distribution_is_independent_of_config_order(monkeypatch, tmp_path):
    """
    Reversing the participants array in the config must not change who wins
    how often. On the pre-fix code this fails immediately and loudly: the
    first-listed participant wins 100% either way, so reversing the config
    moves 100% of wins from p_zeta to p_yankee.
    """
    forward = _build(PIDS, monkeypatch, tmp_path / "fwd")
    fwd_winners = _run_trials(forward, monkeypatch, {pid: 0.8 for pid in PIDS})

    reversed_pids = list(reversed(PIDS))
    backward = _build(reversed_pids, monkeypatch, tmp_path / "rev")
    rev_winners = _run_trials(backward, monkeypatch, {pid: 0.8 for pid in reversed_pids})

    for pid in PIDS:
        fwd_share = fwd_winners[pid] / TRIALS
        rev_share = rev_winners[pid] / TRIALS
        assert LOWER_BAND <= fwd_share <= UPPER_BAND, (pid, dict(fwd_winners))
        assert LOWER_BAND <= rev_share <= UPPER_BAND, (pid, dict(rev_winners))

    # And explicitly: neither config's first-listed participant dominates.
    assert fwd_winners[PIDS[0]] / TRIALS < 0.5, "first-listed still dominates (forward)"
    assert rev_winners[reversed_pids[0]] / TRIALS < 0.5, "first-listed still dominates (reversed)"


# ---------------------------------------------------------------------------
# (c) The real signal still decides when it is not tied
# ---------------------------------------------------------------------------

def test_higher_urgency_always_wins_regardless_of_config_position(monkeypatch, tmp_path):
    """The shuffle must only break exact ties, never override urgency."""
    orch = _build(PIDS, monkeypatch, tmp_path)
    last_listed = PIDS[-1]                      # worst possible config position
    urgencies = {pid: 0.7 for pid in PIDS}
    urgencies[last_listed] = 0.9

    winners = _run_trials(orch, monkeypatch, urgencies)

    assert winners[last_listed] == TRIALS, (
        f"strictly-highest-urgency participant won only {winners[last_listed]}/"
        f"{TRIALS}: {dict(winners)}"
    )


def test_lower_turn_count_always_wins_when_urgency_tied(monkeypatch, tmp_path):
    """turn_count is the documented second key and must still be decisive."""
    orch = _build(PIDS, monkeypatch, tmp_path)
    last_listed = PIDS[-1]
    # Everyone has spoken twice except the last-listed participant.
    turn_counts = {pid: 2 for pid in PIDS}
    turn_counts[last_listed] = 0

    winners = _run_trials(
        orch, monkeypatch, {pid: 0.8 for pid in PIDS}, turn_counts=turn_counts
    )

    assert winners[last_listed] == TRIALS, (
        f"lowest-turn_count participant won only {winners[last_listed]}/"
        f"{TRIALS}: {dict(winners)}"
    )


# ---------------------------------------------------------------------------
# (d) Reproducibility
# ---------------------------------------------------------------------------

def test_same_seed_yields_same_winner(monkeypatch, tmp_path):
    """Same (session_id, total_turns) must select the same speaker every time."""
    orch = _build(PIDS, monkeypatch, tmp_path)
    monkeypatch.setattr("core.orchestrator.assess_engagement",
                        _assessor({pid: 0.8 for pid in PIDS}))

    for turn in (0, 7, 42):
        picks = set()
        for _ in range(5):
            _reset(orch, total_turns=turn)
            picks.add(orch.run_conversation_step()["speaker"])
        assert len(picks) == 1, f"turn {turn} produced varying winners: {picks}"


def test_session_id_changes_the_tie_outcome(monkeypatch, tmp_path):
    """
    The seed includes session_id, so two sessions do not share one fixed
    pecking order. (Guards against seeding on total_turns alone.)
    """
    a = _build(PIDS, monkeypatch, tmp_path / "a", session_id="session_a")
    wa = _run_trials(a, monkeypatch, {pid: 0.8 for pid in PIDS}, n=60)
    b = _build(PIDS, monkeypatch, tmp_path / "b", session_id="session_b")
    wb = _run_trials(b, monkeypatch, {pid: 0.8 for pid in PIDS}, n=60)

    seq_a = [wa[pid] for pid in PIDS]
    seq_b = [wb[pid] for pid in PIDS]
    assert seq_a != seq_b, (
        "different session_ids produced an identical win pattern — is "
        "session_id actually part of the seed?"
    )


def test_shuffle_is_independent_of_pythonhashseed():
    """
    random.Random(str) seeds from the string's bytes (sha512), NOT from the
    per-process-randomised hash(). Prove it by running the same shuffle under
    two different PYTHONHASHSEED values in subprocesses — the orchestrator's
    reproducibility guarantee depends on this.
    """
    snippet = (
        "import random;"
        "xs=list(range(5));"
        "random.Random('tiebreak_test:7').shuffle(xs);"
        "print(xs)"
    )
    outs = []
    for hashseed in ("0", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True, text=True,
            env={"PYTHONHASHSEED": hashseed, "SYSTEMROOT": "C:\\Windows",
                 "PATH": ""},
        )
        assert proc.returncode == 0, proc.stderr
        outs.append(proc.stdout.strip())

    assert outs[0] == outs[1], (
        f"shuffle differed across PYTHONHASHSEED values: {outs}"
    )


# ---------------------------------------------------------------------------
# (e) Persisted order must stay unshuffled — the nuance this change turns on
# ---------------------------------------------------------------------------

def test_last_engagement_round_keeps_config_order(monkeypatch, tmp_path):
    """
    The fix shuffles a COPY. state.group_state.last_engagement_round is a
    reference to the ORIGINAL assessments list and must remain in config /
    insertion order for logs and saved state.

    This is the one test that catches someone "simplifying" the fix into an
    in-place shuffle of `assessments`.
    """
    orch = _build(PIDS, monkeypatch, tmp_path)
    monkeypatch.setattr("core.orchestrator.assess_engagement",
                        _assessor({pid: 0.8 for pid in PIDS}))

    # Check across several seeds: an in-place shuffle would betray itself on
    # at least one of them even if one seed happened to be the identity.
    for turn in range(12):
        _reset(orch, total_turns=turn)
        orch.run_conversation_step()
        persisted = [a.participant_id for a in orch.state.group_state.last_engagement_round]
        assert persisted == PIDS, (
            f"turn {turn}: last_engagement_round was reordered to {persisted}; "
            f"expected config order {PIDS}. The selection shuffle must operate "
            f"on a copy."
        )


# ---------------------------------------------------------------------------
# (f) The low_threshold fallback branch — same guarantees
# ---------------------------------------------------------------------------

_LOW = 0.5   # below URGENCY_THRESHOLD (0.55) but above the branch's own 0.2 floor


def test_low_threshold_branch_is_actually_exercised(monkeypatch, tmp_path):
    """Guard: the (f) tests below are worthless if they silently take the
    primary branch instead."""
    assert _LOW < URGENCY_THRESHOLD, "fixture urgency must be below the threshold"
    orch = _build(PIDS, monkeypatch, tmp_path)
    monkeypatch.setattr("core.orchestrator.assess_engagement",
                        _assessor({pid: _LOW for pid in PIDS}, wants=False))
    _reset(orch, total_turns=0)
    orch.state.group_state.consecutive_silent_turns = 2
    result = orch.run_conversation_step()
    assert result["selection_mode"] == "low_threshold", result


def test_low_threshold_total_tie_distributes_uniformly(monkeypatch, tmp_path):
    orch = _build(PIDS, monkeypatch, tmp_path)
    winners = _run_trials(
        orch, monkeypatch, {pid: _LOW for pid in PIDS}, wants=False, silent_turns=2
    )

    assert set(winners) == set(PIDS), f"some participant never won: {winners}"
    for pid in PIDS:
        share = winners[pid] / TRIALS
        assert LOWER_BAND <= share <= UPPER_BAND, (
            f"{pid} won {share:.1%} in the low_threshold branch; "
            f"distribution: {dict(winners)}"
        )


def test_low_threshold_independent_of_config_order(monkeypatch, tmp_path):
    forward = _build(PIDS, monkeypatch, tmp_path / "fwd")
    fwd = _run_trials(forward, monkeypatch, {pid: _LOW for pid in PIDS},
                      wants=False, silent_turns=2)

    reversed_pids = list(reversed(PIDS))
    backward = _build(reversed_pids, monkeypatch, tmp_path / "rev")
    rev = _run_trials(backward, monkeypatch, {pid: _LOW for pid in reversed_pids},
                      wants=False, silent_turns=2)

    for pid in PIDS:
        assert LOWER_BAND <= fwd[pid] / TRIALS <= UPPER_BAND, (pid, dict(fwd))
        assert LOWER_BAND <= rev[pid] / TRIALS <= UPPER_BAND, (pid, dict(rev))


def test_low_threshold_higher_urgency_still_wins(monkeypatch, tmp_path):
    orch = _build(PIDS, monkeypatch, tmp_path)
    last_listed = PIDS[-1]
    urgencies = {pid: 0.3 for pid in PIDS}
    urgencies[last_listed] = _LOW          # still under URGENCY_THRESHOLD

    winners = _run_trials(orch, monkeypatch, urgencies, wants=False, silent_turns=2)

    assert winners[last_listed] == TRIALS, (
        f"highest-urgency participant won only {winners[last_listed]}/{TRIALS} "
        f"in the low_threshold branch: {dict(winners)}"
    )
