"""
PARTICIPANT_BREADTH_AND_RECURRENCE_HIERARCHY_SIMILARITY

Reads only the existing Tier-1 results. No API call, no new coding, no human task.

WHAT THIS IS
------------
This operationalisation evaluates whether themes have a similar hierarchy of
participant breadth and across-group recurrence. It does not establish that the themes
had equivalent interpretive importance, centrality or meaning.

Reach-based automated salience stays separate from the researcher's decision
CENTRALITY_NOT_ASSESSED, which this analysis neither uses nor supersedes.

WHY THE LEGACY METRIC IS NOT THE HEADLINE
-----------------------------------------
`tier1_salience_hierarchy` correlated ranks over subthemes present on BOTH sides. That
drops every synthetic omission from the comparison, so a run that recovered two of a
human FG's nine themes could score a perfect correlation on those two. It is retained as
LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC and is never a primary result.

The primary universe here is **every subtheme the human FG expressed**. A human theme
the synthetic run genuinely did not produce scores 0 — it is not deleted from the
comparison.

    py scripts/salience_hierarchy.py
"""
from __future__ import annotations

import csv
import json
import os
import statistics
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

from scipy import stats

_ROOT = Path(__file__).resolve().parent.parent
_RES = _ROOT / "analysis/production_evaluation/results"
_OUT = _ROOT / "analysis/production_evaluation/final"

FGS = ["fg1", "fg2", "fg3", "fg4", "fg5"]
REPS = ["1", "2", "3"]
SYNTH = ["enriched", "demographics-only"]
NAME = "PARTICIPANT_BREADTH_AND_RECURRENCE_HIERARCHY_SIMILARITY"

MANDATORY_STATEMENT = (
    "This operationalisation evaluates whether themes have a similar hierarchy of "
    "participant breadth and across-group recurrence. It does not establish that the "
    "themes had equivalent interpretive importance, centrality or meaning.")

FORBIDDEN_TERMS = ("validated thematic importance", "human-validated centrality",
                   "interpretive dominance", "salience validation")

TOP_K = 3


