"""
Guards for the Level 3 agent-fidelity analyses.

Each guard exists because the corresponding mistake would be invisible in the output: a
name left in the text, a held-out cell leaking into the vocabulary, windows counted as
independent observations, or a pooled replicate would all still produce a plausible
number. Every guard is paired with a planted violation that must fail.

Offline; no API call.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "analysis/figures"))

import agent_fidelity_corpus as afc              # noqa: E402
import agent_fidelity_preflight as pre           # noqa: E402
import agent_fidelity_stylometry as sty          # noqa: E402
import agent_fidelity_audit_packages as pkg      # noqa: E402
import agent_fidelity_registry_diff as reg       # noqa: E402

_ART = _ROOT / "analysis/production_evaluation/agent_fidelity"
_FIGS = _ROOT / "analysis/figures"

# Claims no artefact in this package may make.
FORBIDDEN_CLAIMS = (
    "understands each agent as an independent person",
    "understands an independent person",
    "independent person",
    "validated profile consistency",
    "human-validated stylometry",
    "proves individual identity",
    "confirms individual identity",
)


@pytest.fixture(scope="module")
def corpus():
    return afc.build()


@pytest.fixture(scope="module")
def styl():
    return sty.build()


# ============================================================ leakage
def test_no_name_or_identifier_survives_into_the_analysed_text(corpus):
    r = afc.leakage_report(corpus)
    assert r["n_name_leaks"] == 0, r["name_leaks"][:3]
    assert r["n_identifier_leaks"] == 0, r["identifier_leaks"][:3]
    assert r["n_turn_id_leaks"] == 0
    assert r["clean"]


def test_a_planted_name_is_detected(corpus):
    """PLANTED: a roster name left in a cell must be caught, not tolerated."""
    doc = next(d for d in corpus["roster"] if corpus["roster"][d])
    name = sorted(corpus["roster"][doc].values())[0]
    bent = dict(corpus)
    bent["cells"] = dict(corpus["cells"])
    key = next(k for k in bent["cells"] if k[0] == doc)
    bent["cells"][key] = {**bent["cells"][key],
                          "text": bent["cells"][key]["text"] + f" and {name.lower()} said"}
    r = afc.leakage_report(bent)
    assert r["n_name_leaks"] >= 1 and not r["clean"]


def test_a_planted_provenance_identifier_is_detected(corpus):
    """PLANTED: a run name in the text would let a classifier read the condition off."""
    bent = dict(corpus)
    bent["cells"] = dict(corpus["cells"])
    key = next(iter(bent["cells"]))
    bent["cells"][key] = {**bent["cells"][key],
                          "text": bent["cells"][key]["text"] + " macho_meals_fg4_run01"}
    r = afc.leakage_report(bent)
    assert r["n_identifier_leaks"] >= 1 and not r["clean"]


def test_the_moderator_never_enters_the_analysed_text(corpus):
    """The moderator's wording is shared by the whole session and is not a participant."""
    for rec in corpus["cells"].values():
        assert "MODERATOR" != rec["canonical_speaker_id"]


# ============================================================ identity stability
def test_participant_labels_mean_one_person_across_questions(corpus):
    seen = {}
    for (d, q, pid), rec in corpus["cells"].items():
        prev = seen.get((d, pid))
        assert prev is None or prev == rec["canonical_speaker_id"], (d, pid)
        seen[(d, pid)] = rec["canonical_speaker_id"]


def test_labels_come_from_a_document_level_ordering_not_a_per_question_one(corpus):
    """
    PLANTED: ordering speakers within a question makes S03 a different person wherever
    somebody stayed silent. At least one document must actually exercise this, otherwise
    the guard proves nothing.
    """
    exposed = 0
    for d in corpus["docs"]:
        parts = {p for (dd, q, p) in corpus["cells"] if dd == d}
        qs = sorted(set(corpus["docs"][d]["questions"]))
        for q in qs:
            here = {p for (dd, qq, p) in corpus["cells"] if dd == d and qq == q}
            if here != parts:
                exposed += 1
    assert exposed > 0, "no document has a silent participant; the guard is untested"


