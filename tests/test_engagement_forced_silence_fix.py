"""
Tests for the assess_engagement forced-silence bias fix.

THE BIAS THIS CLOSES:
    assess_engagement had no retry. Any JSON/Pydantic fault returned
    stay_silent immediately, so a participant lost their turn to a technical
    fault rather than a modelled choice. Measured across 12 completed sessions:
    44 forced silences, 1.4%-9.4% of assessments per session, present in every
    single session. That contaminates any analysis of who spoke, who dominated
    and who stayed quiet — and `validation_fallback` never caught it, because
    that metric only covers the moderator.

    Two further defects found in the same path:
      * `bool(data.get("wants_to_speak", False))` turned a MISSING key into a
        silent False, logging nothing at all.
      * the failure log hardcoded `error_message: "validation error"` instead of
        the real exception, which is why the original 44 could not be diagnosed.

THE FIX (three layers):
    1. Salvage audit-only fields (unrecognised `intent` -> None, out-of-range
       `urgency` -> clamped) instead of discarding the turn.
    2. One targeted-correction retry when the response is genuinely unusable,
       mirroring the long-standing call_moderator pattern.
    3. Silence only if the retry also fails, logged as
       `engagement_fallback_after_retry` so the residual rate stays measurable.
"""

from __future__ import annotations

import io
import json

import pytest
from unittest.mock import MagicMock, patch

from core.participant_agent import (
    _VALID_INTENTS,
    _try_build_assessment,
    assess_engagement,
)
from core.session_state import ParticipantState, SessionMeta


# ---------------------------------------------------------------------------
# Unit level: _try_build_assessment
# ---------------------------------------------------------------------------

def test_valid_response_passes_untouched():
    a, corr, err, coerced = _try_build_assessment("P1", json.dumps({
        "wants_to_speak": True, "urgency": 0.7, "hook": "meat and mates",
        "addressed_to": "Will", "intent": "challenge",
    }))
    assert a is not None and err is None and coerced == []
    assert a.wants_to_speak is True and a.urgency == 0.7
    assert a.intent == "challenge" and a.addressed_to == "Will"


def test_unrecognised_intent_is_nulled_not_silenced():
    """
    THE headline case. An intent outside the enum used to cost the participant
    their turn. intent is audit-only (except 'challenge'), so it must be nulled
    while wants_to_speak survives.
    """
    a, corr, err, coerced = _try_build_assessment("P1", json.dumps({
        "wants_to_speak": True, "urgency": 0.8, "hook": "h", "intent": "elaborate",
    }))
    assert a is not None, "participant was silenced over an audit-only field"
    assert a.wants_to_speak is True, "the load-bearing signal must survive"
    assert a.urgency == 0.8
    assert a.intent is None
    assert any("intent" in c for c in coerced)


@pytest.mark.parametrize("bad,expected", [(1.5, 1.0), (-0.2, 0.0), (99, 1.0)])
def test_out_of_range_urgency_is_clamped_not_silenced(bad, expected):
    a, corr, err, coerced = _try_build_assessment("P1", json.dumps({
        "wants_to_speak": True, "urgency": bad, "hook": "h", "intent": "respond",
    }))
    assert a is not None
    assert a.urgency == expected
    assert a.wants_to_speak is True
    assert any("urgency" in c for c in coerced)


def test_non_numeric_urgency_is_salvaged():
    a, _, _, coerced = _try_build_assessment("P1", json.dumps({
        "wants_to_speak": True, "urgency": "high", "hook": "h", "intent": "respond",
    }))
    assert a is not None and a.wants_to_speak is True and a.urgency == 0.0
    assert any("urgency" in c for c in coerced)


def test_missing_wants_to_speak_triggers_retry_not_a_silent_false():
    """
    The old code turned a missing key into False with no log line at all. It
    must now be reported as unusable so the caller retries.
    """
    a, corr, err, _ = _try_build_assessment("P1", json.dumps({
        "urgency": 0.9, "hook": "h", "intent": "respond",
    }))
    assert a is None
    assert err == "missing_wants_to_speak"
    assert "wants_to_speak" in corr


def test_string_boolean_is_accepted():
    a, _, _, _ = _try_build_assessment("P1", json.dumps({
        "wants_to_speak": "true", "urgency": 0.5, "hook": "h", "intent": "respond",
    }))
    assert a is not None and a.wants_to_speak is True


def test_malformed_json_reports_parse_error_with_correction():
    a, corr, err, _ = _try_build_assessment("P1", "not json at all")
    assert a is None and err == "json_parse_error"
    assert "JSON" in corr


def test_markdown_fences_are_stripped():
    a, _, err, _ = _try_build_assessment("P1", '```json\n{"wants_to_speak": true, '
                                               '"urgency": 0.3, "hook": "h", '
                                               '"intent": "respond"}\n```')
    assert a is not None and err is None


def test_every_valid_intent_is_accepted():
    for intent in _VALID_INTENTS:
        a, _, _, coerced = _try_build_assessment("P1", json.dumps({
            "wants_to_speak": False, "urgency": 0.0, "hook": "", "intent": intent,
        }))
        assert a is not None and a.intent == intent, intent
        assert coerced == []


def test_genuine_stay_silent_is_preserved():
    """A real modelled silence must NOT be confused with a forced one."""
    a, _, err, coerced = _try_build_assessment("P1", json.dumps({
        "wants_to_speak": False, "urgency": 0.1, "hook": "", "intent": "stay_silent",
    }))
    assert a is not None and err is None and coerced == []
    assert a.wants_to_speak is False and a.intent == "stay_silent"


