"""
E3 — consolidate the NEW_CLUSTER themes and build the balanced extended taxonomy.

    py scripts/stage_e3_consolidate.py --preflight
    py scripts/stage_e3_consolidate.py --submit
    py scripts/stage_e3_consolidate.py --status
    py scripts/stage_e3_consolidate.py --retrieve
    py scripts/stage_e3_consolidate.py --validate

WHY CONSOLIDATION IS A STEP AND NOT AN ASSUMPTION
-------------------------------------------------
E2 returned 195 themes that no E1 cluster covered. Treating each as its own cluster would
inflate the extended repertoire by construction: 195 NEW_CLUSTER answers do not mean 195
distinct claims, they mean 195 themes the balanced taxonomy had no home for. They are
consolidated among themselves, per question, before any extended count is reported.

WHAT IS PRESERVED
-----------------
E1 is not modified. The extended taxonomy carries `parent_taxonomy_sha256` pointing at
the E1 taxonomy it extends, so the strict-against-E1 and extended views stay separable.
The 6 UNCERTAIN themes are kept out of the main curves and reported separately.

This is BALANCED-CONSTRUCTION SENSITIVITY. E1 was induced from 252 themes and Stage B
from 526, so any difference in cluster count confounds corpus balance with sample size;
it is not an isolated estimate of the dominance effect.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_phase_a as pa       # noqa: E402
import stage_b_taxonomy as sb        # noqa: E402
import stage_e_balanced as e1m       # noqa: E402
import stage_e2_assign as e2m        # noqa: E402

_E = e1m._E
STAGE = "E3_NEW_CLUSTER_CONSOLIDATION"
NEW_CLUSTER = "NEW_CLUSTER"
UNCERTAIN = "UNCERTAIN"

JOB = _E / "e3_batch_job.json"
RAW = _E / "e3_raw_responses.json"
MANIFEST = _E / "e3_manifest.json"

SYSTEM_PROMPT = """\
You are given a list of themes that an existing taxonomy did not cover. Build a small \
set of additional clusters for them.

Rules:
  * Group themes that express THE SAME SUBSTANTIVE CLAIM. Do not merge themes merely \
because they share vocabulary.
  * Keep separate any themes that differ in mechanism, agent, stance or consequence.
  * Do NOT create one cluster per theme. If several themes make the same claim in \
different words, they belong together.
  * Do NOT create clusters so broad that they absorb unrelated claims.
  * Give each cluster a self-sufficient label and a one-or-two-sentence definition.
  * Assign every raw_theme_id exactly once, to one of your new clusters or to the \
literal value UNCERTAIN.
  * Never drop a theme and never invent an identifier.
