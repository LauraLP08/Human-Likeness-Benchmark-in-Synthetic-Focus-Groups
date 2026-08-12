"""
Reconcile every headline figure against its source, then emit the provenance index.

READ ONLY. No LLM call, no workbook write. If a figure cannot be reconciled the build
raises rather than publishing a number that two files disagree about.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "analysis" / "production_evaluation"
_RES = _OUT / "results"
_Q3 = _OUT / "emergent_calibration_q3"
_TR = _OUT / "transportability_sample"


class Irreconcilable(RuntimeError):
    pass


def _j(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _csv(p: Path):
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# Artefacts that must not have changed since they were produced.
SEALED = {
    "Clustering_U01_U07.xlsx":
        (_OUT / "partial_emergent_clustering" / "Clustering_U01_U07.xlsx",
         "d5dd0c452287387182b8dadaa10ebefdab765b7c4aa2aab1648db313d720f3ab"),
    "Emergent_Matching_Q3_RESEARCHER_V2.xlsx":
        (_Q3 / "Emergent_Matching_Q3_RESEARCHER_V2.xlsx",
         "4113068f044f52d628dd7955f17629a6eabf58b53f5616cb9c6f21614d836a63"),
    "Transportability_Emergent_SingleCoder.xlsx":
        (_TR / "Transportability_Emergent_SingleCoder.xlsx",
         "c508cea736f558e070e0e424047ead1093f42782c9609af1fe52bef0488866dc"),
    "supplementary_human_reference.json":
        (_TR / "supplementary_human_reference.json",
         "076eb723b00c85479b9576ef00f99f79af9dd278b519a9b612feb46ed8b926a7"),
}


def verify_sealed() -> dict:
    out, bad = {}, []
    for name, (p, expected) in SEALED.items():
        got = _sha(p)
        out[name] = {"path": str(p.relative_to(_ROOT)), "sha256": got,
                     "matches_expected": got == expected}
        if got != expected:
            bad.append(name)
    if bad:
        raise Irreconcilable(f"sealed artefacts changed: {bad}")
    return out


def collect() -> dict:
    """Every headline figure, with the file it came from."""
    eff = {r["metric"]: r for r in _csv(_RES / "primary_effects_summary.csv")}
    byfg = _csv(_RES / "primary_effects_by_fg.csv")
    cond = {r["metric"]: r for r in _csv(_RES / "condition_comparison.csv")}
    d = _j(_Q3 / "matching_derivation_q3.json")
    b = _j(_Q3 / "bplus_evaluation_q3.json")
    a = _j(_Q3 / "cross_model_analysis_q3.json")
    q = _j(_Q3 / "cross_model_quote_audit_q3.json")
    ext = _j(_Q3 / "extraction_results_q3.json")
    ref = _j(_Q3 / "human_reference_q3.json")
    sup = _j(_TR / "supplementary_human_reference.json")
    job = _j(_Q3 / "cross_model_job_q3.json")
    xres = _j(_Q3 / "cross_model_results_q3.json")

    P = []      # provenance rows: (figure, value, source file, note)

    def add(fig, val, src, note=""):
        P.append({"figure": fig, "value": val, "source": src, "note": note})
        return val

    # --- 1. deductive, 30 runs -----------------------------------------
    ded = {}
    for m in ("recall", "precision", "reach", "f1_secondary"):
        ded[m] = {
            "mean_difference": float(eff[m]["mean_difference"]),
            "n_favouring_enriched": int(eff[m]["n_favouring_enriched"]),
            "n_favouring_demographics_only": int(eff[m]["n_favouring_demographics_only"]),
            "n_ties": int(eff[m]["n_ties"]),
            "exploratory_sign_test_p": float(eff[m]["exploratory_sign_test_p_two_sided"]),
            "minimum_attainable_p": float(eff[m]["minimum_attainable_p"]),
            "cannot_reach_p05": eff[m]["sign_test_cannot_reach_p05"] == "True",
        }
        add(f"deductive.{m}.mean_difference", ded[m]["mean_difference"],
            "results/primary_effects_summary.csv", "FG-level, n=5 pairs")

    # cross-check the same means in condition_comparison.csv
    pairs = {"recall": "tier1_subtheme_recall", "precision": "tier1_matched_theme_precision",
             "reach": "tier1_participant_reach"}
    for m, k in pairs.items():
        v1 = ded[m]["mean_difference"]
        v2 = float(cond[k]["mean_difference_enriched_minus_demo"])
        if abs(v1 - v2) > 0.0011:
            raise Irreconcilable(
                f"{m}: primary_effects_summary says {v1}, condition_comparison says {v2}")
        n1 = ded[m]["n_favouring_enriched"]
        n2 = int(cond[k]["n_fgs_favouring_enriched"])
        if n1 != n2:
            raise Irreconcilable(f"{m}: direction counts disagree {n1} vs {n2}")

    per_fg = [{"metric": r["metric"], "fg": r["fg"],
               "enriched_mean": float(r["enriched_mean"]),
               "demographics_only_mean": float(r["demographics_only_mean"]),
               "difference": float(r["difference_enriched_minus_demo"]),
               "direction": r["direction"],
               "enriched_within_cell_sd": float(r["enriched_within_cell_sd"]),
               "demographics_only_within_cell_sd": float(r["demographics_only_within_cell_sd"])}
              for r in byfg]
    # the per-FG differences must average to the reported mean
    for m in ("recall", "precision", "reach", "f1_secondary"):
        diffs = [r["difference"] for r in per_fg if r["metric"] == m]
        if len(diffs) != 5:
            raise Irreconcilable(f"{m}: {len(diffs)} FG rows, expected 5")
        if abs(sum(diffs) / 5 - ded[m]["mean_difference"]) > 0.0011:
            raise Irreconcilable(
                f"{m}: per-FG mean {sum(diffs)/5:.4f} != summary "
                f"{ded[m]['mean_difference']}")

    # --- 2. emergent Q3, human-anchored --------------------------------
    cov = b["metrics"]
    n_human = add("emergent.n_human_instances", d["n_human_instances"],
                  "matching_derivation_q3.json")
    n_mach = add("emergent.n_machine_themes", d["n_machine_themes"],
                 "matching_derivation_q3.json")
    if n_human != len(ref["union_reference"]):
        raise Irreconcilable("human instance count disagrees with the frozen reference")
    n_ext = sum(r["n_themes"] for r in ext["results"])
    if n_mach != n_ext:
        raise Irreconcilable(f"machine themes {n_mach} != extraction total {n_ext}")

    rec = cov["recall_vs_union_reference"]
    prec = cov["strict_precision_vs_union_reference"]
    add("emergent.recall", f"{rec['numerator_matched_human_instances']}/"
        f"{rec['denominator_human_instances']} = {rec['value']:.4f}",
        "bplus_evaluation_q3.json")
    add("emergent.strict_precision",
        f"{prec['numerator_machine_themes_linked']}/"
        f"{prec['denominator_machine_themes']} = {prec['value']:.4f}",
        "bplus_evaluation_q3.json")

    n_quotes = sum(len(t["evidence"]) for r in ext["results"] for t in r["themes"])
    add("emergent.literal_evidence_quotations", n_quotes,
        "extraction_results_q3.json", "counted from source, not copied")
    if n_quotes != 58:
        raise Irreconcilable(f"quotation count is {n_quotes}, expected 58")

    # --- 3. cross-model audit ------------------------------------------
    cal = a["judge_calibration"]
    aud = a["cross_model_audit"]
    if xres["n_results"] != 76 or job["n_requests"] != 76:
        raise Irreconcilable("cross-model request/result counts are not 76")
    if aud["n_corroborated"] + aud["n_unresolved"] != aud["n"]:
        raise Irreconcilable("corroborated + unresolved != total")
    add("crossmodel.corroborated", f"{aud['n_corroborated']}/{aud['n']}",
        "cross_model_analysis_q3.json")
    add("crossmodel.exact_agreement", cal["exact_agreement_on_decided"],
        "cross_model_analysis_q3.json", f"{cal['n_agree']}/{cal['n_decided']} stable cases")
    add("crossmodel.instability_rate", cal["instability_rate"],
        "cross_model_analysis_q3.json", f"{cal['n_unstable']}/{cal['n_calibration_cases']}")
    add("crossmodel.non_verbatim_quotes",
        f"{q['n_non_verbatim']}/{q['n_quotations']}", "cross_model_quote_audit_q3.json")

    # --- 4. supplementary transportability -----------------------------
    add("transportability.n_units", sup["n_units"], "supplementary_human_reference.json")
    add("transportability.n_themes", sup["n_themes"], "supplementary_human_reference.json")
    if sup["n_themes"] != sum(v["n_human_themes"]
                              for v in sup["denominators_per_unit"].values()):
        raise Irreconcilable("supplementary theme count disagrees with its denominators")

    # --- 5. cost --------------------------------------------------------
    cost = q["actual_cost"]
    recomputed = round(cost["actual_input_tokens"] / 1e6 * cost["batch_input_per_mtok"]
                       + cost["actual_output_tokens"] / 1e6
                       * cost["batch_output_per_mtok"], 2)
    if abs(recomputed - cost["actual_batch_usd_at_list_rate"]) > 0.005:
        raise Irreconcilable(f"cost recomputes to {recomputed}, file says "
                             f"{cost['actual_batch_usd_at_list_rate']}")
    add("cost.actual_list_batch_usd", cost["actual_batch_usd_at_list_rate"],
        "cross_model_quote_audit_q3.json", "recomputed from token counts")

    return {"deductive": ded, "deductive_per_fg": per_fg,
            "emergent": {"n_human_instances": n_human, "n_machine_themes": n_mach,
                         "recall": rec, "strict_precision": prec,
                         "literal_evidence_quotations": n_quotes,
                         "taxonomy": d["unconfirmed_theme_taxonomy"],
                         "uncertainty": cov["uncertainty_rate_human_rows"]},
            "crossmodel": {"calibration": cal, "audit": aud, "quotes": q},
            "transportability": {"n_units": sup["n_units"], "n_themes": sup["n_themes"],
                                 "per_unit": sup["denominators_per_unit"],
                                 "consolidation": sup["consolidation_decision"],
                                 "limitations": sup["limitations"]},
            "cost": cost,
            "provenance": P}


def build() -> dict:
    sealed = verify_sealed()
    c = collect()
    return {"built_utc": datetime.now(UTC).isoformat(),
            "sealed_artefacts": sealed,
            "reconciliation": "ALL FIGURES RECONCILED",
            **c}


def main() -> int:
    out = build()
    dst = _Q3 / "final_integration_reconciliation.json"
    tmp = dst.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str),
                       encoding="utf-8")
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()
    print("sealed artefacts verified :", all(v["matches_expected"]
                                             for v in out["sealed_artefacts"].values()))
    print("figures reconciled        :", len(out["provenance"]))
    print("reconciliation            :", out["reconciliation"])
    for p in out["provenance"]:
        print(f"   {p['figure']:44s} {str(p['value'])[:26]:26s} <- {p['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
