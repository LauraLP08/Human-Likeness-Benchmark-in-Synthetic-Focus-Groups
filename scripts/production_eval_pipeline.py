"""
Macho Meals production evaluation pipeline — non-destructive, whitelist-driven.

HARD EVALUATOR GUARD. The pipeline refuses to run on any evaluator other than
`gemini-3.5-flash`. `thematic_coding._MODEL` still defaults to the DISQUALIFIED
`gemini-2.5-flash` (81.8% Gate-1 agreement against an 85% threshold), and
`validate_tier1_reach_tier2.py` defaults to `--evaluator gemini25`, so a forgotten
argument anywhere would silently select the wrong model. The guard makes that
impossible rather than merely discouraged.

EFFECTIVE, NOT LABELLED, CONFIGURATION. `EVALUATOR_CONFIGS["gemininext"]` records
`thinking_level: "medium"`, but `thematic_coding` attaches a thinking config only
for 2.5-class models, so nothing is transmitted for 3.5-flash and temperature is
omitted. The pipeline records — and keys its cache on — what is ACTUALLY sent, so a
cache entry can never claim a parameter that was not part of the request.

INPUTS. Only the 35 frozen documents: 5 complete standardized human transcripts and
30 derived `comparable_transcript.json` windows. Introduction, participant
presentation and closing content never reach the evaluator, by construction.

NON-DESTRUCTIVE.
  * `output/session_logs/` is never written.
  * Results are written once per cache key and never overwritten; a re-run with the
    same key is a cache hit, not a rewrite.
  * Resumable and idempotent: interrupt at any point and re-run.

`scripts/assess_session_batch.py` is deliberately NOT used — it discovers every
directory under the session-log root and would pull in the 12 non-canonical runs.

Usage:
    py scripts/production_eval_pipeline.py --dry-run
    py scripts/production_eval_pipeline.py --one-pair fg1
    py scripts/production_eval_pipeline.py                # full batch (gated elsewhere)
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import thematic_coding as tc                                   # noqa: E402
from thematic_coding import (                                  # noqa: E402
    EVALUATOR_CONFIGS,
    code_transcript_tier1,
    compute_tier1_scores,
    load_codebook,
    to_blind_text,
)

_OUT_DIR = _REPO_ROOT / "analysis" / "production_evaluation"
_CACHE_DIR = _OUT_DIR / "evaluator_cache"
_RESULTS_DIR = _OUT_DIR / "results"
_FROZEN = _OUT_DIR / "frozen_evaluator_inputs.json"

REQUIRED_MODEL = "gemini-3.5-flash"
EVALUATOR_KEY = "gemininext"


class EvaluatorGuardError(RuntimeError):
    """Raised when the resolved evaluator is not the frozen production evaluator."""


def tier1_transmitted_generation_config() -> dict:
    """
    The generation-config keys the Tier-1 call ACTUALLY transmits, read out of
    `thematic_coding.py` rather than restated here.

    Restating them would create a second source of truth that silently drifts: that
    is exactly how `max_output_tokens=32768` came to be transmitted on every call
    while appearing in neither the effective configuration nor the cache key.

    Returns {key: literal_value_or_None}. `None` means the key is set conditionally
    and its value is resolved by `effective_request_config`.
    """
    src = (_REPO_ROOT / "scripts" / "thematic_coding.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "code_transcript_tier1"), None)
    if fn is None:
        raise EvaluatorGuardError(
            "code_transcript_tier1 not found in thematic_coding.py — the effective "
            "request configuration cannot be verified against the real call.")
    keys: dict[str, object] = {}
    for node in ast.walk(fn):
        # the literal dict. NOTE: `_gen_cfg: dict = {...}` is an AnnAssign, not an
        # Assign — matching only Assign silently found nothing and let the very
        # parameters this function exists to catch slip through.
        targets = []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
        else:
            continue
        for tgt in targets:
            if isinstance(tgt, ast.Name) and tgt.id == "_gen_cfg" and isinstance(node.value, ast.Dict):
                for k, v in zip(node.value.keys, node.value.values):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys[k.value] = (v.value if isinstance(v, ast.Constant) else None)
            # conditional additions:  _gen_cfg["temperature"] = ...
            if (isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.value, ast.Name) and tgt.value.id == "_gen_cfg"
                    and isinstance(tgt.slice, ast.Constant)):
                keys.setdefault(tgt.slice.value, None)
    if not keys:
        raise EvaluatorGuardError(
            "No generation-config keys were recovered from code_transcript_tier1. "
            "Refusing to report an effective configuration that was not verified "
            "against the real call.")
    return keys


# Parameters that are transmitted but are NOT part of the model configuration for
# cache purposes, each with the reason. `system_instruction` is the evaluator prompt,
# already hashed into the cache key as `evaluator_prompt_sha256`; including it twice
# would not change what the key distinguishes.
TRANSMITTED_BUT_KEYED_SEPARATELY = {
    "system_instruction": "hashed into the cache key as evaluator_prompt_sha256",
}


def effective_request_config(ecfg: dict, execution_mode: str = "synchronous") -> dict:
    """
    What is ACTUALLY transmitted, not what the config labels claim.

    EVERY transmitted generation parameter that can change the output appears here,
    and this dict is serialised verbatim into the cache key. A parameter that
    influences the result but is absent from the key would let two materially
    different runs collide on one cache entry.
    """
    if execution_mode not in ("synchronous", "batch"):
        raise EvaluatorGuardError(f"unknown execution_mode {execution_mode!r}")
    model = ecfg["model"]
    sends_thinking = "2.5" in model
    transmitted = tier1_transmitted_generation_config()
    return {
        # Batch and synchronous serving are different execution paths. A batch
        # response must never satisfy a synchronous cache lookup, or vice versa, so
        # the mode is part of the keyed configuration rather than metadata beside it.
        "execution_mode": execution_mode,
        "model": model,
        # --- always transmitted, read from thematic_coding.py ---
        "response_mime_type": transmitted.get("response_mime_type"),
        # The cap is overridable per evaluator_cfg (preflight_v2 = 16384). The value
        # recorded here is the one actually transmitted, and it keys the cache, so a
        # 16384 run can never be served a 32768 result.
        "max_output_tokens": ecfg.get("max_output_tokens",
                                      tc.TIER1_DEFAULT_MAX_OUTPUT_TOKENS),
        # --- conditionally transmitted ---
        "temperature_transmitted": ecfg.get("temperature") is not None,
        "temperature": ecfg.get("temperature"),
        "thinking_config_transmitted": sends_thinking,
        "thinking_config": ({"thinking_budget": 0} if sends_thinking else None),
        "thinking_level_effective": (ecfg.get("thinking_level") if sends_thinking
                                     else "model_default_unpinned"),
        "thinking_level_label_in_config": ecfg.get("thinking_level"),
    }


def canonical_model_config(effective: dict) -> str:
    """
    The exact string that enters the cache key. Sorted keys so ordering cannot
    change the hash, and no field dropped: if it was transmitted and it can move the
    output, it keys the cache.
    """
    return json.dumps(effective, sort_keys=True, separators=(",", ":"))


def effective_config_coverage_problems(effective: dict) -> list[str]:
    """
    Every parameter the Tier-1 call transmits must appear in `effective`, or be
    listed in TRANSMITTED_BUT_KEYED_SEPARATELY with a reason.
    """
    problems = []
    for key in tier1_transmitted_generation_config():
        # `max_output_tokens` resolves at call time from evaluator_cfg, so its AST
        # value is a call expression rather than a literal; presence is what matters.
        if key in TRANSMITTED_BUT_KEYED_SEPARATELY:
            continue
        present = key in effective or f"{key}_transmitted" in effective
        if not present:
            problems.append(
                f"{key!r} is transmitted by code_transcript_tier1 but is absent from "
                f"effective_request_config, so it does not key the cache")
    return problems


def assert_evaluator(ecfg: dict | None, execution_mode: str = "synchronous") -> dict:
    """
    Hard guard. Checks the resolved config AND the module default, because a call
    that omits `evaluator_cfg` silently falls back to `thematic_coding._MODEL`.
    """
    if ecfg is None:
        raise EvaluatorGuardError(
            "No evaluator_cfg supplied. Omitting it falls back to "
            f"thematic_coding._MODEL = {tc._MODEL!r}, which is the disqualified "
            f"evaluator. Pass EVALUATOR_CONFIGS['{EVALUATOR_KEY}'] explicitly.")
    model = ecfg.get("model")
    if model != REQUIRED_MODEL:
        raise EvaluatorGuardError(
            f"Resolved evaluator is {model!r}, not the frozen production evaluator "
            f"{REQUIRED_MODEL!r}. gemini-2.5-flash is DISQUALIFIED (81.8% worst "
            f"pairwise Gate-1 agreement, below the 85% threshold). Refusing to run.")
    if not ecfg.get("key_env"):
        raise EvaluatorGuardError("Evaluator config carries no key_env; refusing to run.")
    return effective_request_config(ecfg, execution_mode)


def _sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# `thematic_coding._generate_with_fallback` retries 429 onto a backup key, but a
# 503 UNAVAILABLE ("model experiencing high demand") has no key to fall back to and
# would abort a batch mid-way. Retried here rather than in thematic_coding, so the
# evaluator call path stays untouched. Retries are logged per input.
_RETRY_DELAYS = (20, 60, 120, 240, 300, 300)


def _with_retry(fn, *args, **kwargs):
    from google.genai import errors as genai_errors
    attempts = 0
    for delay in (*_RETRY_DELAYS, None):
        try:
            return fn(*args, **kwargs), attempts
        except genai_errors.ServerError as exc:
            attempts += 1
            if delay is None:
                raise
            print(f"      [transient] {str(exc)[:70]} — retrying in {delay}s "
                  f"({attempts}/{len(_RETRY_DELAYS)})", flush=True)
            time.sleep(delay)


def cache_key(transcript_sha: str, tier: str, codebook_sha: str,
              prompt_sha: str, model_cfg_json: str) -> str:
    return hashlib.sha256(
        "|".join([transcript_sha, tier, codebook_sha, prompt_sha, model_cfg_json]).encode()
    ).hexdigest()


def load_inputs() -> dict:
    if not _FROZEN.exists():
        raise RuntimeError(f"{_FROZEN} not found — run scripts/freeze_evaluator_inputs.py first.")
    return json.loads(_FROZEN.read_text(encoding="utf-8"))


def _entries_for(item: dict) -> list[dict]:
    """Human inputs are plain transcripts; synthetic inputs are windowed payloads."""
    payload = json.loads((_REPO_ROOT / item["path"]).read_text(encoding="utf-8"))
    return payload["transcript"] if isinstance(payload, dict) else payload


def _verify_no_excluded_content(item: dict, blind_text: str) -> list[str]:
    """
    Confirm the evaluator is not receiving introduction, participant-presentation or
    closing material. For synthetic inputs the window guarantees this structurally;
    this re-checks it against the text actually being sent.
    """
    problems = []
    low = blind_text.lower()
    if item["side"] == "synthetic":
        for marker in ("research purposes", "no right or wrong", "45 minutes",
                       "my name's", "i'll be moderating", "i'll be facilitating",
                       "i'll be leading"):
            if marker in low:
                problems.append(f"introduction/instruction marker present: {marker!r}")
    for line in blind_text.splitlines():
        if "] " in line:
            spk = line.split("] ", 1)[1].split(":", 1)[0]
            if spk != "Moderator" and not spk.startswith("Participant "):
                problems.append(f"non-blinded speaker label: {spk!r}")
                break
    return problems


def run_tier1(item: dict, codebook: list[dict], ecfg: dict, effective: dict,
              codebook_sha: str, dry_run: bool) -> dict:
    entries = _entries_for(item)
    blind_text, speaker_map = to_blind_text(entries)
    prompt_sha = _sha_text(tc._TIER1_SYSTEM)
    model_cfg_json = canonical_model_config(effective)
    key = cache_key(item["sha256"], "tier1", codebook_sha, prompt_sha, model_cfg_json)

    blind_problems = _verify_no_excluded_content(item, blind_text)
    rec = {
        "label": item.get("physical_run") or f"human_{item['fg']}",
        "side": item["side"], "fg": item["fg"],
        "condition": item.get("condition", "human"),
        "canonical_replication_index": item.get("canonical_replication_index"),
        "transcript_sha256": item["sha256"],
        "cache_key": key,
        "blind_text_sha256": _sha_text(blind_text),
        "blind_text_words": len(blind_text.split()),
        "blind_text_lines": len(blind_text.splitlines()),
        "speakers": sorted(set(speaker_map.values())),
        "excluded_content_problems": blind_problems,
    }

    cache_path = _CACHE_DIR / f"{key}.json"
    if cache_path.exists():
        rec["status"] = "cache_hit"
        rec["result_path"] = str(cache_path.relative_to(_REPO_ROOT))
        return rec
    if dry_run:
        rec["status"] = "would_call"
        return rec

    t0 = time.monotonic()
    (result, stats), retries = _with_retry(
        code_transcript_tier1, blind_text, codebook, rec["label"], ecfg)
    rec.update({
        "status": "computed",
        "transient_retries": retries,
        "elapsed_s": round(time.monotonic() - t0, 2),
        "present_codes": sorted(c.subtheme_id for c in result.codes
                                if c.present and c.quote_verified),
        "quote_verification_rate": round(stats.quote_verification_rate, 4),
        "code_preservation_rate": round(stats.code_preservation_rate, 4),
        "demoted_codes": stats.demoted_codes,
        "total_quotes": stats.total_quotes,
        "verified_quotes": stats.verified_quotes,
    })

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():                      # never overwrite
        rec["status"] = "cache_hit_race"
        return rec
    cache_path.write_text(json.dumps({
        "cache_key": key,
        "computed_utc": datetime.now(UTC).isoformat(),
        "input": {k: item.get(k) for k in ("side", "fg", "condition", "path",
                                           "sha256", "physical_run",
                                           "canonical_replication_index")},
        "effective_request_config": effective,
        "codebook_sha256": codebook_sha,
        "evaluator_prompt_sha256": prompt_sha,
        "blind_text_sha256": rec["blind_text_sha256"],
        "tier1": json.loads(result.model_dump_json()),
        "quote_validity": {
            "total_quotes": stats.total_quotes,
            "verified_quotes": stats.verified_quotes,
            "total_present_codes": stats.total_present_codes,
            "verified_codes": stats.verified_codes,
            "demoted_codes": stats.demoted_codes,
        },
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    rec["result_path"] = str(cache_path.relative_to(_REPO_ROOT))
    return rec


def main(dry_run: bool, one_pair: str | None) -> None:
    ecfg = EVALUATOR_CONFIGS.get(EVALUATOR_KEY)
    print("=" * 80)
    print("  MACHO MEALS — PRODUCTION EVALUATION PIPELINE")
    print("=" * 80)

    try:
        effective = assert_evaluator(ecfg)
    except EvaluatorGuardError as exc:
        print(f"\nEVALUATOR GUARD TRIPPED — refusing to run.\n  {exc}")
        sys.exit(3)
    print("\nEVALUATOR GUARD: passed")
    print(f"  required model        : {REQUIRED_MODEL}")
    print(f"  resolved model        : {ecfg['model']}")
    print(f"  module default (unused): thematic_coding._MODEL = {tc._MODEL}")
    print("  effective request configuration (what is actually sent):")
    for k, v in effective.items():
        print(f"      {k:<32} {v}")

    frozen = load_inputs()
    codebook = load_codebook()
    codebook_sha = frozen["codebook"]["sha256"]

    items = frozen["human_inputs"] + frozen["synthetic_inputs"]
    if one_pair:
        fg = one_pair.lower()
        chosen = [i for i in items if i["fg"] == fg and (
            i["side"] == "human" or i.get("canonical_replication_index") == 2)]
        items = chosen
        print(f"\nONE-PAIR PREFLIGHT — {fg}: human vs canonical replication 2 of each condition")

    print(f"\nInputs: {len(items)}  "
          f"(human {sum(1 for i in items if i['side'] == 'human')}, "
          f"synthetic {sum(1 for i in items if i['side'] == 'synthetic')})")
    print(f"Mode  : {'DRY RUN — no API call' if dry_run else 'LIVE'}")

    records = []
    for item in items:
        rec = run_tier1(item, codebook, ecfg, effective, codebook_sha, dry_run)
        records.append(rec)
        label = rec["label"]
        extra = ""
        if rec["status"] == "computed":
            extra = (f"  present={len(rec['present_codes'])}/11  "
                     f"quote_verif={rec['quote_verification_rate']:.0%}  "
                     f"{rec['elapsed_s']}s")
        print(f"  {label:<34} {rec['condition']:<18} {rec['status']:<12}"
              f"{rec['blind_text_words']:>7}w{extra}")
        if rec["excluded_content_problems"]:
            for p in rec["excluded_content_problems"]:
                print(f"      EXCLUDED-CONTENT PROBLEM: {p}")

    problems = [r for r in records if r["excluded_content_problems"]]
    dupes = len(records) - len({r["cache_key"] for r in records})
    print(f"\nCache keys unique          : {dupes == 0}")
    print(f"Excluded-content problems  : {len(problems)}")

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tag = "dryrun" if dry_run else (f"onepair_{one_pair}" if one_pair else "batch")
    out = _RESULTS_DIR / f"pipeline_run_{tag}.json"
    out.write_text(json.dumps({
        "run_utc": datetime.now(UTC).isoformat(),
        "mode": tag,
        "evaluator_guard": "passed",
        "required_model": REQUIRED_MODEL,
        "effective_request_config": effective,
        "module_default_model_unused": tc._MODEL,
        "codebook_sha256": codebook_sha,
        "evaluator_prompt_sha256_tier1": _sha_text(tc._TIER1_SYSTEM),
        "records": records,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out.relative_to(_REPO_ROOT)}")

    if problems:
        sys.exit(4)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--one-pair", default=None, metavar="FG")
    a = ap.parse_args()
    main(a.dry_run, a.one_pair)
