"""
Controlled preflight retry — enriched FG1 r2, then demographics-only FG1 r2.

DIFFERENCES FROM THE PIPELINE'S DEFAULT RETRY BEHAVIOUR

1. **No availability probe.** The model's availability is established by whether the
   real request succeeds, not by a separate small call.

2. **At most 2 transient retries** (30 s, 90 s), not 6. Six retries spent ~17 minutes
   re-asking a provider that had already said it was saturated.

3. **HTTP codes are classified specifically.** The previous behaviour treated every
   `ServerError` as if it were a 503. A 500 is not a 503, and neither is a 429 —
   catching them together produces a diagnosis that reads as provider downtime
   regardless of what actually happened. Only 500/502/503/504 are retried; 401, 403,
   404 and 429 are terminal and reported under their own names.

4. **The human result is reused from cache**, never recomputed — its migration to the
   corrected cache key was proof-gated (`cache_key_migration_log.json`).

5. **Demographics-only is attempted only if enriched succeeds.** If enriched fails
   again, the script stops rather than spending a second input's retry budget against
   a provider that has just refused.

Nothing is substituted on failure: not the model, not the API key, not the thinking
configuration, not the transcripts.

Writes only to analysis/production_evaluation/.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import production_eval_pipeline as pep                         # noqa: E402
import thematic_coding as tc                                   # noqa: E402
from thematic_coding import EVALUATOR_CONFIGS, load_codebook   # noqa: E402

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_CACHE = _OUT / "evaluator_cache"
_LOG = _OUT / "preflight_retry_controlled.json"

RETRY_DELAYS = (30, 90)                 # at most 2 transient retries
RETRYABLE = {500, 502, 503, 504}
TERMINAL = {
    401: ("AUTH_ERROR", "authentication failed — the API key is missing, malformed "
                        "or rejected. This IS a key problem."),
    403: ("PERMISSION_ERROR", "authenticated but not permitted — the key or project "
                              "lacks access to this model. This IS a key/permissions "
                              "problem."),
    404: ("MODEL_NOT_FOUND", "model or endpoint not available to this project. NOT a "
                             "key problem."),
    429: ("RATE_LIMITED", "quota or rate limit. NOT provider downtime and NOT a key "
                          "problem — the key is valid and the model exists."),
}


def http_status(exc: Exception) -> int | None:
    """The actual HTTP status, not an assumption that every ServerError is a 503."""
    for attr in ("code", "status_code"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    resp = getattr(exc, "response", None)
    v = getattr(resp, "status_code", None)
    if isinstance(v, int):
        return v
    text = str(exc)
    for c in (401, 403, 404, 429, 500, 502, 503, 504):
        if text.startswith(f"{c} ") or f"'code': {c}" in text or f'"code": {c}' in text:
            return c
    return None


def classify(exc: Exception) -> dict:
    code = http_status(exc)
    if code in TERMINAL:
        name, why = TERMINAL[code]
        return {"http_status": code, "class": name, "retryable": False, "diagnosis": why}
    if code in RETRYABLE:
        return {"http_status": code, "class": "PROVIDER_UNAVAILABLE", "retryable": True,
                "diagnosis": f"{code} — provider-side. NOT a key problem; do not "
                             f"change the API key."}
    return {"http_status": code, "class": "UNCLASSIFIED", "retryable": False,
            "diagnosis": f"unrecognised failure ({type(exc).__name__}): {str(exc)[:200]}"}


def load_env() -> None:
    p = _REPO_ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cached(key: str) -> dict | None:
    p = _CACHE / f"{key}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def evaluate(item: dict, codebook, ecfg: dict, effective: dict,
             codebook_sha: str) -> dict:
    """One input, with the controlled retry policy."""
    entries = pep._entries_for(item)
    blind_text, _ = tc.to_blind_text(entries)
    prompt_sha = pep._sha_text(tc._TIER1_SYSTEM)
    key = pep.cache_key(item["sha256"], "tier1", codebook_sha, prompt_sha,
                        pep.canonical_model_config(effective))
    label = item.get("physical_run") or f"human_{item['fg']}"

    hit = cached(key)
    if hit:
        print(f"  {label:<34} CACHE HIT  (no call)  key {key[:16]}...")
        return {"label": label, "status": "cache_hit", "cache_key": key,
                "attempts": 0, "transient_retries": 0, "record": hit}

    blind_problems = pep._verify_no_excluded_content(item, blind_text)
    attempts, errors = 0, []
    for i in range(len(RETRY_DELAYS) + 1):
        attempts += 1
        t0 = time.time()
        try:
            result, stats = tc.code_transcript_tier1(blind_text, codebook, label,
                                                     evaluator_cfg=ecfg)
            elapsed = round(time.time() - t0, 2)
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
                "tier1": json.loads(result.model_dump_json()),
                "quote_validity": {
                    "total_quotes": stats.total_quotes,
                    "verified_quotes": stats.verified_quotes,
                    "total_present_codes": stats.total_present_codes,
                    "verified_codes": stats.verified_codes,
                    "demoted_codes": stats.demoted_codes,
                },
            }
            _CACHE.mkdir(parents=True, exist_ok=True)
            (_CACHE / f"{key}.json").write_text(
                json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {label:<34} COMPUTED   {elapsed}s  attempts={attempts}  "
                  f"key {key[:16]}...")
            return {"label": label, "status": "computed", "cache_key": key,
                    "attempts": attempts, "transient_retries": attempts - 1,
                    "elapsed_s": elapsed, "errors": errors,
                    "excluded_content_problems": blind_problems, "record": rec}
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
            else:
                print("      retry budget exhausted — stopping, not escalating")
    return {"label": label, "status": "failed", "cache_key": key,
            "attempts": attempts, "transient_retries": attempts - 1,
            "errors": errors, "excluded_content_problems": blind_problems}


def main() -> int:
    load_env()
    effective = pep.assert_evaluator(EVALUATOR_CONFIGS[pep.EVALUATOR_KEY])
    problems = pep.effective_config_coverage_problems(effective)
    if problems:
        print("REFUSING — effective configuration incomplete:", problems)
        return 2
    ecfg = EVALUATOR_CONFIGS[pep.EVALUATOR_KEY]

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

    print("=" * 76)
    print("  CONTROLLED PREFLIGHT RETRY — no availability probe, max 2 retries")
    print("=" * 76)
    print(f"\nmodel    : {effective['model']}")
    print(f"effective: {pep.canonical_model_config(effective)}\n")

    out = {"run_utc": datetime.now(UTC).isoformat(),
           "effective_request_config": effective,
           "retry_policy": {"max_transient_retries": len(RETRY_DELAYS),
                            "delays_s": list(RETRY_DELAYS),
                            "retryable_http": sorted(RETRYABLE),
                            "terminal_http": sorted(TERMINAL)},
           "availability_probe_performed": False,
           "results": []}

    human = evaluate(pick("human"), codebook, ecfg, effective, codebook_sha)
    out["results"].append({k: v for k, v in human.items() if k != "record"})

    enriched = evaluate(pick("synthetic", "enriched"), codebook, ecfg, effective,
                        codebook_sha)
    out["results"].append({k: v for k, v in enriched.items() if k != "record"})

    if enriched["status"] in ("computed", "cache_hit"):
        demo = evaluate(pick("synthetic", "demographics-only"), codebook, ecfg,
                        effective, codebook_sha)
        out["results"].append({k: v for k, v in demo.items() if k != "record"})
    else:
        print("\nSTOPPING: enriched did not complete. demographics-only NOT attempted "
              "— no request issued.")
        out["results"].append({"label": "macho_meals_fg1_demoonly_run02",
                               "status": "not_attempted", "attempts": 0,
                               "transient_retries": 0,
                               "reason": "enriched did not complete; no request issued"})
        out["next_step"] = ("preflight_v2 with max_output_tokens=16384 — a NEW effective "
                            "configuration requiring a NEW cache key and re-evaluation "
                            "of all three inputs including the human. NOT authorised.")

    _LOG.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nlog: {_LOG.relative_to(_REPO_ROOT)}")
    return 0 if all(r.get("status") in ("computed", "cache_hit")
                    for r in out["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
