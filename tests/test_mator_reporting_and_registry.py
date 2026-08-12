"""
Tests for the parts of the Mator layer the first test module did not reach:
section-label misalignment handling, the completeness token cross-check, the
length control, the baseline table, the registry append's effect on the parity
consumer, and the comparison table's rendering.

No model load, no API, no writes to the repository.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import mator_bertscore_metrics as mb  # noqa: E402


def _mod(content="Question text here"):
    return {"speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": content}


def _hmod(content="Question 1. Something?"):
    return {"speaker_id": "MODERATOR", "speaker_name": "Moderator",
            "speaker_role": "moderator", "content": content}


def _p(speaker, words=60, content=None):
    return {"speaker_id": speaker, "speaker_name": speaker,
            "content": content if content is not None else " ".join([speaker] * words)}


def _unit(entries, section_of, side="synthetic", questions=None):
    return mb.Unit("u1", side, "fg1", "enriched", entries, section_of,
                   questions or {}, [])


# ---------------------------------------------------------------------------
# Section-label misalignment (2 of the 30 runs; see load_units)
# ---------------------------------------------------------------------------

def test_misaligned_run_is_excluded_from_the_section_indexed_metric_with_a_reason():
    """When guide question 1 was asked inside section 0, the labels no longer name
    their guide question, so 'the same section' cannot certify 'the same question'."""
    entries = [_mod(), _p("A", words=80), _p("B", words=80), _p("C", words=80)]
    unit = _unit(entries, {0: 1, 1: 1, 2: 1, 3: 1})
    unit.section_labels_misaligned = True

    pairs, used, skipped = mb.between_participant_pairs(unit)
    assert pairs == []
    assert used == []
    assert len(skipped) == 1
    assert "whole run excluded" in skipped[0]["reason"]


def test_aligned_run_with_identical_content_is_not_excluded():
    """Guard against the exclusion firing on everything."""
    entries = [_mod(), _p("A", words=80), _p("B", words=80), _p("C", words=80)]
    pairs, used, _ = mb.between_participant_pairs(_unit(entries, {0: 1, 1: 1, 2: 1, 3: 1}))
    assert used == [1]
    assert len(pairs) == 3


def test_relevance_keeps_misaligned_runs():
    """The turn-indexed metric never consults a section label, so excluding it
    there would discard sound data for no reason."""
    entries = [_mod("Q"), _p("A"), _p("B")]
    unit = _unit(entries, {0: 0, 1: 0, 2: 0})
    unit.section_labels_misaligned = True
    assert len(mb.relevance_pairs(unit)) == 2


# ---------------------------------------------------------------------------
# Completeness (scripts/mator_completeness.py)
# ---------------------------------------------------------------------------

def test_completeness_counts_only_sections_carrying_participant_turns():
    import mator_completeness as mc
    entries = [_mod(), _p("A"), _mod(), _p("B"), _mod()]
    # section 3 is opened by a moderator turn but nobody answers
    out = mc.completeness(_unit(entries, {0: 1, 1: 1, 2: 2, 3: 2, 4: 3}))
    assert out["sections_covered"] == [1, 2]
    assert out["sections_missing"] == [3, 4, 5]
    assert out["value"] == 0.4


def test_completeness_is_one_when_all_five_substantive_sections_are_answered():
    import mator_completeness as mc
    entries, section_of = [], {}
    for k in mb.SUBSTANTIVE_SECTIONS:
        section_of[len(entries)] = k
        entries.append(_mod())
        section_of[len(entries)] = k
        entries.append(_p("A"))
    out = mc.completeness(_unit(entries, section_of))
    assert out["value"] == 1.0
    assert out["sections_missing"] == []


def test_completeness_ignores_the_introduction_and_closing_sections():
    import mator_completeness as mc
    entries = [_mod(), _p("A"), _mod(), _p("B")]
    out = mc.completeness(_unit(entries, {0: 0, 1: 0, 2: 6, 3: 6}))
    assert out["value"] == 0.0


def test_openers_row_per_section_pairs_the_label_with_what_was_actually_asked():
    """The eye-checkable artefact that replaced the removed token cross-check:
    a displaced label shows up as a question that does not match its index."""
    import mator_completeness as mc
    entries = [_mod("Okay, welcome. What is your favourite pub?"),
               _p("A"),
               _mod("Now, how do you decide what to eat?"),
               _p("B")]
    unit = _unit(entries, {0: 0, 1: 0, 2: 1, 3: 1},
                 questions={0: "Hi everyone, thanks for joining.",
                            1: "What is your favourite place in your city?"})
    rows = mc.openers(unit)
    assert [r["section_label_index"] for r in rows] == [0, 1]
    assert "favourite pub" in rows[0]["moderator_actually_asked"]
    assert "thanks for joining" in rows[0]["guide_question_for_this_label"]
    assert "decide what to eat" in rows[1]["moderator_actually_asked"]


def test_openers_only_reports_moderator_turns():
    import mator_completeness as mc
    unit = _unit([_p("A"), _mod("Q1"), _p("B")], {0: 1, 1: 1, 2: 1})
    rows = mc.openers(unit)
    assert len(rows) == 1
    assert rows[0]["moderator_actually_asked"] == "Q1"


# ---------------------------------------------------------------------------
# Length control
# ---------------------------------------------------------------------------

def test_truncate_words_matches_the_r3_rule():
    assert mb.truncate_words("a b c d e", 3) == "a b c"
    assert mb.truncate_words("a b", 5) == "a b"
    assert mb.truncate_words("", 5) == ""


def test_length_match_w_comes_from_the_human_side_only():
    human = mb.Unit("fg1", "human", "fg1", "human",
                    [_hmod(), _p("A", words=10), _p("B", words=20), _p("C", words=30)],
                    {}, {}, [])
    synth = mb.Unit("run", "synthetic", "fg1", "enriched",
                    [_mod(), _p("A", words=500)], {}, {}, [])
    assert mb.length_match_widths([human, synth]) == {"fg1": 20}


# ---------------------------------------------------------------------------
# Baseline table
# ---------------------------------------------------------------------------

def test_baseline_f1_reads_the_packages_own_table():
    pytest.importorskip("bert_score")
    assert mb.baseline_f1("roberta-large", 17) == pytest.approx(0.83122575, abs=1e-9)


def test_rescale_maps_the_baseline_to_zero_and_can_go_negative_below_it():
    base = 0.83122575
    assert mb.rescale(base, base) == pytest.approx(0.0, abs=1e-12)
    assert mb.rescale(1.0, base) == pytest.approx(1.0, abs=1e-12)
    assert mb.rescale(0.82, base) < 0


def test_baseline_spread_shows_the_expectation_is_model_dependent():
    """The load-bearing Mator inference hangs on this: the unrelated-pair
    expectation is not a universal constant, so the comparison must be stated
    conditionally."""
    pytest.importorskip("bert_score")
    spread = mb.baseline_spread()
    assert len(spread) >= 3
    assert max(spread.values()) - min(spread.values()) > 0.3


# ---------------------------------------------------------------------------
# Registry append must not break the parity consumer
# ---------------------------------------------------------------------------

def test_appending_the_mator_rows_keeps_registry_parity_green():
    """The append is only safe if the consumer stays consistent. Simulated
    against the live consumer, not against a copy of its rules."""
    import mator_registry_rows as mrr
    problems = mrr.parity_after_append({r["metric_id"] for r in mrr.NEW_ROWS})
    assert problems == [], problems


def test_every_mator_row_is_declared_in_produced_elsewhere():
    import aggregate_production_results as agg
    import mator_registry_rows as mrr
    declared = set(agg.PRODUCED_ELSEWHERE)
    for r in mrr.NEW_ROWS:
        assert r["metric_id"] in declared, (
            f"{r['metric_id']} would enter the AUTOMATIC parity set undeclared")


def test_mator_rows_use_the_instructed_evidence_class_and_namespace():
    import mator_registry_rows as mrr
    for r in mrr.NEW_ROWS:
        assert r["evidence_class"] == "AUTOMATIC_PROXY_EXPLORATORY"
        assert r["namespace"] == "_comparable_window"
        assert "Mator et al. (2025)" in r["notes_and_caveats"]


def test_mator_rows_quote_the_published_figures():
    """Section 3 requires the published AI/Human values to be readable from the
    registry without re-deriving them."""
    import mator_registry_rows as mrr
    notes = {r["metric_id"]: r["notes_and_caveats"] for r in mrr.NEW_ROWS}
    assert "100%" in notes["mator_conversational_completeness"]
    assert "83%" in notes["mator_relevance_of_response_bertscore_f1"]
    assert "91%" in notes["mator_between_participant_similarity_bertscore_f1"]
    assert "92%" in notes["mator_agreement_consecutive_turn_similarity"]
    assert "18%" in notes["mator_conversational_distribution"]


def test_the_bertscore_rows_carry_the_length_caveat():
    """This project already showed length drives most of the analogous published
    gap; a BERTScore row without that caveat invites the wrong reading."""
    import mator_registry_rows as mrr
    notes = {r["metric_id"]: r["notes_and_caveats"] for r in mrr.NEW_ROWS}
    for mid in ("mator_relevance_of_response_bertscore_f1",
                "mator_between_participant_similarity_bertscore_f1"):
        assert "LENGTH" in notes[mid] or "length-matched" in notes[mid]


def test_the_mator_baseline_claim_is_stated_conditionally():
    """'Their 83% sits at the floor' is only true if they used this backbone, and
    their paper does not say. The registry must not assert it flatly."""
    import mator_registry_rows as mrr
    note = {r["metric_id"]: r["notes_and_caveats"] for r in mrr.NEW_ROWS}[
        "mator_relevance_of_response_bertscore_f1"]
    assert "CONDITIONAL" in note.upper()
    assert "not report" in note


# ---------------------------------------------------------------------------
# Comparison table rendering
# ---------------------------------------------------------------------------

def _syn(fg, cond, **kw):
    return {"unit": f"{fg}_{cond}", "side": "synthetic", "fg": fg, "condition": cond, **kw}


def _paired_fixture():
    return [{"unit": "fg1", "side": "human", "fg": "fg1", "condition": "human",
             "agreement_strict_R2": "0.50"},
            _syn("fg1", "enriched", agreement_strict_R2="0.60"),
            _syn("fg1", "demographics-only", agreement_strict_R2="0.40")]


def test_paired_table_emits_exactly_as_many_cells_as_its_header():
    """One cell too many silently shifts every delta a column to the left."""
    import mator_comparison_table as mct
    out = mct.paired_table(_paired_fixture(), "agreement_strict_R2")
    header = next(l for l in out if l.startswith("| FG |"))
    n_cols = header.count("|") - 1
    body = [l for l in out if l.startswith("| fg1 ") or l.startswith("| **direction**")]
    assert body, "no data rows rendered"
    for line in body:
        assert line.count("|") - 1 == n_cols, f"{line!r} has the wrong cell count"


def test_paired_table_reports_both_deltas_with_the_right_sign():
    import mator_comparison_table as mct
    line = next(l for l in mct.paired_table(_paired_fixture(), "agreement_strict_R2")
                if l.startswith("| fg1 "))
    cells = [c.strip() for c in line.strip("|").split("|")]
    assert cells[-2] == "+10.0 pp"
    assert cells[-1] == "-10.0 pp"


def test_paired_table_direction_row_distinguishes_higher_from_lower():
    import mator_comparison_table as mct
    line = next(l for l in mct.paired_table(_paired_fixture(), "agreement_strict_R2")
                if l.startswith("| **direction**"))
    assert "higher" in line and "lower" in line


def test_completeness_block_reports_zero_not_one_when_nothing_was_covered():
    import mator_comparison_table as mct
    rows = [{"unit": "x", "side": "human", "fg": "fg1", "condition": "human",
             "completeness_sections_covered": "",
             "completeness_sections_missing": "1|2|3|4|5",
             "completeness_token_check": "0.0",
             "completeness_readings_agree": "True"}]
    line = next(l for l in mct.completeness_block(rows) if l.startswith("| x "))
    assert "| 0/5 |" in line


def test_distribution_block_survives_a_unit_with_no_participant_vector():
    import mator_comparison_table as mct
    rows = [{"unit": "x", "side": "human", "fg": "fg1", "condition": "human",
             "moderator_word_share": "0.3", "participant_word_shares": ""}]
    out = mct.distribution_block(rows)   # must not raise
    assert any("Human (5 FG)" in l for l in out)


# ---------------------------------------------------------------------------
# Batched scoring: one encode pass per unit, split back apart correctly
# ---------------------------------------------------------------------------

class _FakeScorer:
    """Returns the index of each pair, so a mis-split is visible immediately."""

    def __init__(self):
        self.calls = 0

    def score(self, cands, refs, verbose=False):
        assert len(cands) == len(refs)
        self.calls += 1
        return None, None, [float(i) for i in range(len(cands))]


def test_score_batches_splits_results_back_onto_their_input_lists():
    sc = _FakeScorer()
    out = mb.score_batches(sc, [(["a", "b"], ["r", "r"]),
                                ([], []),
                                (["c"], ["r"])])
    assert out == [[0.0, 1.0], [], [2.0]]
    assert sc.calls == 1, "the whole point is a single encode pass per unit"


def test_score_batches_handles_an_entirely_empty_unit():
    sc = _FakeScorer()
    assert mb.score_batches(sc, [([], []), ([], [])]) == [[], []]
    assert sc.calls == 0


def test_pair_texts_applies_the_length_control_to_both_sides():
    pairs = [{"cand": "a b c d e", "ref": "z y x w v"}]
    c, r = mb.pair_texts(pairs, width=2)
    assert c == ["a b"] and r == ["z y"]
    c, r = mb.pair_texts(pairs)
    assert c == ["a b c d e"] and r == ["z y x w v"]


def test_pair_texts_can_target_the_section_opener_reference():
    pairs = [{"cand": "x", "ref": "probe", "ref_opener": "opening question"}]
    c, r = mb.pair_texts(pairs, key_ref="ref_opener")
    assert r == ["opening question"]
