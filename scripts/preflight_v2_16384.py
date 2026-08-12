"""
preflight_v2 — the three-input preflight at max_output_tokens=16384.

A NEW effective configuration, therefore a NEW cache key. The 32768 human result is
NOT reused: mixing a 32768 baseline with 16384 synthetic results would place a
configuration difference inside the very comparison the study measures. The 32768
cache is never read for comparison, never deleted and never overwritten.

SEQUENCE IS GATED, NOT BATCHED
  1. human FG1
  2. enriched FG1 r2      — only if the human is COMPLETE and untruncated
  3. demographics-only r2 — only if enriched completes

A smaller cap fails quietly: truncated JSON drops codes, and a missing code looks
exactly like `present=false`. Every result is therefore checked by
`tier1_completeness.assess` before it is allowed to gate the next step. If the human
truncates at 16384, nothing downstream runs.

Retries: at most 2 for 500/502/503/504. 401/403/404/429 are terminal and classified
separately. No availability probe. No model or key substitution.

Writes only to analysis/production_evaluation/.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import production_eval_pipeline as pep                        # noqa: E402
import thematic_coding as tc                                  # noqa: E402
import tier1_completeness as comp                             # noqa: E402
from preflight_retry_controlled import (                      # noqa: E402
    RETRY_DELAYS, classify, load_env,
)
from thematic_coding import EVALUATOR_CONFIGS, load_codebook  # noqa: E402

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_CACHE = _OUT / "evaluator_cache"
_ARTIFACT = _OUT / "preflight_v2_16384.json"

MAX_OUTPUT_TOKENS_V2 = 16384


def evaluate(item: dict, codebook, ecfg: dict, effective: dict,
             codebook_sha: str) -> dict:
    entries = pep._entries_for(item)
    blind_text, _ = tc.to_blind_text(entries)
    prompt_sha = pep._sha_text(tc._TIER1_SYSTEM)
    key = pep.cache_key(item["sha256"], "tier1", codebook_sha, prompt_sha,
                        pep.canonical_model_config(effective))
    label = item.get("physical_run") or f"human_{item['fg']}"

    hit = _CACHE / f"{key}.json"
    if hit.exists():
        rec = json.loads(hit.read_text(encoding="utf-8"))
        print(f"  {label:<34} CACHE HIT (16384 key) {key[:16]}...")
        return {"label": label, "status": "cache_hit", "cache_key": key,
                "attempts": 0, "transient_retries": 0, "record": rec,
                "completeness": rec.get("completeness")}

    blind_problems = pep._verify_no_excluded_content(item, blind_text)
    attempts, errors = 0, []
    for i in range(len(RETRY_DELAYS) + 1):
        attempts += 1
        t0 = time.time()
        parse_error = None
        try:
            result, stats = tc.code_transcript_tier1(blind_text, codebook, label,
                                                     evaluator_cfg=ecfg)
        except Exception as exc:                                # noqa: BLE001
            info = classify(exc)
            info["attempt"] = attempts
            errors.append(info)
            print(f"  {label:<34} {info['class']} (HTTP {info['http_status']}) "
                  f"attempt {attempts}")
            if not info["retryable"]:
                print(f"      TERMINAL: {info['diagnosis']}")
                break
            if i < len(RETRY_DELAYS):
                d = RETRY_DELAYS[i]
                print(f"      retryable; waiting {d}s ({i + 1}/{len(RETRY_DELAYS)})")
                time.sleep(d)
                continue
            print("      retry budget exhausted — stopping")
            break

        elapsed = round(time.time() - t0, 2)
        telemetry = dict(tc.LAST_TIER1_CALL_TELEMETRY)
        payload = json.loads(result.model_dump_json())
        verdict = comp.assess(payload.get("codes"), telemetry, parse_error)

        rec = {
            "cache_key": key,
            "computed_utc": datetime.now(UTC).isoformat(),
            "input": {k: item.get(k) for k in
                      ("side", "fg", "condition", "path", "sha256",
                       "physical_run", "canonical_replication_index")},
            "effective_request_config": effective,
            "codebook_sha256": codebook_sha,
            "evaluator_prompt_sha256": prompt_sha,
            "blind_text_sha256": pep._sha_text(blind_text),
            "call_telemetry": telemetry,
            "completeness": verdict,
            "tier1": payload,
            "quote_validity": {
                "total_quotes": stats.total_quotes,
                "verified_quotes": stats.verified_quotes,
                "total_present_codes": stats.total_present_codes,
                "verified_codes": stats.verified_codes,
                "demoted_codes": stats.demoted_codes,
            },
        }
        status = "computed" if verdict["status"] == comp.STATUS_OK else "incomplete"
        if status == "computed":
            _CACHE.mkdir(parents=True, exist_ok=True)
            (_CACHE / f"{key}.json").write_text(
                json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        else:
            # A truncated/incomplete result must never enter the cache: a later run
            # would silently reuse it as if it were a finished evaluation.
            (_OUT / f"preflight_v2_INCOMPLETE_{label}.json").write_text(
                json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")

        print(f"  {label:<34} {status.upper():<10} {elapsed}s  "
              f"codes={verdict['n_codes_returned']}/11  "
              f"finish={verdict['finish_reasons']}  "
              f"out_tokens={verdict['candidates_tokens']}  "
              f"headroom={verdict['headroom_tokens']}")
        for p in verdict["problems"]:
            print(f"      PROBLEM: {p}")
        return {"label": label, "status": status, "cache_key": key,
                "attempts": attempts, "transient_retries": attempts - 1,
                "elapsed_s": elapsed, "errors": errors,
                "excluded_content_problems": blind_problems,
                "completeness": verdict, "record": rec}

    return {"label": label, "status": "failed", "cache_key": key,
            "attempts": attempts, "transient_retries": attempts - 1,
            "errors": errors, "excluded_content_problems": blind_problems}


def main() -> int:
    load_env()
    base = EVALUATOR_CONFIGS[pep.EVALUATOR_KEY]
    ecfg = dict(base, max_output_tokens=MAX_OUTPUT_TOKENS_V2)
    effective = pep.assert_evaluator(ecfg)
    if effective["max_output_tokens"] != MAX_OUTPUT_TOKENS_V2:
        print(f"REFUSING: effective max_output_tokens is "
              f"{effective['max_output_tokens']}, not {MAX_OUTPUT_TOKENS_V2}")
        return 2
    problems = pep.effective_config_coverage_problems(effective)
    if problems:
        print("REFUSING — effective configuration incomplete:", problems)
        return 2

    frozen = pep.load_inputs()
    codebook = load_codebook()
    codebook_sha = frozen["codebook"]["sha256"]
    items = frozen["human_inputs"] + frozen["synthetic_inputs"]

    def pick(side, cond=None):
        for i in items:
            if i["fg"] != "fg1" or i["side"] != side:
                continue
            if side == "synthetic" and (i.get("condition") != cond
                                        or i.get("canonical_replication_index") != 2):
                continue
            return i
        raise RuntimeError(f"input not found: {side}/{cond}")

    print("=" * 78)
    print(f"  PREFLIGHT v2 — max_output_tokens={MAX_OUTPUT_TOKENS_V2}")
    print("=" * 78)
    print(f"\neffective: {pep.canonical_model_config(effective)}\n")

    out = {
        "run_utc": datetime.now(UTC).isoformat(),
        "configuration": "preflight_v2",
        "max_output_tokens": MAX_OUTPUT_TOKENS_V2,
        "effective_request_config": effective,
        "availability_probe_performed": False,
        "reuses_32768_results": False,
        "note_32768": ("The 32768 human result remains cached under key 068e228d... "
                       "and is NOT used here. 32768 and 16384 results are never mixed."),
        "retry_policy": {"max_transient_retries": len(RETRY_DELAYS),
                         "delays_s": list(RETRY_DELAYS)},
        "results": [],
    }

    def record(r):
        out["results"].append({k: v for k, v in r.items() if k != "record"})

    ok = lambda r: r["status"] in ("computed", "cache_hit")

    human = evaluate(pick("human"), codebook, ecfg, effective, codebook_sha)
    record(human)
    if not ok(human):
        print(f"\nSTOPPING: human FG1 did not complete at {MAX_OUTPUT_TOKENS_V2}. "
              f"Nothing downstream is attempted.")
        out["decision"] = "NO_GO"
        out["decision_reason"] = (
            f"human FG1 status={human['status']} at {MAX_OUTPUT_TOKENS_V2}; the gate "
            f"requires a complete, untruncated human result before any synthetic call")
        _ARTIFACT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nartifact: {_ARTIFACT.relative_to(_REPO_ROOT)}")
        return 1

    enriched = evaluate(pick("synthetic", "enriched"), codebook, ecfg, effective,
                        codebook_sha)
    record(enriched)
    if not ok(enriched):
        print("\nSTOPPING: enriched did not complete. demographics-only NOT attempted.")
        out["results"].append({"label": "macho_meals_fg1_demoonly_run02",
                               "status": "not_attempted", "attempts": 0,
                               "transient_retries": 0,
                               "reason": "enriched did not complete; no request issued"})
        out["decision"] = "NO_GO"
        out["decision_reason"] = f"enriched FG1 r2 status={enriched['status']}"
        _ARTIFACT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nartifact: {_ARTIFACT.relative_to(_REPO_ROOT)}")
        return 1

    demo = evaluate(pick("synthetic", "demographics-only"), codebook, ecfg, effective,
                    codebook_sha)
    record(demo)

    all_ok = all(ok(r) for r in (human, enriched, demo))
    out["decision"] = "GO_TO_BATCH" if all_ok else "NO_GO"
    out["decision_reason"] = (
        "all three inputs complete, untruncated, schema-valid" if all_ok
        else "at least one input did not complete")
    out["batch_authorisation"] = ("NOT GRANTED — the remaining 27 evaluations require "
                                  "explicit human authorisation regardless of this "
                                  "decision")
    _ARTIFACT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\ndecision: {out['decision']}")
    print(f"artifact: {_ARTIFACT.relative_to(_REPO_ROOT)}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
