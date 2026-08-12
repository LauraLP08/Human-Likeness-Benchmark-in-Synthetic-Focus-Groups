"""
Level 2 — coverage accumulation, computed from the existing Tier 1 coded data.

No API call, no new human coding, no new instrument. Input is
results/thematic_code_presence_long.csv: 35 documents (5 human focus groups + 30
synthetic runs) x 11 codebook subthemes = 385 rows.

UNIT OF ACCUMULATION
--------------------
The registry defines `saturation_curve` and `theme_recurrence_across_groups` per
**study replicate x condition**. A study replicate is one complete pass over FG1-FG5 at
a single `canonical_replication_index`. Accumulation therefore runs across the five
focus groups *within* a replicate:

    human               1 curve   (FG1..FG5)
    enriched            3 curves  (R1, R2, R3), each FG1..FG5
    demographics-only   3 curves  (R1, R2, R3), each FG1..FG5

An earlier version unioned the three replicates within each focus group before building
a single curve per condition. That is a different and larger object: it describes what
fifteen sessions collectively contain, not what one study of five groups would recover.
The union figure is retained, but only under the name
CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS, and it must never be
presented as the repertoire of a study replicate.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
Guest et al. (2016) and Hennink et al. (2019) measure saturation over an *inductively
growing* codebook. This study's Tier 1 codebook is fixed a priori at 11 subthemes, so
nothing new can emerge by construction. What is computed is a **coverage-accumulation
curve against a fixed codebook** — the registry's `saturation_curve`. It is NOT code
saturation in the Guest/Hennink sense and the two must never be equated. Meaning
saturation is NOT computed: it requires a judgement about whether an issue is fully
understood, which no automated method supplies.

The endpoint of a curve is simply the total observed for that replicate. It is not
evidence of a plateau. A plateau criterion is applied only where stated, is defined
explicitly below, and is post hoc.

TEMPORAL STATUS
---------------
The general indicators appear in the original methodology, but *these operationalisations*
were finalised after the main results were known. Everything here is EXPLORATORY.

    py scripts/saturation_analysis.py
"""
from __future__ import annotations

import csv
import itertools
import json
import os
import statistics
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RES = _ROOT / "analysis/production_evaluation/results"
_OUT = _ROOT / "analysis/production_evaluation/final/saturation_analysis.json"

FGS = ["fg1", "fg2", "fg3", "fg4", "fg5"]
REPS = ["1", "2", "3"]
SYNTHETIC = ["enriched", "demographics-only"]

# Post hoc and arbitrary. Reported so a reader can disagree with it explicitly rather
# than having "flattened" asserted without a definition.
PLATEAU_INCREMENT = 0.5   # mean codes added by the next focus group
CLASSIFICATION = "LEVEL2_COVERAGE_ACCUMULATION_FIXED_CODEBOOK_EXPLORATORY"


