"""
C_ASSIGNMENT_STABILITY — two blind reassignments against the frozen Stage-B taxonomy.

    py scripts/stage_c_stability.py --submit
    py scripts/stage_c_stability.py --status
    py scripts/stage_c_stability.py --retrieve
    py scripts/stage_c_stability.py --score

Ten Gemini Batch calls: five questions x two separately keyed repetitions. Each call
receives the FROZEN taxonomy for its question and the same opaque themes, and assigns
each theme independently. Stage B's own assignment is a third, separate observation.

Stability is measured, not imposed. No lexical similarity, no embedding and no nearest
neighbour is used to decide any assignment; they are not used at all in this module.
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

_C = _ROOT / "analysis/production_evaluation/inductive_stage_c"
_B = sb._B
STAGE = "C_ASSIGNMENT_STABILITY"
UNCERTAIN = "UNCERTAIN"

_JOB = _C / "stage_c_batch_job.json"
_RAW = _C / "stage_c_raw_responses.json"
_MANIFEST = _C / "stage_c_manifest.json"

SYSTEM_PROMPT = """\
You are given a fixed taxonomy of clusters and a list of themes. Assign each theme to \
exactly one cluster.

Rules:
  * Use ONLY the cluster_ids given to you. Never invent a cluster, never rename one, \
never merge or split them. The taxonomy is fixed.
  * Assign a theme by whether it makes the SAME SUBSTANTIVE CLAIM as the cluster's \
definition, not by shared vocabulary. Two themes about the same topic belong to \
different clusters if they differ in mechanism, agent, stance or consequence.
  * Every raw_theme_id you are given must appear exactly once in your assignments.
  * If a theme genuinely does not resolve to one cluster, assign it the literal value \
UNCERTAIN. This is a legitimate answer and is preferred to forcing a poor fit.
  * Never drop a theme and never invent an identifier.
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["assignments"],
    "properties": {
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["raw_theme_id", "cluster_id"],
                "properties": {"raw_theme_id": {"type": "string"},
                               "cluster_id": {"type": "string"}},
            },
        },
    },
}


def render(question: int, tax: dict, themes: list) -> str:
    lines = ["FIXED TAXONOMY", ""]
    for c in tax["clusters"]:
        lines.append(f"cluster_id: {c['cluster_id']}")
        lines.append(f"  label     : {c['label']}")
        lines.append(f"  definition: {c['definition']}")
        lines.append("")
    lines += ["-" * 60, "", f"THEMES TO ASSIGN ({len(themes)} in total)", ""]
    for t in themes:
        lines.append(f"raw_theme_id: {t['raw_theme_id']}")
        lines.append(f"  label      : {t['label']}")
        lines.append(f"  description: {t['description']}")
        lines.append("")
    return "\n".join(lines)


def build_manifest() -> tuple[dict, dict]:
    taxes = json.loads((_B / "stage_b_canonical_taxonomies.json").read_text(
        encoding="utf-8"))["taxonomies"]
    by_q = sb.load_themes()
    prompt_sha = sb._sha(SYSTEM_PROMPT)
    schema_sha = sb._sha(json.dumps(RESPONSE_SCHEMA, sort_keys=True))

    reqs, bodies, problems = [], {}, []
    for q in sb.QUESTIONS:
        tax = taxes[str(q)]
        if not tax.get("frozen"):
            problems.append(f"Q{q}: taxonomy is not frozen")
        themes = by_q[q]
        body = render(q, tax, themes)
        bodies[q] = body
        if leaks := pa._hits(body, sb.BLIND_TOKENS):
            problems.append(f"Q{q}: blinding leak {leaks}")
        for rep in (1, 2):
            reqs.append({
                "custom_request_key": f"sc::q{q}::r{rep}",
                "question": q, "repetition_index": rep,
                "n_themes": len(themes),
                "expected_raw_theme_ids": [t["raw_theme_id"] for t in themes],
                "valid_cluster_ids": [c["cluster_id"] for c in tax["clusters"]],
                "taxonomy_sha256": tax["taxonomy_sha256"],
                "rendered_sha256": sb._sha(body),
                "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
                "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
                "cache_key": sb._sha("|".join([
                    STAGE, str(q), str(rep), tax["taxonomy_sha256"], sb._sha(body),
                    prompt_sha, schema_sha, sb.MODEL, sb.EXECUTION_MODE])),
            })
    keys = [r["custom_request_key"] for r in reqs]
    if len(reqs) != 10 or len(set(keys)) != 10:
        problems.append(f"{len(reqs)} requests / {len(set(keys))} unique keys")
    if sum(r["n_themes"] for r in reqs) != 526 * 2:
        problems.append("theme total does not reconcile to 526 per repetition")

    return {"built_utc": datetime.now(UTC).isoformat(), "stage": STAGE,
            "n_requests": len(reqs), "repetitions": 2,
            "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
            "similarity_used_for_decisions": False,
            "embeddings_used": False, "nearest_neighbour_used": False,
            "requests": reqs, "problems": problems, "pass": not problems}, bodies


def submit() -> dict:
    man, bodies = build_manifest()
    if not man["pass"]:
        raise sb.StageBError("preflight failed: " + "; ".join(man["problems"]))
    if _JOB.exists():
        raise sb.StageBError("stage C job exists; creation is NOT idempotent")
    sb._atomic(_MANIFEST, man)
    pa._load_env()
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
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
                                config={"display_name": "stage_c_stability_v1"})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "state_at_creation": str(getattr(job, "state", None)),
           "stage": STAGE, "n_requests": len(inline),
           "custom_request_keys": [r["custom_request_key"] for r in man["requests"]]}
    sb._atomic(_JOB, rec)
    print("job:", rec["job_name"])
    return rec


