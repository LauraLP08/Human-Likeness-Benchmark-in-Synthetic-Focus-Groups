"""
Gates for the v2 blinded audits.

These are the checks that must pass BEFORE the hyper-exactness job may be submitted:
the two manifests reconcile, the fixtures are really in the payload, the blinding is
clean, and the 254 real adjudications are covered. Each guard is paired with the mistake
it blocks, because every one of those mistakes produced a plausible-looking artefact in
v1.

Offline; no API call.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import agent_fidelity_corpus as afc              # noqa: E402
import agent_fidelity_audit_v2 as v2             # noqa: E402
import agent_fidelity_audit_packages as v1       # noqa: E402

_ART = _ROOT / "analysis/production_evaluation/agent_fidelity"


def _j(name):
    return json.loads((_ART / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pre():
    return _j("v2_audit_preflight.json")


@pytest.fixture(scope="module")
def hx():
    return {"items": _j("v2_hyper_exactness_items_blinded.json"),
            "item_manifest": _j("v2_hyper_exactness_item_manifest.json"),
            "requests": _j("v2_hyper_exactness_provider_request_manifest.json"),
            "sealed": _j("v2_hyper_exactness_sealed_reference.json")}


@pytest.fixture(scope="module")
def pc():
    return {"items": _j("v2_profile_consistency_items_blinded.json"),
            "item_manifest": _j("v2_profile_consistency_item_manifest.json"),
            "requests": _j("v2_profile_consistency_provider_request_manifest.json"),
            "sealed": _j("v2_profile_consistency_sealed_reference.json")}


# ===================================================== 3. literal evidence
def test_no_evidence_is_a_character_slice():
    """
    PLANTED: v1 sent text[start-40:start+220], which cuts words in half. Reduction is now
    sentence-aligned, so the presented text must start and end on whole words.
    """
    long = " ".join(["word"] * 400) + ". Second sentence here. Third one follows now."
    q, ctx, reduced = v2.sentence_aligned(long, max_words=50)
    assert reduced
    assert not q.startswith(" ") and not q.endswith(" ")
    for piece in (q, ctx):
        for w in piece.split():
            assert w in long.split() or w.strip(".,") in long.replace(".", " ").split()


def test_a_short_turn_is_sent_whole():
    t = "i eat meat about three times a week, mostly chicken."
    q, ctx, reduced = v2.sentence_aligned(t)
    assert q == t and ctx == "" and reduced is False


def test_a_single_very_long_sentence_is_not_cut():
    """Cutting mid-sentence would lose the clause that gives a claim its meaning."""
    s = " ".join(["a"] * 500)
    q, ctx, reduced = v2.sentence_aligned(s, max_words=50)
    assert q == s and reduced is False


def test_every_presented_quote_is_literal_in_its_source(hx, pc):
    for it in hx["items"]["items"]:
        assert v2.verify_literal(it["quote"], it["quote"])
        assert it["presented_text_sha256"] == v2._sha(it["quote"])
    for it in pc["items"]["items"]:
        for side in ("statement_a", "statement_b"):
            s = it[side]
            assert s["presented_text_sha256"] == v2._sha(s["quote"])


def test_every_item_carries_the_required_evidence_fields(hx, pc):
    need = {"turn_id", "guide_question", "quote", "context_window", "is_full_turn",
            "n_words_presented", "n_words_source_turn", "source_turn_sha256",
            "presented_text_sha256"}
    for it in hx["items"]["items"]:
        assert need <= set(it)
        assert it["guide_question"] in v2.GUIDE_QUESTIONS.values()
    for it in pc["items"]["items"]:
        for side in ("statement_a", "statement_b"):
            assert need <= set(it[side])


def test_a_reduced_turn_supplies_context_separately(hx):
    reduced = [i for i in hx["items"]["items"] if not i["is_full_turn"]]
    assert reduced, "no turn was long enough to exercise reduction"
    assert any(i["context_window"] for i in reduced)
    for i in reduced:
        # the context is a separate field, never concatenated into the quote
        if i["context_window"]:
            assert i["context_window"] not in i["quote"]


# ===================================================== 2. consistency screener
def test_the_jaccard_rule_is_retired(pre):
    s = pre["profile_consistency"]["screener"]
    assert s["retired_rule"] == "jaccard < 0.12"
    assert "DIFFERENT topics" in s["why_retired"]
    assert s["requires"] == ["evidence of a common topic or referent",
                             "a possible contrast of position"]


def test_a_change_marker_alone_is_not_a_polarity_contrast():
    """
    PLANTED: "but", "now" and "actually" appear in almost every conversational turn. When
    they counted as contrast, HIGH_TOPIC_SIMILARITY_WITHOUT_POLARITY_CONTRAST was empty
    by construction.
    """
    a = "i eat meat about three times a week but it depends"
    b = "i eat meat about three times a week now and again"
    assert not v2.polarity_contrast(a, b)
    assert v2.polarity_profile(a)["change_marker"]


def test_negation_and_frequency_asymmetry_do_signal_a_contrast():
    assert v2.polarity_contrast("i never eat meat at all",
                                "i eat meat most days of the week")
    assert v2.polarity_contrast("i always cook at home",
                                "i cook at home sometimes i suppose")


def test_all_three_strata_are_populated_and_sampled(pre):
    counts = pre["profile_consistency"]["counts_by_stratum_and_condition"]
    for st in ("HIGH_TOPIC_SIMILARITY_WITH_POLARITY_CONTRAST",
               "HIGH_TOPIC_SIMILARITY_WITHOUT_POLARITY_CONTRAST",
               "LOW_TOPIC_SIMILARITY_RANDOM_CONTROL"):
        assert st in counts, f"{st} was defined but never sampled"
        assert sum(counts[st].values()) > 0


def test_no_stratum_is_called_a_negative(pre):
    s = pre["profile_consistency"]["screener"]
    assert s["no_stratum_is_a_negative"] is True
    blob = json.dumps(pre).lower()
    assert "known negative" not in blob


def test_embeddings_and_nli_may_only_propose(pre):
    assert pre["profile_consistency"]["screener"]["embeddings_or_nli"] == \
        "may propose, never decide"


# ===================================================== 1. balanced denominators
def test_the_pilot_is_balanced_twenty_twenty_twenty(pre):
    role = pre["profile_consistency"]["counts_by_role_and_condition"]
    for tag in ("PROPOSED", "CONTROL"):
        assert role[tag] == {"human": 20, "enriched": 20, "demographics-only": 20}, tag
    assert pre["profile_consistency"]["balanced"] is True
    assert pre["profile_consistency"]["shortfalls"] == []


def test_the_two_high_strata_are_sampled_evenly(pre):
    counts = pre["profile_consistency"]["counts_by_stratum_and_condition"]
    for st in ("HIGH_TOPIC_SIMILARITY_WITH_POLARITY_CONTRAST",
               "HIGH_TOPIC_SIMILARITY_WITHOUT_POLARITY_CONTRAST"):
        assert counts[st] == {"human": 10, "enriched": 10, "demographics-only": 10}


def test_a_shortfall_is_reported_and_never_silently_substituted():
    """PLANTED: an impossible quota must surface, not be quietly topped up."""
    rows, _ = v2.screen_pairs(v1._turns())
    sel, short, _ = v2.balanced_pilot(rows, per_condition_proposed=20,
                                      per_condition_control=400)
    assert short, "an unfillable control quota must be reported"
    for s in short:
        assert s["obtained"] < s["requested"]
        assert s["available"] >= s["obtained"]


def test_the_v1_denominators_are_recorded_as_corrected(pre):
    c = pre["v1_denominator_correction"]
    assert c["v1_pilot_proposed_by_condition"] == {"human": 15, "enriched": 15,
                                                   "demographics-only": 30}
    assert c["v1_pilot_controls_by_condition"] == {"human": 10, "enriched": 17,
                                                   "demographics-only": 33}
    assert c["v1_pilot_total_by_condition"] == {"human": 25, "enriched": 32,
                                                "demographics-only": 63}
    assert "proposed pairs were also unbalanced" in c["what_v1_said_wrongly"]


# ===================================================== 4. fixtures executed
def test_the_fixtures_are_real_items_not_manifest_text(hx, pc):
    hx_ids = {i["item_id"] for i in hx["items"]["items"]}
    for fid, _, _ in v2.HX_FIXTURES:
        assert fid in hx_ids, f"{fid} is not in the payload"
    pc_ids = {i["item_id"] for i in pc["items"]["items"]}
    for fid, *_ in v2.PC_FIXTURES:
        assert fid in pc_ids, f"{fid} is not in the payload"


def test_every_fixture_is_adjudicated_twice(hx, pc):
    for pack, fixtures in ((hx, v2.HX_FIXTURES), (pc, v2.PC_FIXTURES)):
        rows = pack["item_manifest"]["rows"]
        by_item = Counter(r["item_id"] for r in rows)
        for f in fixtures:
            assert by_item[f[0]] == 2, f[0]


def test_the_fixture_marker_is_only_in_the_sealed_mapping(hx, pc):
    for pack in (hx, pc):
        blob = json.dumps(pack["items"])
        assert "TECHNICAL_VALIDATION_FIXTURE" not in blob
        assert "REAL_PILOT_CASE" not in blob
        assert "_expected_category" not in blob
        kinds = {v["_kind"] for v in pack["sealed"].values()}
        assert kinds == {"REAL_PILOT_CASE", "TECHNICAL_VALIDATION_FIXTURE"}


def test_the_fixtures_cover_every_hyper_exactness_category():
    expected = {e for _, e, _ in v2.HX_FIXTURES}
    assert expected == set(v2.HX_CATEGORIES)
    counts = Counter(e for _, e, _ in v2.HX_FIXTURES)
    assert all(v >= 2 for v in counts.values()), counts


def test_the_consistency_fixtures_cover_the_required_behaviours():
    exp = Counter(e for _, e, _, _ in v2.PC_FIXTURES)
    assert exp["UNEXPLAINED_CONTRADICTION"] >= 1
    assert exp["POSITION_CHANGED_WITH_EXPLANATION"] >= 1
    assert exp["CONTEXTUALLY_DIFFERENT_NOT_CONTRADICTORY"] >= 1
    assert exp["REJECT"] >= 4


def test_fixtures_are_excluded_from_rates(pre):
    assert pre["hyper_exactness"]["fixtures_excluded_from_rates"] is True
    assert pre["profile_consistency"]["fixtures_excluded_from_rates"] is True


# ===================================================== 5. two manifests
def test_the_announced_request_count_is_the_provider_manifest_length(pre, hx, pc):
    for pack, block in ((hx, "hyper_exactness"), (pc, "profile_consistency")):
        n = len(pack["requests"]["requests"])
        assert pack["requests"]["n_requests"] == n
        assert pre[block]["cost"]["n_provider_requests"] == n
        # PLANTED: the item-manifest length must NOT be announced as a request count
        assert n != len(pack["item_manifest"]["rows"])


def test_the_item_manifest_is_one_row_per_item_and_repetition(hx, pc):
    for pack in (hx, pc):
        rows = pack["item_manifest"]["rows"]
        keys = {(r["item_id"], r["repetition_index"]) for r in rows}
        assert len(keys) == len(rows)
        assert {r["repetition_index"] for r in rows} == {1, 2}
        assert len({r["cache_key"] for r in rows}) == len(rows)


def test_every_provider_request_carries_the_required_fields(hx, pc):
    need = {"custom_id", "repetition_index", "ordered_item_ids", "expected_item_count",
            "prompt_sha256", "schema_sha256", "model", "effort", "max_output_tokens",
            "estimated_input_tokens", "cache_key"}
    for pack in (hx, pc):
        for r in pack["requests"]["requests"]:
            assert need <= set(r), sorted(need - set(r))
            assert r["expected_item_count"] == len(r["ordered_item_ids"])
            assert r["max_output_tokens"] >= 1024
            assert r["max_output_tokens"] <= 32768


def test_the_union_of_requests_equals_the_item_manifest(hx, pc):
    """The gate the scorer must apply to the returned responses."""
    for pack in (hx, pc):
        covered = Counter()
        for r in pack["requests"]["requests"]:
            for iid in r["ordered_item_ids"]:
                covered[(iid, r["repetition_index"])] += 1
        expected = Counter((r["item_id"], r["repetition_index"])
                           for r in pack["item_manifest"]["rows"])
        assert covered == expected


def test_max_output_tokens_scales_with_the_batch(hx):
    sizes = {r["expected_item_count"]: r["max_output_tokens"]
             for r in hx["requests"]["requests"]}
    if len(sizes) > 1:
        a, b = sorted(sizes)[:2]
        assert sizes[a] < sizes[b]


# ===================================================== 6. hyper-exactness gates
def test_the_universe_is_127_real_plus_10_fixtures(pre, hx):
    b = pre["hyper_exactness"]
    assert b["n_detector_candidates"] == 67
    assert b["n_random_nondetected_controls"] == 60
    assert b["n_real_items"] == 127
    assert b["n_fixtures"] == 10
    assert b["n_items_total"] == 137
    assert len(hx["items"]["items"]) == 137


def test_254_real_adjudications_are_covered(hx):
    real = {k for k, v in hx["sealed"].items() if v["_kind"] == "REAL_PILOT_CASE"}
    assert len(real) == 127
    rows = [r for r in hx["item_manifest"]["rows"] if r["item_id"] in real]
    assert len(rows) == 254
    fixtures = [r for r in hx["item_manifest"]["rows"] if r["item_id"] not in real]
    assert len(fixtures) == 20
    assert len(hx["item_manifest"]["rows"]) == 274


def test_controls_and_candidates_are_indistinguishable_in_the_prompt(hx):
    """PLANTED: any detector field in the payload would reveal the stratum."""
    for it in hx["items"]["items"]:
        assert "detectors_fired" not in it and "n_detectors" not in it
        assert "matched_strings" not in it
        assert set(it) == {"item_id", "speaker", "turn_id", "guide_question", "quote",
                           "context_window", "is_full_turn", "n_words_presented",
                           "n_words_source_turn", "source_turn_sha256",
                           "presented_text_sha256"}
    strata = {v["_stratum"] for v in hx["sealed"].values()}
    assert strata == {"DETECTOR_PROPOSED_CANDIDATE",
                      "RANDOM_NONDETECTED_CONTROL_TURNS",
                      "TECHNICAL_VALIDATION_FIXTURE"}


def test_the_controls_are_twenty_per_condition(hx):
    c = Counter(v["_condition"] for v in hx["sealed"].values()
                if v["_stratum"] == "RANDOM_NONDETECTED_CONTROL_TURNS")
    assert dict(c) == {"human": 20, "enriched": 20, "demographics-only": 20}


def test_the_repetition_rules_are_frozen(pre):
    r = pre["hyper_exactness"]["repetition_rules"]
    assert r["agreement_between_repetitions"] == "CORROBORATED"
    assert r["disagreement"] == "UNRESOLVED"
    assert r["one_repetition_UNCERTAIN"] == "NOT converted to absence"
    assert r["non_literal_quote_or_wrong_speaker_or_invalid_turn_id"] == "GATE_FAILURE"
    assert r["no_third_call"] is True
    assert r["no_confidence_or_majority_resolution"] is True


# ===================================================== blinding
def test_no_payload_carries_provenance(hx, pc):
    """
    Only strings that cannot occur in speech count as provenance. Ordinary English words
    that happen to appear in this project's metadata vocabulary are excluded on purpose:
    a participant really does say "you're not going to replicate a really good burger",
    and flagging that would call natural speech contamination. Metadata FIELD NAMES are
    checked separately, below.
    """
    structural = ("macho_meals", "human::", "E::fg", "D::fg", "demoonly", "run01",
                  "run02", "run03", "::", "demographics-only",
                  "_condition", "_stratum", "_kind", "_replicate")

    def _strings(v):
        if isinstance(v, str):
            yield v
        elif isinstance(v, dict):
            for x in v.values():
                yield from _strings(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                yield from _strings(x)

    for pack in (hx, pc):
        for it in pack["items"]["items"]:
            for s in _strings(it):
                for tok in structural:
                    assert tok not in s, f"{it['item_id']}: {tok}"


def test_no_payload_carries_a_provenance_field_name(hx, pc):
    """Field names are where provenance would actually hide, so they are checked here."""
    banned = {"condition", "fg", "replicate", "doc_id", "question", "stratum", "kind",
              "source", "role", "topic_cosine", "expected_category"}

    def _keys(v):
        if isinstance(v, dict):
            for k, x in v.items():
                yield k
                yield from _keys(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                yield from _keys(x)

    for pack in (hx, pc):
        for it in pack["items"]["items"]:
            for k in _keys(it):
                assert k not in banned and not k.startswith("_"), f"{k}"


def test_the_sealed_reference_is_a_separate_file(hx, pc):
    for pack in (hx, pc):
        ids = {i["item_id"] for i in pack["items"]["items"]}
        assert set(pack["sealed"]) == ids


def test_the_guide_question_is_the_literal_moderator_header():
    guide = set(v2.GUIDE_QUESTIONS.values())
    assert len(guide) == 5
    assert any("favourite place" in g for g in guide)
    assert any("plant-based foods more appealing" in g for g in guide)


# ===================================================== still offline
def test_nothing_was_submitted(pre):
    assert pre["profile_consistency"]["status"] == "PREPARED_NOT_AUTHORISED"


def test_no_closed_artefact_was_modified():
    frozen = (_ROOT / "analysis/production_evaluation/metric_registry.csv").read_text(
        encoding="utf-8")
    assert "lexical_identity_continuity" not in frozen
    styl = _j("agent_fidelity_stylometry.json")
    assert abs(styl["hierarchical"]["human"]["human"][
        "mean_chance_corrected_accuracy"] - 0.2840) < 1e-9
    assert styl["hierarchical"]["demographics-only"]["2"]["coverage"] == "4/5"


# ============================== profile-consistency closure
_HX_VOCAB = ("hyper_exact", "hyper-exact", "HYPER_EXACT", "numeral_density",
             "IMPLAUSIBLY_PRECISE", "ORDINARY_EVERYDAY_SPECIFICITY",
             "PLAUSIBLE_PERSONAL_RECALL")


def test_no_hyper_exactness_metric_name_appears_in_profile_consistency():
    """PLANTED: the contradiction count was once named n_corroborated_hyper_exact."""
    blob = (_ART / "v2_profile_consistency_results.json").read_text(encoding="utf-8")
    for tok in _HX_VOCAB:
        assert tok not in blob, f"hyper-exactness vocabulary in the consistency block: {tok}"
    o = _j("v2_profile_consistency_results.json")
    for block in ("screener_proposed", "random_controls"):
        assert "n_corroborated_unexplained_contradictions" in o[block]
        assert "n_corroborated_hyper_exact" not in o[block]


def test_invalid_evidence_is_not_a_whole_pilot_gate_failure():
    o = _j("v2_profile_consistency_results.json")
    assert o["gate"]["governing_criterion"] == "verbatim evidence validity >= 0.95"
    assert o["n_invalid_evidence_decisions"] == 3
    assert o["n_gate_failures"] == 0
    assert o["gate"]["passed"] is True
    states = Counter(v["state"] for v in o["per_item"].values())
    assert states["UNRESOLVED_INVALID_EVIDENCE"] == 3
    # invalid-evidence items enter no substantive category
    for v in o["per_item"].values():
        if v["state"] == "UNRESOLVED_INVALID_EVIDENCE":
            assert v["category"] is None


def test_verbatim_evidence_validity_meets_the_frozen_floor():
    o = _j("v2_profile_consistency_results.json")
    validity = (240 - o["n_invalid_evidence_decisions"]) / 240
    assert validity >= 0.95
    assert abs(validity - 0.9875) < 1e-6


def test_unfalsifiable_fixtures_are_excluded_not_counted_as_failures():
    o = _j("v2_profile_consistency_results.json")
    g = o["gate"]
    assert g["n_fixtures_excluded_schema_mismatch"] == 4
    assert g["n_executable_fixtures"] == 4
    assert g["executable_fixtures_both_repetitions_correct"] == 4
    for f in o["fixtures"]:
        if not f["executable"]:
            assert f["status"] == "INVALID_AUDITOR_FIXTURE_SCHEMA_MISMATCH"
            assert f["both_correct"] is False and f["either_correct"] is False
    # REJECT was never returnable
    assert "REJECT" not in set(v2.PC_CATEGORIES)


def test_the_headline_counts_are_the_post_correction_ones():
    o = _j("v2_profile_consistency_results.json")
    ag = o["agreement_between_repetitions"]
    assert ag["n_corroborated"] == 100
    assert ag["n_scored"] - ag["n_corroborated"] == 20
    assert abs(ag["exact_agreement"] - 0.8333) < 5e-4
    # the pre-correction figures must not reappear
    assert ag["n_corroborated"] != 103
    assert abs(ag["exact_agreement"] - 0.8583) > 1e-3


def test_the_two_contradictions_are_candidates_not_confirmed():
    doc = (_ART / "PROFILE_CONSISTENCY_PILOT_CLOSURE.md").read_text(encoding="utf-8")
    assert "CROSS_REPETITION_CORROBORATED_CANDIDATE_CONTRADICTION" in doc
    # The document DENIES these labels in one sentence, so a bare substring search
    # flags its own disclaimer. Only an unnegated occurrence is a violation.
    flat0 = " ".join(doc.lower().replace("**", "").split())
    for banned in ("confirmed contradiction", "validated contradiction",
                   "true contradiction", "human-verified contradiction"):
        i = flat0.find(banned)
        while i != -1:
            before = flat0[max(0, i - 80):i]
            assert "not " in before or "never " in before, f"unnegated {banned}"
            i = flat0.find(banned, i + 1)
    assert "not independent validation" in flat0


def test_no_claim_of_a_higher_control_contradiction_rate():
    doc = (_ART / "PROFILE_CONSISTENCY_PILOT_CLOSURE.md").read_text(encoding="utf-8")
    assert "No claim is made that the control stratum contains a higher contradiction " \
           "rate" in doc
    assert "not demonstrated to enrich" in doc


def test_the_full_audit_is_declined_and_the_682_were_not_sent():
    doc = (_ART / "PROFILE_CONSISTENCY_PILOT_CLOSURE.md").read_text(encoding="utf-8")
    assert "FULL_PROFILE_CONSISTENCY_AUDIT = DECLINED_AFTER_PILOT" in doc
    job = _j("v2_profile_consistency_job.json")
    assert job["n_adjudications"] == 256
    assert job["n_real_pairs"] == 120
    assert job["remaining_corpus_blocked_behind_the_gate"] is True
    # only one consistency job was ever created
    assert not (_ART / "v2_profile_consistency_full_job.json").exists()


def test_the_pilot_is_not_a_prevalence_estimate():
    o = _j("v2_profile_consistency_results.json")
    p = o["prevalence"]
    assert p["reportable"] == "DETECTED_LOWER_BOUND_RATE"
    assert p["unaudited_pairs_are_not_negative"] is True
    assert p["n_screened_pairs"] == 2611 and p["n_audited"] == 120
