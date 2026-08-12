"""
Regression tests for initial_session_plan capture in
FocusGroupOrchestrator.run_opening().

THE BUG (2026-07-27):
    run_opening() re-parses the raw assistant text to recover
    initial_session_plan, because ModeratorAPIResponse has no such field and
    Pydantic's default extra='ignore' drops it. That re-parse called
    json.loads() on the raw string directly, while moderator_brain._try_parse()
    stripped markdown fences before parsing the SAME string.

    So when the model wrapped its response in ```json fences:
      - _try_parse() stripped them  -> decision parsed, session ran normally
      - run_opening()'s json.loads() -> JSONDecodeError -> except Exception: pass
    and the plan vanished silently.

    Downstream, _build_section_budget_status() returned the innocuous-looking
    "(time budget not yet available)" on every turn, so nothing ever looked
    wrong. Confirmed empty in initial_session_plan across all 88 runs in
    output/session_logs/, including macho_meals_fg1_run01 (opening turn:
    2,428 output tokens, parse_success=True, error_type='none' — truncation
    excluded) and sandbox_minimal_prompt_budget_01 (a different, older,
    already-fixed failure: truncation at the old 1500-token cap).

WHY IT SURVIVED 88 RUNS:
    No test ever exercised this path. test_section_budget_status_arithmetic
    builds initial_session_plan BY HAND and asserts the formatting — it passes
    whether or not capture works. These tests deliberately drive run_opening()
    end to end so that blind spot cannot recur.

Offline only: call_moderator is mocked. Zero network calls, zero API calls.
"""

from __future__ import annotations

import json
import logging

import pytest
from unittest.mock import MagicMock

from core.moderator_brain import strip_markdown_fences
from core.orchestrator import FocusGroupOrchestrator
from core.prompt_renderer import _build_section_budget_status
from core.session_state import ModeratorAPIResponse, ModeratorDecisionResponse

PLAN = {
    "thematisation_approach": "Men in the UK reflecting on food choices.",
    "priority_research_areas": ["gendered meanings", "social acceptability"],
    "time_budget": {
        "total_minutes": 45,
        "total_word_budget": 4500,
        "budget_rationale": "main_topic sections weighted heaviest.",
        "per_section": [
            {"section_index": 0, "section_label": "Intro",
             "section_phase": "intro", "word_budget": 300, "turn_budget": 3},
        ],
    },
}

DECISION = {
    "situation_assessment": "Session is initialising.",
    "intervention_mode": "speak",
    "dominant_signal": "guide_question_pending",
    "action": "ask_initial_to_group",
    "target": "group",
    "probe_type": None,
    "follow_up_intensity": None,
    "queued_next_action": None,
}

BODY_WITH_PLAN = {"initial_session_plan": PLAN,
                  "moderator_decision": DECISION,
                  "utterance": "Hi everyone, thanks so much for joining today."}
BODY_NO_PLAN = {"moderator_decision": DECISION,
                "utterance": "Hi everyone, thanks so much for joining today."}


def _config(time_budget_tracking: bool = True) -> dict:
    return {
        "session_id": "plan_capture_test",
        "research_objective": "Test",
        "topic_domain": "Test",
        "participation_mode": "emergent",
        "temperature": 1.0,
        "participant_collective_identity": "test participants",
        "moderator_knowledge_brief": "brief",
        "researcher_notes": "",
        "time_budget_tracking_enabled": time_budget_tracking,
        "participants": [
            {"id": "P1", "name": "Alice", "profile_summary": ""},
            {"id": "P2", "name": "Bob", "profile_summary": ""},
        ],
        "discussion_guide": [
            {"section_index": 0, "section_label": "Intro", "section_phase": "intro",
             "section_purpose": "Test", "scripted_question": "Test?",
             "probing_depth_ceiling": "light", "stimulus": None},
        ],
    }


