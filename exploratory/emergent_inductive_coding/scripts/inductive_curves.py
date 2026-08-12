"""
LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION — curves and endpoints.

    py scripts/inductive_curves.py

Builds the canonical and balanced accumulation curves from the frozen stage outputs.
Offline; no API call.

FOUR CANONICAL SCENARIOS, NOT AN INTERVAL
-----------------------------------------
  CANONICAL_RESOLVED_LOWER          338 stable + 102 cross-model consensus = 440/526
  CANONICAL_ASSIGNMENT_SENSITIVITY_R1   the 440, plus the 86 unresolved taken at the
                                        concrete cluster Claude named in repetition 1
  CANONICAL_ASSIGNMENT_SENSITIVITY_R2   the same rule using repetition 2 only
  CANONICAL_MATHEMATICAL_MAXIMUM        every one of the 86 counted as its own category

These are ANALYTIC SENSITIVITY SCENARIOS. LOWER and MAXIMUM are not confidence bounds and
are never described as an interval. The maximum is a ceiling produced by construction,
not an estimate and not a headline result.

TWO BALANCED VIEWS, KEPT APART
------------------------------
  STRICT_AGAINST_E1   only themes an E1 cluster covers
  EXTENDED_E3         E1 plus the 33 consolidated clusters, covering 520 of 526

Canonical and balanced cluster ids are never mixed: the canonical ids come from Stage B,
the balanced ones from E1/E3, and a cluster id means nothing outside its own taxonomy.

ORDERINGS
---------
Q1, Q2, Q3, Q5 use all 120 orderings of the five focus groups. Q4 uses FG1-FG4 and all
24 orderings; synthetic FG5 Q4 units are extracted but stay outside the curve, because
there is no paired human FG5 Q4.
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

import stage_b_taxonomy as sb        # noqa: E402

_PE = _ROOT / "analysis/production_evaluation"
_B, _C = _PE / "inductive_stage_b", _PE / "inductive_stage_c"
_D, _E = _PE / "inductive_stage_d", _PE / "inductive_stage_e"
_OUT = _PE / "inductive_curves"

ANALYSIS = "LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION"
UNCERTAIN = "UNCERTAIN"
Q4_FGS = ("fg1", "fg2", "fg3", "fg4")
ALL_FGS = ("fg1", "fg2", "fg3", "fg4", "fg5")


def provenance() -> dict:
    """question -> raw_theme_id -> {condition, fg, replicate}."""
    sealed = json.loads((_B / "sealed" / "stage_b_sealed_raw_theme_mapping.json")
                        .read_text(encoding="utf-8"))
    out = {}
    for r in sealed["rows"]:
        out[(r["question"], r["raw_theme_id"])] = {
            "condition": r["condition"], "fg": r["fg"],
            "replicate": r["canonical_replication_index"]}
    return out


def canonical_assignments() -> dict:
    """The four scenarios, each mapping (question, raw_theme_id) -> cluster or None."""
    cst = list(csv.DictReader((_C / "stage_c_stability_long.csv").open(
        encoding="utf-8")))
    dd = list(csv.DictReader((_D / "stage_d_decisions_long.csv").open(
        encoding="utf-8")))
    d_by = {(int(r["question"]), r["raw_theme_id"]): r for r in dd}

    lower, r1, r2, mx = {}, {}, {}, {}
    n_stable = n_consensus = n_unres = 0
    for r in cst:
        q, rid = int(r["question"]), r["raw_theme_id"]
        key = (q, rid)
        if r["status"] == "STABLE_SAME_AS_STAGE_B":
            c = r["stage_b_cluster"]
            lower[key] = r1[key] = r2[key] = mx[key] = c
            n_stable += 1
            continue
        d = d_by.get(key)
        if d is None:
            continue
        if d["resolution"] == "CROSS_MODEL_CONSENSUS_ASSIGNMENT":
            c = d["final_cluster_id"]
            lower[key] = r1[key] = r2[key] = mx[key] = c
            n_consensus += 1
        else:
            n_unres += 1
            lower[key] = None
            a1, a2 = d["rep1_cluster"], d["rep2_cluster"]
            r1[key] = a1 if a1 != UNCERTAIN else None
            r2[key] = a2 if a2 != UNCERTAIN else None
            mx[key] = f"MAXSINGLETON::{q}::{rid}"
    return {"CANONICAL_RESOLVED_LOWER": lower,
            "CANONICAL_ASSIGNMENT_SENSITIVITY_R1": r1,
            "CANONICAL_ASSIGNMENT_SENSITIVITY_R2": r2,
            "CANONICAL_MATHEMATICAL_MAXIMUM": mx,
            "_counts": {"stable_same": n_stable, "cross_model_consensus": n_consensus,
                        "unresolved": n_unres,
                        "resolved_total": n_stable + n_consensus}}


def balanced_assignments() -> dict:
    e2 = list(csv.DictReader((_E / "e2_assignments_long.csv").open(encoding="utf-8")))
    e3 = list(csv.DictReader((_E / "e3_consolidated_assignments.csv").open(
        encoding="utf-8")))
    e3_by = {(int(r["question"]), r["raw_theme_id"]): r["extended_cluster_id"]
             for r in e3}
    strict, extended = {}, {}
    for r in e2:
        q, rid = int(r["question"]), r["raw_theme_id"]
        key, c = (q, rid), r["cluster_id"]
        if c == UNCERTAIN:
            strict[key] = extended[key] = None
        elif c == "NEW_CLUSTER":
            strict[key] = None
            ext = e3_by.get(key)
            extended[key] = None if ext in (None, UNCERTAIN) else ext
        else:
            strict[key] = extended[key] = c
    return {"STRICT_AGAINST_E1": strict, "EXTENDED_E3": extended}


def curve(assign: dict, prov: dict, question: int, condition: str) -> dict:
    """
    Accumulation over focus-group orderings. A theme contributes its cluster; a theme
    with no cluster under this scenario contributes nothing and is counted separately.
    """
    fgs = Q4_FGS if question == 4 else ALL_FGS
    by_fg = defaultdict(set)
    n_unassigned = 0
    for (q, rid), cl in assign.items():
        if q != question:
            continue
        p = prov.get((q, rid))
        if p is None or p["condition"] != condition or p["fg"] not in fgs:
            continue
        if cl is None:
            n_unassigned += 1
            continue
        by_fg[p["fg"]].add(cl)

    orders = list(permutations(fgs))
    curves = []
    for order in orders:
        seen, row = set(), []
        for fg in order:
            seen |= by_fg.get(fg, set())
            row.append(len(seen))
        curves.append(row)
    n_pos = len(fgs)
    mean = [round(statistics.mean(c[i] for c in curves), 3) for i in range(n_pos)]
    new_at = [round(mean[0], 3)] + [round(mean[i] - mean[i - 1], 3)
                                    for i in range(1, n_pos)]
    endpoint = len(set().union(*by_fg.values())) if by_fg else 0
    return {"question": question, "condition": condition,
            "n_focus_groups": n_pos, "n_orderings": len(orders),
            "mean_cumulative_by_position": mean,
            "mean_new_clusters_at_position": new_at,
            "endpoint_repertoire": endpoint,
            "n_themes_unassigned_in_this_scenario": n_unassigned,
            "per_fg_repertoire": {fg: len(by_fg.get(fg, set())) for fg in fgs}}


def build() -> dict:
    prov = provenance()
    canon = canonical_assignments()
    counts = canon.pop("_counts")
    bal = balanced_assignments()

    conditions = ("human", "enriched", "demographics-only")
    out = {}
    for name, assign in {**canon, **bal}.items():
        rows = []
        for q in sb.QUESTIONS:
            for cond in conditions:
                rows.append(curve(assign, prov, q, cond))
        out[name] = rows

    # unresolved accumulation, reported as its own curve and never mixed in
    unres = {k for k, v in canon["CANONICAL_RESOLVED_LOWER"].items() if v is None}
    unres_rows = []
    for q in sb.QUESTIONS:
        fgs = Q4_FGS if q == 4 else ALL_FGS
        by_fg = defaultdict(int)
        for (qq, rid) in unres:
            if qq != q:
                continue
            p = prov.get((qq, rid))
            if p and p["fg"] in fgs:
                by_fg[p["fg"]] += 1
        orders = list(permutations(fgs))
        cur = []
        for order in orders:
            tot, row = 0, []
            for fg in order:
                tot += by_fg.get(fg, 0)
                row.append(tot)
            cur.append(row)
        unres_rows.append({"question": q, "n_orderings": len(orders),
                           "mean_cumulative_unresolved": [
                               round(statistics.mean(c[i] for c in cur), 3)
                               for i in range(len(fgs))],
                           "total_unresolved": sum(by_fg.values()),
                           "per_fg": dict(by_fg)})

    # distribution of the 86
    dd = list(csv.DictReader((_D / "stage_d_decisions_long.csv").open(
        encoding="utf-8")))
    un = [r for r in dd if r["resolution"] == "CROSS_MODEL_UNRESOLVED"]
    dist = {"by_question": dict(Counter(int(r["question"]) for r in un)),
            "by_condition": dict(Counter(
                prov[(int(r["question"]), r["raw_theme_id"])]["condition"]
                for r in un)),
            "by_fg": dict(Counter(
                prov[(int(r["question"]), r["raw_theme_id"])]["fg"] for r in un)),
            "disagreement_type": {
                "UNCERTAIN_UNCERTAIN": sum(
                    1 for r in un if r["rep1_cluster"] == r["rep2_cluster"] ==
                    UNCERTAIN),
                "cluster_UNCERTAIN": sum(
                    1 for r in un
                    if (r["rep1_cluster"] == UNCERTAIN) !=
                       (r["rep2_cluster"] == UNCERTAIN)),
                "cluster_cluster_disagreement": sum(
                    1 for r in un if r["rep1_cluster"] != UNCERTAIN
                    and r["rep2_cluster"] != UNCERTAIN)}}

    return {"built_utc": datetime.now(UTC).isoformat(), "analysis": ANALYSIS,
            "scenarios_are_not_confidence_intervals": True,
            "maximum_is_a_construction_ceiling_not_an_estimate": True,
            "canonical_and_balanced_ids_never_mixed": True,
            "resolution_counts": counts,
            "coverage": {
                "canonical_resolved": f"{counts['resolved_total']}/526",
                "canonical_unresolved": f"{counts['unresolved']}/526",
                "balanced_extended": "520/526",
                "balanced_uncertain_excluded": 6},
            "orderings": {"Q1_Q2_Q3_Q5": 120, "Q4": 24,
                          "Q4_focus_groups": list(Q4_FGS),
                          "Q4_synthetic_fg5_outside_curve": True},
            "curves": out,
            "unresolved_accumulation": unres_rows,
            "unresolved_distribution": dist}


def main() -> int:
    b = build()
    _OUT.mkdir(parents=True, exist_ok=True)
    sb._atomic(_OUT / "inductive_accumulation_curves.json",
               {k: v for k, v in b.items() if k != "curves"})
    rows = []
    for scen, rs in b["curves"].items():
        for r in rs:
            rows.append({"scenario": scen, **{k: (json.dumps(v)
                                                  if isinstance(v, (list, dict)) else v)
                                              for k, v in r.items()}})
    with (_OUT / "inductive_accumulation_curves.csv").open(
            "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"=== {ANALYSIS} ===")
    print(f"  resueltos {b['coverage']['canonical_resolved']}   "
          f"sin resolver {b['coverage']['canonical_unresolved']}")
    print(f"  balanceada extendida {b['coverage']['balanced_extended']}")
    print("\n  endpoints por escenario (suma sobre preguntas, por condición):")
    for scen, rs in b["curves"].items():
        by_c = defaultdict(int)
        for r in rs:
            by_c[r["condition"]] += r["endpoint_repertoire"]
        print(f"    {scen:38s} " + "  ".join(
            f"{c} {by_c[c]:3d}" for c in ("human", "enriched", "demographics-only")))
    print("\n  distribución de los no resueltos:")
    d = b["unresolved_distribution"]
    print(f"    por pregunta {d['by_question']}")
    print(f"    por condición {d['by_condition']}")
    print(f"    por FG {d['by_fg']}")
    print(f"    tipo {d['disagreement_type']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
