"""
F1 / F2 — extractor stability control on the 45 frozen units.

    py scripts/stage_f_control.py --f1-preflight
    py scripts/stage_f_control.py --f1-submit
    py scripts/stage_f_control.py --f1-status
    py scripts/stage_f_control.py --f1-retrieve
    py scripts/stage_f_control.py --f1-validate
    py scripts/stage_f_control.py --f2-preflight
    ... same for f2

F1 re-extracts the 45 sampled units with the frozen Phase A prompt. F2 assigns the
themes of that second extraction directly against the frozen canonical taxonomies.

GEMINI DOES BOTH. Claude does not participate in Stage F; its only role in this pipeline
is the Stage D cross-model adjudication.

NEW_CLUSTER in F2 is a SIGNAL OF INSTABILITY, not an instruction. It never modifies the
canonical taxonomy, which stays frozen at its Stage B hash.

No decision anywhere in Stage F is made by nearest neighbour or lexical similarity.
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
import stage_c_stability as sc       # noqa: E402
import stage_e_balanced as e1m       # noqa: E402
import inductive_budget as bud       # noqa: E402

_F = _ROOT / "analysis/production_evaluation/inductive_stage_f"
NEW_CLUSTER = "NEW_CLUSTER"
UNCERTAIN = "UNCERTAIN"

F1_JOB, F1_RAW, F1_MANIFEST = (_F / "f1_batch_job.json", _F / "f1_raw_responses.json",
                               _F / "f1_manifest.json")
F2_JOB, F2_RAW, F2_MANIFEST = (_F / "f2_batch_job.json", _F / "f2_raw_responses.json",
                               _F / "f2_manifest.json")

F2_SYSTEM_PROMPT = """\
You are given a fixed taxonomy of clusters and a list of themes. Assign each theme to \
exactly one cluster.

Rules:
  * Use ONLY the cluster_ids given to you. The taxonomy is fixed and may not be \
extended, renamed, merged or split.
  * Assign by whether the theme makes the SAME SUBSTANTIVE CLAIM as the cluster's \
definition, not by shared vocabulary. Themes about the same topic belong to different \
clusters when they differ in mechanism, agent, stance or consequence.
  * If a theme expresses a claim that NO cluster covers, return the literal value \
NEW_CLUSTER.
  * If it could belong to more than one existing cluster and you cannot resolve it, \
return the literal value UNCERTAIN.
  * Every raw_theme_id must appear exactly once. Never drop a theme and never invent an \
