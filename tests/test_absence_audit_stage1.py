"""
Stage-1 post-hoc corrections. Offline; no API call.

  C8  the original coder's quotations ARE recoverable from the evaluator cache, and the
      two evaluators' turn LABELS are not a shared space — comparison must be projected
      through quote text
  C9  max_output_tokens = 8192 recorded as a post-freeze configuration completion and
      frozen prospectively for Stage 2

Also pins every Stage-1 count, so neither correction can move a metric.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import absence_audit_build as B              # noqa: E402
import absence_audit_rules as R              # noqa: E402
import absence_audit_stage1 as S1            # noqa: E402
import absence_audit_gemini_evidence as G    # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/salience_absence_audit"


@pytest.fixture(scope="module")
def stage1():
    return json.loads(
        (_OUT / "stage1_calibration_results.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def eve():
    return json.loads(
        (_OUT / "stage1_two_evaluator_evidence.json").read_text(encoding="utf-8"))


# =====================================================================
# Stage-1 counts must not move
# =====================================================================
def test_every_stage1_count_is_unchanged(stage1):
    c = stage1["counts"]
    assert c == {"n_cells": 154, "n_positive_controls": 63, "n_absence_cells": 91,
                 "n_detected": 60, "n_agree": 140, "n_unresolved": 24}
    g = stage1["gate"]
    assert g["outcome"] == R.GATE_B
    assert g["detection_rate"]["lower"] == 0.8691
    assert g["repetition_stability"]["lower"] == 0.8532
    assert g["unresolved_rate"]["upper"] == 0.2214
    assert stage1["n_absences_corroborated"] == 0
    assert stage1["final_absence_labels"] == {
        "AUDITOR_DID_NOT_FIND_EVIDENCE": 64, "ABSENCE_CONTESTED": 6,
        "ABSENCE_UNRESOLVED": 21}
    assert stage1["n_gate_failures"] == 2
    assert stage1["validation"]["n_invalid"] == 0


def test_all_eleven_controls_still_eligible(stage1):
    assert all(e["eligible_for_corroboration"]
               for e in stage1["eligibility"].values())
    assert len(stage1["eligibility"]) == 11


def test_nothing_was_converted(stage1):
    assert stage1["stage_2_submitted"] is False
    assert stage1["gemini_results_modified"] is False
    assert stage1["any_absence_converted_to_presence"] is False


# =====================================================================
# C8 — the withdrawn claim, and the cache reconstruction
# =====================================================================
def test_the_unavailability_claim_is_withdrawn(eve):
    assert "withdrawn" in eve["withdrawal"]
    assert eve["changes_stage1_metrics"] is False
    proto = (_OUT / "STAGE1_CALIBRATION_REPORT.md").read_text(encoding="utf-8")
    low = " ".join(proto.lower().split())
    for claim in ("are not stored in any results artefact",
                  "no direct comparison against its evidence is possible"):
        assert claim not in low, claim


def test_cache_selection_is_objective_and_unique():
    sel = G.select_cache_records()
    assert sel["pass"] is True, sel["problems"]
    assert sel["n_selected"] == 35
    assert "never selection by timestamp" in sel["selection_rule"]
    # the fg1 duplicates must be excluded on stated grounds, not silently
    assert len(sel["rejected"]) == 2
    for r in sel["rejected"]:
        assert r["reasons"], r


def test_planted_a_wrong_presence_pattern_disqualifies_a_record(monkeypatch):
    """PLANTED VIOLATION: selection must actually test the presence pattern."""
    real = B.presence_grid()
    victim = next(k for k, v in sorted(real.items()) if v is True)
    monkeypatch.setattr(B, "presence_grid", lambda: {**real, victim: False})
    sel = G.select_cache_records()
    assert sel["pass"] is False
    assert any(victim[0] in p for p in sel["problems"])


def test_all_63_controls_have_original_quotations(eve):
    v = eve["verification_of_63_controls"]
    assert v["n_controls"] == 63
    assert v["with_quotes"] == 63
    assert v["with_turn"] == 63
    assert v["with_speaker"] == 63
    assert v["n_quotations"] == 174


def test_total_gemini_quotations_reported(eve):
    assert eve["gemini_quotations_total_corpus"] == 356


# --------------------------------------------- the turn-label finding
def test_turn_label_spaces_are_not_shared(eve):
    t = eve["turn_label_spaces_do_not_align"]
    assert "not an index base" in t["finding"] or "not a correctable index base" in \
        t["finding"]
    assert "never compared directly" in t["consequence"]
    assert t["n_original_quotations_corpus"] == 356


def test_planted_comparing_raw_turn_labels_would_be_wrong():
    """
    PLANTED VIOLATION: if the label spaces were shared, projecting by text would be
    unnecessary. Measure the offset directly and assert it is NOT constant.
    """
    sel = G.select_cache_records()
    gem = G.gemini_evidence(sel["selected"])["by_doc"]
    cb = B.codebook()
    store = B.render_store(cb, sorted(cb))
    offsets = set()
    dk = "macho_meals_fg1_run01"
    bid = B.blind_id(dk)
    turns = store[bid]["turns"]
    for code, qs in gem[dk].items():
        for q in qs:
            nq = G._norm(q["quote"])
            hits = [t for t, us in turns.items() for u in us
                    if nq and nq in G._norm(u["text"])]
            if len(hits) == 1:
                offsets.add(int(q["turn_id"][1:]) - int(hits[0][1:]))
    assert len(offsets) > 1, ("this document's label offset is constant; the projection "
                              "rationale would need revisiting")


def test_projection_recovers_almost_every_quotation(eve):
    v = eve["verification_of_63_controls"]
    assert v["n_projected_into_audit_space"] == 173
    assert v["n_quotations"] - v["n_projected_into_audit_space"] == 1


def test_speaker_maps_are_unambiguous_in_every_stage1_document(eve):
    sr = eve["speaker_reconciliation"]
    assert len(sr) == 14
    for bid, s in sr.items():
        assert s["ambiguous"] == {}, bid


# ------------------------------------------------- comparison reporting
def test_the_four_comparison_outcomes_are_reported_separately(eve):
    per_ctl = eve["comparison_categories_per_control"]
    per_item = eve["comparison_categories_per_evidence_item"]
    assert per_ctl["SAME_TURN_SAME_SPEAKER"] == 61
    assert sum(per_ctl.values()) == 63
    # different valid evidence is not collapsed into disagreement
    assert per_item["DIFFERENT_VALID_EVIDENCE_SAME_SPEAKER"] == 2
    assert per_item["DIFFERENT_VALID_EVIDENCE_DIFFERENT_SPEAKER"] == 2
    assert per_item["ADJACENT_CODE_DIVERGENCE"] == 2
    assert "best match" in eve["category_note"]


def test_identical_quotations_are_never_required(eve):
    """A different valid passage supporting the same code is its own category."""
    names = set(eve["comparison_categories_per_evidence_item"])
    assert any(n.startswith("DIFFERENT_VALID_EVIDENCE") for n in names)
    assert "DISAGREEMENT" not in " ".join(names)


def test_adjacent_analysis_uses_both_evaluators(eve):
    a = eve["adjacent_two_evaluator"]
    assert a["n_original_coder_within_family"] == 11
    assert "n" in a
    for r in a["original_coder_same_turn_two_codes_one_family"]:
        assert "audit_turn_id" in r and len(r["codes"]) > 1
        assert len({B.codebook()[c]["parent_theme"] for c in r["codes"]}) == 1


def test_undetected_controls_carry_the_original_evidence(eve):
    u = eve["undetected_controls_with_original_evidence"]
    assert {c["subtheme_id"] for c in u} == {"D", "B.1", "B.4"}
    for c in u:
        assert c["n_gemini_quotations"] >= 2
        assert c["gemini_audit_turns"] and c["gemini_audit_speakers"]
        assert all(s.startswith("P") for s in c["gemini_audit_speakers"])


# =====================================================================
# C9 — max_output_tokens as a post-freeze configuration completion
# =====================================================================
def test_config_completion_record_is_exact():
    c = S1.CONFIG_COMPLETION
    assert c["parameter"] == "max_output_tokens" and c["value"] == 8192
    assert c["record_type"] == "POST_FREEZE_CONFIGURATION_COMPLETION"
    assert c["absent_from_pre_submission_manifest"] is True
    assert "cross_model_audit_q3" in c["adopted_from"]
    assert c["invented_for_this_audit"] is False
    assert c["chosen_from_stage1_results"] is False
    assert c["transmitted_on_all_28_stage1_requests"] is True
    assert c["stage1_end_turn_responses"] == "28/28"
    assert c["stage1_truncated_responses"] == 0
    assert c["stage1_complete_11_code_outputs"] == "28/28"


def test_it_is_frozen_prospectively_and_not_retunable():
    c = S1.CONFIG_COMPLETION
    assert c["frozen_prospectively_for_stage_2"] is True
    assert c["may_be_retuned_on_stage1_results"] is False
    assert "calibration data" in c["why_not_retuned"]
    assert S1.MAX_OUTPUT_TOKENS == 8192


def test_the_record_reached_both_artefacts():
    job = json.loads((_OUT / "stage1_batch_job.json").read_text(encoding="utf-8"))
    man = json.loads((_OUT / "batch_manifest.json").read_text(encoding="utf-8"))
    assert job["max_output_tokens"] == 8192
    assert job["max_output_tokens_record"] == S1.CONFIG_COMPLETION
    assert man["auditor"]["max_output_tokens"] == 8192
    assert man["auditor"]["max_output_tokens_record"]["record_type"] == \
        "POST_FREEZE_CONFIGURATION_COMPLETION"


def test_the_claim_about_stage1_responses_is_true_of_the_raw_data():
    raw = json.loads((_OUT / "stage1_raw_responses.json").read_text(encoding="utf-8"))
    assert len(raw["responses"]) == 28
    assert all(r["stop_reason"] == "end_turn" for r in raw["responses"])
    for r in raw["responses"]:
        assert len(json.loads(r["raw_text"])["assessments"]) == 11
