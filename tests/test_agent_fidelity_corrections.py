"""
Guards for the methodological corrections applied after the initial agent-fidelity
delivery.

Each of these exists because the mistake it blocks produced a plausible number the first
time: a trial-weighted mean that silently weighted sessions by how talkative they were, a
budget described in tokens when it is cut in words, a gap reported as a null result, and
an averaged chance line drawn across sessions whose baselines differ.

Offline; no API call.
"""
from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "analysis/figures"))

import agent_fidelity_corpus as afc              # noqa: E402
import agent_fidelity_stylometry as sty          # noqa: E402
import agent_fidelity_audit_packages as pkg      # noqa: E402
import agent_fidelity_registry_diff as reg       # noqa: E402

_ART = _ROOT / "analysis/production_evaluation/agent_fidelity"
_FIGS = _ROOT / "analysis/figures"
_FIGSRC = _FIGS / "render_agent_fidelity_lexical_distinctiveness.py"

EXPECTED_HIERARCHICAL = {
    ("human", "human"): 0.284,
    ("enriched", "1"): 0.018, ("enriched", "2"): -0.093, ("enriched", "3"): 0.114,
    ("demographics-only", "1"): -0.012, ("demographics-only", "2"): 0.141,
    ("demographics-only", "3"): 0.184,
}


@pytest.fixture(scope="module")
def styl():
    return json.loads((_ART / "agent_fidelity_stylometry.json").read_text(
        encoding="utf-8"))


@pytest.fixture(scope="module")
def packages():
    return json.loads((_ART / "agent_fidelity_audit_packages.json").read_text(
        encoding="utf-8"))


# ============================================================ 1. hierarchy
def test_the_hierarchy_is_trial_document_focus_group_study_replicate(styl):
    assert styl["hierarchy"] == ["trial", "document", "focus group", "study replicate"]
    assert styl["primary_estimand"] == \
        "HIERARCHICAL_DOCUMENT_TO_FOCUS_GROUP_TO_STUDY_REPLICATE"


def test_the_hierarchical_estimates_recompute_from_the_documents(styl):
    """Recomputed from the per-document values, never read from a stored constant."""
    for (c, r), expected in EXPECTED_HIERARCHICAL.items():
        block = styl["hierarchical"][c][r]
        vals = [v for v in block["per_focus_group"].values() if v is not None]
        # per-focus-group values are stored rounded to four places, so recomputing from
        # them lands within rounding of the stored mean rather than exactly on it
        # the expected figures are quoted to three places, and 0.1835 rounds to 0.184,
        # so the comparison tolerance is the rounding step itself
        assert abs(statistics.mean(vals) - expected) <= 1e-3, f"{c} {r}"
        assert abs(block["mean_chance_corrected_accuracy"] - expected) <= 1e-3


def test_each_focus_group_value_comes_from_exactly_one_document(styl):
    for c, reps in styl["hierarchical"].items():
        for r, v in reps.items():
            if r == "_across_realisations":
                continue
            for f, val in v["per_focus_group"].items():
                docs = [d for d, rec in styl["per_document"].items()
                        if rec["condition"] == c and rec["fg"] == f
                        and str(rec["replicate"]) == r]
                assert len(docs) == 1, f"{c} {r} {f}: {docs}"
                assert styl["per_document"][docs[0]][
                    "chance_corrected_accuracy"] == val


def test_trials_do_not_produce_the_primary_condition_estimate(styl):
    """
    PLANTED: the pooled trial figure must not stand in for the hierarchical one. Pooling
    weights a session by how many speakers and eligible folds it happens to contain.
    """
    assert styl["pooled_label"] == \
        "TRIAL_WEIGHTED_DIAGNOSTIC_NOT_PRIMARY_CONDITION_ESTIMATE"
    assert "property of the transcript" in styl["pooled_caveat"]
    for c in ("enriched", "demographics-only"):
        pooled = styl["by_condition"][c]["chance_corrected_accuracy"]
        hier = [v["mean_chance_corrected_accuracy"]
                for r, v in styl["hierarchical"][c].items()
                if r != "_across_realisations"]
        assert len(hier) == 3
        assert not all(abs(pooled - h) < 1e-9 for h in hier)


def test_replicates_are_never_grouped_as_independent_focus_groups(styl):
    for c in ("enriched", "demographics-only"):
        reps = [r for r in styl["hierarchical"][c] if r != "_across_realisations"]
        assert sorted(reps) == ["1", "2", "3"]
        a = styl["hierarchical"][c]["_across_realisations"]
        assert a["replicates_are_not_pooled"] is True
        assert a["n_realisations"] == 3
        for r in reps:
            # fifteen sessions must never appear as fifteen focus groups
            assert styl["hierarchical"][c][r]["n_focus_groups"] <= 5


