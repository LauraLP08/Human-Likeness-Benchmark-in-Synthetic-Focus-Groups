"""
Offline tests for the blinded cross-model absence audit. No API call is made here and
none has been made at all: the build is at the pre-submission stopping point.

Each of the four corrections applied before Stage 1 is demonstrated to FAIL under a
planted violation, so none of these checks can be vacuous:

  1. Stage-1 gate      planting THRESHOLD_A = 0.80 must move the exact gate
  2. Manifest split    planting an answer-key token in the public manifest must be caught,
                       and deleting the sealed directory must not stop requests building
  3. Repetition claim  planting the overstated phrase must be caught in any artefact
  4. Sensitivity       planting a gate-failed speaker, an empty union, or an unresolved
                       cell must never reach a bound
"""
from __future__ import annotations

import csv
import inspect
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import absence_audit_build as B      # noqa: E402
import absence_audit_rules as R      # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/salience_absence_audit"
_SEALED = _OUT / "sealed"
_RES = _ROOT / "analysis/production_evaluation/results"


@pytest.fixture(scope="module")
def built():
    return B.build()


@pytest.fixture(scope="module")
def manifest():
    return json.loads((_OUT / "batch_manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def public():
    return json.loads(
        (_OUT / "calibration_request_manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sealed_ref():
    return json.loads(
        (_SEALED / "calibration_reference_SEALED.json").read_text(encoding="utf-8"))


# =====================================================================
# universe
# =====================================================================
def test_universe_is_derived_and_reconciles(built):
    u = built["universe"]
    assert u["pass"] is True, u["problems"]
    assert u["hard_coded"] is False
    assert u["n_documents"] * u["n_subthemes"] - u["n_verified_present"] \
        == u["n_absence_decisions_derived"] == 260


def test_universe_matches_the_source_table_row_for_row(built):
    src = set()
    for r in csv.DictReader(
            (_RES / "thematic_code_presence_long.csv").open(encoding="utf-8")):
        if not (r["present"] == "True" and r["quote_verified"] == "True"):
            k = f"human::{r['fg']}" if r["side"] == "human" else r["physical_run"]
            src.add((k, r["subtheme_id"]))
    assert {(r["doc_key"], r["subtheme_id"])
            for r in built["universe"]["rows"]} == src


def test_planted_a_changed_presence_table_changes_the_universe(monkeypatch):
    """PLANTED VIOLATION: a hard-coded 260 would survive this; the derivation must not."""
    real = B.presence_grid()
    victim = next(k for k, v in sorted(real.items()) if v is True)
    monkeypatch.setattr(B, "presence_grid", lambda: {**real, victim: False})
    u = B.absence_universe()
    assert u["n_absence_decisions_derived"] == 261
    assert u["n_verified_present"] == 124 and len(u["rows"]) == 261


def test_planted_an_incomplete_presence_table_aborts_the_build(monkeypatch):
    real = B.presence_grid()
    monkeypatch.setattr(
        B, "presence_grid",
        lambda: {k: v for i, (k, v) in enumerate(sorted(real.items())) if i})
    u = B.absence_universe()
    assert u["pass"] is False
    assert any("absent from the source table" in p or "384" in p for p in u["problems"])


# =====================================================================
# CORRECTION 1 — explicit prospective Stage-1 gate
# =====================================================================
def test_wilson_is_correct_and_returns_null_on_an_empty_denominator():
    w = R.wilson(59, 63)
    assert w["lower"] == 0.8478 and w["upper"] > w["point"] > w["lower"]
    assert R.wilson(0, 0)["lower"] is None
    with pytest.raises(ValueError):
        R.wilson(5, 3)


def test_threshold_a_is_derived_from_a_declared_tolerance_not_from_0_80():
    assert R.THRESHOLD_A == round(1 / 1.20, 4) == 0.8333
    assert R.THRESHOLD_A != 0.80
    assert R.THRESHOLD_B == 0.50


def test_planted_moving_threshold_a_to_0_80_moves_the_exact_gate(monkeypatch):
    """
    PLANTED VIOLATION: if the exact counts were hard-coded rather than computed from the
    threshold, swapping in the unsupported 0.80 convention would change nothing.
    """
    codes = sorted(B.codebook())
    cal = B.calibration_selection(B.codebook())
    before = B.stage1_gate_specification(sorted(cal["doc_keys"]), codes)
    monkeypatch.setattr(R, "THRESHOLD_A", 0.80)
    after = B.stage1_gate_specification(sorted(cal["doc_keys"]), codes)
    k_before = before["exact_gate"]["band_a_requires"][
        "detected_on_original_present_at_least"]
    k_after = after["exact_gate"]["band_a_requires"][
        "detected_on_original_present_at_least"]
    assert k_before == 59 and k_after < k_before


def test_the_exact_gate_is_resolved_to_integer_counts(manifest):
    g = manifest["stage1_gate"]
    assert g["frozen_before_submission"] is True
    assert g["n_original_present_quote_verified"] == 63
    assert g["n_cells_returned"] == 154
    a = g["exact_gate"]["band_a_requires"]
    b = g["exact_gate"]["band_b_requires"]
    assert a["detected_on_original_present_at_least"] == 59
    assert a["repetition_agreement_at_least"] == 138
    assert a["unresolved_at_most"] == 21
    assert b["detected_on_original_present_at_least"] == 40
    assert b["repetition_agreement_at_least"] == 90


def test_the_designated_set_could_never_pass_and_is_not_the_denominator(manifest):
    """The reason the denominator is 63 and not 11, asserted rather than assumed."""
    g = manifest["stage1_gate"]
    assert R.wilson(11, 11)["lower"] == 0.7412 < R.THRESHOLD_A
    assert g["max_achievable_lower_bound_on_designated_present_only"] == 0.7412
    assert "designated cases guarantee" in g["denominator_rule"]


@pytest.mark.parametrize("det,agree,unres,expect", [
    (63, 154, 0, R.GATE_A),          # flawless
    (59, 138, 21, R.GATE_A),         # exactly at the gate
    (58, 138, 0, R.GATE_B),          # one detection short
    (59, 137, 0, R.GATE_B),          # one agreement short
    (59, 138, 22, R.GATE_B),         # unresolved too wide
    (40, 90, 0, R.GATE_B),           # bottom of band B
    (39, 154, 0, R.GATE_C),          # detection below one half
    (63, 89, 0, R.GATE_C),           # stability below one half
])
def test_stage1_gate_boundaries(det, agree, unres, expect):
    out = R.stage1_gate(det, 63, agree, 154, unres)
    assert out["outcome"] == expect, out["reasons"]


def test_band_b_permits_only_the_neutral_label():
    out = R.stage1_gate(50, 63, 120, 154, 5)
    assert out["outcome"] == R.GATE_B
    assert out["permitted_label"] == "AUDITOR_DID_NOT_FIND_EVIDENCE"
    assert R.ABSENCE_CORROBORATED in out["forbidden_labels"]


def test_band_a_prints_the_residual_miss_rate():
    out = R.stage1_gate(63, 63, 154, 154, 0)
    assert out["outcome"] == R.GATE_A
    assert out["residual_miss_rate_upper"] == round(
        1 - out["detection_rate"]["lower"], 4)


def test_band_c_stops_stage_2():
    out = R.stage1_gate(10, 63, 154, 154, 0)
    assert out["outcome"] == R.GATE_C
    assert "Stage 2 is not submitted" in out["consequence"]


def test_the_undefined_phrase_too_low_appears_nowhere():
    """PLANTED VIOLATION: the phrase the correction removed must not creep back."""
    for p in (_OUT / "AUDIT_PROTOCOL.md", _OUT / "stage1_gate.json",
              _ROOT / "scripts/absence_audit_rules.py"):
        assert "too low" not in p.read_text(encoding="utf-8").lower(), p


def test_gate_reports_intervals_not_bare_points():
    out = R.stage1_gate(59, 63, 138, 154, 5)
    for k in ("detection_rate", "repetition_stability", "unresolved_rate"):
        assert set(out[k]) >= {"k", "n", "point", "lower", "upper"}


# =====================================================================
# CORRECTION 5 — subtheme-specific eligibility for corroboration
# =====================================================================
# The 11 production subtheme ids, written out literally.
#
# This is DELIBERATELY not derived from B.codebook(): a derived fixture would make
# test_the_eligibility_code_set_matches_production tautological and could not detect
# drift at all. The literal is the claim; the test below is what checks it.
#
# It previously read "D.1", an identifier that exists nowhere in the frozen codebook.
# Every eligibility test then ran against a phantom subtheme while silently omitting the
# real one, so the rule was never exercised on D.
_CODES = ["A.1", "A.2", "A.3", "B.1", "B.2", "B.3", "B.4", "C.1", "C.2", "C.3", "D"]


def _all_controls_detected(codes=None):
    return {c: R.AUD_EVIDENCE for c in (codes or _CODES)}


def test_the_eligibility_code_set_matches_production():
    """
    Guards against identifier drift in either direction: a fixture id that does not
    exist in the codebook, or a codebook id the fixture never exercises.
    """
    production = set(B.codebook())
    assert set(_CODES) == production, {
        "in_fixture_only": sorted(set(_CODES) - production),
        "in_codebook_only": sorted(production - set(_CODES))}
    assert len(_CODES) == len(set(_CODES)) == 11
    assert "D.1" not in _CODES and "D" in _CODES


def test_the_eligibility_code_set_matches_the_sealed_reference(sealed_ref):
    """The sealed designated cases must cover the same ids, from the other direction."""
    sealed_ids = {c["subtheme_id"] for c in sealed_ref["cases"]}
    assert sealed_ids == set(_CODES) == set(B.codebook())


def test_production_adjacent_family_ids_are_real():
    """The same drift could occur in production code; _ADJACENT is checked too."""
    assert B._ADJACENT <= set(B.codebook())


def test_eligibility_requires_the_control_to_be_detected():
    e = R.subtheme_control_eligibility(
        {"A.1": R.AUD_EVIDENCE, "A.2": R.AUD_NONE, "A.3": R.AUD_UNRESOLVED},
        subthemes=["A.1", "A.2", "A.3", "B.1"])
    assert e["A.1"]["eligible_for_corroboration"] is True
    assert e["A.1"]["status"] == R.ELIGIBLE
    assert e["A.2"]["status"] == R.INELIGIBLE_NOT_DETECTED
    assert e["A.3"]["status"] == R.INELIGIBLE_UNRESOLVED
    assert e["B.1"]["status"] == R.INELIGIBLE_MISSING       # no control returned at all
    for s in ("A.2", "A.3", "B.1"):
        assert e[s]["eligible_for_corroboration"] is False


def test_corroboration_requires_band_a_and_the_subtheme_control():
    e = R.subtheme_control_eligibility(_all_controls_detected(), _CODES)
    ok = R.absence_label(R.GATE_A, "A.1", R.AUD_NONE, e)
    assert ok["label"] == R.ABSENCE_CORROBORATED and ok["downgraded"] is False


def test_planted_one_failed_subtheme_control_blocks_that_subtheme_at_59_of_63():
    """
    PLANTED VIOLATION — the case the correction exists for.

    The global gate is exactly at band A (59/63 detections, 138/154 agreement), yet the
    designated control for B.2 was not detected. Every non-detection for B.2 must stay
    AUDITOR_DID_NOT_FIND_EVIDENCE while the other subthemes corroborate normally.
    """
    g = R.stage1_gate(59, 63, 138, 154, 0)
    assert g["outcome"] == R.GATE_A, g["reasons"]

    controls = _all_controls_detected()
    controls["B.2"] = R.AUD_NONE                      # the one complete control failure
    e = R.subtheme_control_eligibility(controls, _CODES)

    blocked = R.absence_label(g["outcome"], "B.2", R.AUD_NONE, e)
    assert blocked["label"] == R.AUD_NONE == "AUDITOR_DID_NOT_FIND_EVIDENCE"
    assert blocked["label"] != R.ABSENCE_CORROBORATED
    assert blocked["downgraded"] is True
    assert "B.2" in blocked["reason"] and R.INELIGIBLE_NOT_DETECTED in blocked["reason"]

    for other in [c for c in _CODES if c != "B.2"]:
        assert R.absence_label(g["outcome"], other, R.AUD_NONE, e)["label"] \
            == R.ABSENCE_CORROBORATED, other


def test_planted_an_unresolved_subtheme_control_also_blocks_at_band_a():
    g = R.stage1_gate(59, 63, 138, 154, 0)
    controls = _all_controls_detected()
    controls["C.3"] = R.AUD_UNRESOLVED
    e = R.subtheme_control_eligibility(controls, _CODES)
    out = R.absence_label(g["outcome"], "C.3", R.AUD_NONE, e)
    assert out["label"] == R.AUD_NONE and out["downgraded"] is True
    assert R.INELIGIBLE_UNRESOLVED in out["reason"]


def test_a_contested_absence_survives_a_failed_subtheme_control():
    """A gate-passed quotation is verified against the transcript, not the auditor."""
    g = R.stage1_gate(59, 63, 138, 154, 0)
    controls = _all_controls_detected()
    controls["B.2"] = R.AUD_NONE
    e = R.subtheme_control_eligibility(controls, _CODES)
    out = R.absence_label(g["outcome"], "B.2", R.AUD_EVIDENCE, e)
    assert out["label"] == R.ABSENCE_CONTESTED and out["downgraded"] is False
    assert "unaffected by the subtheme eligibility rule" in out["reason"]


def test_contested_survives_even_under_band_b_and_band_c():
    e = R.subtheme_control_eligibility({}, _CODES)          # every control missing
    for band in (R.GATE_B, R.GATE_C):
        assert R.absence_label(band, "A.1", R.AUD_EVIDENCE, e)["label"] \
            == R.ABSENCE_CONTESTED


def test_band_b_never_corroborates_however_good_the_subtheme_control():
    e = R.subtheme_control_eligibility(_all_controls_detected(), _CODES)
    out = R.absence_label(R.GATE_B, "A.1", R.AUD_NONE, e)
    assert out["label"] == R.AUD_NONE and out["downgraded"] is True
    assert R.GATE_B in out["reason"]


def test_unresolved_absences_are_untouched_by_the_eligibility_rule():
    e = R.subtheme_control_eligibility({}, _CODES)
    out = R.absence_label(R.GATE_A, "A.1", R.AUD_UNRESOLVED, e)
    assert out["label"] == R.ABSENCE_UNRESOLVED and out["downgraded"] is False


def test_an_unknown_auditor_verdict_is_rejected():
    e = R.subtheme_control_eligibility(_all_controls_detected(), _CODES)
    with pytest.raises(ValueError):
        R.absence_label(R.GATE_A, "A.1", "SOMETHING_ELSE", e)


def test_the_manifest_records_the_eligibility_rule(manifest):
    r = manifest["stage1_gate"]["subtheme_eligibility_rule"]
    assert r["applies_to"] == R.ABSENCE_CORROBORATED
    assert len(r["requires_both"]) == 2
    assert r["n_designated_controls"] == 11 and r["one_control_per_subtheme"] is True
    assert "contestable regardless" in r["contested_cells_unaffected"]
    band_a = manifest["stage1_gate"]["exact_gate"]["band_a_requires"]
    assert "NECESSARY_BUT_NOT_SUFFICIENT" in band_a


def test_every_subtheme_has_exactly_one_designated_positive_control(sealed_ref):
    """
    The rule is only enforceable because coverage is complete — one positive control for
    each of the 11 REAL ids, checked by identity and not merely by count.
    """
    controls = [c for c in sealed_ref["cases"]
                if c["original_status"] == R.ORIGINAL_PRESENT]
    assert len(controls) == 11
    ids = [c["subtheme_id"] for c in controls]
    assert sorted(ids) == sorted(_CODES) == sorted(B.codebook())
    assert len(set(ids)) == 11, "a subtheme with two controls would mask one with none"


# ------------------------------------------------ the previously untested subtheme
@pytest.mark.parametrize("verdict,status", [
    (R.AUD_NONE, R.INELIGIBLE_NOT_DETECTED),
    (R.AUD_UNRESOLVED, R.INELIGIBLE_UNRESOLVED),
])
def test_a_failed_or_unresolved_D_control_blocks_corroboration_of_D(verdict, status):
    """(1) D is a real subtheme and the eligibility rule must bind on it."""
    g = R.stage1_gate(59, 63, 138, 154, 0)
    assert g["outcome"] == R.GATE_A
    controls = _all_controls_detected()
    controls["D"] = verdict
    e = R.subtheme_control_eligibility(controls, _CODES)
    assert e["D"]["status"] == status
    assert e["D"]["eligible_for_corroboration"] is False

    out = R.absence_label(g["outcome"], "D", R.AUD_NONE, e)
    assert out["label"] == R.AUD_NONE == "AUDITOR_DID_NOT_FIND_EVIDENCE"
    assert out["label"] != R.ABSENCE_CORROBORATED and out["downgraded"] is True
    assert status in out["reason"]

    # and the other ten are unaffected
    for other in [c for c in _CODES if c != "D"]:
        assert R.absence_label(g["outcome"], other, R.AUD_NONE, e)["label"] \
            == R.ABSENCE_CORROBORATED, other


def test_a_detected_D_control_permits_corroboration_only_under_band_a():
    """(2) The subtheme control is necessary, never sufficient on its own."""
    e = R.subtheme_control_eligibility(_all_controls_detected(), _CODES)
    assert e["D"]["eligible_for_corroboration"] is True

    a = R.absence_label(R.GATE_A, "D", R.AUD_NONE, e)
    assert a["label"] == R.ABSENCE_CORROBORATED and a["downgraded"] is False

    for band in (R.GATE_B, R.GATE_C):
        out = R.absence_label(band, "D", R.AUD_NONE, e)
        assert out["label"] == R.AUD_NONE and out["downgraded"] is True
        assert band in out["reason"]


def test_a_contested_D_absence_survives_a_failed_D_control():
    g = R.stage1_gate(59, 63, 138, 154, 0)
    controls = _all_controls_detected()
    controls["D"] = R.AUD_NONE
    e = R.subtheme_control_eligibility(controls, _CODES)
    assert R.absence_label(g["outcome"], "D", R.AUD_EVIDENCE, e)["label"] \
        == R.ABSENCE_CONTESTED


def test_a_phantom_subtheme_is_ineligible_rather_than_silently_accepted():
    """What the old fixture was really doing, now asserted as the correct behaviour."""
    e = R.subtheme_control_eligibility(_all_controls_detected(), _CODES)
    assert "D.1" not in e
    out = R.absence_label(R.GATE_A, "D.1", R.AUD_NONE, e)
    assert out["label"] == R.AUD_NONE and out["downgraded"] is True
    assert R.INELIGIBLE_MISSING in out["reason"]


# =====================================================================
# CORRECTION 6 — Wilson intervals are gate summaries, not confirmatory
# =====================================================================
def test_wilson_caveat_states_clustering_and_dependence():
    c = R.WILSON_CAVEAT.lower()
    assert "not a confirmatory confidence interval" in c
    assert "clustered within 14 documents" in c
    assert "dependent" in c and "anticonservative" in c


def test_the_caveat_reaches_the_gate_artefact(manifest):
    t = manifest["stage1_gate"]["thresholds"]
    assert t["interval_status"] == R.WILSON_CAVEAT
    proto = " ".join((_OUT / "AUDIT_PROTOCOL.md")
                     .read_text(encoding="utf-8").replace("*", "").split())
    assert "not confirmatory confidence intervals" in proto
    assert "clustered within 14 documents" in proto


# =====================================================================
# CORRECTION 7 — Band B makes no per-cell claim
# =====================================================================
def test_band_b_rationale_is_about_the_instrument_not_the_cell(manifest):
    t = manifest["stage1_gate"]["thresholds"]
    d = t["THRESHOLD_B_derivation"].lower()
    assert "fails to detect more known-localisable positive controls than it detects" in d
    assert "no statement is made about whether any individual" in \
        t["THRESHOLD_B_makes_no_per_cell_claim"].lower()


def test_planted_the_per_cell_overclaim_is_caught():
    """PLANTED VIOLATION: the checker must not be vacuous."""
    assert B.per_cell_overclaim_problems(
        "so a non-detection is more likely a miss than a true absence")
    assert B.per_cell_overclaim_problems("the corroboration reverses sign")
    assert B.per_cell_overclaim_problems(
        "the auditor fails to detect more controls than it detects") == []


def test_no_artefact_makes_the_per_cell_claim():
    for p in [_OUT / "AUDIT_PROTOCOL.md", _OUT / "batch_manifest.json",
              _OUT / "stage1_gate.json", _ROOT / "scripts/absence_audit_rules.py",
              _ROOT / "scripts/absence_audit_build.py"]:
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".py":
            text = _strip_per_cell_ban_definition(text)
        assert B.per_cell_overclaim_problems(text) == [], p.name


def _strip_per_cell_ban_definition(src: str) -> str:
    start = src.find("BANNED_PER_CELL_CLAIMS = (")
    if start == -1:
        return src
    return src[:start] + src[src.index(")", src.index('"', start)):]


def test_the_per_cell_stripper_does_not_hide_real_prose():
    src = ('before\nBANNED_PER_CELL_CLAIMS = (\n    "probably a miss",\n)\n'
           'after: the corroboration reverses sign\n')
    out = _strip_per_cell_ban_definition(src)
    assert "before" in out and "after" in out
    assert B.per_cell_overclaim_problems(out)


# =====================================================================
# CORRECTION 2 — manifest split, no read dependency on the sealed file
# =====================================================================
def test_public_manifest_contains_no_answer_key(public):
    assert B.public_manifest_problems(public) == []
    assert public["classification"].endswith("REQUEST_MANIFEST")
    for d in public["documents"]:
        assert set(d) == {"blinded_document_id", "rendered_sha256", "candidate_order",
                          "n_turns", "n_participants", "prompt_words"}


def test_planted_an_answer_key_token_in_the_public_manifest_is_caught(public):
    """PLANTED VIOLATION: the purity check must not be vacuous."""
    poisoned = json.loads(json.dumps(public))
    poisoned["documents"][0]["original_status"] = R.ORIGINAL_ABSENCE
    probs = B.public_manifest_problems(poisoned)
    assert probs, "an answer key slipped through the public-manifest check"
    assert any("original_status" in p for p in probs)
    assert B.public_manifest_problems(
        {"x": "human::fg1"}), "a document key must be caught"


def test_sealed_reference_holds_what_the_public_manifest_must_not(sealed_ref):
    assert sealed_ref["classification"].endswith("SEALED")
    assert sealed_ref["n_designated_cases"] == 22
    for c in sealed_ref["cases"]:
        assert {"original_status", "doc_key", "side", "subtheme_id"} <= set(c)
        assert c["original_status"] in (R.ORIGINAL_PRESENT, R.ORIGINAL_ABSENCE)
    assert B.public_manifest_problems(sealed_ref), \
        "the sealed file is expected to fail the public check; that is its purpose"


def test_planted_requests_still_build_with_the_sealed_directory_gone(monkeypatch,
                                                                    built):
    """
    PLANTED VIOLATION: point the sealed directory at a path that does not exist. If the
    request builder had any read dependency on the sealed reference, this would raise.
    """
    monkeypatch.setattr(B, "_SEALED", _OUT / "no_such_sealed_dir_zzz")
    assert not B._SEALED.exists()
    cb = B.codebook()
    codes = sorted(cb)
    store = B.render_store(cb, codes)
    rows = [{"blinded_document_id": b} for b in sorted(store)]
    reqs = B.build_requests(rows, store, lambda bid: "STAGE2_COMPLETE",
                            "p", "s", codes)
    assert len(reqs) == 35
    assert all(r["n_candidates"] == 11 for r in reqs)


def test_the_request_builder_never_names_a_sealed_path():
    src = inspect.getsource(B.build_requests)
    low = src.lower()
    for token in ("sealed", "original_status", "doc_key", "reference"):
        assert token not in low, f"build_requests references {token!r}"
    params = list(inspect.signature(B.build_requests).parameters)
    assert "sealed" not in " ".join(params).lower()


def test_the_render_store_is_keyed_only_by_opaque_ids(built):
    store = B.render_store(built["codebook"], built["codes"])
    assert len(store) == 35
    for k in store:
        assert k.startswith("DOC_") and len(k) == 14


def test_the_old_combined_manifest_is_gone():
    assert not (_OUT / "calibration_manifest.json").exists()
    assert not (_OUT / "sealed_document_mapping.json").exists()
    assert (_SEALED / "sealed_document_mapping.json").exists()


def test_calibration_original_status_matches_the_source(sealed_ref):
    grid = B.presence_grid()
    for c in sealed_ref["cases"]:
        want = c["original_status"] == R.ORIGINAL_PRESENT
        assert grid[(c["doc_key"], c["subtheme_id"])] is want, c["case_id"]


def test_absent_cells_are_not_called_known_negatives(sealed_ref):
    """
    The file must DENY that these cells are ground truth. Banning the bare words would
    fail on the denial itself, so the affirmative constructions are what is checked.
    """
    txt = json.dumps(sealed_ref).lower()
    label = sealed_ref["labels"][R.ORIGINAL_ABSENCE].lower()
    assert "not a known negative" in label and "not ground truth" in label
    for affirmative in ("is a known negative", "are known negatives",
                        "is ground truth", "as ground truth", "known-negative"):
        assert affirmative not in txt, affirmative
    assert "reference_absent" not in txt
    assert R.ORIGINAL_ABSENCE == "ORIGINAL_GEMINI_ABSENCE"


# =====================================================================
# CORRECTION 3 — repetition independence is not overstated
# =====================================================================
def _strip_ban_definition(src: str) -> str:
    """
    The module that DEFINES the banned phrases necessarily contains them. Excise the
    literal tuple so the surrounding prose is still checked rather than exempted.
    """
    start = src.find("BANNED_REPETITION_PHRASES = (")
    if start == -1:
        return src
    end = src.index(")", src.index('"', start))
    return src[:start] + src[end:]


def test_no_artefact_overstates_repetition_independence():
    for p in [_OUT / "AUDIT_PROTOCOL.md", _OUT / "batch_manifest.json",
              _OUT / "calibration_request_manifest.json", _OUT / "stage1_gate.json",
              _ROOT / "scripts/absence_audit_rules.py",
              _ROOT / "scripts/absence_audit_build.py"]:
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".py":
            text = _strip_ban_definition(text)
        probs = B.repetition_language_problems(text)
        assert probs == [], f"{p.name}: {probs}"


def test_the_ban_definition_stripper_does_not_hide_real_prose():
    """The excision must remove only the tuple, not neighbouring text."""
    src = ('prose before\nBANNED_REPETITION_PHRASES = (\n    "two independent '
           'repetitions",\n)\nprose after with independent repetitions\n')
    out = _strip_ban_definition(src)
    assert "prose before" in out and "prose after" in out
    assert B.repetition_language_problems(out), \
        "prose outside the tuple must still be caught"


def test_planted_the_overstated_phrase_is_caught():
    """PLANTED VIOLATION: the language check must not be vacuous."""
    assert B.repetition_language_problems(
        "verified by two independent repetitions of the auditor")
    assert B.repetition_language_problems("the request was independently repeated")
    assert B.repetition_language_problems("ordinary prose about repetitions") == []


def test_the_correct_formulation_is_stated_in_the_artefacts(manifest):
    assert B.REPETITION_PHRASE in manifest["auditor"]["repetition_semantics"]
    assert "not two independent auditors" in \
        manifest["auditor"]["repetition_semantics"].replace(
            "are not two independent auditors", "not two independent auditors")
    assert "independent of Gemini" in manifest["auditor"]["cross_model_independence"]
    # markdown wraps lines and emboldens the phrase; compare on normalised text
    proto = " ".join((_OUT / "AUDIT_PROTOCOL.md")
                     .read_text(encoding="utf-8").replace("*", "").split())
    assert B.REPETITION_PHRASE in proto
    assert "stability of a single auditor" in proto


def test_the_cross_model_independence_claim_is_kept_and_scoped(manifest):
    """Claude IS independent of Gemini. That claim must survive the correction."""
    assert "Gemini" in manifest["auditor_rationale"]
    assert manifest["auditor"]["model"] == "claude-opus-5"


# =====================================================================
# CORRECTION 4 — separated sensitivity outputs and frozen speaker handling
# =====================================================================
_TURNS = {
    "T012": [{"speaker": "P2", "text": "I just cook whatever is quick, honestly.",
              "is_moderator": False}],
    "T013": [{"speaker": "Moderator", "text": "Does anyone feel differently about that?",
              "is_moderator": True}],
    "T014": [{"speaker": "P3", "text": "For me it is mostly about the cost of it.",
              "is_moderator": False}],
}


def _a(**kw):
    base = {"code_id": "A.1", "verdict": "EVIDENCE_FOUND", "reasoning": "r"}
    base.update(kw)
    return base


def _pass(turn, spk, quote):
    return R.evidence_gate(_a(turn_id=turn, speaker=spk, quotation=quote), _TURNS)


def test_speaker_union_and_intersection_are_both_recorded():
    g1 = _pass("T012", "P2", "cook whatever is quick")
    g2 = _pass("T014", "P3", "mostly about the cost")
    ev = R.speaker_evidence(g1, g2)
    assert ev["union"] == ["P2", "P3"] and ev["n_union"] == 2
    assert ev["intersection"] == [] and ev["n_intersection"] == 0
    same = R.speaker_evidence(g1, _pass("T012", "P2", "whatever is quick"))
    assert same["union"] == ["P2"] and same["intersection"] == ["P2"]


def test_planted_a_gate_failed_repetition_contributes_no_speaker():
    """PLANTED VIOLATION: a paraphrased quotation must not smuggle a speaker in."""
    good = _pass("T012", "P2", "cook whatever is quick")
    bad = _pass("T012", "P2", "I cook whatever is quick")        # paraphrase
    assert bad["gate"] == R.GATE_NOT_IN_TURN and bad["speaker"] is None
    ev = R.speaker_evidence(good, bad)
    assert ev["union"] == ["P2"] and ev["n_union"] == 1


def test_planted_moderator_evidence_contributes_no_speaker():
    mod = _pass("T013", "Moderator", "Does anyone feel differently")
    assert mod["gate"] == R.GATE_MODERATOR and mod["speaker"] is None
    assert R.speaker_evidence(mod, mod)["union"] == []


def test_unresolved_and_not_found_contribute_no_speaker():
    for v in ("NO_EVIDENCE_FOUND", "UNCERTAIN"):
        g = R.evidence_gate(_a(verdict=v), _TURNS)
        assert g["speaker"] is None
    assert R.speaker_evidence(None, None)["union"] == []


def test_participant_breadth_bounds_are_lower_mid_upper():
    out = R.participant_breadth_bounds(
        [{"doc_key": "d1", "subtheme_id": "A.1",
          "union_speakers": ["P2"], "intersection_speakers": ["P2"]},
         {"doc_key": "d1", "subtheme_id": "B.2",
          "union_speakers": ["P1", "P3"], "intersection_speakers": ["P1"]}],
        {"d1": 4})
    assert out["output"] == "participant_breadth_bounds"
    assert out["treatments"] == ["LOWER", "MID", "UPPER"] and out["primary"] == "LOWER"
    a, b = out["rows"]
    assert (a["lower_reach"], a["mid_reach"], a["upper_reach"]) == (0.0, 0.25, 0.25)
    assert (b["lower_reach"], b["mid_reach"], b["upper_reach"]) == (0.0, 0.25, 0.50)
    assert b["n_intersection"] == 1


def test_intersection_is_recorded_but_is_never_a_bound():
    out = R.participant_breadth_bounds(
        [{"doc_key": "d", "subtheme_id": "A.1",
          "union_speakers": ["P1", "P2"], "intersection_speakers": ["P1"]}], {"d": 4})
    assert out["intersection_is_a_bound"] is False
    r = out["rows"][0]
    assert r["upper_reach"] == 0.5                      # union, not intersection
    assert r["intersection_speakers"] == ["P1"]


def test_planted_a_contested_cell_with_no_gated_speaker_is_an_error():
    """PLANTED VIOLATION: an unsupported contested cell must not silently score 1/n."""
    with pytest.raises(ValueError, match="no gate-passed speaker"):
        R.participant_breadth_bounds(
            [{"doc_key": "d", "subtheme_id": "A.1", "union_speakers": [],
              "intersection_speakers": []}], {"d": 4})


def test_planted_an_intersection_wider_than_the_union_is_an_error():
    with pytest.raises(ValueError, match="subset"):
        R.participant_breadth_bounds(
            [{"doc_key": "d", "subtheme_id": "A.1", "union_speakers": ["P1"],
              "intersection_speakers": ["P1", "P9"]}], {"d": 4})


def test_a_zero_denominator_is_an_error_not_a_silent_zero():
    with pytest.raises(ValueError):
        R.participant_breadth_bounds(
            [{"doc_key": "d", "subtheme_id": "A.1", "union_speakers": ["P1"],
              "intersection_speakers": []}], {"d": 0})


def test_recurrence_sensitivity_is_a_separate_output_with_two_treatments():
    rows = [
        {"condition": "enriched", "canonical_replication_index": 1, "fg": "fg1",
         "subtheme_id": "A.1", "doc_key": "r1", "present": True},
        {"condition": "enriched", "canonical_replication_index": 1, "fg": "fg2",
         "subtheme_id": "A.1", "doc_key": "r2", "present": False},
        {"condition": "enriched", "canonical_replication_index": 1, "fg": "fg3",
         "subtheme_id": "A.1", "doc_key": "r3", "present": False},
    ]
    out = R.across_group_recurrence_sensitivity(rows, {("r2", "A.1")})
    assert out["output"] == "across_group_recurrence_sensitivity"
    assert out["treatments"] == ["ORIGINAL", "CONTESTED_AS_PRESENT"]
    assert out["primary"] == "ORIGINAL"
    row = out["rows"][0]
    assert row["n_fgs_original"] == 1 and row["n_fgs_contested_as_present"] == 2
    assert row["delta"] == 1 and out["n_changed"] == 1


def test_recurrence_has_no_mid_treatment_and_no_reach():
    out = R.across_group_recurrence_sensitivity([], set())
    assert "MID" not in out["treatments"]
    assert out["no_mid_treatment"] == "a focus group either counts or does not"
    assert out["unresolved_enter_any_treatment"] is False


def test_planted_an_unresolved_cell_never_enters_either_output():
    """
    PLANTED VIOLATION: unresolved cells are supplied to neither function. Both outputs
    declare it, and passing none leaves both empty.
    """
    b = R.participant_breadth_bounds([], {"d": 4})
    assert b["n_contested_cells"] == 0 and b["unresolved_enter_any_bound"] is False
    r = R.across_group_recurrence_sensitivity(
        [{"condition": "c", "canonical_replication_index": 1, "fg": "fg1",
          "subtheme_id": "A.1", "doc_key": "d", "present": False}], set())
    assert r["rows"][0]["delta"] == 0 and r["n_changed"] == 0


def test_the_two_sensitivity_outputs_are_not_merged():
    b = R.participant_breadth_bounds([], {})
    r = R.across_group_recurrence_sensitivity([], set())
    assert b["output"] != r["output"]
    assert set(b["treatments"]) & set(r["treatments"]) == set()


# =====================================================================
# blinding, request shape, gate order — unchanged guarantees
# =====================================================================
def test_no_forbidden_term_in_any_authored_scaffolding(manifest):
    assert manifest["blinding"]["scaffold_failures"] == []
    assert manifest["blinding"]["check"] == "SPLIT"


def test_no_hard_provenance_leak_in_any_transcript(manifest):
    assert manifest["blinding"]["verbatim_leak_failures"] == []


def test_planted_scaffold_gate_actually_fires():
    assert B.scaffold_purity_problems("assess whether the code is absent here")
    assert B.scaffold_purity_problems("this is the enriched condition for fg3")
    assert B.scaffold_purity_problems("was this missed by the previous pass") == \
        ["forbidden term in authored scaffolding: 'missed'"]


def test_planted_hard_leak_gate_fires_on_underscore_adjacent_identifiers():
    """The boundary must not treat '_' as a word character."""
    assert B.transcript_leak_problems("this came from macho_meals_fg4_run01")
    assert B.transcript_leak_problems("coded by gemini")


def test_ordinary_english_never_trips_the_verbatim_gate():
    for s in ["you'd be missing out on certain nutrients",
              "more room for error out in the suburbs",
              "we reach for all the reasons why we can't",
              "that's sort of the baseline",
              "it's very hard to replicate that",
              "it's just absent, that's a proper constraint"]:
        assert B.transcript_leak_problems(s) == [], s


def test_no_prompt_body_contains_provenance_or_status(built):
    cb, codes = built["codebook"], built["codes"]
    for d in B.documents()[:6]:
        _, body, _ = B.render_request(d, B.render_blinded(d), codes, cb)
        for token in (d["doc_key"], "SEALED", "ORIGINAL_GEMINI", "original_status"):
            assert token not in body


def test_document_ids_are_opaque_and_unique():
    ids = [B.blind_id(d["doc_key"]) for d in B.documents()]
    assert len(set(ids)) == 35
    assert all(i.startswith("DOC_") and len(i) == 14 for i in ids)


def test_every_request_carries_the_full_codebook(manifest):
    for r in manifest["requests"]:
        assert r["n_candidates"] == 11
        assert r["n_absence_cells"] + r["n_present_control_cells"] == 11


def test_absence_and_control_cells_reconcile(manifest):
    t = manifest["total_corpus"]
    assert t["n_absence_cells"] == 260 and t["n_present_control_cells"] == 125


def test_cache_keys_are_unique_and_repetition_sensitive(manifest):
    keys = [k for r in manifest["requests"] for k in r["cache_keys"].values()]
    assert len(keys) == len(set(keys)) == 70
    assert manifest["cache_key_collisions"] == 0
    for r in manifest["requests"]:
        assert r["cache_keys"]["1"] != r["cache_keys"]["2"]


def test_no_sampling_parameter_is_transmitted(manifest):
    a = manifest["auditor"]
    assert not (a["temperature_transmitted"] or a["top_p_transmitted"]
                or a["top_k_transmitted"])


def test_no_api_call_has_been_made(manifest):
    assert manifest["status"] == "PRE_SUBMISSION_NO_API_CALL_MADE"


# ------------------------------------------------------ evidence gate
def test_gate_passes_an_exact_local_quotation():
    g = _pass("T012", "P2", "cook whatever is quick")
    assert g["gate"] == R.GATE_PASS and g["speaker"] == "P2"


def test_gate_tolerates_typography_but_not_paraphrase():
    assert _pass("T012", "P2", "I  just cook whatever is QUICK")["gate"] == R.GATE_PASS
    assert _pass("T012", "P2", "I cook whatever is quick")["gate"] == R.GATE_NOT_IN_TURN


def test_gate_rejects_an_invented_turn_and_a_missing_quotation():
    assert _pass("T999", "P2", "x")["gate"] == R.GATE_NO_TURN
    assert _pass("T012", "P2", "  ")["gate"] == R.GATE_NO_QUOTE


def test_gate_rejects_a_misattributed_quotation():
    assert _pass("T012", "P9", "cook whatever is quick")["gate"] \
        == R.GATE_SPEAKER_MISMATCH


def test_gate_never_upgrades_and_never_repairs():
    for v in ("NO_EVIDENCE_FOUND", "UNCERTAIN"):
        g = R.evidence_gate(_a(verdict=v), _TURNS)
        assert g["verdict_after_gate"] == v and g["downgraded"] is False
    assert "quotation" not in _pass("T012", "P2", "not in here")


@pytest.mark.parametrize("pair,expect", [
    (["EVIDENCE_FOUND", "EVIDENCE_FOUND"], R.AUD_EVIDENCE),
    (["NO_EVIDENCE_FOUND", "NO_EVIDENCE_FOUND"], R.AUD_NONE),
    (["EVIDENCE_FOUND", "NO_EVIDENCE_FOUND"], R.AUD_UNRESOLVED),
    (["UNCERTAIN", "UNCERTAIN"], R.AUD_UNRESOLVED),
])
def test_repetition_rule(pair, expect):
    assert R.reconcile_repetitions(pair)["verdict"] == expect


def test_a_disagreement_is_never_broken_by_a_third_opinion():
    assert R.reconcile_repetitions(
        ["EVIDENCE_FOUND", "NO_EVIDENCE_FOUND", "EVIDENCE_FOUND"]
    )["verdict"] == R.AUD_UNRESOLVED


def test_gate_runs_before_reconciliation_not_after():
    r1 = _pass("T012", "P2", "cook whatever is quick")
    r2 = _pass("T012", "P2", "I never cook at all")
    assert R.reconcile_repetitions(
        [r1["verdict_after_gate"], r2["verdict_after_gate"]]
    )["verdict"] == R.AUD_UNRESOLVED


def test_cross_model_outcomes():
    assert R.cross_model_outcome(False, R.AUD_NONE) == R.ABSENCE_CORROBORATED
    assert R.cross_model_outcome(False, R.AUD_EVIDENCE) == R.ABSENCE_CONTESTED
    assert R.cross_model_outcome(False, R.AUD_UNRESOLVED) == R.ABSENCE_UNRESOLVED
    assert R.cross_model_outcome(True, R.AUD_EVIDENCE) == R.PRESENCE_CONCURRED
    assert R.cross_model_outcome(True, R.AUD_NONE) == R.PRESENCE_NOT_CONCURRED


# --------------------------------------------------- calibration scoring
def test_calibration_uses_the_new_labels_and_prints_denominators():
    cells = ([{"original_status": R.ORIGINAL_PRESENT,
               "auditor_verdict": R.AUD_EVIDENCE}] * 8
             + [{"original_status": R.ORIGINAL_PRESENT,
                 "auditor_verdict": R.AUD_NONE}] * 2
             + [{"original_status": R.ORIGINAL_PRESENT,
                 "auditor_verdict": R.AUD_UNRESOLVED}]
             + [{"original_status": R.ORIGINAL_ABSENCE,
                 "auditor_verdict": R.AUD_NONE}] * 9
             + [{"original_status": R.ORIGINAL_ABSENCE,
                 "auditor_verdict": R.AUD_EVIDENCE}] * 2)
    s = R.calibration_scores(cells)
    assert s["n_original_present_quote_verified"] == 11
    assert s["n_original_gemini_absence"] == 11
    assert s["detection_rate_on_original_present"]["k"] == 8
    assert s["single_accuracy_figure"] is None
    assert "NOT a specificity" in s["interpretation"]


def test_an_unknown_status_is_rejected():
    with pytest.raises(ValueError):
        R.calibration_scores([{"original_status": "REFERENCE_ABSENT",
                               "auditor_verdict": R.AUD_NONE}])


# ------------------------------------------------------------ estimates
def test_token_estimates_are_labelled_as_estimates_with_a_band(manifest):
    tm = manifest["token_model"]
    assert tm["r_squared"] > 0.99 and "extrapolated" in tm["caveat"]
    for k in ("stage_1_calibration", "stage_2_incremental", "total_corpus"):
        lo, hi = manifest[k]["calculated_list_batch_cost_band_usd"]
        assert lo < manifest[k]["calculated_list_batch_cost_usd"] < hi


def test_stage_totals_reconcile(manifest):
    a, b, t = (manifest["stage_1_calibration"], manifest["stage_2_incremental"],
               manifest["total_corpus"])
    assert a["n_documents"] + b["n_documents"] == t["n_documents"] == 35
    assert a["n_requests"] + b["n_requests"] == t["n_requests"] == 70
    assert a["n_assessments"] + b["n_assessments"] == t["n_assessments"] == 770
