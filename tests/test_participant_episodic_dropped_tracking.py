"""
Offline verification for INSTRUCTIONS_PARTICIPANT_MEMORY_TRACKING_AND_CACHING.md
§3.7 — FocusGroupOrchestrator._get_participant_episodic_entries() now returns a
third value, the count of entries silently dropped by the 'since_last_n' cap.

Why this matters: the cap discards the OLDEST part of a participant's catch-up
block when more happened since they last spoke than the cap allows. That is real
information loss, and before this change it left no trace anywhere. The count is
recorded (never acted on) so the drop rate is measurable from api_calls.jsonl.

Pure state construction + a pure function. Zero network calls, zero API calls —
the orchestrator fixture below patches every LLM entry point, mirroring the
fixture already used in tests/test_model_b_grocery.py. It is replicated rather
than imported because this repo has no shared conftest for orchestrator
fixtures and test_model_b_grocery.py's version hardcodes a grocery config that
doesn't fit these episodic-depth cases.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from core.orchestrator import FocusGroupOrchestrator
from core.session_state import ParticipantEngagementAssessment


def _config(**session_overrides) -> dict:
    config = {
        "session_id": "test_episodic_dropped",
        "research_objective": "Test",
        "topic_domain": "Test",
        "participation_mode": "emergent",
        "temperature": 1.0,
        "participant_collective_identity": "consumers",
        "moderator_knowledge_brief": "brief",
        "researcher_notes": "",
        "participants": [
            {"id": "P1", "name": "Sarah", "profile_summary": ""},
            {"id": "P2", "name": "John", "profile_summary": ""},
            {"id": "P3", "name": "Elena", "profile_summary": ""},
        ],
        "discussion_guide": [
            {
                "section_index": 0,
                "section_label": "Intro",
                "section_phase": "intro",
                "section_purpose": "Test",
                "scripted_question": "Test",
                "probing_depth_ceiling": "light",
                "stimulus": None,
            }
        ],
    }
    config.update(session_overrides)
    return config


@pytest.fixture
def orchestrator(monkeypatch):
    """Orchestrator with every LLM entry point mocked out."""
    orch = FocusGroupOrchestrator(_config())
    monkeypatch.setattr(
        "core.orchestrator.call_participant",
        MagicMock(return_value=("Mocked participant response.", [])),
    )
    monkeypatch.setattr(
        "core.orchestrator.assess_engagement",
        MagicMock(
            return_value=ParticipantEngagementAssessment(
                participant_id="P1",
                wants_to_speak=False,
                urgency=0.0,
                hook="",
                addressed_to=None,
                intent="stay_silent",
            )
        ),
    )
    monkeypatch.setattr(orch, "run_opening", MagicMock())
    return orch


def _transcript(*speaker_ids: str) -> list[dict]:
    return [
        {"speaker_id": sid, "speaker_name": sid, "content": f"turn {i} by {sid}"}
        for i, sid in enumerate(speaker_ids)
    ]


def test_gap_smaller_than_cap_drops_nothing(orchestrator):
    """P1 spoke, then 3 entries followed — under the cap of 10, nothing lost."""
    orchestrator.state.session_meta.participant_episodic_depth = "since_last_n"
    orchestrator.state.session_meta.participant_episodic_since_last_n = 10
    orchestrator.state.transcript = _transcript("P1", "P2", "P3", "MODERATOR")

    entries, use_history, dropped = orchestrator._get_participant_episodic_entries("P1")

    assert dropped == 0
    assert use_history is True
    # Everything in the gap is returned — the whole slice after P1's own turn.
    assert [e["speaker_id"] for e in entries] == ["P2", "P3", "MODERATOR"]


def test_gap_exceeding_cap_reports_the_shortfall_and_keeps_the_newest(orchestrator):
    """
    P1 spoke at index 0, then 8 entries followed, cap is 3. Three most RECENT
    are kept (not the oldest three) and the count of 5 is reported.
    """
    orchestrator.state.session_meta.participant_episodic_depth = "since_last_n"
    orchestrator.state.session_meta.participant_episodic_since_last_n = 3
    orchestrator.state.transcript = _transcript(
        "P1", "P2", "P3", "P2", "P3", "MODERATOR", "P2", "P3", "MODERATOR"
    )

    entries, use_history, dropped = orchestrator._get_participant_episodic_entries("P1")

    gap_size = 8
    cap = 3
    assert dropped == gap_size - cap == 5
    assert use_history is True
    assert len(entries) == cap
    # The MOST RECENT `cap` entries, i.e. the tail of the transcript.
    assert entries == orchestrator.state.transcript[-cap:]
    # Sanity: the oldest gap entry really is gone.
    assert orchestrator.state.transcript[1] not in entries


def test_participant_who_has_never_spoken_uses_whole_transcript(orchestrator):
    """No prior turn for P1 — the gap is the entire transcript so far."""
    orchestrator.state.session_meta.participant_episodic_depth = "since_last_n"
    orchestrator.state.session_meta.participant_episodic_since_last_n = 10
    orchestrator.state.transcript = _transcript("MODERATOR", "P2", "P3")

    entries, use_history, dropped = orchestrator._get_participant_episodic_entries("P1")

    assert dropped == 0
    assert use_history is True
    assert len(entries) == 3


def test_recent_k_never_reports_drops(orchestrator):
    """
    recent_k is a stateless sliding window — it discards by design rather than
    by cap, and returns use_accumulated_history=False. Reporting a drop count
    here would conflate two different mechanisms.
    """
    orchestrator.state.session_meta.participant_episodic_depth = "recent_k"
    orchestrator.state.session_meta.participant_episodic_recent_k = 2
    orchestrator.state.transcript = _transcript("P1", "P2", "P3", "MODERATOR", "P2")

    entries, use_history, dropped = orchestrator._get_participant_episodic_entries("P1")

    assert dropped == 0
    assert use_history is False
    assert len(entries) == 2


def test_full_depth_never_reports_drops(orchestrator):
    """'full' has no cap, so nothing can be dropped no matter how big the gap."""
    orchestrator.state.session_meta.participant_episodic_depth = "full"
    orchestrator.state.session_meta.participant_episodic_since_last_n = 2  # ignored
    orchestrator.state.transcript = _transcript(
        "P1", "P2", "P3", "MODERATOR", "P2", "P3", "MODERATOR"
    )

    entries, use_history, dropped = orchestrator._get_participant_episodic_entries("P1")

    assert dropped == 0
    assert use_history is True
    assert len(entries) == 6  # the entire gap, uncapped