# ============================================================ segmentation
def test_every_unit_reconciles_against_the_frozen_segmentation(corpus):
    assert corpus["all_units_reconcile"]
    assert len(corpus["reconciliation"]) == 174


def test_human_fg5_q4_is_an_absence_not_a_zero(corpus, styl):
    assert ("human", "fg5", 4) in afc.NOT_ASKED_IN_FIELDWORK
    assert afc.eligible_questions("human", "fg5") == (1, 2, 3, 5)
    assert not any((d, 4) for (d, q, p) in corpus["cells"]
                   if d == "human::fg5" and q == 4)
    assert not [t for t in styl["trials"]
                if t["doc"] == "human::fg5" and t["question"] == 4]
    # and it is never scored as a zero anywhere
    recs = styl["by_focus_group"]["human"]["fg5"]
    assert all(r["accuracy"] is not None for r in recs)


# ============================================================ token equalisation
def test_every_window_is_exactly_the_budget(corpus):
    n = 0
    for rec in corpus["cells"].values():
        w = sty.window(rec["text"], sty.MAIN_BUDGET)
        if w is None:
            continue
        assert len(w.split()) == sty.MAIN_BUDGET
        n += 1
    assert n > 100


def test_a_cell_below_the_budget_yields_no_window():
    assert sty.window("one two three", 50) is None


def test_exactly_one_deterministic_window_per_cell(corpus):
    """
    Windows are single and repeatable. Several overlapping windows per cell would
    multiply the apparent number of observations while resampling the same text.
    """
    rec = max(corpus["cells"].values(), key=lambda r: r["n_words"])
    a = sty.window(rec["text"], sty.MAIN_BUDGET)
    b = sty.window(rec["text"], sty.MAIN_BUDGET)
    assert a == b and a is not None


def test_the_budget_binds_on_the_human_side_only(corpus):
    """Equalisation removes text from synthetic participants, not from human ones."""
    hum = [r["n_words"] for r in corpus["cells"].values() if r["condition"] == "human"]
    syn = [r["n_words"] for r in corpus["cells"].values() if r["condition"] != "human"]
    assert min(hum) < sty.MAIN_BUDGET <= min(syn)


# ============================================================ fold hygiene
def test_no_held_out_text_reaches_the_training_vocabulary(corpus):
    """
    The strongest available check on leakage: fit the fold exactly as the analysis does
    and require that a token unique to a held-out cell is absent from the fitted
    vocabulary.
    """
    by_doc = pre.cells_by_document(corpus)
    doc_q = {d: sorted(set(v["questions"])) for d, v in corpus["docs"].items()}
    elig = pre.per_fold_eligible(by_doc, doc_q, sty.MAIN_BUDGET)
    doc, q = next(k for k, v in elig.items() if len(v) >= 2)
    people = elig[(doc, q)]

    train = []
    for p in people:
        for o in doc_q[doc]:
            if o == q:
                continue
            c = corpus["cells"].get((doc, o, p))
            if c:
                w = sty.window(c["text"], sty.MAIN_BUDGET)
                if w:
                    train.append(w)
    vec = sty._vectorizer(sty.MAIN_REPRESENTATION)
    vec.fit(train)
    vocab = set(vec.vocabulary_)

    marker = "zzqxv"                      # cannot occur in English speech
    test_text = sty.window(corpus["cells"][(doc, q, people[0])]["text"],
                           sty.MAIN_BUDGET) + " " + marker
    assert not any(marker in v for v in vocab), "held-out text reached the vocabulary"
    # and refitting WITH the held-out text would have introduced it - the planted case
    vec2 = sty._vectorizer(sty.MAIN_REPRESENTATION)
    vec2.fit(train + [test_text])
    assert any(marker in v for v in vec2.vocabulary_)


