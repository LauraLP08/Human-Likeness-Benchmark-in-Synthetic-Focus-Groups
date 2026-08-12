"""
Unit tests for site 2 of the config-order bias class:
FocusGroupOrchestrator._resolve_name_to_id().

THE BUG:
    for pid, p in self.state.participants.items():
        if name_lower in p.name.lower():
            return pid

    First SUBSTRING match in config order won. With a roster containing
    Sam and Samuel, resolving "Sam" returned whichever was listed first —
    and resolving "Samuel" could return Sam if Sam came first, because
    "samuel" is not a substring of "sam"... but "sam" IS a substring of
    "samuel", so "Sam" was the genuinely dangerous direction. The
    constructor's collision check only rejects exact case-insensitive
    duplicates, never containment, so nothing caught it.

    Not a fairness problem like sites 1 and 3 — a match-precedence problem.
    Latent on FG1 (no containing name pairs) but real for Sam/Samuel,
    Dan/Daniel, Jo/Joanne, Will/William.

    Note the pre-existing docstring already promised "None if ambiguous" —
    the ambiguity branch simply was never implemented.

THE FIX: exact case-insensitive match first; substring containment only as a
fallback, and only when exactly one participant matches. Two or more is
ambiguous — warn and return None. The result feeds moderator direct-address
targeting, where returning None falls back to the normal engagement auction;
guessing wrong hands the turn to the wrong person.

Pure function tests. Zero network calls, zero API calls.
"""

from __future__ import annotations

import logging

import pytest

from core.orchestrator import FocusGroupOrchestrator


def _config(names: list[str]) -> dict:
    return {
        "session_id": "resolve_name_test",
        "research_objective": "Test",
        "topic_domain": "Test",
        "participation_mode": "emergent",
        "temperature": 1.0,
        "participant_collective_identity": "test participants",
        "moderator_knowledge_brief": "brief",
        "researcher_notes": "",
        "participants": [
            {"id": f"p_{n.lower()}", "name": n, "profile_summary": ""} for n in names
        ],
        "discussion_guide": [
            {
                "section_index": 0,
                "section_label": "Intro",
                "section_phase": "intro",
                "section_purpose": "Test",
                "scripted_question": "Test?",
                # No probing_depth_ceiling: it is pinned to None for all runs,
                # and setting it makes _build_state_from_config log an "ignoring
                # it" warning that pollutes the caplog assertions below.
                "stimulus": None,
            }
        ],
    }


@pytest.fixture
def orch(monkeypatch, tmp_path):
    """Factory: build an orchestrator with the given participant names."""
    monkeypatch.setattr("core.orchestrator._OUTPUT_ROOT", tmp_path)

    def _make(names: list[str]) -> FocusGroupOrchestrator:
        return FocusGroupOrchestrator(_config(names))

    return _make


# ---------------------------------------------------------------------------
# (a) Exact match wins over a longer name that also contains it
# ---------------------------------------------------------------------------

def test_exact_match_wins_over_containing_name(orch):
    """"Sam" is Sam, not Samuel — even though "Samuel" contains "sam"."""
    o = orch(["Sam", "Samuel"])
    assert o._resolve_name_to_id("Sam") == "p_sam"


def test_exact_match_wins_regardless_of_config_position(orch):
    """Same assertion with the config order reversed — Samuel listed first."""
    o = orch(["Samuel", "Sam"])
    assert o._resolve_name_to_id("Sam") == "p_sam"


def test_exact_match_is_case_insensitive(orch):
    o = orch(["Sam", "Samuel"])
    assert o._resolve_name_to_id("SAM") == "p_sam"
    assert o._resolve_name_to_id("sAm") == "p_sam"


def test_longer_name_resolves_to_itself(orch):
    """The other direction: "Samuel" is unambiguous and must still resolve."""
    for order in (["Sam", "Samuel"], ["Samuel", "Sam"]):
        o = orch(order)
        assert o._resolve_name_to_id("Samuel") == "p_samuel"


# ---------------------------------------------------------------------------
# (b) Unambiguous substring still resolves, as before
# ---------------------------------------------------------------------------

def test_unambiguous_substring_still_resolves(orch):
    """Behaviour preserved: a partial name with one candidate resolves."""
    o = orch(["Alice", "Bob", "Charlotte"])
    assert o._resolve_name_to_id("Charl") == "p_charlotte"


def test_unambiguous_substring_resolves_from_any_position(orch):
    o = orch(["Charlotte", "Alice", "Bob"])
    assert o._resolve_name_to_id("harlot") == "p_charlotte"


def test_full_name_match_unaffected(orch):
    """The common case — moderator says the exact name — is unchanged."""
    o = orch(["Amir", "David", "Ibrahim", "Isaiah", "Will"])
    assert o._resolve_name_to_id("Ibrahim") == "p_ibrahim"
    assert o._resolve_name_to_id("Will") == "p_will"


# ---------------------------------------------------------------------------
# (c) Ambiguous substring returns None and warns
# ---------------------------------------------------------------------------

def test_ambiguous_substring_returns_none(orch):
    """"Dan" matches both Danielle and Danny — refuse to guess."""
    o = orch(["Danielle", "Danny"])
    assert o._resolve_name_to_id("Dan") is None


def test_ambiguous_substring_logs_a_warning(orch, caplog):
    o = orch(["Danielle", "Danny"])

    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        result = o._resolve_name_to_id("Dan")

    assert result is None
    assert len(caplog.records) == 1, caplog.records
    msg = caplog.records[0].message
    assert caplog.records[0].levelno == logging.WARNING
    assert "Ambiguous participant name" in msg
    # Both candidates are named, so the log is actionable.
    assert "Danielle" in msg and "Danny" in msg


def test_ambiguous_outcome_is_independent_of_config_order(orch, caplog):
    """
    The regression test for this bug. Pre-fix, "Dan" returned the first-listed
    of Danielle/Danny, so reversing the config flipped the answer. Now both
    orders agree — on None.
    """
    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        forward = orch(["Danielle", "Danny"])._resolve_name_to_id("Dan")
        backward = orch(["Danny", "Danielle"])._resolve_name_to_id("Dan")

    assert forward is backward is None


def test_three_way_ambiguity_returns_none(orch):
    o = orch(["Jo", "Joanne", "Joseph"])
    # "Jo" is exact for the first, so that one resolves...
    assert o._resolve_name_to_id("Jo") == "p_jo"
    # ...but a partial matching all three does not.
    assert o._resolve_name_to_id("J") is None


# ---------------------------------------------------------------------------
# (d) No match / empty input — unchanged behaviour
# ---------------------------------------------------------------------------

def test_no_match_returns_none(orch):
    o = orch(["Alice", "Bob"])
    assert o._resolve_name_to_id("Zebedee") is None


def test_no_match_does_not_warn(orch, caplog):
    """A plain miss is normal (e.g. target "group") — it must stay quiet."""
    o = orch(["Alice", "Bob"])
    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        assert o._resolve_name_to_id("group") is None
    assert caplog.records == []


def test_empty_and_none_input_return_none(orch):
    o = orch(["Alice", "Bob"])
    assert o._resolve_name_to_id(None) is None
    assert o._resolve_name_to_id("") is None
