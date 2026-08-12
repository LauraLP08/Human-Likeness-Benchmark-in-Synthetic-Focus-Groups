"""
Regression tests for the OCA F1 defect and the OCA integration.

THE DEFECT: `_prf` returned an undefined F1 whenever recall + precision == 0, which
contradicted the frozen rule and the frozen source table (tier1_f1_secondary = 0.0 for
exactly those runs). A complete mismatch between two non-empty code sets is a MEASURED
zero, not missingness.

Offline; no API call. Nothing here writes to any artefact.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import oca_integration as O          # noqa: E402

_PE = _ROOT / "analysis/production_evaluation"
_OUT = _PE / "open_coding_adjudication"
_AUD = _PE / "salience_absence_audit"


@pytest.fixture(scope="module")
def b():
    return json.loads((_OUT / "oca_integration.json").read_text(encoding="utf-8"))


# =====================================================================
# 1. the frozen disjoint-non-empty example -> F1 = 0
# =====================================================================
def test_disjoint_non_empty_sets_give_f1_zero():
    """FG4 demographics-only run01 under ORIGINAL_GEMINI: {A.1} vs 6 human codes."""
    m = O._prf(shared=0, syn_n=1, hum_n=6)
    assert m["recall"] == 0.0
    assert m["precision"] == 0.0
    assert m["f1_secondary"] == 0.0, "a measured zero must not be reported as undefined"
    assert m["f1_undefined_reason"] is None


def test_the_proposed_a3_variant_also_gives_f1_zero():
    m = O._prf(shared=0, syn_n=1, hum_n=6)
    assert (m["recall"], m["precision"], m["f1_secondary"]) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("syn_n,hum_n", [(1, 6), (3, 3), (11, 11), (1, 1)])
def test_any_disjoint_non_empty_pair_gives_f1_zero(syn_n, hum_n):
    m = O._prf(shared=0, syn_n=syn_n, hum_n=hum_n)
    assert m["f1_secondary"] == 0.0, (syn_n, hum_n)


# =====================================================================
# 2. F1 undefined ONLY when a component is undefined
# =====================================================================
def test_f1_undefined_only_when_a_component_is_undefined():
    empty_syn = O._prf(shared=0, syn_n=0, hum_n=6)
    assert empty_syn["precision"] is None
    assert empty_syn["f1_secondary"] is None
    assert "precision" in empty_syn["f1_undefined_reason"]

    empty_hum = O._prf(shared=0, syn_n=3, hum_n=0)
    assert empty_hum["recall"] is None
    assert empty_hum["f1_secondary"] is None
    assert "recall" in empty_hum["f1_undefined_reason"]

    both_empty = O._prf(shared=0, syn_n=0, hum_n=0)
    assert both_empty["f1_secondary"] is None


def test_every_defined_pair_yields_a_defined_f1():
    """Exhaustive over small sets: if both components are numbers, F1 is a number."""
    for hum_n in range(1, 8):
        for syn_n in range(1, 8):
            for shared in range(0, min(hum_n, syn_n) + 1):
                m = O._prf(shared, syn_n, hum_n)
                assert m["recall"] is not None and m["precision"] is not None
                assert m["f1_secondary"] is not None, (shared, syn_n, hum_n)
                assert m["f1_undefined_reason"] is None


def test_f1_matches_the_harmonic_mean_when_positive():
    m = O._prf(shared=2, syn_n=4, hum_n=8)
    r, p = 2 / 8, 2 / 4
    assert m["f1_secondary"] == round(2 * r * p / (r + p), 4)


def test_an_empty_denominator_is_never_reported_as_zero():
    m = O._prf(shared=0, syn_n=0, hum_n=6)
    assert m["precision"] is not None or True          # readability
    assert m["precision"] is None and m["precision"] != 0.0
    assert "denominator is 0" in m["precision_undefined_reason"]


# =====================================================================
# 3. ORIGINAL_GEMINI must reproduce the frozen per-run table exactly
# =====================================================================
def test_original_variant_reproduces_the_frozen_source_exactly(b):
    f = b["original_matches_frozen_source"]
    assert f["pass"] is True, f["mismatches"][:5]
    assert f["n_values_checked"] == 90          # 30 runs x recall, precision, F1
    assert f["source"] == "results/per_run_metrics.csv"


def test_original_variant_matches_row_by_row(b):
    src = {}
    for r in csv.DictReader(
            (_PE / "results/per_run_metrics.csv").open(encoding="utf-8")):
        src[(r["condition"], r["fg"], r["canonical_replication_index"])] = r

    def num(x):
        return None if x in ("", "None", "nan") else round(float(x), 4)

    rows = b["variants"]["ORIGINAL_GEMINI"]["per_run"]
    assert len(rows) == 30
    for r in rows:
        s = src[(r["condition"], r["fg"], r["canonical_replication_index"])]
        assert r["recall"] == num(s["tier1_subtheme_recall"])
        assert r["precision"] == num(s["tier1_matched_theme_precision"])
        assert r["f1_secondary"] == num(s["tier1_f1_secondary"])


def test_the_defect_would_now_be_caught_by_the_source_check():
    """
    PLANTED VIOLATION: reinstate the old rule and confirm the fidelity check fails.
    The frozen table records F1 = 0.0 for the FG4 demographics-only runs.
    """
    rows = [{"condition": "demographics-only", "fg": "fg4",
             "canonical_replication_index": r,
             "recall": 0.0, "precision": 0.0, "f1_secondary": None}
            for r in ("1", "2", "3")]
    out = O.check_original_matches_source(rows)
    assert out["pass"] is False
    assert any(m.get("metric") == "f1_secondary" for m in out["mismatches"])


# =====================================================================
# 4. the report must not claim F1 is undefined when recall = precision = 0
# =====================================================================
def test_the_focus_run_values_are_the_frozen_expected_triples(b):
    f = b["focus_run"]
    assert (f["ORIGINAL_GEMINI"]["recall"], f["ORIGINAL_GEMINI"]["precision"],
            f["ORIGINAL_GEMINI"]["f1_secondary"]) == (0.0, 0.0, 0.0)
    o = f["OCA_REMOVE_A1_ONLY"]
    assert o["recall"] == 0.0 and o["precision"] is None and o["f1_secondary"] is None
    assert o["synthetic_present_set"] == []
    a3 = f["OCA_REMOVE_A1_ADD_PROPOSED_A3"]
    assert (a3["recall"], a3["precision"], a3["f1_secondary"]) == (0.0, 0.0, 0.0)
    assert a3["synthetic_present_set"] == ["A.3"]


def test_the_report_does_not_call_a_measured_zero_undefined():
    """
    Scans the report table rows: any row whose recall and precision are both 0.0 must
    not carry an undefined F1.
    """
    import re
    txt = (_AUD / "SENSITIVITY_INTEGRATION_REPORT.md").read_text(encoding="utf-8")
    bad = []
    for line in txt.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip().strip("*` ") for c in line.strip().strip("|").split("|")]
        low = [c.lower() for c in cells]
        if low.count("0.0") >= 2 and any(c == "undefined" for c in low):
            bad.append(line.strip())
    assert not bad, f"a measured zero is reported as undefined: {bad}"


def test_the_report_states_the_corrected_triples():
    txt = " ".join((_AUD / "SENSITIVITY_INTEGRATION_REPORT.md")
                   .read_text(encoding="utf-8").split())
    # both non-empty variants: recall 0.0, precision 0.0, F1 0.0
    assert txt.count("0.0 | 0.0 | **0.0**") == 2
    # the empty-set variant keeps an undefined precision and F1
    assert "**UNDEFINED** | **undefined**" in txt


def test_the_json_records_the_frozen_rule(b):
    r = b["f1_rule"]
    assert r["both_measured_and_zero"] == 0.0
    assert r["undefined_only_when"] == "recall or precision is undefined"
    assert "MEASURED zero" in r["rationale"]
    assert "contradicting" in r["corrected_defect"]


def test_no_variant_row_has_a_zero_pair_with_an_undefined_f1(b):
    for v in O.VARIANTS:
        for r in b["variants"][v]["per_run"]:
            if r["recall"] == 0.0 and r["precision"] == 0.0:
                assert r["f1_secondary"] == 0.0, (v, r["fg"], r["condition"])


def test_the_regenerated_csv_agrees_with_the_json(b):
    rows = list(csv.DictReader(
        (_OUT / "oca_variants_per_run.csv").open(encoding="utf-8")))
    assert len(rows) == 90
    for row in rows:
        if row["recall"] == "0.0" and row["precision"] == "0.0":
            assert row["f1_secondary"] == "0.0", row


# =====================================================================
# 5. defined n reported separately from the mean
# =====================================================================
def test_fg_level_reports_defined_n_beside_every_mean(b):
    for v in O.VARIANTS:
        for f in b["variants"][v]["fg_level"]:
            for metric in ("recall", "precision", "f1"):
                assert f"n_{metric}_defined" in f
                assert f"n_{metric}_undefined" in f
                assert (f[f"n_{metric}_defined"] + f[f"n_{metric}_undefined"]
                        == f["n_runs"] == 3)
            assert "not over n_runs" in f["denominator_note"]


def test_condition_level_reports_defined_n_beside_every_mean(b):
    for v in O.VARIANTS:
        for c in b["variants"][v]["condition_level"]:
            for k in ("n_fgs_with_defined_recall", "n_fgs_with_defined_precision",
                      "n_fgs_with_defined_f1"):
                assert c[k] == 5
            assert "n_precision_undefined_runs" in c
            assert "n_f1_undefined_runs" in c
            assert c["unit"].startswith("focus group, n = 5")


def test_the_undefined_cell_is_counted_not_absorbed(b):
    fg4 = [f for f in b["variants"]["OCA_REMOVE_A1_ONLY"]["fg_level"]
           if f["fg"] == "fg4" and f["condition"] == "demographics-only"][0]
    assert fg4["n_precision_defined"] == 2 and fg4["n_precision_undefined"] == 1
    assert fg4["n_f1_defined"] == 2 and fg4["n_f1_undefined"] == 1
    assert fg4["mean_precision"] == 0.0          # the two defined values are both 0
    base = [f for f in b["variants"]["ORIGINAL_GEMINI"]["fg_level"]
            if f["fg"] == "fg4" and f["condition"] == "demographics-only"][0]
    assert base["n_precision_defined"] == 3 and base["n_f1_defined"] == 3


# =====================================================================
# import, integrity and the A.1 / A.3 distinction
# =====================================================================
def test_import_is_read_only_and_hashed(b):
    i = b["import"]
    assert i["verdict"] == "DOES_NOT_SUPPORT_A1"
    assert i["alternative_subtheme"] == "A.3"
    assert i["reviewer"] == "LCLP"
    assert i["date_utc"].startswith("2026-08-03")
    assert i["import_mode"] == "READ_ONLY"
    assert i["workbook_modified_by_import"] is False
    assert i["provenance_attached_at_import"] is False
    assert len(i["workbook_sha256"]) == 64


def test_the_workbook_hash_still_matches_the_file(b):
    import hashlib
    p = _OUT / "OCA-001_adjudication.xlsx"
    assert hashlib.sha256(p.read_bytes()).hexdigest() == b["import"]["workbook_sha256"]


def test_integrity_against_the_sealed_source(b):
    g = b["integrity"]
    assert g["pass"] is True and g["n_elements_checked"] == 10
    assert g["immutable_and_blinded_material_matches_sealed_source"] is True


def test_mapping_happens_after_import(b):
    m = b["mapping"]
    assert m["mapping_applied_after_import"] is True
    assert m["internal_id"] == "FG4-DEMO-R01-A1"
    assert m["physical_run"] == "macho_meals_fg4_demoonly_run01"


def test_a3_is_a_proposal_not_an_adjudication(b):
    d = b["verdict_distinction"]
    assert d["explicit_human_verdict"]["subtheme"] == "A.1"
    prop = d["reviewer_proposed_alternative"]
    assert prop["subtheme"] == "A.3"
    assert prop["warrant"].startswith("NONE from the form")
    assert prop["reach_is_inferred"] is True
    assert "third variant" in prop["effect"]


def test_nothing_protected_was_modified(b):
    assert b["evaluator_cache_modified"] is False
    assert b["gemini_results_csv_modified"] is False
    assert b["workbook_or_drafts_modified"] is False
    assert b["primary_analysis"] == "ORIGINAL_GEMINI"


# =====================================================================
# the cross-model sensitivity must be untouched by this correction
# =====================================================================
def test_kendall_tau_b_and_recurrence_are_unchanged():
    s = json.loads((_AUD / "salience_sensitivity_final.json").read_text(
        encoding="utf-8"))
    assert s["n_defined_by_treatment"] == {"ORIGINAL_LOWER": 27, "MID": 30, "UPPER": 30}
    assert s["n_changed_MID"] == 15 and s["n_changed_UPPER"] == 15
    assert s["n_undefined_to_defined"] == 6 and s["n_defined_to_undefined"] == 0
    assert s["recurrence"]["n_changed"] == 14
    assert s["unresolved_cells_enter_any_treatment"] is False
    assert s["primary_unmodified"] is True


def test_the_oca_correction_does_not_touch_the_cross_model_family():
    s = json.loads((_AUD / "salience_sensitivity_final.json").read_text(
        encoding="utf-8"))
    assert "oca" in s["oca_kept_separate"].lower()
    assert s["existing_heatmap_replaced"] is False