identifier.
"""


def frozen_sample() -> dict:
    """The 45 units the budget froze: question x condition x length tercile."""
    plan = bud.plan()
    cells = plan["stage_f_cells"]["cells"]
    if len(cells) != 45:
        raise sb.StageBError(f"{len(cells)} cells, expected 45")
    return {"n_cells": len(cells), "cells": cells}


def build_f1_manifest():
    sample = frozen_sample()
    seg = json.loads((_ROOT / "analysis/production_evaluation/final"
                      / "inductive_segments.json").read_text(encoding="utf-8"))
    by_uid = {s["unit_id"]: s for s in seg["segments"]}
    prompt_sha = sb._sha(pa.SYSTEM_PROMPT)
    schema_sha = sb._sha(json.dumps(pa.RESPONSE_SCHEMA, sort_keys=True))

    reqs, bodies, problems = [], {}, []
    cover = defaultdict(set)
    for c in sample["cells"]:
        uid = c["unit_id"]
        s = by_uid.get(uid)
        if s is None:
            problems.append(f"{uid}: not in the frozen segmentation")
            continue
        r = pa.render_unit(s)
        if not r["reconciles"]:
            problems.append(f"{uid}: rendering does not reconcile")
        bodies[uid] = r["body"]
        cover[(s["question"], s["condition"])].add(s["length_tercile"])
        reqs.append({
            "custom_request_key": f"f1::{uid}",
            "unit_id": uid, "question": s["question"],
            "condition": s["condition"], "length_tercile": s["length_tercile"],
            "segment_text_sha256": s["section_sha256"],
            "rendered_sha256": sb._sha(r["body"]),
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
            "cache_key": sb._sha("|".join(["F1_REEXTRACTION", uid,
                                           s["section_sha256"], sb._sha(r["body"]),
                                           prompt_sha, schema_sha, sb.MODEL,
                                           sb.EXECUTION_MODE])),
            "prompt_words": r["words"]})
    if len(reqs) != 45:
        problems.append(f"{len(reqs)} requests, expected 45")
    missing_cover = [k for k, v in cover.items() if len(v) != 3]
    if len(cover) != 15 or missing_cover:
        problems.append(f"coverage: {len(cover)}/15 question x condition cells, "
                        f"{len(missing_cover)} without all three terciles")
    return {"built_utc": datetime.now(UTC).isoformat(), "stage": "F1_REEXTRACTION",
            "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
            "claude_participates": False,
            "n_requests": len(reqs),
            "coverage_question_x_condition": len(cover),
            "coverage_all_three_terciles": len(cover) - len(missing_cover),
            "prompt_identical_to_phase_a": True,
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "requests": reqs, "problems": problems, "pass": not problems}, bodies


def _submit(man, bodies, key_field, system_prompt, schema, job_path, label):
    from google.genai import types
    client = e1m._client()
    cfg = types.GenerateContentConfig(
        system_instruction=system_prompt, response_mime_type="application/json",
        response_schema=schema, max_output_tokens=sb.MAX_OUTPUT_TOKENS)
    inline = [{"model": sb.MODEL,
               "contents": [{"parts": [{"text": bodies[r[key_field]]}], "role": "user"}],
               "config": cfg,
               "metadata": {"custom_request_key": r["custom_request_key"]}}
              for r in man["requests"]]
    job = client.batches.create(model=sb.MODEL, src=inline,
                                config={"display_name": label})
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "job_name": getattr(job, "name", None),
           "state_at_creation": str(getattr(job, "state", None)),
           "stage": man["stage"], "n_requests": len(inline),
           "custom_request_keys": [r["custom_request_key"] for r in man["requests"]]}
    sb._atomic(job_path, rec)
    print("job:", rec["job_name"])
    return rec


def _status(job_path):
    rec = json.loads(job_path.read_text(encoding="utf-8"))
    client = e1m._client()
    st = str(getattr(client.batches.get(name=rec["job_name"]), "state", None))
    print(rec["job_name"], st)
    return st


def _retrieve(job_path, raw_path):
    rec = json.loads(job_path.read_text(encoding="utf-8"))
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
    sb._atomic(raw_path, {"retrieved_utc": datetime.now(UTC).isoformat(),
                          "job_name": rec["job_name"], "final_observed_state": st,
                          "matched_by": "custom_request_key", "n_results": len(out),
                          "measured_usage": {"input_tokens": uin,
                                             "output_tokens": uout},
                          "responses": [out[k] for k in sorted(out)]})
    print(f"retrieved {len(out)}")


def f1_validate():
    """Second extraction, validated with the same evidence gate as Phase A."""
    man = json.loads(F1_MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(F1_RAW.read_text(encoding="utf-8"))
    seg = json.loads((_ROOT / "analysis/production_evaluation/final"
                      / "inductive_segments.json").read_text(encoding="utf-8"))
    by_uid = {s["unit_id"]: s for s in seg["segments"]}
    by_key = {r["custom_request_key"]: r for r in man["requests"]}

    units, quarantine, themes_out = [], [], []
    for resp in raw["responses"]:
        req = by_key[resp["custom_request_key"]]
        uid = req["unit_id"]
        turns = pa.render_unit(by_uid[uid])["turns"]
        problems = []
        if "STOP" not in (resp["finish_reason"] or "").upper():
            problems.append(f"finish_reason {resp['finish_reason']}")
        try:
            j = json.loads(resp["raw_text"] or "")
        except Exception as e:                                # noqa: BLE001
            quarantine.append({"unit_id": uid, "problems": [str(e)]})
            continue
        kept = []
        for i, t in enumerate(j.get("themes") or []):
            valid = []
            for q in t.get("quotes") or []:
                import phase_a_revalidation as rv
                c = rv.classify_quote(q, turns)
                if c["verdict"] == rv.Q_VALID:
                    valid.append(c)
            if valid:
                # OPAQUE. The unit_id carries condition, focus group and replicate, so
                # using it as the theme key would have walked provenance straight into
                # the F2 prompt. The real identity stays in the sealed mapping only.
                tid = "F1T_" + sb._sha(
                    f"stage_f1_key|{uid}|{t.get('theme_id') or i}")[:12].upper()
                kept.append({"f1_theme_key": tid, "label": t.get("label"),
                             "description": t.get("description"),
                             "n_valid_quotes": len(valid)})
        if problems:
            quarantine.append({"unit_id": uid, "problems": problems})
            continue
        themes_out.extend([{**t, "unit_id": uid, "question": req["question"],
                            "condition": req["condition"],
                            "length_tercile": req["length_tercile"]} for t in kept])
        units.append({"unit_id": uid, "question": req["question"],
                      "condition": req["condition"],
                      "length_tercile": req["length_tercile"],
                      "n_themes_f1": len(kept)})
    sealed = [{"f1_theme_key": t["f1_theme_key"], "unit_id": t["unit_id"],
               "question": t["question"], "condition": t["condition"],
               "length_tercile": t["length_tercile"]} for t in themes_out]
    sb._atomic(_F / "sealed" / "f1_sealed_theme_mapping.json",
               {"WARNING": "SEALED. Maps the opaque F1 theme key to its provenance.",
                "n_rows": len(sealed), "rows": sealed})
    return {"validated_utc": datetime.now(UTC).isoformat(), "stage": "F1_REEXTRACTION",
            "n_units": len(units), "n_themes": len(themes_out),
            "theme_keys_are_opaque": True,
            "quarantine": quarantine, "gate_pass": len(units) == 45 and not quarantine,
            "units": units, "themes": themes_out,
            "measured_usage": raw["measured_usage"]}


def build_f2_manifest():
    f1 = json.loads((_F / "f1_extraction.json").read_text(encoding="utf-8"))
    taxes = json.loads((sb._B / "stage_b_canonical_taxonomies.json").read_text(
        encoding="utf-8"))["taxonomies"]
    prompt_sha = sb._sha(F2_SYSTEM_PROMPT)
    schema_sha = sb._sha(json.dumps(sb.RESPONSE_SCHEMA, sort_keys=True))
    by_q = defaultdict(list)
    for t in f1["themes"]:
        by_q[t["question"]].append(t)

    reqs, bodies, problems = [], {}, []
    for q in sb.QUESTIONS:
        themes = [{"raw_theme_id": t["f1_theme_key"], "label": t["label"],
                   "description": t["description"]} for t in by_q[q]]
        if not themes:
            continue
        tax = taxes[str(q)]
        recomputed = sb._sha(json.dumps({"clusters": tax["clusters"]},
                                        sort_keys=True, ensure_ascii=False))
        if recomputed != tax["taxonomy_sha256"]:
            problems.append(f"Q{q}: canonical taxonomy hash drifted")
        body = sc.render(q, tax, themes)
        bodies[q] = body
        if leaks := pa._hits(body, sb.BLIND_TOKENS):
            problems.append(f"Q{q}: blinding leak {leaks}")
        reqs.append({"custom_request_key": f"f2::q{q}", "question": q,
                     "n_themes": len(themes),
                     "expected_raw_theme_ids": [t["raw_theme_id"] for t in themes],
                     "valid_cluster_ids": [c["cluster_id"] for c in tax["clusters"]],
                     "canonical_taxonomy_sha256": tax["taxonomy_sha256"],
                     "rendered_sha256": sb._sha(body),
                     "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
                     "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
                     "cache_key": sb._sha("|".join(["F2_DIRECT_ASSIGNMENT", str(q),
                                                    tax["taxonomy_sha256"],
                                                    sb._sha(body), prompt_sha,
                                                    schema_sha, sb.MODEL,
                                                    sb.EXECUTION_MODE])),
                     "prompt_words": len(body.split())})
    return {"built_utc": datetime.now(UTC).isoformat(), "stage": "F2_DIRECT_ASSIGNMENT",
            "model": sb.MODEL, "execution_mode": sb.EXECUTION_MODE,
            "claude_participates": False,
            "canonical_taxonomy_modifiable": False,
            "new_cluster_is_an_instability_signal": True,
            "n_requests": len(reqs),
            "n_themes": sum(r["n_themes"] for r in reqs),
            "prompt_sha256": prompt_sha, "schema_sha256": schema_sha,
            "requests": reqs, "problems": problems, "pass": not problems}, bodies


def f2_validate():
    man = json.loads(F2_MANIFEST.read_text(encoding="utf-8"))
    raw = json.loads(F2_RAW.read_text(encoding="utf-8"))
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
            rows.append({"question": q, "f1_theme_key": a["raw_theme_id"],
                         "cluster_id": a["cluster_id"],
                         "is_new_cluster": a["cluster_id"] == NEW_CLUSTER,
                         "is_uncertain": a["cluster_id"] == UNCERTAIN})
    n_new = sum(1 for r in rows if r["is_new_cluster"])
    return {"validated_utc": datetime.now(UTC).isoformat(),
            "stage": "F2_DIRECT_ASSIGNMENT",
            "gate_pass": not quarantine and len(rows) == man["n_themes"],
            "n_assigned": len(rows), "n_expected": man["n_themes"],
            "n_new_cluster": n_new,
            "new_cluster_rate": round(n_new / len(rows), 4) if rows else None,
            "n_uncertain": sum(1 for r in rows if r["is_uncertain"]),
            "canonical_taxonomy_modified": False,
            "new_cluster_interpretation": ("a signal of extractor instability; it does "
                                           "NOT modify the canonical taxonomy"),
            "per_question": {str(q): {
                "n": sum(1 for r in rows if r["question"] == q),
                "new_cluster": sum(1 for r in rows
                                   if r["question"] == q and r["is_new_cluster"])}
                for q in sb.QUESTIONS},
            "quarantine": quarantine,
            "measured_usage": raw["measured_usage"], "rows": rows}


def main() -> int:
    a = sys.argv[1:]
    if "--f1-preflight" in a:
        man, _ = build_f1_manifest()
        sb._atomic(F1_MANIFEST, man)
        print("=== F1 PREFLIGHT ===")
        print(f"  requests {man['n_requests']}  (45 unidades congeladas)")
        print(f"  cobertura pregunta x corpus: "
              f"{man['coverage_question_x_condition']}/15")
        print(f"  celdas con los tres terciles: "
              f"{man['coverage_all_three_terciles']}/15")
        print(f"  Claude participa: {man['claude_participates']}")
        print(f"\n  PASS: {man['pass']}")
        for p in man["problems"]:
            print("   PROBLEM:", p)
        return 0 if man["pass"] else 1
    if "--f1-submit" in a:
        man, bodies = build_f1_manifest()
        if not man["pass"]:
            raise sb.StageBError("; ".join(man["problems"]))
        sb._atomic(F1_MANIFEST, man)
        _submit(man, bodies, "unit_id", pa.SYSTEM_PROMPT, pa.RESPONSE_SCHEMA,
                F1_JOB, "stage_f1_reextraction_v1")
    elif "--f1-status" in a:
        _status(F1_JOB)
    elif "--f1-retrieve" in a:
        _retrieve(F1_JOB, F1_RAW)
    elif "--f1-validate" in a:
        v = f1_validate()
        sb._atomic(_F / "f1_extraction.json", v)
        print(f"F1 gate {v['gate_pass']}  unidades {v['n_units']}/45  "
              f"temas {v['n_themes']}  cuarentena {len(v['quarantine'])}")
    elif "--f2-preflight" in a:
        man, _ = build_f2_manifest()
        sb._atomic(F2_MANIFEST, man)
        print("=== F2 PREFLIGHT ===")
        print(f"  requests {man['n_requests']}  temas {man['n_themes']}")
        print(f"  taxonomía canónica modificable: "
              f"{man['canonical_taxonomy_modifiable']}")
        print(f"  NEW_CLUSTER = señal de inestabilidad: "
              f"{man['new_cluster_is_an_instability_signal']}")
        print(f"\n  PASS: {man['pass']}")
        for p in man["problems"]:
            print("   PROBLEM:", p)
        return 0 if man["pass"] else 1
    elif "--f2-submit" in a:
        man, bodies = build_f2_manifest()
        if not man["pass"]:
            raise sb.StageBError("; ".join(man["problems"]))
        sb._atomic(F2_MANIFEST, man)
        _submit(man, bodies, "question", F2_SYSTEM_PROMPT, sb.RESPONSE_SCHEMA,
                F2_JOB, "stage_f2_direct_assignment_v1")
    elif "--f2-status" in a:
        _status(F2_JOB)
    elif "--f2-retrieve" in a:
        _retrieve(F2_JOB, F2_RAW)
    elif "--f2-validate" in a:
        v = f2_validate()
        sb._atomic(_F / "f2_assignment.json",
                   {k: val for k, val in v.items() if k != "rows"})
        with (_F / "f2_assignments_long.csv").open("w", encoding="utf-8",
                                                   newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(v["rows"][0]))
            w.writeheader()
            w.writerows(v["rows"])
        print(f"F2 gate {v['gate_pass']}  asignados {v['n_assigned']}/{v['n_expected']}"
              f"  NEW_CLUSTER {v['n_new_cluster']} ({v['new_cluster_rate']})"
              f"  UNCERTAIN {v['n_uncertain']}")
        for q, x in v["per_question"].items():
            print(f"  Q{q}: {x}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