def _parsed_response() -> ModeratorAPIResponse:
    return ModeratorAPIResponse(
        moderator_decision=ModeratorDecisionResponse(**DECISION),
        utterance="Hi everyone, thanks so much for joining today.",
        validation_fallback=False,
    )


def _run_opening_with_raw(monkeypatch, tmp_path, raw_text: str,
                          time_budget_tracking: bool = True) -> FocusGroupOrchestrator:
    """
    Drive the REAL run_opening() with a mocked call_moderator whose returned
    history carries `raw_text` as the assistant message — exactly the shape
    core/moderator_brain.py:285 produces on the success path.
    """
    monkeypatch.setattr("core.orchestrator._OUTPUT_ROOT", tmp_path)
    orch = FocusGroupOrchestrator(_config(time_budget_tracking))
    monkeypatch.setattr(
        "core.orchestrator.call_moderator",
        MagicMock(return_value=(
            _parsed_response(),
            [{"role": "user", "content": "<opening prompt>"},
             {"role": "assistant", "content": raw_text}],
        )),
    )
    orch.run_opening()
    return orch


# ---------------------------------------------------------------------------
# The 2x2: {fenced, bare} x {plan present, plan absent}
# ---------------------------------------------------------------------------

def test_fenced_response_with_plan_is_captured(monkeypatch, tmp_path):
    """THE regression case — this is what silently failed on every run."""
    raw = "```json\n" + json.dumps(BODY_WITH_PLAN, indent=2) + "\n```"
    orch = _run_opening_with_raw(monkeypatch, tmp_path, raw)

    plan = orch.state.session_meta.initial_session_plan
    assert isinstance(plan, dict), "fenced response: plan was dropped"
    assert plan["time_budget"]["total_minutes"] == 45
    assert plan["time_budget"]["total_word_budget"] == 4500


def test_bare_response_with_plan_is_captured(monkeypatch, tmp_path):
    raw = json.dumps(BODY_WITH_PLAN, indent=2)
    orch = _run_opening_with_raw(monkeypatch, tmp_path, raw)

    plan = orch.state.session_meta.initial_session_plan
    assert isinstance(plan, dict)
    assert plan["time_budget"]["per_section"][0]["word_budget"] == 300


def test_fenced_response_without_plan_leaves_none_and_warns(monkeypatch, tmp_path, caplog):
    """Fenced JSON parses cleanly but carries no plan — distinct from a parse failure."""
    raw = "```json\n" + json.dumps(BODY_NO_PLAN, indent=2) + "\n```"
    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        orch = _run_opening_with_raw(monkeypatch, tmp_path, raw)

    assert orch.state.session_meta.initial_session_plan is None
    assert any("carried no initial_session_plan" in r.message for r in caplog.records), caplog.text


def test_bare_response_without_plan_leaves_none_and_warns(monkeypatch, tmp_path, caplog):
    raw = json.dumps(BODY_NO_PLAN, indent=2)
    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        orch = _run_opening_with_raw(monkeypatch, tmp_path, raw)

    assert orch.state.session_meta.initial_session_plan is None
    assert any("carried no initial_session_plan" in r.message for r in caplog.records), caplog.text


# ---------------------------------------------------------------------------
# The failure that actually occurred in sandbox_minimal_prompt_budget_01
# ---------------------------------------------------------------------------

def test_truncated_json_does_not_crash_and_warns_distinguishably(monkeypatch, tmp_path, caplog):
    """
    Opening response cut off mid-object (what truncation at the old 1500-token
    cap produced). Must not raise out of run_opening(), must leave the plan
    None, and must log the JSON-decode case distinguishably from 'valid JSON,
    no plan'.
    """
    raw = json.dumps(BODY_WITH_PLAN, indent=2)[:400]     # cut mid-object
    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        orch = _run_opening_with_raw(monkeypatch, tmp_path, raw)

    assert orch.state.session_meta.initial_session_plan is None
    msgs = [r.message for r in caplog.records]
    assert any("not valid JSON even after fence-stripping" in m for m in msgs), caplog.text
    assert not any("carried no initial_session_plan" in m for m in msgs), (
        "truncation must not be reported as a missing-key case"
    )