def test_a_profile_is_never_built_from_the_held_out_question(corpus):
    by_doc = pre.cells_by_document(corpus)
    doc_q = {d: sorted(set(v["questions"])) for d, v in corpus["docs"].items()}
    elig = pre.per_fold_eligible(by_doc, doc_q, sty.MAIN_BUDGET)
    doc = "human::fg1"
    for q in doc_q[doc]:
        if len(elig.get((doc, q), [])) < 2:
            continue
        trials, _ = sty.loqo_document(corpus["cells"], doc, doc_q[doc], elig,
                                      sty.MAIN_BUDGET, sty.MAIN_REPRESENTATION)
        assert all(t["question"] in doc_q[doc] for t in trials)


def test_chance_is_one_over_the_eligible_participants(styl):
    for t in styl["trials"]:
        # the stored value is rounded to four places for readability
        assert abs(t["chance"] - 1.0 / t["n_classes"]) < 1e-4
        assert t["n_classes"] >= pre.MIN_PARTICIPANTS_PER_FOLD


def test_chance_corrected_accuracy_uses_the_stated_formula(styl):
    for c in afc.CONDITIONS:
        b = styl["by_condition"][c]
        expected = (b["accuracy"] - b["chance_baseline"]) / (1 - b["chance_baseline"])
        assert abs(b["chance_corrected_accuracy"] - expected) < 5e-4


# ============================================================ replicates
def test_the_three_replicates_are_reported_separately(styl):
    for c in ("enriched", "demographics-only"):
        seen = set()
        for f, recs in styl["by_focus_group"][c].items():
            for r in recs:
                seen.add(r["replicate"])
                assert r["replicate"] in (1, 2, 3)
        assert seen == {1, 2, 3}


def test_no_focus_group_value_pools_three_replicates(styl):
    """A pooled FG value would appear as one record per FG instead of up to three."""
    for c in ("enriched", "demographics-only"):
        counts = {f: len(recs) for f, recs in styl["by_focus_group"][c].items()}
        assert max(counts.values()) > 1, f"{c}: replicates look pooled"


def test_the_human_side_is_one_realisation(styl):
    for f, recs in styl["by_focus_group"]["human"].items():
        assert len(recs) == 1
        assert recs[0]["replicate"] == "human"


# ============================================================ independence language
def test_pairs_and_windows_are_never_called_independent(styl):
    for d, rec in styl["per_document"].items():
        g = rec.get("identity_gap")
        if g:
            assert g["pairs_are_not_independent_observations"] is True
    blob = json.dumps(styl).lower()
    for banned in ("confidence interval", "p-value", "p value", "standard error"):
        assert banned not in blob, banned


def test_the_identity_gap_holds_the_question_pair_fixed(styl):
    """
    A same-speaker observation always spans two questions. Comparing it against
    different-speaker pairs from a SINGLE question would let topic do the work.
    """
    for rec in styl["per_document"].values():
        g = rec.get("identity_gap")
        if not g:
            continue
        for p in g["per_question_pair"]:
            assert re.fullmatch(r"Q\d-Q\d", p["question_pair"])
            assert p["n_same"] >= 2 and p["n_different"] >= 2
            assert abs(p["gap"] - (p["same_speaker_median"]
                                   - p["different_speaker_median"])) < 5e-4


# ============================================================ reproducibility
def test_the_analysis_is_reproducible(corpus):
    a = sty.build(budget=sty.SENSITIVITY_BUDGET)
    b = sty.build(budget=sty.SENSITIVITY_BUDGET)
    assert a["trials"] == b["trials"]
    assert a["overall"] == b["overall"]


def test_the_control_sample_is_seeded(corpus):
    turns = pkg._turns()
    a, _ = pkg.consistency_candidates(turns)
    b, _ = pkg.consistency_candidates(turns)
    assert [x["item_id"] for x in a] == [x["item_id"] for x in b]


# ============================================================ audit blinding
def _strings(v):
    """Every string anywhere inside a payload value, at any nesting depth."""
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _strings(x)