def test_demographics_only_r2_rests_on_four_of_five_focus_groups(styl):
    b = styl["hierarchical"]["demographics-only"]["2"]
    assert b["coverage"] == "4/5"
    assert b["n_focus_groups"] == 4
    assert b["focus_groups_without_an_eligible_fold"] == ["fg1"]
    assert "fg1" not in b["per_focus_group"]
    assert b["missing_focus_groups_are_absent_not_zero"] is True
    assert 0.0 not in list(b["per_focus_group"].values())
    assert abs(b["mean_chance_corrected_accuracy"]
               - statistics.mean(b["per_focus_group"].values())) < 1e-3
    # PLANTED: imputing the missing focus group as zero must give a different number
    imputed = statistics.mean(list(b["per_focus_group"].values()) + [0.0])
    assert abs(imputed - b["mean_chance_corrected_accuracy"]) > 1e-3


def test_no_inferential_test_is_derived_from_the_realisations(styl):
    for c in afc.CONDITIONS:
        a = styl["hierarchical"][c]["_across_realisations"]
        assert a["no_inferential_test_is_derived_from_five_focus_groups_or_three_"
                 "realisations"] is True
    blob = json.dumps(styl).lower()
    for banned in ("p-value", "p value", "confidence interval", "standard error",
                   "significant"):
        assert banned not in blob, banned


def test_the_hierarchical_csv_carries_both_levels():
    rows = list(csv.DictReader(
        (_ART / "agent_fidelity_hierarchical_estimates.csv").open(encoding="utf-8")))
    fg = [r for r in rows if r["level"] == "focus_group"]
    sr = [r for r in rows if r["level"] == "study_replicate"]
    assert len(sr) == 7                      # 1 human + 3 + 3
    assert len(fg) == 34                     # 5 + 15 + 14 documents
    r2 = next(r for r in sr if r["condition"] == "demographics-only"
              and r["study_replicate"] == "2")
    assert r2["coverage"] == "4/5"


# ============================================================ 2. words not tokens
_TOKEN_MISUSE = re.compile(
    r"\d+\s*[-\s]?tokens?\s+(?:budget|per\s+participant)"
    r"|tokens?\s+per\s+participant"
    r"|\d+\s*tokens?\s+is\s+not\s+viable"
    r"|budget[^.\"]{0,25}\btokens?\b"
    r"|\btokens?\b[^.\"]{0,25}\bbudget\b", re.I)

_TOKEN_LEGAL_CONTEXT = ("api", "cost", "usd", "batch", "1.7502", "model token",
                        "model-token", "tokenisation", "tokenization", "not model",
                        "estimated_input", "estimated_output", "token_model")


@pytest.mark.parametrize("artefact", ["agent_fidelity_preflight.json",
                                      "agent_fidelity_stylometry.json"])
def test_the_stylometric_budget_is_described_in_words_not_tokens(artefact):
    """
    The windows are cut in WORDS by the project lexical tokeniser. Calling them tokens
    invites the reader to think of model tokenisation, which is a different unit and a
    different number. 'Token' stays legal for API cost and model tokenisation only.
    """
    text = (_ART / artefact).read_text(encoding="utf-8")
    for m in _TOKEN_MISUSE.finditer(text):
        seg = text[max(0, m.start() - 120):m.end() + 120].lower()
        if any(k in seg for k in _TOKEN_LEGAL_CONTEXT):
            continue
        raise AssertionError(f"{artefact}: stylometric budget in tokens -> "
                             f"{m.group(0)!r}")


def test_the_token_misuse_detector_actually_fires():
    """PLANTED: a guard whose pattern never matches proves nothing."""
    assert _TOKEN_MISUSE.search("100 tokens is not viable at the budget level")
    assert _TOKEN_MISUSE.search("tokens per participant x question")
    assert _TOKEN_MISUSE.search("a 50-token budget")


def test_the_budget_unit_is_declared(styl):
    assert styl["budget_unit"] == "words"
    assert "not a model-token budget" in styl["budget_unit_note"]
    assert "WORDS" in styl["window_rule"]


def test_the_figure_says_words_not_tokens():
    src = _FIGSRC.read_text(encoding="utf-8")
    assert "WORD budget" in src and "not model tokens" in src


