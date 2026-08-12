"""
Guards on the derivation and the B+ evaluation for U01-U07 / Q3.

The things that must not slip:
  * an UNCERTAIN key is never a match and never moves recall;
  * the single format-level interpretation is confined to UNCERTAIN rows;
  * no metric is derived from how many quotes either side cited;
  * AI-assisted provisional adjudication is never counted as human validation;
  * recall alone cannot produce a PASS.

No API calls. No workbook is modified.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import analyse_matching_q3 as an       # noqa: E402
import bplus_evaluation_q3 as bp       # noqa: E402
import emergent_calibration_q3 as cal  # noqa: E402
import emergent_matching_researcher as mr   # noqa: E402

OUT = ROOT / "analysis" / "production_evaluation" / "emergent_calibration_q3"

pytestmark = pytest.mark.skipif(
    not (OUT / "matching_derivation_q3.json").exists(),
    reason="derivation not built",
)


@pytest.fixture(scope="module")
def d():
    return json.loads((OUT / "matching_derivation_q3.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def b():
    return json.loads((OUT / "bplus_evaluation_q3.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The returned workbook itself
# ---------------------------------------------------------------------------

def test_all_44_rows_are_decided_and_immutable_columns_are_intact():
    rows = mr.read_rows()
    assert len(rows) == 44
    canon = {c["human_key"]: c for c in mr.canonical_rows()}
    for r in rows:
        hk = str(r["human_key"]).strip()
        assert str(r.get("human_decision") or "").strip() in mr.HUMAN_DECISIONS
        for f in mr.IMMUTABLE_COLS:
            act = "" if r.get(f) is None else str(r.get(f))
            assert act == canon[hk][f], f"{hk}.{f} drifted"


def test_the_gate_is_ready_after_the_authorised_amendment():
    """
    The single cross-unit key was corrected by the researcher under
    MATCHING_AMENDMENT_01 (U02::M2 -> U03::M2, one cell, decision left UNCERTAIN).
    """
    assert mr.validate() == []
    rec = json.loads((OUT / "MATCHING_AMENDMENT_01_U03C09.json")
                     .read_text(encoding="utf-8"))
    assert (rec["previous_value"], rec["new_value"]) == ("U02::M2", "U03::M2")
    assert rec["human_decision_unchanged"] == "UNCERTAIN"
    assert rec["cells_changed"] == 1


# ---------------------------------------------------------------------------
# The one interpretation
# ---------------------------------------------------------------------------

def test_no_interpretation_is_applied_any_more(d):
    """The amendment removed the only case; the rule is retained, not exercised."""
    assert d["invalid_candidate_keys_dropped"] == []
    assert d["interpretation_applied"]["status"].startswith("NO_LONGER_APPLIED")
    assert "MATCHING_AMENDMENT_01" in d["interpretation_applied"]["status"]


def test_an_invalid_key_on_a_matched_row_would_raise_not_be_interpreted(monkeypatch):
    """
    The rule still holds even though no live row exercises it: plant a cross-unit key
    on a MATCHED row and the derivation must refuse rather than interpret it away.
    """
    rows, themes, humans = an.load()          # capture BEFORE patching
    planted = False
    for r in rows:
        if str(r["human_key"]).strip() == "U03::C09":
            r["human_decision"] = "MATCHED"
            r["matched_machine_keys"] = "U02::M2"      # belongs to another unit
            planted = True
    assert planted
    monkeypatch.setattr(an, "load", lambda: (rows, themes, humans))
    with pytest.raises(RuntimeError, match="substantive defect"):
        an.derive()


def test_every_key_belongs_to_its_own_unit(d):
    """No key was ever substituted; the corrected one came from the researcher."""
    for r in d["rows"]:
        for k in r["confirmed_machine_keys"] + r["candidate_machine_keys"]:
            assert k.startswith(r["unit_id"] + "::"), k
    for k, humans in d["candidate_uncertain_links"].items():
        for hk in humans:
            assert k.split("::")[0] == hk.split("::")[0]


def test_the_corrected_key_is_a_candidate_not_a_match(d):
    """U03::M2 is now a valid candidate, and still counts for nothing."""
    assert d["candidate_uncertain_links"].get("U03::M2") == ["U03::C09"]
    assert "U03::M2" not in d["confirmed_links"]
    assert "U03::M2" in d["machine_themes_unlinked"]
    row = next(r for r in d["rows"] if r["human_key"] == "U03::C09")
    assert row["decision"] == "UNCERTAIN"
    assert row["confirmed_machine_keys"] == []


# ---------------------------------------------------------------------------
# UNCERTAIN never counts
# ---------------------------------------------------------------------------

def test_uncertain_rows_are_absent_from_confirmed_links(d):
    uncertain = {r["human_key"] for r in d["rows"] if r["decision"] == "UNCERTAIN"}
    assert len(uncertain) == 6
    for k, humans in d["confirmed_links"].items():
        assert not (set(humans) & uncertain), (k, humans)


def test_recall_counts_only_matched_rows(d):
    r = d["coverage"]["recall_vs_union_reference"]
    n_matched = sum(1 for x in d["rows"] if x["decision"] == "MATCHED")
    assert r["numerator_matched_human_instances"] == n_matched == 30
    assert r["denominator_human_instances"] == 44
    assert abs(r["value"] - 30 / 44) < 1e-12
    assert r["numerator_matched_human_instances"] + \
        sum(1 for x in d["rows"] if x["decision"] == "NO_MATCH_HUMAN_ONLY") + \
        sum(1 for x in d["rows"] if x["decision"] == "UNCERTAIN") == 44


def test_a_candidate_key_does_not_clear_the_adjudication_queue(d):
    """A machine theme named only on an UNCERTAIN row still needs a verdict."""
    for k in d["candidate_uncertain_links"]:
        if k not in d["confirmed_links"]:
            assert k in d["machine_themes_unlinked"], (
                f"{k} was cleared from the queue by a candidate key alone")


def test_fusion_and_fragmentation_come_only_from_confirmed_links(d):
    for k, humans in d["possible_fusion_one_machine_many_human"].items():
        assert d["confirmed_links"][k] == humans
    for hk, keys in d["possible_fragmentation_one_human_many_machine"].items():
        row = next(r for r in d["rows"] if r["human_key"] == hk)
        assert row["decision"] == "MATCHED"
        assert row["confirmed_machine_keys"] == keys


# ---------------------------------------------------------------------------
# Quote counts are never used
# ---------------------------------------------------------------------------

def test_no_metric_is_derived_from_quote_counts(d, b):
    banned = ("quote_count", "n_quotes", "quote_density", "quote_coverage",
              "evidence_count", "quotes_per_theme")
    blob = (json.dumps(d["coverage"]) + json.dumps(b["metrics"])).lower()
    for x in banned:
        assert x not in blob, x
    assert "NOT COMPARED" in b["four_dimensions_kept_separate"]["quantity_of_evidence"]
    assert "one human quote per theme" in \
        b["four_dimensions_kept_separate"]["quantity_of_evidence"]


def test_the_dimensions_are_reported_separately(b):
    d = b["four_dimensions_kept_separate"]
    for k in ("thematic_coverage", "granularity", "literal_evidence_attachment",
              "substantive_groundedness", "quantity_of_evidence"):
        assert k in d, k
    assert "groundedness" not in d, "the overclaiming name must be gone"


def test_literality_is_never_reported_as_substantive_groundedness(b):
    """A verbatim quote shows attachment, not that the claim is warranted."""
    d = b["four_dimensions_kept_separate"]
    assert "NOT ESTABLISHED" in d["substantive_groundedness"]
    m = b["metrics"]
    assert "grounded_theme_rate" not in m
    r = m["literal_evidence_attachment_rate"]
    assert r["numerator"] == r["denominator"] == 30
    assert "verbatim" in r["measures"]
    assert "substantively warranted" in r["does_NOT_measure"]


# ---------------------------------------------------------------------------
# Granularity
# ---------------------------------------------------------------------------

def test_every_granularity_case_is_classified(d, b):
    o2m = {x["human_key"] for x in b["granularity_audit"]["one_to_many"]}
    m2o = {x["machine_key"] for x in b["granularity_audit"]["many_to_one"]}
    assert o2m == set(d["possible_fragmentation_one_human_many_machine"])
    assert m2o == set(d["possible_fusion_one_machine_many_human"])
    for x in (b["granularity_audit"]["one_to_many"] +
              b["granularity_audit"]["many_to_one"]):
        assert x["classification"] in bp.GRANULARITY_CLASSES
        assert len(x["rationale"]) > 40


def test_granularity_differences_are_not_automatically_penalised(b):
    """A broad human cluster decomposed by the machine is legitimate by default."""
    cls = [x["classification"] for x in b["granularity_audit"]["one_to_many"]]
    assert cls.count("LEGITIMATE_GRANULARITY_DIFFERENCE") >= 7
    assert "SUBSTANTIVE_MISMATCH" not in cls
    # and granularity never enters the recall figure
    assert b["metrics"]["recall_vs_union_reference"]["denominator_human_instances"] == 44


def test_the_researchers_matches_were_not_changed(d, b):
    rows = {r["human_key"]: r for r in d["rows"]}
    for x in b["granularity_audit"]["one_to_many"]:
        assert rows[x["human_key"]]["confirmed_machine_keys"] == x["machine_keys"]


# ---------------------------------------------------------------------------
# Machine-only queue and the B+ state
# ---------------------------------------------------------------------------

def test_every_unlinked_theme_has_a_verdict_from_the_frozen_set(d, b):
    keys = [q["machine_key"] for q in b["machine_only_queue"]]
    assert keys == d["machine_themes_unlinked"]
    assert len(keys) == 6
    for q in b["machine_only_queue"]:
        assert q["verdict"] in cal.MACHINE_ONLY_VERDICTS
        assert len(q["rationale"]) > 40
        assert q["model_relevance_caveat"] == \
            "DESCRIPTIVE_MODEL_METADATA_NOT_HUMAN_VALIDATED"


def test_the_adjudication_is_labelled_provisional_and_not_human(b):
    assert b["classification"] == "AI_ASSISTED_PROVISIONAL_ADJUDICATION"
    c = b["bplus_conditions"]["complete_adjudication_of_every_machine_only_theme"]
    assert c["met"] is False
    assert "not human validation" in c["why_not"]


def test_recall_alone_does_not_produce_a_pass(b):
    assert b["bplus_conditions"]["coverage_benchmark_met"]["met"] is True
    assert b["bplus_state"] != "PASS_WITH_SAMPLED_HUMAN_VERIFICATION"
    assert b["bplus_state"] == "PENDING_LIMITED_REVIEW"
    assert "Recall alone does not produce a PASS" in b["state_rationale"]


def test_the_state_is_one_of_the_four_frozen_labels(b):
    allowed = set(cal.FINAL_STATES) | {"PENDING_LIMITED_REVIEW"}
    assert b["bplus_state"] in allowed


def test_unresolved_items_are_escalated_and_bounded(b):
    e = b["escalate_to_researcher"]
    assert len(e["unresolved_uncertain_rows"]) == 6
    assert len(e["granularity_cases_still_uncertain"]) == 3
    assert "No new workbook" in e["note"]
    for r in e["unresolved_uncertain_rows"]:
        assert r["reasoning"], "an escalated row must carry her own reasoning"


def test_benchmark_is_met_but_two_conditions_are_not(b):
    met = [k for k, c in b["bplus_conditions"].items() if c["met"]]
    unmet = [k for k, c in b["bplus_conditions"].items() if not c["met"]]
    assert len(met) == 2 and len(unmet) == 2
    assert b["metrics"]["recall_vs_union_reference"]["value"] >= cal.COVERAGE_BENCHMARK
