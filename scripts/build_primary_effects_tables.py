"""
Primary effects at the FROZEN unit of analysis: the focus group.

THE UNIT IS THE FG, n = 5 PAIRS
Each FG x condition value is the mean of its three canonical replicates. The
replicates estimate GENERATOR variability under a fixed configuration; they are not
five additional focus groups and not independent observations of the population. So
the paired comparison has n = 5, not n = 15, and no test treating the 15 runs as
independent is run here.

WHAT IS AND IS NOT EMITTED
  * per-FG replicate values, means, difference, direction, within-cell SD;
  * across-FG mean / median / min / max difference and the direction count;
  * F1 kept separate and secondary;
  * an EXPLORATORY paired sign test whose ceiling is stated, not implied;
  * no confidence intervals built on n = 15 independent observations.

No API calls. Reads the emitted tables only.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from datetime import datetime, UTC
from math import comb
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_R = _REPO_ROOT / "analysis" / "production_evaluation" / "results"

FGS = ("fg1", "fg2", "fg3", "fg4", "fg5")
PRIMARY = (("recall", "tier1_subtheme_recall"),
           ("precision", "tier1_matched_theme_precision"),
           ("reach", "tier1_participant_reach"))
SECONDARY = (("f1_secondary", "tier1_f1_secondary"),)


# Tie definition, stated rather than implied:
#   a pair is a TIE when the FULL-PRECISION difference of the two cell means is
#   exactly 0.0 — not when it rounds to 0.0 at any display precision.
TIE_IS_EXACT_ZERO = True


def _rows():
    """
    Session values at FULL precision, computed from the evaluator cache.

    Reading per_run_metrics.csv would start from values the aggregator already
    rounded to 4 dp; averaging and differencing those would decide signs and ties on
    twice-rounded numbers. The definitions are shared with the aggregator via
    `unrounded_run_metrics`, so only the rounding differs.
    """
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import aggregate_production_results as agg
    res = agg.load_results()
    human = {r["input"]["fg"]: r for r in res if r["input"]["side"] == "human"}
    rows = []
    for r in res:
        if r["input"]["side"] != "synthetic":
            continue
        m = agg.unrounded_run_metrics(human[r["input"]["fg"]], r)
        rows.append({
            "physical_run": r["input"]["physical_run"],
            "fg": r["input"]["fg"], "condition": r["input"]["condition"],
            "canonical_replication_index": r["input"]["canonical_replication_index"],
            "tier1_subtheme_recall": m["recall"],
            "tier1_matched_theme_precision": m["precision"],
            "tier1_participant_reach": m["reach"],
            "tier1_f1_secondary": m["f1_secondary"],
        })
    return rows


def _f(v):
    return None if v in ("", None) else float(v)


def cell(rows, fg, cond, col):
    vals = [_f(r[col]) for r in sorted(rows, key=lambda x: x["canonical_replication_index"])
            if r["fg"] == fg and r["condition"] == cond and _f(r[col]) is not None]
    return vals


def sign_test_two_sided(diffs: list[float]) -> dict:
    """
    Exact paired sign test. EXPLORATORY ONLY.

    THE CEILING DEPENDS ON n_effective, NOT n_total.
    Ties (zero differences) carry no sign and are dropped, so a metric with five
    pairs and two ties is tested on THREE observations: 2^3 = 8 assignments and a
    minimum attainable two-sided p of 0.25, not 0.0625. Quoting the n=5 ceiling for
    such a metric would overstate what the test could ever have detected.
    """
    n_total = len(diffs)
    nz = [d for d in diffs if d != 0]
    n_eff = len(nz)
    ties = n_total - n_eff
    base = {
        "test": "exact paired sign test",
        "classification": "EXPLORATORY — not confirmatory",
        "n_total_pairs": n_total,
        "n_effective_pairs": n_eff,
        "n_ties": ties,
    }
    if n_eff == 0:
        return {**base, "possible_sign_assignments": 0, "p_two_sided": None,
                "minimum_attainable_two_sided_p": None,
                "cannot_reach_p05": True,
                "caveat": ("every paired difference is exactly zero; the sign test is "
                           "undefined and no p-value exists")}
    k = sum(1 for d in nz if d > 0)
    assignments = 2 ** n_eff
    tail = sum(comb(n_eff, i) for i in range(0, min(k, n_eff - k) + 1))
    p = min(1.0, 2 * tail / assignments)
    p_min = 2 / assignments
    return {
        **base,
        "n_favouring_enriched": k,
        "n_favouring_demographics_only": n_eff - k,
        "possible_sign_assignments": assignments,
        "p_two_sided": round(p, 4),
        "minimum_attainable_two_sided_p": round(p_min, 4),
        "cannot_reach_p05": p_min > 0.05,
        "caveat": (f"n_total={n_total} pairs, {ties} tie(s), so n_effective={n_eff}. "
                   f"{assignments} possible sign assignments and a minimum attainable "
                   f"two-sided p of {round(p_min, 4)}. The ceiling follows n_effective, "
                   f"not n_total. This test "
                   f"{'cannot' if p_min > 0.05 else 'can in principle'} reach p<.05, and "
                   f"it does not replace the per-FG effects or the qualitative analysis."),
    }


def build() -> dict:
    rows = _rows()
    out = {"generated_utc": datetime.now(UTC).isoformat(),
           "unit_of_analysis": "focus group",
           "n_pairs": 5,
           "cell_value": "mean of the three canonical replicates",
           "replicates_are": ("generator variability under a fixed configuration; NOT "
                              "independent focus groups"),
           "tests_not_run": ["t-test", "Mann-Whitney", "regression treating the 15 runs "
                             "as independent"],
           "metrics": {}}

    for label, col in PRIMARY + SECONDARY:
        per_fg, diffs = [], []
        for fg in FGS:
            e, d = cell(rows, fg, "enriched", col), cell(rows, fg, "demographics-only", col)
            # FULL precision for the arithmetic; rounding happens only on output.
            em = statistics.mean(e) if e else None
            dm = statistics.mean(d) if d else None
            diff = (em - dm) if (em is not None and dm is not None) else None
            per_fg.append({
                "fg": fg,
                "enriched_values": [round(x, 4) for x in e],
                "enriched_mean": None if em is None else round(em, 4),
                "enriched_within_cell_sd": round(statistics.stdev(e), 4) if len(e) > 1 else None,
                "demographics_only_values": [round(x, 4) for x in d],
                "demographics_only_mean": None if dm is None else round(dm, 4),
                "demographics_only_within_cell_sd": round(statistics.stdev(d), 4) if len(d) > 1 else None,
                "difference_enriched_minus_demo": None if diff is None else round(diff, 4),
                "difference_full_precision": diff,
                "direction": ("enriched" if diff and diff > 0 else
                              "demographics-only" if diff and diff < 0 else "tie"),
            })
            if diff is not None:
                diffs.append(diff)
        summary = {
            "n_fgs": len(diffs),
            "mean_difference": round(statistics.mean(diffs), 4),
            "median_difference": round(statistics.median(diffs), 4),
            "min_difference": round(min(diffs), 4), "max_difference": round(max(diffs), 4),
            "n_favouring_enriched": sum(1 for d in diffs if d > 0),
            "n_favouring_demographics_only": sum(1 for d in diffs if d < 0),
            "n_ties": sum(1 for d in diffs if d == 0),
        }
        entry = {"role": "primary" if (label, col) in PRIMARY else "secondary",
                 "per_fg": per_fg, "across_fgs": summary,
                 "exploratory_sign_test": sign_test_two_sided(diffs)}
        out["metrics"][label] = entry

        # sensitivity: with and without FG4 — diagnostic only
        d4 = [p["difference_enriched_minus_demo"] for p in per_fg if p["fg"] != "fg4"]
        entry["sensitivity_excluding_fg4"] = {
            "justified": False,
            "note": ("Diagnostic only. FG4 demographics-only shows zero overlap, not a "
                     "technical failure, so exclusion is NOT methodologically justified. "
                     "Both figures are shown."),
            "n_fgs": len(d4),
            "mean_difference_with_fg4": summary["mean_difference"],
            "mean_difference_without_fg4": round(statistics.mean(d4), 4),
            "n_favouring_enriched_without_fg4": sum(1 for d in d4 if d > 0),
        }
    return out


def write_csv(data: dict) -> None:
    hdr = ["metric", "role", "fg",
           "enriched_r1", "enriched_r2", "enriched_r3", "enriched_mean",
           "enriched_within_cell_sd",
           "demographics_only_r1", "demographics_only_r2", "demographics_only_r3",
           "demographics_only_mean", "demographics_only_within_cell_sd",
           "difference_enriched_minus_demo", "direction"]
    rows = []
    for label, entry in data["metrics"].items():
        for p in entry["per_fg"]:
            ev = (p["enriched_values"] + [None] * 3)[:3]
            dv = (p["demographics_only_values"] + [None] * 3)[:3]
            rows.append({
                "metric": label, "role": entry["role"], "fg": p["fg"],
                "enriched_r1": ev[0], "enriched_r2": ev[1], "enriched_r3": ev[2],
                "enriched_mean": p["enriched_mean"],
                "enriched_within_cell_sd": p["enriched_within_cell_sd"],
                "demographics_only_r1": dv[0], "demographics_only_r2": dv[1],
                "demographics_only_r3": dv[2],
                "demographics_only_mean": p["demographics_only_mean"],
                "demographics_only_within_cell_sd": p["demographics_only_within_cell_sd"],
                "difference_enriched_minus_demo": p["difference_enriched_minus_demo"],
                "direction": p["direction"],
            })
    with (_R / "primary_effects_by_fg.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in hdr})

    hdr2 = ["metric", "role", "n_fgs", "mean_difference", "median_difference",
            "min_difference", "max_difference", "n_favouring_enriched",
            "n_favouring_demographics_only", "n_ties",
            "n_nonzero_pairs", "possible_sign_assignments",
            "exploratory_sign_test_p_two_sided", "minimum_attainable_p",
            "sign_test_cannot_reach_p05", "inference_note"]
    with (_R / "primary_effects_summary.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr2, extrasaction="ignore")
        w.writeheader()
        for label, e in data["metrics"].items():
            s, t = e["across_fgs"], e["exploratory_sign_test"]
            w.writerow({"metric": label, "role": e["role"], **s,
                        "n_nonzero_pairs": t.get("n_effective_pairs"),
                        "possible_sign_assignments": t.get("possible_sign_assignments"),
                        "exploratory_sign_test_p_two_sided": t.get("p_two_sided"),
                        "minimum_attainable_p": t.get("minimum_attainable_two_sided_p"),
                        "sign_test_cannot_reach_p05": t.get("cannot_reach_p05"),
                        "inference_note": t.get("caveat", "")})


if __name__ == "__main__":
    data = build()
    write_csv(data)
    (_REPO_ROOT / "analysis" / "production_evaluation" /
     "primary_effects_fg_level.json").write_text(
        json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    for label, e in data["metrics"].items():
        s = e["across_fgs"]
        print(f"\n== {label} ({e['role']}) — unit=FG, n={s['n_fgs']} pairs")
        for p in e["per_fg"]:
            print(f"   {p['fg']}  enr {p['enriched_mean']!s:<7} (sd {p['enriched_within_cell_sd']!s:<7}) "
                  f"demo {p['demographics_only_mean']!s:<7} (sd {p['demographics_only_within_cell_sd']!s:<7}) "
                  f"diff {p['difference_enriched_minus_demo']!s:<8} {p['direction']}")
        print(f"   across FGs: mean {s['mean_difference']}  median {s['median_difference']}  "
              f"range [{s['min_difference']}, {s['max_difference']}]  "
              f"favour E/D/tie {s['n_favouring_enriched']}/{s['n_favouring_demographics_only']}/{s['n_ties']}")
        t = e["exploratory_sign_test"]
        print(f"   sign test (EXPLORATORY): n_total={t['n_total_pairs']} ties={t['n_ties']} "
              f"n_effective={t['n_effective_pairs']} assignments={t['possible_sign_assignments']} "
              f"p={t.get('p_two_sided')} p_min={t.get('minimum_attainable_two_sided_p')}")
    print("\nwrote primary_effects_by_fg.csv, primary_effects_summary.csv, "
          "primary_effects_fg_level.json")
