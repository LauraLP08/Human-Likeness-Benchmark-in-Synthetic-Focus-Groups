"""
Stage 2 of the blinded cross-model absence audit — the incremental 21 documents.

    py scripts/absence_audit_stage2.py --preflight
    py scripts/absence_audit_stage2.py --submit
    py scripts/absence_audit_stage2.py --status
    py scripts/absence_audit_stage2.py --retrieve

Runs under the Stage-1 outcome Band B, PROCEED_DETECTION_ONLY. ABSENCE_CORROBORATED is
forbidden globally under that band, regardless of subtheme control eligibility.

Configuration is frozen and identical to Stage 1, including max_output_tokens = 8192,
which was frozen prospectively and is not retuned on Stage-1 results.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import absence_audit_build as B      # noqa: E402
import absence_audit_rules as R      # noqa: E402
import absence_audit_stage1 as S1    # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/salience_absence_audit"
_SEALED = _OUT / "sealed"
_JOB = _OUT / "stage2_batch_job.json"
_RAW = _OUT / "stage2_raw_responses.json"

BAND = R.GATE_B


class Stage2Error(RuntimeError):
    pass


def preflight() -> dict:
    problems = []

    def check(cond, msg):
        if not cond:
            problems.append(msg)

    s1 = json.loads(
        (_OUT / "stage1_calibration_results.json").read_text(encoding="utf-8"))
    check(s1["gate"]["outcome"] == BAND,
          f"Stage-1 outcome {s1['gate']['outcome']}, expected {BAND}")

    cb = B.codebook()
    codes = sorted(cb)
    check(codes == sorted(S1.PRODUCTION_IDS), "codebook ids differ from production ids")

    cal = B.calibration_selection(cb)
    stage1_ids = {B.blind_id(k) for k in cal["doc_keys"]}
    store = B.render_store(cb, codes)
    stage2_ids = sorted(set(store) - stage1_ids)
    check(len(stage1_ids) == 14, f"{len(stage1_ids)} Stage-1 documents")
    check(len(stage2_ids) == 21, f"{len(stage2_ids)} Stage-2 documents, expected 21")
    check(not (set(stage2_ids) & stage1_ids), "a Stage-1 document leaked into Stage 2")

    prompt_sha = B._sha(B.SYSTEM_PROMPT)
    schema_sha = B._sha(json.dumps(B.RESPONSE_SCHEMA, sort_keys=True))
    man = json.loads((_OUT / "batch_manifest.json").read_text(encoding="utf-8"))
    check(man["prompt_sha256"] == prompt_sha, "prompt hash differs from the frozen build")
    check(man["schema_sha256"] == schema_sha, "schema hash differs from the frozen build")

    rows = [{"blinded_document_id": b} for b in stage2_ids]
    reqs = B.build_requests(rows, store, lambda b: "STAGE2_COMPLETE",
                            prompt_sha, schema_sha, codes)
    for r in reqs:
        check(r["n_candidates"] == 11, f"{r['blinded_document_id']} candidates")
        check(sorted(r["candidate_order"]) == sorted(S1.PRODUCTION_IDS),
              f"{r['blinded_document_id']} candidate ids")
    keys = [k for r in reqs for k in r["cache_keys"].values()]
    check(len(keys) == 42, f"{len(keys)} cache keys, expected 42")
    check(len(set(keys)) == len(keys), "cache-key collision")

    s1keys = {k for v in json.loads(
        (_OUT / "stage1_batch_job.json").read_text(encoding="utf-8")
    )["custom_id_map"].values() for k in [v["cache_key"]]}
    check(not (set(keys) & s1keys), "a Stage-2 cache key collides with a Stage-1 key")

    scaffold_fail, leak_fail, sealed_leak = [], [], []
    for b in stage2_ids:
        s = store[b]
        if bad := B.scaffold_purity_problems(s["scaffold"]):
            scaffold_fail.append({b: bad})
        body = s["body"]
        if lk := B.transcript_leak_problems(body[body.index("TRANSCRIPT\n\n"):]):
            leak_fail.append({b: lk})
        for tok in ("SEALED", "ORIGINAL_GEMINI", "original_status", "human::"):
            if tok in body:
                sealed_leak.append({b: tok})
    check(not scaffold_fail, f"scaffold leaks: {scaffold_fail}")
    check(not leak_fail, f"transcript leaks: {leak_fail}")
    check(not sealed_leak, f"original-decision leaks: {sealed_leak}")

    check(S1.MAX_OUTPUT_TOKENS == 8192, "max_output_tokens is not the frozen 8192")
    check(S1.CONFIG_COMPLETION["frozen_prospectively_for_stage_2"] is True,
          "max_output_tokens is not frozen prospectively")
    check(S1.CONFIG_COMPLETION["may_be_retuned_on_stage1_results"] is False,
          "max_output_tokens is marked retunable")

    return {"pass": not problems, "problems": problems,
            "stage1_outcome": s1["gate"]["outcome"],
            "n_stage2_documents": len(stage2_ids), "n_requests": len(keys),
            "n_candidates_per_request": 11,
            "corroboration_forbidden_globally": True,
            "scaffold_leaks": len(scaffold_fail), "transcript_leaks": len(leak_fail),
            "original_decision_leaks": len(sealed_leak),
            "cache_key_collisions": len(keys) - len(set(keys)),
            "requests": reqs, "stage2_ids": stage2_ids,
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha}


def submit() -> dict:
    pf = preflight()
    if not pf["pass"]:
        raise Stage2Error("preflight failed:\n  " + "\n  ".join(pf["problems"]))
    if _JOB.exists():
        raise Stage2Error(f"{_JOB.name} already exists; refusing to resubmit")

    S1._load_env()
    import anthropic
    from anthropic.types.messages.batch_create_params import Request
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

    cb = B.codebook()
    codes = sorted(cb)
    store = B.render_store(cb, codes)

    reqs, id_map, n = [], {}, 0
    for r in sorted(pf["requests"], key=lambda x: x["blinded_document_id"]):
        bid = r["blinded_document_id"]
        for rep in (1, 2):
            n += 1
            cid = f"s2_{n:03d}"
            id_map[cid] = {"blinded_document_id": bid, "repetition_index": rep,
                           "cache_key": r["cache_keys"][str(rep)],
                           "candidate_order": r["candidate_order"],
                           "rendered_sha256": r["rendered_sha256"]}
            reqs.append(Request(
                custom_id=cid,
                params=MessageCreateParamsNonStreaming(
                    model=S1.MODEL,
                    max_tokens=S1.MAX_OUTPUT_TOKENS,
                    system=B.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": store[bid]["body"]}],
                    output_config={"effort": S1.EFFORT,
                                   "format": {"type": "json_schema",
                                              "schema": B.RESPONSE_SCHEMA}})))
    if len(reqs) != 42:
        raise Stage2Error(f"{len(reqs)} requests built, expected 42")

    print(f"submitting Stage 2: {len(reqs)} requests, model {S1.MODEL}, "
          f"effort {S1.EFFORT}, max_output_tokens {S1.MAX_OUTPUT_TOKENS}")
    batch = anthropic.Anthropic().messages.batches.create(requests=reqs)

    rec = {"created_utc": datetime.now(UTC).isoformat(), "job_id": batch.id,
           "stage": "STAGE2_COMPLETE", "band": BAND,
           "corroboration_forbidden_globally": True,
           "processing_status": batch.processing_status, "n_requests": len(reqs),
           "model": S1.MODEL, "effort": S1.EFFORT,
           "max_output_tokens": S1.MAX_OUTPUT_TOKENS,
           "max_output_tokens_record": S1.CONFIG_COMPLETION,
           "structured_output": "output_config.format json_schema",
           "temperature_transmitted": False, "top_p_transmitted": False,
           "top_k_transmitted": False,
           "prompt_sha256": pf["prompt_sha256"], "schema_sha256": pf["schema_sha256"],
           "retrieval_rule": "by custom_id only, never by response position",
           "custom_id_map": id_map}
    S1._atomic(_JOB, rec)
    print("  job id:", batch.id, "->", _JOB.name)
    return rec


def status() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    S1._load_env()
    import anthropic
    b = anthropic.Anthropic().messages.batches.retrieve(rec["job_id"])
    print(rec["job_id"], b.processing_status, dict(b.request_counts))
    return {"processing_status": b.processing_status}


def retrieve() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    S1._load_env()
    import anthropic
    client = anthropic.Anthropic()
    b = client.messages.batches.retrieve(rec["job_id"])
    if b.processing_status != "ended":
        raise Stage2Error(f"status {b.processing_status}, not ended")

    id_map = rec["custom_id_map"]
    out = {}
    for res in client.messages.batches.results(rec["job_id"]):
        cid = res.custom_id
        if cid not in id_map:
            raise Stage2Error(f"unknown custom_id {cid}")
        if cid in out:
            raise Stage2Error(f"duplicate custom_id {cid}")
        e = {"custom_id": cid, **id_map[cid], "result_type": res.result.type}
        if res.result.type == "succeeded":
            msg = res.result.message
            e["stop_reason"] = msg.stop_reason
            e["usage"] = {"input_tokens": msg.usage.input_tokens,
                          "output_tokens": msg.usage.output_tokens}
            e["raw_text"] = next((bl.text for bl in msg.content
                                  if bl.type == "text"), None)
        else:
            e["error"] = str(getattr(res.result, "error", res.result.type))
        out[cid] = e

    missing = sorted(set(id_map) - set(out))
    if missing:
        raise Stage2Error(f"missing responses: {missing}")

    payload = {"retrieved_utc": datetime.now(UTC).isoformat(),
               "job_id": rec["job_id"], "stage": "STAGE2_COMPLETE",
               "matched_by": "custom_id", "raw_preserved_unchanged": True,
               "n_results": len(out),
               "total_usage": {
                   "input_tokens": sum(e.get("usage", {}).get("input_tokens", 0)
                                       for e in out.values()),
                   "output_tokens": sum(e.get("usage", {}).get("output_tokens", 0)
                                        for e in out.values())},
               "responses": [out[c] for c in sorted(out)]}
    S1._atomic(_RAW, payload)
    print(f"retrieved {len(out)} responses -> {_RAW.name}")
    return payload


def main() -> int:
    a = sys.argv[1:]
    if "--preflight" in a:
        pf = preflight()
        print("=== STAGE-2 PREFLIGHT ===")
        for k in ("stage1_outcome", "n_stage2_documents", "n_requests",
                  "n_candidates_per_request", "corroboration_forbidden_globally",
                  "cache_key_collisions", "scaffold_leaks", "transcript_leaks",
                  "original_decision_leaks"):
            print(f"  {k:34s} {pf[k]}")
        print(f"  max_output_tokens                  {S1.MAX_OUTPUT_TOKENS} (frozen)")
        print(f"\n  PASS: {pf['pass']}")
        for p in pf["problems"]:
            print("   PROBLEM:", p)
        return 0 if pf["pass"] else 1
    if "--submit" in a:
        submit()
        return 0
    if "--status" in a:
        status()
        return 0
    if "--retrieve" in a:
        retrieve()
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
