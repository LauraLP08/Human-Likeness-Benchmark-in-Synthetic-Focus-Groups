"""
OCA-001 integration: read-only import, integrity verification, and three deductive
variants with full downstream recomputation.

    py scripts/oca_integration.py

NOTHING IS OVERWRITTEN. `evaluator_cache/` is not touched, the Gemini results CSVs are
not rewritten, and the ORIGINAL analysis stays primary. Both OCA variants are labelled
POST_RESULT_HUMAN_ADJUDICATED_SENSITIVITY.

The two verdicts are kept distinct, because the form asked one question and not the other:

  * A.1 removal        the reviewer's EXPLICIT verdict — DOES_NOT_SUPPORT_A1
  * A.3                a reviewer-PROPOSED alternative. The form never asked whether A.3
                       should be set present=true, so proposing it is not the same as
                       adjudicating it present, and it is never promoted automatically.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import salience_hierarchy as sh      # noqa: E402
import absence_audit_stage1 as S1    # noqa: E402

_PE = _ROOT / "analysis/production_evaluation"
_FORM = _PE / "open_coding_adjudication/OCA-001_adjudication.xlsx"
_SEALED = _PE / "gold_standard_sealed/open_coding_item_mapping.json"
_CODEBOOK = _PE / "gold_standard_sealed/codebook_reference.csv"
_OUT = _PE / "open_coding_adjudication"

ORIGINAL = "ORIGINAL_GEMINI"
REMOVE_A1 = "OCA_REMOVE_A1_ONLY"
REMOVE_A1_ADD_A3 = "OCA_REMOVE_A1_ADD_PROPOSED_A3"
VARIANTS = (ORIGINAL, REMOVE_A1, REMOVE_A1_ADD_A3)

CLASSIFICATION = "POST_RESULT_HUMAN_ADJUDICATED_SENSITIVITY"


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ------------------------------------------------------------ 1. import
def import_form() -> dict:
    """
    READ-ONLY import of the returned form. The workbook is opened, never written, and
    its hash is recorded. NO provenance is attached at this step — the mapping to
    FG4-DEMO-R01-A1 happens afterwards, in map_after_import().
    """
    import openpyxl
    wb = openpyxl.load_workbook(_FORM, data_only=True, read_only=True)
    ws = wb["Adjudication"]
    kv = {}
    for row in ws.iter_rows():
        cells = [c.value for c in row]
        if len(cells) >= 2 and cells[0] not in (None, ""):
            kv[str(cells[0]).strip()] = cells[1]
    wb.close()

    d = (kv.get("date (UTC)") or "")
    rec = {
        "form_item_id": str(kv.get("Item") or "").strip(),
        "verdict": str(kv.get("verdict") or "").strip(),
        "alternative_subtheme": str(kv.get("alternative subtheme (optional)")
                                    or "").strip(),
        "reasoning": str(kv.get("reasoning (required)") or "").strip(),
        "reviewer": str(kv.get("reviewer") or "").strip(),
        "date_utc": (d.isoformat() if hasattr(d, "isoformat") else str(d)).strip(),
        "workbook_sha256": _sha_file(_FORM),
        "workbook_bytes": _FORM.stat().st_size,
        "imported_utc": datetime.now(UTC).isoformat(),
        "import_mode": "READ_ONLY",
        "workbook_modified_by_import": False,
        "provenance_attached_at_import": False,
        "_cells": kv,
    }
    problems = []
    if rec["form_item_id"] != "OCA-001":
        problems.append(f"unexpected item id {rec['form_item_id']!r}")
    if rec["verdict"] not in ("SUPPORTS_A1", "DOES_NOT_SUPPORT_A1", "UNCERTAIN"):
        problems.append(f"verdict not an offered option: {rec['verdict']!r}")
    if not rec["reasoning"]:
        problems.append("reasoning is required and is empty")
    if not rec["reviewer"]:
        problems.append("reviewer is empty")
    rec["problems"] = problems
    rec["pass"] = not problems
    return rec


# --------------------------------------------- 2. integrity vs the sealed source
def verify_against_sealed(rec: dict) -> dict:
    """
    Confirms every immutable and blinded element in the returned form still matches the
    sealed source: the presented turn text (by sha256), the speaker labels, the cited
    flags, and the codebook definitions for A.1 and A.3.
    """
    sealed = json.loads(_SEALED.read_text(encoding="utf-8"))
    item = next(i for i in sealed["items"] if i["form_item_id"] == "OCA-001")
    kv = rec["_cells"]
    problems, checked = [], 0

    for t in item["turn_provenance"]:
        label = f"  {t['turn']} · {t['speaker_blind']}"
        cited_label = f"► {t['turn']} · {t['speaker_blind']}"
        got = kv.get(label.strip()) or kv.get(cited_label) or kv.get(label)
        if got is None:
            for k, v in kv.items():
                if t["turn"] in str(k):
                    got = v
                    break
        if got is None:
            problems.append(f"{t['turn']}: not present in the returned form")
            continue
        checked += 1
        if _sha(str(got)) != t["presented_sha256"]:
            problems.append(f"{t['turn']}: presented text differs from the sealed source")

    cb = {r["subtheme_id"]: r for r in
          csv.DictReader(_CODEBOOK.open(encoding="utf-8"))}
    for code, lab_key, def_key in (("A.1", "A.1 label", "A.1 definition"),
                                   ("A.3", "A.3 label", "A.3 definition")):
        checked += 2
        if str(kv.get(lab_key, "")).strip() != cb[code]["subtheme_label"].strip():
            problems.append(f"{code} label differs from the frozen codebook")
        if str(kv.get(def_key, "")).strip() != cb[code]["description"].strip():
            problems.append(f"{code} definition differs from the frozen codebook")

    n_cited = sum(1 for t in item["turn_provenance"] if t["cited_in_support_of_A1"])
    if n_cited != len(item["turns_cited"]):
        problems.append("cited-turn count differs from the sealed source")

    return {"n_elements_checked": checked, "problems": problems,
            "pass": not problems,
            "immutable_and_blinded_material_matches_sealed_source": not problems,
            "sealed_file": str(_SEALED.relative_to(_ROOT)),
            "sealed_utc": sealed["sealed_utc"]}


def map_after_import(rec: dict) -> dict:
    """Provenance is attached ONLY here, after the verdict has been imported."""
    sealed = json.loads(_SEALED.read_text(encoding="utf-8"))
    item = next(i for i in sealed["items"] if i["form_item_id"] == "OCA-001")
    return {"form_item_id": "OCA-001", "internal_id": item["internal_id"],
            "physical_run": item["physical_run"], "fg": item["fg"],
            "condition": item["condition"], "side": item["side"],
            "subtheme_under_review": item["subtheme_under_review"],
            "boundary_subtheme_shown": item["boundary_subtheme_shown"],
            "turns_shown": item["turns_shown"], "turns_cited": item["turns_cited"],
            "mapping_applied_after_import": True}


# ------------------------------------------------------- 3. three variants
def variant_keys(mapping: dict):
    cond, fg, rep = mapping["condition"], mapping["fg"], "1"
    return (cond, fg, rep, "A.1"), (cond, fg, rep, "A.3")


def apply_variant(P, R, mapping: dict, variant: str):
    """
    Returns modified copies. The source CSVs and evaluator_cache are never written.

    The proposed-A.3 reach is derived from the three turns the form cited (one per
    participant, 3 of 3). The form did not ask for reach, so this is an inference from
    the cited evidence and is labelled as such — not a measurement.
    """
    P, R = deepcopy(P), deepcopy(R)
    k_a1, k_a3 = variant_keys(mapping)
    notes = []
    if variant == ORIGINAL:
        return P, R, ["no change"]

    row = P[k_a1]
    row["present"] = "False"
    row["voiced_by_n"] = "0"
    R.pop(k_a1, None)
    notes.append("A.1 set present=False and its reach row removed "
                 "(explicit human verdict DOES_NOT_SUPPORT_A1)")

    if variant == REMOVE_A1_ADD_A3:
        cited = mapping["turns_cited"]
        n_part = 3
        P[k_a3]["present"] = "True"
        P[k_a3]["voiced_by_n"] = str(len(cited))
        R[k_a3] = {**{c: P[k_a3].get(c, "") for c in P[k_a3]},
                   "voiced_by_n": str(len(cited)), "participants_n": str(n_part),
                   "reach": str(len(cited) / n_part)}
        notes.append(f"A.3 set present=True with reach {len(cited)}/{n_part} derived "
                     f"from the {len(cited)} cited turns — a REVIEWER-PROPOSED "
                     "alternative, not an explicit presence adjudication")
    return P, R, notes


# --------------------------------------------------- 4. recomputation
def _prf(shared: int, syn_n: int, hum_n: int) -> dict:
    """
    THE FROZEN F1 RULE.

      * F1 is undefined ONLY when recall or precision is undefined, i.e. only when a
        denominator is empty.
      * If recall and precision are both measured and both equal 0, F1 = 0.0.
      * A complete mismatch between two NON-EMPTY code sets is a MEASURED ZERO, not
        missingness. Both sides asserted codes and none of them agreed; that is a real
        result, and calling it undefined would hide a total mismatch behind a blank.

    Empty denominators remain undefined and are never 0. Removing A.1 leaves this run
    asserting no verified code at all, so the precision denominator becomes 0. Reporting
    that as precision = 0 would claim the run was perfectly wrong when it made no claim
    to be wrong about.

    This function previously returned an undefined F1 whenever recall + precision == 0,
    which contradicted the frozen rule and the frozen source table, where
    tier1_f1_secondary is recorded as 0.0 for exactly those runs.
    """
    recall = None if hum_n == 0 else round(shared / hum_n, 4)
    precision = None if syn_n == 0 else round(shared / syn_n, 4)
    if recall is None or precision is None:
        which = "precision" if precision is None else "recall"
        f1, f1_reason = None, f"undefined: {which} has an empty denominator"
    elif recall == 0.0 and precision == 0.0:
        f1, f1_reason = 0.0, None          # measured zero: disjoint non-empty sets
    else:
        f1 = round(2 * recall * precision / (recall + precision), 4)
        f1_reason = None
    return {"shared_n": shared, "synthetic_present_n": syn_n, "human_present_n": hum_n,
            "recall": recall, "recall_undefined_reason":
                None if recall is not None else "human present set is empty",
            "precision": precision, "precision_undefined_reason":
                None if precision is not None else
                "synthetic asserted no verified code; denominator is 0",
            "f1_secondary": f1, "f1_undefined_reason": f1_reason}


def recompute(P, R, codes) -> dict:
    """Per-run present sets, recall/precision/F1 and reach, over all 30 runs."""
    runs = sorted({(k[0], k[1], k[2]) for k in P if k[2] != "human"})
    per_run = []
    for cond, fg, rep in runs:
        hum = {c for c in codes if P.get((cond, fg, "human", c), P.get(
            ("human", fg, "human", c), {})).get("present") == "True"}
        if not hum:
            hum = {c for c in codes
                   if any(P[k]["present"] == "True" for k in P
                          if k[1] == fg and k[2] == "human" and k[3] == c)}
        syn = {c for c in codes if P[(cond, fg, rep, c)]["present"] == "True"}
        shared = hum & syn
        m = _prf(len(shared), len(syn), len(hum))
        reach = {c: float(R[(cond, fg, rep, c)]["reach"])
                 for c in sorted(syn) if (cond, fg, rep, c) in R}
        per_run.append({"condition": cond, "fg": fg,
                        "canonical_replication_index": rep,
                        "human_present_set": sorted(hum),
                        "synthetic_present_set": sorted(syn),
                        "shared_set": sorted(shared), **m,
                        "reach": reach,
                        "mean_reach": (round(sum(reach.values()) / len(reach), 4)
                                       if reach else None)})
    return {"per_run": per_run}


def _mean(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 4) if v else None


def summarise(per_run) -> dict:
    """
    Every mean is reported WITH the number of defined values behind it. A mean over 2 of
    3 runs and a mean over 3 of 3 are different quantities, and printing the figure alone
    hides which one it is.
    """
    def n_def(rs, key):
        return sum(1 for r in rs if r[key] is not None)

    fg_level, cond_level = [], []
    by_fg = {}
    for r in per_run:
        by_fg.setdefault((r["condition"], r["fg"]), []).append(r)
    for (cond, fg), rs in sorted(by_fg.items()):
        fg_level.append({
            "condition": cond, "fg": fg, "n_runs": len(rs),
            "mean_recall": _mean(r["recall"] for r in rs),
            "n_recall_defined": n_def(rs, "recall"),
            "n_recall_undefined": len(rs) - n_def(rs, "recall"),
            "mean_precision": _mean(r["precision"] for r in rs),
            "n_precision_defined": n_def(rs, "precision"),
            "n_precision_undefined": len(rs) - n_def(rs, "precision"),
            "mean_f1_secondary": _mean(r["f1_secondary"] for r in rs),
            "n_f1_defined": n_def(rs, "f1_secondary"),
            "n_f1_undefined": len(rs) - n_def(rs, "f1_secondary"),
            "mean_synthetic_present_n": _mean(r["synthetic_present_n"] for r in rs),
            "zero_overlap_runs": sum(1 for r in rs if r["shared_n"] == 0),
            "denominator_note": "each mean is over its own n_*_defined, not over n_runs"})
    by_cond = {}
    for r in fg_level:
        by_cond.setdefault(r["condition"], []).append(r)
    for cond, rs in sorted(by_cond.items()):
        cond_level.append({
            "condition": cond, "n_focus_groups": len(rs),
            "mean_recall_over_fgs": _mean(r["mean_recall"] for r in rs),
            "n_fgs_with_defined_recall": n_def(rs, "mean_recall"),
            "mean_precision_over_fgs": _mean(r["mean_precision"] for r in rs),
            "n_fgs_with_defined_precision": n_def(rs, "mean_precision"),
            "n_precision_undefined_runs": sum(r["n_precision_undefined"] for r in rs),
            "mean_f1_secondary_over_fgs": _mean(r["mean_f1_secondary"] for r in rs),
            "n_fgs_with_defined_f1": n_def(rs, "mean_f1_secondary"),
            "n_f1_undefined_runs": sum(r["n_f1_undefined"] for r in rs),
            "unit": "focus group, n = 5; never 15 sessions",
            "denominator_note": ("means are over focus groups with a defined value; "
                                 "undefined RUN counts are reported separately")})
    return {"fg_level": fg_level, "condition_level": cond_level}


def zero_overlap_interpretation(per_run, variant) -> dict:
    rs = [r for r in per_run if r["condition"] == "demographics-only"
          and r["fg"] == "fg4"]
    detail = [{"canonical_replication_index": r["canonical_replication_index"],
               "synthetic_present_n": r["synthetic_present_n"],
               "shared_n": r["shared_n"], "recall": r["recall"],
               "precision": r["precision"],
               "precision_undefined_reason": r["precision_undefined_reason"]}
              for r in rs]
    asserts_nothing = [d for d in detail if d["synthetic_present_n"] == 0]
    if not asserts_nothing:
        reading = ("ZERO_OVERLAP_NOT_ZERO_CODING — codes were asserted; none overlap "
                   "the human FG4 set")
    elif len(asserts_nothing) == len(detail):
        reading = ("NO_VERIFIED_CODE_ASSERTED in every replicate — the original flag's "
                   "wording no longer applies to this cell")
    else:
        reading = (f"MIXED — {len(asserts_nothing)} of {len(detail)} replicates now "
                   "assert no verified code at all, so for those the original flag's "
                   "wording 'codes WERE asserted' no longer holds; the remainder still "
                   "show zero overlap with codes asserted")
    return {"variant": variant, "cell": "demographics-only / fg4", "runs": detail,
            "n_replicates_asserting_nothing": len(asserts_nothing),
            "interpretation": reading,
            "original_flag": "ZERO_OVERLAP_NOT_ZERO_CODING",
            "original_flag_file_modified": False}


def check_original_matches_source(per_run) -> dict:
    """
    ORIGINAL_GEMINI must reproduce the frozen per-run table EXACTLY — recall, precision
    and F1. If it does not, the variant machinery has changed the baseline it is supposed
    to leave alone, and no sensitivity built on it can be trusted.

    This is the check that would have caught the F1 defect: the frozen table records
    tier1_f1_secondary = 0.0 for the FG4 demographics-only runs, and the earlier
    implementation returned undefined.
    """
    src = {}
    for r in csv.DictReader((_PE / "results/per_run_metrics.csv").open(encoding="utf-8")):
        src[(r["condition"], r["fg"], r["canonical_replication_index"])] = r

    def num(x):
        return None if x in (None, "", "None", "nan") else round(float(x), 4)

    mismatches, checked = [], 0
    for r in per_run:
        k = (r["condition"], r["fg"], r["canonical_replication_index"])
        s = src.get(k)
        if s is None:
            mismatches.append({"run": k, "problem": "absent from the frozen table"})
            continue
        for ours, theirs in (("recall", "tier1_subtheme_recall"),
                             ("precision", "tier1_matched_theme_precision"),
                             ("f1_secondary", "tier1_f1_secondary")):
            checked += 1
            a, b = r[ours], num(s[theirs])
            if a != b:
                mismatches.append({"run": k, "metric": ours,
                                   "recomputed": a, "frozen_source": b})
    return {"n_values_checked": checked, "mismatches": mismatches,
            "pass": not mismatches,
            "source": "results/per_run_metrics.csv"}


def build() -> dict:
    rec = import_form()
    if not rec["pass"]:
        raise RuntimeError(f"import failed: {rec['problems']}")
    integrity = verify_against_sealed(rec)
    if not integrity["pass"]:
        raise RuntimeError(f"integrity failed: {integrity['problems']}")
    mapping = map_after_import(rec)

    codes, P0, R0 = sh.load()
    out = {}
    for v in VARIANTS:
        P, R, notes = apply_variant(P0, R0, mapping, v)
        comp = recompute(P, R, codes)
        out[v] = {"notes": notes, **comp, **summarise(comp["per_run"]),
                  "zero_overlap": zero_overlap_interpretation(comp["per_run"], v),
                  "status": ("PRIMARY" if v == ORIGINAL else CLASSIFICATION)}

    fidelity = check_original_matches_source(out[ORIGINAL]["per_run"])
    if not fidelity["pass"]:
        raise RuntimeError(f"ORIGINAL_GEMINI does not reproduce the frozen source: "
                           f"{fidelity['mismatches'][:5]}")

    target = (mapping["condition"], mapping["fg"], "1")
    focus = {v: next(r for r in out[v]["per_run"]
                     if (r["condition"], r["fg"], r["canonical_replication_index"])
                     == target) for v in VARIANTS}

    rec.pop("_cells", None)
    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": CLASSIFICATION,
        "primary_analysis": ORIGINAL,
        "evaluator_cache_modified": False,
        "gemini_results_csv_modified": False,
        "workbook_or_drafts_modified": False,
        "import": rec, "integrity": integrity, "mapping": mapping,
        "f1_rule": {
            "undefined_only_when": "recall or precision is undefined",
            "both_measured_and_zero": 0.0,
            "rationale": ("a complete mismatch between two non-empty code sets is a "
                          "MEASURED zero, not missingness"),
            "corrected_defect": ("an earlier implementation returned undefined whenever "
                                 "recall + precision == 0, contradicting this rule and "
                                 "the frozen source table")},
        "original_matches_frozen_source": fidelity,
        "verdict_distinction": {
            "explicit_human_verdict": {
                "subtheme": "A.1", "verdict": rec["verdict"],
                "effect": "A.1 set present=False",
                "warrant": "the form asked exactly this question"},
            "reviewer_proposed_alternative": {
                "subtheme": rec["alternative_subtheme"],
                "effect": "present=True ONLY in the third variant",
                "warrant": ("NONE from the form — the form did not ask whether A.3 "
                            "should be set present=true, so the proposal is not an "
                            "adjudication of presence and is never promoted "
                            "automatically"),
                "reach_is_inferred": True,
                "reach_basis": "the three cited turns, one per participant, 3 of 3"}},
        "variants": out, "focus_run": focus,
    }


def main() -> int:
    b = build()
    S1._atomic(_OUT / "oca_integration.json", b)

    rows = []
    for v in VARIANTS:
        for r in b["variants"][v]["per_run"]:
            rows.append({"variant": v, "status": b["variants"][v]["status"],
                         **{k: r[k] for k in ("condition", "fg",
                                              "canonical_replication_index",
                                              "shared_n", "synthetic_present_n",
                                              "human_present_n", "recall", "precision",
                                              "f1_secondary")},
                         "precision_undefined_reason":
                             r["precision_undefined_reason"] or "",
                         "f1_undefined_reason": r["f1_undefined_reason"] or "",
                         "synthetic_present_set": "|".join(r["synthetic_present_set"])})
    with (_OUT / "oca_variants_per_run.csv").open("w", encoding="utf-8",
                                                  newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    i, g = b["import"], b["integrity"]
    print("=== OCA-001 import (read-only) ===")
    print(f"  verdict               {i['verdict']}")
    print(f"  alternative subtheme  {i['alternative_subtheme']}")
    print(f"  reviewer / date       {i['reviewer']}  {i['date_utc']}")
    print(f"  workbook sha256       {i['workbook_sha256']}")
    print(f"  workbook modified     {i['workbook_modified_by_import']}")
    print(f"\n  integrity: {g['n_elements_checked']} immutable/blinded elements checked, "
          f"matches sealed source: "
          f"{g['immutable_and_blinded_material_matches_sealed_source']}")
    m = b["mapping"]
    print(f"  mapping (after import) {m['form_item_id']} -> {m['internal_id']} -> "
          f"{m['physical_run']}")

    print("\n=== the affected run, three variants ===")
    for v in VARIANTS:
        r = b["focus_run"][v]
        print(f"  {v}")
        print(f"    synthetic present set {r['synthetic_present_set'] or '(empty)'}   "
              f"shared {r['shared_n']}/{r['human_present_n']}")
        print(f"    recall {r['recall']}   precision "
              f"{r['precision'] if r['precision'] is not None else 'UNDEFINED'}"
              f"   F1 {r['f1_secondary'] if r['f1_secondary'] is not None else 'UNDEFINED'}")
        if r["precision_undefined_reason"]:
            print(f"      precision undefined: {r['precision_undefined_reason']}")
        print(f"    reach {r['reach'] or '(none)'}")

    print("\n=== FG4 demographics-only zero-overlap reading ===")
    for v in VARIANTS:
        z = b["variants"][v]["zero_overlap"]
        print(f"  {v}: {z['interpretation']}")

    print("\n=== condition-level (unit = focus group, n=5) ===")
    for v in VARIANTS:
        print(f"  {v}")
        for c in b["variants"][v]["condition_level"]:
            print(f"    {c['condition']:20s} "
                  f"recall {c['mean_recall_over_fgs']} "
                  f"(n={c['n_fgs_with_defined_recall']}/5)  "
                  f"precision {c['mean_precision_over_fgs']} "
                  f"(n={c['n_fgs_with_defined_precision']}/5)  "
                  f"F1 {c['mean_f1_secondary_over_fgs']} "
                  f"(n={c['n_fgs_with_defined_f1']}/5)  "
                  f"undefined runs: prec {c['n_precision_undefined_runs']}, "
                  f"F1 {c['n_f1_undefined_runs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
