"""
LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION — curves, corrected unit of analysis.

    py scripts/inductive_curves_v2.py

THE DEFECT THIS CORRECTS
------------------------
The first curve module accumulated with `by_fg[fg].add(cluster)`, pooling replicates R1,
R2 and R3 into one set per focus group. A synthetic curve therefore drew on FIFTEEN
sessions while the human curve drew on FIVE, and the endpoints were not comparable
quantities at all. The aggregate endpoints human=31, enriched=65, demographics-only=63
are RETIRED_SUPERSEDED and must not be cited.

THE CORRECT UNIT
----------------
  human               ONE realisation, FG1-FG5
  enriched            THREE independent realisations: R1, R2, R3
  demographics-only   THREE independent realisations: R1, R2, R3

Every synthetic curve uses exactly five focus groups drawn from a SINGLE replication
index (four for Q4). Themes from different replicates are never unioned before an
endpoint is computed.

TWO LEVELS OF AVERAGING, NEVER COLLAPSED
----------------------------------------
Within a replicate, the mean is taken over its own orderings. Across replicates, the
median and the full range are reported. The 360 orderings of a synthetic condition are
NOT treated as 360 independent observations; they are 3 realisations x 120 orderings.

No API calls. Stages B-F are not modified.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, UTC
from itertools import permutations
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import stage_b_taxonomy as sb            # noqa: E402
import inductive_curves as v1            # noqa: E402

_PE = _ROOT / "analysis/production_evaluation"
_D = _PE / "inductive_stage_d"
_OUT = _PE / "inductive_curves"

ANALYSIS = "LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION"
UNCERTAIN = "UNCERTAIN"
Q4_FGS = ("fg1", "fg2", "fg3", "fg4")
ALL_FGS = ("fg1", "fg2", "fg3", "fg4", "fg5")
SYNTHETIC = ("enriched", "demographics-only")
REPLICATES = ("1", "2", "3")

RETIRED = {"record": "RETIRED_SUPERSEDED",
           "superseded_endpoints": {"human": 31, "enriched": 65,
                                    "demographics-only": 63},
           "reason": ("replicates were pooled before accumulation, so each synthetic "
                      "curve drew on 15 sessions against the human curve's 5"),
           "must_not_be_cited": True}


def realisation_curve(assign, prov, question, condition, replicate):
    """
    One realisation: five focus groups at a single replication index (four for Q4).
    """
    fgs = Q4_FGS if question == 4 else ALL_FGS
    by_fg, n_unassigned = {}, 0
    for (q, rid), cl in assign.items():
        if q != question:
            continue
        p = prov.get((q, rid))
        if p is None or p["condition"] != condition or p["fg"] not in fgs:
            continue
        if condition != "human" and str(p["replicate"]) != str(replicate):
            continue
        if cl is None:
            n_unassigned += 1
            continue
        by_fg.setdefault(p["fg"], set()).add(cl)

    n_sessions = len(by_fg)
    orders = list(permutations(fgs))
    curves = []
    for order in orders:
        seen, row = set(), []
        for fg in order:
            seen |= by_fg.get(fg, set())
            row.append(len(seen))
        curves.append(row)
    mean = [round(statistics.mean(c[i] for c in curves), 3) for i in range(len(fgs))]
    return {"question": question, "condition": condition,
            "replicate": None if condition == "human" else replicate,
            "n_focus_groups_in_curve": len(fgs),
            "n_sessions_contributing": n_sessions,
            "n_orderings": len(orders),
            "mean_cumulative_by_position": mean,
            "mean_new_at_position": [round(mean[0], 3)] + [
                round(mean[i] - mean[i - 1], 3) for i in range(1, len(fgs))],
            "endpoint": len(set().union(*by_fg.values())) if by_fg else 0,
            "per_fg_repertoire": {fg: len(by_fg.get(fg, set())) for fg in fgs},
            "n_themes_unassigned_in_this_scenario": n_unassigned}


def condition_summary(realisations):
    """Across replicates: median and full range. Never a mean of pooled orderings."""
    eps = [r["endpoint"] for r in realisations]
    n_pos = realisations[0]["n_focus_groups_in_curve"]
    per_pos = []
    for i in range(n_pos):
        vals = [r["mean_cumulative_by_position"][i] for r in realisations]
        per_pos.append({"position": i + 1,
                        "replicate_means": vals,
                        "median": round(statistics.median(vals), 3),
                        "min": round(min(vals), 3), "max": round(max(vals), 3)})
    out = {"n_realisations": len(realisations),
           "endpoints": eps,
           "mean_endpoint": round(statistics.mean(eps), 3),
           "median_endpoint": round(statistics.median(eps), 3),
           "min_endpoint": min(eps), "max_endpoint": max(eps),
           "endpoint_range": max(eps) - min(eps),
           "cumulative_by_position": per_pos,
           "averaging_rule": ("mean within a replicate over its own orderings, then "
                              "median and range across replicates")}
    if len(realisations) == 1:
        out["endpoint_R1"] = eps[0]
        out["single_realisation"] = True
        out["no_between_replicate_variation"] = (
            "one human realisation exists; no SD or replicate variation is invented")
    else:
        for i, r in enumerate(realisations, start=1):
            out[f"endpoint_R{i}"] = r["endpoint"]
    return out


def unresolved_by_replicate(prov):
    dd = list(csv.DictReader((_D / "stage_d_decisions_long.csv").open(
        encoding="utf-8")))
    un = [r for r in dd if r["resolution"] == "CROSS_MODEL_UNRESOLVED"]
    rows = []
    for r in un:
        q = int(r["question"])
        p = prov[(q, r["raw_theme_id"])]
        rows.append({"question": q, "condition": p["condition"], "fg": p["fg"],
                     "replicate": p["replicate"] or "human",
                     "in_q4_curve_universe": (q != 4) or (p["fg"] in Q4_FGS)})
    by = defaultdict(int)
    for r in rows:
        by[(r["condition"], str(r["replicate"]), r["question"])] += 1
    q4_all = sum(1 for r in rows if r["question"] == 4)
    q4_in = sum(1 for r in rows if r["question"] == 4 and r["in_q4_curve_universe"])
    return {"n_total": len(rows),
            "by_condition_replicate_question": {
                f"{c}|R{rp}|Q{q}": n for (c, rp, q), n in sorted(by.items())},
            "q4_note": {
                "unresolved_in_full_universe": q4_all,
                "unresolved_inside_FG1_FG4_curve_universe": q4_in,
                "outside_curve": q4_all - q4_in,
                "why": ("Q4 curves use FG1-FG4 only; synthetic FG5 Q4 units are "
                        "extracted but stay outside the curve because no paired human "
                        "FG5 Q4 exists")},
            "rows": rows}


def build():
    prov = v1.provenance()
    canon = v1.canonical_assignments()
    canon.pop("_counts")
    bal = v1.balanced_assignments()
    scenarios = {**canon, **bal}

    out, flat = {}, []
    for name, assign in scenarios.items():
        per_q = {}
        for q in sb.QUESTIONS:
            block = {}
            hr = realisation_curve(assign, prov, q, "human", None)
            block["human"] = {"realisations": [hr], **condition_summary([hr])}
            flat.append({"scenario": name, "question": q, "condition": "human",
                         "replicate": "human", "endpoint": hr["endpoint"],
                         "n_sessions": hr["n_sessions_contributing"],
                         "n_orderings": hr["n_orderings"]})
            for cond in SYNTHETIC:
                rs = [realisation_curve(assign, prov, q, cond, rp)
                      for rp in REPLICATES]
                block[cond] = {"realisations": rs, **condition_summary(rs)}
                for rp, r in zip(REPLICATES, rs):
                    flat.append({"scenario": name, "question": q, "condition": cond,
                                 "replicate": f"R{rp}", "endpoint": r["endpoint"],
                                 "n_sessions": r["n_sessions_contributing"],
                                 "n_orderings": r["n_orderings"]})
            per_q[str(q)] = block
        out[name] = per_q

    # sums are only meaningful inside one realisation, and only as a sum of endpoints
    sums = {}
    for name in scenarios:
        s = {}
        for cond in ("human",) + SYNTHETIC:
            reps = ["human"] if cond == "human" else REPLICATES
            vals = []
            for rp in reps:
                tot = sum(out[name][str(q)][cond]["realisations"][
                    0 if cond == "human" else REPLICATES.index(rp)]["endpoint"]
                    for q in sb.QUESTIONS)
                vals.append(tot)
            s[cond] = {"per_realisation": vals,
                       "median": round(statistics.median(vals), 3),
                       "min": min(vals), "max": max(vals)}
        sums[name] = s

    return {"built_utc": datetime.now(UTC).isoformat(), "analysis": ANALYSIS,
            "unit_of_analysis": {
                "human": "one realisation, FG1-FG5",
                "enriched": "three independent realisations R1, R2, R3",
                "demographics-only": "three independent realisations R1, R2, R3",
                "replicates_never_pooled_before_accumulation": True},
            "supersedes": RETIRED,
            "orderings": {"Q1_Q2_Q3_Q5": 120, "Q4": 24,
                          "Q4_focus_groups": list(Q4_FGS),
                          "orderings_are_not_independent_observations": True},
            "scenarios_are_not_confidence_intervals": True,
            "maximum_is_a_construction_ceiling_not_an_estimate": True,
            "canonical_and_balanced_ids_never_mixed": True,
            "sum_label": "sum of question-specific repertoire endpoints",
            "sum_is_not": ("the number of distinct themes in the study; cluster ids "
                           "belong to a different taxonomy for each question"),
            "sums_within_realisation": sums,
            "unresolved": unresolved_by_replicate(prov),
            "curves": out, "_flat": flat}


def main() -> int:
    b = build()
    flat = b.pop("_flat")
    _OUT.mkdir(parents=True, exist_ok=True)
    sb._atomic(_OUT / "inductive_accumulation_curves_v2.json",
               {k: v for k, v in b.items() if k != "curves"})
    sb._atomic(_OUT / "inductive_curves_v2_full.json", b["curves"])
    with (_OUT / "inductive_endpoints_by_replicate.csv").open(
            "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(flat[0]))
        w.writeheader()
        w.writerows(flat)

    # retire the superseded file rather than deleting it
    old = _OUT / "inductive_accumulation_curves.json"
    if old.exists():
        j = json.loads(old.read_text(encoding="utf-8"))
        j["status"] = "RETIRED_SUPERSEDED"
        j["superseded_by"] = "inductive_accumulation_curves_v2.json"
        j["reason"] = RETIRED["reason"]
        sb._atomic(old, j)

    print(f"=== {ANALYSIS} — unidad corregida ===")
    print(f"  {RETIRED['record']}: endpoints anteriores "
          f"{RETIRED['superseded_endpoints']} no deben citarse\n")
    for name in b["curves"]:
        print(f"  {name}")
        for cond in ("human",) + SYNTHETIC:
            eps = []
            for q in sb.QUESTIONS:
                s = b["curves"][name][str(q)][cond]
                eps.append(s["endpoints"])
            if cond == "human":
                print(f"    human            endpoints por Q "
                      f"{[e[0] for e in eps]}  suma {sum(e[0] for e in eps)}")
            else:
                tot = b["sums_within_realisation"][name][cond]
                print(f"    {cond:17s} endpoints por Q "
                      f"{[e for e in eps]}")
                print(f"    {'':17s} suma por réplica {tot['per_realisation']}  "
                      f"mediana {tot['median']}  rango {tot['min']}-{tot['max']}")
        print()
    u = b["unresolved"]
    print(f"  no resueltos {u['n_total']}   Q4: {u['q4_note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
