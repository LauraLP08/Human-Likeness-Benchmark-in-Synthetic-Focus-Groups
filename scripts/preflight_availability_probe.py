"""
Single minimal availability probe for the frozen evaluator model.

ONE call. No retries, no polling loop. The point is to distinguish, on the first
response, between failure modes that mean very different things:

    401 / 403  authentication, permissions or API key
    404        model or endpoint not available for this project
    429        quota or rate limit
    503        temporary provider unavailability

A 503 is NOT an API-key problem, and the key must not be changed in response to
one. Anything else is misdiagnosis waiting to happen.

The probe sends a 3-token prompt with no temperature and no thinking config, i.e.
the same effective request configuration the evaluation uses, so a success here is
evidence about the configuration actually frozen.

Writes only to analysis/production_evaluation/.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_LOG = _OUT / "preflight_availability_probe.jsonl"

MODEL = "gemini-3.5-flash"
KEY_ENV = "GEMINI_API_KEY_NEXT"


def _load_env() -> None:
    """Read .env without printing or logging any secret."""
    p = _REPO_ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def classify(exc: Exception) -> tuple[str, str]:
    """Map an SDK exception to an explicit, non-interchangeable diagnosis."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc)
    for c in (401, 403, 404, 429, 503, 500, 502, 504):
        if code == c or f" {c} " in f" {text} " or f"{c}," in text or f"code': {c}" in text:
            code = c
            break
    table = {
        401: ("AUTH_ERROR", "401 — authentication failed: the API key is missing, "
                            "malformed or rejected. This IS a key problem."),
        403: ("PERMISSION_ERROR", "403 — authenticated but not permitted: the key or "
                                  "project lacks access to this model. This IS a key/"
                                  "permissions problem."),
        404: ("MODEL_NOT_FOUND", "404 — model or endpoint not available for this "
                                 "project. NOT a key problem; the model id or the "
                                 "project's model access is wrong."),
        429: ("RATE_LIMITED", "429 — quota or rate limit. NOT a key problem and NOT "
                              "provider downtime; the key is valid and the model exists."),
        503: ("PROVIDER_UNAVAILABLE", "503 — temporary provider unavailability. NOT a "
                                      "key problem. DO NOT change the API key; retry later."),
        500: ("PROVIDER_ERROR", "500 — provider-side error. Not a key problem."),
        502: ("PROVIDER_ERROR", "502 — provider-side error. Not a key problem."),
        504: ("PROVIDER_ERROR", "504 — provider-side timeout. Not a key problem."),
    }
    if code in table:
        return table[code]
    return ("UNCLASSIFIED", f"unrecognised failure: {text[:300]}")


def main() -> int:
    _load_env()
    started = datetime.now(UTC).isoformat()
    rec = {
        "probe_utc": started,
        "model": MODEL,
        "key_env": KEY_ENV,
        "key_present": bool(os.environ.get(KEY_ENV)),
        "attempts": 1,
        "retries": 0,
        "temperature_transmitted": False,
        "thinking_config_transmitted": False,
        "effective_config_note": ("temperature and thinking configuration are both "
                                  "left at the model default, unpinned; neither is "
                                  "transmitted"),
    }
    if not rec["key_present"]:
        rec.update(outcome="AUTH_ERROR",
                   diagnosis=f"{KEY_ENV} is not set; no call was attempted",
                   call_made=False)
        _write(rec)
        print(json.dumps(rec, indent=1))
        return 2

    from google import genai
    client = genai.Client(api_key=os.environ[KEY_ENV])
    try:
        resp = client.models.generate_content(model=MODEL, contents="Reply with: OK")
        usage = getattr(resp, "usage_metadata", None)
        rec.update(
            outcome="AVAILABLE",
            call_made=True,
            diagnosis="model responded normally on the first attempt",
            response_text=(getattr(resp, "text", "") or "")[:120],
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            total_tokens=getattr(usage, "total_token_count", None),
        )
        _write(rec)
        print(json.dumps(rec, indent=1))
        return 0
    except Exception as exc:                                   # noqa: BLE001
        outcome, diagnosis = classify(exc)
        rec.update(outcome=outcome, call_made=True, diagnosis=diagnosis,
                   exception_type=type(exc).__name__, exception=str(exc)[:600])
        _write(rec)
        print(json.dumps(rec, indent=1))
        return 3


def _write(rec: dict) -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    with _LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