# ============================================================ 3. identity gap
FORBIDDEN_GAP_LANGUAGE = ("null identity gap", "identity gap is null", "no difference",
                          "absence of difference", "demonstrates no difference",
                          "conditions are equivalent")


@pytest.mark.parametrize("artefact", ["agent_fidelity_stylometry.json",
                                      "agent_fidelity_audit_packages.json"])
def test_the_identity_gap_is_never_stated_as_a_null_or_equivalence(artefact):
    """
    The artefacts DENY these claims, so a bare substring search flags their own
    disclaimers. Only an unnegated occurrence is a violation.
    """
    text = (_ART / artefact).read_text(encoding="utf-8").lower()
    for banned in FORBIDDEN_GAP_LANGUAGE:
        i = text.find(banned)
        while i != -1:
            before = text[max(0, i - 70):i]
            negated = any(k in before for k in
                          ("not ", "never ", "no ", "does not", "cannot", "is not an"))
            assert negated, f"{artefact}: unnegated {banned!r} -> ...{before[-60:]}"
            i = text.find(banned, i + 1)


def test_the_required_identity_gap_wording_is_present(styl):
    assert styl["identity_gap_interpretation"] == (
        "The median identity-separation gap was close to zero in all three conditions "
        "and did not provide additional evidence of persistent speaker "
        "differentiation.")
    assert "no equivalence margin was defined" in \
        styl["identity_gap_is_not_an_equivalence_claim"]
    for rec in styl["per_document"].values():
        g = rec.get("identity_gap")
        if g:
            assert "no equivalence margin was defined" in \
                g["close_to_zero_is_not_an_equivalence_result"]


def test_speaker_identification_is_declared_the_primary_estimand(styl):
    r = styl["primary_estimand_rationale"]
    assert "attributed to its own speaker" in r
    assert "eligible participants of the same session" in r


def test_the_gap_values_are_still_reported(styl):
    """The result is kept even though it favours no condition."""
    for c in afc.CONDITIONS:
        vals = [v for v in styl["by_condition"][c][
            "identity_gap_per_document"].values() if v is not None]
        assert vals, c


# ============================================================ 4. figure
def _panel(name):
    src = _FIGSRC.read_text(encoding="utf-8")
    marks = {k: src.index(f"# ------------------------------------------------------ "
                          f"Panel {k}") for k in "ABCD"}
    order = "ABCD"
    i = order.index(name)
    end = marks[order[i + 1]] if i + 1 < len(order) else len(src)
    return src[marks[name]:end]


def test_panel_b_uses_chance_corrected_accuracy_with_a_zero_line():
    b = _panel("B")
    assert "per_document_chance_corrected" in b
    assert "0 = chance" in b
    assert "no averaged chance line is drawn" in b


def test_no_averaged_chance_line_is_drawn_in_panel_b():
    """
    PLANTED: one averaged chance line across sessions whose baselines differ would
    misstate every session except the average one.
    """
    b = _panel("B")
    assert 'chance_baseline' not in b
    assert "y_ch" not in b


def test_panel_b_declares_the_ineligible_session():
    b = _panel("B")
    assert "no eligible fold" in b and "n=14, not 15" in b


def test_panel_a_is_retained_and_labelled_as_a_differentiation_diagnostic():
    a = _panel("A")
    assert "between_speaker_median_cosine" in a
    assert "higher = participants more alike" in a
    assert "not evidence of individual identity" in a


def test_panel_c_is_named_identity_separation_gap():
    c = _panel("C")
    assert "Identity-separation gap" in c
    assert "close to zero is not an equivalence result" in c
    assert "not independent" in c


def test_panel_d_shows_replicates_separately_and_never_joined():
    d = _panel("D")
    assert "never joined" in d
    src = _FIGSRC.read_text(encoding="utf-8")
    assert 'm["hierarchical"]' in src           # study-replicate summaries present
    assert "observed range" in src              # not "error bar", not "CI"
    for banned in ("confidence interval =", "error bar"):
        assert banned not in src


def test_the_plotted_csv_carries_the_study_replicate_summaries():
    rows = list(csv.DictReader(
        (_FIGS / "agent_fidelity_lexical_distinctiveness.csv").open(encoding="utf-8")))
    summary = [r for r in rows if r["panel"] == "D_summary"]
    assert len(summary) == 14                  # 7 realisations x (mean + coverage)
    cov = {r["condition"] + str(r["replicate"]): r["value"] for r in summary
           if r["metric"] == "coverage_focus_groups"}
    assert cov["demographics-only2"] == "4/5"
    means = {r["condition"] + str(r["replicate"]): float(r["value"]) for r in summary
             if r["metric"] == "study_replicate_mean_chance_corrected"}
    assert abs(means["demographics-only2"] - 0.141) < 5e-4
    assert abs(means["humanhuman"] - 0.284) < 5e-4


