"""
Batch execution of the emergent extractor over U01-U07 / Q3.

Exactly SEVEN requests, one per unit, in ONE batch job. The configuration and prompt
are frozen in emergent_calibration_q3.py and are not re-decided here.

Batch creation is NOT idempotent: once a job exists, this refuses to create another.

    py scripts/emergent_batch_q3.py --manifest    # offline, no call
    py scripts/emergent_batch_q3.py --submit      # ONE job, 7 requests
    py scripts/emergent_batch_q3.py --status
    py scripts/emergent_batch_q3.py --retrieve
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import emergent_calibration_q3 as cal   # noqa: E402

_DIR = cal._DIR
_MANIFEST = _DIR / "batch_manifest_q3.json"
_JOB = _DIR / "batch_job_q3.json"
_RAW = _DIR / "batch_raw_responses_q3.json"
_RESULTS = _DIR / "extraction_results_q3.json"

MODEL = "gemini-3.5-flash"
KEY_ENV = "GEMINI_API_KEY_NEXT"


class BatchError(RuntimeError):
    pass


def _load_env() -> None:
    p = _REPO_ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


# ---------------------------------------------------------------------------
# Manifest — fully offline
# ---------------------------------------------------------------------------

def build_manifest() -> dict:
    cfg = cal.proposed_effective_config()
    if cfg["execution_mode"] != "batch":
        raise BatchError("execution_mode is not batch")
    if cal.prompt_purity_problems():
        raise BatchError(f"prompt is not clean: {cal.prompt_purity_problems()}")

    requests = []
    for unit in cal.UNITS:
        leaks = cal.unit_text_problems(unit)
        if leaks:
            raise BatchError(f"provenance leak in transmitted text: {leaks}")
        text = cal.unit_text(unit)
        tsha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        requests.append({
            "custom_request_key": unit,
            "unit_id": unit,
            "guide_question": cal.GUIDE_QUESTION,
            "n_turns": len(cal.unit_lines(unit)),
            "n_words": len(text.split()),
            "unit_text_sha256": tsha,
            "cache_key": cal.cache_key(tsha, cal.prompt_sha(), cfg),
        })

    keys = [r["cache_key"] for r in requests]
    if len(set(keys)) != len(keys):
        raise BatchError("duplicate cache keys — two units would collide")

    man = {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": cal.CLASSIFICATION,
        "scope": {"units": cal.UNITS, "guide_question": cal.GUIDE_QUESTION},
        "batch_request_id_local": "emergent_calibration_q3_u01_u07",
        "model": MODEL,
        "n_requests": len(requests),
        "prompt_sha256": cal.prompt_sha(),
        "response_schema_sha256": cal.response_schema_sha(),
        "effective_request_config": cfg,
        "requests": requests,
    }
    _atomic(_MANIFEST, man)
    return man


def _assert_manifest_matches_frozen(man: dict) -> None:
    if man["prompt_sha256"] != cal.prompt_sha():
        raise BatchError("manifest prompt hash does not match the frozen prompt")
    if man["response_schema_sha256"] != cal.response_schema_sha():
        raise BatchError("manifest schema hash does not match the transmitted schema")
    if man["effective_request_config"] != cal.proposed_effective_config():
        raise BatchError("manifest effective config drifted from the frozen config")
    if [r["unit_id"] for r in man["requests"]] != cal.UNITS:
        raise BatchError("manifest scope is not exactly U01-U07")


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

def submit() -> dict:
    if _JOB.exists():
        e = json.loads(_JOB.read_text(encoding="utf-8"))
        raise BatchError(
            f"a batch job already exists: {e.get('job_name')!r} created "
            f"{e.get('created_utc')}. Batch creation is NOT idempotent — refusing to "
            f"create another. Use --status.")

    man = json.loads(_MANIFEST.read_text(encoding="utf-8")) if _MANIFEST.exists() \
        else build_manifest()
    _assert_manifest_matches_frozen(man)

    _load_env()
    if not os.environ.get(KEY_ENV):
        raise BatchError(f"{KEY_ENV} is not set")

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ[KEY_ENV])

    cfg = types.GenerateContentConfig(
        system_instruction=cal.EXTRACTION_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=cal.transmitted_response_schema(),
        max_output_tokens=man["effective_request_config"]["max_output_tokens"],
        # temperature and thinking_config are deliberately NOT set.
    )
    inline = [
        {"model": MODEL,
         "contents": [{"parts": [{"text": cal.unit_text(r["unit_id"])}],
                       "role": "user"}],
         "config": cfg,
         "metadata": {"custom_request_key": r["custom_request_key"]}}
        for r in man["requests"]
    ]
    print(f"submitting ONE job with {len(inline)} requests ...")
    job = client.batches.create(
        model=MODEL, src=inline,
        config={"display_name": man["batch_request_id_local"]})

    rec = {
        "created_utc": datetime.now(UTC).isoformat(),
        "job_name": getattr(job, "name", None),
        "display_name": getattr(job, "display_name", None),
        "state": str(getattr(job, "state", None)),
        "model": MODEL,
        "n_requests": len(inline),
        "custom_request_keys": [r["custom_request_key"] for r in man["requests"]],
        "prompt_sha256": man["prompt_sha256"],
        "response_schema_sha256": man["response_schema_sha256"],
        "effective_request_config": man["effective_request_config"],
        "warning": "batch creation is NOT idempotent — never create again for this scope",
    }
    _atomic(_JOB, rec)
    print(f"  job    : {rec['job_name']}")
    print(f"  state  : {rec['state']}")
    return rec


def status() -> dict:
    if not _JOB.exists():
        raise BatchError("no job recorded; nothing to poll")
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    _load_env()
    from google import genai
    client = genai.Client(api_key=os.environ[KEY_ENV])
    job = client.batches.get(name=rec["job_name"])
    st = str(getattr(job, "state", None))
    print(f"  job   : {rec['job_name']}")
    print(f"  state : {st}")
    return {"job_name": rec["job_name"], "state": st, "job": job}


# ---------------------------------------------------------------------------
# Retrieve + technical validation
# ---------------------------------------------------------------------------

def _telemetry(resp) -> dict:
    fr, um = [], getattr(resp, "usage_metadata", None)
    for c in (getattr(resp, "candidates", None) or []):
        fr.append(str(getattr(c, "finish_reason", None)))
    return {
        "finish_reasons": fr,
        "prompt_token_count": getattr(um, "prompt_token_count", None),
        "candidates_token_count": getattr(um, "candidates_token_count", None),
        "thoughts_token_count": getattr(um, "thoughts_token_count", None),
        "total_token_count": getattr(um, "total_token_count", None),
    }


def retrieve() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    _load_env()
    from google import genai
    client = genai.Client(api_key=os.environ[KEY_ENV])
    job = client.batches.get(name=rec["job_name"])
    st = str(getattr(job, "state", None))
    if "SUCCEEDED" not in st:
        raise BatchError(f"job state is {st}; not retrievable yet")

    man = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    by_unit = {r["unit_id"]: r for r in man["requests"]}

    raw, results = [], []
    dest = getattr(job, "dest", None)
    inlined = getattr(dest, "inlined_responses", None) or []
    if len(inlined) != len(man["requests"]):
        raise BatchError(f"{len(inlined)} responses for {len(man['requests'])} requests")

    for ir in inlined:
        meta = getattr(ir, "metadata", None) or {}
        unit = meta.get("custom_request_key") if isinstance(meta, dict) else None
        err = getattr(ir, "error", None)
        resp = getattr(ir, "response", None)
        text = None
        tele = {}
        if resp is not None:
            tele = _telemetry(resp)
            try:
                text = resp.text
            except Exception as e:            # noqa: BLE001
                text = None
                tele["text_error"] = str(e)
        raw.append({"unit_id": unit, "error": str(err) if err else None,
                    "telemetry": tele, "text": text})

        if unit is None:
            results.append({"unit_id": None, "status": "UNKEYED_RESPONSE",
                            "problems": ["response carried no custom_request_key"]})
            continue
        if err or not text:
            results.append({"unit_id": unit, "status": "NO_OUTPUT",
                            "problems": [f"error={err}"], "telemetry": tele})
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            results.append({"unit_id": unit, "status": "INVALID_JSON",
                            "problems": [str(e)], "telemetry": tele})
            continue
        v = cal.validate_extraction(unit, payload, tele, cal.unit_lines(unit))
        v["unit_text_sha256"] = by_unit[unit]["unit_text_sha256"]
        v["cache_key"] = by_unit[unit]["cache_key"]
        v["themes"] = payload.get("themes", [])
        results.append(v)

    _atomic(_RAW, {"retrieved_utc": datetime.now(UTC).isoformat(),
                   "job_name": rec["job_name"], "responses": raw})
    out = {
        "retrieved_utc": datetime.now(UTC).isoformat(),
        "classification": cal.CLASSIFICATION,
        "job_name": rec["job_name"],
        "prompt_sha256": rec["prompt_sha256"],
        "response_schema_sha256": rec["response_schema_sha256"],
        "effective_request_config": rec["effective_request_config"],
        "n_units": len(results),
        "results": results,
    }
    _atomic(_RESULTS, out)
    return out


def main() -> int:
    a = sys.argv[1:]
    if "--manifest" in a:
        m = build_manifest()
        print(f"manifest: {m['n_requests']} requests")
        for r in m["requests"]:
            print(f"  {r['unit_id']}  {r['n_turns']:>2} turns  {r['n_words']:>5} words"
                  f"  key {r['cache_key'][:16]}")
        print("NOT SUBMITTED.")
    elif "--submit" in a:
        submit()
    elif "--status" in a:
        status()
    elif "--retrieve" in a:
        o = retrieve()
        for r in o["results"]:
            print(f"  {r['unit_id']}: {r['status']} "
                  f"({r.get('n_themes', '?')} themes) {r.get('problems') or ''}")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
