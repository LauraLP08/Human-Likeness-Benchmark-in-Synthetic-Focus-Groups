"""
Full-corpus reconciliation of the blinded absence audit, and the two sensitivity outputs.

    py scripts/absence_audit_final.py

Reconciles all 35 documents and all 385 cells from the Stage-1 and Stage-2 raw responses,
reports the complete 260-cell absence audit, and computes both sensitivity outputs.

BAND B — PROCEED_DETECTION_ONLY. ABSENCE_CORROBORATED is forbidden globally, regardless
of subtheme control eligibility.

The Gemini coding is not modified. The final heatmap and workbook are
not touched. ORIGINAL and LOWER remain the primary thematic-salience result.
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

import absence_audit_build as B      # noqa: E402
import absence_audit_rules as R      # noqa: E402
import absence_audit_stage1 as S1    # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/salience_absence_audit"
_SEALED = _OUT / "sealed"
_RES = _ROOT / "analysis/production_evaluation/results"
_FINAL = _ROOT / "analysis/production_evaluation/final"

BAND = R.GATE_B
RATE_IN, RATE_OUT = 2.50, 12.50


def band_b_label(auditor_verdict: str) -> dict:
    """
    The frozen Band-B mapping. ABSENCE_CORROBORATED is unreachable from this function by
    construction — not filtered out afterwards.
    """
    if auditor_verdict == R.AUD_EVIDENCE:
        return {"label": R.ABSENCE_CONTESTED,
                "reason": "gate-passed evidence in both repetitions"}
    if auditor_verdict == R.AUD_NONE:
        return {"label": R.AUD_NONE,
                "reason": f"repeated non-detection; corroboration forbidden under {BAND}"}
    return {"label": R.ABSENCE_UNRESOLVED,
            "reason": "repetitions disagreed or were undecided"}


def build() -> dict:
    cb = B.codebook()
    codes = sorted(cb)
    store = B.render_store(cb, codes)
    grid = B.presence_grid()
    sealed_map = json.loads(
        (_SEALED / "sealed_document_mapping.json").read_text(encoding="utf-8"))["mapping"]

    raws = [json.loads((_OUT / f).read_text(encoding="utf-8"))
            for f in ("stage1_raw_responses.json", "stage2_raw_responses.json")]

    # ------------------------------------------------- parse and validate
    parsed, validation = {}, []
    for raw in raws:
        for e in raw["responses"]:
            bid, rep = e["blinded_document_id"], e["repetition_index"]
            probs = []
            if e["result_type"] != "succeeded":
                probs.append("not succeeded")
            elif e.get("stop_reason") != "end_turn":
                probs.append(f"stop_reason {e.get('stop_reason')}")
            else:
                j = json.loads(e["raw_text"])
                if j.get("document_id") != bid:
                    probs.append("document_id mismatch")
                ass = j.get("assessments") or []
                ids = [a.get("code_id") for a in ass]
                if len(ass) != 11:
                    probs.append(f"{len(ass)} assessments")
                if sorted(set(ids)) != codes:
                    probs.append("code ids differ from production")
                if len(set(ids)) != len(ids):
                    probs.append("duplicated code ids")
                if not probs:
                    parsed[(bid, rep)] = {a["code_id"]: a for a in ass}
            validation.append({"stage": raw["stage"], "custom_id": e["custom_id"],
                               "blinded_document_id": bid, "repetition_index": rep,
                               "valid": not probs, "problems": probs})

    n_invalid = sum(1 for v in validation if not v["valid"])
    if n_invalid:
        raise RuntimeError(f"{n_invalid} invalid responses; refusing to score")

    # ------------------------------- gate, reconcile, label — all 385 cells
    cells, gate_failures = [], Counter()
    for bid in sorted({b for (b, _) in parsed}):
        dk = sealed_map[bid]["doc_key"]
        turns = store[bid]["turns"]
        for code in codes:
            g1 = R.evidence_gate(parsed[(bid, 1)][code], turns)
            g2 = R.evidence_gate(parsed[(bid, 2)][code], turns)
            for g in (g1, g2):
                if g["downgraded"]:
                    gate_failures[g["gate"]] += 1
            rec = R.reconcile_repetitions([g1["verdict_after_gate"],
                                           g2["verdict_after_gate"]])
            spk = R.speaker_evidence(g1, g2)
            original_present = grid[(dk, code)]
            row = {"blinded_document_id": bid, "doc_key": dk, "subtheme_id": code,
                   "side": sealed_map[bid]["side"],
                   "condition": sealed_map[bid]["condition"],
                   "fg": sealed_map[bid]["fg"],
                   "canonical_replication_index":
                       sealed_map[bid]["canonical_replication_index"],
                   "original_status": (R.ORIGINAL_PRESENT if original_present
                                       else R.ORIGINAL_ABSENCE),
                   "rep1_verdict_after_gate": g1["verdict_after_gate"],
                   "rep2_verdict_after_gate": g2["verdict_after_gate"],
                   "rep1_gate": g1["gate"], "rep2_gate": g2["gate"],
                   "auditor_verdict": rec["verdict"],
                   "repetitions_agree": rec["agreement"],
                   "union_speakers": spk["union"],
                   "intersection_speakers": spk["intersection"]}
            if original_present:
                row["final_label"] = ""
                row["label_reason"] = "originally-present cell; concurrence control"
                row["control_outcome"] = R.cross_model_outcome(True, rec["verdict"])
            else:
                lab = band_b_label(rec["verdict"])
                row["final_label"] = lab["label"]
                row["label_reason"] = lab["reason"]
                row["control_outcome"] = ""
            cells.append(row)

    absences = [c for c in cells if c["original_status"] == R.ORIGINAL_ABSENCE]
    controls = [c for c in cells if c["original_status"] == R.ORIGINAL_PRESENT]
    final_counts = Counter(c["final_label"] for c in absences)
    if final_counts.get(R.ABSENCE_CORROBORATED):
        raise RuntimeError("ABSENCE_CORROBORATED emitted under band B")

    contested = [c for c in absences if c["final_label"] == R.ABSENCE_CONTESTED]

    # --------------------------------------- sensitivity 1: breadth bounds
    reach = {}
    for r in csv.DictReader((_RES / "thematic_reach_long.csv").open(encoding="utf-8")):
        k = f"human::{r['fg']}" if r["side"] == "human" else r["physical_run"]
        reach[k] = int(r["participants_n"])
    participants = {c["doc_key"]: reach.get(c["doc_key"],
                                            store[c["blinded_document_id"]]
                                            ["n_participants"])
                    for c in cells}
    breadth = R.participant_breadth_bounds(
        [{"doc_key": c["doc_key"], "subtheme_id": c["subtheme_id"],
          "union_speakers": c["union_speakers"],
          "intersection_speakers": c["intersection_speakers"]} for c in contested],
        participants)

    # ----------------------------------- sensitivity 2: recurrence ORIGINAL vs flipped
    pres_rows = []
    for r in csv.DictReader(
            (_RES / "thematic_code_presence_long.csv").open(encoding="utf-8")):
        k = f"human::{r['fg']}" if r["side"] == "human" else r["physical_run"]
        pres_rows.append({"condition": r["condition"],
                          "canonical_replication_index":
                              r["canonical_replication_index"] or None,
                          "fg": r["fg"], "subtheme_id": r["subtheme_id"],
                          "doc_key": k,
                          "present": r["present"] == "True"
                          and r["quote_verified"] == "True"})
    recurrence = R.across_group_recurrence_sensitivity(
        pres_rows, {(c["doc_key"], c["subtheme_id"]) for c in contested})

    # --------------------------- exactly which salience cells and tau-b would change
    import salience_hierarchy as sh
    base = sh.build()
    affected_docs = {c["doc_key"] for c in contested}
    affected_runs = {d for d in affected_docs if not d.startswith("human::")}
    affected_human = {d for d in affected_docs if d.startswith("human::")}

    changed_cells = []
    for c in contested:
        dk = c["doc_key"]
        changed_cells.append({
            "doc_key": dk, "subtheme_id": c["subtheme_id"],
            "side": c["side"], "condition": c["condition"], "fg": c["fg"],
            "canonical_replication_index": c["canonical_replication_index"],
            "LOWER_reach": 0.0,
            "MID_reach": round(1 / participants[dk], 4),
            "UPPER_reach": round(len(c["union_speakers"]) / participants[dk], 4),
            "n_participants": participants[dk],
            "union_speakers": c["union_speakers"],
            "intersection_speakers": c["intersection_speakers"]})

    # `per_run` carries no physical_run column, so the synthetic side must be joined
    # through (condition, fg, replication index) from the frozen inputs. Reading a
    # missing key would have silently reported human-side effects only.
    run_of = {(d["condition"], d["fg"], str(d["canonical_replication_index"])):
              d["physical_run"] for d in B.documents() if d["side"] == "synthetic"}
    if len(run_of) != 30:
        raise RuntimeError(f"{len(run_of)} synthetic runs joined, expected 30")

    tau_rows = []
    for r in base["per_run"]:
        key = (r["condition"], r["fg"], str(r["canonical_replication_index"]))
        run = run_of.get(key)
        if run is None:
            raise RuntimeError(f"no physical_run for {key}")
        hkey = f"human::{r['fg']}"
        syn_codes = sorted({c["subtheme_id"] for c in contested
                            if c["doc_key"] == run})
        hum_codes = sorted({c["subtheme_id"] for c in contested
                            if c["doc_key"] == hkey})
        if syn_codes or hum_codes:
            tau_rows.append({
                "fg": r["fg"], "condition": r["condition"],
                "canonical_replication_index": r["canonical_replication_index"],
                "physical_run": run,
                "primary_kendall_tau_b_ORIGINAL_LOWER": r["kendall_tau_b"],
                "undefined_reason": r["undefined_reason"],
                "synthetic_side_contested_codes": syn_codes,
                "human_side_contested_codes": hum_codes,
                "human_universe_would_grow": bool(hum_codes),
                "would_change_under_MID_or_UPPER": True})

    est = json.loads((_OUT / "batch_manifest.json").read_text(encoding="utf-8"))
    m_in = sum(r["total_usage"]["input_tokens"] for r in raws)
    m_out = sum(r["total_usage"]["output_tokens"] for r in raws)
    s2 = json.loads((_OUT / "stage2_raw_responses.json").read_text(encoding="utf-8"))
    s1 = json.loads((_OUT / "stage1_raw_responses.json").read_text(encoding="utf-8"))

    def money(i, o):
        return round(i / 1e6 * RATE_IN + o / 1e6 * RATE_OUT, 2)

    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": "BLINDED_CROSS_MODEL_ABSENCE_AUDIT_COMPLETE",
        "band": BAND,
        "corroboration_forbidden_globally": True,
        "gemini_coding_modified": False,
        "any_absence_converted_to_presence": False,
        "heatmap_workbook_drafts_updated": False,
        "primary_result": "ORIGINAL / LOWER, unchanged",
        "jobs": {"stage1": s1["job_id"], "stage2": s2["job_id"]},
        "coverage": {"n_documents": len({c["blinded_document_id"] for c in cells}),
                     "n_cells": len(cells), "n_absences": len(absences),
                     "n_controls": len(controls),
                     "n_responses_validated": len(validation),
                     "n_invalid": n_invalid},
        "gate_failures_by_type": dict(gate_failures),
        "n_gate_failures": sum(gate_failures.values()),
        "absence_audit_260": dict(final_counts),
        "n_absences_corroborated": final_counts.get(R.ABSENCE_CORROBORATED, 0),
        "control_concurrence_125": dict(Counter(c["control_outcome"]
                                                for c in controls)),
        "agreement_all_cells": sum(1 for c in cells if c["repetitions_agree"]),
        "participant_breadth_bounds": {k: v for k, v in breadth.items()
                                       if k != "per_document"},
        "across_group_recurrence_sensitivity": recurrence,
        "salience_cells_that_would_change": changed_cells,
        "n_salience_cells_that_would_change": len(changed_cells),
        "kendall_tau_b_values_that_would_change": tau_rows,
        "n_kendall_tau_b_affected": len(tau_rows),
        "n_kendall_tau_b_unaffected": 30 - len(tau_rows),
        "contested_on_human_documents": sorted(
            {(c["doc_key"], c["subtheme_id"]) for c in contested
             if c["doc_key"].startswith("human::")}),
        "tokens": {
            "estimated_total_input": est["total_corpus"]["estimated_input_tokens"],
            "estimated_total_output": est["total_corpus"]["estimated_output_tokens"],
            "estimated_cost_usd": est["total_corpus"]["calculated_list_batch_cost_usd"],
            "measured_stage1_input": s1["total_usage"]["input_tokens"],
            "measured_stage1_output": s1["total_usage"]["output_tokens"],
            "measured_stage2_input": s2["total_usage"]["input_tokens"],
            "measured_stage2_output": s2["total_usage"]["output_tokens"],
            "measured_total_input": m_in, "measured_total_output": m_out,
            "calculated_stage1_cost_usd": money(s1["total_usage"]["input_tokens"],
                                                s1["total_usage"]["output_tokens"]),
            "calculated_stage2_cost_usd": money(s2["total_usage"]["input_tokens"],
                                                s2["total_usage"]["output_tokens"]),
            "calculated_total_cost_usd": money(m_in, m_out),
            "IMPORTANT": ("measured token counts and a cost CALCULATED at published list "
                          "Batch rates; reported separately from the pre-run estimates "
                          "and not necessarily the amount charged")},
        "_cells": cells,
    }


def main() -> int:
    b = build()
    cells = b.pop("_cells")
    S1._atomic(_OUT / "absence_audit_complete.json", b)

    with (_OUT / "absence_adjudication_260.csv").open(
            "w", encoding="utf-8", newline="") as f:
        rows = [{**{k: v for k, v in c.items()
                    if k not in ("union_speakers", "intersection_speakers")},
                 "union_speakers": "|".join(c["union_speakers"]),
                 "intersection_speakers": "|".join(c["intersection_speakers"])}
                for c in cells if c["original_status"] == R.ORIGINAL_ABSENCE]
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    with (_OUT / "audit_results_long_385.csv").open(
            "w", encoding="utf-8", newline="") as f:
        rows = [{**{k: v for k, v in c.items()
                    if k not in ("union_speakers", "intersection_speakers")},
                 "union_speakers": "|".join(c["union_speakers"]),
                 "intersection_speakers": "|".join(c["intersection_speakers"])}
                for c in cells]
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    if b["salience_cells_that_would_change"]:
        with (_OUT / "participant_breadth_bounds.csv").open(
                "w", encoding="utf-8", newline="") as f:
            rows = [{**r, "union_speakers": "|".join(r["union_speakers"]),
                     "intersection_speakers": "|".join(r["intersection_speakers"])}
                    for r in b["salience_cells_that_would_change"]]
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    rec = b["across_group_recurrence_sensitivity"]
    with (_OUT / "across_group_recurrence_sensitivity.csv").open(
            "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rec["rows"][0]))
        w.writeheader()
        w.writerows(rec["rows"])

    c = b["coverage"]
    print("=== COMPLETE AUDIT ===")
    print(f"  documents {c['n_documents']}  cells {c['n_cells']}  "
          f"absences {c['n_absences']}  controls {c['n_controls']}  "
          f"invalid {c['n_invalid']}")
    print(f"  band {b['band']}   corroboration forbidden globally: "
          f"{b['corroboration_forbidden_globally']}")
    print("\n  the 260-cell absence audit:")
    for k, v in sorted(b["absence_audit_260"].items(), key=lambda x: -x[1]):
        print(f"    {k:34s} {v}")
    print(f"    ABSENCE_CORROBORATED               "
          f"{b['n_absences_corroborated']}  (forbidden)")
    print("\n  concurrence control on the 125 originally-present cells:")
    for k, v in sorted(b["control_concurrence_125"].items(), key=lambda x: -x[1]):
        print(f"    {k:34s} {v}")
    print(f"\n  gate failures {b['n_gate_failures']} {b['gate_failures_by_type']}")
    print(f"  repetition agreement {b['agreement_all_cells']}/385")

    pb = b["participant_breadth_bounds"]
    print(f"\n  participant_breadth_bounds: primary {pb['primary']}, "
          f"contested cells {pb['n_contested_cells']}")
    print(f"  salience cells that would change: "
          f"{b['n_salience_cells_that_would_change']}")
    for r in b["salience_cells_that_would_change"]:
        print(f"    {r['doc_key']:32s} {r['subtheme_id']:4s} n={r['n_participants']}  "
              f"LOWER {r['LOWER_reach']}  MID {r['MID_reach']}  UPPER {r['UPPER_reach']}")
    print(f"\n  across_group_recurrence_sensitivity: primary {rec['primary']}, "
          f"rows changed {rec['n_changed']}")
    for r in rec["rows"]:
        if r["delta"]:
            print(f"    {r['condition']:20s} R{r['canonical_replication_index']} "
                  f"{r['subtheme_id']:4s} {r['n_fgs_original']} -> "
                  f"{r['n_fgs_contested_as_present']}")
    print(f"\n  Kendall tau-b values that would change: "
          f"{b['n_kendall_tau_b_affected']}")
    for r in b["kendall_tau_b_values_that_would_change"]:
        tb = r["primary_kendall_tau_b_ORIGINAL_LOWER"]
        print(f"    {r['fg']} {r['condition']:20s} R{r['canonical_replication_index']}  "
              f"tau-b {tb if tb is not None else 'undefined'}"
              f"   syn {r['synthetic_side_contested_codes'] or '-'}"
              f"   hum {r['human_side_contested_codes'] or '-'}")

    t = b["tokens"]
    print(f"\n=== tokens: estimate vs measured, reported separately ===")
    print(f"  ESTIMATED  in {t['estimated_total_input']:>9,}  "
          f"out {t['estimated_total_output']:>8,}  ${t['estimated_cost_usd']}")
    print(f"  MEASURED   in {t['measured_total_input']:>9,}  "
          f"out {t['measured_total_output']:>8,}  "
          f"${t['calculated_total_cost_usd']}")
    print(f"    stage 1  in {t['measured_stage1_input']:>9,}  "
          f"out {t['measured_stage1_output']:>8,}  "
          f"${t['calculated_stage1_cost_usd']}")
    print(f"    stage 2  in {t['measured_stage2_input']:>9,}  "
          f"out {t['measured_stage2_output']:>8,}  "
          f"${t['calculated_stage2_cost_usd']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