# ================================================= 5. hyper-exactness controls
def test_the_hyper_exactness_universe_is_candidates_plus_controls(packages):
    o = packages["hyper_exactness"]
    assert o["n_detector_candidates"] == 67
    assert o["n_random_nondetected_controls"] == 60
    assert o["n_universe"] == 127
    assert o["control_stratum_name"] == "RANDOM_NONDETECTED_CONTROL_TURNS"
    assert o["controls_by_condition"] == {"human": 20, "enriched": 20,
                                          "demographics-only": 20}


def test_controls_are_not_called_known_negatives(packages):
    o = packages["hyper_exactness"]
    assert "must never be called known negatives" in \
        o["controls_are_not_known_negatives"]
    assert o["if_controls_cannot_support_prevalence"] == "DETECTED_LOWER_BOUND_RATE"
    assert "never as negative" in o["unaudited_is_not_negative"]
    assert o["reporting_distinctions_required"] == [
        "detector candidate yield",
        "adjudicated hyper-exact cases among candidates",
        "hyper-exact cases found in the nondetected controls",
        "estimated or detected corpus rate"]


def test_controls_and_candidates_do_not_overlap():
    sealed = json.loads((_ART / "agent_fidelity_audit_sealed_reference.json")
                        .read_text(encoding="utf-8"))["hyper_exactness"]
    cand = {k for k, v in sealed.items()
            if v.get("_stratum") == "DETECTOR_PROPOSED_CANDIDATE"}
    ctl = {k for k, v in sealed.items()
           if v.get("_stratum") == "RANDOM_NONDETECTED_CONTROL_TURNS"}
    assert len(cand) == 67 and len(ctl) == 60
    assert not (cand & ctl)
    keys = {(v["_doc_id"], v["_question"]) for v in sealed.values()}
    assert len(keys) > 1


def test_the_controls_fired_no_detector():
    """PLANTED: a control that a detector would fire on is not a control."""
    sealed = json.loads((_ART / "agent_fidelity_audit_sealed_reference.json")
                        .read_text(encoding="utf-8"))["hyper_exactness"]
    ctl_ids = {k for k, v in sealed.items()
               if v.get("_stratum") == "RANDOM_NONDETECTED_CONTROL_TURNS"}
    items = {i["item_id"]: i for i in
             json.loads((_ART / "hyper_exactness_universe_blinded.json")
                        .read_text(encoding="utf-8"))["items"]}
    for iid in ctl_ids:
        q = items[iid]["quote"]
        for name, pat in pkg.PATTERNS.items():
            assert not pat.search(q), f"{iid} fires {name}"


def test_the_stratum_is_invisible_to_the_auditor():
    """PLANTED: a detector field in the payload would reveal the stratum."""
    items = json.loads((_ART / "hyper_exactness_universe_blinded.json")
                       .read_text(encoding="utf-8"))["items"]
    assert len(items) == 127
    for it in items:
        assert set(it) == {"item_id", "turn_id", "speaker", "quote", "n_words"}


def test_numeral_density_is_still_only_a_descriptive_proxy(packages):
    assert packages["numeral_density_status"] == \
        "NUMERAL_DENSITY_DESCRIPTIVE_PROXY_NOT_HYPER_EXACTNESS"
    assert "must not be read as less hyper-exactness" in \
        packages["numeral_density_warning"]


# ================================================= 6. profile-consistency pilot
def test_the_pilot_is_sixty_controls_and_sixty_proposed_pairs(packages):
    pl = packages["profile_consistency"]["pilot"]
    assert pl["n_pairs"] == 120
    assert pl["n_random_controls"] == 60
    assert pl["n_screener_proposed"] == 60
    assert pl["n_repetitions"] == 2
    assert pl["n_adjudications"] == 240


def test_every_pilot_repetition_has_its_own_cache_key():
    """PLANTED: a shared key would serve one cached answer twice as 'agreement'."""
    reqs = json.loads((_ART / "profile_consistency_pilot_manifest.json")
                      .read_text(encoding="utf-8"))["requests"]
    assert len(reqs) == 240
    assert len({r["cache_key"] for r in reqs}) == 240
    by_item = defaultdict(set)
    for r in reqs:
        by_item[r["item_id"]].add(r["cache_key"])
    assert len(by_item) == 120
    assert all(len(v) == 2 for v in by_item.values())