def _load():
    with (_RES / "thematic_code_presence_long.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    codes = sorted({r["subtheme_id"] for r in rows})
    # (condition, replicate, fg) -> set of subthemes; humans have a single replicate
    cell = defaultdict(set)
    docs = set()
    for r in rows:
        rep = r["canonical_replication_index"] if r["side"] == "synthetic" else "human"
        docs.add((r["condition"], rep, r["fg"]))
        if r["present"] == "True":
            cell[(r["condition"], rep, r["fg"])].add(r["subtheme_id"])
    return codes, cell, rows, docs


def _curve(sets_in_order):
    acc, out = set(), []
    for s in sets_in_order:
        acc |= s
        out.append(len(acc))
    return out


def _exhaustive(sets_by_fg):
    """Mean/min/max accumulation over all 120 orderings of the five focus groups."""
    perms = list(itertools.permutations(FGS))
    curves = [_curve([sets_by_fg[f] for f in p]) for p in perms]
    exact = [statistics.mean(c[i] for c in curves) for i in range(5)]
    return {
        "n_orderings": len(perms), "exhaustive": True,
        "mean_exact": exact,
        "mean": [round(v, 4) for v in exact],
        "min": [min(c[i] for c in curves) for i in range(5)],
        "max": [max(c[i] for c in curves) for i in range(5)],
        "observed_order": _curve([sets_by_fg[f] for f in FGS]),
        "marginal_mean_increment": [round(exact[i + 1] - exact[i], 4) for i in range(4)],
    }


def _plateau(inc):
    """First k after which every subsequent mean increment stays below the criterion."""
    for i in range(len(inc)):
        if all(x < PLATEAU_INCREMENT for x in inc[i:]):
            return i + 1
    return None


def _replicate_curve(sets_by_fg, codes):
    e = _exhaustive(sets_by_fg)
    total = len(set().union(*sets_by_fg.values())) if sets_by_fg else 0
    return {
        **e,
        "codes_per_fg": {f: len(sets_by_fg[f]) for f in FGS},
        "final_total_codes": total,
        "of_codebook": round(total / len(codes), 4),
        "codes_reached": sorted(set().union(*sets_by_fg.values())),
        "codes_not_reached": sorted(set(codes) - set().union(*sets_by_fg.values())),
        "plateau_k_at_increment_lt_0_5": _plateau(e["marginal_mean_increment"]),
    }


def build() -> dict:
    codes, cell, rows, docs = _load()
    n_codes = len(codes)

    # ---------------- accumulation curves, per study replicate --------------
    curves = {"human": {"human": _replicate_curve(
        {f: cell[("human", "human", f)] for f in FGS}, codes)}}
    for cond in SYNTHETIC:
        curves[cond] = {r: _replicate_curve(
            {f: cell[(cond, r, f)] for f in FGS}, codes) for r in REPS}

    # ---------------- summary across replicates (NOT as independent FGs) ----
    across = {}
    for cond in SYNTHETIC:
        totals = [curves[cond][r]["final_total_codes"] for r in REPS]
        per_k = [[curves[cond][r]["mean_exact"][k] for r in REPS] for k in range(5)]
        union15 = set().union(*[cell[(cond, r, f)] for r in REPS for f in FGS])
        across[cond] = {
            "n_study_replicates": 3,
            "final_total_codes_per_replicate": {r: totals[i] for i, r in enumerate(REPS)},
            "final_total_mean": round(statistics.mean(totals), 4),
            "final_total_min": min(totals), "final_total_max": max(totals),
            "final_total_range": f"{min(totals)}-{max(totals)}",
            "mean_curve_over_replicates": [round(statistics.mean(v), 4) for v in per_k],
            "min_curve_over_replicates": [round(min(v), 4) for v in per_k],
            "max_curve_over_replicates": [round(max(v), 4) for v in per_k],
            "replicates_are_not_independent_focus_groups": (
                "the three replicates are re-runs of the same five groups; they are "
                "summarised as a mean and a range and are never treated as extra FGs"),
            "CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS": {
                "value": len(union15),
                "of_codebook": round(len(union15) / n_codes, 4),
                "codes": sorted(union15),
                "definition": ("distinct subthemes observed anywhere in the 15 sessions "
                               "of this condition (5 FGs x 3 replicates)"),
                "is_NOT": ("the repertoire of a study replicate, and must never be "
                           "reported as one; no single replicate reached this many"),
            },
        }
    hum_total = curves["human"]["human"]["final_total_codes"]

    # ---------------- theme recurrence, per subtheme per replicate ----------
    recurrence = {}
    for code in codes:
        entry = {"human": sum(1 for f in FGS if code in cell[("human", "human", f)])}
        for cond in SYNTHETIC:
            for r in REPS:
                entry[f"{cond}_R{r}"] = sum(
                    1 for f in FGS if code in cell[(cond, r, f)])
        for cond in SYNTHETIC:
            vals = [entry[f"{cond}_R{r}"] for r in REPS]
            entry[f"{cond}_mean"] = round(statistics.mean(vals), 4)
            entry[f"{cond}_range"] = f"{min(vals)}-{max(vals)}"
        entry["never_observed_in_any_synthetic_session"] = all(
            entry[f"{c}_R{r}"] == 0 for c in SYNTHETIC for r in REPS)
        recurrence[code] = entry

    # ---------------- prevalence, code by code ------------------------------
    # No terciles: a 4/4/3 split cut tied codes apart by alphabetical order, which is an
    # artefact of sorting rather than of prevalence. Tie-preserving bands are offered
    # instead, and are exploratory.
    hum_prev = {c: recurrence[c]["human"] for c in codes}
    bands = defaultdict(list)
    for c in codes:
        bands[hum_prev[c]].append(c)
    prevalence = {
        "reported_code_by_code": True,
        "terciles_withdrawn": ("the previous 4/4/3 split separated codes with identical "
                               "human prevalence by alphabetical order"),
        "human_prevalence_per_code": hum_prev,
        "tie_preserving_bands": {str(k): sorted(v) for k, v in sorted(bands.items(),
                                                                     reverse=True)},
        "tie_preserving_bands_status": "EXPLORATORY — bands group exact ties only",
    }

    out = {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": CLASSIFICATION,
        "status": "EXPLORATORY",
        "temporal_transparency": (
            "The general indicators (saturation_curve, theme_recurrence_across_groups) "
            "appear in the original methodology, but these specific operationalisations "
            "— study-replicate accumulation, exhaustive ordering, the plateau criterion, "
            "tie-preserving bands — were finalised AFTER the main results were known. "
            "They are exploratory and were not pre-registered in this form."),
        "source": "results/thematic_code_presence_long.csv",
        "source_shape": f"{len(docs)} documents x {n_codes} subthemes = {len(rows)} rows",
        "documents": "5 human focus groups + 30 synthetic runs = 35",
        "no_api_calls": True, "no_new_human_coding": True,
        "codebook_size": n_codes,
        "codebook_is_fixed_a_priori": True,
        "unit_of_accumulation": (
            "study replicate x condition: one complete pass over FG1-FG5 at a single "
            "canonical_replication_index"),
        "estimand": "coverage accumulation against a FIXED codebook",
        "not_equivalent_to": ("Guest et al. (2016) / Hennink et al. (2019) code "
                              "saturation, which requires an inductively growing "
                              "codebook"),
        "meaning_saturation": "NOT COMPUTED — requires human interpretive judgement",
        "endpoint_interpretation": (
            "the last point of a curve is the total observed for that replicate. It is "
            "NOT evidence of a plateau and no plateau is claimed from it"),
        "plateau_criterion": {
            "rule": f"mean increment to every later focus group < {PLATEAU_INCREMENT} codes",
            "status": "POST HOC and arbitrary; reported so it can be disagreed with",
        },
        "order_bias_control": "exhaustive over all 120 orderings of the five FGs",
        "human_reference_total_codes": hum_total,
        "accumulation_curves": curves,
        "across_replicates": across,
        "theme_recurrence": recurrence,
        "prevalence": prevalence,
    }
    tmp = _OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _OUT)
    return out


