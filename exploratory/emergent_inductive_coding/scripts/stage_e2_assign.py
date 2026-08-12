"""
E2_BALANCED_ASSIGNMENT — reassign all 526 themes against the frozen E1 taxonomies.

    py scripts/stage_e2_assign.py --preflight
    py scripts/stage_e2_assign.py --submit
    py scripts/stage_e2_assign.py --status
    py scripts/stage_e2_assign.py --retrieve
    py scripts/stage_e2_assign.py --validate

The E1 balanced taxonomy is FIXED here and may not be modified or extended. A theme whose
claim no E1 cluster covers is returned as NEW_CLUSTER, which is a different answer from
UNCERTAIN: NEW_CLUSTER says the taxonomy is missing the claim, UNCERTAIN says the theme
cannot be resolved between clusters that already exist. Both pass through to E3 rather
than being silently absorbed.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_phase_a as pa       # noqa: E402
import stage_b_taxonomy as sb        # noqa: E402
import stage_c_stability as sc       # noqa: E402
import stage_e_balanced as e1        # noqa: E402

_E = e1._E
NEW_CLUSTER = "NEW_CLUSTER"
UNCERTAIN = "UNCERTAIN"

JOB = _E / "e2_batch_job.json"
RAW = _E / "e2_raw_responses.json"
MANIFEST = _E / "e2_manifest.json"

SYSTEM_PROMPT = """\
You are given a fixed taxonomy of clusters and a list of themes. Assign each theme to \
exactly one cluster.

Rules:
  * Use ONLY the cluster_ids given to you. Never invent, rename, merge or split a \
cluster. The taxonomy is fixed and may not be extended.
  * Assign by whether the theme makes the SAME SUBSTANTIVE CLAIM as the cluster's \
definition, not by shared vocabulary. Themes about the same topic belong to different \
clusters when they differ in mechanism, agent, stance or consequence.
  * If a theme expresses a claim that NO cluster in this taxonomy covers, return the \
literal value NEW_CLUSTER. Do not force it into the nearest cluster.
  * If a theme could belong to more than one existing cluster and you cannot resolve \
it, return the literal value UNCERTAIN.
  * NEW_CLUSTER and UNCERTAIN are different answers. NEW_CLUSTER means the taxonomy is \
missing this claim. UNCERTAIN means you cannot decide between clusters that do exist.
  * Every raw_theme_id you are given must appear exactly once. Never drop a theme and \
