"""
Tests for the single-target assessment optimization in run_conversation_step.

Verifies that:
  - A single-target moderator directive causes exactly 1 assess_engagement call.
  - The auction path (zero or multiple targets) still calls assess_engagement
    for every participant, unchanged.
  - The peer-address bonus survives a single-target step (the assessed target's
    addressed_to is stored in last_engagement_round and picked up next step).
  - addressed_to=None is safe and does not fire the peer-address bonus.
  - Call-count savings: N=5 participants → 1 call vs 5 calls.

Zero network calls. All model-calling paths are monkeypatched.
See docs/changes/2026-07-23_single_target_assessment_optimization.md
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from core.session_state import (
    DiscussionGuideSection,
    GroupState,
    ModeratorAction,
    ModeratorLogEntry,
    ParticipantEngagementAssessment,
    ParticipantState,
    SectionPhase,
    SessionMeta,
    SessionState,
    TriggerEvent,
    TriggerEventType,
)
from core.orchestrator import FocusGroupOrchestrator


# ---------------------------------------------------------------------------
# Helpers: build minimal test state
# ---------------------------------------------------------------------------

def _make_participants(*names: str) -> dict[str, ParticipantState]:
    return {
        f"P{i + 1}": ParticipantState(id=f"P{i + 1}", name=name)
        for i, name in enumerate(names)
    }


def _make_state(participants: dict[str, ParticipantState]) -> SessionState:
    meta = SessionMeta(
        id="test_opt",
        research_objective="test",
        topic_domain="test",
        participant_collective_identity="test participants",
        moderator_knowledge_brief="",
    )
    guide = [
        DiscussionGuideSection(
            section_index=0,
            section_label="main",
            section_phase=SectionPhase.MAIN_TOPIC,
            section_purpose="test",
            scripted_question="Tell us something.",
        )
    ]
    return SessionState(
        session_meta=meta,
        discussion_guide=guide,
        participants=participants,
        group_state=GroupState(),
    )


def _make_orchestrator(state: SessionState, tmp_path: Path) -> FocusGroupOrchestrator:
    """Build an orchestrator that skips __init__ (no file I/O, no API)."""
    orch = object.__new__(FocusGroupOrchestrator)
    orch.state = state
    orch.log_dir = tmp_path
    orch.participant_histories = {pid: [] for pid in state.participants}
    orch.config = {}
    return orch


def _seed_last_mod(
    state: SessionState,
    *,
    target: str | None = None,
    intervention_mode: str = "speak",
) -> None:
    """Append a ModeratorLogEntry so run_conversation_step has a last_mod to read."""
    state.moderator_log.append(
        ModeratorLogEntry(
            turn=0,
            utterance="go ahead",
            action=ModeratorAction.DIRECT_PROBE,
            target=target,
            intervention_mode=intervention_mode,
        )
    )


# ---------------------------------------------------------------------------
# Shared fake factories
# ---------------------------------------------------------------------------

def _fake_assess_factory(
    call_log: list[str],
    responses: dict[str, ParticipantEngagementAssessment] | None = None,
    default_urgency: float = 0.0,
    default_wants: bool = False,
):
    """Returns a fake assess_engagement. Logs participant_id of every call."""
    def fake(participant, session_meta, recent, participant_own_turns=None, log_dir=None):
        pid = participant.id
        call_log.append(pid)
        if responses and pid in responses:
            return responses[pid]
        return ParticipantEngagementAssessment(
            participant_id=pid,
            wants_to_speak=default_wants,
            urgency=default_urgency,
        )
    return fake


def _fake_participant_turn_factory(call_log: list[str]):
    """Returns a fake run_participant_turn that records the pid and appends to transcript."""
    def fake(self, participant_id, recent_transcript=None, hook=""):
        call_log.append(participant_id)
        self.state.transcript.append({
            "turn": self.state.session_meta.total_turns,
            "speaker_id": participant_id,
            "speaker_name": self.state.participants[participant_id].name,
            "content": f"canned from {participant_id}",
        })
        return f"canned from {participant_id}"
    return fake


def _fake_moderator_turn():
    """Returns a fake run_moderator_turn that appends a canned log entry."""
    def fake(self, trigger_event, selection_mode=None):
        self.state.moderator_log.append(
            ModeratorLogEntry(
                turn=self.state.session_meta.total_turns,
                utterance="canned moderator",
                action=ModeratorAction.STAY_SILENT,
                intervention_mode="observe",
                target=None,
            )
        )
        return "canned moderator"
    return fake


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSingleTargetAssessesOnlyTarget:
    def test_single_target_assesses_only_target(self, monkeypatch, tmp_path):
        """Single-target handoff calls assess_engagement exactly once, for the target."""
        participants = _make_participants("Alice", "Bob", "Carol", "Dave")
        state = _make_state(participants)
        _seed_last_mod(state, target="Bob", intervention_mode="speak")

        assess_calls: list[str] = []
        participant_calls: list[str] = []

        monkeypatch.setattr(
            "core.orchestrator.assess_engagement",
            _fake_assess_factory(assess_calls),
        )

        orch = _make_orchestrator(state, tmp_path)
        monkeypatch.setattr(FocusGroupOrchestrator, "run_participant_turn", _fake_participant_turn_factory(participant_calls))
        monkeypatch.setattr(FocusGroupOrchestrator, "run_moderator_turn", _fake_moderator_turn())

        result = orch.run_conversation_step()

        assert assess_calls == ["P2"], f"Expected exactly 1 call for P2, got {assess_calls}"
        assert participant_calls == ["P2"]
        assert result["selection_mode"] == "moderator_direct_address"
        assert len(state.group_state.last_engagement_round) == 1
        assert state.group_state.last_engagement_round[0].participant_id == "P2"


class TestAuctionPathAssessesAll:
    def test_auction_path_assesses_all(self, monkeypatch, tmp_path):
        """When intervention_mode is not 'speak', all participants are assessed and auction runs."""
        participants = _make_participants("Alice", "Bob", "Carol", "Dave")
        state = _make_state(participants)
        _seed_last_mod(state, target=None, intervention_mode="observe")

        assess_calls: list[str] = []
        participant_calls: list[str] = []

        # P3 has highest urgency — should win the auction
        responses = {
            "P1": ParticipantEngagementAssessment(participant_id="P1", wants_to_speak=False, urgency=0.0),
            "P2": ParticipantEngagementAssessment(participant_id="P2", wants_to_speak=False, urgency=0.0),
            "P3": ParticipantEngagementAssessment(participant_id="P3", wants_to_speak=True, urgency=0.9, intent="respond"),
            "P4": ParticipantEngagementAssessment(participant_id="P4", wants_to_speak=False, urgency=0.0),
        }
        monkeypatch.setattr(
            "core.orchestrator.assess_engagement",
            _fake_assess_factory(assess_calls, responses=responses),
        )

        orch = _make_orchestrator(state, tmp_path)
        monkeypatch.setattr(FocusGroupOrchestrator, "run_participant_turn", _fake_participant_turn_factory(participant_calls))
        monkeypatch.setattr(FocusGroupOrchestrator, "run_moderator_turn", _fake_moderator_turn())

        result = orch.run_conversation_step()

        assert set(assess_calls) == {"P1", "P2", "P3", "P4"}, f"Expected all 4 assessed, got {assess_calls}"
        assert len(assess_calls) == 4
        assert participant_calls == ["P3"]


class TestPeerAddressPreservedAfterSingleTarget:
    def test_peer_address_preserved_after_single_target(self, monkeypatch, tmp_path):
        """
        Step 1: single-target (P2), assessment has addressed_to="Carol" (P3's name).
        Step 2: auction — P3 should receive PEER_ADDRESS_BONUS and win.
        Proves Option 2 keeps peer-address working through a directed handoff.
        """
        participants = _make_participants("Alice", "Bob", "Carol", "Dave")
        state = _make_state(participants)
        _seed_last_mod(state, target="Bob", intervention_mode="speak")

        assess_calls: list[str] = []
        participant_calls: list[str] = []

        # Step 1: called once for P2 with addressed_to="Carol"
        # Step 2: called 4 times, all at urgency=0.5 (below threshold 0.55)
        # After PEER_ADDRESS_BONUS (+0.15), P3 reaches 0.65 → qualifies
        step = [0]

        def multi_step_assess(participant, session_meta, recent, participant_own_turns=None, log_dir=None):
            pid = participant.id
            assess_calls.append(pid)
            if step[0] == 0:
                # Step 1, single-target: only P2 is assessed
                return ParticipantEngagementAssessment(
                    participant_id=pid,
                    wants_to_speak=True,
                    urgency=0.8,
                    addressed_to="Carol",
                )
            else:
                # Step 2, auction: everyone below urgency threshold
                return ParticipantEngagementAssessment(
                    participant_id=pid,
                    wants_to_speak=True,
                    urgency=0.5,
                    intent="respond",
                )

        monkeypatch.setattr("core.orchestrator.assess_engagement", multi_step_assess)

        orch = _make_orchestrator(state, tmp_path)
        monkeypatch.setattr(FocusGroupOrchestrator, "run_participant_turn", _fake_participant_turn_factory(participant_calls))
        monkeypatch.setattr(FocusGroupOrchestrator, "run_moderator_turn", _fake_moderator_turn())

        # Step 1: direct handoff to P2
        step[0] = 0
        orch.run_conversation_step()

        # Verify: last_engagement_round has P2's addressed_to="Carol"
        assert len(state.group_state.last_engagement_round) == 1
        assert state.group_state.last_engagement_round[0].participant_id == "P2"
        assert state.group_state.last_engagement_round[0].addressed_to == "Carol"

        # Step 2: auction with no direct target — P3 should get peer-address bonus
        step[0] = 1
        _seed_last_mod(state, target=None, intervention_mode="observe")

        assess_calls.clear()
        participant_calls.clear()
        orch.run_conversation_step()

        # All 4 assessed in auction
        assert len(assess_calls) == 4
        # P3 won via peer-address bonus
        assert participant_calls == ["P3"], (
            f"Expected P3 to win via peer-address bonus, got {participant_calls}"
        )


class TestAddressedToNullIsOk:
    def test_addressed_to_null_is_ok(self, monkeypatch, tmp_path):
        """
        Single-target step where the target's addressed_to is None.
        No exception; peer-address does not fire next step; step still selects normally.
        """
        participants = _make_participants("Alice", "Bob", "Carol")
        state = _make_state(participants)
        _seed_last_mod(state, target="Bob", intervention_mode="speak")

        assess_calls: list[str] = []
        participant_calls: list[str] = []
        step = [0]

        def null_addressed_assess(participant, session_meta, recent, participant_own_turns=None, log_dir=None):
            pid = participant.id
            assess_calls.append(pid)
            if step[0] == 0:
                return ParticipantEngagementAssessment(
                    participant_id=pid, wants_to_speak=True, urgency=0.8, addressed_to=None
                )
            else:
                # Give P3 high urgency for step 2 to confirm normal auction
                if pid == "P3":
                    return ParticipantEngagementAssessment(
                        participant_id=pid, wants_to_speak=True, urgency=0.9, intent="respond"
                    )
                return ParticipantEngagementAssessment(
                    participant_id=pid, wants_to_speak=False, urgency=0.0
                )

        monkeypatch.setattr("core.orchestrator.assess_engagement", null_addressed_assess)
        orch = _make_orchestrator(state, tmp_path)
        monkeypatch.setattr(FocusGroupOrchestrator, "run_participant_turn", _fake_participant_turn_factory(participant_calls))
        monkeypatch.setattr(FocusGroupOrchestrator, "run_moderator_turn", _fake_moderator_turn())

        # Step 1: no exception even with addressed_to=None
        step[0] = 0
        result = orch.run_conversation_step()
        assert result["selection_mode"] == "moderator_direct_address"
        assert state.group_state.last_engagement_round[0].addressed_to is None

        # Step 2: peer-address does not fire (no addressed_to to follow); P3 wins by own urgency
        step[0] = 1
        _seed_last_mod(state, target=None, intervention_mode="observe")
        assess_calls.clear()
        participant_calls.clear()
        orch.run_conversation_step()

        # Normal auction — peer-address did not interfere
        assert len(assess_calls) == 3
        assert participant_calls == ["P3"]

    def test_addressed_to_null_schema_constructors(self):
        """
        Pure schema assertions: addressed_to=None by default; absent from dict → None.
        No orchestrator, no API.
        """
        # Explicit construction
        a = ParticipantEngagementAssessment(
            participant_id="P1", wants_to_speak=False, urgency=0.0
        )
        assert a.addressed_to is None

        # Mirroring data.get("addressed_to") when key is absent
        data = {"participant_id": "P1", "wants_to_speak": False, "urgency": 0.0}
        b = ParticipantEngagementAssessment(**data)
        assert b.addressed_to is None


@pytest.mark.parametrize("n_participants", [5])
class TestCallCountSavings:
    def test_call_count_savings(self, n_participants, monkeypatch, tmp_path):
        """
        Regression guard: N participants → 1 assess_engagement call for single-target,
        N calls for an equivalent auction step.
        """
        names = [f"Person{i}" for i in range(1, n_participants + 1)]
        participants = _make_participants(*names)
        state = _make_state(participants)

        # Single-target step: target = P2 (Person2)
        _seed_last_mod(state, target="Person2", intervention_mode="speak")

        assess_calls_single: list[str] = []
        participant_calls: list[str] = []

        monkeypatch.setattr(
            "core.orchestrator.assess_engagement",
            _fake_assess_factory(assess_calls_single),
        )

        orch = _make_orchestrator(state, tmp_path)
        monkeypatch.setattr(FocusGroupOrchestrator, "run_participant_turn", _fake_participant_turn_factory(participant_calls))
        monkeypatch.setattr(FocusGroupOrchestrator, "run_moderator_turn", _fake_moderator_turn())

        orch.run_conversation_step()
        assert len(assess_calls_single) == 1, (
            f"Single-target: expected 1 assess_engagement call, got {len(assess_calls_single)}"
        )

        # Auction step: no target
        _seed_last_mod(state, target=None, intervention_mode="observe")
        assess_calls_auction: list[str] = []
        participant_calls.clear()
        monkeypatch.setattr(
            "core.orchestrator.assess_engagement",
            _fake_assess_factory(assess_calls_auction),
        )

        orch.run_conversation_step()
        assert len(assess_calls_auction) == n_participants, (
            f"Auction: expected {n_participants} assess_engagement calls, got {len(assess_calls_auction)}"
        )