# ---------------------------------------------------------------------------
# Integration level: assess_engagement retry behaviour
# ---------------------------------------------------------------------------

def _participant():
    return ParticipantState(
        id="mm_fg4_mark", name="Mark", profile_summary="Mark, 52, Male.",
        agent_payload={"persona": {"demographics": {"name": "Mark", "age": 52,
                                                    "gender": "Male", "location": {}}},
                       "simulation_config": {"model": "claude-haiku-4-5-20251001"}},
    )


def _meta():
    return SessionMeta(
        id="test_session", research_objective="o", topic_domain="d",
        participation_mode="emergent", temperature=1.0,
        participant_collective_identity="men in the UK",
        moderator_knowledge_brief="brief",
    )


def _resp(text, tin=10, tout=5):
    m = MagicMock()
    m.content = [MagicMock(text=text)]
    m.usage = MagicMock(input_tokens=tin, output_tokens=tout)
    return m


def _rows(tmp_path):
    p = tmp_path / "api_calls.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


GOOD = json.dumps({"wants_to_speak": True, "urgency": 0.9,
                   "hook": "I disagree about Newcastle", "intent": "challenge"})


def test_unusable_first_attempt_recovers_on_retry(tmp_path):
    """The core integration case: no forced silence when the retry succeeds."""
    client = MagicMock()
    client.messages.create.side_effect = [_resp("garbage not json"), _resp(GOOD)]

    with patch("core.participant_agent.anthropic.Anthropic", return_value=client):
        out = assess_engagement(_participant(), _meta(), [], [], log_dir=tmp_path)

    assert client.messages.create.call_count == 2, "retry did not fire"
    assert out.wants_to_speak is True, "participant was silenced despite a good retry"
    assert out.urgency == 0.9

    rows = _rows(tmp_path)
    assert any(r.get("error_type") == "recovered_on_retry" for r in rows), rows
    assert not any(r.get("error_type") == "engagement_fallback_after_retry"
                   for r in rows)


def test_retry_prompt_carries_the_bad_output_and_a_correction(tmp_path):
    client = MagicMock()
    client.messages.create.side_effect = [_resp("nope"), _resp(GOOD)]

    with patch("core.participant_agent.anthropic.Anthropic", return_value=client):
        assess_engagement(_participant(), _meta(), [], [], log_dir=tmp_path)

    msgs = client.messages.create.call_args_list[1].kwargs["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"] == "nope", "the failed output must be shown back"
    assert "JSON" in msgs[2]["content"]


def test_both_attempts_failing_silences_but_is_logged_distinctly(tmp_path):
    client = MagicMock()
    client.messages.create.side_effect = [_resp("bad"), _resp("still bad")]

    with patch("core.participant_agent.anthropic.Anthropic", return_value=client):
        out = assess_engagement(_participant(), _meta(), [], [], log_dir=tmp_path)

    assert client.messages.create.call_count == 2
    assert out.wants_to_speak is False and out.intent == "stay_silent"
    rows = _rows(tmp_path)
    fb = [r for r in rows if r.get("error_type") == "engagement_fallback_after_retry"]
    assert len(fb) == 1, "the residual forced silence must remain measurable"
    assert fb[0]["first_attempt_error_type"] == "json_parse_error"


def test_good_first_attempt_makes_no_second_call(tmp_path):
    """The happy path must cost exactly one call — no added spend."""
    client = MagicMock()
    client.messages.create.side_effect = [_resp(GOOD)]

    with patch("core.participant_agent.anthropic.Anthropic", return_value=client):
        out = assess_engagement(_participant(), _meta(), [], [], log_dir=tmp_path)

    assert client.messages.create.call_count == 1
    assert out.wants_to_speak is True
    rows = _rows(tmp_path)
    assert all(r.get("error_type") in ("none", None) for r in rows), rows


def test_salvageable_first_attempt_makes_no_second_call(tmp_path):
    """
    A bad intent is salvaged in-place, so it must NOT trigger a paid retry —
    that is what keeps the fix cost-neutral on the common failure.
    """
    salvageable = json.dumps({"wants_to_speak": True, "urgency": 0.6,
                              "hook": "h", "intent": "agree_strongly"})
    client = MagicMock()
    client.messages.create.side_effect = [_resp(salvageable)]

    with patch("core.participant_agent.anthropic.Anthropic", return_value=client):
        out = assess_engagement(_participant(), _meta(), [], [], log_dir=tmp_path)

    assert client.messages.create.call_count == 1, "salvage should not cost a retry"
    assert out.wants_to_speak is True and out.intent is None
    rows = _rows(tmp_path)
    coerced = [r for r in rows if r.get("fields_coerced")]
    assert coerced, "the coercion must be recorded for audit"
    assert "intent" in coerced[0]["fields_coerced"]


def test_api_exception_still_silences_and_logs(tmp_path):
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")

    with patch("core.participant_agent.anthropic.Anthropic", return_value=client):
        out = assess_engagement(_participant(), _meta(), [], [], log_dir=tmp_path)

    assert out.wants_to_speak is False
    rows = _rows(tmp_path)
    assert any(r.get("error_type") == "engagement_api_error" for r in rows), rows


def test_works_without_log_dir(tmp_path):
    client = MagicMock()
    client.messages.create.side_effect = [_resp("bad"), _resp(GOOD)]
    with patch("core.participant_agent.anthropic.Anthropic", return_value=client):
        out = assess_engagement(_participant(), _meta(), [], [], log_dir=None)
    assert out.wants_to_speak is True
