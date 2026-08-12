"""
Derive every structural figure quoted in the final report from its source artefact.

Nothing here is copied from the report. Each figure is recomputed from
results/structural_interaction_metrics_long.csv (or primary_effects_by_fg.csv for the
theme-level FG4 context), so the traceability index records a derivation rather than a
transcription. Read-only.

    py scripts/structural_traceability.py
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RES = _ROOT / "analysis/production_evaluation/results"
_OUT = _ROOT / "analysis/production_evaluation/final/structural_traceability.json"

STRUCTURAL = ["total_words", "participant_turns", "words_per_turn_iqr",
              "short_turn_proportion_25w", "turn_balance_gini", "chain_depth",
              "moderator_word_share"]
CONDITIONS = ["human", "enriched", "demographics-only"]


def _rows():
    with (_RES / "structural_interaction_metrics_long.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def build() -> dict:
    rows = [r for r in _rows() if r["metric_id"] in STRUCTURAL]
    figures, per_fg = [], {}

    for mid in STRUCTURAL:
        mrows = [r for r in rows if r["metric_id"] == mid]
        ns = sorted({r["namespace"] for r in mrows})
        # FG-level mean per condition: replicates collapse to their FG mean first, so
        # the comparative unit stays the focus group and not the session.
        by_cond = {}
        for cond in CONDITIONS:
            crows = [r for r in mrows if r["condition"] == cond]
            fgm = {}
            for r in crows:
                v = _num(r["value"])
                if v is not None:
                    fgm.setdefault(r["fg"], []).append(v)
            # Exact throughout. Rounding happens once, at presentation, and never
            # before a subtraction or a comparison: rounding e and d to 4 dp and then
            # subtracting gives the difference two rounding errors instead of one, and
            # can move the last digit (it did: four figures were off by 1 ulp against
            # the source table). Comparisons on rounded means can also flip a near-tie.
            fg_means = {fg: statistics.mean(v) for fg, v in sorted(fgm.items())}
            by_cond[cond] = {
                "fg_means_exact": fg_means,
                "mean_over_fgs_exact": (statistics.mean(fg_means.values())
                                        if fg_means else None),
                "n_fg": len(fg_means),
                "n_rows": len(crows)}
        e = by_cond["enriched"]["mean_over_fgs_exact"]
        d = by_cond["demographics-only"]["mean_over_fgs_exact"]
        h = by_cond["human"]["mean_over_fgs_exact"]
        diff = None if e is None or d is None else round(e - d, 4)

        closer, per_fg_closer = 0, {}
        if h is not None:
            for fg in by_cond["enriched"]["fg_means_exact"]:
                ev = by_cond["enriched"]["fg_means_exact"].get(fg)
                dv = by_cond["demographics-only"]["fg_means_exact"].get(fg)
                hv = by_cond["human"]["fg_means_exact"].get(fg)
                if None in (ev, dv, hv):
                    continue
                win = abs(ev - hv) < abs(dv - hv)      # exact operands, not rounded
                per_fg_closer[fg] = win
                closer += int(win)

        for cond, key in (("human", "human"), ("enriched", "enriched"),
                          ("demographics-only", "demographics_only")):
            _m = by_cond[cond]["mean_over_fgs_exact"]
            figures.append({
                "figure": f"structural.{mid}.{key}",
                "value": None if _m is None else round(_m, 4),
                "source": "results/structural_interaction_metrics_long.csv",
                "rule": (f"filter metric_id == '{mid}' and condition == '{cond}'; mean "
                         "of the per-FG means (replicates collapse to their FG mean "
                         "first, so the FG stays the comparative unit)"),
                "column": "value",
                "unit_of_analysis": f"focus group (n={by_cond[cond]['n_fg']})",
                "namespace": ns[0] if len(ns) == 1 else ns,
                "n_source_rows": by_cond[cond]["n_rows"]})
        figures.append({
            "figure": f"structural.{mid}.enriched_minus_demo",
            "value": diff,
            "source": "results/structural_interaction_metrics_long.csv",
            "rule": ("exact enriched mean minus exact demographics-only mean, rounded "
                     "once at the end. NOT the difference of the two rounded means "
                     "printed above — subtracting already-rounded values would carry "
                     "two rounding errors into the result"),
            "column": "value", "unit_of_analysis": "focus group (n=5)",
            "namespace": ns[0] if len(ns) == 1 else ns,
            "operands_exact": {"enriched": e, "demographics_only": d},
            "n_source_rows": len(mrows)})
        figures.append({
            "figure": f"structural.{mid}.n_fg_enriched_closer_to_human",
            "value": f"{closer}/{len(per_fg_closer)}",
            "source": "results/structural_interaction_metrics_long.csv",
            "rule": ("per FG, count where |enriched_fg_mean - human_fg_mean| < "
                     "|demo_fg_mean - human_fg_mean|. A small-n directional count: it "
                     "is not a test and does not evidence a consistent advantage. "
                     "Compared on exact FG means, never on rounded ones"),
            "column": "value", "unit_of_analysis": "focus group (n=5)",
            "namespace": ns[0] if len(ns) == 1 else ns,
            "per_fg": per_fg_closer})
        per_fg[mid] = {c: {k: round(v, 4)
                           for k, v in by_cond[c]["fg_means_exact"].items()}
                       for c in CONDITIONS}

    # --- FG2 and FG4 numeric exceptions, and the theme-level FG4 context ------
    with (_RES / "primary_effects_by_fg.csv").open(encoding="utf-8") as f:
        pe = list(csv.DictReader(f))
    for metric in ("recall", "precision", "reach", "f1_secondary"):
        for fg in ("fg2", "fg4"):
            r = next((x for x in pe if x["metric"] == metric and x["fg"] == fg), None)
            if not r:
                continue
            figures.append({
                "figure": f"deductive.{metric}.{fg}.difference_enriched_minus_demo",
                "value": _num(r["difference_enriched_minus_demo"]),
                "source": "results/primary_effects_by_fg.csv",
                "rule": (f"row metric == '{metric}' and fg == '{fg}'; the exception "
                         "noted in the report narrative"),
                "column": "difference_enriched_minus_demo",
                "unit_of_analysis": "focus group (mean of 3 replicates per cell)",
                "namespace": "_comparable_window",
                "direction": r["direction"],
                "demographics_only_mean": _num(r["demographics_only_mean"]),
                "enriched_mean": _num(r["enriched_mean"]),
                "within_cell_sd": {"enriched": _num(r["enriched_within_cell_sd"]),
                                   "demographics_only":
                                       _num(r["demographics_only_within_cell_sd"])}})

    # --- theme-level FG4 context: the figures that qualify the subtheme-level zeros ---
    with (_RES / "per_run_metrics.csv").open(encoding="utf-8") as f:
        pr = [r for r in csv.DictReader(f)
              if r.get("fg") == "fg4" and r.get("condition") == "demographics-only"]
    for col, lbl in (("tier1_subtheme_recall", "subtheme_recall"),
                     ("tier1_matched_theme_precision", "subtheme_precision"),
                     ("tier1_theme_level_recall", "theme_level_recall"),
                     ("tier1_theme_level_precision", "theme_level_precision")):
        vals = sorted(_num(r[col]) for r in pr)
        figures.append({
            "figure": f"deductive.fg4_demographics_only.{lbl}",
            "value": (f"{vals[0]}" if vals[0] == vals[-1]
                      else f"{vals[0]}-{vals[-1]}"),
            "per_replicate": {r["physical_run"]: _num(r[col]) for r in sorted(
                pr, key=lambda x: x["physical_run"])},
            "source": "results/per_run_metrics.csv",
            "rule": (f"rows fg == 'fg4' and condition == 'demographics-only'; column "
                     f"'{col}' across the three replicates. Reported to qualify the "
                     "subtheme-level zeros: the same runs are not empty at theme level"),
            "column": col,
            "unit_of_analysis": "run (3 replicates of one FG cell)",
            "namespace": "_comparable_window"})

    out = {"built_from": "source artefacts only; no value copied from the report",
           "n_figures": len(figures),
           "figures": figures,
           "per_fg_structural_means": per_fg}
    tmp = _OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    import os
    os.replace(tmp, _OUT)
    return out


def main() -> int:
    o = build()
    print(f"{o['n_figures']} structural / exception figures derived from source\n")
    for f in o["figures"]:
        print(f"  {f['figure']:58s} {str(f['value']):>10s}  <- {f['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
