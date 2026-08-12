"""
Phase 2 — Gemini emergent extraction over S01-S06. Exactly six Batch requests.

Same model, prompt, schema and effective configuration as U01-U07/Q3. A defective
response is quarantined, never repaired. If any unit is not COMPLETE the run stops.

    py scripts/hybrid_gemini_extract.py --submit
    py scripts/hybrid_gemini_extract.py --status
    py scripts/hybrid_gemini_extract.py --retrieve
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import hybrid_transportability as hy   # noqa: E402
import emergent_calibration_q3 as cal  # noqa: E402

_HY = hy._HY
_JOB = _HY / "gemini_job.json"
_RAW = _HY / "gemini_raw.json"
_RES = _HY / "gemini_extraction_results.json"

KEY_ENV = "GEMINI_API_KEY_NEXT"


class ExtractError(RuntimeError):
    pass


def _load_env():
    p = _ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def submit() -> dict:
    if _JOB.exists():
        e = json.loads(_JOB.read_text(encoding="utf-8"))
        raise ExtractError(f"a job already exists: {e.get('job_name')}. Batch creation "
                           f"is NOT idempotent.")
    man = json.loads((_HY / "hybrid_manifest.json").read_text(encoding="utf-8"))
    if man["gemini"]["prompt_sha256"] != cal.prompt_sha():
        raise ExtractError("prompt drifted from the frozen manifest")
    if man["gemini"]["response_schema_sha256"] != cal.response_schema_sha():
        raise ExtractError("schema drifted from the frozen manifest")

    _load_env()
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ[KEY_ENV])

    cfg = types.GenerateContentConfig(
        system_instruction=cal.EXTRACTION_SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=cal.transmitted_response_schema(),
        max_output_tokens=hy.GEMINI_MAX_OUTPUT_TOKENS,
        # temperature and thinking_config deliberately NOT set
    )
    inline = []
    for u in hy.UNITS:
        text = hy.unit_text(u)
        if u in text:
            raise ExtractError(f"{u}: the real unit id leaked into the transmitted text")
        inline.append({"model": hy.GEMINI_MODEL,
                       "contents": [{"parts": [{"text": text}], "role": "user"}],
                       "config": cfg,
                       "metadata": {"custom_request_key": u}})

    print(f"submitting ONE job with {len(inline)} requests ...")
    job = client.batches.create(model=hy.GEMINI_MODEL, src=inline,
                                config={"display_name": "hybrid_transportability_s01_s06"})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "state": str(getattr(job, "state", None)),
           "model": hy.GEMINI_MODEL, "n_requests": len(inline),
           "units": hy.UNITS,
           "prompt_sha256": cal.prompt_sha(),
           "response_schema_sha256": cal.response_schema_sha(),
           "effective_config": hy.gemini_effective_config(),
           "cache_keys": {u: hy.gemini_cache_key(u) for u in hy.UNITS},
           "warning": "batch creation is NOT idempotent"}
    hy._atomic(_JOB, rec)
    print("  job  :", rec["job_name"])
    print("  state:", rec["state"])
    return rec


def status() -> str:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    _load_env()
    from google import genai
    # Hold the client in a local: an inline temporary is garbage-collected mid-call and
    # closes its own httpx client, which surfaces as "client has been closed".
    client = genai.Client(api_key=os.environ[KEY_ENV])
    job = client.batches.get(name=rec["job_name"])
    st = str(getattr(job, "state", None))
    print(f"  job   : {rec['job_name']}")
    print(f"  state : {st}")
    return st


def _telemetry(resp) -> dict:
    um = getattr(resp, "usage_metadata", None)
    return {"finish_reasons": [str(getattr(c, "finish_reason", None))
                               for c in (getattr(resp, "candidates", None) or [])],
            "prompt_token_count": getattr(um, "prompt_token_count", None),
            "candidates_token_count": getattr(um, "candidates_token_count", None),
            "thoughts_token_count": getattr(um, "thoughts_token_count", None),
            "total_token_count": getattr(um, "total_token_count", None)}


def _turns(unit: str):
    d = {}
    for ln in hy.units()[unit]["lines"]:
        m = re.match(r"^\[(T\d+)\]\s+([^:]+):\s*(.*)$", ln, re.S)
        if m:
            d[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
    return d


def validate_unit(unit: str, payload: dict, tele: dict) -> dict:
    """Frozen acceptance gate. A failure quarantines the unit; nothing is repaired."""
    problems = []
    turns = _turns(unit)
    norm = lambda t: " ".join(str(t).split())

    reasons = tele.get("finish_reasons") or []
    if not reasons or any("STOP" not in str(r).upper() for r in reasons):
        problems.append(f"finish_reason {reasons}, expected STOP")
    if tele.get("candidates_token_count") and \
            tele["candidates_token_count"] >= hy.GEMINI_MAX_OUTPUT_TOKENS:
        problems.append("output reached max_output_tokens — possible truncation")

    themes = (payload or {}).get("themes")
    if themes is None:
        problems.append("no `themes` array — schema invalid")
        themes = []
    ids = [t.get("machine_theme_id") for t in themes]
    if len(set(ids)) != len(ids):
        problems.append(f"duplicate machine_theme_id: {sorted({i for i in ids if ids.count(i) > 1})}")
    if any(not i for i in ids):
        problems.append("a theme has no machine_theme_id")

    n_quotes = 0
    for t in themes:
        tid = t.get("machine_theme_id", "?")
        for f in ("label", "one_sentence_description", "relevance"):
            if not t.get(f):
                problems.append(f"{tid}: missing {f}")
        if t.get("relevance") not in (None, "central", "secondary"):
            problems.append(f"{tid}: relevance {t.get('relevance')!r}")
        ev = t.get("evidence") or []
        if not ev:
            problems.append(f"{tid}: no evidence")
        for e in ev:
            n_quotes += 1
            tu = e.get("turn_id")
            if tu not in turns:
                problems.append(f"{tid}: turn {tu!r} is not in this unit")
                continue
            speaker, body = turns[tu]
            if speaker.lower().startswith("moderator"):
                problems.append(f"{tid}: quotes the moderator at {tu}")
            if norm(e.get("quote", "")) not in norm(body):
                problems.append(f"{tid}: quote at {tu} is not literal in that turn")

    return {"blind_unit_id": unit, "question_id": hy.QUESTION_OF[unit],
            "status": "COMPLETE" if not problems else "QUARANTINE",
            "n_themes": len(themes), "n_quotes": n_quotes,
            "problems": problems, "telemetry": tele, "themes": themes}


def retrieve() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    _load_env()
    from google import genai
    client = genai.Client(api_key=os.environ[KEY_ENV])
    job = client.batches.get(name=rec["job_name"])
    if "SUCCEEDED" not in str(getattr(job, "state", None)):
        raise ExtractError(f"state is {getattr(job, 'state', None)}; not retrievable")

    inlined = getattr(getattr(job, "dest", None), "inlined_responses", None) or []
    if len(inlined) != len(hy.UNITS):
        raise ExtractError(f"{len(inlined)} responses for {len(hy.UNITS)} requests")

    raw, results = [], []
    for ir in inlined:
        meta = getattr(ir, "metadata", None) or {}
        unit = meta.get("custom_request_key") if isinstance(meta, dict) else None
        err, resp = getattr(ir, "error", None), getattr(ir, "response", None)
        tele, text = {}, None
        if resp is not None:
            tele = _telemetry(resp)
            try:
                text = resp.text
            except Exception as e:                     # noqa: BLE001
                tele["text_error"] = str(e)
        raw.append({"blind_unit_id": unit, "error": str(err) if err else None,
                    "telemetry": tele, "text": text})
        if unit is None:
            results.append({"blind_unit_id": None, "status": "UNKEYED_RESPONSE",
                            "problems": ["response carried no custom_request_key"]})
            continue
        if err or not text:
            results.append({"blind_unit_id": unit, "status": "QUARANTINE",
                            "problems": [f"error={err}"], "telemetry": tele})
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            results.append({"blind_unit_id": unit, "status": "QUARANTINE",
                            "problems": [f"invalid JSON: {e}"], "telemetry": tele})
            continue
        v = validate_unit(unit, payload, tele)
        v["cache_key"] = rec["cache_keys"][unit]
        v["unit_text_sha256"] = hashlib.sha256(
            hy.unit_text(unit).encode()).hexdigest()
        results.append(v)

    hy._atomic(_RAW, {"retrieved_utc": datetime.now(UTC).isoformat(),
                      "job_name": rec["job_name"], "responses": raw})
    out = {"retrieved_utc": datetime.now(UTC).isoformat(),
           "classification": hy.CLASSIFICATION,
           "job_name": rec["job_name"],
           "model": hy.GEMINI_MODEL,
           "prompt_sha256": rec["prompt_sha256"],
           "response_schema_sha256": rec["response_schema_sha256"],
           "effective_config": rec["effective_config"],
           "n_units": len(results),
           "n_complete": sum(1 for r in results if r["status"] == "COMPLETE"),
           "total_usage": {
               "input_tokens": sum((r["telemetry"] or {}).get("prompt_token_count") or 0
                                   for r in raw),
               "output_tokens": sum((r["telemetry"] or {}).get("candidates_token_count") or 0
                                    for r in raw)},
           "relevance_caveat": ("central/secondary is DESCRIPTIVE MODEL METADATA and is "
                                "NOT validated"),
           "results": results}
    hy._atomic(_RES, out)
    return out


def main() -> int:
    a = sys.argv[1:]
    if "--submit" in a:
        submit()
    elif "--status" in a:
        status()
    elif "--retrieve" in a:
        o = retrieve()
        for r in o["results"]:
            print(f"  {r['blind_unit_id']} ({r.get('question_id','?')}): {r['status']}  "
                  f"themes={r.get('n_themes')} quotes={r.get('n_quotes')}  "
                  f"{r.get('problems') or ''}")
        print(f"\ncomplete: {o['n_complete']}/{o['n_units']}   usage: {o['total_usage']}")
        if o["n_complete"] != len(hy.UNITS):
            print("STOP — not every unit is COMPLETE; no partial corpus proceeds.")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
