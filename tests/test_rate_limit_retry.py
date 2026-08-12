"""
Offline tests for the 429 retry layer (core/api_retry.py).

THE GAP THIS CLOSES:
    A 429 was not handled anywhere in core/ — the only retry in the codebase is
    the JSON/Pydantic one inside call_moderator, which fires when _try_parse
    returns None. A RateLimitError never reaches it: it propagated straight out
    of the raw API call and killed the session, losing that replicate. That is
    the failure mode that matters when running sessions concurrently, where the
    combined request rate is a multiple of one session's.

DESIGN UNDER TEST:
    call_with_rate_limit_retry() wraps the raw call ONLY, strictly outside the
    JSON/Pydantic retry. Up to MAX_RATE_LIMIT_RETRIES (3) attempts at this
    layer, on top of the SDK's own internal DEFAULT_MAX_RETRIES=2. Honours a
    `retry-after` header when present, exponential backoff (10s, doubling,
    capped 60s) when not, and re-raises unchanged once exhausted.

No network calls and no real sleeping — `_sleep` is injected so the tests run
instantly.
"""

from __future__ import annotations

import io
import json

import anthropic
import httpx
import pytest
from unittest.mock import MagicMock, patch

from core.api_retry import (
    MAX_RATE_LIMIT_RETRIES,
    call_with_rate_limit_retry,
)


def _rate_limit_error(retry_after: str | None = None) -> anthropic.RateLimitError:
    """A real RateLimitError, optionally carrying a retry-after header."""
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    response = httpx.Response(
        429,
        headers=headers,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    return anthropic.RateLimitError("rate limited", response=response, body=None)


def _log_rows(tmp_path):
    p = tmp_path / "api_calls.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


# ---------------------------------------------------------------------------
# A.4.1 — one 429 then success
# ---------------------------------------------------------------------------

def test_single_429_then_success_retries_once_and_returns(tmp_path):
    calls = []
    sleeps = []

    def make_call():
        calls.append(1)
        if len(calls) == 1:
            raise _rate_limit_error()
        return "OK"

    result = call_with_rate_limit_retry(
        make_call, log_dir=tmp_path, source_function="call_moderator",
        model="claude-sonnet-4-6", _sleep=sleeps.append,
    )

    assert result == "OK"
    assert len(calls) == 2, "should have retried exactly once"
    assert len(sleeps) == 1

    rows = _log_rows(tmp_path)
    retries = [r for r in rows if r.get("error_type") == "rate_limit_retry"]
    assert len(retries) == 1, rows
    assert retries[0]["attempt_number"] == 1
    assert retries[0]["source_function"] == "call_moderator"
    assert retries[0]["event_type"] == "rate_limit_retry"
    # Nothing was exhausted — the session survived.
    assert not [r for r in rows if r.get("error_type") == "rate_limit_exhausted"]


def test_no_429_makes_no_log_entries_and_does_not_sleep(tmp_path):
    """The happy path must be untouched — no cost when the limit isn't hit."""
    sleeps = []
    result = call_with_rate_limit_retry(
        lambda: "fine", log_dir=tmp_path, source_function="call_participant",
        _sleep=sleeps.append,
    )
    assert result == "fine"
    assert sleeps == []
    assert _log_rows(tmp_path) == []


# ---------------------------------------------------------------------------
# A.4.2 — sustained 429s exhaust and re-raise
# ---------------------------------------------------------------------------

def test_sustained_429_raises_after_cap_with_expected_log_trail(tmp_path):
    calls = []
    sleeps = []

    def make_call():
        calls.append(1)
        raise _rate_limit_error()

    with pytest.raises(anthropic.RateLimitError):
        call_with_rate_limit_retry(
            make_call, log_dir=tmp_path, source_function="assess_engagement",
            _sleep=sleeps.append,
        )

    # 1 initial attempt + MAX retries, then re-raise.
    assert len(calls) == MAX_RATE_LIMIT_RETRIES + 1
    assert len(sleeps) == MAX_RATE_LIMIT_RETRIES

    rows = _log_rows(tmp_path)
    retries = [r for r in rows if r.get("error_type") == "rate_limit_retry"]
    exhausted = [r for r in rows if r.get("error_type") == "rate_limit_exhausted"]
    assert len(retries) == MAX_RATE_LIMIT_RETRIES, rows
    assert [r["attempt_number"] for r in retries] == list(range(1, MAX_RATE_LIMIT_RETRIES + 1))
    assert len(exhausted) == 1, "exhaustion must be distinguishable in the log"


def test_backoff_is_exponential_and_capped(tmp_path):
    sleeps = []

    def make_call():
        raise _rate_limit_error()

    with pytest.raises(anthropic.RateLimitError):
        call_with_rate_limit_retry(make_call, log_dir=tmp_path, _sleep=sleeps.append)

    assert sleeps == [10.0, 20.0, 40.0], sleeps
    assert all(s <= 60.0 for s in sleeps)


def test_retry_after_header_is_honoured_over_backoff(tmp_path):
    sleeps = []
    calls = []

    def make_call():
        calls.append(1)
        if len(calls) == 1:
            raise _rate_limit_error(retry_after="7")
        return "OK"

    assert call_with_rate_limit_retry(
        make_call, log_dir=tmp_path, _sleep=sleeps.append) == "OK"

    # 7s plus up to 2s jitter — and crucially NOT the 10s backoff default.
    assert 7.0 <= sleeps[0] <= 9.0, sleeps
    rows = _log_rows(tmp_path)
    assert rows[0]["delay_source"] == "retry_after_header"


def test_unparseable_retry_after_falls_back_to_backoff(tmp_path):
    """An HTTP-date retry-after must not raise inside the error path."""
    sleeps = []
    calls = []

    def make_call():
        calls.append(1)
        if len(calls) == 1:
            raise _rate_limit_error(retry_after="Wed, 21 Oct 2026 07:28:00 GMT")
        return "OK"

    assert call_with_rate_limit_retry(
        make_call, log_dir=tmp_path, _sleep=sleeps.append) == "OK"
    assert sleeps == [10.0]
    assert _log_rows(tmp_path)[0]["delay_source"] == "exponential_backoff"


# ---------------------------------------------------------------------------
# Only 429s are caught — everything else propagates immediately
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exc", [
    anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")),
    ValueError("not an API problem"),
])
def test_non_rate_limit_errors_propagate_immediately(tmp_path, exc):
    calls = []

    def make_call():
        calls.append(1)
        raise exc

    with pytest.raises(type(exc)):
        call_with_rate_limit_retry(make_call, log_dir=tmp_path, _sleep=lambda s: None)

    assert len(calls) == 1, "must not retry non-429 failures"
    assert _log_rows(tmp_path) == []