def status() -> str:
    rec = json.loads(_JOB.read_text(encoding="utf-8"))
    pa._load_env()
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY_NEXT"])
    st = str(getattr(client.batches.get(name=rec["job_name"]), "state", None))
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
    missing = sorted(set(rec["custom_request_keys"]) - set(out))
    if missing:
        raise sb.StageBError(f"missing: {missing}")
    payload = {"retrieved_utc": datetime.now(UTC).isoformat(),
               "job_name": rec["job_name"], "final_observed_state": st,
               "matched_by": "custom_request_key", "n_results": len(out),
               "measured_usage": {"input_tokens": uin, "output_tokens": uout},
               "responses": [out[k] for k in sorted(out)]}
    sb._atomic(_RAW, payload)
    print(f"retrieved {len(out)}")
    return payload


STABLE, UNSTABLE, UNRESOLVED = "STABLE", "UNSTABLE", "UNRESOLVED"


def score() -> dict:
    man = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(_RAW.read_text(encoding="utf-8"))
    b = json.loads((_B / "stage_b_canonical_taxonomies.json").read_text(
        encoding="utf-8"))
    b_asg = {}
    for row in csv.DictReader((_B / "stage_b_assignments_long.csv").open(
            encoding="utf-8")):
        b_asg[(int(row["question"]), row["raw_theme_id"])] = row["cluster_id"]

    by_key = {r["custom_request_key"]: r for r in man["requests"]}
    reps, quarantine = defaultdict(dict), []
    for resp in raw["responses"]:
        req = by_key[resp["custom_request_key"]]
        q, rep = req["question"], req["repetition_index"]
        problems = []
        if "STOP" not in (resp["finish_reason"] or "").upper():
            problems.append(f"finish_reason {resp['finish_reason']}")
        try:
            j = json.loads(resp["raw_text"] or "")
        except Exception as e:                                   # noqa: BLE001
            quarantine.append({"question": q, "rep": rep, "problems": [str(e)]})
            continue
        asg = j.get("assignments") or []
        expected = set(req["expected_raw_theme_ids"])
        got = [a.get("raw_theme_id") for a in asg]
        if [i for i, n in Counter(got).items() if n > 1]:
            problems.append("duplicated raw_theme_id")
        if set(got) - expected:
            problems.append("unknown raw_theme_id")
        if expected - set(got):
            problems.append(f"{len(expected - set(got))} omitted raw_theme_id")
        valid = set(req["valid_cluster_ids"]) | {UNCERTAIN}
        if [a for a in asg if a.get("cluster_id") not in valid]:
            problems.append("assignment to a non-existent cluster")
        if problems:
            quarantine.append({"question": q, "rep": rep, "problems": problems})
            continue
        for a in asg:
            reps[(q, a["raw_theme_id"])][rep] = a["cluster_id"]

    rows = []
    for (q, rid), r in sorted(reps.items()):
        c1, c2 = r.get(1), r.get(2)
        b0 = b_asg.get((q, rid))
        votes = [x for x in (b0, c1, c2) if x is not None]
        n_unc = sum(1 for x in votes if x == UNCERTAIN)
        if c1 is None or c2 is None:
            status = UNRESOLVED
        elif c1 == c2 == UNCERTAIN:
            status = UNRESOLVED
        elif c1 == c2:
            status = STABLE
        else:
            status = UNSTABLE
        rows.append({"question": q, "raw_theme_id": rid,
                     "stage_b_cluster": b0, "rep1_cluster": c1, "rep2_cluster": c2,
                     "status": status,
                     "agrees_with_stage_b": bool(c1 == c2 == b0),
                     "n_uncertain_votes": n_unc,
                     "modal_cluster": Counter(
                         [x for x in votes if x != UNCERTAIN]).most_common(1)[0][0]
                     if any(x != UNCERTAIN for x in votes) else UNCERTAIN})

    per_q = defaultdict(Counter)
    for r in rows:
        per_q[r["question"]][r["status"]] += 1
    counts = Counter(r["status"] for r in rows)
    return {"scored_utc": datetime.now(UTC).isoformat(), "stage": STAGE,
            "n_themes": len(rows), "status_counts": dict(counts),
            "per_question": {str(q): dict(v) for q, v in sorted(per_q.items())},
            "stability_rate": round(counts[STABLE] / len(rows), 4) if rows else None,
            "n_quarantined_calls": len(quarantine), "quarantine": quarantine,
            "measured_usage": raw["measured_usage"],
            "similarity_used_for_decisions": False,
            "rows": rows}


def main() -> int:
    a = sys.argv[1:]
    if "--submit" in a:
        submit()
    elif "--status" in a:
        status()
    elif "--retrieve" in a:
        retrieve()
    elif "--score" in a:
        s = score()
        sb._atomic(_C / "stage_c_stability.json",
                   {k: v for k, v in s.items() if k != "rows"})
        with (_C / "stage_c_stability_long.csv").open("w", encoding="utf-8",
                                                      newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(s["rows"][0]))
            w.writeheader()
            w.writerows(s["rows"])
        print(f"temas {s['n_themes']}  {s['status_counts']}  "
              f"estabilidad {s['stability_rate']}")
        for q, v in s["per_question"].items():
            print(f"  Q{q}: {v}")
        print(f"  llamadas en cuarentena: {s['n_quarantined_calls']}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
