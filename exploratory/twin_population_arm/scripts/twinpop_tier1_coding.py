#!/usr/bin/env python3
"""
twinpop_tier1_coding.py — Tier-1 codebook coding of the 6 twinpop documents with
the frozen evaluator, submitted as one Batch job.

WHY THIS ISN'T A NEW EVALUATION
It is the SAME evaluation, extended to a fourth condition. Everything that decides
what the evaluator sees and how it answers is imported from the production modules
that coded the canonical 32 — `production_eval_pipeline` for the cache key, the
blind-text rendering and the config assertions, `thematic_coding` for the codebook,
the Tier-1 system prompt and the stable prefix. Nothing about the instrument is
re-declared here, because a re-declared instrument can drift from the one whose
numbers twinpop is about to be compared against.

THE EQUIVALENCE GATE
Before anything is submitted, the effective request configuration built for twinpop
is compared field-by-field with the one recorded in `batch_corpus_result.json` — the
actual config the canonical 32 were coded under, read off the returned job rather
than off a document that claims what it was. Any difference aborts. A twinpop recall
number produced under a different model, token ceiling or execution mode is not
comparable to the canonical numbers no matter how carefully the rest was done.

COST
Exactly one Tier-1 call per document — the discipline `thematic_coding` states and
the canonical corpus followed. 6 documents, 6 requests, one job.

Usage:
    py scripts/twinpop_tier1_coding.py                 # build + validate, no spend
    py scripts/twinpop_tier1_coding.py --submit        # submit the batch job
    py scripts/twinpop_tier1_coding.py --status        # poll
    py scripts/twinpop_tier1_coding.py --retrieve      # fetch + parse + verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import production_eval_pipeline as pep                        # noqa: E402
import thematic_coding as tc                                  # noqa: E402
from thematic_coding import EVALUATOR_CONFIGS, load_codebook  # noqa: E402

_OUT = _REPO_ROOT / "analysis" / "production_evaluation" / "twinpop"
_SEGMENTS = _OUT / "twinpop_segments.json"
_MANIFEST = _OUT / "twinpop_tier1_manifest.json"
_JOB = _OUT / "twinpop_tier1_job.json"
_RESULT = _OUT / "twinpop_tier1_result.json"
_CANONICAL_RESULT = (_REPO_ROOT / "analysis" / "production_evaluation"
                     / "batch_corpus_result.json")
_DERIVED = _REPO_ROOT / "analysis" / "production_evaluation" / "comparable_transcripts"

MODEL = "gemini-3.5-flash"
MAX_OUTPUT_TOKENS = 16384
EXECUTION_MODE = "batch"
CONDITION = "twinpop"
EXPECTED_REQUESTS = 6


class CodingError(RuntimeError):
    pass


def twinpop_items() -> list[dict]:
    """The 6 canonical-set documents, in the shape `frozen_evaluator_inputs.json`
    uses for the synthetic side. Read from the segmentation output so the archived
    run cannot leak in: whatever is in the corpus there is what gets coded."""
    seg = json.loads(_SEGMENTS.read_text(encoding="utf-8"))
    runs = {}
    for s in seg["segments"]:
        runs.setdefault(s["physical_run"], s)
    items = []
    for run, s in sorted(runs.items()):
        path = _DERIVED / run / "comparable_transcript.json"
        items.append({
            "side": "synthetic", "condition": CONDITION, "fg": s["fg"],
            "canonical_replication_index": s["canonical_replication_index"],
            "physical_run": run,
            "path": str(path.relative_to(_REPO_ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "window": "q1_ask_to_end_of_last_substantive_section",
            "boundary_algorithm": "anchor_and_extend_v1",
        })
    archived = {a["run"] for a in seg.get("archived_runs", [])}
    leaked = archived & {i["physical_run"] for i in items}
    if leaked:
        raise CodingError(f"archived run(s) reached the coding set: {sorted(leaked)}")
    return items


def canonical_effective_config() -> dict:
    """The config the canonical 32 were ACTUALLY coded under, read off the returned
    batch job — not off a document asserting what it should have been."""
    j = json.loads(_CANONICAL_RESULT.read_text(encoding="utf-8"))
    return j["effective_request_config"]


def equivalence_gate(effective: dict) -> tuple[bool, dict]:
    canon = canonical_effective_config()
    fields = sorted(set(canon) | set(effective))
    rows = [{"field": f, "canonical": canon.get(f), "twinpop": effective.get(f),
             "equal": canon.get(f) == effective.get(f)} for f in fields]
    return all(r["equal"] for r in rows), {
        "canonical_source": str(_CANONICAL_RESULT.relative_to(_REPO_ROOT)),
        "fields": rows,
        "equivalent": all(r["equal"] for r in rows),
    }


def build() -> tuple[dict, dict]:
    frozen = pep.load_inputs()
    codebook = load_codebook()
    codebook_sha = frozen["codebook"]["sha256"]
    prompt_sha = pep._sha_text(tc._TIER1_SYSTEM)
    ecfg = dict(EVALUATOR_CONFIGS[pep.EVALUATOR_KEY], max_output_tokens=MAX_OUTPUT_TOKENS)
    effective = pep.assert_evaluator(ecfg, EXECUTION_MODE)
    if pep.effective_config_coverage_problems(effective):
        raise CodingError("effective configuration incomplete")

    # The codebook and the Tier-1 prompt must be the frozen ones, byte for byte.
    if codebook_sha != frozen["codebook"]["sha256"]:
        raise CodingError("codebook hash drifted")
    if prompt_sha != frozen["evaluator_prompt_sha256"]["tier1"]:
        raise CodingError(
            f"Tier-1 prompt hash drifted: {prompt_sha[:12]} != "
            f"{frozen['evaluator_prompt_sha256']['tier1'][:12]}")

    items = twinpop_items()
    if len(items) != EXPECTED_REQUESTS:
        raise CodingError(f"{len(items)} documents, expected {EXPECTED_REQUESTS}")

    stable_prefix = tc._get_tier1_stable_prefix(codebook)
    records, prompts = [], {}
    for item in items:
        entries = pep._entries_for(item)
        blind_text, _ = tc.to_blind_text(entries)
        key = pep.cache_key(item["sha256"], "tier1", codebook_sha, prompt_sha,
                            pep.canonical_model_config(effective))
        key_label = f"{CONDITION}_{item['fg']}_r{item['canonical_replication_index']}"
        rec = {
            # `input_id` is what the production retriever copies onto the cache
            # entry; the canonical manifest carries both and so must this one, or
            # `preflight_batch_retrieve.py` cannot consume it.
            "custom_request_key": key_label, "input_id": key_label,
            "side": item["side"], "fg": item["fg"], "condition": CONDITION,
            "canonical_replication_index": item["canonical_replication_index"],
            "physical_run": item["physical_run"], "path": item["path"],
            "window": item["window"],
            "transcript_sha256": item["sha256"],
            "blind_text_sha256": pep._sha_text(blind_text),
            "blind_text_words": len(blind_text.split()),
            "evaluator_prompt_sha256": prompt_sha,
            "codebook_sha256": codebook_sha,
            "effective_request_config": effective,
            "expected_cache_key": key,
            "excluded_content_problems": pep._verify_no_excluded_content(item, blind_text),
        }
        records.append(rec)
        prompts[rec["custom_request_key"]] = stable_prefix + f"TRANSCRIPT:\n{blind_text}"

    eq_ok, eq = equivalence_gate(effective)
    problems = [p for r in records for p in r["excluded_content_problems"]]

    manifest = {
        "created_utc": datetime.now(UTC).isoformat(),
        "purpose": "Tier-1 coding of the twinpop arm with the frozen evaluator",
        "batch_request_id_local": "batch_twinpop_tier1_16384_v1",
        "model": MODEL, "execution_mode": EXECUTION_MODE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "effective_request_config": effective,
        "canonical_model_config": pep.canonical_model_config(effective),
        "equivalence_with_canonical_corpus": eq,
        "blinding_problems": problems,
        "counts": {"documents": len(records), "requests": len(records),
                   "calls_per_document": 1},
        "requests": records,
    }
    return manifest, prompts


_CACHE = _REPO_ROOT / "analysis" / "production_evaluation" / "evaluator_cache"
_JOB_RETRY = _OUT / "twinpop_tier1_job_retry.json"


def complete_keys() -> set[str]:
    """Cache keys with a COMPLETE entry. A quarantined entry is NOT a result."""
    done = set()
    for p in _CACHE.glob("*.json"):
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        if e.get("completeness", {}).get("status") == "COMPLETE":
            done.add(e.get("cache_key"))
    return done


def retry() -> int:
    """Resubmit only what has no COMPLETE cache entry, under the identical frozen
    configuration, following `batch_retry_single.py`'s protocol:

      * the quarantined attempt is left untouched — it is the evidence that the
        first attempt was malformed;
      * nothing is repaired by hand. The three FG3 responses carried a complete
        JSON object followed by a duplicated closing fragment. Stripping that tail
        in a lenient parser would put a researcher-edited object into the corpus
        under a cache key that claims it came from the evaluator, and would parse
        twinpop by a rule the canonical 32 were never parsed by;
      * the configuration is re-derived by `build()` from the same sources, not
        copied, so the retry cannot silently differ and the cache key is identical.
    """
    from preflight_retry_controlled import load_env
    load_env()
    manifest, prompts = build()
    done = complete_keys()
    pending = [r for r in manifest["requests"] if r["expected_cache_key"] not in done]

    print("REINTENTO TIER-1 TWINPOP\n")
    for r in manifest["requests"]:
        state = "COMPLETE (no se reintenta)" if r["expected_cache_key"] in done \
            else "SIN RESULTADO -> se reintenta"
        print(f"  {r['custom_request_key']:<20} {state}")
    if not pending:
        print("\nNada pendiente.")
        return 0
    if _JOB_RETRY.exists():
        raise CodingError(
            f"Ya existe un job de reintento: "
            f"{json.loads(_JOB_RETRY.read_text(encoding='utf-8')).get('job_name')!r}. "
            f"No se crea un segundo.")

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
              for r in pending]
    print(f"\nenviando {len(inline)} peticiones de reintento ...")
    job = client.batches.create(model=MODEL, src=inline,
                                config={"display_name": "retry_twinpop_tier1"})
    _JOB_RETRY.write_text(json.dumps({
        "created_utc": datetime.now(UTC).isoformat(),
        "job_name": getattr(job, "name", None),
        "state": str(getattr(job, "state", None)),
        "model": MODEL, "execution_mode": EXECUTION_MODE, "n_requests": len(inline),
        "custom_request_keys": [r["custom_request_key"] for r in pending],
        "retry_of": "quarantine/batch_twinpop_fg3_r*.json",
        "previous_attempt_preserved": True,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"job: {getattr(job, 'name', None)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--retrieve", action="store_true")
    ap.add_argument("--retry", action="store_true",
                    help="resubmit ONLY the requests without a COMPLETE cache entry")
    args = ap.parse_args()

    if args.retry:
        return retry()

    from preflight_retry_controlled import load_env
    load_env()

    if args.status or args.retrieve:
        rec = json.loads(_JOB.read_text(encoding="utf-8"))
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
        job = client.batches.get(name=rec["job_name"])
        state = str(getattr(job, "state", None))
        rec["state"] = state
        rec["last_polled_utc"] = datetime.now(UTC).isoformat()
        _JOB.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"job   : {rec['job_name']}\nstate : {state}")
        if args.retrieve and "SUCCEEDED" in state:
            _RESULT.write_text(json.dumps({
                "retrieved_utc": datetime.now(UTC).isoformat(),
                "job_name": rec["job_name"], "job_state": state,
                "execution_mode": EXECUTION_MODE,
                "raw": [str(r) for r in (job.dest.inlined_responses or [])],
            }, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"raw responses -> {_RESULT.relative_to(_REPO_ROOT)}")
        return 0

    manifest, prompts = build()
    _OUT.mkdir(parents=True, exist_ok=True)
    _MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    eq = manifest["equivalence_with_canonical_corpus"]
    print("=" * 78)
    print("  CODIFICACION TIER-1 DEL BRAZO TWINPOP")
    print("=" * 78)
    print("\nEQUIVALENCIA CON LA CONFIGURACION DE LOS 32 CANONICOS")
    for r in eq["fields"]:
        print(f"  {'OK  ' if r['equal'] else 'DIFIERE'} {r['field']:34s} "
              f"canonico={str(r['canonical'])[:22]:24s} twinpop={str(r['twinpop'])[:22]}")
    print(f"\n  -> {'EQUIVALENTE' if eq['equivalent'] else 'NO EQUIVALENTE'}")

    if manifest["blinding_problems"]:
        print(f"\nPROBLEMAS DE CEGADO: {manifest['blinding_problems']}")
        return 1

    print(f"\nDOCUMENTOS A CODIFICAR ({manifest['counts']['requests']} llamadas, "
          f"1 por documento):")
    for r in manifest["requests"]:
        print(f"  {r['custom_request_key']:<22} {r['physical_run']:<34} "
              f"{r['blind_text_words']:>6}p  key {r['expected_cache_key'][:12]}...")

    if not eq["equivalent"]:
        print("\nABORTA: la configuracion no coincide con la de los 32 canonicos.")
        return 1
    if not args.submit:
        print("\nNo enviado (pasa --submit).")
        return 0
    if _JOB.exists():
        raise CodingError(
            f"Ya existe un job twinpop: "
            f"{json.loads(_JOB.read_text(encoding='utf-8')).get('job_name')!r}. "
            f"La creacion NO es idempotente — no se crea un segundo.")

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
    print(f"\nenviando UN job con {len(inline)} peticiones ...")
    job = client.batches.create(model=MODEL, src=inline,
                                config={"display_name": manifest["batch_request_id_local"]})
    _JOB.write_text(json.dumps({
        "created_utc": datetime.now(UTC).isoformat(),
        "job_name": getattr(job, "name", None),
        "display_name": getattr(job, "display_name", None),
        "state": str(getattr(job, "state", None)),
        "model": MODEL, "execution_mode": EXECUTION_MODE, "n_requests": len(inline),
        "custom_request_keys": [r["custom_request_key"] for r in manifest["requests"]],
        "warning": "la creacion NO es idempotente — nunca crear un segundo job para reintentar",
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"job: {getattr(job, 'name', None)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