def test_the_pilot_payload_hides_the_screener_stratum():
    items = json.loads((_ART / "profile_consistency_pilot_blinded.json")
                       .read_text(encoding="utf-8"))["items"]
    assert len(items) == 120
    for it in items:
        assert set(it) == {"item_id", "speaker", "statement_a", "statement_b"}


def test_the_proposed_pairs_are_stratified(packages):
    pl = packages["profile_consistency"]["pilot"]
    assert "condition x similarity tercile x focus group" in pl["stratification"]
    assert len(pl["similarity_tercile_bounds"]) == 2
    assert pl["n_strata_available"] > 10
    assert len(pl["strata_represented"]) >= 6
    assert "NOT balanced by condition" in pl["control_condition_balance_note"]


def test_the_remaining_pairs_are_not_sent(packages):
    pl = packages["profile_consistency"]["pilot"]
    assert pl["n_remaining_pairs_not_sent"] == 682
    assert pl["remaining_pairs_are_blocked_until_the_gate_passes"] is True
    assert packages["profile_consistency"]["n_candidate_pairs_total"] == 802


def test_the_gate_is_prospective_and_not_a_conventional_threshold():
    g = pkg.CONSISTENCY_PILOT_GATE
    assert g["fixed_before_any_result_is_seen"] is True
    assert "0.80 is not used as a default" in g["no_conventional_threshold_adopted"]
    assert set(g["outcomes"]) == {"AUDITOR_USABLE_FOR_EXPLORATORY_FULL_AUDIT",
                                  "AUDITOR_USABLE_FOR_DETECTION_ONLY",
                                  "AUDITOR_USABLE_FOR_CORROBORATION_ONLY",
                                  "AUDITOR_UNSTABLE_STOP"}
    for name, c in g["criteria"].items():
        assert c.get("why"), f"{name} carries no justification"
    floors = [c.get("full_audit_floor") for c in g["criteria"].values()]
    assert 0.80 not in floors and 0.8 not in floors


def test_the_gate_covers_every_required_dimension():
    c = pkg.CONSISTENCY_PILOT_GATE["criteria"]
    assert "exact_agreement_between_repetitions" in c
    assert "uncertain_rate" in c
    assert "verbatim_evidence_validity" in c
    assert "planted_contradiction_recall" in c
    assert "contradiction_vs_context_separation" in c
    assert "control_behaviour" in c
    assert "malformed_response_rejection" in c


def test_a_failed_gate_blocks_the_remaining_pairs():
    g = pkg.CONSISTENCY_PILOT_GATE
    assert "682 pairs are NOT executed" in g["if_gate_fails"]


def test_disagreements_are_never_resolved_by_a_forbidden_route():
    g = pkg.CONSISTENCY_PILOT_GATE
    for banned in ("model confidence", "modal vote", "a third call",
                   "similarity scores", "unrecorded manual choice"):
        assert banned in g["disagreement_resolution_forbidden"]
    assert "stay UNRESOLVED" in g["disagreement_resolution_rule"]


def test_the_auditor_validation_cases_cover_every_required_behaviour():
    cases = {c["case"]: c for c in pkg.AUDITOR_VALIDATION_CASES}
    assert cases["DIRECT_CONTRADICTION"]["must_return"] == "UNEXPLAINED_CONTRADICTION"
    assert cases["EXPLAINED_CHANGE"]["must_return"] == \
        "POSITION_CHANGED_WITH_EXPLANATION"
    assert cases["DIFFERENT_CONTEXTS_NOT_CONTRADICTORY"]["must_return"] == \
        "CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY"
    for name in ("EVIDENCE_FROM_ANOTHER_SPEAKER", "NON_LITERAL_QUOTE",
                 "UNKNOWN_TURN_ID", "NO_JUSTIFICATION",
                 "UNCERTAIN_WITHOUT_EXPLANATION"):
        assert cases[name]["must_return"] == "REJECT"
        assert cases[name]["reject_reason"]


def test_no_sealed_or_screener_field_enters_a_prompt():
    blob = json.dumps(json.loads(
        (_ART / "profile_consistency_pilot_manifest.json").read_text(
            encoding="utf-8"))["requests"])
    for tok in ("_condition", "_fg", "_replicate", "_doc_id", "_similarity_tercile",
                "SCREENER_PROPOSED", "RANDOM_CONTROL_NOT_PROPOSED"):
        assert tok not in blob, tok