def main() -> int:
    o = build()
    print(f"source: {o['source_shape']}\n")
    print("=== accumulation per STUDY REPLICATE (FG1..FG5, 120 orderings) ===")
    print(f"{'condition':20s}{'rep':5s}  mean cumulative curve                 final")
    h = o["accumulation_curves"]["human"]["human"]
    print(f"{'human':20s}{'-':5s}  {str(h['mean']):36s}  {h['final_total_codes']}/11")
    for cond in SYNTHETIC:
        for r in REPS:
            v = o["accumulation_curves"][cond][r]
            print(f"{cond:20s}R{r:4s}  {str(v['mean']):36s}  "
                  f"{v['final_total_codes']}/11")
    print("\n=== across replicates (mean and range; NOT independent FGs) ===")
    for cond, a in o["across_replicates"].items():
        m = a["CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS"]
        print(f"  {cond:20s} final total per replicate "
              f"{list(a['final_total_codes_per_replicate'].values())}  "
              f"mean {a['final_total_mean']}  range {a['final_total_range']}")
        print(f"  {'':20s} condition-wide max across 15 sessions: {m['value']}/11 "
              f"(NOT a replicate repertoire)")
    print("\n=== theme recurrence: FGs of 5 containing each subtheme ===")
    hdr = f"{'code':6s}{'human':>7s}" + "".join(f"{c[:4]+'R'+r:>8s}"
                                                for c in SYNTHETIC for r in REPS)
    print(hdr)
    for code, e in o["theme_recurrence"].items():
        row = f"{code:6s}{e['human']:>7d}"
        for c in SYNTHETIC:
            for r in REPS:
                row += f"{e[f'{c}_R{r}']:>8d}"
        print(row + ("   never in any synthetic session"
                     if e["never_observed_in_any_synthetic_session"] else ""))
    print("\nplateau criterion:", o["plateau_criterion"]["rule"],
          "|", o["plateau_criterion"]["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