# ---------------------------------------------------------------------------
# Non-fatality: the side channel must never abort the opening turn
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,label", [
    (json.dumps([1, 2, 3]), "valid JSON array"),
    (json.dumps("just a string"), "valid JSON scalar"),
    ("", "empty string"),
    ("```json\n```", "empty fenced block"),
])
def test_non_object_responses_do_not_abort_the_opening_turn(monkeypatch, tmp_path, raw, label):
    """
    A valid-JSON-but-not-an-object response would make raw_data.get() raise
    AttributeError. At turn 0 that would kill a live session (~50 min, real
    spend). run_opening() must survive and simply carry no plan.
    """
    orch = _run_opening_with_raw(monkeypatch, tmp_path, raw)
    assert orch.state.session_meta.initial_session_plan is None, label


# ---------------------------------------------------------------------------
# End-to-end: a captured plan actually reaches the per-turn budget line
# ---------------------------------------------------------------------------

def test_captured_plan_produces_a_real_budget_line(monkeypatch, tmp_path):
    """
    The assertion whose absence let this persist for 88 runs: not just that
    the field is set, but that _build_section_budget_status() stops returning
    the placeholder.
    """
    raw = "```json\n" + json.dumps(BODY_WITH_PLAN, indent=2) + "\n```"
    orch = _run_opening_with_raw(monkeypatch, tmp_path, raw)

    line = _build_section_budget_status(orch.state)
    assert line != "(time budget not yet available)"
    assert "of 45 minutes estimated elapsed" in line, line
    assert "/300 words" in line, line


def test_uncaptured_plan_still_yields_the_placeholder(monkeypatch, tmp_path):
    """Control for the test above — the placeholder is correct when there is no plan."""
    orch = _run_opening_with_raw(monkeypatch, tmp_path, json.dumps(BODY_NO_PLAN))
    assert _build_section_budget_status(orch.state) == "(time budget not yet available)"


# ---------------------------------------------------------------------------
# The config-intent guard
# ---------------------------------------------------------------------------

def test_tracking_enabled_but_no_plan_warns_loudly(monkeypatch, tmp_path, caplog):
    """
    Without this, a full billable session runs to completion with the budget
    mechanism silently inert — exactly what happened on macho_meals_fg1_run01.
    """
    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        _run_opening_with_raw(monkeypatch, tmp_path, json.dumps(BODY_NO_PLAN),
                              time_budget_tracking=True)

    assert any("time_budget_tracking_enabled=True but no initial_session_plan" in r.message
               for r in caplog.records), caplog.text


def test_tracking_disabled_does_not_warn_about_missing_plan(monkeypatch, tmp_path, caplog):
    """No plan is unremarkable when tracking is off — don't cry wolf."""
    with caplog.at_level(logging.WARNING, logger="core.orchestrator"):
        _run_opening_with_raw(monkeypatch, tmp_path, json.dumps(BODY_NO_PLAN),
                              time_budget_tracking=False)

    assert not any("time_budget_tracking_enabled=True" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# The helper itself is now public and shared by both parse paths
# ---------------------------------------------------------------------------

def test_strip_markdown_fences_is_public_and_shared():
    """
    Guards the root cause: both parse paths must use the same unwrapper. If
    someone re-privatises this, orchestrator.py's import breaks loudly rather
    than silently diverging again.
    """
    assert strip_markdown_fences("```json\n{\"a\": 1}\n```") == '{"a": 1}'
    assert strip_markdown_fences('{"a": 1}') == '{"a": 1}'

    import core.orchestrator as orch_mod
    assert orch_mod.strip_markdown_fences is strip_markdown_fences
