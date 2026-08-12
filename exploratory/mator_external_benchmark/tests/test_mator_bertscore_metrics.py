"""
Tests for the Mator-comparable metric layer.

Everything here runs without loading roberta-large: the pair-construction,
completeness and rescaling logic is pure and is checked against fabricated
transcripts with KNOWN answers. The two tests that touch the real repository
read only the frozen manifest and assert corpus-boundary properties (no model,
no API, no writes).
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import mator_bertscore_metrics as mb  # noqa: E402


# ---------------------------------------------------------------------------
# Fabricated transcripts
# ---------------------------------------------------------------------------

def _mod(content="Question text here"):
    """Synthetic-side moderator entry: no speaker_role, MODERATOR speaker_id."""
    return {"speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": content}


def _hmod(content="Question 1. Something?"):
    """Human-side moderator entry: carries speaker_role."""
    return {"speaker_id": "MODERATOR", "speaker_name": "Moderator",
            "speaker_role": "moderator", "content": content}


def _p(speaker, words=60, content=None):
    return {"speaker_id": speaker, "speaker_name": speaker,
            "content": content if content is not None else " ".join([speaker] * words)}


def _unit(entries, section_of, side="synthetic", notes=None):
    return mb.Unit("u1", side, "fg1", "enriched", entries, section_of, {}, notes or [])


# ---------------------------------------------------------------------------
# Moderator detection — the two transcript conventions must both work
# ---------------------------------------------------------------------------

def test_moderator_detected_on_both_transcript_conventions():
    assert mb._is_moderator(_mod())
    assert mb._is_moderator(_hmod())
    assert not mb._is_moderator(_p("Amir"))


def test_participant_named_moderator_is_not_treated_as_moderator_on_human_side():
    """`speaker_role` is authoritative when present; a display name must not
    override it."""
    entry = {"speaker_id": "mm_fg1_x", "speaker_name": "Moderator",
             "speaker_role": "participant", "content": "hello"}
    assert not mb._is_moderator(entry)


# ---------------------------------------------------------------------------
# Relevance pairs
# ---------------------------------------------------------------------------

def test_relevance_pairs_use_the_most_recent_preceding_moderator_turn():
    entries = [_mod("Q1"), _p("A"), _p("B"), _mod("probe"), _p("A")]
    section_of = {0: 1, 1: 1, 2: 1, 3: 1, 4: 1}
    pairs = mb.relevance_pairs(_unit(entries, section_of))

    assert len(pairs) == 3
    assert [p["ref"] for p in pairs] == ["Q1", "Q1", "probe"]
    assert [p["cand"] for p in pairs] == [entries[1]["content"], entries[2]["content"],
                                          entries[4]["content"]]


def test_relevance_opener_variant_ignores_mid_section_probes():
    """The sensitivity variant must anchor on the turn that OPENED the section,
    not on a later probe inside it."""
    entries = [_mod("Q1"), _p("A"), _mod("probe"), _p("B")]
    section_of = {0: 1, 1: 1, 2: 1, 3: 1}
    pairs = mb.relevance_pairs(_unit(entries, section_of))

    assert [p["ref"] for p in pairs] == ["Q1", "probe"]
    assert [p["ref_opener"] for p in pairs] == ["Q1", "Q1"]


def test_relevance_opener_advances_at_a_real_section_boundary():
    entries = [_mod("Q1"), _p("A"), _mod("Q2"), _p("B")]
    section_of = {0: 1, 1: 1, 2: 2, 3: 2}
    pairs = mb.relevance_pairs(_unit(entries, section_of))
    assert [p["ref_opener"] for p in pairs] == ["Q1", "Q2"]


def test_relevance_skips_participant_turns_with_no_preceding_moderator_turn():
    entries = [_p("A"), _mod("Q1"), _p("B")]
    pairs = mb.relevance_pairs(_unit(entries, {0: 1, 1: 1, 2: 1}))
    assert len(pairs) == 1
    assert pairs[0]["cand"] == entries[2]["content"]


# ---------------------------------------------------------------------------
# Between-participant pairs
# ---------------------------------------------------------------------------

def test_between_pairs_are_cross_speaker_and_within_section_only():
    entries = [_mod(), _p("A"), _p("B"), _p("A"),
               _mod(), _p("A"), _p("B"), _p("C")]
    section_of = {0: 1, 1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 7: 2}
    pairs, used, skipped = mb.between_participant_pairs(_unit(entries, section_of))

    assert used == [1, 2]
    assert skipped == []
    # section 1: A-B, A-A (dropped), B-A  -> 2 pairs
    # section 2: A-B, A-C, B-C            -> 3 pairs
    assert sum(1 for p in pairs if p["section_index"] == 1) == 2
    assert sum(1 for p in pairs if p["section_index"] == 2) == 3
    for p in pairs:
        a = entries[p["cand_index"]]["speaker_id"]
        b = entries[p["ref_index"]]["speaker_id"]
        assert a != b


def test_between_pairs_enforce_the_tier2b_data_floor_and_report_the_skip():
    """Two participant turns is below MIN_PARTICIPANT_TURNS=3: the section must
    be reported as skipped, never dropped in silence."""
    entries = [_mod(), _p("A", words=200), _p("B", words=200)]
    pairs, used, skipped = mb.between_participant_pairs(_unit(entries, {0: 1, 1: 1, 2: 1}))

    assert pairs == []
    assert used == []
    assert len(skipped) == 1
    assert skipped[0]["section_index"] == 1
    assert skipped[0]["participant_turns"] == 2
    assert "below floor" in skipped[0]["reason"]


def test_between_pairs_skip_word_floor_and_report_real_counts():
    entries = [_mod(), _p("A", words=5), _p("B", words=5), _p("C", words=5)]
    _, used, skipped = mb.between_participant_pairs(_unit(entries, {0: 1, 1: 1, 2: 1, 3: 1}))
    assert used == []
    assert skipped[0]["participant_words"] == 15
    assert skipped[0]["participant_turns"] == 3


def test_single_speaker_section_yields_no_pairs_and_is_reported():
    entries = [_mod(), _p("A", words=80), _p("A", words=80), _p("A", words=80)]
    pairs, used, skipped = mb.between_participant_pairs(_unit(entries, {0: 1, 1: 1, 2: 1, 3: 1}))
    assert pairs == []
    assert used == []
    assert skipped[0]["reason"].startswith("no cross-speaker pair")


def test_non_substantive_sections_are_excluded():
    """Section 0 (introduction) and 6 (closing) have no human counterpart and
    must never enter the pair universe."""
    entries = [_mod(), _p("A", words=80), _p("B", words=80), _p("C", words=80)]
    for sec in (0, 6):
        pairs, used, _ = mb.between_participant_pairs(
            _unit(entries, {0: sec, 1: sec, 2: sec, 3: sec}))
        assert pairs == []
        assert used == []


# ---------------------------------------------------------------------------
# Corpus boundary — the frozen universe, not a directory listing
# ---------------------------------------------------------------------------

def test_frozen_universe_is_5_human_and_30_synthetic_units():
    frozen = json.loads(mb._FROZEN.read_text(encoding="utf-8"))
    assert len(frozen["human_inputs"]) == 5
    assert len(frozen["synthetic_inputs"]) == 30


def test_twin_population_runs_are_outside_the_frozen_universe():
    """`comparable_transcripts/` now also holds the twin-population arm. Reading
    the run list from the directory instead of the frozen manifest would silently
    pull a different experiment into every figure."""
    frozen = json.loads(mb._FROZEN.read_text(encoding="utf-8"))
    frozen_runs = {s["physical_run"] for s in frozen["synthetic_inputs"]}
    assert not any("twinpop" in r for r in frozen_runs)

    comparable = ROOT / "analysis" / "production_evaluation" / "comparable_transcripts"
    if comparable.exists():
        on_disk = {p.name for p in comparable.iterdir() if p.is_dir()}
        if any("twinpop" in r for r in on_disk):
            assert on_disk - frozen_runs, (
                "twin-population runs exist on disk; load_units must report them "
                "as excluded")


def test_substantive_sections_match_the_executed_guide():
    """Guide sections 0 and 6 are the introduction and the closing; only 1-5
    carry the prompted topics Mator's completeness metric counts."""
    guide_src = ROOT / "output" / "session_logs" / "macho_meals_fg1_run01" / "session_state_initial.json"
    if not guide_src.exists():
        pytest.skip("session logs not present")
    sections = mb.load_guide_sections(guide_src)
    labels = {s["section_index"]: s["section_label"] for s in sections}
    assert len(sections) == 7
    assert "Introduction" in labels[0]
    assert "Closing" in labels[6]
    assert mb.SUBSTANTIVE_SECTIONS == [1, 2, 3, 4, 5]