def test_works_without_a_log_dir(tmp_path):
    """log_dir is optional across the codebase — must not crash when absent."""
    calls = []

    def make_call():
        calls.append(1)
        if len(calls) == 1:
            raise _rate_limit_error()
        return "OK"

    assert call_with_rate_limit_retry(make_call, log_dir=None, _sleep=lambda s: None) == "OK"


# ---------------------------------------------------------------------------
# A.4.3 — the existing JSON/Pydantic retry path still works unchanged
# ---------------------------------------------------------------------------

def test_pydantic_retry_path_unaffected_by_the_new_layer(tmp_path):
    """
    Regression check: a malformed first response must still trigger the
    targeted-correction retry inside call_moderator (the turn-25 path in
    macho_meals_fg1_run01) and succeed on the second attempt. The 429 layer
    wraps the raw call and must be invisible here.
    """
    from core.moderator_brain import call_moderator
    from tests.test_initial_session_plan_capture import BODY_WITH_PLAN, _config
    from core.orchestrator import _build_state_from_config
    from core.session_state import TriggerEvent, TriggerEventType

    state = _build_state_from_config(_config())

    bad = MagicMock()
    bad.content = [MagicMock(text="this is not JSON at all")]
    bad.usage = MagicMock(input_tokens=10, output_tokens=5)
    good = MagicMock()
    good.content = [MagicMock(text=json.dumps(BODY_WITH_PLAN))]
    good.usage = MagicMock(input_tokens=10, output_tokens=5)

    client = MagicMock()
    client.messages.create.side_effect = [bad, good]

    trigger = TriggerEvent(
        type=TriggerEventType.SESSION_START, speaker_id=None, speaker_name=None,
        content="start", turn_number=0, follow_up_count_this_question=0,
    )

    with patch("core.moderator_brain.anthropic.Anthropic", return_value=client):
        response, history = call_moderator(
            state=state, trigger_event=trigger, conversation_history=[],
            is_opening_turn=True, log_dir=tmp_path,
        )

    assert client.messages.create.call_count == 2, "validation retry did not fire"
    assert response.validation_fallback is False
    assert response.moderator_decision.action.value == "ask_initial_to_group"

    rows = _log_rows(tmp_path)
    # The failure was a parse error, NOT a rate-limit one.
    assert any(r.get("error_type") == "json_parse_error" for r in rows), rows
    assert not [r for r in rows if r.get("error_type") == "rate_limit_retry"]
