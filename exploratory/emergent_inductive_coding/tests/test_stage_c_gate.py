"""
Mutation tests for the hardened Stage C gate.

Each planted defect must FAIL. A gate that cannot be made to fail is not a gate, and a
partial corpus that slips through here would be treated as complete by every later stage.

Offline; no API call.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import stage_b_taxonomy as sb       # noqa: E402
import stage_c_score as sc2         # noqa: E402


# ------------------------------------------------------------- fixtures
def _requests(n_themes=4, questions=(1, 2), reps=(1, 2), tax_hash="H"):
    out = []
    for q in questions:
        ids = [f"RT_Q{q}_{i}" for i in range(n_themes)]
        for rep in reps:
            out.append({"custom_request_key": f"sc::q{q}::r{rep}",
                        "question": q, "repetition_index": rep,
                        "expected_raw_theme_ids": ids,
                        "valid_cluster_ids": ["C1", "C2"],
                        "taxonomy_sha256": tax_hash})
    return out


def _parsed(requests, cluster="C1"):
    out = {}
    for r in requests:
        out[(r["question"], r["repetition_index"])] = {
            i: cluster for i in r["expected_raw_theme_ids"]}
    return out


# ============================================================ taxonomy hash
def _tax(clusters):
    return {"clusters": clusters,
            "taxonomy_sha256": sb._sha(json.dumps({"clusters": clusters},
                                                  sort_keys=True, ensure_ascii=False))}


def test_matching_taxonomy_hashes_pass():
    clusters = [{"cluster_id": "C1", "label": "l", "definition": "d"}]
    t = _tax(clusters)
    reqs = _requests(tax_hash=t["taxonomy_sha256"], questions=(1,))
    out = sc2.verify_taxonomy_hashes({"1": t}, reqs)
    assert out["pass"] is True


def test_planted_altered_taxonomy_fails_the_hash_check():
    """PLANTED: a cluster definition edited after freezing."""
    clusters = [{"cluster_id": "C1", "label": "l", "definition": "d"}]
    t = _tax(clusters)
    frozen = t["taxonomy_sha256"]
    t["clusters"][0]["definition"] = "TAMPERED"      # drift after freezing
    reqs = _requests(tax_hash=frozen, questions=(1,))
    out = sc2.verify_taxonomy_hashes({"1": t}, reqs)
    assert out["pass"] is False
    assert any("recomputed taxonomy hash" in p for p in out["problems"])


def test_planted_stage_c_request_carrying_a_different_hash_fails():
    clusters = [{"cluster_id": "C1", "label": "l", "definition": "d"}]
    t = _tax(clusters)
    reqs = _requests(tax_hash="A_DIFFERENT_HASH", questions=(1,))
    out = sc2.verify_taxonomy_hashes({"1": t}, reqs)
    assert out["pass"] is False
    assert any("Stage C requests carry" in p for p in out["problems"])


# ========================================================= completeness gate
def test_a_whole_corpus_passes_the_completeness_gate(monkeypatch):
    monkeypatch.setattr(sc2, "EXPECTED_THEMES", 8)
    monkeypatch.setattr(sc2, "EXPECTED_CALLS", 4)
    monkeypatch.setattr(sc2, "EXPECTED_QUESTIONS", 2)
    reqs = _requests()
    out = sc2.completeness_gate(_parsed(reqs), [], reqs)
    assert out["pass"] is True, out["problems"]
    assert out["n_raw_theme_ids_covered"] == 8
    assert out["n_with_exactly_two_assignments"] == 8


def test_planted_a_missing_repetition_fails(monkeypatch):
    """PLANTED: one of the two repetitions never returned."""
    monkeypatch.setattr(sc2, "EXPECTED_THEMES", 8)
    monkeypatch.setattr(sc2, "EXPECTED_CALLS", 4)
    monkeypatch.setattr(sc2, "EXPECTED_QUESTIONS", 2)
    reqs = _requests()
    p = _parsed(reqs)
    del p[(1, 2)]
    out = sc2.completeness_gate(p, [{"question": 1, "repetition": 2}], reqs)
    assert out["pass"] is False
    assert any("repetitions [1]" in x for x in out["problems"])
    assert any("without exactly 2 assignments" in x for x in out["problems"])


def test_planted_a_whole_question_missing_fails(monkeypatch):
    monkeypatch.setattr(sc2, "EXPECTED_THEMES", 8)
    monkeypatch.setattr(sc2, "EXPECTED_CALLS", 4)
    monkeypatch.setattr(sc2, "EXPECTED_QUESTIONS", 2)
    reqs = _requests()
    p = {k: v for k, v in _parsed(reqs).items() if k[0] != 2}
    out = sc2.completeness_gate(p, [], reqs)
    assert out["pass"] is False
    assert any("questions complete" in x for x in out["problems"])


def test_planted_525_themes_instead_of_526_fails(monkeypatch):
    """PLANTED: one theme silently dropped from both repetitions."""
    monkeypatch.setattr(sc2, "EXPECTED_THEMES", 8)
    monkeypatch.setattr(sc2, "EXPECTED_CALLS", 4)
    monkeypatch.setattr(sc2, "EXPECTED_QUESTIONS", 2)
    reqs = _requests()
    p = _parsed(reqs)
    victim = "RT_Q1_0"
    for rep in (1, 2):
        p[(1, rep)].pop(victim)
    out = sc2.completeness_gate(p, [], reqs)
    assert out["pass"] is False
    assert out["n_raw_theme_ids_covered"] == 7
    assert any("no assignment" in x for x in out["problems"])


def test_planted_an_unknown_id_fails(monkeypatch):
    monkeypatch.setattr(sc2, "EXPECTED_THEMES", 8)
    monkeypatch.setattr(sc2, "EXPECTED_CALLS", 4)
    monkeypatch.setattr(sc2, "EXPECTED_QUESTIONS", 2)
    reqs = _requests()
    p = _parsed(reqs)
    p[(1, 1)]["RT_INVENTED"] = "C1"
    out = sc2.completeness_gate(p, [], reqs)
    assert out["pass"] is False
    assert any("unknown raw_theme_id" in x for x in out["problems"])


def test_a_quarantined_call_is_documented_but_still_blocks(monkeypatch):
    monkeypatch.setattr(sc2, "EXPECTED_THEMES", 8)
    monkeypatch.setattr(sc2, "EXPECTED_CALLS", 4)
    monkeypatch.setattr(sc2, "EXPECTED_QUESTIONS", 2)
    reqs = _requests()
    p = _parsed(reqs)
    del p[(2, 1)]
    q = [{"question": 2, "repetition": 1, "problems": ["truncated"]}]
    out = sc2.completeness_gate(p, q, reqs)
    assert out["pass"] is False
    assert out["n_quarantined_calls"] == 1
    assert out["quarantine"] == q, "the quarantine must still be documented"


# =============================================================== four states
def test_two_agreeing_repetitions_matching_stage_b():
    assert sc2.classify("C1", "C1", "C1") == sc2.STABLE_SAME


def test_planted_two_agreeing_repetitions_that_differ_from_stage_b():
    """
    PLANTED: the repetitions are perfectly stable AND both disagree with Stage B.
    Collapsing this into STABLE would hide a systematic Stage-B error.
    """
    assert sc2.classify("C2", "C2", "C1") == sc2.STABLE_DIFF


def test_disagreeing_repetitions_are_unstable():
    assert sc2.classify("C1", "C2", "C1") == sc2.UNSTABLE


def test_both_uncertain_is_unresolved_not_stable():
    assert sc2.classify("UNCERTAIN", "UNCERTAIN", "C1") == sc2.UNRESOLVED
    assert sc2.classify("UNCERTAIN", "UNCERTAIN", "UNCERTAIN") == sc2.UNRESOLVED


def test_a_missing_repetition_is_unresolved():
    assert sc2.classify(None, "C1", "C1") == sc2.UNRESOLVED
    assert sc2.classify("C1", None, "C1") == sc2.UNRESOLVED


def test_stage_b_uncertain_resolved_by_agreeing_repetitions_is_stable_diff():
    """Stage B said UNCERTAIN; both repetitions agree on a real cluster."""
    assert sc2.classify("C1", "C1", "UNCERTAIN") == sc2.STABLE_DIFF


# ------------------------------------------------- no premature resolution
def test_the_scorer_does_not_choose_a_final_assignment():
    src = Path(_ROOT / "scripts/stage_c_score.py").read_text(encoding="utf-8")
    assert "most_common(1)" not in src, "no modal assignment may be selected here"
    assert "modal_assignment_used" in src