def test_screening_never_dictates_a_verdict(packages):
    o = packages["profile_consistency"]
    assert "it never decides" in o["screener_role"]
    assert "No embedding and no NLI model may dictate a verdict" in o["screener_role"]


# ================================================= 7. continuity scope
def test_only_lexical_identity_continuity_is_closed(styl):
    assert styl["status"] == "EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC"
    o = reg.build()
    for mid in ("input_profile_adherence", "expressed_position_continuity"):
        c = next(x for x in o["changes"] if x["metric_id"] == mid)
        assert c["change"] == "PROPOSED_PENDING_AUDIT"


def test_lexical_continuity_is_not_called_psychological_continuity(styl):
    blob = json.dumps(styl).lower()
    for banned in ("psychological continuity", "biographical continuity",
                   "attitudinal continuity"):
        idx = blob.find(banned)
        while idx != -1:
            window = blob[max(0, idx - 60):idx]
            assert "not" in window or "nothing about" in window, banned
            idx = blob.find(banned, idx + 1)
    joined = " ".join(styl["what_this_does_not_show"]).lower()
    assert "independent person" in joined


# ================================================= 8. registry
def test_only_metrics_with_evidence_are_proposable_now():
    """
    The three offline metrics, plus the two audits that have since been EXECUTED and
    passed their gates. Nothing whose evidence does not exist may be proposed.
    """
    o = reg.build()
    now = {c["metric_id"] for c in o["changes"]
           if c["change"] in ("ADD", "RECLASSIFY")}
    assert now == set(reg.PROPOSABLE_NOW)
    assert now == {"lexical_identity_continuity",
                   "between_speaker_lexical_differentiation", "numeral_density",
                   "hyper_exactness", "profile_consistency"}


def test_audit_dependent_metrics_are_marked_pending():
    o = reg.build()
    pending = {c["metric_id"] for c in o["changes"]
               if c["change"] == "PROPOSED_PENDING_AUDIT"}
    # the two executed audits have left this set; the two unexecuted expansions remain
    assert {"input_profile_adherence", "expressed_position_continuity"} <= pending
    assert not ({"hyper_exactness", "profile_consistency"} & pending)


def test_nothing_is_superseded_yet():
    o = reg.build()
    assert o["nothing_is_superseded_yet"] is True
    for mid in ("profile_continuity_group", "profile_consistency_group"):
        c = next(x for x in o["changes"] if x["metric_id"] == mid)
        assert c["change"] == "PROPOSED_PENDING_AUDIT"
        assert c["to_evidence_class"] != "SUPERSEDED"


def test_the_frozen_registry_is_still_untouched():
    o = reg.build()
    assert o["frozen_registry_untouched"] is True
    frozen = (_ROOT / "analysis/production_evaluation/metric_registry.csv").read_text(
        encoding="utf-8")
    for mid in ("lexical_identity_continuity", "input_profile_adherence",
                "expressed_position_continuity"):
        assert mid not in frozen


# ================================================= 9. POST_A_REPLAN snapshot
def test_the_replan_snapshot_marker_does_not_rewrite_history():
    p = _ROOT / "analysis/production_evaluation/inductive_phase_a/POST_A_REPLAN.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["snapshot_taken_at"] == "STAGE_B_LAUNCH"
    assert d["snapshot_note"] == ("Historical planning snapshot; not a statement of "
                                  "current execution status.")
    # historical content untouched: the stages it recorded as not-yet-run stay recorded
    assert d["stages_executed_here"] == ["B_CANONICAL_TAXONOMY"]
    assert set(d["stages_not_executed"]) == {"C", "D", "E1", "E2", "E3", "F1", "F2"}
    assert d["observed"]["n_themes"] == 526
    assert d["superseded_planning_total"] == 925


# ================================================= 12. still offline
def test_no_api_call_was_made_in_this_turn():
    for f in ("agent_fidelity_preflight.json", "agent_fidelity_stylometry.json",
              "agent_fidelity_audit_packages.json"):
        assert json.loads((_ART / f).read_text(encoding="utf-8"))["no_api_calls"]
    man = json.loads((_ART / "profile_consistency_pilot_manifest.json").read_text(
        encoding="utf-8"))
    assert man["status"] == "PREPARED_NOT_SUBMITTED"
    assert json.loads((_ART / "agent_fidelity_audit_packages.json").read_text(
        encoding="utf-8"))["status"] == "PREPARED_NOT_EXECUTED"
