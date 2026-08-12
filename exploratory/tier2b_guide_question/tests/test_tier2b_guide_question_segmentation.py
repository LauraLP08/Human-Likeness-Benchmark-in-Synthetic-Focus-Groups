"""
Tier 2b — guide-question segmentation tests.

Covers:
  1.  Guide loads identically from the YAML and from the executed run guide
  2.  Human FG1 boundaries land on the five `Question N.` headers
  3.  Human question numbers map 1:1 onto guide section indices
  4.  Human sections partition every transcript entry with none unassigned
  5.  Synthetic boundaries come from moderator_log `section_transition` entries
  6.  Synthetic sections cover all 7 guide sections for the principal run
  7.  Synthetic sections partition every transcript entry with none unassigned
  8.  Section turn ids are global, contiguous, and gap-free across sections
  9.  Every section's blind lines are verbatim slices of the full blind render
  10. Section blind text carries no speaker names and no provenance
  11. Synthetic boundaries cross-check clean against state_turn_*.json
  12. comparable_sections keeps 1–5 and rejects 0 and 6 as no-counterpart
  13. A below-floor section is reported as skipped_insufficient_data, not dropped
  14. A transcript with no Question header raises rather than guessing boundaries
  15. Question-number gaps are warned about, not silently interpolated
  16. _blind_line_index raises if to_blind_text's rendering changes
  17. Segmentation makes no network call (thematic_coding client is never built)

No API key and no network access required.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from thematic_coding import to_blind_text                      # noqa: E402
import tier2b_segmentation as seg                              # noqa: E402
from tier2b_segmentation import (                              # noqa: E402
    MIN_PARTICIPANT_TURNS,
    MIN_WORDS,
    comparable_sections,
    crosscheck_synthetic_against_state_files,
    find_human_boundaries,
    find_synthetic_boundaries,
    load_guide_sections,
    segment_human_by_guide,
    segment_synthetic_by_guide,
)

HUMAN_FG1 = os.path.join(ROOT, "data", "datasets_transcripts", "standardized",
                         "macho_meals", "fg1", "transcript.json")
SYNTH_RUN_DIR = os.path.join(ROOT, "output", "session_logs", "macho_meals_fg1_run01")
SYNTH_FG1 = os.path.join(SYNTH_RUN_DIR, "transcript.json")
RUN_GUIDE = os.path.join(SYNTH_RUN_DIR, "session_state_initial.json")
GUIDE_YAML = os.path.join(ROOT, "configs", "guides",
                          "macho_meals_plant_based_masculinity_uk.yaml")

pytestmark = pytest.mark.skipif(
    not (os.path.exists(HUMAN_FG1) and os.path.exists(SYNTH_FG1)),
    reason="FG1 transcripts not present in this checkout",
)


@pytest.fixture(scope="module")
def human():
    return segment_human_by_guide(HUMAN_FG1, RUN_GUIDE)


@pytest.fixture(scope="module")
def synthetic():
    return segment_synthetic_by_guide(SYNTH_FG1, RUN_GUIDE)


# --- 1 -------------------------------------------------------------------

def test_yaml_and_executed_guide_agree():
    """The YAML mirror and the guide the run actually executed must not drift."""
    from_yaml = load_guide_sections(GUIDE_YAML)
    from_run = load_guide_sections(RUN_GUIDE)
    assert [s["section_index"] for s in from_yaml] == [s["section_index"] for s in from_run]
    assert [s["section_label"] for s in from_yaml] == [s["section_label"] for s in from_run]


# --- 2, 3 ----------------------------------------------------------------

def test_human_boundaries_are_the_five_question_headers():
    entries = json.load(open(HUMAN_FG1, encoding="utf-8"))
    found, warnings = find_human_boundaries(entries)
    assert [q for _, q in found] == [1, 2, 3, 4, 5]
    assert [i for i, _ in found] == [0, 14, 22, 32, 46]
    assert warnings == []


def test_human_question_numbers_map_onto_guide_sections(human):
    guide = {s["section_index"]: s["section_label"] for s in load_guide_sections(RUN_GUIDE)}
    assert human.section_indices() == [1, 2, 3, 4, 5]
    for idx, section in human.sections.items():
        assert section.section_label == guide[idx]


# --- 4 -------------------------------------------------------------------

def test_human_sections_partition_the_transcript(human):
    entries = json.load(open(HUMAN_FG1, encoding="utf-8"))
    assigned = [i for s in human.sections.values() for i in s.entry_indices]
    assert human.unassigned_entry_indices == []
    assert sorted(assigned) == list(range(len(entries)))
    assert len(assigned) == len(set(assigned))


# --- 5 -------------------------------------------------------------------

def test_synthetic_boundaries_come_from_moderator_log():
    entries = json.load(open(SYNTH_FG1, encoding="utf-8"))
    log = json.load(open(os.path.join(SYNTH_RUN_DIR, "moderator_log.json"), encoding="utf-8"))
    guide = load_guide_sections(RUN_GUIDE)

    boundaries, warnings = find_synthetic_boundaries(entries, log, len(guide))
    assert warnings == []
    # One boundary opens each guide section after the first; a trailing
    # section_transition on the last section does not advance the index.
    assert len(boundaries) == len(guide) - 1
    assert boundaries == sorted(boundaries)

    transition_turns = [e["turn"] for e in log if e.get("action") == "section_transition"]
    for entry_idx, turn in zip(boundaries, transition_turns):
        entry = entries[entry_idx]
        assert entry["speaker_name"] == "Moderator"
        assert entry["turn"] == turn


# --- 6, 7 ----------------------------------------------------------------

def test_synthetic_covers_every_guide_section(synthetic):
    guide = load_guide_sections(RUN_GUIDE)
    assert synthetic.section_indices() == [s["section_index"] for s in guide]
    assert synthetic.warnings == []


def test_synthetic_sections_partition_the_transcript(synthetic):
    entries = json.load(open(SYNTH_FG1, encoding="utf-8"))
    assigned = [i for s in synthetic.sections.values() for i in s.entry_indices]
    assert synthetic.unassigned_entry_indices == []
    assert sorted(assigned) == list(range(len(entries)))


# --- 8 -------------------------------------------------------------------

@pytest.mark.parametrize("side", ["human", "synthetic"])
def test_turn_ids_are_global_contiguous_and_gap_free(side, human, synthetic):
    """Turns are never renumbered per section: concatenating the sections in
    order must reproduce T001..TNNN with no gaps and no repeats."""
    result = human if side == "human" else synthetic
    ids = [tid for idx in result.section_indices() for tid in result.sections[idx].turn_ids]
    numbers = [int(t.lstrip("T")) for t in ids]
    assert numbers == sorted(numbers)
    assert numbers == list(range(numbers[0], numbers[0] + len(numbers)))
    assert len(set(ids)) == len(ids)
    # Human sections start at the first Question header, which is entry 0.
    assert numbers[0] == 1


# --- 9 -------------------------------------------------------------------

@pytest.mark.parametrize("side", ["human", "synthetic"])
def test_section_blind_text_is_a_verbatim_slice_of_the_full_render(side, human, synthetic):
    """A quote verified inside a section must still verify against the full
    blind transcript — so section text has to be an exact substring of it."""
    result = human if side == "human" else synthetic
    for idx in result.section_indices():
        section = result.sections[idx]
        assert section.blind_text in result.blind_text_full
        for line, turn_id in zip(section.blind_lines, section.turn_ids):
            assert line.startswith(f"[{turn_id}] ")


# --- 10 ------------------------------------------------------------------

def test_section_blind_text_is_anonymous_and_carries_no_provenance(human, synthetic):
    names = {"David", "Amir", "Ibrahim", "Isaiah", "Will"}
    for result in (human, synthetic):
        for section in result.sections.values():
            for line in section.blind_lines:
                speaker = line.split("] ", 1)[1].split(":", 1)[0]
                assert speaker == "Moderator" or speaker.startswith("Participant ")
                assert speaker not in names
            # Neither the section label nor any provenance marker is rendered
            # into the text the evaluator sees.
            assert section.section_label not in section.blind_text
            lowered = section.blind_text.lower()
            for marker in ("session_logs", "standardized", "baseline_metadata"):
                assert marker not in lowered


# --- 11 ------------------------------------------------------------------

def test_synthetic_boundaries_crosscheck_clean_against_state_files(synthetic):
    report = crosscheck_synthetic_against_state_files(synthetic, SYNTH_RUN_DIR)
    assert report["state_files_found"] > 0
    assert report["entries_in_conflict"] == 0, report["conflicts"]
    assert report["clean"] is True
    # Differences must be confined to boundary turns — one per advancing transition.
    assert report["entries_differ_on_boundary_turn"] == len(synthetic.sections) - 1


# --- 12 ------------------------------------------------------------------

def test_comparable_sections_keeps_shared_questions_only(human, synthetic):
    indices, skipped = comparable_sections(human, synthetic)
    assert indices == [1, 2, 3, 4, 5]
    assert {s["section_index"] for s in skipped} == {0, 6}
    for s in skipped:
        assert s["status"] == "skipped_no_counterpart"
        assert s["human_counts"] is None
        assert s["synthetic_counts"] is not None


# --- 13 ------------------------------------------------------------------

def test_below_floor_section_is_reported_not_dropped(human, synthetic, monkeypatch):
    """Raising the floor above the data must surface every section as
    skipped_insufficient_data with its real counts."""
    monkeypatch.setattr(seg, "MIN_WORDS", 10 ** 6)
    indices, skipped = comparable_sections(human, synthetic)
    assert indices == []
    insufficient = [s for s in skipped if s["status"] == "skipped_insufficient_data"]
    assert {s["section_index"] for s in insufficient} == {1, 2, 3, 4, 5}
    for s in insufficient:
        assert s["human_counts"]["total_words"] > 0
        assert s["synthetic_counts"]["total_words"] > 0
        assert "human" in s["reason"] and "synthetic" in s["reason"]


def test_floor_constants_match_the_documented_defaults():
    assert MIN_PARTICIPANT_TURNS == 3
    assert MIN_WORDS == 150


# --- 14 ------------------------------------------------------------------

def test_missing_question_headers_raise_rather_than_guess(tmp_path):
    fake = tmp_path / "transcript.json"
    fake.write_text(json.dumps([
        {"turn": 0, "speaker_name": "Moderator", "speaker_role": "moderator",
         "content": "So, tell me about food."},
        {"turn": 1, "speaker_name": "Alex", "speaker_role": "participant",
         "content": "I eat what's easy."},
    ]), encoding="utf-8")
    with pytest.raises(ValueError, match="No 'Question N.' headers"):
        segment_human_by_guide(fake, RUN_GUIDE)


# --- 15 ------------------------------------------------------------------

def test_question_number_gap_is_warned_not_interpolated(tmp_path):
    """FG5 really is missing Question 4. The gap must surface as a warning and
    leave section 4 absent — never inferred from neighbouring turns."""
    entries = []
    for q in (1, 2, 3, 5):
        entries.append({"turn": len(entries), "speaker_name": "Moderator",
                        "speaker_role": "moderator", "content": f"Question {q}. Something?"})
        for k in range(3):
            entries.append({"turn": len(entries), "speaker_name": f"P{k}",
                            "speaker_role": "participant", "content": "word " * 60})
    fake = tmp_path / "transcript.json"
    fake.write_text(json.dumps(entries), encoding="utf-8")

    result = segment_human_by_guide(fake, RUN_GUIDE)
    assert result.section_indices() == [1, 2, 3, 5]
    assert 4 not in result.sections
    assert any("gaps" in w for w in result.warnings)


# --- 16 ------------------------------------------------------------------

def test_blind_render_reconstruction_is_guarded(monkeypatch):
    """If to_blind_text's format changes, Tier 2b must raise instead of
    mis-slicing sections against a stale reconstruction."""
    monkeypatch.setattr(
        seg, "to_blind_text",
        lambda entries: ("<T1> Moderator - hello", {"Moderator": "Moderator"}),
    )
    with pytest.raises(RuntimeError, match="Blind-render mismatch"):
        seg._blind_line_index([
            {"speaker_name": "Moderator", "speaker_role": "moderator", "content": "hello"},
        ])


def test_reconstruction_matches_to_blind_text_on_real_transcripts():
    for path in (HUMAN_FG1, SYNTH_FG1):
        entries = json.load(open(path, encoding="utf-8"))
        blind, speaker_map, kept, records = seg._blind_line_index(entries)
        expected, expected_map = to_blind_text(entries)
        assert blind == expected
        assert speaker_map == expected_map
        assert "\n".join(records) == expected
        assert len(kept) == len(records)


# --- 17 ------------------------------------------------------------------

def test_segmentation_makes_no_api_call(monkeypatch):
    """Segmentation is pure offline arithmetic — it must never construct a
    Gemini client, so it stays runnable without an API key."""
    import thematic_coding

    def _boom(*args, **kwargs):
        raise AssertionError("segmentation must not build an API client")

    monkeypatch.setattr(thematic_coding, "_client", _boom)
    monkeypatch.setattr(thematic_coding, "_client_for_evaluator", _boom)
    monkeypatch.setattr(thematic_coding, "_generate_with_fallback", _boom)

    segment_human_by_guide(HUMAN_FG1, RUN_GUIDE)
    segment_synthetic_by_guide(SYNTH_FG1, RUN_GUIDE)