never invent an identifier.
"""

RESPONSE_SCHEMA = sb.RESPONSE_SCHEMA


def build_manifest():
    e1f = json.loads((_E / "e1_balanced_taxonomies.json").read_text(encoding="utf-8"))
    taxes = e1f["taxonomies"]
    by_q = sb.load_themes()
    prompt_sha = sb._sha(SYSTEM_PROMPT)
    schema_sha = sb._sha(json.dumps(RESPONSE_SCHEMA, sort_keys=True))

    reqs, bodies, problems, total = [], {}, [], 0
    for q in sb.QUESTIONS:
        tax = taxes[str(q)]
        recomputed = sb._sha(json.dumps({"clusters": tax["clusters"]},
                                        sort_keys=True, ensure_ascii=False))
        if recomputed != tax["taxonomy_sha256"]:
            problems.append(f"Q{q}: E1 taxonomy hash drifted; it may not be modified")
        themes = by_q[q]
        total += len(themes)
        body = sc.render(q, tax, themes)
        bodies[q] = body
        if leaks := pa._hits(body, sb.BLIND_TOKENS):
            problems.append(f"Q{q}: blinding leak {leaks}")
        reqs.append({
            "custom_request_key": f"e2::q{q}", "question": q,
            "n_themes": len(themes),
            "expected_raw_theme_ids": [t["raw_theme_id"] for t in themes],
            "valid_cluster_ids": [c["cluster_id"] for c in tax["clusters"]],
            "e1_taxonomy_sha256": tax["taxonomy_sha256"],
            "rendered_sha256": sb._sha(body),
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
            "cache_key": sb._sha("|".join(["E2_BALANCED_ASSIGNMENT", str(q),
                                           tax["taxonomy_sha256"], sb._sha(body),
                                           prompt_sha, schema_sha, sb.MODEL,
                                           sb.EXECUTION_MODE])),
            "prompt_words": len(body.split())})
    if total != 526:
        problems.append(f"{total} themes, expected 526")
    if len(reqs) != 5:
        problems.append(f"{len(reqs)} requests, expected 5")
    return {"built_utc": datetime.now(UTC).isoformat(),
            "stage": "E2_BALANCED_ASSIGNMENT",
            "n_requests": len(reqs), "n_themes": total,
            "e1_taxonomy_may_be_extended": False,
            "new_cluster_and_uncertain_are_distinct": True,
            "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "requests": reqs, "problems": problems, "pass": not problems}, bodies


def submit():
    man, bodies = build_manifest()
    if not man["pass"]:
        raise sb.StageBError("E2 preflight failed: " + "; ".join(man["problems"]))
    if JOB.exists():
        raise sb.StageBError("E2 job exists; creation is NOT idempotent")
    sb._atomic(MANIFEST, man)
    from google.genai import types
    client = e1._client()
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
                                config={"display_name": "stage_e2_balanced_assign_v1"})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "state_at_creation": str(getattr(job, "state", None)),
           "stage": "E2_BALANCED_ASSIGNMENT", "n_requests": len(inline),
           "custom_request_keys": [r["custom_request_key"] for r in man["requests"]]}
    sb._atomic(JOB, rec)
    print("job:", rec["job_name"])


def status():
    rec = json.loads(JOB.read_text(encoding="utf-8"))
    client = e1._client()
    st = str(getattr(client.batches.get(name=rec["job_name"]), "state", None))
    print(rec["job_name"], st)
    return st


def retrieve():
    rec = json.loads(JOB.read_text(encoding="utf-8"))
    client = e1._client()
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
            raise sb.StageBError("no custom_request_key")
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
    sb._atomic(RAW, {"retrieved_utc": datetime.now(UTC).isoformat(),
                     "job_name": rec["job_name"], "final_observed_state": st,
                     "matched_by": "custom_request_key", "n_results": len(out),
                     "measured_usage": {"input_tokens": uin, "output_tokens": uout},
                     "responses": [out[k] for k in sorted(out)]})
    print(f"retrieved {len(out)}")


def validate():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    by_key = {r["custom_request_key"]: r for r in man["requests"]}
    rows, quarantine = [], []
    for resp in raw["responses"]:
        req = by_key[resp["custom_request_key"]]
        q = req["question"]
        problems = []
        if "STOP" not in (resp["finish_reason"] or "").upper():
            problems.append(f"finish_reason {resp['finish_reason']}")
        try:
            j = json.loads(resp["raw_text"] or "")
        except Exception as e:                                # noqa: BLE001
            quarantine.append({"question": q, "problems": [str(e)]})
            continue
        asg = j.get("assignments") or []
        expected = set(req["expected_raw_theme_ids"])
        got = [a.get("raw_theme_id") for a in asg]
        if dup := [i for i, n in Counter(got).items() if n > 1]:
            problems.append(f"{len(dup)} duplicated")
        if unk := sorted(set(got) - expected):
            problems.append(f"{len(unk)} unknown")
        if omi := sorted(expected - set(got)):
            problems.append(f"{len(omi)} omitted")
        valid = set(req["valid_cluster_ids"]) | {UNCERTAIN, NEW_CLUSTER}
        if bad := [a for a in asg if a.get("cluster_id") not in valid]:
            problems.append(f"{len(bad)} to a non-existent cluster")
        if problems:
            quarantine.append({"question": q, "problems": problems})
            continue
        for a in asg:
            rows.append({"question": q, "raw_theme_id": a["raw_theme_id"],
                         "cluster_id": a["cluster_id"],
                         "is_new_cluster": a["cluster_id"] == NEW_CLUSTER,
                         "is_uncertain": a["cluster_id"] == UNCERTAIN})
    gate = []
    if len(rows) != 526:
        gate.append(f"{len(rows)}/526 themes assigned")
    if len({(r["question"], r["raw_theme_id"]) for r in rows}) != len(rows):
        gate.append("duplicate theme assignments")
    if quarantine:
        gate.append(f"{len(quarantine)} quarantined questions")
    return {"validated_utc": datetime.now(UTC).isoformat(),
            "stage": "E2_BALANCED_ASSIGNMENT",
            "gate_pass": not gate, "gate_problems": gate,
            "n_assigned": len(rows),
            "n_new_cluster": sum(1 for r in rows if r["is_new_cluster"]),
            "n_uncertain": sum(1 for r in rows if r["is_uncertain"]),
            "per_question": {str(q): {
                "n": sum(1 for r in rows if r["question"] == q),
                "new_cluster": sum(1 for r in rows
                                   if r["question"] == q and r["is_new_cluster"]),
                "uncertain": sum(1 for r in rows
                                 if r["question"] == q and r["is_uncertain"])}
                for q in sb.QUESTIONS},
            "quarantine": quarantine,
            "measured_usage": raw["measured_usage"], "rows": rows}


def main() -> int:
    a = sys.argv[1:]
    if "--preflight" in a:
        man, _ = build_manifest()
        sb._atomic(MANIFEST, man)
        print("=== E2 PREFLIGHT ===")
        print(f"  requests {man['n_requests']}  themes {man['n_themes']}")
        print(f"  E1 extendable: {man['e1_taxonomy_may_be_extended']}")
        print(f"  NEW_CLUSTER != UNCERTAIN: "
              f"{man['new_cluster_and_uncertain_are_distinct']}")
        print(f"\n  PASS: {man['pass']}")
        for p in man["problems"]:
            print("   PROBLEM:", p)
        return 0 if man["pass"] else 1
    if "--submit" in a:
        submit()
    elif "--status" in a:
        status()
    elif "--retrieve" in a:
        retrieve()
    elif "--validate" in a:
        v = validate()
        sb._atomic(_E / "e2_assignment.json",
                   {k: val for k, val in v.items() if k != "rows"})
        if v["rows"]:
            with (_E / "e2_assignments_long.csv").open("w", encoding="utf-8",
                                                       newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(v["rows"][0]))
                w.writeheader()
                w.writerows(v["rows"])
        print(f"E2 gate {v['gate_pass']}  asignados {v['n_assigned']}/526  "
              f"NEW_CLUSTER {v['n_new_cluster']}  UNCERTAIN {v['n_uncertain']}")
        for q, x in v["per_question"].items():
            print(f"  Q{q}: {x}")
        if not v["gate_pass"]:
            print("  GATE PROBLEMS:", v["gate_problems"])
            return 2
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
