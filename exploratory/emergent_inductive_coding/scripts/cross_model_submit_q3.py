"""
Submit and retrieve the frozen 76-request cross-model audit batch.

Submission is NOT idempotent: once a job record exists this refuses to create another.
Responses are matched by custom_id, never by position.

    py scripts/cross_model_submit_q3.py --cost-basis
    py scripts/cross_model_submit_q3.py --submit
    py scripts/cross_model_submit_q3.py --status
    py scripts/cross_model_submit_q3.py --retrieve
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import cross_model_audit_q3 as cm      # noqa: E402
import emergent_calibration_q3 as cal  # noqa: E402

_DIR = cal._DIR
_MANIFEST = _DIR / "cross_model_manifest_q3.json"
_JOB = _DIR / "cross_model_job_q3.json"
_RAW = _DIR / "cross_model_raw_q3.json"
_RESULTS = _DIR / "cross_model_results_q3.json"
_COST = _DIR / "cross_model_cost_basis.json"

# Verified 2026-08-02 against platform.claude.com/docs/en/about-claude/pricing.
RATE = {
    "source": "https://platform.claude.com/docs/en/about-claude/pricing",
    "verified_utc": "2026-08-02",
    "model": "claude-opus-5",
    "standard_input_per_mtok": 5.00,
    "standard_output_per_mtok": 25.00,
    "batch_input_per_mtok": 2.50,
    "batch_output_per_mtok": 12.50,
    "batch_discount": "50% on both input and output tokens",
    "caveat": ("This is the PUBLISHED LIST RATE. The effective rate for this "
               "organisation is not exposed by any API endpoint — volume, academic and "
               "enterprise discounts are negotiated case by case. Treat every figure "
               "below as an UPPER BOUND at list price, not a confirmed charge. The "
               "actual charge is whatever the Console reports."),
}


class SubmitError(RuntimeError):
    pass


def _load_env():
    p = _REPO_ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _atomic(path: Path, payload) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str),
                       encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def safe_id(i: int) -> str:
    """Batch custom_id must be short and [A-Za-z0-9_-]; the real key is in the map."""
    return f"cma{i:03d}"


def cost_basis() -> dict:
    man = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    chars = sum(r["rendered_chars"] for r in man["requests"])
    rub = sum(len(cm.prompt_for(r["task"])) for r in man["requests"])
    tin = (chars + rub) / 4
    tout = man["n_requests"] * 700
    out = {
        **RATE,
        "n_requests": man["n_requests"],
        "estimated_input_tokens": round(tin),
        "estimated_output_tokens": tout,
        "token_estimate_method": ("~4 characters per token, offline. count_tokens was "
                                  "NOT called because it is itself an API request."),
        "upper_bound_standard_usd": round(tin / 1e6 * 5 + tout / 1e6 * 25, 2),
        "upper_bound_batch_usd": round(tin / 1e6 * 2.50 + tout / 1e6 * 12.50, 2),
        "status": "ESTIMATE_AT_PUBLISHED_LIST_RATE_NOT_A_CONFIRMED_CHARGE",
    }
    _atomic(_COST, out)
    return out


def submit() -> dict:
    if _JOB.exists():
        e = json.loads(_JOB.read_text(encoding="utf-8"))
        raise SubmitError(f"a job already exists: {e.get('job_id')} created "
                          f"{e.get('created_utc')}. Batch creation is NOT idempotent.")

    man = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    if man["n_requests"] != 76:
        raise SubmitError(f"manifest has {man['n_requests']} requests, expected 76")
    if cm.prompt_purity_problems():
        raise SubmitError("rubrics are not clean")

    cases = {c["case_id"]: c for g in ("calibration", "pending") for c in man["cases"][g]}
    _load_env()
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    client = anthropic.Anthropic()

    reqs, id_map = [], {}
    for i, r in enumerate(man["requests"], start=1):
        cid = safe_id(i)
        case = cases[r["case_id"]]
        rendered = cm.render(case, r["repetition_index"])
        # the manifest hash is the contract: what we send must be what was frozen
        import hashlib
        if hashlib.sha256(rendered.encode()).hexdigest() != r["rendered_sha256"]:
            raise SubmitError(f"{r['custom_request_key']}: rendered text drifted "
                              f"from the frozen manifest")
        id_map[cid] = {"custom_request_key": r["custom_request_key"],
                       "case_id": r["case_id"], "task": r["task"],
                       "repetition_index": r["repetition_index"],
                       "group": r["group"], "cache_key": r["cache_key"]}
        reqs.append(Request(
            custom_id=cid,
            params=MessageCreateParamsNonStreaming(
                model=cm.AUDITOR_MODEL,
                max_tokens=cm.MAX_OUTPUT_TOKENS,
                system=cm.prompt_for(r["task"]),
                messages=[{"role": "user", "content": rendered}],
                output_config={
                    "effort": cm.EFFORT,
                    "format": {"type": "json_schema",
                               "schema": cm.task_schema(r["task"])},
                },
            ),
        ))

    print(f"submitting ONE batch with {len(reqs)} requests ...")
    batch = client.messages.batches.create(requests=reqs)
    rec = {
        "created_utc": datetime.now(UTC).isoformat(),
        "job_id": batch.id,
        "processing_status": batch.processing_status,
        "n_requests": len(reqs),
        "model": cm.AUDITOR_MODEL,
        "effective_config": cm.effective_config(),
        "manifest_prompt_sha256": man["prompt_sha256"],
        "manifest_schema_sha256": man["schema_sha256"],
        "custom_id_map": id_map,
        "warning": "batch creation is NOT idempotent — never create again for this scope",
    }
    _atomic(_JOB, rec)
    print(f"  job id : {batch.id}")
    print(f"  status : {batch.processing_status}")
    return rec


def status() -> str:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    _load_env()
    import anthropic
    b = anthropic.Anthropic().messages.batches.retrieve(rec["job_id"])
    print(f"  job    : {rec['job_id']}")
    print(f"  status : {b.processing_status}")
    print(f"  counts : {b.request_counts}")
    return b.processing_status


def retrieve() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    id_map = rec["custom_id_map"]
    _load_env()
    import anthropic
    client = anthropic.Anthropic()
    b = client.messages.batches.retrieve(rec["job_id"])
    if b.processing_status != "ended":
        raise SubmitError(f"processing_status is {b.processing_status}, not ended")

    raw, results = [], []
    for res in client.messages.batches.results(rec["job_id"]):
        cid = res.custom_id                      # matched by id, never by position
        meta = id_map.get(cid)
        if meta is None:
            raise SubmitError(f"unknown custom_id in results: {cid}")
        rtype = res.result.type
        entry = {"custom_id": cid, **meta, "result_type": rtype}
        if rtype != "succeeded":
            entry["error"] = str(getattr(res.result, "error", None))
            raw.append(entry)
            results.append({**entry, "status": "NO_OUTPUT"})
            continue
        msg = res.result.message
        text = next((bl.text for bl in msg.content if bl.type == "text"), None)
        entry["stop_reason"] = msg.stop_reason
        entry["usage"] = {"input_tokens": msg.usage.input_tokens,
                          "output_tokens": msg.usage.output_tokens}
        entry["text"] = text
        raw.append(entry)
        if msg.stop_reason == "max_tokens":
            results.append({**entry, "status": "OUTPUT_TRUNCATED"})
            continue
        try:
            payload = json.loads(text)
        except Exception as e:                    # noqa: BLE001
            results.append({**entry, "status": "INVALID_JSON", "error": str(e)})
            continue
        cats = cm.TASKS[meta["task"]]
        problems = []
        if payload.get("category") not in cats:
            problems.append(f"category {payload.get('category')!r} not in {list(cats)}")
        if payload.get("confidence") not in cm.CONFIDENCE:
            problems.append(f"confidence {payload.get('confidence')!r} invalid")
        results.append({**entry, "status": "COMPLETE" if not problems else "INVALID",
                        "problems": problems, "judgement": payload})

    _atomic(_RAW, {"retrieved_utc": datetime.now(UTC).isoformat(),
                   "job_id": rec["job_id"], "responses": raw})

    got = {r["custom_id"] for r in results}
    missing = sorted(set(id_map) - got)
    if missing:
        raise SubmitError(f"{len(missing)} responses missing: {missing[:10]}")
    if len(results) != 76:
        raise SubmitError(f"{len(results)} results, expected 76")

    # repetitions are kept apart by construction
    for r in results:
        assert r["repetition_index"] in (1, 2)
    out = {
        "retrieved_utc": datetime.now(UTC).isoformat(),
        "job_id": rec["job_id"],
        "classification": cm.CLASSIFICATION,
        "n_results": len(results),
        "n_complete": sum(1 for r in results if r["status"] == "COMPLETE"),
        "total_usage": {
            "input_tokens": sum(r.get("usage", {}).get("input_tokens", 0) for r in raw),
            "output_tokens": sum(r.get("usage", {}).get("output_tokens", 0) for r in raw),
        },
        "results": results,
    }
    _atomic(_RESULTS, out)
    return out


def main() -> int:
    a = sys.argv[1:]
    if "--cost-basis" in a:
        c = cost_basis()
        print(json.dumps({k: c[k] for k in
                          ("model", "standard_input_per_mtok", "standard_output_per_mtok",
                           "batch_input_per_mtok", "batch_output_per_mtok",
                           "upper_bound_standard_usd", "upper_bound_batch_usd",
                           "status")}, indent=1))
    elif "--submit" in a:
        submit()
    elif "--status" in a:
        status()
    elif "--retrieve" in a:
        o = retrieve()
        print(f"results: {o['n_results']}  complete: {o['n_complete']}")
        print(f"usage  : {o['total_usage']}")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
