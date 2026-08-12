"""
Stage 1 calibration of the blinded cross-model absence audit.

    py scripts/absence_audit_stage1.py --preflight
    py scripts/absence_audit_stage1.py --submit
    py scripts/absence_audit_stage1.py --status
    py scripts/absence_audit_stage1.py --retrieve
    py scripts/absence_audit_stage1.py --score

STAGE 1 ONLY. Nothing here submits Stage 2, and nothing here writes to the Gemini
results, the salience tables, the heatmap or the workbook. No
Gemini absence is ever converted into a presence.

Everything runs against the manifests already frozen on disk. The preflight revalidates
each of them and refuses to submit on any failure.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import absence_audit_build as B      # noqa: E402
import absence_audit_rules as R      # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/salience_absence_audit"
_SEALED = _OUT / "sealed"
_JOB = _OUT / "stage1_batch_job.json"
_RAW = _OUT / "stage1_raw_responses.json"

MODEL = "claude-opus-5"
EFFORT = "high"
MAX_OUTPUT_TOKENS = 8192

# POST-FREEZE CONFIGURATION COMPLETION
#
# max_output_tokens was ABSENT from the pre-submission manifest — an omission in the
# frozen build, not a value that was chosen and then changed. It was completed, not
# revised.
#
# The value 8192 was adopted from the existing project cross-model audit configuration
# (scripts/cross_model_audit_q3.py MAX_OUTPUT_TOKENS), not invented for this audit and
# not selected by inspecting Stage-1 behaviour. It was transmitted on all 28 Stage-1
# requests and is associated with 28/28 end_turn responses and complete 11-code outputs:
# no response was truncated and none returned a short assessment list.
#
# It is now FROZEN PROSPECTIVELY FOR STAGE 2 at the same 8192. It must not be retuned on
# the strength of Stage-1 results — the measured Stage-1 output of 399 tokens per
# assessment (~4,390 per response) is well inside the ceiling, and adjusting a frozen
# parameter to fit observed behaviour would convert a fixed instrument into one tuned on
# its own calibration data.
CONFIG_COMPLETION = {
    "parameter": "max_output_tokens",
    "value": 8192,
    "record_type": "POST_FREEZE_CONFIGURATION_COMPLETION",
    "absent_from_pre_submission_manifest": True,
    "adopted_from": ("the existing project cross-model audit configuration, "
                     "scripts/cross_model_audit_q3.py MAX_OUTPUT_TOKENS"),
    "invented_for_this_audit": False,
    "chosen_from_stage1_results": False,
    "transmitted_on_all_28_stage1_requests": True,
    "stage1_end_turn_responses": "28/28",
    "stage1_truncated_responses": 0,
    "stage1_complete_11_code_outputs": "28/28",
    "frozen_prospectively_for_stage_2": True,
    "may_be_retuned_on_stage1_results": False,
    "why_not_retuned": ("measured Stage-1 output was 399 tokens per assessment, about "
                        "4,390 per response, well inside the ceiling; retuning a frozen "
                        "parameter to fit observed behaviour would tune the instrument "
                        "on its own calibration data"),
}

PRODUCTION_IDS = ["A.1", "A.2", "A.3", "B.1", "B.2", "B.3", "B.4",
                  "C.1", "C.2", "C.3", "D"]


class Stage1Error(RuntimeError):
    pass


def _atomic(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _load_env() -> None:
    p = _ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ------------------------------------------------------------- preflight
def preflight() -> dict:
    """Revalidates every frozen invariant. Any failure blocks submission."""
    problems = []

    def check(cond, msg):
        if not cond:
            problems.append(msg)

    cb = B.codebook()
    codes = sorted(cb)
    check(codes == sorted(PRODUCTION_IDS),
          f"codebook ids {codes} != production ids {sorted(PRODUCTION_IDS)}")

    uni = B.absence_universe()
    check(uni["pass"], f"universe problems: {uni['problems']}")
    check(uni["n_absence_decisions_derived"] == 260,
          f"universe {uni['n_absence_decisions_derived']} != 260")

    cal = B.calibration_selection(cb)
    cal_docs = sorted(cal["doc_keys"])
    check(len(cal_docs) == 14, f"{len(cal_docs)} Stage-1 documents, expected 14")

    store = B.render_store(cb, codes)
    stage1_ids = {B.blind_id(k) for k in cal_docs}
    check(len(stage1_ids) == 14, "blinded ids collide across Stage-1 documents")

    public, sealed_ref = B.split_calibration(cal, store, codes)
    check(B.public_manifest_problems(public) == [],
          f"public manifest leaks: {B.public_manifest_problems(public)}")

    # subtheme coverage of the designated controls
    controls = [c for c in sealed_ref["cases"]
                if c["original_status"] == R.ORIGINAL_PRESENT]
    check(len(controls) == 11, f"{len(controls)} designated controls, expected 11")
    check(sorted(c["subtheme_id"] for c in controls) == sorted(PRODUCTION_IDS),
          "designated controls do not cover the production ids exactly")

    # cells, controls and absences over the Stage-1 documents
    grid = B.presence_grid()
    n_cells = len(cal_docs) * len(codes)
    n_present = sum(1 for k in cal_docs for c in codes if grid[(k, c)])
    n_absence = n_cells - n_present
    check(n_cells == 154, f"{n_cells} cells per repetition, expected 154")
    check(n_present == 63, f"{n_present} positive controls, expected 63")
    check(n_absence == 91, f"{n_absence} absence cells, expected 91")

    # requests, blinding, cache keys
    prompt_sha = B._sha(B.SYSTEM_PROMPT)
    schema_sha = B._sha(json.dumps(B.RESPONSE_SCHEMA, sort_keys=True))
    rows = [{"blinded_document_id": b} for b in sorted(stage1_ids)]
    reqs = B.build_requests(rows, store, lambda b: "STAGE1_CALIBRATION",
                            prompt_sha, schema_sha, codes)
    check(len(reqs) == 14, f"{len(reqs)} request rows, expected 14")
    for r in reqs:
        check(r["n_candidates"] == 11,
              f"{r['blinded_document_id']} has {r['n_candidates']} candidates")
        check(sorted(r["candidate_order"]) == sorted(PRODUCTION_IDS),
              f"{r['blinded_document_id']} candidate ids differ from production")

    keys = [k for r in reqs for k in r["cache_keys"].values()]
    check(len(keys) == 28, f"{len(keys)} cache keys, expected 28")
    check(len(set(keys)) == len(keys),
          f"{len(keys) - len(set(keys))} cache-key collisions")

    # leakage, on the exact bytes that will be transmitted
    scaffold_fail, leak_fail, sealed_leak = [], [], []
    for b in sorted(stage1_ids):
        s = store[b]
        if bad := B.scaffold_purity_problems(s["scaffold"]):
            scaffold_fail.append({b: bad})
        body = s["body"]
        if lk := B.transcript_leak_problems(body[body.index("TRANSCRIPT\n\n"):]):
            leak_fail.append({b: lk})
        for tok in ("SEALED", "ORIGINAL_GEMINI", "original_status",
                    R.ORIGINAL_PRESENT, R.ORIGINAL_ABSENCE, "human::"):
            if tok in body:
                sealed_leak.append({b: tok})
    check(not scaffold_fail, f"scaffold leaks: {scaffold_fail}")
    check(not leak_fail, f"transcript provenance leaks: {leak_fail}")
    check(not sealed_leak, f"original-decision leaks: {sealed_leak}")

    for doc_key in cal_docs:
        if doc_key in {b for b in stage1_ids}:
            problems.append("a document key appears where a blinded id was expected")

    # the request builder cannot reach the sealed reference
    import inspect
    src = inspect.getsource(B.build_requests).lower()
    check(not any(t in src for t in ("sealed", "original_status", "doc_key",
                                     "reference")),
          "build_requests names a sealed path or answer-key field")

    return {"pass": not problems, "problems": problems,
            "n_documents": len(cal_docs), "n_requests": len(keys),
            "n_candidates_per_request": 11, "production_ids": PRODUCTION_IDS,
            "n_cells_per_repetition": n_cells, "n_assessments_total": n_cells * 2,
            "n_positive_controls": n_present, "n_absence_cells": n_absence,
            "cache_key_collisions": len(keys) - len(set(keys)),
            "scaffold_leaks": len(scaffold_fail),
            "transcript_leaks": len(leak_fail),
            "original_decision_leaks": len(sealed_leak),
            "builder_reads_sealed_files": False,
            "requests": reqs, "store_keys": sorted(stage1_ids),
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha}


# --------------------------------------------------------------- submit
def submit() -> dict:
    pf = preflight()
    if not pf["pass"]:
        raise Stage1Error("preflight failed:\n  " + "\n  ".join(pf["problems"]))
    if _JOB.exists():
        raise Stage1Error(f"{_JOB.name} already exists; refusing to resubmit")

    _load_env()
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
            cid = f"s1_{n:03d}"
            id_map[cid] = {"blinded_document_id": bid, "repetition_index": rep,
                           "cache_key": r["cache_keys"][str(rep)],
                           "candidate_order": r["candidate_order"],
                           "rendered_sha256": r["rendered_sha256"]}
            reqs.append(Request(
                custom_id=cid,
                params=MessageCreateParamsNonStreaming(
                    model=MODEL,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=B.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": store[bid]["body"]}],
                    output_config={"effort": EFFORT,
                                   "format": {"type": "json_schema",
                                              "schema": B.RESPONSE_SCHEMA}})))

    if len(reqs) != 28:
        raise Stage1Error(f"{len(reqs)} requests built, expected 28")
    if len({v["cache_key"] for v in id_map.values()}) != 28:
        raise Stage1Error("cache-key collision at submission time")

    print(f"submitting Stage 1: {len(reqs)} requests, model {MODEL}, effort {EFFORT}")
    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=reqs)

    rec = {"created_utc": datetime.now(UTC).isoformat(), "job_id": batch.id,
           "stage": "STAGE1_CALIBRATION",
           "processing_status": batch.processing_status,
           "n_requests": len(reqs), "model": MODEL, "effort": EFFORT,
           "max_output_tokens": MAX_OUTPUT_TOKENS,
           "structured_output": "output_config.format json_schema",
           "temperature_transmitted": False, "top_p_transmitted": False,
           "top_k_transmitted": False,
           "prompt_sha256": pf["prompt_sha256"], "schema_sha256": pf["schema_sha256"],
           "retrieval_rule": "by custom_id only, never by response position",
           "custom_id_map": id_map, "preflight": {k: pf[k] for k in
                                                  ("n_documents", "n_requests",
                                                   "n_positive_controls",
                                                   "n_absence_cells",
                                                   "cache_key_collisions")}}
    _atomic(_JOB, rec)                       # persisted immediately after submission
    print("  job id:", batch.id, "->", _JOB.name)
    return rec


def status() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    _load_env()
    import anthropic
    b = anthropic.Anthropic().messages.batches.retrieve(rec["job_id"])
    print(rec["job_id"], b.processing_status, dict(b.request_counts))
    return {"job_id": rec["job_id"], "processing_status": b.processing_status,
            "counts": dict(b.request_counts)}


# ------------------------------------------------------------- retrieve
def retrieve() -> dict:
    """Retrieves strictly by custom_id and preserves raw responses unchanged."""
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    _load_env()
    import anthropic
    client = anthropic.Anthropic()
    b = client.messages.batches.retrieve(rec["job_id"])
    if b.processing_status != "ended":
        raise Stage1Error(f"status {b.processing_status}, not ended")

    id_map = rec["custom_id_map"]
    out = {}
    for res in client.messages.batches.results(rec["job_id"]):
        cid = res.custom_id
        if cid not in id_map:
            raise Stage1Error(f"unknown custom_id {cid}")
        if cid in out:
            raise Stage1Error(f"duplicate custom_id {cid}")
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
        raise Stage1Error(f"missing responses: {missing}")

    payload = {"retrieved_utc": datetime.now(UTC).isoformat(),
               "job_id": rec["job_id"], "stage": "STAGE1_CALIBRATION",
               "matched_by": "custom_id",
               "raw_preserved_unchanged": True,
               "n_results": len(out),
               "total_usage": {
                   "input_tokens": sum(e.get("usage", {}).get("input_tokens", 0)
                                       for e in out.values()),
                   "output_tokens": sum(e.get("usage", {}).get("output_tokens", 0)
                                        for e in out.values())},
               "responses": [out[c] for c in sorted(out)]}
    _atomic(_RAW, payload)
    print(f"retrieved {len(out)} responses -> {_RAW.name}")
    return payload


def main() -> int:
    a = sys.argv[1:]
    if "--preflight" in a:
        pf = preflight()
        print("=== STAGE-1 PREFLIGHT ===")
        for k in ("n_documents", "n_requests", "n_candidates_per_request",
                  "n_cells_per_repetition", "n_assessments_total",
                  "n_positive_controls", "n_absence_cells", "cache_key_collisions",
                  "scaffold_leaks", "transcript_leaks", "original_decision_leaks",
                  "builder_reads_sealed_files"):
            print(f"  {k:28s} {pf[k]}")
        print(f"  production_ids               {' '.join(pf['production_ids'])}")
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
