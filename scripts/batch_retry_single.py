"""
Single-request Batch retry for one input, under the identical frozen configuration.

The previous attempt for `macho_meals_fg5_run01` returned 12 code entries (`A.3`
twice) and was quarantined. That artifact is left untouched: it is the evidence that
the first attempt was malformed. Nothing is deduplicated by hand — hand-editing a
model response would put a researcher-authored object into the corpus under a cache
key that claims it came from the evaluator.

Configuration is re-derived from the same sources as the corpus job, not copied, so
the retry cannot silently differ. The cache key is therefore identical to the one the
corpus manifest expected for this input.

Acceptance is all-or-nothing: STOP, exactly 11 unique ids in the expected order,
valid schema, verified quotes, zero moderator quotes, zero excluded-content problems.
Anything else goes back to quarantine under a distinct name.

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
_QUAR = _OUT / "quarantine"

MODEL = "gemini-3.5-flash"
MAX_OUTPUT_TOKENS = 16384
EXECUTION_MODE = "batch"


class RetryError(RuntimeError):
    pass


def resolve(target: str):
    frozen = pep.load_inputs()
    items = frozen["human_inputs"] + frozen["synthetic_inputs"]
    for i in items:
        label = i.get("physical_run") or f"human_{i['fg']}"
        if label == target:
            return i, frozen["codebook"]["sha256"]
    raise RetryError(f"{target} not found in frozen inputs")


def prepare(target: str):
    item, codebook_sha = resolve(target)
    codebook = load_codebook()
    ecfg = dict(EVALUATOR_CONFIGS[pep.EVALUATOR_KEY], max_output_tokens=MAX_OUTPUT_TOKENS)
    effective = pep.assert_evaluator(ecfg, EXECUTION_MODE)
    if pep.effective_config_coverage_problems(effective):
        raise RetryError("effective configuration incomplete")
    entries = pep._entries_for(item)
    blind_text, _ = tc.to_blind_text(entries)
    excluded = pep._verify_no_excluded_content(item, blind_text)
    if excluded:
        raise RetryError(f"excluded-content problems before sending: {excluded}")
    prompt_sha = pep._sha_text(tc._TIER1_SYSTEM)
    key = pep.cache_key(item["sha256"], "tier1", codebook_sha, prompt_sha,
                        pep.canonical_model_config(effective))
    if (_CACHE / f"{key}.json").exists():
        raise RetryError(f"{target} already has a COMPLETE cache entry at {key[:16]}...")
    prompt = tc._get_tier1_stable_prefix(codebook) + f"TRANSCRIPT:\n{blind_text}"
    return {"item": item, "effective": effective, "key": key, "prompt": prompt,
            "blind_text": blind_text, "prompt_sha": prompt_sha,
            "codebook_sha": codebook_sha}


def main() -> int:
    load_env()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--retrieve", action="store_true")
    args = ap.parse_args()
    job_file = _OUT / f"batch_job_retry_{args.target}.json"

    ctx = prepare(args.target)
    print(f"target            : {args.target}")
    print(f"transcript sha    : {ctx['item']['sha256'][:16]}...")
    print(f"expected cache key: {ctx['key'][:16]}...")
    print(f"effective         : {pep.canonical_model_config(ctx['effective'])}")

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])

    if args.status or args.retrieve:
        rec = json.loads(job_file.read_text(encoding="utf-8"))
        job = client.batches.get(name=rec["job_name"])
        rec["state"] = str(getattr(job, "state", None))
        rec["last_polled_utc"] = datetime.now(UTC).isoformat()
        job_file.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"job   : {rec['job_name']}\nstate : {rec['state']}")
        if not args.retrieve:
            return 0
        responses = list(getattr(job.dest, "inlined_responses", None) or [])
        if len(responses) != 1:
            raise RetryError(f"expected 1 response, got {len(responses)}")
        resp = responses[0]
        if getattr(resp, "error", None):
            raise RetryError(f"request error: {resp.error}")
        r = resp.response
        cands = getattr(r, "candidates", None) or []
        um = getattr(r, "usage_metadata", None)
        telemetry = {
            "max_output_tokens_requested": MAX_OUTPUT_TOKENS,
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
            result = tc.Tier1Result.model_validate(json.loads(tc._strip_fences(r.text)))
            n_part = tc._count_participants(ctx["blind_text"])
            verified, stats = tc.verify_codes(result, ctx["blind_text"],
                                              transcript_label=args.target,
                                              n_participants=n_part)
            payload = json.loads(verified.model_dump_json())
        except Exception as exc:                                # noqa: BLE001
            parse_error = exc
        verdict = comp.assess(payload.get("codes") if payload else None,
                              telemetry, parse_error)

        # extra acceptance conditions beyond completeness
        extra = []
        if payload:
            ids = [c["subtheme_id"] for c in payload["codes"]]
            if ids != list(comp.EXPECTED_SUBTHEME_IDS):
                extra.append(f"ids not unique/in expected order: {ids}")
            mod_quotes = 0
            for c in payload["codes"]:
                for q in c.get("supporting_quotes", []) or []:
                    spk = str(q.get("speaker", ""))
                    if spk.lower().startswith("moderator"):
                        mod_quotes += 1
            if mod_quotes:
                extra.append(f"{mod_quotes} moderator-sourced quote(s)")
            if stats and stats.total_quotes != stats.verified_quotes:
                extra.append(f"quote verification {stats.verified_quotes}/{stats.total_quotes}")

        rec_out = {
            "cache_key": ctx["key"],
            "computed_utc": datetime.now(UTC).isoformat(),
            "execution_mode": EXECUTION_MODE,
            "batch_job_name": rec["job_name"],
            "custom_request_key": args.target,
            "retry_of": "quarantine/batch_macho_meals_fg5_run01.json",
            "input": {k: ctx["item"].get(k) for k in
                      ("side", "fg", "condition", "path", "sha256", "physical_run",
                       "canonical_replication_index")},
            "effective_request_config": ctx["effective"],
            "codebook_sha256": ctx["codebook_sha"],
            "evaluator_prompt_sha256": ctx["prompt_sha"],
            "blind_text_sha256": pep._sha_text(ctx["blind_text"]),
            "call_telemetry": telemetry,
            "completeness": verdict,
            "extra_acceptance_problems": extra,
            "tier1": payload,
            "quote_validity": ({"total_quotes": stats.total_quotes,
                                "verified_quotes": stats.verified_quotes,
                                "total_present_codes": stats.total_present_codes,
                                "verified_codes": stats.verified_codes,
                                "demoted_codes": stats.demoted_codes} if stats else None),
        }
        accepted = verdict["status"] == comp.STATUS_OK and not extra
        if accepted:
            (_CACHE / f"{ctx['key']}.json").write_text(
                json.dumps(rec_out, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"\nACCEPTED -> cached as {ctx['key'][:16]}...")
        else:
            _QUAR.mkdir(parents=True, exist_ok=True)
            out = _QUAR / f"batch_{args.target}_retry.json"
            out.write_text(json.dumps(rec_out, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"\nREJECTED -> {out.name}")
            for p in verdict["problems"] + extra:
                print(f"   PROBLEM: {p}")
        print(f"codes={verdict['n_codes_returned']}/11 finish={verdict['finish_reasons']} "
              f"out={telemetry['candidates_tokens']} "
              f"quotes={rec_out['quote_validity']['verified_quotes'] if stats else '-'}"
              f"/{rec_out['quote_validity']['total_quotes'] if stats else '-'}")
        return 0 if accepted else 1

    if not args.submit:
        print("\nnot submitted (pass --submit).")
        return 0
    if job_file.exists():
        raise RetryError(f"a retry job already exists: "
                         f"{json.loads(job_file.read_text(encoding='utf-8'))['job_name']!r}. "
                         f"Creation is NOT idempotent — refusing to create another.")

    cfg = types.GenerateContentConfig(
        system_instruction=tc._TIER1_SYSTEM,
        response_mime_type="application/json",
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    inline = [{"model": MODEL,
               "contents": [{"parts": [{"text": ctx["prompt"]}], "role": "user"}],
               "config": cfg,
               "metadata": {"custom_request_key": args.target}}]
    print("\nsubmitting ONE job with 1 request ...")
    job = client.batches.create(model=MODEL, src=inline,
                                config={"display_name": f"retry_{args.target}"})
    job_file.write_text(json.dumps({
        "created_utc": datetime.now(UTC).isoformat(),
        "job_name": getattr(job, "name", None),
        "state": str(getattr(job, "state", None)),
        "target": args.target, "n_requests": 1,
        "expected_cache_key": ctx["key"],
        "retry_of": "quarantine/batch_macho_meals_fg5_run01.json",
        "previous_attempt_preserved": True,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"job name saved immediately: {getattr(job, 'name', None)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RetryError as exc:
        print(f"REFUSED: {exc}")
        raise SystemExit(2)