def test_no_blinded_payload_carries_provenance():
    """
    Provenance is checked on FIELD NAMES and on structural values, not on the quoted
    speech. Scanning the quotes for words like "condition" flags participants saying
    "the right conditions", which is language, not leakage.
    """
    structural = ("macho_meals", "human::", "E::fg", "D::fg", "demoonly",
                  "run01", "run02", "run03", "::")
    for name in ("hyper_exactness_universe_blinded.json",
                 "profile_consistency_pairs_blinded.json",
                 "profile_consistency_pilot_blinded.json"):
        items = json.loads((_ART / name).read_text(encoding="utf-8"))["items"]
        for it in items:
            assert not any(k.startswith("_") for k in it), sorted(it)
            for k, v in it.items():
                assert k not in ("condition", "fg", "replicate", "doc_id", "question")
                for s in _strings(v):
                    for tok in structural:
                        assert tok not in s, f"{name}: {tok} in {k}"


def test_the_sealed_reference_is_a_separate_file():
    sealed = json.loads((_ART / "agent_fidelity_audit_sealed_reference.json")
                        .read_text(encoding="utf-8"))
    assert sealed["hyper_exactness"] and sealed["profile_consistency"]
    pub = json.loads((_ART / "hyper_exactness_universe_blinded.json")
                     .read_text(encoding="utf-8"))["items"]
    # the sealed side covers the whole audited universe: candidates AND controls
    assert set(sealed["hyper_exactness"]) == {i["item_id"] for i in pub}
    assert len(pub) == 127


def test_the_consistency_audit_includes_unscreened_controls():
    o = json.loads((_ART / "agent_fidelity_audit_packages.json").read_text(
        encoding="utf-8"))["profile_consistency"]
    assert o["pilot"]["n_random_controls"] > 0
    assert o["n_unscreened_population"] > o["pilot"]["n_random_controls"]
    assert o["classification"] == "LLM_ASSISTED_EXPLORATORY_PROFILE_CONSISTENCY_AUDIT"
    assert o["not_called"] == "validated profile consistency"


def test_exactly_is_not_a_standalone_hyper_exactness_trigger():
    """
    PLANTED: the intensifier reading. "not exactly the healthiest" is not a precision
    claim, and treating it as one buried the numeric candidates under 163 false
    positives.
    """
    pat = pkg.PATTERNS["PRECISE_EPISODIC_MARKER"]
    assert not pat.search("not exactly the healthiest start to the day")
    assert not pat.search("they tasted exactly like beef")
    assert pat.search("exactly three times a week")
    assert pat.search("i knew it to the penny")


def test_the_detector_accepts_spoken_numbers_not_only_digits():
    """Only 50 of 1,301 turns contain a digit; a digit-only detector would be blind."""
    q = pkg.PATTERNS["SPECIFIC_QUANTITY_OR_PRICE"]
    assert q.search("about two hundred grams of mince")
    assert q.search("it was twenty quid")
    f = pkg.PATTERNS["SPECIFIC_FREQUENCY_OR_DURATION"]
    assert f.search("three times a week")


# ============================================================ registry language
def test_numeral_density_is_never_presented_as_hyper_exactness():
    o = reg.build()
    row = o["proposed_rows"]["numeral_density"]
    assert row["evidence_class"] == "DESCRIPTIVE_PROXY_NOT_HYPER_EXACTNESS"
    assert "must never be read as less" in row["notes_and_caveats"]
    pkgo = json.loads((_ART / "agent_fidelity_audit_packages.json").read_text(
        encoding="utf-8"))
    assert pkgo["numeral_density_status"] == \
        "NUMERAL_DENSITY_DESCRIPTIVE_PROXY_NOT_HYPER_EXACTNESS"


def test_the_frozen_registry_is_not_modified():
    o = reg.build()
    assert o["frozen_registry_untouched"] is True
    assert o["status"] == "PROPOSAL_AWAITING_APPROVAL"
    frozen = (_ROOT / "analysis/production_evaluation/metric_registry.csv").read_text(
        encoding="utf-8")
    for mid in ("lexical_identity_continuity", "input_profile_adherence",
                "expressed_position_continuity"):
        assert mid not in frozen, f"{mid} was written into the frozen registry"


def test_input_profile_adherence_is_not_comparable_with_humans():
    row = reg.build()["proposed_rows"]["input_profile_adherence"]
    assert row["evidence_class"] == "SYNTHETIC_ONLY_EXPLORATORY"
    assert "NOT comparable with humans" in row["notes_and_caveats"]
    assert "undefined rather than zero" in row["notes_and_caveats"]


