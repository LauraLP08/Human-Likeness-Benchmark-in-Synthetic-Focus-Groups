"""
Offline guards for BLINDED_CROSS_MODEL_LLM_ADJUDICATION.

Nothing here calls the Claude API. The protocol is proved blind, the repetitions are
proved independent, and corroboration is proved to refuse anything short of two
agreeing, evidenced, non-LOW readings.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cross_model_audit_q3 as cm       # noqa: E402
import emergent_calibration_q3 as cal   # noqa: E402

OUT = ROOT / "analysis" / "production_evaluation" / "emergent_calibration_q3"

pytestmark = pytest.mark.skipif(
    not (OUT / "bplus_evaluation_q3.json").exists(),
    reason="B+ evaluation not built",
)


@pytest.fixture(scope="module")
def cases():
    return cm.build_cases()


@pytest.fixture(scope="module")
def manifest():
    return cm.build_manifest()


# ---------------------------------------------------------------------------
# It is not what it must not be called
# ---------------------------------------------------------------------------

def test_classification_and_disclaimers():
    assert cm.CLASSIFICATION == "BLINDED_CROSS_MODEL_LLM_ADJUDICATION"
    joined = " ".join(cm.NOT_WHAT_IT_IS)
    assert "not human validation" in joined
    assert "not a neutral judge" in joined
    assert "not ground truth" in joined
    doc = " ".join(cm.__doc__.split()).lower()
    assert "not human validation" in doc


def test_no_api_client_is_constructed_at_import():
    """Importing the module must not be able to spend anything."""
    src = (ROOT / "scripts" / "cross_model_audit_q3.py").read_text(encoding="utf-8")
    for forbidden in ("anthropic.Anthropic(", "client.messages", "messages.create",
                      "batches.create", "import anthropic"):
        assert forbidden not in src, forbidden


# ---------------------------------------------------------------------------
# Blinding
# ---------------------------------------------------------------------------

def test_the_frozen_rubrics_are_clean():
    assert cm.prompt_purity_problems() == []


def test_the_purity_check_actually_fires():
    assert "gemini" in cm.prompt_purity_problems("produced by Gemini")
    assert "enriched" in cm.prompt_purity_problems("the enriched condition")
    assert "0.6364" in cm.prompt_purity_problems("benchmark is 0.6364")
    assert "u03" in cm.prompt_purity_problems("see U03 for context")
    # word-boundary matched, so an innocent substring must not fire
    assert cm.prompt_purity_problems("the modelling of themes") == []


def test_every_rendered_request_is_blind(cases):
    for group in ("calibration", "pending"):
        for c in cases[group]:
            for rep in (1, 2):
                assert cm.render_problems(c, rep) == [], (c["case_id"], rep)


def test_the_real_unit_id_never_appears_and_the_blinded_one_does(cases):
    for c in cases["pending"]:
        text = cm.render(c, 1)
        assert c["unit_id"] not in text
        assert cm.blind_unit(c["unit_id"]) in text
        assert not cm.blind_unit(c["unit_id"]).startswith("U0")


def test_blinded_labels_are_stable_and_not_reversible_by_ordering():
    labels = [cm.blind_unit(u) for u in cal.UNITS]
    assert len(set(labels)) == len(labels)
    assert labels == [cm.blind_unit(u) for u in cal.UNITS]      # stable
    assert labels != sorted(labels), "labels must not preserve unit order"


def test_the_sides_are_never_called_human_or_machine(cases):
    blob = " ".join(cm.render(c, 1) for c in cases["pending"]).lower()
    blob += " ".join([cm.SHARED_RUBRIC] + list(cm.TASK_RUBRICS.values())).lower()
    for word in ("human theme", "machine theme", "the human", "the machine"):
        assert word not in blob, word
    assert "reference theme" in blob and "candidate theme" in blob


def test_calibration_never_shows_the_human_decision(cases):
    for c in cases["calibration"]:
        assert "WITHHELD" in " ".join(c)
        text = cm.render(c, 1)
        for v in ("MATCHED", "NO_MATCH_HUMAN_ONLY", "one_to_one", "one_to_many",
                  "many_to_one"):
            assert v not in text, (c["case_id"], v)


def test_quote_counts_are_explicitly_ruled_out_as_a_signal():
    r = " ".join(cm.SHARED_RUBRIC.split())
    assert "quote counts are not comparable" in r
    assert "Do NOT judge by" in r


# ---------------------------------------------------------------------------
# Four separate tasks
# ---------------------------------------------------------------------------

def test_the_four_tasks_are_separate_with_frozen_categories():
    assert set(cm.TASKS) == {"A_PAIRWISE_CORRESPONDENCE", "B_CANDIDATE_GROUNDEDNESS",
                             "C_UNMATCHED_CANDIDATE_STATUS", "D_GRANULARITY"}
    assert "SAME_SUBSTANTIVE_THEME" in cm.TASKS["A_PAIRWISE_CORRESPONDENCE"]
    assert "FULLY_SUPPORTED" in cm.TASKS["B_CANDIDATE_GROUNDEDNESS"]
    assert "VALID_NOVEL_THEME" in cm.TASKS["C_UNMATCHED_CANDIDATE_STATUS"]
    assert "LEGITIMATE_GRANULARITY_DIFFERENCE" in cm.TASKS["D_GRANULARITY"]
    for cats in cm.TASKS.values():
        assert "UNCERTAIN" in cats
    # no holistic task
    assert not any("HOLISTIC" in t or "OVERALL" in t for t in cm.TASKS)


def test_each_task_has_its_own_prompt_and_schema():
    shas = {t: cm.prompt_sha(t) for t in cm.TASKS}
    assert len(set(shas.values())) == len(shas)
    for t in cm.TASKS:
        s = cm.task_schema(t)
        assert s["additionalProperties"] is False
        assert s["properties"]["category"]["enum"] == list(cm.TASKS[t])
        for f in ("category", "confidence", "quotations", "reasoning",
                  "information_that_would_settle_it"):
            assert f in s["required"]
        assert s["properties"]["confidence"]["enum"] == ["LOW", "MEDIUM", "HIGH"]


def test_aliases_restore_the_approved_category_names():
    for blind, approved in cm.CATEGORY_ALIASES.items():
        assert blind in sum([list(v) for v in cm.TASKS.values()], [])
        assert "HUMAN" in approved or "MACHINE" in approved


# ---------------------------------------------------------------------------
# Configuration and cache keys
# ---------------------------------------------------------------------------

def test_effective_config_records_every_transmitted_parameter():
    cfg = cm.effective_config()
    assert cfg["model"] == "claude-opus-5"
    assert cfg["execution_mode"] == "batch"
    assert cfg["temperature_transmitted"] is False
    assert cfg["top_p_transmitted"] is False
    assert cfg["top_k_transmitted"] is False
    assert cfg["output_config_format"] == "json_schema"


def test_repetitions_have_distinct_cache_keys_by_construction():
    a = cm.cache_key("A_PAIRWISE_CORRESPONDENCE", "case-1", 1, "sha")
    b = cm.cache_key("A_PAIRWISE_CORRESPONDENCE", "case-1", 2, "sha")
    assert a != b, "repetition 2 could be served from repetition 1's cache"


@pytest.mark.parametrize("mutate", [
    lambda k: k(task="B_CANDIDATE_GROUNDEDNESS"),
    lambda k: k(case_id="other"),
    lambda k: k(rendered="different"),
])
def test_cache_key_changes_with_every_input(mutate):
    def key(task="A_PAIRWISE_CORRESPONDENCE", case_id="case-1", rep=1, rendered="sha"):
        return cm.cache_key(task, case_id, rep, rendered)
    assert mutate(key) != key()


def test_all_manifest_cache_keys_are_unique(manifest):
    keys = [r["cache_key"] for r in manifest["requests"]]
    assert len(set(keys)) == len(keys) == manifest["n_requests"]


# ---------------------------------------------------------------------------
# Robustness: rotation and two repetitions
# ---------------------------------------------------------------------------

def test_every_case_runs_exactly_twice(manifest):
    from collections import Counter
    c = Counter(r["case_id"] for r in manifest["requests"])
    assert set(c.values()) == {2}
    assert manifest["repetitions_per_case"] == 2
    assert manifest["n_requests"] == 2 * manifest["n_cases"]


def test_every_case_with_something_to_rotate_is_rotated(cases):
    """
    Rotation reorders alternatives. A case with one section and one quotation has no
    ordering to vary — asserting that ALL cases rotate would be false, so the real
    property is asserted instead: rotation happens wherever it can.
    """
    for group in ("calibration", "pending"):
        for c in cases[group]:
            n_sections = sum(1 for k in ("reference", "candidate") if c.get(k))
            n_quotes = len((c.get("candidate") or {}).get("evidence") or [])
            rotatable = n_sections > 1 or n_quotes > 1 or any(
                c.get(k) for k in ("reference_group", "candidate_group",
                                   "reference_inventory", "sibling_candidates"))
            if rotatable:
                assert cm.render(c, 1) != cm.render(c, 2), c["case_id"]


def test_the_non_rotatable_cases_are_disclosed_not_hidden(manifest):
    rot = manifest["rotation"]
    assert rot["n_cases_rotated"] + rot["n_cases_with_nothing_to_rotate"] == \
        manifest["n_cases"]
    assert rot["n_cases_with_nothing_to_rotate"] == 2
    assert all(c.startswith("B::") for c in rot["cases_with_nothing_to_rotate"])
    assert "anti-anchoring control does not apply" in rot["note"]


def test_non_rotatable_repetitions_are_still_independent_calls(manifest):
    """Identical prompt, but distinct cache keys — so both genuinely run."""
    for cid in manifest["rotation"]["cases_with_nothing_to_rotate"]:
        keys = [r["cache_key"] for r in manifest["requests"] if r["case_id"] == cid]
        assert len(keys) == 2 and keys[0] != keys[1]


def test_rotation_does_not_change_the_content(cases):
    """Order differs; the set of lines must not."""
    for c in cases["pending"][:8]:
        assert sorted(cm.render(c, 1).split("\n")) == sorted(cm.render(c, 2).split("\n"))


# ---------------------------------------------------------------------------
# Corroboration
# ---------------------------------------------------------------------------

LINES = [
    "[T001] Moderator: What do you make of that?",
    "[T002] Participant 1: I would buy it more often if it were cheaper, honestly.",
    "[T003] Participant 2: Price is not what stops me at all.",
]


def _rep(cat="SAME_SUBSTANTIVE_THEME", conf="HIGH", turn="T002",
         quote="I would buy it more often if it were cheaper"):
    return {"category": cat, "confidence": conf,
            "quotations": [{"turn_id": turn, "speaker": "Participant 1",
                            "quote": quote}],
            "reasoning": "r", "information_that_would_settle_it": "nothing"}


def test_two_agreeing_evidenced_confident_readings_corroborate():
    out = cm.corroborate(_rep(), _rep(), LINES)
    assert out["status"] == cm.CORROBORATED
    assert out["category"] == "SAME_SUBSTANTIVE_THEME"
    assert out["reasons"] == []


def test_disagreement_is_unresolved_and_never_averaged():
    out = cm.corroborate(_rep(), _rep(cat="NO_CORRESPONDENCE"), LINES)
    assert out["status"] == cm.UNRESOLVED
    assert out["category"] is None
    assert any("disagree" in r for r in out["reasons"])


@pytest.mark.parametrize("c1,c2", [("LOW", "HIGH"), ("HIGH", "LOW"), ("LOW", "LOW")])
def test_low_confidence_blocks_corroboration(c1, c2):
    out = cm.corroborate(_rep(conf=c1), _rep(conf=c2), LINES)
    assert out["status"] == cm.UNRESOLVED
    assert any("LOW" in r for r in out["reasons"])


def test_an_invented_quote_blocks_corroboration():
    out = cm.corroborate(_rep(quote="a sentence that appears nowhere"), _rep(), LINES)
    assert out["status"] == cm.UNRESOLVED
    assert any("not verbatim" in r for r in out["reasons"])


def test_a_moderator_quote_blocks_corroboration():
    bad = _rep(turn="T001", quote="What do you make of that?")
    out = cm.corroborate(bad, bad, LINES)
    assert out["status"] == cm.UNRESOLVED
    assert any("moderator" in r for r in out["reasons"])


def test_an_unknown_turn_blocks_corroboration():
    out = cm.corroborate(_rep(turn="T999"), _rep(), LINES)
    assert out["status"] == cm.UNRESOLVED
    assert any("unknown turn" in r for r in out["reasons"])


def test_no_evidence_blocks_corroboration():
    empty = {**_rep(), "quotations": []}
    out = cm.corroborate(empty, empty, LINES)
    assert out["status"] == cm.UNRESOLVED
    assert any("cited no evidence" in r for r in out["reasons"])


def test_corroborated_is_still_not_validation():
    out = cm.corroborate(_rep(), _rep(), LINES)
    assert "never converts a human-anchored finding" in out["note"]


# ---------------------------------------------------------------------------
# Scope and cost
# ---------------------------------------------------------------------------

def test_the_manifest_covers_the_pending_work_and_a_calibration_set(manifest, cases):
    tasks = {c["task"] for c in cases["pending"]}
    assert tasks == set(cm.TASKS), tasks
    strata = {c["stratum"] for c in cases["calibration"]}
    assert strata == {"MATCHED_one_to_one", "NO_MATCH_HUMAN_ONLY", "one_to_many",
                      "many_to_one"}
    assert len(cases["calibration"]) >= 12


def test_the_submitted_batch_matches_the_frozen_manifest():
    """The audit has now run under explicit approval: one job, 76 requests."""
    job = json.loads((OUT / "cross_model_job_q3.json").read_text(encoding="utf-8"))
    man = json.loads((OUT / "cross_model_manifest_q3.json").read_text(encoding="utf-8"))
    assert job["n_requests"] == man["n_requests"] == 76
    assert job["model"] == "claude-opus-5"
    assert job["manifest_prompt_sha256"] == man["prompt_sha256"]
    assert job["manifest_schema_sha256"] == man["schema_sha256"]
    assert len(job["custom_id_map"]) == 76


def test_results_are_keyed_by_custom_id_never_by_position():
    res = json.loads((OUT / "cross_model_results_q3.json").read_text(encoding="utf-8"))
    job = json.loads((OUT / "cross_model_job_q3.json").read_text(encoding="utf-8"))
    assert res["n_results"] == 76
    ids = [r["custom_id"] for r in res["results"]]
    assert len(set(ids)) == 76
    assert set(ids) == set(job["custom_id_map"])
    for r in res["results"]:
        assert r["custom_request_key"] == job["custom_id_map"][r["custom_id"]]["custom_request_key"]


def test_repetitions_were_never_mixed():
    res = json.loads((OUT / "cross_model_results_q3.json").read_text(encoding="utf-8"))
    from collections import Counter
    per_case = Counter((r["case_id"], r["repetition_index"]) for r in res["results"])
    assert set(per_case.values()) == {1}, "a case/repetition appeared twice"
    assert Counter(r["repetition_index"] for r in res["results"]) == {1: 38, 2: 38}


def test_scope_is_only_q3_units(cases):
    for group in ("calibration", "pending"):
        for c in cases[group]:
            assert c["unit_id"] in cal.UNITS
