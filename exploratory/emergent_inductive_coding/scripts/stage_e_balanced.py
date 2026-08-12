"""
E1 / E2 / E3 — corpus-composition sensitivity.

    py scripts/stage_e_balanced.py --e1-preflight
    py scripts/stage_e_balanced.py --e1-submit
    py scripts/stage_e_balanced.py --e1-status
    py scripts/stage_e_balanced.py --e1-retrieve
    py scripts/stage_e_balanced.py --e1-validate

WHY THIS EXISTS
---------------
The canonical Stage B taxonomy was induced from 442 synthetic themes against 84 human
ones. Clusters form around wording that recurs, and synthetic wording recurs over five
times more often. E1 induces an INDEPENDENT taxonomy from a condition-balanced subsample
so the canonical result can be read against one that is not exposed to that asymmetry.

E1 does NOT replace Stage B. The canonical taxonomy is never overwritten; the two are
reported side by side.

BALANCED SUBSAMPLE RULE, frozen here
------------------------------------
Per question: every human theme, plus an equal number drawn from each synthetic
condition by deterministic content hash. So each question contributes 3 x n_human
themes, one third from each corpus. The draw is reproducible from the hash alone and
uses no similarity, no embedding and no nearest neighbour.

E1 runs independently of Stage C: it depends only on the 526 Phase A themes.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_phase_a as pa      # noqa: E402
import stage_b_taxonomy as sb       # noqa: E402

_E = _ROOT / "analysis/production_evaluation/inductive_stage_e"
_SEALED = _E / "sealed"
SUBSAMPLE_SALT = "stage_e1_balanced_v1"
CONDITIONS = ("human", "enriched", "demographics-only")

E1_JOB = _E / "e1_batch_job.json"
E1_RAW = _E / "e1_raw_responses.json"
E1_MANIFEST = _E / "e1_manifest.json"


def balanced_subsample() -> dict:
    """
    Frozen, deterministic, reproducible from the content hash alone.

    Each condition contributes exactly n_human themes for that question. Where a
    synthetic condition holds more than n_human, the first n_human by content hash are
    taken; the hash is over the theme's own text, so the draw cannot depend on
    provenance order.
    """
    by_q = sb.load_themes()
    out, rows = {}, []
    for q in sb.QUESTIONS:
        pools = defaultdict(list)
        for t in by_q[q]:
            pools[t["_condition"]].append(t)
        n_h = len(pools["human"])
        chosen = []
        for cond in CONDITIONS:
            pool = sorted(pools[cond],
                          key=lambda t: sb._sha(f"{SUBSAMPLE_SALT}|{q}|{cond}|"
                                                f"{t['label']}|{t['description']}"))
            take = pool[:n_h]
            if len(take) != n_h:
                raise sb.StageBError(
                    f"Q{q} {cond}: only {len(take)} themes, need {n_h}")
            chosen.extend(take)
            for t in take:
                rows.append({"question": q, "condition": cond,
                             "raw_theme_id": t["raw_theme_id"]})
        # present in the same content-hash order used everywhere else
        chosen.sort(key=lambda t: sb._sha(f"{sb.ORDER_SALT}|{t['label']}|"
                                          f"{t['description']}|{t['raw_theme_id']}"))
        out[q] = {"n_per_condition": n_h, "n_total": len(chosen), "themes": chosen}
    return {"salt": SUBSAMPLE_SALT, "rule": (
        "every human theme for the question, plus an equal number from each synthetic "
        "condition drawn by deterministic content hash"),
        "per_question": {str(q): {"n_per_condition": v["n_per_condition"],
                                  "n_total": v["n_total"]} for q, v in out.items()},
        "n_total": sum(v["n_total"] for v in out.values()),
        "similarity_used": False, "embeddings_used": False,
        "selection_rows": rows, "_by_q": out}


SYSTEM_PROMPT = sb.SYSTEM_PROMPT
RESPONSE_SCHEMA = sb.RESPONSE_SCHEMA


def build_e1_manifest() -> tuple[dict, dict]:
    sub = balanced_subsample()
    prompt_sha = sb._sha(SYSTEM_PROMPT)
    schema_sha = sb._sha(json.dumps(RESPONSE_SCHEMA, sort_keys=True))
    all_ids = {t["raw_theme_id"] for q in sb.QUESTIONS
               for t in sub["_by_q"][q]["themes"]}

    reqs, bodies, problems = [], {}, []
    for q in sb.QUESTIONS:
        themes = sub["_by_q"][q]["themes"]
        body = sb.render(q, themes)
        bodies[q] = body

        # nothing outside the subsample may reach the prompt
        in_prompt = {ln.split("raw_theme_id: ")[1].strip()
                     for ln in body.splitlines() if ln.startswith("raw_theme_id: ")}
        expected = {t["raw_theme_id"] for t in themes}
        if in_prompt != expected:
            problems.append(f"Q{q}: prompt carries {len(in_prompt - expected)} themes "
                            f"outside the subsample and omits "
                            f"{len(expected - in_prompt)}")
        if leaks := pa._hits(body, sb.BLIND_TOKENS):
            problems.append(f"Q{q}: blinding leak {leaks}")
        counts = Counter(t["_condition"] for t in themes)
        if len(set(counts.values())) != 1:
            problems.append(f"Q{q}: subsample is not balanced: {dict(counts)}")

        reqs.append({
            "custom_request_key": f"e1::q{q}",
            "question": q, "n_themes": len(themes),
            "n_per_condition": sub["_by_q"][q]["n_per_condition"],
            "expected_raw_theme_ids": sorted(expected),
            "rendered_sha256": sb._sha(body),
            "subsample_sha256": sb._sha("|".join(sorted(expected))),
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
            "cache_key": sb._sha("|".join(["E1_BALANCED_TAXONOMY", str(q),
                                           sb._sha(body), prompt_sha, schema_sha,
                                           sb.MODEL, sb.EXECUTION_MODE])),
            "prompt_words": len(body.split()),
        })

    if len(reqs) != 5:
        problems.append(f"{len(reqs)} requests, expected 5")
    if len({r["custom_request_key"] for r in reqs}) != 5:
        problems.append("custom request keys are not unique")

    man = {"built_utc": datetime.now(UTC).isoformat(),
           "stage": "E1_BALANCED_SUBSAMPLE_TAXONOMY",
           "purpose": ("independent taxonomy from a condition-balanced subsample, so the "
                       "canonical taxonomy can be read against one not exposed to volume "
                       "dominance"),
           "does_not_overwrite_stage_b": True,
           "independent_of_stage_c": True,
           "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
           "n_requests": len(reqs),
           "subsample": {k: v for k, v in sub.items()
                         if k not in ("_by_q", "selection_rows")},
           "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
           "no_theme_outside_subsample_in_prompt": not any(
               "outside the subsample" in p for p in problems),
           "requests": reqs, "problems": problems, "pass": not problems}
    return man, bodies


def _client():
    pa._load_env()
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])


def e1_submit() -> dict:
    man, bodies = build_e1_manifest()
    if not man["pass"]:
        raise sb.StageBError("E1 preflight failed: " + "; ".join(man["problems"]))
    if E1_JOB.exists():
        raise sb.StageBError("E1 job exists; creation is NOT idempotent")
    sb._atomic(E1_MANIFEST, man)
    sub = balanced_subsample()
    sb._atomic(_SEALED / "e1_subsample_selection.json",
               {"WARNING": "SEALED. Maps subsample membership to condition.",
                "salt": SUBSAMPLE_SALT, "rows": sub["selection_rows"]})

    from google.genai import types
    client = _client()
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT, response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA, max_output_tokens=sb.MAX_OUTPUT_TOKENS)
    inline = [{"model": sb.MODEL,
               "contents": [{"parts": [{"text": bodies[r["question"]]}],
                             "role": "user"}],
               "config": cfg,
               "metadata": {"custom_request_key": r["custom_request_key"]}}
              for r in man["requests"]]
    job = client.batches.create(model=sb.MODEL, src=inline,
                                config={"display_name": "stage_e1_balanced_v1"})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "state_at_creation": str(getattr(job, "state", None)),
           "stage": "E1_BALANCED_SUBSAMPLE_TAXONOMY", "n_requests": len(inline),
           "custom_request_keys": [r["custom_request_key"] for r in man["requests"]]}
    sb._atomic(E1_JOB, rec)
    print("job:", rec["job_name"])
    return rec


def e1_status() -> str:
    rec = json.loads(E1_JOB.read_text(encoding="utf-8"))
    client = _client()
    st = str(getattr(client.batches.get(name=rec["job_name"]), "state", None))
    print(rec["job_name"], st)
    return st


def e1_retrieve() -> dict:
    rec = json.loads(E1_JOB.read_text(encoding="utf-8"))
    client = _client()
    job = client.batches.get(name=rec["job_name"])
    st = str(getattr(job, "state", ""))
    if "SUCCEEDED" not in st:
        raise sb.StageBError(f"state {st}")
    out, uin, uout = {}, 0, 0
    for item in (getattr(getattr(job, "dest", None), "inlined_responses", None) or []):
        meta = getattr(item, "metadata", None) or {}
        key = (meta.get("custom_request_key") if isinstance(meta, dict)
               else getattr(meta, "custom_request_key", None))
        if key is None:
            raise sb.StageBError("no custom_request_key on a response")
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
    if missing := sorted(set(rec["custom_request_keys"]) - set(out)):
        raise sb.StageBError(f"missing: {missing}")
    payload = {"retrieved_utc": datetime.now(UTC).isoformat(),
               "job_name": rec["job_name"], "final_observed_state": st,
               "matched_by": "custom_request_key", "n_results": len(out),
               "measured_usage": {"input_tokens": uin, "output_tokens": uout},
               "responses": [out[k] for k in sorted(out)]}
    sb._atomic(E1_RAW, payload)
    print(f"retrieved {len(out)}")
    return payload


def e1_validate() -> dict:
    man = json.loads(E1_MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(E1_RAW.read_text(encoding="utf-8"))
    by_key = {r["custom_request_key"]: r for r in man["requests"]}
    taxes, asg_rows, quarantine = {}, [], []
    for resp in raw["responses"]:
        req = by_key[resp["custom_request_key"]]
        q = req["question"]
        problems = []
        if "STOP" not in (resp["finish_reason"] or "").upper():
            problems.append(f"finish_reason {resp['finish_reason']}")
        try:
            j = json.loads(resp["raw_text"] or "")
        except Exception as e:                                   # noqa: BLE001
            quarantine.append({"question": q, "problems": [str(e)]})
            continue
        clusters = j.get("clusters") or []
        asg = j.get("assignments") or []
        cids = [c.get("cluster_id") for c in clusters]
        if len(cids) != len(set(cids)):
            problems.append("duplicate cluster ids")
        expected = set(req["expected_raw_theme_ids"])
        got = [a.get("raw_theme_id") for a in asg]
        if [i for i, n in Counter(got).items() if n > 1]:
            problems.append("duplicated raw_theme_id")
        if set(got) - expected:
            problems.append("unknown raw_theme_id")
        if expected - set(got):
            problems.append(f"{len(expected - set(got))} omitted raw_theme_id")
        if [a for a in asg if a.get("cluster_id") not in set(cids) | {"UNCERTAIN"}]:
            problems.append("assignment to a non-existent cluster")
        if problems:
            quarantine.append({"question": q, "problems": problems})
            continue
        taxes[str(q)] = {"question": q, "n_clusters": len(clusters),
                         "clusters": clusters, "n_assigned": len(asg),
                         "n_uncertain": sum(1 for a in asg
                                            if a["cluster_id"] == "UNCERTAIN"),
                         "taxonomy_sha256": sb._sha(json.dumps(
                             {"clusters": clusters}, sort_keys=True,
                             ensure_ascii=False)),
                         "frozen": True}
        for a in asg:
            asg_rows.append({"question": q, "raw_theme_id": a["raw_theme_id"],
                             "cluster_id": a["cluster_id"]})
    return {"validated_utc": datetime.now(UTC).isoformat(),
            "stage": "E1_BALANCED_SUBSAMPLE_TAXONOMY",
            "n_questions_passed": len(taxes),
            "n_questions_quarantined": len(quarantine),
            "taxonomies": taxes, "assignments": asg_rows,
            "quarantine": quarantine,
            "measured_usage": raw["measured_usage"],
            "stage_b_overwritten": False,
            "gemini_cost_status": "NOT_CALCULATED_RATE_NOT_VERIFIED"}


def main() -> int:
    a = sys.argv[1:]
    if "--e1-preflight" in a:
        man, _ = build_e1_manifest()
        sb._atomic(E1_MANIFEST, man)
        print("=== E1 PREFLIGHT ===")
        print(f"  requests {man['n_requests']}  subsample total "
              f"{man['subsample']['n_total']}")
        for q, v in man["subsample"]["per_question"].items():
            print(f"    Q{q}: {v['n_per_condition']} por condición x3 = {v['n_total']}")
        print(f"  ningún tema fuera del subsample en el prompt: "
              f"{man['no_theme_outside_subsample_in_prompt']}")
        print(f"  no sobrescribe Stage B: {man['does_not_overwrite_stage_b']}")
        print(f"\n  PASS: {man['pass']}")
        for p in man["problems"]:
            print("   PROBLEM:", p)
        return 0 if man["pass"] else 1
    if "--e1-submit" in a:
        e1_submit()
    elif "--e1-status" in a:
        e1_status()
    elif "--e1-retrieve" in a:
        e1_retrieve()
    elif "--e1-validate" in a:
        v = e1_validate()
        sb._atomic(_E / "e1_balanced_taxonomies.json",
                   {k: val for k, val in v.items() if k != "assignments"})
        if v["assignments"]:
            with (_E / "e1_assignments_long.csv").open("w", encoding="utf-8",
                                                       newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(v["assignments"][0]))
                w.writeheader()
                w.writerows(v["assignments"])
        print(f"E1 questions passed {v['n_questions_passed']}/5  "
              f"quarantined {v['n_questions_quarantined']}")
        for q in sorted(v["taxonomies"]):
            t = v["taxonomies"][q]
            print(f"  Q{q}: {t['n_clusters']:3d} clusters  {t['n_assigned']:3d} temas  "
                  f"{t['n_uncertain']:2d} uncertain  hash {t['taxonomy_sha256'][:12]}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
