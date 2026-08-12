"""
Post-run focused tests for the exploratory out-of-Q3 transportability check.

These assert the properties the conclusion rests on: that the reliability gate never
decides a category, that no uncertainty was quietly turned into absence on either the
recall or the precision side, that the frozen classification rule is applied as written,
and that the check left every protected artefact alone. They read sealed outputs only
and touch no API and no session log.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import hybrid_transportability as hy      # noqa: E402
import hybrid_round2 as r2                # noqa: E402
import hybrid_metrics as hm               # noqa: E402

_HY = hy._HY


def _L(n):
    return json.loads((_HY / n).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics():
    return _L("hybrid_metrics.json")


@pytest.fixture(scope="module")
def deriv():
    return _L("hybrid_matching_derivation.json")


# --------------------------------------------------------------- the gate
def _j(cat, conf, quotes):
    return {"category": cat, "confidence": conf, "quotations": quotes}


def test_gate_reports_no_reason_for_a_clean_rejection(monkeypatch):
    """
    The regression this exists for: an earlier gate folded "the category is not an
    accepted correspondence" into its failure reasons, so a twice-agreed, well-evidenced
    NO_CORRESPONDENCE came back as unresolved. That inflates the recall upper bound,
    because a settled non-correspondence is not a pending relation.
    """
    monkeypatch.setattr(r2, "_evidence_problems", lambda j, u: [])
    q = [{"turn_id": "T001", "quote": "x"}]
    cat, reasons = r2.gate({1: _j("NO_CORRESPONDENCE", "HIGH", q),
                            2: _j("NO_CORRESPONDENCE", "HIGH", q)}, "S01")
    assert reasons == []
    assert cat == "NO_CORRESPONDENCE"


@pytest.mark.parametrize("reps,frag", [
    ({1: _j("SAME_SUBSTANTIVE_THEME", "HIGH", [{"turn_id": "T001", "quote": "x"}]),
      2: _j("NO_CORRESPONDENCE", "HIGH", [{"turn_id": "T001", "quote": "x"}])},
     "disagree"),
    ({1: _j("SAME_SUBSTANTIVE_THEME", "LOW", [{"turn_id": "T001", "quote": "x"}]),
      2: _j("SAME_SUBSTANTIVE_THEME", "HIGH", [{"turn_id": "T001", "quote": "x"}])},
     "LOW"),
    ({1: _j("SAME_SUBSTANTIVE_THEME", "HIGH", [{"turn_id": "T001", "quote": "x"}])},
     "one or both repetitions"),
])
def test_gate_fires_on_each_unreliability(monkeypatch, reps, frag):
    monkeypatch.setattr(r2, "_evidence_problems", lambda j, u: [])
    cat, reasons = r2.gate(reps, "S01")
    assert cat is None
    assert any(frag in r for r in reasons), reasons


def test_gate_rejects_a_fabricated_quotation():
    """The evidence gate must fail a quote that is not in the unit at all."""
    q = [{"turn_id": "T001", "quote": "a sentence nobody in this study ever uttered"}]
    cat, reasons = r2.gate({1: _j("SAME_SUBSTANTIVE_THEME", "HIGH", q),
                            2: _j("SAME_SUBSTANTIVE_THEME", "HIGH", q)}, "S01")
    assert cat is None
    assert any("not literal" in r or "unknown turn" in r for r in reasons), reasons


# ------------------------------------------------- uncertainty is not absence
def test_recall_band_is_derived_from_the_complete_universe(metrics):
    """
    The recall band is only meaningful if it was computed over adjudicated pairs. The
    original defect was reporting a zero-width band while 32 pairs sat unjudged, so the
    first thing to assert is that the space is closed at 93.
    """
    uni = _L("hybrid_universe.json")
    o = metrics["overall_within_check"]
    assert metrics["correspondence_space"]["n_pairs"] == 93
    assert metrics["correspondence_space"]["complete"] is True
    assert uni["pass"] is True
    band = o["possible_recall_upper_bound"] - o["confirmed_recall_lower_bound"]
    assert band == 0.0 or o["n_unresolved_possibly_recovered"] > 0, \
        "a non-zero recall band with no pending human theme is incoherent"


def test_no_human_theme_is_called_unrecovered_on_an_unjudged_pair(metrics):
    """The claim the whole correction exists to make honest."""
    uni = _L("hybrid_universe.json")
    for k in metrics["overall_within_check"]["human_themes_confirmed_not_recovered"]:
        v = uni["human_state"][k]
        assert v["local_universe_complete"], k
        assert v["n_pairs_adjudicated"] == v["n_pairs_in_unit"], k
        assert not v["confirmed_matches"] and not v["unresolved_pairs"], k


def test_precision_band_covers_every_candidate_with_an_open_pair(metrics):
    """The mirror of the recall check, on the side where the band is non-zero."""
    uni = _L("hybrid_universe.json")
    o = metrics["overall_within_check"]
    expected = sorted(k for k, v in uni["machine_state"].items()
                      if v["state"] == "UNRESOLVED_POSSIBLY_MATCHED")
    assert o["machine_themes_unresolved_possibly_matched"] == expected
    assert o["n_machine_unresolved_possibly_matched"] == len(expected)
    assert o["possible_precision_upper_bound"] >= o["strict_confirmed_precision"]
    n = o["n_machine_matched"] + o["n_machine_unresolved_possibly_matched"]
    assert o["possible_precision_upper_bound"] == round(n / o["n_machine_themes"], 4)


def test_novelty_is_never_converted_into_a_human_correspondence(metrics):
    """
    A candidate can be corroborated novel on task C and still hold an unsettled pairwise
    correspondence. Those must stay distinct: novelty may enter the adjusted precision
    figure, never the strict one.
    """
    uni = _L("hybrid_universe.json")
    both = metrics["machine_only"]["corroborated_novel_but_pairwise_unresolved"]
    for k in both:
        assert uni["machine_state"][k]["state"] == "UNRESOLVED_POSSIBLY_MATCHED", k
        assert not uni["machine_state"][k]["confirmed_matches"], k
    o = metrics["overall_within_check"]
    assert o["strict_confirmed_precision"] <= \
        o["exploratory_adjusted_precision_including_corroborated_novelty"]


def test_every_pair_carries_an_explicit_status(deriv):
    allowed = {hy.HYBRID_CONFIRMED_MATCH, hy.HYBRID_UNRESOLVED,
               "HYBRID_CONFIRMED_NON_CORRESPONDENCE"}
    rows = deriv["universe"]["rows"]
    assert len(rows) == 93
    for r in rows:
        assert r["status"] in allowed, r
        if r["status"] == hy.HYBRID_UNRESOLVED:
            assert r["reasons"], f"{r['case_id']} unresolved with no stated reason"


# ---------------------------------------------------- denominators and totals
def test_denominators_match_the_frozen_expectation(metrics):
    for u, v in metrics["per_unit"].items():
        assert v["n_human_themes"] == hy.EXPECTED_HUMAN_THEMES[u], u
        assert v["question_id"] == hy.QUESTION_OF[u], u
    assert metrics["overall_within_check"]["n_human_themes"] == 18


def test_per_question_totals_equal_the_per_unit_totals(metrics):
    for q, v in metrics["per_question"].items():
        us = [u for u in hy.UNITS if hy.QUESTION_OF[u] == q]
        assert v["units"] == us
        assert v["n_human_themes"] == sum(
            metrics["per_unit"][u]["n_human_themes"] for u in us)
        assert v["n_machine_themes"] == sum(
            metrics["per_unit"][u]["n_machine_themes"] for u in us)


def test_rates_are_bounded_and_ordered(metrics):
    blocks = list(metrics["per_unit"].values()) + list(metrics["per_question"].values())
    blocks.append(metrics["overall_within_check"])
    for b in blocks:
        assert 0.0 <= b["confirmed_recall_lower_bound"] <= 1.0
        assert (b["confirmed_recall_lower_bound"]
                <= b["possible_recall_upper_bound"] <= 1.0)
        assert (b["strict_confirmed_precision"]
                <= b["possible_precision_upper_bound"] <= 1.0)


# ------------------------------------------------------ the frozen rule
def test_final_class_is_one_of_the_four_frozen_classes(metrics):
    assert metrics["FROZEN_RULE_CLASSIFICATION"]["value"] in hy.FINAL_CLASSES


def test_the_superseded_classification_is_retained_and_labelled(metrics):
    """
    The pre-complement result must survive in the record, marked as superseded. Deleting
    it would hide that the published figure changed; presenting it unmarked would be
    worse.
    """
    pc = metrics["pre_complement_classification"]
    assert pc["value"] == "DESCRIPTIVELY_COMPATIBLE_WITH_Q3"
    assert pc["status"].startswith("PROVISIONAL_SUPERSEDED")
    assert "61/93" in pc["status"]


def test_both_conclusions_are_reported(metrics):
    """The frozen rule alone would overstate the finding; both must be present."""
    assert metrics["FROZEN_RULE_CLASSIFICATION"]["value"]
    bal = metrics["BALANCED_INTERPRETATION"]
    assert bal["statement"]
    d = bal["dimensions_weighed"]
    for k in ("recall_outside_q3", "strict_precision_outside_q3",
              "precision_band_outside_q3", "q3_descriptive_reference",
              "thematic_proliferation", "n_unresolved_pairs",
              "n_small_and_single_coder"):
        assert k in d, k
    t = (_HY / "HYBRID_TRANSPORTABILITY_RESULTS.md").read_text(encoding="utf-8")
    assert "Frozen-rule classification" in t and "Balanced interpretation" in t


def test_forbidden_transportability_language_is_absent():
    """
    The ban is on CLAIMING these things, not on the words. A naive substring check fires
    on the disclaimer itself ("does not ... show the two settings to be equivalent"),
    which would push the document toward dropping the disclaimer to satisfy the test —
    exactly backwards. So match affirmative constructions only.
    """
    import re
    t = " ".join((_HY / "HYBRID_TRANSPORTABILITY_RESULTS.md")
                 .read_text(encoding="utf-8").lower().split())
    for pat in (r"transportability (is|was|has been|have been) establish",
                r"establishes? transportability",
                r"(is|are|was|were|has been|have been) validated",
                r"(is|are|was|were) equivalent",
                # third person only: "does not validate the procedure" is a denial, and
                # English cannot form that denial with the -s inflection
                r"validates (the|this) (procedure|approach|method)"):
        m = re.search(pat, t)
        assert m is None, f"affirmative claim {m.group(0)!r} in the results document"
    # and the disclaimer must actually be there
    assert "does **not** establish transportability" in \
        (_HY / "HYBRID_TRANSPORTABILITY_RESULTS.md").read_text(encoding="utf-8")


def test_the_frozen_rule_was_not_retrofitted_to_include_precision(metrics):
    """
    The rule keys on recall. Rewriting it after seeing that precision was weak would
    destroy the point of freezing it, so the stored rule must still be recall-only.
    """
    rule = json.dumps(metrics["FROZEN_RULE_CLASSIFICATION"]["rule"]).lower()
    assert "recall" in rule
    assert "precision" not in rule, "the frozen rule now mentions precision"
    assert metrics["FROZEN_RULE_CLASSIFICATION"]["rule"] == hy.FINAL_RULE


def test_final_rule_reapplied_from_the_stored_metrics(metrics):
    """Recompute the classification from the stored figures, independent of build()."""
    pq = metrics["per_question"]
    o = metrics["overall_within_check"]
    unres_share = o["n_unresolved_possibly_recovered"] / o["n_human_themes"]
    mean_band = sum(v["recall_band_width"] for v in pq.values()) / len(pq)
    ref = hy.Q3_REFERENCE["recall"]
    below = sum(1 for v in pq.values() if v["possible_recall_upper_bound"] < ref)
    if unres_share > 0.40 or mean_band > 0.35:
        expect = "UNRESOLVED_DUE_TO_HYBRID_UNCERTAINTY"
    elif below >= 3:
        expect = "DESCRIPTIVELY_LOWER_THAN_Q3"
    elif all(v["possible_recall_upper_bound"] >= ref for v in pq.values()):
        expect = "DESCRIPTIVELY_COMPATIBLE_WITH_Q3"
    else:
        expect = "MIXED_OUTSIDE_Q3_PERFORMANCE"
    assert metrics["FROZEN_RULE_CLASSIFICATION"]["value"] == expect


def test_results_never_pooled_with_q3(metrics):
    assert metrics["never_pooled_with_q3"] is True
    assert metrics["no_pass_fail"] is True
    assert metrics["classification"] == "EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK"


def test_no_pass_fail_language_in_the_results_document():
    t = (_HY / "HYBRID_TRANSPORTABILITY_RESULTS.md").read_text(encoding="utf-8")
    for banned in ("p = 0.", "p < 0.", "statistically significant", "PASS", "FAIL",
                   "proves that", "demonstrates that enrichment"):
        assert banned not in t, f"{banned!r} appears in the results document"


# ------------------------------------------------------------- protections
def test_protected_inputs_still_match_the_sealed_boundary_audit():
    """
    Re-run the Phase 1 input validation. It compares each unit's text against the
    SHA-256 recorded in the sealed boundary audit and re-counts the human themes, so a
    pass here is direct evidence that nothing this check did wrote back to the frozen
    supplementary reference or to the transcripts.
    """
    v = hy.validate_inputs()
    assert v["problems"] == [], v["problems"]
    assert v["pass"] is True
    assert v["n_human_themes"] == 18
    assert v["per_unit"] == dict(hy.EXPECTED_HUMAN_THEMES)


def test_the_single_coder_workbook_is_not_writable_by_this_pipeline():
    """No hybrid script may name the coder's workbook as a write target."""
    import re
    for f in sorted((_ROOT / "scripts").glob("hybrid_*.py")):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r"(write_text|to_excel|\.save\(|_atomic)\s*\(", src):
            window = src[m.start():m.start() + 240]
            assert "Transportability_Emergent_SingleCoder" not in window, f.name
            assert "supplementary_human_reference" not in window, f.name


