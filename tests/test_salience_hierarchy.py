"""
Tests for PARTICIPANT_BREADTH_AND_RECURRENCE_HIERARCHY_SIMILARITY.

Offline; no API call. The properties guarded here are the ones the legacy shared-only
metric got wrong: deleting synthetic omissions, going undefined on most sessions, and
scoring favourably on a tiny subset.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import salience_hierarchy as sh              # noqa: E402
import salience_hierarchy_outputs as so      # noqa: E402

_RES = _ROOT / "analysis/production_evaluation/results"
_OUT = _ROOT / "analysis/production_evaluation/final"


@pytest.fixture(scope="module")
def b():
    return sh.build()


# ------------------------------------------------------------- scoring
def test_true_absence_scores_zero_and_unmeasured_stays_null():
    P = {("enriched", "fg1", "1", "A.1"): {"present": "False"}}
    R = {}
    v, s = sh.score(P, R, "enriched", "fg1", "1", "A.1")
    assert (v, s) == (0.0, "TRUE_ABSENCE")
    v2, s2 = sh.score(P, R, "enriched", "fg1", "1", "Z.9")
    assert v2 is None and s2 == "UNMEASURED_NO_PRESENCE_ROW"


def test_present_without_a_reach_row_is_unmeasured_not_zero():
    P = {("enriched", "fg1", "1", "A.1"): {"present": "True"}}
    v, s = sh.score(P, {}, "enriched", "fg1", "1", "A.1")
    assert v is None
    assert s == "UNMEASURED_PRESENT_BUT_NO_REACH"


def test_no_null_is_ever_coerced_to_zero(b):
    for r in b["theme_scores_long"]:
        if r["is_unmeasured_null"]:
            assert r["reach"] == "", r
        if r["status"] == "TRUE_ABSENCE":
            assert r["reach"] == 0.0 and not r["is_unmeasured_null"], r


def test_every_true_absence_in_the_source_becomes_a_zero(b):
    pres = list(csv.DictReader(
        (_RES / "thematic_code_presence_long.csv").open(encoding="utf-8")))
    n_false = sum(1 for r in pres if r["present"] != "True")
    n_zero = sum(1 for r in b["theme_scores_long"] if r["status"] == "TRUE_ABSENCE")
    assert n_zero == n_false == 260


# -------------------------------------------------- undefined behaviour
def test_all_equal_ranks_are_undefined_not_zero():
    tau, why = sh._tau_b([0.5, 0.5, 0.5], [0.2, 0.4, 0.6])
    assert tau is None and why == "HUMAN_SIDE_CONSTANT"
    tau2, why2 = sh._tau_b([0.2, 0.4, 0.6], [0.0, 0.0, 0.0])
    assert tau2 is None and why2 == "SYNTHETIC_SIDE_CONSTANT"
    tau3, why3 = sh._tau_b([0.3, 0.3], [0.3, 0.3])
    assert tau3 is None and why3 == "FEWER_THAN_3_THEMES"


def test_undefined_runs_carry_a_reason(b):
    for r in b["per_run"]:
        if r["kendall_tau_b"] is None:
            assert r["undefined_reason"], r
        else:
            assert r["undefined_reason"] is None


def test_ties_are_counted_and_tau_b_handles_them():
    tau, why = sh._tau_b([1.0, 1.0, 0.5, 0.0], [0.8, 0.4, 0.4, 0.0])
    assert why is None and tau is not None
    assert sh._n_ties([1.0, 1.0, 0.5, 0.0]) == 1
    assert sh._n_ties([0.5, 0.5, 0.5]) == 3
    assert sh._n_ties([1, 2, 3]) == 0


def test_top_set_is_tie_aware():
    codes = ["a", "b", "c", "d"]
    vals = [0.9, 0.5, 0.5, 0.1]
    top = sh._top_set(codes, vals, k=2)
    assert top == {"a", "b", "c"}, "a tie at the cut must include both codes"


# ----------------------------------------------- primary universe rule
def test_primary_universe_includes_every_human_theme(b):
    for r in b["per_run"]:
        assert r["n_scored"] + r["n_unmeasured_excluded"] == r["n_human_present"]
        assert r["n_synthetic_recovered"] + r["n_human_themes_assigned_zero"] \
            == r["n_scored"]
        assert r["primary_universe"] == "all subthemes the human FG expressed"


def test_zeros_are_actually_present_in_the_primary_comparison(b):
    """
    The whole point: synthetic omissions must reach the correlation. If every run had
    zero assigned zeros, the new metric would be the legacy one wearing a new name.
    """
    total_zero = sum(r["n_human_themes_assigned_zero"] for r in b["per_run"])
    assert total_zero > 0
    assert total_zero == 148


def test_new_metric_is_defined_more_often_than_the_legacy_one(b):
    defined = sum(1 for r in b["per_run"] if r["kendall_tau_b"] is not None)
    per = list(csv.DictReader((_RES / "per_run_metrics.csv").open(encoding="utf-8")))
    legacy = sum(1 for r in per
                 if r.get("tier1_salience_hierarchy", "") not in ("", "None", "nan"))
    assert defined == 27 and legacy == 16
    assert defined > legacy


# ------------------------------------------------------- aggregation
def test_replicates_are_kept_and_summarised_by_median(b):
    for c in b["by_fg_condition"]:
        assert c["n_replicates"] == 3
        assert set(c["replicate_values"]) == {"1", "2", "3"}
        if c["n_defined"]:
            vals = [v for v in c["replicate_values"].values() if v is not None]
            assert c["min_kendall_tau_b"] == round(min(vals), 4)
            assert c["max_kendall_tau_b"] == round(max(vals), 4)
        assert "median" in c["summary_rule"]
        assert "not averaged" in c["summary_rule"]


def test_paired_differences_use_five_focus_groups_not_fifteen(b):
    p = b["paired_summary"]
    assert len(p["paired_differences"]) == 5
    assert "n = 5" in p["unit_of_analysis"]
    assert "never 15" in p["unit_of_analysis"]
    assert p["inference"].startswith("NONE")


def test_study_level_unit_is_a_complete_study_realisation(b):
    assert len(b["study_replicates"]) == 6          # 2 conditions x 3 replicates
    for s in b["study_replicates"]:
        assert "NEVER treated as 15 independent focus groups" in s["unit"]


# ----------------------------------------------------- union sensitivity
def test_union_variant_is_labelled_as_mixing_fidelity_with_proliferation(b):
    for r in b["per_run"]:
        assert "proliferation" in r["union_caveat"]
        assert "secondary" in r["union_caveat"]


# ------------------------------------------------------- terminology
def test_mandatory_statement_present_and_forbidden_terms_absent(b):
    assert sh.MANDATORY_STATEMENT in b["mandatory_statement"]
    blob = json.dumps(b).lower()
    for term in sh.FORBIDDEN_TERMS:
        assert term not in blob, term
    assert b["analysis"] == "PARTICIPANT_BREADTH_AND_RECURRENCE_HIERARCHY_SIMILARITY"
    assert "CENTRALITY_NOT_ASSESSED" in b["separate_from"]


def test_legacy_metric_is_reclassified_not_deleted(b):
    lg = b["legacy_metric"]
    assert lg["metric_id"] == "tier1_salience_hierarchy"
    assert lg["reclassified_as"] == "LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC"
    assert lg["retained"] is True
    assert lg["used_as_primary_result"] is False


# ------------------------------------------------------- verification
def test_verification_passes_and_checks_denominators(b):
    v = so.verify(b)
    assert v["pass"] is True, v["problems"]
    assert v["n_reach_rows_checked"] == 125
    assert v["n_true_absences_scored_zero"] == 260
    assert v["n_unmeasured_nulls"] == 0


def test_reach_equals_voiced_by_over_participants():
    for r in csv.DictReader((_RES / "thematic_reach_long.csv").open(encoding="utf-8")):
        assert abs(float(r["reach"])
                   - int(r["voiced_by_n"]) / int(r["participants_n"])) < 1e-6, r


def test_outputs_exist_and_reconcile():
    for n, want in (("salience_hierarchy_per_run.csv", 30),
                    ("salience_hierarchy_by_fg_condition.csv", 10),
                    ("salience_hierarchy_study_replicates.csv", 6),
                    ("salience_hierarchy_theme_scores_long.csv", 385)):
        rows = list(csv.DictReader((_OUT / n).open(encoding="utf-8")))
        assert len(rows) == want, n
    assert (_OUT / "salience_recurrence_heatmap.png").exists()