"""

RESPONSE_SCHEMA = sb.RESPONSE_SCHEMA


def new_cluster_themes() -> dict:
    """question -> the NEW_CLUSTER themes from E2, with their text."""
    rows = list(csv.DictReader((_E / "e2_assignments_long.csv").open(encoding="utf-8")))
    wanted = {(int(r["question"]), r["raw_theme_id"]) for r in rows
              if r["cluster_id"] == NEW_CLUSTER}
    by_q = sb.load_themes()
    out = defaultdict(list)
    for q in sb.QUESTIONS:
        for t in by_q[q]:
            if (q, t["raw_theme_id"]) in wanted:
                out[q].append({"raw_theme_id": t["raw_theme_id"],
                               "label": t["label"], "description": t["description"]})
    got = sum(len(v) for v in out.values())
    if got != len(wanted):
        raise sb.StageBError(f"{got} resolved, expected {len(wanted)}")
    return dict(out)


def build_manifest():
    nc = new_cluster_themes()
    e1f = json.loads((_E / "e1_balanced_taxonomies.json").read_text(encoding="utf-8"))
    prompt_sha = sb._sha(SYSTEM_PROMPT)
    schema_sha = sb._sha(json.dumps(RESPONSE_SCHEMA, sort_keys=True))

    reqs, bodies, problems, total = [], {}, [], 0
    for q in sb.QUESTIONS:
        themes = nc.get(q, [])
        total += len(themes)
        if not themes:
            continue
        body = sb.render(q, themes)
        bodies[q] = body
        if leaks := pa._hits(body, sb.BLIND_TOKENS):
            problems.append(f"Q{q}: blinding leak {leaks}")
        reqs.append({
            "custom_request_key": f"e3::q{q}", "question": q,
            "n_themes": len(themes),
            "expected_raw_theme_ids": [t["raw_theme_id"] for t in themes],
            "parent_taxonomy_sha256": e1f["taxonomies"][str(q)]["taxonomy_sha256"],
            "rendered_sha256": sb._sha(body),
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
            "cache_key": sb._sha("|".join([STAGE, str(q), sb._sha(body), prompt_sha,
                                           schema_sha, sb.MODEL,
                                           sb.EXECUTION_MODE])),
            "prompt_words": len(body.split())})
    if total != 195:
        problems.append(f"{total} NEW_CLUSTER themes, expected 195")
    return {"built_utc": datetime.now(UTC).isoformat(), "stage": STAGE,
            "classification": "BALANCED_CONSTRUCTION_SENSITIVITY",
            "not_an_isolated_dominance_estimate": True,
            "e1_modified": False,
            "n_requests": len(reqs), "n_new_cluster_themes": total,
            "per_question": {str(q): len(v) for q, v in sorted(nc.items())},
            "one_cluster_per_theme_forbidden": True,
            "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "requests": reqs, "problems": problems, "pass": not problems}, bodies


def submit():
    man, bodies = build_manifest()
    if not man["pass"]:
        raise sb.StageBError("E3 preflight failed: " + "; ".join(man["problems"]))
    if JOB.exists():
        raise sb.StageBError("E3 job exists; creation is NOT idempotent")
    sb._atomic(MANIFEST, man)
    from google.genai import types
    client = e1m._client()
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
                                config={"display_name": "stage_e3_consolidate_v1"})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "state_at_creation": str(getattr(job, "state", None)),
           "stage": STAGE, "n_requests": len(inline),
           "custom_request_keys": [r["custom_request_key"] for r in man["requests"]]}
    sb._atomic(JOB, rec)
    print("job:", rec["job_name"])


def status():
    rec = json.loads(JOB.read_text(encoding="utf-8"))
    client = e1m._client()
    st = str(getattr(client.batches.get(name=rec["job_name"]), "state", None))
    print(rec["job_name"], st)
    return st


def retrieve():
    rec = json.loads(JOB.read_text(encoding="utf-8"))
    client = e1m._client()
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
    e1f = json.loads((_E / "e1_balanced_taxonomies.json").read_text(encoding="utf-8"))
    by_key = {r["custom_request_key"]: r for r in man["requests"]}

    extended, rows, quarantine = {}, [], []
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
        clusters = j.get("clusters") or []
        asg = j.get("assignments") or []
        cids = [c.get("cluster_id") for c in clusters]
        if len(cids) != len(set(cids)):
            problems.append("duplicate cluster ids")
        expected = set(req["expected_raw_theme_ids"])
        got = [a.get("raw_theme_id") for a in asg]
        if dup := [i for i, n in Counter(got).items() if n > 1]:
            problems.append(f"{len(dup)} duplicated")
        if unk := sorted(set(got) - expected):
            problems.append(f"{len(unk)} unknown")
        if omi := sorted(expected - set(got)):
            problems.append(f"{len(omi)} omitted")
        if [a for a in asg if a.get("cluster_id") not in set(cids) | {UNCERTAIN}]:
            problems.append("assignment to a non-existent cluster")
        if len(clusters) >= len(expected):
            problems.append(f"{len(clusters)} clusters for {len(expected)} themes; "
                            "one cluster per theme is not consolidation")
        if problems:
            quarantine.append({"question": q, "problems": problems})
            continue

        base = e1f["taxonomies"][str(q)]
        # the extended taxonomy is E1 plus the consolidated additions, prefixed so the
        # two origins never blur
        add = [{"cluster_id": f"N{c['cluster_id']}", "label": c["label"],
                "definition": c["definition"], "origin": "E3_CONSOLIDATED"}
               for c in clusters]
        base_clusters = [{**c, "origin": "E1_BALANCED"} for c in base["clusters"]]
        merged = base_clusters + add
        extended[str(q)] = {
            "question": q,
            "parent_taxonomy_sha256": base["taxonomy_sha256"],
            "n_e1_clusters": len(base_clusters),
            "n_consolidated_clusters": len(add),
            "n_extended_clusters": len(merged),
            "n_new_cluster_themes_consolidated": len(expected),
            "consolidation_ratio": round(len(expected) / len(add), 2) if add else None,
            "clusters": merged,
            "extended_taxonomy_sha256": sb._sha(json.dumps(
                {"clusters": merged}, sort_keys=True, ensure_ascii=False)),
            "frozen": True}
        for a in asg:
            rows.append({"question": q, "raw_theme_id": a["raw_theme_id"],
                         "extended_cluster_id": (f"N{a['cluster_id']}"
                                                 if a["cluster_id"] != UNCERTAIN
                                                 else UNCERTAIN),
                         "origin": "E3_CONSOLIDATED"})
    gate = []
    if len(extended) != len(man["requests"]):
        gate.append(f"{len(extended)}/{len(man['requests'])} questions consolidated")
    if len(rows) != man["n_new_cluster_themes"]:
        gate.append(f"{len(rows)}/{man['n_new_cluster_themes']} themes assigned")
    if quarantine:
        gate.append(f"{len(quarantine)} quarantined")
    return {"validated_utc": datetime.now(UTC).isoformat(), "stage": STAGE,
            "classification": "BALANCED_CONSTRUCTION_SENSITIVITY",
            "gate_pass": not gate, "gate_problems": gate,
            "e1_modified": False,
            "extended_taxonomies": extended,
            "n_consolidated_assignments": len(rows),
            "quarantine": quarantine,
            "measured_usage": raw["measured_usage"], "rows": rows}


def main() -> int:
    a = sys.argv[1:]
    if "--preflight" in a:
        man, _ = build_manifest()
        sb._atomic(MANIFEST, man)
        print("=== E3 PREFLIGHT ===")
        print(f"  requests {man['n_requests']}  NEW_CLUSTER themes "
              f"{man['n_new_cluster_themes']}  {man['per_question']}")
        print(f"  E1 modificada: {man['e1_modified']}")
        print(f"  un cluster por tema prohibido: "
              f"{man['one_cluster_per_theme_forbidden']}")
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
        sb._atomic(_E / "e3_extended_taxonomies.json",
                   {k: val for k, val in v.items() if k != "rows"})
        if v["rows"]:
            with (_E / "e3_consolidated_assignments.csv").open(
                    "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(v["rows"][0]))
                w.writeheader()
                w.writerows(v["rows"])
        print(f"E3 gate {v['gate_pass']}  asignaciones {v['n_consolidated_assignments']}")
        for q, t in sorted(v["extended_taxonomies"].items()):
            print(f"  Q{q}: E1 {t['n_e1_clusters']:2d} + consolidados "
                  f"{t['n_consolidated_clusters']:2d} = {t['n_extended_clusters']:2d}"
                  f"   ({t['n_new_cluster_themes_consolidated']} temas -> "
                  f"{t['n_consolidated_clusters']}, ratio {t['consolidation_ratio']})")
        if not v["gate_pass"]:
            print("  GATE PROBLEMS:", v["gate_problems"])
            return 2
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