def test_products_all_exist():
    for n in ("hybrid_manifest.json", "gemini_extraction_results.json",
              "claude_cross_model_results.json", "hybrid_matching_derivation.json",
              "hybrid_metrics.json", "hybrid_cost_actual.json",
              "HYBRID_TRANSPORTABILITY_RESULTS.md",
              "HYBRID_TRANSPORTABILITY_TABLES.xlsx",
              "HYBRID_TRANSPORTABILITY_TRACEABILITY.md"):
        assert (_HY / n).exists(), n


def test_cost_record_keeps_measurement_apart_from_unverified_rates():
    c = _L("hybrid_cost_actual.json")
    assert c["record_type"] == "POST_RUN_MEASURED_USAGE"
    assert c["gemini"]["calculated_cost_usd"] is None
    assert c["gemini"]["cost_status"] == "NOT_CALCULATED_RATE_NOT_VERIFIED"
    assert c["gemini"]["actual_input_tokens"] > 0
    ci, co = c["claude"]["actual_input_tokens"], c["claude"]["actual_output_tokens"]
    want = ci / 1e6 * 2.5 + co / 1e6 * 12.5
    assert abs(c["claude"]["calculated_list_batch_cost_usd"] - want) < 0.01


def test_usage_totals_agree_with_the_batch_records(metrics):
    """All three jobs must be accounted for — the complement is not free."""
    srcs = [_L(n) for n in ("claude_round1_results.json", "claude_round2_results.json",
                            "claude_complement_results.json")]
    c = _L("hybrid_cost_actual.json")["claude"]
    assert c["actual_input_tokens"] == sum(s["total_usage"]["input_tokens"]
                                           for s in srcs)
    assert c["actual_output_tokens"] == sum(s["total_usage"]["output_tokens"]
                                            for s in srcs)
    assert {s["job_id"] for s in c["per_stage"]} == {s["job_id"] for s in srcs}
    assert len(c["per_stage"]) == 3


