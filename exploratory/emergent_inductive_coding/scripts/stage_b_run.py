"""
Stage B runner: preflight, submit, status, retrieve, validate.

    py scripts/stage_b_run.py --preflight
    py scripts/stage_b_run.py --submit
    py scripts/stage_b_run.py --status
    py scripts/stage_b_run.py --retrieve
    py scripts/stage_b_run.py --validate

Stage B only. C, D, E1, E2, E3, F1 and F2 are not run.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_phase_a as pa      # noqa: E402
import stage_b_taxonomy as sb       # noqa: E402

_B = sb._B
_SEALED = sb._SEALED
_MANIFEST = sb._MANIFEST
_JOB = sb._JOB
_RAW = sb._RAW

UNCERTAIN = "UNCERTAIN"


def submit() -> dict:
    man, bodies = sb.build_manifest()
    if not man["pass"]:
        raise sb.StageBError("preflight failed:\n  " + "\n  ".join(man["problems"]))
    if _JOB.exists():
        raise sb.StageBError("stage B job already exists; creation is NOT idempotent")
    sb._atomic(_MANIFEST, man)
    sb._atomic(_SEALED / "stage_b_sealed_raw_theme_mapping.json", sb.sealed_mapping())

    pa._load_env()
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    cfg = types.GenerateContentConfig(
        system_instruction=sb.SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=sb.RESPONSE_SCHEMA,
        max_output_tokens=sb.MAX_OUTPUT_TOKENS)
    inline = [{"model": sb.MODEL,
               "contents": [{"parts": [{"text": bodies[r["question"]]}],
                             "role": "user"}],
               "config": cfg,
               "metadata": {"custom_request_key": r["custom_request_key"]}}
              for r in man["requests"]]
    if len(inline) != 5:
        raise sb.StageBError(f"{len(inline)} requests, expected 5")

    print(f"submitting ONE batch job with {len(inline)} requests, model {sb.MODEL} ...")
    job = client.batches.create(
        model=sb.MODEL, src=inline,
        config={"display_name": "stage_b_canonical_taxonomy_v1"})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "state_at_creation": str(getattr(job, "state", None)),
           "stage": sb.STAGE, "model": sb.MODEL,
           "execution_mode": sb.EXECUTION_MODE,
           "n_requests": len(inline),
           "custom_request_keys": [r["custom_request_key"] for r in man["requests"]],
           "retrieval_rule": "by custom_request_key only, never by position"}
    sb._atomic(_JOB, rec)
    print("job:", rec["job_name"])
    return rec


def status() -> str:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    pa._load_env()
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    j = client.batches.get(name=rec["job_name"])
    st = str(getattr(j, "state", None))
    print(rec["job_name"], st)
    return st


def retrieve() -> dict:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    pa._load_env()
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    job = client.batches.get(name=rec["job_name"])
    st = str(getattr(job, "state", ""))
    if "SUCCEEDED" not in st:
        raise sb.StageBError(f"state {st}, not succeeded")

    out, uin, uout = {}, 0, 0
    for item in (getattr(getattr(job, "dest", None), "inlined_responses", None) or []):
        meta = getattr(item, "metadata", None) or {}
        key = (meta.get("custom_request_key") if isinstance(meta, dict)
               else getattr(meta, "custom_request_key", None))
        if key is None:
            raise sb.StageBError("a response carries no custom_request_key; "
                                 "positional matching is not permitted")
        if key in out:
            raise sb.StageBError(f"duplicate custom_request_key {key}")
        resp = getattr(item, "response", None)
        cands = getattr(resp, "candidates", None) or []
        um = getattr(resp, "usage_metadata", None)
        if um is not None:
            uin += getattr(um, "prompt_token_count", 0) or 0
            uout += getattr(um, "candidates_token_count", 0) or 0
        out[key] = {"custom_request_key": key,
                    "finish_reason": (str(getattr(cands[0], "finish_reason", ""))
                                      if cands else ""),
                    "raw_text": getattr(resp, "text", None)}
    missing = sorted(set(rec["custom_request_keys"]) - set(out))
    if missing:
        raise sb.StageBError(f"missing responses: {missing}")

    payload = {"retrieved_utc": datetime.now(UTC).isoformat(),
               "job_name": rec["job_name"], "final_observed_state": st,
               "stage": sb.STAGE, "matched_by": "custom_request_key",
               "n_results": len(out),
               "measured_usage": {"input_tokens": uin, "output_tokens": uout},
               "responses": [out[k] for k in sorted(out)]}
    sb._atomic(_RAW, payload)
    print(f"retrieved {len(out)} -> {_RAW.name}")
    return payload


def validate() -> dict:
    """Every gate condition, per question. An incomplete answer is quarantined whole."""
    man = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(_RAW.read_text(encoding="utf-8"))
    by_key = {r["custom_request_key"]: r for r in man["requests"]}

    taxonomies, assignments, quarantine = {}, [], []
    for resp in raw["responses"]:
        req = by_key[resp["custom_request_key"]]
        q = req["question"]
        problems = []
        if "STOP" not in (resp["finish_reason"] or "").upper():
            problems.append(f"finish_reason {resp['finish_reason']}")
        try:
            j = json.loads(resp["raw_text"] or "")
        except Exception as e:                                    # noqa: BLE001
            quarantine.append({"question": q, "problems": [f"invalid json: {e}"]})
            continue
        clusters = j.get("clusters") or []
        asg = j.get("assignments") or []
        if not clusters:
            problems.append("no clusters returned")
        if not asg:
            problems.append("no assignments returned")

        cids = [c.get("cluster_id") for c in clusters]
        if len(cids) != len(set(cids)):
            problems.append("duplicate cluster ids")
        for c in clusters:
            if not (c.get("cluster_id") and c.get("label") and c.get("definition")):
                problems.append("a cluster is missing id, label or definition")
                break

        expected = set(req["expected_raw_theme_ids"])
        got = [a.get("raw_theme_id") for a in asg]
        dupes = [i for i, n in Counter(got).items() if n > 1]
        unknown = sorted(set(got) - expected)
        omitted = sorted(expected - set(got))
        if dupes:
            problems.append(f"{len(dupes)} duplicated raw_theme_id")
        if unknown:
            problems.append(f"{len(unknown)} unknown raw_theme_id")
        if omitted:
            problems.append(f"{len(omitted)} omitted raw_theme_id")

        valid = set(cids) | {UNCERTAIN}
        bad = [a for a in asg if a.get("cluster_id") not in valid]
        if bad:
            problems.append(f"{len(bad)} assignments to a non-existent cluster")

        if problems:
            quarantine.append({"question": q, "problems": problems,
                               "note": "an incomplete response is never completed "
                                       "by hand"})
            continue

        taxonomies[str(q)] = {
            "question": q, "n_clusters": len(clusters), "clusters": clusters,
            "n_assigned": len(asg),
            "n_uncertain": sum(1 for a in asg if a["cluster_id"] == UNCERTAIN),
            "n_raw_themes_expected": len(expected),
            "taxonomy_sha256": sb._sha(json.dumps({"clusters": clusters},
                                                  sort_keys=True, ensure_ascii=False)),
            "frozen": True}
        for a in asg:
            assignments.append({"question": q, "raw_theme_id": a["raw_theme_id"],
                                "cluster_id": a["cluster_id"],
                                "is_uncertain": a["cluster_id"] == UNCERTAIN})

    return {"validated_utc": datetime.now(UTC).isoformat(), "stage": sb.STAGE,
            "n_questions_passed": len(taxonomies),
            "n_questions_quarantined": len(quarantine),
            "taxonomies": taxonomies, "assignments": assignments,
            "quarantine": quarantine,
            "measured_usage": raw["measured_usage"],
            "gemini_cost_status": "NOT_CALCULATED_RATE_NOT_VERIFIED"}


def main() -> int:
    a = sys.argv[1:]
    if "--preflight" in a:
        man, _ = sb.build_manifest()
        sb._atomic(_MANIFEST, man)
        sb._atomic(_SEALED / "stage_b_sealed_raw_theme_mapping.json",
                   sb.sealed_mapping())
        print("=== STAGE B PREFLIGHT ===")
        print(f"  requests {man['n_requests']}   themes {man['n_themes_total']}")
        print(f"  per question {man['per_question']}")
        print(f"  blinding leaks {len(man['blinding']['leaks'])} "
              f"(of {man['blinding']['theme_text_tokens_checked']} tokens checked)")
        print(f"  ordering seed {man['ordering']['seed']}, "
              f"grouped by condition first: "
              f"{not man['ordering']['never_grouped_by_condition_first']}")
        print(f"  corpus quantities shown to model: "
              f"{man['ordering']['corpus_quantities_shown_to_model']}")
        v = man["volume_dominance"]
        print(f"  volume dominance {v['synthetic_themes']} synthetic vs "
              f"{v['human_themes']} human ({v['ratio']}), acknowledged "
              f"{v['acknowledged']}, corrected here {v['corrected_in_stage_b']}")
        print(f"\n  PASS: {man['pass']}")
        for p in man["problems"]:
            print("   PROBLEM:", p)
        return 0 if man["pass"] else 1
    if "--submit" in a:
        submit()
        return 0
    if "--status" in a:
        status()
        return 0
    if "--retrieve" in a:
        retrieve()
        return 0
    if "--validate" in a:
        v = validate()
        sb._atomic(_B / "stage_b_canonical_taxonomies.json",
                   {k: v[k] for k in ("validated_utc", "stage", "n_questions_passed",
                                      "n_questions_quarantined", "taxonomies",
                                      "quarantine", "measured_usage",
                                      "gemini_cost_status")})
        if v["assignments"]:
            with (_B / "stage_b_assignments_long.csv").open(
                    "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(v["assignments"][0]))
                w.writeheader()
                w.writerows(v["assignments"])
        print(f"questions passed {v['n_questions_passed']}/5   "
              f"quarantined {v['n_questions_quarantined']}")
        for q in sorted(v["taxonomies"]):
            t = v["taxonomies"][q]
            print(f"  Q{q}: {t['n_clusters']:3d} clusters  {t['n_assigned']:3d} assigned"
                  f"  {t['n_uncertain']:2d} uncertain")
        for x in v["quarantine"]:
            print(f"  Q{x['question']} QUARANTINE: {x['problems']}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except sb.StageBError as e:
        print("REFUSED:", e)
        raise SystemExit(2)
