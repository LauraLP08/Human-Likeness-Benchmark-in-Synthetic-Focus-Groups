"""
Non-destructive migration of evaluator-cache entries to the corrected cache key.

The cache key previously omitted `max_output_tokens` and `response_mime_type`, both
of which ARE transmitted. Entries computed before the fix therefore sit under a key
that does not describe the call that produced them.

MIGRATION IS PROOF-GATED, NOT ASSUMED
An entry is re-keyed only when ALL of these are demonstrated:

  1. same input SHA-256                     (recorded in the artifact)
  2. same evaluator prompt SHA-256          (recorded in the artifact)
  3. same codebook SHA-256                  (recorded in the artifact)
  4. same model                             (recorded in the artifact)
  5. effective max_output_tokens = 32768    (the literal in thematic_coding.py, whose
                                             mtime PREDATES the call, so no other
                                             value can have been transmitted)
  6. no other effective parameter changed   (every field of the stored old-form
                                             config equals the new-form value)

If any of these cannot be shown, the entry is marked `legacy_unmigrated` and left to
be recomputed. Guessing would put a result under a key asserting a configuration
that was never verified — worse than recomputing.

THE ORIGINAL ARTIFACT IS NEVER DELETED OR OVERWRITTEN. It is copied to
`evaluator_cache_legacy/` and the migration is logged with both keys.

No API call.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import production_eval_pipeline as pep                      # noqa: E402
from thematic_coding import EVALUATOR_CONFIGS               # noqa: E402

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_CACHE = _OUT / "evaluator_cache"
_LEGACY = _OUT / "evaluator_cache_legacy"
_LOG = _OUT / "cache_key_migration_log.json"

EXPECTED_MAX_OUTPUT_TOKENS = 32768
_TC = _REPO_ROOT / "scripts" / "thematic_coding.py"


def source_predates(iso_utc: str) -> tuple[bool, str, str]:
    """Was thematic_coding.py last modified before this call was made?"""
    mt = _dt.datetime.fromtimestamp(_TC.stat().st_mtime, _dt.UTC)
    call = _dt.datetime.fromisoformat(iso_utc)
    return mt < call, mt.isoformat(), call.isoformat()


def evaluate(entry: dict, effective_now: dict) -> tuple[bool, list[str], list[str]]:
    """Returns (migratable, proofs, failures)."""
    proofs, failures = [], []
    stored = entry.get("effective_request_config") or {}
    inp = entry.get("input") or {}

    for label, got in (("input SHA-256", inp.get("sha256")),
                       ("evaluator prompt SHA-256", entry.get("evaluator_prompt_sha256")),
                       ("codebook SHA-256", entry.get("codebook_sha256"))):
        (proofs if got else failures).append(
            f"{label}: {got[:16] + '...' if got else 'ABSENT from the artifact'}")

    model = stored.get("model")
    if model == effective_now.get("model"):
        proofs.append(f"model: {model} (unchanged)")
    else:
        failures.append(f"model differs: stored {model!r} vs now {effective_now.get('model')!r}")

    ok, src_mt, call_ts = source_predates(entry["computed_utc"])
    if ok and effective_now.get("max_output_tokens") == EXPECTED_MAX_OUTPUT_TOKENS:
        proofs.append(
            f"max_output_tokens = {EXPECTED_MAX_OUTPUT_TOKENS}: thematic_coding.py "
            f"mtime {src_mt} predates the call {call_ts}, so no other value can have "
            f"been transmitted")
    else:
        failures.append(
            f"max_output_tokens NOT demonstrable (source mtime {src_mt} vs call "
            f"{call_ts}; current literal {effective_now.get('max_output_tokens')})")

    drift = [k for k, v in stored.items()
             if k in effective_now and effective_now[k] != v]
    if drift:
        failures.append(f"effective parameters changed: {drift}")
    else:
        proofs.append(f"all {len(stored)} stored effective fields equal today's values")

    return (not failures), proofs, failures


def main(apply: bool) -> int:
    # assert_evaluator ALREADY returns the effective config; calling
    # effective_request_config on its output applies the transform twice and silently
    # nulls the label fields.
    effective_now = pep.assert_evaluator(EVALUATOR_CONFIGS[pep.EVALUATOR_KEY])
    problems = pep.effective_config_coverage_problems(effective_now)
    if problems:
        print("REFUSING: the effective configuration is still incomplete:")
        for p in problems:
            print("   -", p)
        return 2

    entries = sorted(_CACHE.glob("*.json"))
    print("=" * 76)
    print(f"  CACHE KEY MIGRATION  ({'APPLY' if apply else 'DRY RUN'})")
    print("=" * 76)
    print(f"\ncorrected effective config: {pep.canonical_model_config(effective_now)}\n")

    log = {"migration_utc": _dt.datetime.now(_dt.UTC).isoformat(),
           "applied": apply,
           "corrected_effective_request_config": effective_now,
           "entries": []}
    migrated = legacy = 0

    for path in entries:
        entry = json.loads(path.read_text(encoding="utf-8"))
        old_key = entry["cache_key"]
        label = (entry["input"].get("physical_run")
                 or f"human_{entry['input'].get('fg')}")
        ok, proofs, failures = evaluate(entry, effective_now)
        new_key = pep.cache_key(entry["input"]["sha256"], "tier1",
                                entry["codebook_sha256"],
                                entry["evaluator_prompt_sha256"],
                                pep.canonical_model_config(effective_now))
        rec = {"label": label, "old_cache_key": old_key, "new_cache_key": new_key,
               "input_sha256": entry["input"]["sha256"],
               "codebook_sha256": entry["codebook_sha256"],
               "evaluator_prompt_sha256": entry["evaluator_prompt_sha256"],
               "computed_utc": entry["computed_utc"],
               "proofs": proofs, "failures": failures,
               "decision": "migrate" if ok else "legacy_unmigrated"}
        print(f"{label}")
        print(f"   old key : {old_key}")
        print(f"   new key : {new_key}")
        for p in proofs:
            print(f"   [proof] {p}")
        for f in failures:
            print(f"   [FAIL ] {f}")
        print(f"   decision: {rec['decision']}")

        if ok and apply:
            _LEGACY.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, _LEGACY / path.name)       # original preserved
            entry["effective_request_config"] = effective_now
            entry["cache_key"] = new_key
            entry["cache_key_migration"] = {
                "migrated_utc": _dt.datetime.now(_dt.UTC).isoformat(),
                "from_cache_key": old_key, "to_cache_key": new_key,
                "reason": ("original key omitted max_output_tokens and "
                           "response_mime_type, both transmitted"),
                "original_artifact": str((_LEGACY / path.name).relative_to(_REPO_ROOT)),
                "proofs": proofs,
                "recomputed": False,
                "note": ("Re-keyed only; the Tier-1 result is byte-identical to the "
                         "original and was NOT recomputed."),
            }
            (_CACHE / f"{new_key}.json").write_text(
                json.dumps(entry, indent=1, ensure_ascii=False), encoding="utf-8")
            if new_key != old_key:
                path.unlink()          # superseded copy; original is in _LEGACY
            migrated += 1
        elif ok:
            migrated += 1
        else:
            if apply:
                entry_path = path
                marker = entry_path.with_suffix(".legacy_unmigrated.json")
                marker.write_text(json.dumps(
                    {"cache_key": old_key, "reason": failures}, indent=1), encoding="utf-8")
            legacy += 1
        log["entries"].append(rec)

    log["migrated"] = migrated
    log["legacy_unmigrated"] = legacy
    if apply:
        _LOG.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nmigrated: {migrated}   legacy_unmigrated: {legacy}")
    if apply:
        print(f"log: {_LOG.relative_to(_REPO_ROOT)}")
        print(f"originals preserved in: {_LEGACY.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the migration; without it nothing is changed")
    raise SystemExit(main(ap.parse_args().apply))
