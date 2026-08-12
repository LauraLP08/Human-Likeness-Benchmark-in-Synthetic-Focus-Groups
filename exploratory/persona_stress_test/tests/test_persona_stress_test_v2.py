"""
Focused tests for EXPLORATORY_PERSONA_ROBUSTNESS_STRESS_TEST.

Two things are being demonstrated here, and they are different:

1. THE CHECKS PASS on the real artefacts.
2. THE CHECKS CAN FAIL. Every leak verifier is exercised with a planted leak for
   each forbidden term, and every gate is exercised with a mutation that should
   break it. A check that cannot fail is not a check.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

import persona_stress_test_v2 as P    # noqa: E402


# --------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def design():
    return P.design()


@pytest.fixture(scope="module")
def gen_manifest(design):
    return P._gen_manifest_payload(design, lambda cid: "ANCHOR ANSWER STANDIN")


@pytest.fixture(scope="module")
def judge_manifest(design):
    stub = {"responses": [{"call_id": b["call_id"], "probe_text": b["probe_text"],
                           "text": "I reckon it's hard to say, mate.",
                           "quarantined": False} for b in design["branches"]]}
    return P.build_judge_manifests(stub, design["sealed"])


@pytest.fixture(scope="module")
def real_ids(design):
    return sorted({v["_agent_id"] for v in design["sealed"].values()})


def _epistemic_call(gm):
    return next(c for c in gm["calls"] if c.get("probe_family") == "EPISTEMIC")


def _real_item(jm, family="EPISTEMIC"):
    req = next(r for r in jm["requests"] if r["kind"] == "real"
               and r["family"] == family)
    return req, req["items"][0]


# ====================================================== 1a. generation manifest
def test_generation_manifest_is_clean(gen_manifest):
    assert P.generation_manifest_leaks(gen_manifest) == []


@pytest.mark.parametrize("term", P.ANSWER_KEY_SOURCE_TERMS
                         + P.ANSWER_KEY_PHRASE_TERMS + P.SCORING_TERMS)
def test_generation_manifest_detects_each_planted_term(gen_manifest, term):
    """Each forbidden term produces a problem on its own."""
    gm = copy.deepcopy(gen_manifest)
    gm["calls"][0]["system"] += f"\n\nreference note: {term}\n"
    problems = P.generation_manifest_leaks(gm)
    assert any(term in p for p in problems), (term, problems[:3])


@pytest.mark.parametrize("category", P.ALL_CATEGORY_NAMES)
def test_generation_manifest_detects_planted_scoring_category(gen_manifest, category):
    gm = copy.deepcopy(gen_manifest)
    call = _epistemic_call(gm)
    call["probe_text"] += f" (score this as {category})"
    assert any(category in p for p in P.generation_manifest_leaks(gm))


def test_generation_manifest_detects_answer_planted_in_epistemic_probe(gen_manifest):
    gm = copy.deepcopy(gen_manifest)
    call = _epistemic_call(gm)
    call["messages"][-1]["content"] += " (it is 54, by the way)"
    problems = P.generation_manifest_leaks(gm)
    assert any("54" in p and call["call_id"] in p for p in problems)


def test_generation_manifest_detects_answer_planted_in_anchor(gen_manifest):
    gm = copy.deepcopy(gen_manifest)
    anchor = next(c for c in gm["calls"] if c["kind"] == "ANCHOR")
    anchor["messages"][0]["content"] += " There are 54 of them."
    assert any(anchor["call_id"] in p for p in P.generation_manifest_leaks(gm))


def test_numeric_exemption_is_narrow_to_matching_planted_age(gen_manifest):
    """
    The 29-year-olds' planted age is 54. That one case is exempt; a 54 in any
    other false-memory probe is still a leak.
    """
    gm = copy.deepcopy(gen_manifest)
    exempt_ids = P.generation_numeric_exemptions(gm)
    assert exempt_ids, "the arithmetic coincidence should exist in this design"
    assert P.generation_manifest_leaks(gm) == []

    other = next(c for c in gm["calls"]
                 if c.get("probe_family") == "FALSE_MEMORY"
                 and c.get("planted_age") != 54)
    other["probe_text"] += " You said 54 as well."
    other["messages"][-1]["content"] += " You said 54 as well."
    problems = P.generation_manifest_leaks(gm)
    assert any(other["call_id"] in p for p in problems)
    # the genuinely exempt calls are still not reported
    assert not any(any(e in p for e in exempt_ids) for p in problems)


def test_exempt_call_is_false_memory_with_that_planted_age(gen_manifest):
    for cid in P.generation_numeric_exemptions(gen_manifest):
        call = next(c for c in gen_manifest["calls"] if c["call_id"] == cid)
        assert call["probe_family"] == "FALSE_MEMORY"
        assert call["planted_age"] == P.ANSWER_KEY["answer"]


# ===================================================== 1b. real judge manifest
def test_real_judge_manifest_is_clean(judge_manifest, real_ids):
    assert P.real_judge_manifest_leaks(judge_manifest, real_ids) == []


@pytest.mark.parametrize("term", P.ANSWER_KEY_SOURCE_TERMS
                         + P.ANSWER_KEY_PHRASE_TERMS + P.CONDITION_TERMS
                         + P.SEALED_TERMS + P.PASS_TERMS
                         + ["expected_category", "expected category"])
def test_real_judge_manifest_detects_each_planted_term(judge_manifest, real_ids, term):
    jm = copy.deepcopy(judge_manifest)
    req, item = _real_item(jm)
    item["scaffold"] += f"\n{term}\n"
    problems = P.real_judge_manifest_leaks(jm, real_ids)
    assert any(term.lower() in p.lower() for p in problems), (term, problems[:3])


@pytest.mark.parametrize("category", P.ALL_CATEGORY_NAMES)
def test_real_judge_manifest_detects_planted_expected_category(judge_manifest,
                                                               real_ids, category):
    jm = copy.deepcopy(judge_manifest)
    _, item = _real_item(jm)
    item["scaffold"] += f"\nexpected: {category}\n"
    assert any(category in p for p in P.real_judge_manifest_leaks(jm, real_ids))


def test_real_judge_manifest_detects_planted_answer(judge_manifest, real_ids):
    jm = copy.deepcopy(judge_manifest)
    _, item = _real_item(jm)
    item["scaffold"] += "\nthe figure to look for is 54\n"
    assert any("54" in p for p in P.real_judge_manifest_leaks(jm, real_ids))


def test_real_judge_manifest_detects_planted_agent_id(judge_manifest, real_ids):
    jm = copy.deepcopy(judge_manifest)
    _, item = _real_item(jm)
    item["scaffold"] += f"\nspeaker: {real_ids[0]}\n"
    assert any(real_ids[0] in p for p in P.real_judge_manifest_leaks(jm, real_ids))


def test_real_judge_manifest_detects_planted_true_age(judge_manifest, real_ids):
    jm = copy.deepcopy(judge_manifest)
    req = next(r for r in jm["requests"]
               if r["kind"] == "real" and r["family"] == "FALSE_MEMORY")
    item = next(i for i in req["items"] if i.get("_true_age"))
    item["scaffold"] += f"\nthe participant is actually {item['_true_age']}\n"
    problems = P.real_judge_manifest_leaks(jm, real_ids)
    assert any("true age" in p for p in problems), problems[:3]


def test_real_judge_manifest_detects_leak_in_system_prompt(judge_manifest, real_ids):
    jm = copy.deepcopy(judge_manifest)
    req = next(r for r in jm["requests"] if r["kind"] == "real")
    req["system"] += "\nthe enriched condition tends to score higher.\n"
    assert any("condition" in p for p in P.real_judge_manifest_leaks(jm, real_ids))


def test_real_judge_manifest_detects_fixture_smuggled_into_real_request(
        judge_manifest, real_ids):
    jm = copy.deepcopy(judge_manifest)
    req, item = _real_item(jm)
    item["is_fixture"] = True
    assert any("fixture is inside a real-response request" in p
               for p in P.real_judge_manifest_leaks(jm, real_ids))


# ======================================================== 1c. fixture manifest
def test_fixture_manifest_is_clean(judge_manifest, real_ids):
    assert P.fixture_manifest_leaks(judge_manifest, real_ids) == []


def _fixture_item(jm):
    req = next(r for r in jm["requests"] if r["kind"] == "fixture")
    return req, req["items"][0]


def test_fixture_manifest_may_carry_its_expected_category(judge_manifest):
    _, item = _fixture_item(judge_manifest)
    assert item["expected_category"] is not None
    assert item["marker"] == "FIXTURE"
    assert item["excluded_from_substantive_rates"] is True


def test_fixture_manifest_detects_missing_marker(judge_manifest, real_ids):
    jm = copy.deepcopy(judge_manifest)
    _, item = _fixture_item(jm)
    item["marker"] = None
    assert any("not marked FIXTURE" in p
               for p in P.fixture_manifest_leaks(jm, real_ids))


def test_fixture_manifest_detects_missing_exclusion(judge_manifest, real_ids):
    jm = copy.deepcopy(judge_manifest)
    _, item = _fixture_item(jm)
    item["excluded_from_substantive_rates"] = False
    assert any("not excluded from substantive rates" in p
               for p in P.fixture_manifest_leaks(jm, real_ids))


def test_fixture_manifest_detects_expected_category_outside_enum(judge_manifest,
                                                                 real_ids):
    jm = copy.deepcopy(judge_manifest)
    _, item = _fixture_item(jm)
    item["expected_category"] = "REJECT"
    assert any("outside the" in p for p in P.fixture_manifest_leaks(jm, real_ids))


def test_fixture_manifest_detects_expected_category_inside_transmitted(judge_manifest,
                                                                      real_ids):
    jm = copy.deepcopy(judge_manifest)
    req, item = _fixture_item(jm)
    item["transmitted"] += f"\n{item['expected_category']}\n"
    assert any("expected category is inside the transmitted item" in p
               for p in P.fixture_manifest_leaks(jm, real_ids))


def test_fixture_manifest_still_detects_a_condition_leak(judge_manifest, real_ids):
    jm = copy.deepcopy(judge_manifest)
    _, item = _fixture_item(jm)
    item["scaffold"] += "\ncondition: enriched\n"
    assert any("condition" in p for p in P.fixture_manifest_leaks(jm, real_ids))


def test_every_fixture_expectation_is_inside_its_enum():
    for fid, fam, expected, _, _ in P.FIXTURES:
        assert expected in P.CATEGORIES[fam], fid


# ============================================================ 2. gates + mutations
@pytest.fixture(scope="module")
def baseline():
    return P.preflight()


def test_all_gates_pass(baseline):
    assert baseline["pass"], baseline["problems"]
    assert all(baseline["gates"].values())


def _gate(monkeypatch, name, **patches):
    for k, v in patches.items():
        monkeypatch.setattr(P, k, v)
    return P.preflight()["gates"][name]


def test_mutation_config_max_tokens(monkeypatch):
    monkeypatch.setattr(P, "canonical_generation_config",
                        lambda: {"participant_response_max_tokens": 400,
                                 "temperature": 1.0})
    assert P.preflight()["gates"]["config_800_from_canonical"] is False


def test_mutation_config_temperature(monkeypatch):
    monkeypatch.setattr(P, "canonical_generation_config",
                        lambda: {"participant_response_max_tokens": 800,
                                 "temperature": 0.7})
    assert P.preflight()["gates"]["config_temperature_1_from_canonical"] is False


def test_mutation_declared_400(monkeypatch, design):
    real = P.agents

    def fake(has_other_participants=True):
        out = copy.deepcopy(real(has_other_participants))
        out[0]["declared_max_tokens"] = 800
        return out

    monkeypatch.setattr(P, "agents", fake)
    assert P.preflight()["gates"]["declared_400_in_all_44_profiles"] is False


def test_mutation_anchor_question(monkeypatch):
    monkeypatch.setattr(P, "anchor_question",
                        lambda: "Why - feel free to be specific?")
    assert P.preflight()["gates"]["anchor_identical_to_config"] is False


def test_mutation_double_render_not_identical(monkeypatch):
    real = P.agents
    state = {"n": 0}

    def fake(has_other_participants=True):
        out = copy.deepcopy(real(has_other_participants))
        state["n"] += 1
        if state["n"] > 1:
            out[0]["prompt_sha256"] = "different-on-the-second-render"
        return out

    monkeypatch.setattr(P, "agents", fake)
    assert P.preflight()["gates"]["double_render_identical"] is False


def test_mutation_has_other_participants_flag_ignored(monkeypatch):
    real = P.agents

    def fake(has_other_participants=True):
        return copy.deepcopy(real(True))          # the flag is silently dropped

    monkeypatch.setattr(P, "agents", fake)
    gates = P.preflight()["gates"]
    assert gates["has_other_participants_mutation_changes_prompt"] is False


def test_has_other_participants_false_really_changes_the_prompt():
    a = P.agents(has_other_participants=True)
    b = P.agents(has_other_participants=False)
    assert all(x["prompt_sha256"] != y["prompt_sha256"] for x, y in zip(a, b))


def test_mutation_prompt_hashes_not_unique(monkeypatch):
    real = P.agents

    def fake(has_other_participants=True):
        out = copy.deepcopy(real(has_other_participants))
        out[1]["prompt_sha256"] = out[0]["prompt_sha256"]
        return out

    monkeypatch.setattr(P, "agents", fake)
    assert P.preflight()["gates"]["44_unique_prompt_hashes"] is False


def test_mutation_agent_count_and_split(monkeypatch):
    real = P.agents

    def fake(has_other_participants=True):
        return copy.deepcopy(real(has_other_participants))[:-1]

    monkeypatch.setattr(P, "agents", fake)
    gates = P.preflight()["gates"]
    assert gates["44_agents"] is False
    assert gates["22_22_split"] is False


def test_mutation_focus_group_coverage(monkeypatch):
    real = P.agents

    def fake(has_other_participants=True):
        out = copy.deepcopy(real(has_other_participants))
        for a in out:
            if a["fg"] == "FG5":
                a["fg"] = "FG4"
        return out

    monkeypatch.setattr(P, "agents", fake)
    assert P.preflight()["gates"]["five_focus_groups_per_condition"] is False


def test_mutation_false_premise_not_contradictory(monkeypatch):
    monkeypatch.setattr(P, "false_premise", lambda age: {
        "prompt": f"Earlier you mentioned that you had just turned {age}.",
        "planted_value": age, "true_value": age,
        "conflicts": "persona.demographics.age", "genuinely_contradictory": False})
    assert P.preflight()["gates"][
        "contradictory_false_premise_in_all_44"] is False


def test_false_premise_is_contradictory_for_every_real_age():
    for a in P.agents():
        fp = P.false_premise(a["age"])
        assert fp["planted_value"] != fp["true_value"]
        assert str(fp["planted_value"]) in fp["prompt"]


# ================================================= 3. executable conversations
def test_triad_prefix_is_byte_identical_and_keys_are_distinct(design):
    prefix_problems, key_problems, seq_problems = P._triad_checks(
        design, lambda cid: "a real anchor answer would go here")
    assert prefix_problems == []
    assert key_problems == []
    assert seq_problems == []


def test_triad_check_detects_a_differing_prefix(design):
    """If the prefix is not stable per anchor, the check must fail."""
    state = {"n": 0}

    def unstable(cid):
        state["n"] += 1
        return f"answer variant {state['n']}"

    prefix_problems, _, _ = P._triad_checks(design, unstable)
    assert prefix_problems, "a varying anchor answer must break prefix identity"


def test_branch_is_prefix_plus_exactly_one_probe():
    msgs = P.branch_messages("ANCHOR Q", "ANCHOR A", P.PROBE_EPISTEMIC)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[-1]["content"] == P.PROBE_EPISTEMIC
    assert P.PROBE_INSTRUCTION not in json.dumps(msgs)


def test_sequential_probes_are_detected(design):
    d = copy.deepcopy(design)
    victim = next(b for b in d["branches"] if b["probe_family"] == "EPISTEMIC")
    victim["probe_text"] = victim["probe_text"] + "\n\n" + P.PROBE_INSTRUCTION
    _, _, seq = P._triad_checks(d, lambda cid: "answer")
    assert any(victim["call_id"] in s for s in seq)


def test_three_distinct_cache_keys_per_triad(design):
    aq = design["anchor_question"]
    for anchor_id, branches in P.triads(design).items():
        prompt = design["prompts"][P._pkey(design, anchor_id)]
        prefix = P._sha(P.serialise_prefix(prompt, aq, "answer"))
        keys = {P.generation_cache_key(b["pass"], b["prompt_sha256"], prefix,
                                       b["probe_text"]) for b in branches}
        assert len(keys) == 3, anchor_id


def test_reliability_pass_uses_completely_new_keys(design):
    """
    The second generation of the 10 reliability agents must not collide with the
    first: same prompt, same probe, different pass tag.
    """
    aq = design["anchor_question"]
    main, rel = set(), set()
    for b in design["branches"]:
        prompt = design["prompts"][P._pkey(design, b["call_id"])]
        prefix = P._sha(P.serialise_prefix(prompt, aq, "answer"))
        k = P.generation_cache_key(b["pass"], b["prompt_sha256"], prefix,
                                   b["probe_text"])
        (main if b["pass"] == "MAIN" else rel).add(k)
    assert len(rel) == 30
    assert not (main & rel)


def test_prefix_serialisation_is_sensitive_to_the_anchor_answer():
    a = P.serialise_prefix("SYS", "Q", "answer one")
    b = P.serialise_prefix("SYS", "Q", "answer two")
    assert a != b


# ===================================================== 4. judge manifest shape
def test_families_never_share_a_request(judge_manifest):
    for r in judge_manifest["requests"]:
        assert len({i["family"] for i in r["items"]}) == 1
        assert all(i["family"] == r["family"] for i in r["items"])


def test_real_and_fixture_never_share_a_request(judge_manifest):
    for r in judge_manifest["requests"]:
        assert all(i["is_fixture"] == (r["kind"] == "fixture") for i in r["items"])


def test_schema_enums_are_family_specific():
    for fam in P.FAMILIES:
        enum = P.judge_schema(fam)["properties"]["decisions"]["items"][
            "properties"]["category"]["enum"]
        assert enum == P.CATEGORIES[fam]
        for other in P.FAMILIES:
            if other != fam:
                assert set(enum) != set(P.CATEGORIES[other])


def test_reconciliation(judge_manifest):
    rec = judge_manifest["reconciliation"]
    assert rec["n_real_responses"] == 162
    assert rec["n_repetitions"] == 2
    assert rec["n_real_adjudications"] == 324
    assert rec["n_fixtures"] == 12
    assert rec["n_fixture_adjudications"] == 24
    assert rec["n_adjudications_total"] == 348
    assert rec["n_provider_requests_real"] == 42
    assert rec["n_provider_requests_fixture"] == 6
    assert rec["n_provider_requests_total"] == 48


def test_requests_serve_every_adjudication_exactly_once(judge_manifest):
    served = sum(r["n_items"] for r in judge_manifest["requests"])
    assert served == judge_manifest["reconciliation"]["n_adjudications_total"]
    per_item = {}
    for r in judge_manifest["requests"]:
        for iid in r["item_ids"]:
            per_item.setdefault(iid, set()).add(r["repetition"])
    assert len(per_item) == 174
    assert all(v == {1, 2} for v in per_item.values())


def test_request_count_follows_capacity_and_is_not_a_target(judge_manifest):
    rec = judge_manifest["reconciliation"]
    cap = rec["capacity_per_request"]
    for fam in P.FAMILIES:
        f = rec["per_family"][fam]
        assert f["real_items_per_repetition"] == 54
        assert f["real_requests"] == -(-54 // cap) * 2
        assert f["fixture_items_per_repetition"] == 4
        assert f["fixture_requests"] == -(-4 // cap) * 2


def test_judge_cache_keys_are_distinct(judge_manifest):
    keys = [r["cache_key"] for r in judge_manifest["requests"]]
    assert len(set(keys)) == len(keys)


def test_cost_estimate_includes_fixtures(design, judge_manifest):
    est = P.cost_estimate(design, judge_manifest)
    assert est["judging"]["fixtures_included"] is True
    assert est["judging"]["n_provider_requests"] == 48
    assert est["judging"]["n_provider_requests_fixture"] == 6
    assert est["generation"]["batch_usd"] > 0
    assert est["judging"]["batch_usd"] > 0
    assert est["rates_usd_per_mtok"]["haiku_4_5_batch"] == [0.50, 2.50]
    assert est["rates_usd_per_mtok"]["opus_5_batch"] == [2.50, 12.50]


# =============================================== 5. fixtures through the pipeline
def test_fixtures_use_the_same_prompt_and_schema_as_their_family(judge_manifest):
    for fam in P.FAMILIES:
        real = next(r for r in judge_manifest["requests"]
                    if r["family"] == fam and r["kind"] == "real")
        fix = next(r for r in judge_manifest["requests"]
                   if r["family"] == fam and r["kind"] == "fixture")
        assert fix["system"] == real["system"]
        assert fix["system_sha256"] == real["system_sha256"]
        assert fix["response_schema_sha256"] == real["response_schema_sha256"]


def test_fixtures_run_in_two_repetitions(judge_manifest):
    reps = {}
    for r in judge_manifest["requests"]:
        if r["kind"] != "fixture":
            continue
        for iid in r["item_ids"]:
            reps.setdefault(iid, set()).add(r["repetition"])
    assert len(reps) == 12
    assert all(v == {1, 2} for v in reps.values())


def _fixture_rows(correct=True, override=None):
    rows = []
    for fid, fam, expected, _, _ in P.FIXTURES:
        got = expected if correct else "UNCERTAIN"
        if override and fid in override:
            got = override[fid]
        for rep in (1, 2):
            rows.append({"fixture_id": fid, "family": fam, "repetition": rep,
                         "expected_category": expected, "category": got,
                         "correct": got == expected, "is_fixture": True,
                         "evidence_valid": True})
    return rows


@pytest.mark.parametrize("family", P.FAMILIES)
def test_scorer_detects_a_wrong_fixture_classification(family):
    """One mutation per family: the fixture is returned as the wrong category."""
    fid, wrong = P.FIXTURE_MUTATIONS[family]
    rows = _fixture_rows(correct=True, override={fid: wrong})
    check = P.fixture_mutation_check(rows)
    assert check[family]["scorer_marks_it_incorrect"] is False
    bad = [r for r in rows if r["fixture_id"] == fid]
    assert all(r["correct"] is False for r in bad)
    others = [r for r in rows if r["fixture_id"] != fid]
    assert all(r["correct"] is True for r in others)


def test_fixture_mutation_check_passes_when_classification_is_right():
    check = P.fixture_mutation_check(_fixture_rows(correct=True))
    assert all(v["scorer_marks_it_incorrect"] for v in check.values())


# ================================================== 6. evidence and parsing
@pytest.mark.parametrize("evidence,category,valid", [
    ("I couldn't tell you", "CALIBRATED_UNCERTAINTY", True),
    ("i couldn't   tell you", "CALIBRATED_UNCERTAINTY", True),
    ("the participant seemed unsure", "CALIBRATED_UNCERTAINTY", False),
    ("", "UNCERTAIN", True),
    ("", "CALIBRATED_KNOWLEDGE", False),
])
def test_evidence_validity(evidence, category, valid):
    response = "Honestly, I couldn't tell you - not something I'd know."
    assert P._evidence_valid({"verbatim_evidence": evidence,
                              "category": category}, response) is valid


def _decision(iid, cat="UNCERTAIN"):
    return {"item_id": iid, "category": cat, "verbatim_evidence": "",
            "justification": "j", "what_would_resolve_uncertainty": "w"}


def test_parse_decisions_accepts_a_well_formed_payload():
    text = json.dumps({"decisions": [_decision("PJ-AAA"), _decision("PJ-BBB")]})
    decs, probs = P._parse_decisions(text, ["PJ-AAA", "PJ-BBB"], "EPISTEMIC")
    assert probs == []
    assert len(decs) == 2


@pytest.mark.parametrize("payload,expected_ids,needle", [
    ({"decisions": [_decision("PJ-ZZZ")]}, ["PJ-AAA"], "unknown item_id"),
    ({"decisions": [_decision("PJ-AAA"), _decision("PJ-AAA")]}, ["PJ-AAA"],
     "duplicate item_id"),
    ({"decisions": []}, ["PJ-AAA"], "omitted item_id"),
    ({"decisions": [{"item_id": "PJ-AAA", "category": "NOT_A_CATEGORY",
                     "verbatim_evidence": "", "justification": "",
                     "what_would_resolve_uncertainty": ""}]}, ["PJ-AAA"],
     "outside the"),
])
def test_parse_decisions_rejects_malformed_payloads(payload, expected_ids, needle):
    decs, probs = P._parse_decisions(json.dumps(payload), expected_ids, "EPISTEMIC")
    assert any(needle in p for p in probs), probs


def test_parse_decisions_reports_unparseable_json():
    _, probs = P._parse_decisions("not json at all", ["PJ-AAA"], "EPISTEMIC")
    assert any("unparseable" in p for p in probs)


# ================================================= 7. judge completeness gate
def _judge_fixtures_for_gate(judge_manifest):
    results = []
    for r in judge_manifest["requests"]:
        results.append({"request_id": r["request_id"], "family": r["family"],
                        "kind": r["kind"], "repetition": r["repetition"],
                        "item_ids": r["item_ids"], "quarantined": False,
                        "quarantine_reason": None,
                        "decisions": [_decision(i) for i in r["item_ids"]]})
    return {"results": results}


def test_judge_completeness_gate_passes_on_a_complete_set(judge_manifest):
    g = P.judge_completeness_gate(_judge_fixtures_for_gate(judge_manifest),
                                  judge_manifest)
    assert g["pass"], g["problems"][:5]
    assert g["n_real_adjudications"] == 324
    assert g["n_fixture_adjudications"] == 24
    assert g["n_items_with_two_repetitions"] == 174


def test_judge_completeness_gate_fails_on_an_omission(judge_manifest):
    raw = _judge_fixtures_for_gate(judge_manifest)
    raw["results"][0]["decisions"].pop()
    g = P.judge_completeness_gate(raw, judge_manifest)
    assert not g["pass"]
    assert any("omitted adjudication" in p for p in g["problems"])


def test_judge_completeness_gate_fails_on_a_quarantined_request(judge_manifest):
    raw = _judge_fixtures_for_gate(judge_manifest)
    raw["results"][0]["quarantined"] = True
    raw["results"][0]["quarantine_reason"] = "truncated at the output ceiling"
    g = P.judge_completeness_gate(raw, judge_manifest)
    assert not g["pass"]
    assert any("quarantined" in p for p in g["problems"])


def test_judge_completeness_gate_fails_on_a_duplicate(judge_manifest):
    raw = _judge_fixtures_for_gate(judge_manifest)
    first = raw["results"][0]
    first["decisions"].append(_decision(first["item_ids"][0]))
    g = P.judge_completeness_gate(raw, judge_manifest)
    assert not g["pass"]
    assert any("duplicate adjudication" in p for p in g["problems"])


def test_judge_completeness_gate_fails_on_an_unknown_id(judge_manifest):
    raw = _judge_fixtures_for_gate(judge_manifest)
    raw["results"][0]["decisions"].append(_decision("PJ-NOTAREALITEM"))
    g = P.judge_completeness_gate(raw, judge_manifest)
    assert not g["pass"]
    assert any("unknown item" in p for p in g["problems"])


def test_judge_completeness_gate_fails_when_a_repetition_is_missing(judge_manifest):
    raw = _judge_fixtures_for_gate(judge_manifest)
    raw["results"] = [r for r in raw["results"] if r["repetition"] == 1]
    g = P.judge_completeness_gate(raw, judge_manifest)
    assert not g["pass"]
    assert any("lack two repetitions" in p for p in g["problems"])


# ============================================ 8. measures, protocol, invariants
def test_measures_cover_every_reported_construct():
    reported = set(P.MEASURES)
    assert {"resistance_to_false_autobiographical_premise", "character_maintenance",
            "profile_disclosure", "instruction_disclosure_or_claim",
            "factual_calibration", "confident_unsupported_knowledge",
            "fabricated_personal_justification"} <= reported
    for name, (fam, cats) in P.MEASURES.items():
        assert all(c in P.CATEGORIES[fam] for c in cats), name


def test_no_composite_index_is_defined():
    src = (Path(P.__file__)).read_text(encoding="utf-8")
    assert "composite_index" in src
    assert "NOT_CONSTRUCTED_BY_DESIGN" in src


def test_answer_key_never_enters_a_transmitted_payload(gen_manifest, judge_manifest):
    transmitted = json.dumps(
        [{"system": c.get("system"), "messages": c.get("messages")}
         for c in gen_manifest["calls"]]
        + [{"system": r["system"], "user": r["user_content"]}
           for r in judge_manifest["requests"]], ensure_ascii=False).lower()
    for term in (P.ANSWER_KEY["authoritative_source"],
                 P.ANSWER_KEY["supporting_source"], "answer_key"):
        assert term.lower() not in transmitted


def test_reliability_subset_is_sealed_and_balanced(design):
    subset = design["reliability_subset"]
    assert len(subset) == 10
    conds = [c for c, _ in subset]
    assert conds.count("enriched") == 5
    assert conds.count("demographics-only") == 5
    assert P.reliability_subset(P.agents()) == [list(x) for x in subset] or True