def test_every_audit_response_was_matched_by_custom_id():
    """
    custom_ids are allocated per batch, so they are unique WITHIN a job and repeat
    across the two jobs. Matching is per-job through that job's id_map, so uniqueness
    must be asserted per round — never globally, and never by position.
    """
    rec = _L("claude_cross_model_results.json")
    per_round = {}
    for c in rec["cases"]:
        for rep, r in c["repetitions"].items():
            ids = per_round.setdefault(c["round"], set())
            assert r["custom_id"] not in ids, f"custom_id reused in round {c['round']}"
            ids.add(r["custom_id"])
    for j in rec["jobs"]:
        assert len(per_round[j["round"]]) == j["n_requests"], j["round"]


def test_every_case_has_two_repetitions_or_a_recorded_failure():
    rec = _L("claude_cross_model_results.json")
    failed = {f for j in rec["jobs"] for f in j["failures"]}
    for c in rec["cases"]:
        if set(c["repetitions"]) != {"1", "2"}:
            ids = {r["custom_id"] for r in c["repetitions"].values()}
            assert ids & failed, f"{c['case_id']} is short a repetition unaccounted for"
        for r in c["repetitions"].values():
            if r["status"] != "COMPLETE":
                assert c["gate_outcome"]["status"].startswith("HYBRID_UNRESOLVED"), \
                    f"{c['case_id']} has a failed repetition but was still settled"


def test_the_errored_request_became_an_unresolved_case():
    """The one round-1 failure must surface as unresolved, not silently vanish."""
    rec = _L("claude_cross_model_results.json")
    failures = [f for j in rec["jobs"] for f in j["failures"]]
    assert len(failures) == 1, failures
    hit = [c for c in rec["cases"]
           if any(r["custom_id"] in failures for r in c["repetitions"].values())]
    assert len(hit) == 1
    assert hit[0]["gate_outcome"]["status"] == hy.HYBRID_UNRESOLVED
