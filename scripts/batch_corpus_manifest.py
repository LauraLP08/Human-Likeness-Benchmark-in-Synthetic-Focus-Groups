"""
Production Batch manifest — the frozen corpus minus what the Batch preflight already
completed.

THE COUNT IS DERIVED, NEVER ASSERTED
An earlier report said "the remaining 27 evaluations", which was simply wrong: the
preflight completed 3 of 35, so 32 remain. The number is now computed from
`frozen_evaluator_inputs.json` and the set of COMPLETE batch cache keys on disk, so
it cannot drift from a stale sentence in a document.

Completion means a batch-mode cache entry whose `completeness.status` is COMPLETE.
A quarantined or synchronous entry does not count: a quarantined result is not a
result, and a synchronous result answers a different cache key.

Validation runs before anything is sent, and covers the FINAL set
(preflight + production), not just this job — the design guarantees are about the
corpus, not about one submission.

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
from thematic_coding import EVALUATOR_CONFIGS, load_codebook  # noqa: E402

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_CACHE = _OUT / "evaluator_cache"
_MANIFEST = _OUT / "batch_corpus_manifest.json"
_JOB = _OUT / "batch_job_corpus.json"

MODEL = "gemini-3.5-flash"
MAX_OUTPUT_TOKENS = 16384
EXECUTION_MODE = "batch"

EXPECTED_TOTAL = 35
EXPECTED_HUMAN = 5
EXPECTED_SYNTHETIC = 30
EXPECTED_REPLICATES = 3
CONDITIONS = ("enriched", "demographics-only")
FGS = ("fg1", "fg2", "fg3", "fg4", "fg5")

# From the canonical manifest — recorded so the archived runs cannot silently return.
ARCHIVED_EXCLUDED = ("macho_meals_fg4_run02", "macho_meals_fg5_run02")
FG4_ENRICHED_EXPECTED = ("macho_meals_fg4_run01", "macho_meals_fg4_run04",
                         "macho_meals_fg4_run03")
FG5_ENRICHED_EXPECTED = ("macho_meals_fg5_run01", "macho_meals_fg5_run03",
                         "macho_meals_fg5_run04")


class ManifestError(RuntimeError):
    pass


def input_id_for(item: dict) -> str:
    if item["side"] == "human":
        return f"human_{item['fg']}"
    return item["physical_run"]


def completed_batch_keys() -> dict[str, dict]:
    """Cache keys of COMPLETE batch-mode results only."""
    out = {}
    for p in _CACHE.glob("*.json"):
        j = json.loads(p.read_text(encoding="utf-8"))
        eff = j.get("effective_request_config") or {}
        if eff.get("execution_mode") != EXECUTION_MODE:
            continue
        if (j.get("completeness") or {}).get("status") != "COMPLETE":
            continue
        out[j["cache_key"]] = j
    return out


def build() -> tuple[dict, dict]:
    frozen = pep.load_inputs()
    codebook = load_codebook()
    codebook_sha = frozen["codebook"]["sha256"]
    prompt_sha = pep._sha_text(tc._TIER1_SYSTEM)
    ecfg = dict(EVALUATOR_CONFIGS[pep.EVALUATOR_KEY], max_output_tokens=MAX_OUTPUT_TOKENS)
    effective = pep.assert_evaluator(ecfg, EXECUTION_MODE)
    if pep.effective_config_coverage_problems(effective):
        raise ManifestError("effective configuration incomplete")

    items = frozen["human_inputs"] + frozen["synthetic_inputs"]
    if len(items) != EXPECTED_TOTAL:
        raise ManifestError(f"frozen inputs = {len(items)}, expected {EXPECTED_TOTAL}")

    done = completed_batch_keys()
    stable_prefix = tc._get_tier1_stable_prefix(codebook)

    all_records, pending, prompts = [], [], {}
    for item in items:
        entries = pep._entries_for(item)
        blind_text, _ = tc.to_blind_text(entries)
        key = pep.cache_key(item["sha256"], "tier1", codebook_sha, prompt_sha,
                            pep.canonical_model_config(effective))
        excluded = pep._verify_no_excluded_content(item, blind_text)
        rec = {
            "custom_request_key": input_id_for(item),
            "input_id": input_id_for(item),
            "side": item["side"], "fg": item["fg"],
            "condition": item.get("condition", "human"),
            "canonical_replication_index": item.get("canonical_replication_index"),
            "physical_run": item.get("physical_run"),
            "path": item["path"], "window": item.get("window"),
            "transcript_sha256": item["sha256"],
            "blind_text_sha256": pep._sha_text(blind_text),
            "blind_text_words": len(blind_text.split()),
            "evaluator_prompt_sha256": prompt_sha,
            "codebook_sha256": codebook_sha,
            "effective_request_config": effective,
            "expected_cache_key": key,
            "excluded_content_problems": excluded,
            "already_complete_from_preflight": key in done,
        }
        all_records.append(rec)
        if key not in done:
            pending.append(rec)
            prompts[rec["custom_request_key"]] = stable_prefix + f"TRANSCRIPT:\n{blind_text}"

    manifest = {
        "created_utc": datetime.now(UTC).isoformat(),
        "purpose": "production Batch evaluation of the frozen corpus minus the preflight",
        "batch_request_id_local": "batch_corpus_16384_v1",
        "model": MODEL, "execution_mode": EXECUTION_MODE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "effective_request_config": effective,
        "canonical_model_config": pep.canonical_model_config(effective),
        "counts": {
            "frozen_total": len(items),
            "frozen_human": sum(1 for i in items if i["side"] == "human"),
            "frozen_synthetic": sum(1 for i in items if i["side"] == "synthetic"),
            "already_complete_from_preflight": len(done),
            "pending_total": len(pending),
            "pending_human": sum(1 for r in pending if r["side"] == "human"),
            "pending_synthetic": sum(1 for r in pending if r["side"] == "synthetic"),
            "derivation": ("pending = frozen inputs MINUS cache keys with "
                           "execution_mode=batch and completeness.status=COMPLETE"),
        },
        "preflight_complete_keys": sorted(done),
        "requests": pending,
        "final_set_all_35": [
            {k: r[k] for k in ("input_id", "side", "fg", "condition",
                               "canonical_replication_index", "physical_run",
                               "expected_cache_key", "already_complete_from_preflight")}
            for r in all_records],
    }
    validate(manifest, all_records)
    return manifest, prompts


def validate(m: dict, all_records: list[dict]) -> None:
    """Validates the FINAL set, not just this job."""
    problems: list[str] = []
    reqs = m["requests"]
    c = m["counts"]

    # --- this submission --------------------------------------------------
    if c["pending_total"] != 32:
        problems.append(f"pending total {c['pending_total']}, expected 32")
    if c["pending_human"] != 4:
        problems.append(f"pending human {c['pending_human']}, expected 4")
    if c["pending_synthetic"] != 28:
        problems.append(f"pending synthetic {c['pending_synthetic']}, expected 28")
    keys = [r["custom_request_key"] for r in reqs]
    if len(set(keys)) != len(keys):
        problems.append("custom request keys are not unique")
    ck = [r["expected_cache_key"] for r in reqs]
    if len(set(ck)) != len(ck):
        problems.append("expected cache keys collide within this job")
    if set(ck) & set(m["preflight_complete_keys"]):
        problems.append("a pending request reuses a completed preflight cache key")

    # --- the FINAL set: preflight + production ----------------------------
    if len(all_records) != EXPECTED_TOTAL:
        problems.append(f"final set {len(all_records)}, expected {EXPECTED_TOTAL}")
    humans = [r for r in all_records if r["side"] == "human"]
    synth = [r for r in all_records if r["side"] == "synthetic"]
    if len(humans) != EXPECTED_HUMAN:
        problems.append(f"final human {len(humans)}, expected {EXPECTED_HUMAN}")
    if len(synth) != EXPECTED_SYNTHETIC:
        problems.append(f"final synthetic {len(synth)}, expected {EXPECTED_SYNTHETIC}")
    if sorted(r["fg"] for r in humans) != sorted(FGS):
        problems.append(f"final human FGs {sorted(r['fg'] for r in humans)}")
    for cond in CONDITIONS:
        for fg in FGS:
            rows = [r for r in synth if r["condition"] == cond and r["fg"] == fg]
            if len(rows) != EXPECTED_REPLICATES:
                problems.append(f"{cond}/{fg}: {len(rows)} replicates, expected 3")
            idx = sorted(r["canonical_replication_index"] for r in rows)
            if idx != [1, 2, 3]:
                problems.append(f"{cond}/{fg}: replication indices {idx}")

    runs = {r["physical_run"] for r in synth}
    for archived in ARCHIVED_EXCLUDED:
        if archived in runs:
            problems.append(f"ARCHIVED run present in the corpus: {archived}")
    for fg, expected in (("fg4", FG4_ENRICHED_EXPECTED), ("fg5", FG5_ENRICHED_EXPECTED)):
        got = sorted(r["physical_run"] for r in synth
                     if r["fg"] == fg and r["condition"] == "enriched")
        if got != sorted(expected):
            problems.append(f"{fg} enriched runs {got}, expected {sorted(expected)}")

    # --- per-request integrity -------------------------------------------
    frozen = pep.load_inputs()
    frozen_by_path = {i["path"]: i for i in
                      frozen["human_inputs"] + frozen["synthetic_inputs"]}
    for r in all_records:
        rid = r["input_id"]
        if r["path"] not in frozen_by_path:
            problems.append(f"{rid}: path not in frozen inputs")
        elif frozen_by_path[r["path"]]["sha256"] != r["transcript_sha256"]:
            problems.append(f"{rid}: transcript hash differs from frozen")
        norm = r["path"].replace("\\", "/")
        if "output/session_logs" in norm:
            problems.append(f"{rid}: points at output/session_logs")
        if r["side"] == "synthetic":
            if "comparable_transcript.json" not in norm:
                problems.append(f"{rid}: not a comparable_transcript.json window")
            if r["window"] != "q1_ask_to_end_of_last_substantive_section":
                problems.append(f"{rid}: window {r['window']!r}")
        if r["excluded_content_problems"]:
            problems.append(f"{rid}: excluded-content {r['excluded_content_problems']}")
        eff = r["effective_request_config"]
        if eff["execution_mode"] != "batch":
            problems.append(f"{rid}: execution_mode {eff['execution_mode']}")
        if eff["model"] != MODEL:
            problems.append(f"{rid}: model {eff['model']}")
        if eff["max_output_tokens"] != MAX_OUTPUT_TOKENS:
            problems.append(f"{rid}: max_output_tokens {eff['max_output_tokens']}")
        if eff["response_mime_type"] != "application/json":
            problems.append(f"{rid}: response_mime_type {eff['response_mime_type']}")
        if eff["temperature_transmitted"] or eff["thinking_config_transmitted"]:
            problems.append(f"{rid}: temperature/thinking must not be transmitted")

    # batch keys must differ from every synchronous configuration
    sync_eff = pep.effective_request_config(
        dict(EVALUATOR_CONFIGS[pep.EVALUATOR_KEY], max_output_tokens=MAX_OUTPUT_TOKENS),
        "synchronous")
    sync_cfg = pep.canonical_model_config(sync_eff)
    for r in all_records:
        sync_key = pep.cache_key(r["transcript_sha256"], "tier1", r["codebook_sha256"],
                                 r["evaluator_prompt_sha256"], sync_cfg)
        if sync_key == r["expected_cache_key"]:
            problems.append(f"{r['input_id']}: batch key equals its synchronous key")

    if problems:
        raise ManifestError("MANIFEST VALIDATION FAILED — no job will be created:\n  - "
                            + "\n  - ".join(problems))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    from preflight_retry_controlled import load_env
    load_env()

    if args.status:
        rec = json.loads(_JOB.read_text(encoding="utf-8"))
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
        job = client.batches.get(name=rec["job_name"])
        rec["state"] = str(getattr(job, "state", None))
        rec["last_polled_utc"] = datetime.now(UTC).isoformat()
        _JOB.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"job   : {rec['job_name']}\nstate : {rec['state']}")
        return 0

    manifest, prompts = build()
    _MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    c = manifest["counts"]
    print("=" * 78)
    print("  PRODUCTION BATCH MANIFEST — validated")
    print("=" * 78)
    print(f"\nfrozen corpus            : {c['frozen_total']} "
          f"({c['frozen_human']} human + {c['frozen_synthetic']} synthetic)")
    print(f"already complete (batch) : {c['already_complete_from_preflight']}")
    print(f"pending this job         : {c['pending_total']} "
          f"({c['pending_human']} human + {c['pending_synthetic']} synthetic)")
    print(f"\neffective: {manifest['canonical_model_config']}\n")
    for r in manifest["requests"]:
        print(f"  {r['custom_request_key']:<34} {r['condition']:<18} "
              f"rep={r['canonical_replication_index'] or '-'}  "
              f"{r['blind_text_words']:>6}w  key {r['expected_cache_key'][:12]}...")
    print(f"\nmanifest: {_MANIFEST.relative_to(_REPO_ROOT)}")
    if not args.submit:
        print("\nnot submitted (pass --submit).")
        return 0

    if _JOB.exists():
        raise ManifestError(
            f"A corpus batch job already exists: "
            f"{json.loads(_JOB.read_text(encoding='utf-8')).get('job_name')!r}. "
            f"Creation is NOT idempotent — refusing to create another.")

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    cfg = types.GenerateContentConfig(
        system_instruction=tc._TIER1_SYSTEM,
        response_mime_type="application/json",
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    inline = [{"model": MODEL,
               "contents": [{"parts": [{"text": prompts[r["custom_request_key"]]}],
                             "role": "user"}],
               "config": cfg,
               "metadata": {"custom_request_key": r["custom_request_key"]}}
              for r in manifest["requests"]]
    print(f"\nsubmitting ONE job with {len(inline)} requests ...")
    job = client.batches.create(model=MODEL, src=inline,
                                config={"display_name": manifest["batch_request_id_local"]})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "display_name": getattr(job, "display_name", None),
           "state": str(getattr(job, "state", None)),
           "model": MODEL, "execution_mode": EXECUTION_MODE,
           "n_requests": len(inline),
           "custom_request_keys": [r["custom_request_key"] for r in manifest["requests"]],
           "manifest": str(_MANIFEST.relative_to(_REPO_ROOT)),
           "warning": "creation is NOT idempotent — never create a second job to retry"}
    _JOB.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"job name saved immediately: {rec['job_name']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManifestError as exc:
        print(f"REFUSED: {exc}")
        raise SystemExit(2)
