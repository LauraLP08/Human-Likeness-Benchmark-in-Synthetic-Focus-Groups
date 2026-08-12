"""
Three-input preflight via the Gemini Batch API.

WHY BATCH
Synchronous serving has returned 503 for the enriched synthetic window on three
occasions across two output caps. Batch is a different serving path with its own
capacity; whether it is admitted is an empirical question this answers.

JOB CREATION IS NOT IDEMPOTENT
Submitting twice creates two jobs and bills twice. So:
  * the returned job resource name is written to disk IMMEDIATELY, before anything
    else can fail;
  * if that file already exists, this script REFUSES to create another job and
    reports the existing one instead;
  * `--status` polls without ever creating.

BATCH RESULTS ARE NOT SYNCHRONOUS RESULTS
`execution_mode="batch"` is part of the effective configuration and therefore part
of the cache key. A batch response can never satisfy a synchronous lookup, nor the
reverse. The synchronous human results stay under their own keys and are NOT reused
as comparative results here.

Every request is validated before submission: exactly three, correct hashes, and no
full synthetic transcript.

Writes only to analysis/production_evaluation/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import production_eval_pipeline as pep                        # noqa: E402
import thematic_coding as tc                                  # noqa: E402
import tier1_completeness as comp                             # noqa: E402
from preflight_retry_controlled import load_env               # noqa: E402
from thematic_coding import EVALUATOR_CONFIGS, load_codebook  # noqa: E402

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_CACHE = _OUT / "evaluator_cache"
_MANIFEST = _OUT / "preflight_batch_manifest.json"
_JOB = _OUT / "batch_job_preflight.json"          # the non-idempotency guard
_ARTIFACT = _OUT / "preflight_batch_result.json"
_QUARANTINE = _OUT / "quarantine"

MAX_OUTPUT_TOKENS = 16384
EXECUTION_MODE = "batch"
MODEL = "gemini-3.5-flash"


class BatchPreflightError(RuntimeError):
    pass


def build_manifest() -> dict:
    """Three requests, fully hashed, validated before anything is sent."""
    frozen = pep.load_inputs()
    codebook = load_codebook()
    codebook_sha = frozen["codebook"]["sha256"]
    prompt_sha = pep._sha_text(tc._TIER1_SYSTEM)
    ecfg = dict(EVALUATOR_CONFIGS[pep.EVALUATOR_KEY], max_output_tokens=MAX_OUTPUT_TOKENS)
    effective = pep.assert_evaluator(ecfg, EXECUTION_MODE)
    if effective["execution_mode"] != "batch":
        raise BatchPreflightError("execution_mode did not reach the effective config")
    problems = pep.effective_config_coverage_problems(effective)
    if problems:
        raise BatchPreflightError(f"effective config incomplete: {problems}")

    items = frozen["human_inputs"] + frozen["synthetic_inputs"]

    def pick(side, cond=None):
        for i in items:
            if i["fg"] != "fg1" or i["side"] != side:
                continue
            if side == "synthetic" and (i.get("condition") != cond
                                        or i.get("canonical_replication_index") != 2):
                continue
            return i
        raise BatchPreflightError(f"input not found: {side}/{cond}")

    chosen = [("human_fg1", pick("human")),
              ("enriched_fg1_r2", pick("synthetic", "enriched")),
              ("demographics_only_fg1_r2", pick("synthetic", "demographics-only"))]

    stable_prefix = tc._get_tier1_stable_prefix(codebook)
    requests, entries_by_key = [], {}
    for input_id, item in chosen:
        entries = pep._entries_for(item)
        blind_text, _ = tc.to_blind_text(entries)
        blind_sha = pep._sha_text(blind_text)
        excluded = pep._verify_no_excluded_content(item, blind_text)
        if excluded:
            raise BatchPreflightError(f"{input_id}: excluded-content problems {excluded}")
        key = pep.cache_key(item["sha256"], "tier1", codebook_sha, prompt_sha,
                            pep.canonical_model_config(effective))
        requests.append({
            "custom_request_key": input_id,
            "input_id": input_id,
            "side": item["side"],
            "fg": item["fg"],
            "condition": item.get("condition", "human"),
            "canonical_replication_index": item.get("canonical_replication_index"),
            "physical_run": item.get("physical_run"),
            "path": item["path"],
            "window": item.get("window"),
            "transcript_sha256": item["sha256"],
            "blind_text_sha256": blind_sha,
            "blind_text_words": len(blind_text.split()),
            "evaluator_prompt_sha256": prompt_sha,
            "codebook_sha256": codebook_sha,
            "effective_request_config": effective,
            "expected_cache_key": key,
        })
        entries_by_key[input_id] = stable_prefix + f"TRANSCRIPT:\n{blind_text}"

    manifest = {
        "created_utc": datetime.now(UTC).isoformat(),
        "purpose": "three-input preflight via Batch API",
        "batch_request_id_local": "preflight_batch_fg1_16384_v1",
        "model": MODEL,
        "execution_mode": EXECUTION_MODE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "effective_request_config": effective,
        "canonical_model_config": pep.canonical_model_config(effective),
        "reuses_synchronous_results": False,
        "requests": requests,
    }
    validate_manifest(manifest)
    return manifest, entries_by_key, codebook_sha, effective


def validate_manifest(m: dict) -> None:
    """Exactly three requests; no full synthetic transcript; hashes intact."""
    reqs = m["requests"]
    if len(reqs) != 3:
        raise BatchPreflightError(f"expected exactly 3 requests, got {len(reqs)}")
    if len({r["custom_request_key"] for r in reqs}) != 3:
        raise BatchPreflightError("custom request keys are not unique")
    if len({r["expected_cache_key"] for r in reqs}) != 3:
        raise BatchPreflightError("expected cache keys collide")

    sides = sorted((r["side"], r.get("condition")) for r in reqs)
    want = sorted([("human", "human"), ("synthetic", "enriched"),
                   ("synthetic", "demographics-only")])
    if sides != want:
        raise BatchPreflightError(f"wrong input set: {sides}")

    frozen = pep.load_inputs()
    frozen_paths = {i["path"]: i for i in frozen["human_inputs"] + frozen["synthetic_inputs"]}
    for r in reqs:
        if r["path"] not in frozen_paths:
            raise BatchPreflightError(f"{r['input_id']}: path not in frozen inputs")
        if frozen_paths[r["path"]]["sha256"] != r["transcript_sha256"]:
            raise BatchPreflightError(f"{r['input_id']}: transcript hash mismatch")
        # A synthetic request must use a comparable window, never the full transcript.
        if r["side"] == "synthetic":
            if "comparable_transcript" not in r["path"].replace("\\", "/"):
                raise BatchPreflightError(
                    f"{r['input_id']}: synthetic input is NOT a comparable window "
                    f"({r['path']}) — full synthetic transcripts must never be sent")
            if r["window"] != "q1_ask_to_end_of_last_substantive_section":
                raise BatchPreflightError(f"{r['input_id']}: unexpected window "
                                          f"{r['window']!r}")
        if r["effective_request_config"]["execution_mode"] != "batch":
            raise BatchPreflightError(f"{r['input_id']}: execution_mode not batch")
        if r["effective_request_config"]["max_output_tokens"] != MAX_OUTPUT_TOKENS:
            raise BatchPreflightError(f"{r['input_id']}: wrong max_output_tokens")


def submit(manifest: dict, prompts: dict) -> dict:
    if _JOB.exists():
        existing = json.loads(_JOB.read_text(encoding="utf-8"))
        raise BatchPreflightError(
            f"A batch job already exists: {existing.get('job_name')!r} (created "
            f"{existing.get('created_utc')}). Batch creation is NOT idempotent — "
            f"refusing to create another. Use --status to poll it.")

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])

    cfg = types.GenerateContentConfig(
        system_instruction=tc._TIER1_SYSTEM,
        response_mime_type="application/json",
        max_output_tokens=MAX_OUTPUT_TOKENS,
        # temperature and thinking_config are deliberately NOT set.
    )
    # InlinedRequest has no `key` field in google-genai 2.10.0; the custom request
    # key travels in `metadata`, which InlinedResponse echoes back, so each response
    # can be matched to its input rather than matched by position.
    inline = [
        {"model": MODEL,
         "contents": [{"parts": [{"text": prompts[r["custom_request_key"]]}],
                       "role": "user"}],
         "config": cfg,
         "metadata": {"custom_request_key": r["custom_request_key"]}}
        for r in manifest["requests"]
    ]
    print(f"submitting ONE job with {len(inline)} requests ...")
    job = client.batches.create(model=MODEL, src=inline,
                                config={"display_name": manifest["batch_request_id_local"]})
    rec = {
        "created_utc": datetime.now(UTC).isoformat(),
        "job_name": getattr(job, "name", None),
        "display_name": getattr(job, "display_name", None),
        "state": str(getattr(job, "state", None)),
        "model": MODEL,
        "execution_mode": EXECUTION_MODE,
        "n_requests": len(inline),
        "custom_request_keys": [r["custom_request_key"] for r in manifest["requests"]],
        "manifest": str(_MANIFEST.relative_to(_REPO_ROOT)),
        "warning": "batch creation is NOT idempotent — never create again for this preflight",
    }
    # Written before anything else can fail.
    _JOB.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"job name saved immediately: {rec['job_name']}")
    return rec


def poll() -> dict:
    if not _JOB.exists():
        raise BatchPreflightError("no batch job record; nothing to poll")
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    job = client.batches.get(name=rec["job_name"])       # never creates
    state = str(getattr(job, "state", None))
    rec["last_polled_utc"] = datetime.now(UTC).isoformat()
    rec["state"] = state
    err = getattr(job, "error", None)
    if err is not None:
        rec["job_error"] = str(err)[:500]
    _JOB.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"job   : {rec['job_name']}")
    print(f"state : {state}")
    if err is not None:
        print(f"error : {str(err)[:300]}")
    return {"record": rec, "job": job, "client": client}


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest-only", action="store_true",
                    help="build and validate the manifest; submit nothing")
    ap.add_argument("--submit", action="store_true", help="create the ONE batch job")
    ap.add_argument("--status", action="store_true", help="poll without creating")
    args = ap.parse_args()

    if args.status:
        poll()
        return 0

    manifest, prompts, codebook_sha, effective = build_manifest()
    _MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print("=" * 78)
    print("  BATCH PREFLIGHT MANIFEST — validated")
    print("=" * 78)
    print(f"\nlocal batch request id : {manifest['batch_request_id_local']}")
    print(f"effective config       : {manifest['canonical_model_config']}\n")
    for r in manifest["requests"]:
        print(f"  {r['custom_request_key']:<26} {r['side']:<10} {r['condition']:<18} "
              f"{r['blind_text_words']:>6}w")
        print(f"      transcript {r['transcript_sha256'][:16]}...  "
              f"blind {r['blind_text_sha256'][:16]}...")
        print(f"      expected cache key {r['expected_cache_key'][:16]}...")
    print(f"\nmanifest: {_MANIFEST.relative_to(_REPO_ROOT)}")
    print("validated: exactly 3 requests, no full synthetic transcript, hashes match")

    if not args.submit:
        print("\n--manifest-only: nothing submitted.")
        return 0
    submit(manifest, prompts)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BatchPreflightError as exc:
        print(f"REFUSED: {exc}")
        raise SystemExit(2)
