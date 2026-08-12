"""
Application-level retry for rate-limit (429) responses.

WHY THIS EXISTS
    Before this module, a 429 was not handled anywhere in core/ (grep for
    `429|RateLimitError|APIStatusError|max_retries|except anthropic` across
    core/*.py returned zero matches). The only retry in the codebase is the
    JSON/Pydantic one inside call_moderator — it fires when _try_parse returns
    None, and a rate-limit error never reaches it: RateLimitError propagates
    straight out of the API call and kills the whole session, losing that
    replicate. That matters most when running sessions concurrently, where the
    combined request rate is a multiple of a single session's.

RELATIONSHIP TO THE EXISTING RETRY
    This is a NEW, ADDITIVE layer wrapped *around* the raw API call, strictly
    outside the JSON/Pydantic retry. That path is untouched: a malformed
    response still gets its targeted correction prompt and one retry, exactly
    as before.

RELATIONSHIP TO THE SDK'S OWN RETRIES
    The Anthropic SDK already retries 429/5xx internally (DEFAULT_MAX_RETRIES=2)
    before raising to application code. So by the time we see a RateLimitError,
    the SDK has already backed off and retried twice. This layer is therefore a
    second line of defence against a *sustained* limit, not the first response
    to a brief blip — which is why 3 retries is enough and there is no case for
    retrying indefinitely.
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import anthropic

from core.api_logging import append_api_log

T = TypeVar("T")

# Retries at THIS layer, on top of the SDK's own internal DEFAULT_MAX_RETRIES=2.
MAX_RATE_LIMIT_RETRIES = 3

_BACKOFF_START_SECONDS = 10.0
_BACKOFF_CAP_SECONDS = 60.0
_JITTER_SECONDS = 2.0


def _retry_after_seconds(exc: anthropic.RateLimitError) -> float | None:
    """
    Read the server's `retry-after` hint if the SDK exposed one.

    Deliberately defensive: the header is optional, may be absent on a
    synthesised/mocked exception, and is a string. Anything unusable falls
    through to exponential backoff rather than raising inside the error path.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        raw = headers.get("retry-after")
    except Exception:                                    # noqa: BLE001
        return None
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None                                      # HTTP-date form: ignore
    return value if value >= 0 else None


def _delay_for(attempt: int, exc: anthropic.RateLimitError) -> tuple[float, str]:
    """Return (seconds_to_sleep, reason) for this attempt. attempt is 1-based."""
    hinted = _retry_after_seconds(exc)
    if hinted is not None:
        return hinted + random.uniform(0, _JITTER_SECONDS), "retry_after_header"
    backoff = min(_BACKOFF_START_SECONDS * (2 ** (attempt - 1)), _BACKOFF_CAP_SECONDS)
    return backoff, "exponential_backoff"


def call_with_rate_limit_retry(
    make_call: Callable[[], T],
    *,
    log_dir: Path | None = None,
    source_function: str | None = None,
    role: str = "system",
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
    _sleep: Callable[[float], None] = time.sleep,
) -> T:
    """
    Invoke `make_call()`, retrying on 429 up to MAX_RATE_LIMIT_RETRIES times.

    Every non-RateLimitError propagates untouched on the first raise — this
    layer must not silently absorb connection errors, auth failures or
    validation problems, which have their own handling (or deliberately have
    none).

    After the retries are exhausted the original exception is re-raised exactly
    as before this module existed, so run_full_session.py's
    `finally: save_transcript()` backstop still behaves identically.

    `_sleep` is injectable purely so tests can run instantly without patching
    time globally.
    """
    attempt = 0
    while True:
        try:
            return make_call()
        except anthropic.RateLimitError as exc:
            attempt += 1
            if attempt > MAX_RATE_LIMIT_RETRIES:
                # Exhausted — re-raise unchanged.
                if log_dir is not None:
                    append_api_log(
                        log_dir=log_dir,
                        event_type="rate_limit_exhausted",
                        role=role,
                        model=model,
                        source_function=source_function,
                        token_accounting=False,
                        metadata={
                            **(metadata or {}),
                            "error_type": "rate_limit_exhausted",
                            "attempt_number": attempt,
                            "max_retries": MAX_RATE_LIMIT_RETRIES,
                        },
                    )
                raise

            delay, reason = _delay_for(attempt, exc)
            if log_dir is not None:
                append_api_log(
                    log_dir=log_dir,
                    event_type="rate_limit_retry",
                    role=role,
                    model=model,
                    source_function=source_function,
                    token_accounting=False,
                    metadata={
                        **(metadata or {}),
                        "error_type": "rate_limit_retry",
                        "attempt_number": attempt,
                        "max_retries": MAX_RATE_LIMIT_RETRIES,
                        "sleep_seconds": round(delay, 2),
                        "delay_source": reason,
                    },
                )
            _sleep(delay)
