"""
Tests for the frozen Phase A quote-level and theme-level validation policy.

Offline; no API call. The properties guarded are the ones the unit-level validator got
wrong: one bad quote destroyed a whole unit, and a theme that kept good evidence was
discarded along with it.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import phase_a_revalidation as rv    # noqa: E402

_D = _ROOT / "analysis/production_evaluation/inductive_phase_a"

_TURNS = {
    "T012": [{"speaker": "P2", "text": "I just cook whatever is quick, honestly.",
              "is_moderator": False}],
    "T013": [{"speaker": "Moderator", "text": "Does anyone feel differently?",
              "is_moderator": True}],
    "T014": [{"speaker": "P3", "text": "There's actual foods that just feel a bit, "
                                       "I dunno, not for blokes.", "is_moderator": False}],
}


def _q(**kw):
    base = {"turn_id": "T012", "speaker": "P2", "quote": "cook whatever is quick"}
    base.update(kw)
    return base


# ------------------------------------------------------------ quote policy
def test_a_contiguous_participant_quote_is_valid():
    assert rv.classify_quote(_q(), _TURNS)["verdict"] == rv.Q_VALID


def test_internal_elision_fails():
    """The exact defect: real words, correct turn, but words dropped from the middle."""
    c = rv.classify_quote(
        _q(turn_id="T014", speaker="P3",
           quote="There's actual foods that just feel a bit, not for blokes."), _TURNS)
    assert c["verdict"] == rv.Q_NOT_CONTIGUOUS


def test_normalisation_is_permitted_but_never_bridges_an_elision():
    ok = rv.classify_quote(_q(quote="I  JUST cook whatever is quick"), _TURNS)
    assert ok["verdict"] == rv.Q_VALID
    bad = rv.classify_quote(_q(quote="I cook whatever is quick"), _TURNS)
    assert bad["verdict"] == rv.Q_NOT_CONTIGUOUS


def test_a_quote_from_another_turn_fails():
    assert rv.classify_quote(
        _q(turn_id="T014", quote="cook whatever is quick"),
        _TURNS)["verdict"] == rv.Q_NOT_CONTIGUOUS
    assert rv.classify_quote(
        _q(turn_id="T999"), _TURNS)["verdict"] == rv.Q_TURN_NOT_IN_UNIT


def test_a_moderator_quote_fails():
    c = rv.classify_quote(
        _q(turn_id="T013", speaker="Moderator", quote="Does anyone feel differently"),
        _TURNS)
    assert c["verdict"] == rv.Q_MODERATOR


def test_a_speaker_mismatch_fails():
    assert rv.classify_quote(
        _q(speaker="P9"), _TURNS)["verdict"] == rv.Q_SPEAKER_MISMATCH


def test_an_empty_quote_fails():
    assert rv.classify_quote(_q(quote="   "), _TURNS)["verdict"] == rv.Q_EMPTY


# ------------------------------------------------------------ theme policy
def _theme(quotes):
    return {"theme_id": "T1", "label": "l", "description": "d", "quotes": quotes}


def _decide(theme):
    kept = [c for c in (rv.classify_quote(q, _TURNS) for q in theme["quotes"])
            if c["verdict"] == rv.Q_VALID]
    return (rv.THEME_ACCEPTED if kept else rv.THEME_REPAIR), len(kept)


def test_an_extra_invalid_quote_does_not_remove_a_theme_that_keeps_a_valid_one():
    """The central correction: theme-level, not unit-level."""
    t = _theme([_q(), _q(quote="I cook whatever is quick")])   # one good, one elided
    status, n_valid = _decide(t)
    assert status == rv.THEME_ACCEPTED and n_valid == 1


def test_a_theme_with_no_valid_quote_requires_repair():
    t = _theme([_q(quote="I cook whatever is quick"),
                _q(turn_id="T013", speaker="Moderator",
                   quote="Does anyone feel differently")])
    status, n_valid = _decide(t)
    assert status == rv.THEME_REPAIR and n_valid == 0


def test_invalid_quotes_are_retained_in_the_audit_never_deleted():
    audit = json.loads((_D / "rejected_quotes_audit.json").read_text(encoding="utf-8"))
    val = json.loads((_D / "phase_a_theme_level_validation.json").read_text(
        encoding="utf-8"))
    n_invalid = val["n_quotes"] - val["quote_verdicts"].get("VALID", 0)
    assert audit["n_rejected"] == n_invalid
    for q in audit["quotes"]:
        assert q["verdict"] != rv.Q_VALID
        assert q["quote"], "the rejected text itself must be retained"


# ------------------------------------------------------------- repair rule
def test_not_supported_in_unit_removes_the_theme_without_inventing_evidence():
    """
    The repair schema offers exactly two verdicts, and neither fabricates a quote.
    """
    rep = json.loads((_D / "evidence_repair_manifest.json").read_text(encoding="utf-8"))
    assert rep["schema"]["properties"]["verdict"]["enum"] == [
        "SUPPORTED", "NOT_SUPPORTED_IN_UNIT"]
    assert "contiguous substring copied exactly" in rep["prompt"]
    assert "Do not omit words from the middle" in rep["prompt"]
    assert rep["submitted"] is False
    assert rep["codebook_shown"] is False
    assert rep["segmented_units_changed"] is False
    assert rep["execution_stage"] == "PHASE_A_EVIDENCE_REPAIR"
    for r in rep["requests"]:
        assert r["execution_stage"] == "PHASE_A_EVIDENCE_REPAIR"
        for k in ("unit_text_sha256", "theme_sha256", "prompt_sha256",
                  "schema_sha256", "cache_key"):
            assert len(r[k]) == 64
    assert rep["unique_keys"] is True


def test_the_repair_count_is_derived_not_hardcoded():
    rep = json.loads((_D / "evidence_repair_manifest.json").read_text(encoding="utf-8"))
    val = json.loads((_D / "phase_a_theme_level_validation.json").read_text(
        encoding="utf-8"))
    assert rep["n_requests"] == val["themes_no_valid_quote"]
    assert rep["n_units"] == val["n_units_requiring_repair"]
    assert "revalidation" in rep["derived_not_hardcoded"]


# ------------------------------------------------------- integrity of history
def test_the_174_raw_responses_are_byte_identical():
    raw = _D / "phase_a_raw_responses.json"
    assert hashlib.sha256(raw.read_bytes()).hexdigest().startswith("cc34ad0113e22a22")
    j = json.loads(raw.read_text(encoding="utf-8"))
    assert j["n_results"] == 174
    assert all(r["result_type"] == "succeeded" for r in j["responses"])


def test_revalidation_is_deterministic():
    a, b = rv.revalidate(), rv.revalidate()
    for k in ("n_themes", "n_quotes", "themes_all_quotes_valid",
              "themes_mixed_valid_and_invalid", "themes_no_valid_quote",
              "n_units_complete", "n_units_requiring_repair"):
        assert a[k] == b[k]
    assert json.dumps(a["units"], sort_keys=True) == \
        json.dumps(b["units"], sort_keys=True)


def test_the_superseded_artefact_is_marked_but_retained():
    a = json.loads((_D / "phase_a_accepted.json").read_text(encoding="utf-8"))
    assert a["status"] == "PROVISIONAL_SUPERSEDED"
    assert a["original_counts_retained"] == {"n_accepted": 162, "n_quarantined": 12}
    assert a["accepted"], "the original content must not be emptied"


def test_the_job_record_keeps_its_creation_state_and_adds_the_observed_one():
    j = json.loads((_D / "phase_a_batch_job.json").read_text(encoding="utf-8"))
    assert j["state_at_creation"] == "JobState.JOB_STATE_PENDING"
    assert j["final_observed_state"] == "JOB_STATE_SUCCEEDED"
    assert j["n_responses_retrieved"] == 174


def test_the_structural_totals_that_do_reproduce():
    val = json.loads((_D / "phase_a_theme_level_validation.json").read_text(
        encoding="utf-8"))
    assert val["n_themes"] == 526
    assert val["n_quotes"] == 1398
    assert val["raw_responses_modified"] is False
    assert val["policy_id"] == "PHASE_A_QUOTE_AND_THEME_VALIDATION_V1"
    assert val["normalisation_never_bridges_elision"] is True


# ============================================================ repair stage
_RTURNS = {
    "T012": [{"speaker": "P2", "text": "I just cook whatever is quick, honestly.",
              "is_moderator": False}],
    "T013": [{"speaker": "Moderator", "text": "Does anyone feel differently?",
              "is_moderator": True}],
}


def test_supported_requires_all_three_evidence_fields():
    for missing in ("turn_id", "speaker", "quote"):
        p = {"verdict": "SUPPORTED", "turn_id": "T012", "speaker": "P2",
             "quote": "cook whatever is quick"}
        p[missing] = ""
        out = rv.validate_repair(p, _RTURNS)
        assert out["resolution"] == "QUARANTINE"
        assert any(missing in x for x in out["problems"])


def test_not_supported_must_carry_no_evidence_fields():
    clean = rv.validate_repair({"verdict": "NOT_SUPPORTED_IN_UNIT"}, _RTURNS)
    assert clean["resolution"] == "EXCLUDE_THEME"
    assert clean["evidence_invented"] is False
    dirty = rv.validate_repair(
        {"verdict": "NOT_SUPPORTED_IN_UNIT", "turn_id": "T012", "speaker": "P2",
         "quote": "x"}, _RTURNS)
    assert dirty["resolution"] == "QUARANTINE"


def test_not_supported_in_unit_removes_the_theme_without_inventing_evidence():
    out = rv.validate_repair({"verdict": "NOT_SUPPORTED_IN_UNIT"}, _RTURNS)
    assert out["resolution"] == "EXCLUDE_THEME"
    assert "quote" not in out


def test_the_repair_is_validated_without_normalisation():
    """Phase A tolerates normalisation; the repair does not."""
    exact = rv.validate_repair(
        {"verdict": "SUPPORTED", "turn_id": "T012", "speaker": "P2",
         "quote": "cook whatever is quick"}, _RTURNS)
    assert exact["resolution"] == "KEEP_THEME" and exact["character_exact"] is True
    cased = rv.validate_repair(
        {"verdict": "SUPPORTED", "turn_id": "T012", "speaker": "P2",
         "quote": "COOK WHATEVER IS QUICK"}, _RTURNS)
    assert cased["resolution"] == "QUARANTINE", "case must not rescue a repair"


def test_a_repair_quote_from_the_moderator_is_quarantined():
    out = rv.validate_repair(
        {"verdict": "SUPPORTED", "turn_id": "T013", "speaker": "Moderator",
         "quote": "Does anyone feel differently?"}, _RTURNS)
    assert out["resolution"] == "QUARANTINE"
    assert any("moderator" in p for p in out["problems"])


def test_a_third_category_is_rejected():
    for v in ("UNCERTAIN", "PARTIAL", "", None):
        assert rv.validate_repair({"verdict": v}, _RTURNS)["resolution"] == "QUARANTINE"


def test_the_metric_is_named_for_what_it_measures():
    val = json.loads((_D / "phase_a_theme_level_validation.json").read_text(
        encoding="utf-8"))
    assert val["metric_name"] == "normalized_contiguous_quote"
    assert val["metric_is_not"] == "character_exact_quote"
    d = val["raw_exact_diagnostic"]
    assert d["metric"] == "raw_exact_contiguous_quote"
    assert d["n_raw_exact_contiguous"] <= d["n_normalized_contiguous"]
    assert d["difference_absorbed_by_normalisation"] == (
        d["n_normalized_contiguous"] - d["n_raw_exact_contiguous"])


def test_the_authoritative_text_is_the_rendering_shown_to_the_extractor():
    val = json.loads((_D / "phase_a_theme_level_validation.json").read_text(
        encoding="utf-8"))
    assert "rendered_sha256" in val["authoritative_text"]


# ------------------------------------------------------------- final gate
def test_phase_a_final_gate_passes_on_all_174_units():
    v2 = json.loads((_D / "phase_a_accepted_v2.json").read_text(encoding="utf-8"))
    g = v2["gate"]
    assert g["pass"] is True
    assert g["all_174_units_resolved"] is True
    assert g["units_resolved"] == "174/174"
    assert g["every_retained_theme_has_a_valid_quote"] is True
    assert g["moderator_quotes"] == 0
    assert g["themes_without_evidence"] == 0
    assert g["incomplete_results"] == 0
    assert g["rejected_quotes_retained_in_audit"] == 14
    assert len(v2["units"]) == 174


def test_accepted_v2_counts_are_rebuilt_from_the_units():
    v2 = json.loads((_D / "phase_a_accepted_v2.json").read_text(encoding="utf-8"))
    assert v2["n_themes"] == sum(u["n_themes"] for u in v2["units"])
    assert v2["n_quotes"] == sum(u["n_quotes"] for u in v2["units"])
    assert v2["n_units"] == 174


def test_tokens_separate_the_original_batch_from_the_repair():
    t = json.loads((_D / "phase_a_accepted_v2.json").read_text(
        encoding="utf-8"))["tokens"]
    assert t["original_batch"]["input_tokens"] == 452273
    assert t["evidence_repair"]["input_tokens"] > 0
    assert t["total_input"] == (t["original_batch"]["input_tokens"]
                                + t["evidence_repair"]["input_tokens"])
    assert t["gemini_cost_status"] == "NOT_CALCULATED_RATE_NOT_VERIFIED"


def test_post_a_replan_uses_observed_not_estimated_counts():
    """
    The replan must be keyed to the 526 themes actually observed, never to the 925 that
    were planned for. This test asserts the substance, not the wording: it previously
    named keys the rebuilt artefact no longer carries and so stopped guarding anything.
    """
    r = json.loads((_D / "POST_A_REPLAN.json").read_text(encoding="utf-8"))
    v2 = json.loads((_D / "phase_a_accepted_v2.json").read_text(encoding="utf-8"))
    assert r["status"] == "REBUILT_ON_OBSERVED_PHASE_A"
    assert r["binding_source"].endswith("phase_a_accepted_v2.json")

    obs = r["observed"]
    assert obs["n_themes"] == v2["n_themes"] == 526
    assert obs["n_units"] == v2["n_units"] == 174
    assert obs["n_quotes"] == v2["n_quotes"]
    assert sum(obs["per_question"].values()) == v2["n_themes"]
    assert sum(obs["per_condition"].values()) == v2["n_themes"]

    # The superseded planning figure is recorded as superseded, not quietly dropped.
    assert r["superseded_planning_total"] == 925
    assert r["observed"]["n_themes"] < r["superseded_planning_total"]

    # No Gemini rate has ever been verified, so no Gemini cost may be stated.
    assert r["gemini_cost_status"] == "NOT_CALCULATED_RATE_NOT_VERIFIED"
    assert r["stage_d_status"] == "DEFERRED"


def test_post_a_replan_is_a_snapshot_taken_at_stage_b():
    """
    `stages_not_executed` is true as of the moment the replan was built, and stages C-F2
    have since run. Anyone reading this artefact needs the two facts together, so the
    test states them rather than letting the stale list read as current.
    """
    r = json.loads((_D / "POST_A_REPLAN.json").read_text(encoding="utf-8"))
    assert r["stages_executed_here"] == ["B_CANONICAL_TAXONOMY"]
    assert set(r["stages_not_executed"]) == {"C", "D", "E1", "E2", "E3", "F1", "F2"}
    curves = _ROOT / "analysis/production_evaluation/inductive_curves"
    assert (curves / "inductive_curves_v2_full.json").exists(), (
        "stages C-F2 have since executed; this artefact is a planning snapshot, "
        "not a current status report")