# ------------------------------------------------------------------ load
def _rows(name):
    with (_RES / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load():
    """
    presence: 35 documents x 11 subthemes, complete.
    reach   : one row per present subtheme.

    A subtheme with a presence row saying present=False is a TRUE ABSENCE and scores 0.
    A subtheme with no presence row at all would be UNMEASURED and scores null. The two
    are never conflated, and a test asserts no null is silently coerced to 0.
    """
    pres = _rows("thematic_code_presence_long.csv")
    reach = _rows("thematic_reach_long.csv")
    codes = sorted({r["subtheme_id"] for r in pres})

    def key(r):
        side = r["side"]
        return (r["condition"], r["fg"],
                r["canonical_replication_index"] if side == "synthetic" else "human",
                r["subtheme_id"])

    P = {key(r): r for r in pres}
    R = {key(r): r for r in reach}
    if len(P) != len(pres):
        raise RuntimeError("duplicate presence keys")
    orphan_reach = sorted(set(R) - set(P))
    if orphan_reach:
        raise RuntimeError(f"reach rows without presence: {orphan_reach[:5]}")
    return codes, P, R


def score(P, R, cond, fg, rep, code):
    """
    (value, status) for one cell.

      present   -> observed reach
      absent    -> 0.0, a measured absence
      unmeasured-> None, and never turned into 0
    """
    k = (cond, fg, rep, code)
    p = P.get(k)
    if p is None:
        return None, "UNMEASURED_NO_PRESENCE_ROW"
    if p["present"] == "True":
        r = R.get(k)
        if r is None or r.get("reach") in (None, ""):
            return None, "UNMEASURED_PRESENT_BUT_NO_REACH"
        return float(r["reach"]), "PRESENT"
    return 0.0, "TRUE_ABSENCE"


# ------------------------------------------------------- rank statistics
def _tau_b(a, b):
    if len(a) < 3:
        return None, "FEWER_THAN_3_THEMES"
    if len(set(a)) == 1 and len(set(b)) == 1:
        return None, "BOTH_SIDES_CONSTANT"
    if len(set(a)) == 1:
        return None, "HUMAN_SIDE_CONSTANT"
    if len(set(b)) == 1:
        return None, "SYNTHETIC_SIDE_CONSTANT"
    t = stats.kendalltau(a, b, variant="b")
    v = float(t.statistic)
    return (None, "UNDEFINED_NAN") if v != v else (round(v, 4), None)


def _spearman(a, b):
    if len(a) < 3 or len(set(a)) == 1 or len(set(b)) == 1:
        return None
    v = float(stats.spearmanr(a, b).statistic)
    return None if v != v else round(v, 4)


def _n_ties(v):
    c = defaultdict(int)
    for x in v:
        c[x] += 1
    return sum(n * (n - 1) // 2 for n in c.values())


def _top_set(codes, vals, k=TOP_K):
    """Tie-aware top-k: every code sharing the k-th value is included."""
    pairs = sorted(zip(codes, vals), key=lambda x: -x[1])
    if len(pairs) <= k:
        return {c for c, _ in pairs}
    cut = pairs[k - 1][1]
    return {c for c, v in pairs if v >= cut}


def _overlap(a, b):
    u = a | b
    return round(len(a & b) / len(u), 4) if u else None


def _norm_mad(a, b):
    return round(sum(abs(x - y) for x, y in zip(a, b)) / len(a), 4) if a else None


# ------------------------------------- A. group-level breadth hierarchy
def group_level(codes, P, R):
    out = []
    for fg in FGS:
        human = {c: score(P, R, "human", fg, "human", c) for c in codes}
        universe = sorted(c for c, (v, s) in human.items() if s == "PRESENT")
        union_base = set(universe)
        for cond in SYNTH:
            for rep in REPS:
                syn = {c: score(P, R, cond, fg, rep, c) for c in codes}
                # ---- primary: every human-present theme -------------------
                hv, sv, used, nulls = [], [], [], []
                for c in universe:
                    a, _ = human[c]
                    b, st = syn[c]
                    if b is None:
                        nulls.append({"subtheme_id": c, "reason": st})
                        continue
                    hv.append(a)
                    sv.append(b)
                    used.append(c)
                tau, undef = _tau_b(hv, sv)
                zeros = sum(1 for c, v in zip(used, sv) if v == 0.0)
                rec = sum(1 for c, v in zip(used, sv) if v > 0.0)
                # ---- union sensitivity ------------------------------------
                uni = sorted(union_base | {c for c, (v, s) in syn.items()
                                           if s == "PRESENT"})
                uh, us = [], []
                for c in uni:
                    a, sa = human[c]
                    b, sb = syn[c]
                    if a is None or b is None:
                        continue
                    uh.append(a)
                    us.append(b)
                utau, uundef = _tau_b(uh, us)
                out.append({
                    "fg": fg, "condition": cond, "canonical_replication_index": rep,
                    "n_human_present": len(universe),
                    "n_scored": len(used),
                    "n_synthetic_recovered": rec,
                    "n_human_themes_assigned_zero": zeros,
                    "n_unmeasured_excluded": len(nulls),
                    "unmeasured_detail": nulls,
                    "n_ties_human": _n_ties(hv), "n_ties_synthetic": _n_ties(sv),
                    "kendall_tau_b": tau, "undefined_reason": undef,
                    "spearman_avg_ranks": _spearman(hv, sv),
                    "normalized_mean_abs_reach_diff": _norm_mad(hv, sv),
                    "top_theme_overlap_tie_aware": _overlap(
                        _top_set(used, hv), _top_set(used, sv)) if used else None,
                    "union_n_themes": len(uh),
                    "union_kendall_tau_b": utau,
                    "union_undefined_reason": uundef,
                    "union_caveat": ("the union variant mixes fidelity with synthetic "
                                     "thematic proliferation and is a secondary "
                                     "sensitivity only"),
                    "primary_universe": "all subthemes the human FG expressed",
                })
    return out


# --------------------------------- B. study-level recurrence hierarchy
def study_level(codes, P, R):
    def profile(cond, rep):
        n_present, mean_reach, unmeasured = {}, {}, {}
        for c in codes:
            vals, miss = [], 0
            for fg in FGS:
                v, st = score(P, R, cond, fg, rep, c)
                if v is None:
                    miss += 1
                else:
                    vals.append(v)
            n_present[c] = sum(1 for v in vals if v > 0.0)
            mean_reach[c] = round(statistics.mean(vals), 4) if vals else None
            unmeasured[c] = miss
        return n_present, mean_reach, unmeasured

    hn, hm, hu = profile("human", "human")
    out = []
    for cond in SYNTH:
        for rep in REPS:
            sn, sm, su = profile(cond, rep)
            use = [c for c in codes if hm[c] is not None and sm[c] is not None]
            tau_n, u1 = _tau_b([hn[c] for c in use], [sn[c] for c in use])
            tau_m, u2 = _tau_b([hm[c] for c in use], [sm[c] for c in use])
            out.append({
                "condition": cond, "canonical_replication_index": rep,
                "n_subthemes": len(use),
                "kendall_tau_b_n_fgs_present": tau_n, "undefined_reason_n_fgs": u1,
                "kendall_tau_b_mean_reach": tau_m, "undefined_reason_mean_reach": u2,
                "top3_overlap_tie_aware_n_fgs": _overlap(
                    _top_set(use, [hn[c] for c in use]),
                    _top_set(use, [sn[c] for c in use])),
                "top3_overlap_tie_aware_mean_reach": _overlap(
                    _top_set(use, [hm[c] for c in use]),
                    _top_set(use, [sm[c] for c in use])),
                "n_unmeasured_cells": sum(su.values()),
                "human_n_fgs_present": hn, "synthetic_n_fgs_present": sn,
                "human_mean_reach": hm, "synthetic_mean_reach": sm,
                "unit": ("one complete realisation of the study: 5 FGs at a single "
                         "canonical_replication_index; the 15 sessions of a condition "
                         "are NEVER treated as 15 independent focus groups"),
            })
    return out, (hn, hm)


# ------------------------------------------------------- D. aggregation
def aggregate(per_run):
    by_cell = defaultdict(list)
    for r in per_run:
        by_cell[(r["fg"], r["condition"])].append(r)
    cells = []
    for (fg, cond), rows in sorted(by_cell.items()):
        taus = [r["kendall_tau_b"] for r in rows if r["kendall_tau_b"] is not None]
        cells.append({
            "fg": fg, "condition": cond,
            "n_replicates": len(rows),
            "n_defined": len(taus),
            "replicate_values": {r["canonical_replication_index"]: r["kendall_tau_b"]
                                 for r in rows},
            "undefined_reasons": {r["canonical_replication_index"]:
                                  r["undefined_reason"] for r in rows
                                  if r["undefined_reason"]},
            "median_kendall_tau_b": round(statistics.median(taus), 4) if taus else None,
            "min_kendall_tau_b": round(min(taus), 4) if taus else None,
            "max_kendall_tau_b": round(max(taus), 4) if taus else None,
            "summary_rule": ("median over the three replicates; min and max are shown "
                             "so no value is hidden. Correlations are not averaged."),
        })
    med = {(c["fg"], c["condition"]): c["median_kendall_tau_b"] for c in cells}
    paired = []
    for fg in FGS:
        e, d = med.get((fg, "enriched")), med.get((fg, "demographics-only"))
        paired.append({
            "fg": fg, "enriched_median": e, "demographics_only_median": d,
            "difference_enriched_minus_demo": (None if e is None or d is None
                                               else round(e - d, 4)),
            "direction": ("undefined" if e is None or d is None else
                          "enriched" if e > d else
                          "demographics-only" if d > e else "tie"),
        })
    defined = [p["difference_enriched_minus_demo"] for p in paired
               if p["difference_enriched_minus_demo"] is not None]
    return cells, {
        "paired_differences": paired,
        "n_pairs_defined": len(defined),
        "median_difference": round(statistics.median(defined), 4) if defined else None,
        "min_difference": round(min(defined), 4) if defined else None,
        "max_difference": round(max(defined), 4) if defined else None,
        "direction_counts": {
            d: sum(1 for p in paired if p["direction"] == d)
            for d in ("enriched", "demographics-only", "tie", "undefined")},
        "unit_of_analysis": "focus group; n = 5 paired differences, never 15",
        "inference": "NONE — direction and descriptive distribution only",
    }


# ------------------------------------------------------------ theme long
def theme_long(codes, P, R):
    out = []
    for cond in ["human"] + SYNTH:
        reps = ["human"] if cond == "human" else REPS
        for fg in FGS:
            for rep in reps:
                for c in codes:
                    v, st = score(P, R, cond, fg, rep, c)
                    out.append({
                        "condition": cond, "fg": fg,
                        "canonical_replication_index": "" if rep == "human" else rep,
                        "subtheme_id": c, "reach": "" if v is None else v,
                        "status": st,
                        "is_true_absence_scored_zero": st == "TRUE_ABSENCE",
                        "is_unmeasured_null": v is None})
    return out


def build() -> dict:
    codes, P, R = load()
    per_run = group_level(codes, P, R)
    studies, human_profile = study_level(codes, P, R)
    cells, paired = aggregate(per_run)
    long = theme_long(codes, P, R)
    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "analysis": NAME,
        "status": "EXPLORATORY — post-result operationalisation",
        "mandatory_statement": MANDATORY_STATEMENT,
        "separate_from": ("the researcher decision CENTRALITY_NOT_ASSESSED; automated "
                          "reach-based salience neither uses nor supersedes it"),
        "legacy_metric": {
            "metric_id": "tier1_salience_hierarchy",
            "reclassified_as": "LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC",
            "why": ("Spearman over shared-present subthemes only; drops synthetic "
                    "omissions, is undefined in many sessions, and can look favourable "
                    "on a tiny subset"),
            "retained": True, "used_as_primary_result": False},
        "no_api_calls": True, "no_new_coding": True,
        "n_codes": len(codes), "codes": codes,
        "per_run": per_run, "by_fg_condition": cells,
        "paired_summary": paired, "study_replicates": studies,
        "human_study_profile": {"n_fgs_present": human_profile[0],
                                "mean_reach": human_profile[1]},
        "theme_scores_long": long,
    }


if __name__ == "__main__":
    b = build()
    print(b["analysis"], "|", b["status"])
    print(f"per-run rows {len(b['per_run'])}  cells {len(b['by_fg_condition'])}  "
          f"study replicates {len(b['study_replicates'])}  long {len(b['theme_scores_long'])}")
    d = b["paired_summary"]
    print("direction counts:", d["direction_counts"], " median diff:",
          d["median_difference"])
