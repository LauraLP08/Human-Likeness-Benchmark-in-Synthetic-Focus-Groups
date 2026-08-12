"""
Stage-1 validation, gating, reconciliation and scoring.

    py scripts/absence_audit_stage1_score.py

Reads the raw responses unchanged and writes the Stage-1 artefacts. Touches no Gemini
result, no salience table, no heatmap and no workbook. No Gemini
absence is converted into a presence anywhere in this file.
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

import absence_audit_build as B      # noqa: E402
import absence_audit_rules as R      # noqa: E402
import absence_audit_stage1 as S1    # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/salience_absence_audit"
_SEALED = _OUT / "sealed"

RATE_IN, RATE_OUT = 2.50, 12.50


def _atomic(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def build() -> dict:
    cb = B.codebook()
    codes = sorted(cb)
    store = B.render_store(cb, codes)
    raw = json.loads((_OUT / "stage1_raw_responses.json").read_text(encoding="utf-8"))
    sealed_map = json.loads(
        (_SEALED / "sealed_document_mapping.json").read_text(encoding="utf-8"))["mapping"]
    sealed_ref = json.loads(
        (_SEALED / "calibration_reference_SEALED.json").read_text(encoding="utf-8"))
    grid = B.presence_grid()

    designated = {c["subtheme_id"]: c for c in sealed_ref["cases"]
                  if c["original_status"] == R.ORIGINAL_PRESENT}

    # ---------------------------------------------------- response validation
    validation, parsed = [], {}
    for e in raw["responses"]:
        bid, rep = e["blinded_document_id"], e["repetition_index"]
        v = {"custom_id": e["custom_id"], "blinded_document_id": bid,
             "repetition_index": rep, "result_type": e["result_type"],
             "stop_reason": e.get("stop_reason"), "problems": []}
        if e["result_type"] != "succeeded":
            v["problems"].append("result not succeeded")
        elif e.get("stop_reason") != "end_turn":
            v["problems"].append(f"stop_reason {e.get('stop_reason')}")
        else:
            try:
                j = json.loads(e["raw_text"])
            except Exception as ex:                       # noqa: BLE001
                v["problems"].append(f"invalid json: {ex}")
                j = None
            if j is not None:
                if j.get("document_id") != bid:
                    v["problems"].append(
                        f"document_id {j.get('document_id')} != {bid}")
                ass = j.get("assessments") or []
                ids = [a.get("code_id") for a in ass]
                if len(ass) != 11:
                    v["problems"].append(f"{len(ass)} assessments, expected 11")
                dup = [c for c, n in Counter(ids).items() if n > 1]
                if dup:
                    v["problems"].append(f"duplicated code_ids {dup}")
                missing = sorted(set(codes) - set(ids))
                if missing:
                    v["problems"].append(f"missing code_ids {missing}")
                extra = sorted(set(ids) - set(codes))
                if extra:
                    v["problems"].append(f"non-production code_ids {extra}")
                for a in ass:
                    if a.get("verdict") not in B.VERDICTS:
                        v["problems"].append(f"bad verdict {a.get('verdict')!r}")
                if not v["problems"]:
                    parsed[(bid, rep)] = {a["code_id"]: a for a in ass}
        v["valid"] = not v["problems"]
        validation.append(v)

    n_invalid = sum(1 for v in validation if not v["valid"])

    # ------------------------------------------------------- evidence gate
    gated, gate_failures = {}, Counter()
    for (bid, rep), by_code in parsed.items():
        turns = store[bid]["turns"]
        for code, a in by_code.items():
            g = R.evidence_gate(a, turns)
            gated[(bid, rep, code)] = {"assessment": a, "gate": g}
            if g["downgraded"]:
                gate_failures[g["gate"]] += 1

    # ------------------------------------------- reconcile the repetitions
    cells = []
    for bid in sorted({b for (b, _) in parsed}):
        doc_key = sealed_map[bid]["doc_key"]
        for code in codes:
            g1 = gated.get((bid, 1, code))
            g2 = gated.get((bid, 2, code))
            if g1 is None or g2 is None:
                continue
            rec = R.reconcile_repetitions([g1["gate"]["verdict_after_gate"],
                                           g2["gate"]["verdict_after_gate"]])
            spk = R.speaker_evidence(g1["gate"], g2["gate"])
            original_present = grid[(doc_key, code)]
            cells.append({
                "blinded_document_id": bid, "doc_key": doc_key, "subtheme_id": code,
                "original_status": (R.ORIGINAL_PRESENT if original_present
                                    else R.ORIGINAL_ABSENCE),
                "rep1_raw_verdict": g1["assessment"].get("verdict"),
                "rep2_raw_verdict": g2["assessment"].get("verdict"),
                "rep1_gate": g1["gate"]["gate"], "rep2_gate": g2["gate"]["gate"],
                "rep1_verdict_after_gate": g1["gate"]["verdict_after_gate"],
                "rep2_verdict_after_gate": g2["gate"]["verdict_after_gate"],
                "auditor_verdict": rec["verdict"], "repetitions_agree": rec["agreement"],
                "cross_model_outcome": R.cross_model_outcome(original_present,
                                                             rec["verdict"]),
                "union_speakers": spk["union"], "intersection_speakers":
                    spk["intersection"],
                "rep1_turn_id": g1["assessment"].get("turn_id"),
                "rep2_turn_id": g2["assessment"].get("turn_id"),
                "is_designated_control": (
                    designated.get(code, {}).get("doc_key") == doc_key
                    and original_present),
            })

    n_cells = len(cells)
    pos = [c for c in cells if c["original_status"] == R.ORIGINAL_PRESENT]
    neg = [c for c in cells if c["original_status"] == R.ORIGINAL_ABSENCE]
    n_detected = sum(1 for c in pos if c["auditor_verdict"] == R.AUD_EVIDENCE)
    n_agree = sum(1 for c in cells if c["repetitions_agree"])
    n_unres = sum(1 for c in cells if c["auditor_verdict"] == R.AUD_UNRESOLVED)

    gate = R.stage1_gate(n_detected, len(pos), n_agree, n_cells, n_unres)

    # ------------------------------------------------ subtheme eligibility
    control_verdicts = {}
    for c in cells:
        if c["is_designated_control"]:
            control_verdicts[c["subtheme_id"]] = c["auditor_verdict"]
    eligibility = R.subtheme_control_eligibility(control_verdicts, codes)
    if len(control_verdicts) != 11:
        raise RuntimeError(
            f"{len(control_verdicts)} designated controls resolved, expected 11")

    # -------------------------------------------------- FINAL absence labels
    #
    # cross_model_outcome is only the raw relation between the two codings. The label
    # that may actually be reported is produced by absence_label(), which applies the
    # global band AND the subtheme eligibility rule. Under band B nothing is corroborated,
    # however favourable the raw relation looks.
    for c in cells:
        if c["original_status"] == R.ORIGINAL_ABSENCE:
            lab = R.absence_label(gate["outcome"], c["subtheme_id"],
                                  c["auditor_verdict"], eligibility)
            c["final_absence_label"] = lab["label"]
            c["label_downgraded"] = lab["downgraded"]
            c["label_reason"] = lab["reason"]
        else:
            c["final_absence_label"] = ""
            c["label_downgraded"] = ""
            c["label_reason"] = ""
    final_counts = Counter(c["final_absence_label"] for c in cells
                           if c["original_status"] == R.ORIGINAL_ABSENCE)

    # ------------------------------------ adjacent-subtheme confusion signals
    #
    # The original coder's per-code quotations are not stored in any results artefact,
    # so a direct comparison against its evidence is impossible. What CAN be observed is
    # the auditor's own behaviour: one turn cited for several codes. Reuse within a
    # parent theme is the adjacent-code signal; reuse across parent themes is the
    # baseline it must be read against.
    reuse_within, reuse_across = [], []
    for bid in sorted({b for (b, _) in parsed}):
        for rep in (1, 2):
            by_turn = defaultdict(list)
            for code in codes:
                g = gated.get((bid, rep, code))
                if g and g["gate"]["gate"] == R.GATE_PASS:
                    by_turn[g["assessment"]["turn_id"]].append(code)
            for tid, cs in by_turn.items():
                if len(cs) < 2:
                    continue
                fams = {cb[c]["parent_theme"] for c in cs}
                row = {"blinded_document_id": bid, "repetition_index": rep,
                       "turn_id": tid, "codes": sorted(cs),
                       "parent_themes": sorted(fams)}
                (reuse_within if len(fams) == 1 else reuse_across).append(row)

    missed_with_sibling = []
    for c in pos:
        if c["auditor_verdict"] == R.AUD_EVIDENCE:
            continue
        fam = cb[c["subtheme_id"]]["parent_theme"]
        sibs = [d["subtheme_id"] for d in cells
                if d["blinded_document_id"] == c["blinded_document_id"]
                and d["subtheme_id"] != c["subtheme_id"]
                and cb[d["subtheme_id"]]["parent_theme"] == fam
                and d["auditor_verdict"] == R.AUD_EVIDENCE]
        if sibs:
            missed_with_sibling.append({
                "blinded_document_id": c["blinded_document_id"],
                "subtheme_id": c["subtheme_id"], "parent_theme": fam,
                "auditor_verdict": c["auditor_verdict"],
                "same_family_codes_detected_instead": sorted(sibs)})

    # ----------------------------------------------------- tokens and cost
    est = json.loads((_OUT / "batch_manifest.json").read_text(
        encoding="utf-8"))["stage_1_calibration"]
    m_in = raw["total_usage"]["input_tokens"]
    m_out = raw["total_usage"]["output_tokens"]
    cost = m_in / 1e6 * RATE_IN + m_out / 1e6 * RATE_OUT

    scores = R.calibration_scores(
        [{"original_status": c["original_status"],
          "auditor_verdict": c["auditor_verdict"]} for c in cells])

    return {
        "scored_utc": datetime.now(UTC).isoformat(),
        "stage": "STAGE1_CALIBRATION",
        "job_id": raw["job_id"],
        "stage_2_submitted": False,
        "gemini_results_modified": False,
        "any_absence_converted_to_presence": False,
        "validation": {"n_responses": len(validation), "n_invalid": n_invalid,
                       "rows": validation},
        "gate_failures_by_type": dict(gate_failures),
        "n_gate_failures": sum(gate_failures.values()),
        "cells": cells,
        "counts": {"n_cells": n_cells, "n_positive_controls": len(pos),
                   "n_absence_cells": len(neg), "n_detected": n_detected,
                   "n_agree": n_agree, "n_unresolved": n_unres},
        "gate": gate,
        "final_absence_labels": dict(final_counts),
        "final_label_note": ("cross_model_outcome is the raw relation between the two "
                             "codings; final_absence_label is what may be reported, "
                             "after the global band and the subtheme eligibility rule. "
                             f"Under {gate['outcome']} no cell may be labelled "
                             f"{R.ABSENCE_CORROBORATED}."),
        "n_absences_corroborated": final_counts.get(R.ABSENCE_CORROBORATED, 0),
        "calibration_scores": scores,
        "designated_controls": {
            s: {"subtheme_id": s, "doc_key": designated[s]["doc_key"],
                "blinded_document_id": designated[s]["blinded_document_id"],
                "auditor_verdict": control_verdicts.get(s),
                "status": eligibility[s]["status"],
                "eligible_for_corroboration":
                    eligibility[s]["eligible_for_corroboration"]}
            for s in codes},
        "eligibility": eligibility,
        "adjacent_confusion": {
            "limitation": ("the original coder's per-code quotations are not stored in "
                           "any results artefact, so no direct comparison against its "
                           "evidence is possible; these are signals from the auditor's "
                           "own responses only"),
            "same_turn_reused_within_a_parent_theme": reuse_within,
            "same_turn_reused_across_parent_themes": reuse_across,
            "n_within": len(reuse_within), "n_across": len(reuse_across),
            "missed_control_with_same_family_code_detected": missed_with_sibling,
            "n_missed_with_sibling": len(missed_with_sibling)},
        "tokens": {"estimated_input": est["estimated_input_tokens"],
                   "measured_input": m_in,
                   "estimated_output": est["estimated_output_tokens"],
                   "measured_output": m_out,
                   "input_error_pct": round(
                       (est["estimated_input_tokens"] - m_in) / m_in * 100, 1),
                   "output_error_pct": round(
                       (est["estimated_output_tokens"] - m_out) / m_out * 100, 1),
                   "estimated_cost_usd": est["calculated_list_batch_cost_usd"],
                   "calculated_list_batch_cost_usd": round(cost, 2),
                   "IMPORTANT": ("cost CALCULATED at published list Batch rates from "
                                 "measured token counts; not necessarily the amount "
                                 "charged")},
    }


def main() -> int:
    b = build()
    _atomic(_OUT / "stage1_calibration_results.json", b)

    with (_OUT / "stage1_cells_long.csv").open("w", encoding="utf-8", newline="") as f:
        cols = [k for k in b["cells"][0] if k not in ("union_speakers",
                                                      "intersection_speakers")]
        w = csv.DictWriter(f, fieldnames=cols + ["union_speakers",
                                                 "intersection_speakers"])
        w.writeheader()
        for c in b["cells"]:
            w.writerow({**{k: c[k] for k in cols},
                        "union_speakers": "|".join(c["union_speakers"]),
                        "intersection_speakers": "|".join(c["intersection_speakers"])})

    with (_OUT / "stage1_designated_controls.csv").open(
            "w", encoding="utf-8", newline="") as f:
        rows = list(b["designated_controls"].values())
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    g, c = b["gate"], b["counts"]
    print("=== STAGE 1 ===")
    print(f"  outcome            {g['outcome']}")
    for r in g["reasons"]:
        print(f"    reason           {r}")
    print(f"  detections         {c['n_detected']}/{c['n_positive_controls']}"
          f"   Wilson lo {g['detection_rate']['lower']}")
    print(f"  agreement          {c['n_agree']}/{c['n_cells']}"
          f"   Wilson lo {g['repetition_stability']['lower']}")
    print(f"  unresolved         {c['n_unresolved']}/{c['n_cells']}"
          f"   Wilson hi {g['unresolved_rate']['upper']}")
    print(f"  gate failures      {b['n_gate_failures']} {b['gate_failures_by_type']}")
    print(f"  invalid responses  {b['validation']['n_invalid']}")
    print("\n  designated controls:")
    for s, d in b["designated_controls"].items():
        mark = "OK " if d["eligible_for_corroboration"] else "NO "
        print(f"    {mark}{s:5s} {d['auditor_verdict']}")
    print(f"\n  raw relation over the 91 absence cells:")
    for k, v in sorted(Counter(c["cross_model_outcome"] for c in b["cells"]
                               if c["original_status"] == R.ORIGINAL_ABSENCE).items()):
        print(f"    {k:24s} {v}")
    print(f"  FINAL reportable labels (band + eligibility applied):")
    for k, v in sorted(b["final_absence_labels"].items()):
        print(f"    {k:32s} {v}")
    print(f"  absences corroborated: {b['n_absences_corroborated']}")

    elig = [s for s, e in b["eligibility"].items() if e["eligible_for_corroboration"]]
    print(f"\n  eligible subthemes   {len(elig)}/11: {' '.join(elig)}")
    print(f"  ineligible           "
          f"{' '.join(s for s in b['eligibility'] if s not in elig) or 'none'}")
    a = b["adjacent_confusion"]
    print(f"\n  adjacent signals: within-family turn reuse {a['n_within']}, "
          f"across-family {a['n_across']}, "
          f"missed control with sibling detected {a['n_missed_with_sibling']}")
    t = b["tokens"]
    print(f"\n  tokens in  est {t['estimated_input']:,} vs measured "
          f"{t['measured_input']:,} ({t['input_error_pct']:+}%)")
    print(f"  tokens out est {t['estimated_output']:,} vs measured "
          f"{t['measured_output']:,} ({t['output_error_pct']:+}%)")
    print(f"  cost  est ${t['estimated_cost_usd']} vs calculated "
          f"${t['calculated_list_batch_cost_usd']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