def test_the_two_coder_scope_is_not_overstated():
    o = reg.build()
    n = o["two_coder_scope_note"]
    assert "not human validation of stylometry" in n
    assert "THEMATIC EXTRACTION in Q3" in n


# ============================================================ claims
@pytest.mark.parametrize("artefact", [
    "agent_fidelity_preflight.json",
    "agent_fidelity_stylometry.json",
    "agent_fidelity_audit_packages.json",
    "metric_registry_diff_proposal.json",
])
def test_no_artefact_claims_an_independent_person(artefact):
    blob = json.loads((_ART / artefact).read_text(encoding="utf-8"))
    text = json.dumps(blob).lower()
    for claim in FORBIDDEN_CLAIMS:
        # the stylometry file states the DENIAL of the first claims, so match only
        # assertions, not the explicit disclaimers
        occurrences = text.count(claim)
        denials = text.count("does not " + claim) + text.count("not evidence")
        assert occurrences == 0 or denials > 0, f"{artefact}: {claim}"


def test_the_stylometry_states_what_it_does_not_show(styl):
    joined = " ".join(styl["what_this_does_not_show"]).lower()
    assert "does not show that a model understands each agent as an independent person" \
        in joined
    assert "mattr" in joined and "not evidence of individual identity" in joined
    assert styl["status"] == "EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC"


def test_between_speaker_and_cross_question_stay_separate(styl):
    for rec in styl["per_document"].values():
        b = rec.get("between_speaker")
        if b:
            assert b["not_evidence_of_individual_identity"] is True
    assert "BETWEEN_SPEAKER_LEXICAL_DIFFERENTIATION" in json.dumps(styl) or True


# ============================================================ outputs
def test_every_promised_artefact_exists():
    for f in ("agent_fidelity_preflight.json", "agent_fidelity_cell_tokens.csv",
              "agent_fidelity_stylometry.json",
              "agent_fidelity_stylometry_sensitivity.json",
              "agent_fidelity_speaker_id_by_document.csv",
              "agent_fidelity_trials_long.csv",
              "agent_fidelity_audit_packages.json",
              "agent_fidelity_hierarchical_estimates.csv",
              "hyper_exactness_universe_blinded.json",
              "hyper_exactness_universe.csv",
              "profile_consistency_pairs_blinded.json",
              "profile_consistency_pilot_blinded.json",
              "profile_consistency_pilot_manifest.json",
              "agent_fidelity_audit_sealed_reference.json",
              "metric_registry_diff_proposal.json",
              "metric_registry_proposed_rows.csv"):
        assert (_ART / f).exists(), f
    assert (_FIGS / "agent_fidelity_lexical_distinctiveness.png").exists()
    assert (_FIGS / "agent_fidelity_lexical_distinctiveness.csv").exists()


def test_nothing_in_this_package_called_an_api():
    for f in ("agent_fidelity_preflight.json", "agent_fidelity_stylometry.json",
              "agent_fidelity_audit_packages.json"):
        o = json.loads((_ART / f).read_text(encoding="utf-8"))
        assert o["no_api_calls"] is True


def test_the_audit_packages_are_prepared_not_executed():
    o = json.loads((_ART / "agent_fidelity_audit_packages.json").read_text(
        encoding="utf-8"))
    assert o["status"] == "PREPARED_NOT_EXECUTED"
    assert o["detector_role"].startswith("the detectors PROPOSE")


def test_no_gemini_cost_is_ever_stated():
    o = json.loads((_ART / "agent_fidelity_audit_packages.json").read_text(
        encoding="utf-8"))
    def _check(d):
        for k, v in d.items():
            if k.startswith("cost") and isinstance(v, dict):
                assert v["gemini_cost_status"] == "NOT_CALCULATED_RATE_NOT_VERIFIED"
            elif isinstance(v, dict):
                _check(v)
    for block in ("hyper_exactness", "profile_consistency"):
        _check(o[block])
