"""
Does `gemini-3.5-flash` support BatchGenerateContent for THIS project and API version?

METADATA ONLY. This queries the model's declared capabilities via `models.get` /
`models.list`. It generates no content, submits no job, and never substitutes the
model. If the capability is absent, nothing is sent.

The question is deliberately narrow: not "does the Gemini API have a Batch mode"
(it does), but "does this exact model id expose batchGenerateContent to the key and
API version actually in use". A capability that exists for other models, or for
Vertex but not the Developer API, is not a capability this project has.

Evidence is recorded verbatim — the raw supported-actions list — so the conclusion
can be checked rather than taken on trust.
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
_ARTIFACT = _OUT / "batch_capability_check.json"

MODEL = "gemini-3.5-flash"
KEY_ENV = "GEMINI_API_KEY_NEXT"
BATCH_ACTION_MARKERS = ("batchgeneratecontent", "batch_generate_content")


def load_env() -> None:
    p = _REPO_ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    load_env()
    rec: dict = {
        "checked_utc": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "key_env": KEY_ENV,
        "check_type": "metadata only — no content generated, no job submitted",
    }
    if not os.environ.get(KEY_ENV):
        rec.update(supported=None, conclusion="CANNOT_CHECK",
                   detail=f"{KEY_ENV} not set")
        _ARTIFACT.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        print(json.dumps(rec, indent=1))
        return 2

    from google import genai
    import google.genai as genai_mod
    client = genai.Client(api_key=os.environ[KEY_ENV])
    rec["sdk_version"] = getattr(genai_mod, "__version__", None)

    # 1. Does the SDK expose a batches surface at all?
    batches = getattr(client, "batches", None)
    rec["sdk_exposes_batches_api"] = batches is not None
    rec["sdk_batches_methods"] = sorted(
        m for m in dir(batches) if not m.startswith("_")) if batches else []

    # 2. What does the API say THIS model supports?
    try:
        info = client.models.get(model=MODEL)
        actions = (getattr(info, "supported_actions", None)
                   or getattr(info, "supported_generation_methods", None) or [])
        actions = [str(a) for a in actions]
        rec["model_found"] = True
        rec["supported_actions_raw"] = actions
        rec["input_token_limit"] = getattr(info, "input_token_limit", None)
        rec["output_token_limit"] = getattr(info, "output_token_limit", None)
        rec["model_version"] = getattr(info, "version", None)
        supports = any(any(m in a.lower() for m in BATCH_ACTION_MARKERS) for a in actions)
        rec["declares_batch_generate_content"] = supports
    except Exception as exc:                                    # noqa: BLE001
        rec["model_found"] = False
        rec["models_get_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        rec["declares_batch_generate_content"] = None
        actions = []

    # 3. Cross-check against the model listing, in case get() and list() differ.
    try:
        listed = {}
        for m in client.models.list():
            name = str(getattr(m, "name", "")).split("/")[-1]
            if MODEL in name:
                acts = (getattr(m, "supported_actions", None)
                        or getattr(m, "supported_generation_methods", None) or [])
                listed[name] = [str(a) for a in acts]
        rec["listing_entries_matching_model"] = listed
    except Exception as exc:                                    # noqa: BLE001
        rec["models_list_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    supports = rec.get("declares_batch_generate_content")
    if supports is True:
        rec["conclusion"] = "BATCH_SUPPORTED"
        rec["recommendation"] = "proceed to build the three-request batch preflight"
    elif supports is False:
        rec["conclusion"] = "BATCH_NOT_SUPPORTED"
        rec["recommendation"] = (
            "do not submit anything; recommend a deferred/off-peak synchronous retry")
    else:
        rec["conclusion"] = "UNDETERMINED"
        rec["recommendation"] = "do not submit anything until the capability is known"

    _ARTIFACT.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rec, indent=1, ensure_ascii=False))
    return 0 if supports else 1


if __name__ == "__main__":
    raise SystemExit(main())
