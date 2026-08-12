"""Retrieve batch responses by custom request key, validate, cache or quarantine."""
import json, os, sys, pathlib
sys.path.insert(0, "scripts")
from datetime import datetime, UTC

import production_eval_pipeline as pep
import thematic_coding as tc
import tier1_completeness as comp
from preflight_retry_controlled import load_env

OUT = pathlib.Path("analysis/production_evaluation")
CACHE, QUAR = OUT / "evaluator_cache", OUT / "quarantine"
load_env()

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--job", default="batch_job_preflight.json")
_ap.add_argument("--manifest", default="preflight_batch_manifest.json")
_ap.add_argument("--out", default="preflight_batch_result.json")
_a = _ap.parse_args()
job_rec = json.loads((OUT / _a.job).read_text(encoding="utf-8"))
manifest = json.loads((OUT / _a.manifest).read_text(encoding="utf-8"))
by_key = {r["custom_request_key"]: r for r in manifest["requests"]}

from google import genai
client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
job = client.batches.get(name=job_rec["job_name"])
dest = job.dest
responses = list(getattr(dest, "inlined_responses", None) or [])
print(f"state: {job.state}   inlined responses: {len(responses)}")

out = {
    "retrieved_utc": datetime.now(UTC).isoformat(),
    "job_name": job_rec["job_name"],
    "job_state": str(job.state),
    "execution_mode": "batch",
    "max_output_tokens": manifest["max_output_tokens"],
    "effective_request_config": manifest["effective_request_config"],
    "reuses_synchronous_results": False,
    "n_responses": len(responses),
    "results": [],
}

for i, resp in enumerate(responses):
    meta = getattr(resp, "metadata", None) or {}
    key = (meta.get("custom_request_key") if isinstance(meta, dict)
           else getattr(meta, "custom_request_key", None))
    err = getattr(resp, "error", None)
    entry = {"custom_request_key": key, "position": i}
    if key not in by_key:
        entry.update(status="UNMATCHED", detail=f"metadata={meta!r}")
        out["results"].append(entry)
        print(f"  [{i}] UNMATCHED metadata: {meta!r}")
        continue
    man = by_key[key]
    entry.update({k: man[k] for k in ("input_id", "side", "condition", "fg",
                                      "canonical_replication_index", "physical_run",
                                      "transcript_sha256", "blind_text_sha256",
                                      "expected_cache_key")})
    if err is not None:
        entry.update(status="REQUEST_ERROR", error=str(err)[:400])
        print(f"  {key:<26} REQUEST_ERROR {str(err)[:120]}")
        out["results"].append(entry)
        continue

    r = resp.response
    cands = getattr(r, "candidates", None) or []
    um = getattr(r, "usage_metadata", None)
    telemetry = {
        "max_output_tokens_requested": manifest["max_output_tokens"],
        "finish_reasons": [str(getattr(c, "finish_reason", None)) for c in cands],
        "n_candidates": len(cands),
        "prompt_tokens": getattr(um, "prompt_token_count", None),
        "candidates_tokens": getattr(um, "candidates_token_count", None),
        "total_tokens": getattr(um, "total_token_count", None),
        "thoughts_tokens": getattr(um, "thoughts_token_count", None),
        "cached_tokens": getattr(um, "cached_content_token_count", None),
        "raw_text_chars": len(getattr(r, "text", "") or ""),
        "parse_attempt": 1,
    }
    parse_error, payload, stats = None, None, None
    try:
        raw = tc._strip_fences(r.text)
        result = tc.Tier1Result.model_validate(json.loads(raw))
        blind_text, _ = tc.to_blind_text(pep._entries_for(
            {"path": man["path"], "side": man["side"]}))
        n_part = tc._count_participants(blind_text)
        verified, stats = tc.verify_codes(result, blind_text,
                                          transcript_label=key, n_participants=n_part)
        payload = json.loads(verified.model_dump_json())
    except Exception as exc:                                    # noqa: BLE001
        parse_error = exc

    verdict = comp.assess(payload.get("codes") if payload else None,
                          telemetry, parse_error)
    entry["call_telemetry"] = telemetry
    entry["completeness"] = verdict
    rec = {
        "cache_key": man["expected_cache_key"],
        "computed_utc": out["retrieved_utc"],
        "execution_mode": "batch",
        "batch_job_name": job_rec["job_name"],
        "custom_request_key": key,
        "input": {"side": man["side"], "fg": man["fg"], "condition": man.get("condition"),
                  "path": man["path"], "sha256": man["transcript_sha256"],
                  "physical_run": man.get("physical_run"),
                  "canonical_replication_index": man.get("canonical_replication_index")},
        "effective_request_config": manifest["effective_request_config"],
        "codebook_sha256": man["codebook_sha256"],
        "evaluator_prompt_sha256": man["evaluator_prompt_sha256"],
        "blind_text_sha256": man["blind_text_sha256"],
        "call_telemetry": telemetry,
        "completeness": verdict,
        "tier1": payload,
        "quote_validity": ({"total_quotes": stats.total_quotes,
                            "verified_quotes": stats.verified_quotes,
                            "total_present_codes": stats.total_present_codes,
                            "verified_codes": stats.verified_codes,
                            "demoted_codes": stats.demoted_codes} if stats else None),
    }
    if verdict["status"] == comp.STATUS_OK:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / f"{man['expected_cache_key']}.json").write_text(
            json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        entry["status"] = "COMPLETE"
        entry["cached_as"] = man["expected_cache_key"]
    else:
        QUAR.mkdir(parents=True, exist_ok=True)
        (QUAR / f"batch_{key}.json").write_text(
            json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        entry["status"] = "QUARANTINED"
    entry["quote_validity"] = rec["quote_validity"]
    out["results"].append(entry)
    print(f"  {key:<26} {entry['status']:<12} codes={verdict['n_codes_returned']}/11 "
          f"finish={verdict['finish_reasons']} out={telemetry['candidates_tokens']} "
          f"quotes={rec['quote_validity']['verified_quotes'] if rec['quote_validity'] else '-'}"
          f"/{rec['quote_validity']['total_quotes'] if rec['quote_validity'] else '-'}")
    for p in verdict["problems"]:
        print(f"      PROBLEM: {p}")

(OUT / _a.out).write_text(
    json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
print("\nwrote preflight_batch_result.json")
