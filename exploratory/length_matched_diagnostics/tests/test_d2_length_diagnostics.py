"""
D2 length-diagnostic tests against fabricated windows with KNOWN values.

Excerpt construction is checked against the frozen rule in
frozen_evaluation_spec.md §13, including the two cases most likely to be got
wrong: entries must never be cut mid-turn, and an excerpt must never be empty.

No API calls; nothing is read from or written to the real corpus.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import d2_length_diagnostics as d2  # noqa: E402


def _entry(i, words, speaker="P1", content=None):
    return {"turn": i, "speaker_id": speaker, "speaker_name": speaker,
            "content": content if content is not None else " ".join(["w"] * words)}


def _window(word_list):
    return [_entry(i, w) for i, w in enumerate(word_list)]


def _code(sid, turns, present=True, verified=True):
    return {"subtheme_id": sid, "present": present, "quote_verified": verified,
            "supporting_quotes": [{"turn_id": f"T{t:03d}", "speaker": "Participant 1",
                                   "quote": "q"} for t in turns],
            "voiced_by": ["Participant 1"], "reach": 0.2}


def _result(codes):
    return {"tier1": {"codes": codes}}


# ---------------------------------------------------------------------------
# Turn numbering must match to_blind_text, empty-turn skip included
# ---------------------------------------------------------------------------

def test_blind_entries_skips_empty_turns_like_to_blind_text():
    entries = [_entry(0, 5), _entry(1, 0, content="   "), _entry(2, 5)]
    be = d2.blind_entries(entries)
    assert len(be) == 2, "empty turns must not consume a turn id"


def test_turn_ids_align_with_the_real_renderer():
    """If this drifts, every quote position in the D2 output is off by the number
    of empty turns before it."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from thematic_coding import to_blind_text
    entries = [_entry(0, 3, "Moderator"), _entry(1, 0, content=""),
               _entry(2, 4, "P1"), _entry(3, 4, "P2")]
    blind, _ = to_blind_text(entries)
    rendered = [l for l in blind.splitlines() if l.startswith("[T")]
    assert len(rendered) == len(d2.blind_entries(entries))
    assert rendered[-1].startswith("[T003]")


# ---------------------------------------------------------------------------
# Excerpt construction — the frozen rule
# ---------------------------------------------------------------------------

def test_excerpt_never_cuts_an_entry_and_never_exceeds_target():
    entries = _window([10, 10, 10, 10, 10])
    ex = d2.build_excerpt(entries, start=0, target_words=25)
    assert ex["n_entries"] == 2                    # 10+10=20 fits, 30 would not
    assert ex["achieved_words"] == 20
    assert ex["achieved_words"] <= ex["target_words"]
    assert ex["first_entry_exceeds_target"] is False
    assert ex["start_entry_index"] == 1 and ex["end_entry_index"] == 2


def test_excerpt_is_never_empty_when_the_first_entry_exceeds_target():
    entries = _window([100, 10, 10])
    ex = d2.build_excerpt(entries, start=0, target_words=25)
    assert ex["n_entries"] == 1, "the oversized first entry is included whole"
    assert ex["achieved_words"] == 100
    assert ex["first_entry_exceeds_target"] is True
    assert ex["achieved_over_target"] == 4.0, "overshoot must stay visible"


def test_excerpt_records_target_and_achieved_and_their_ratio():
    entries = _window([10, 10, 10, 10])
    ex = d2.build_excerpt(entries, start=0, target_words=100)
    assert ex["target_words"] == 100
    assert ex["achieved_words"] == 40
    assert ex["achieved_over_target"] == 0.4, "residual mismatch must be reported"


def test_excerpt_start_is_an_entry_boundary_for_every_offset():
    entries = _window([7, 3, 11, 5, 9, 4])
    for start in range(len(entries)):
        ex = d2.build_excerpt(entries, start, target_words=15)
        assert ex["n_entries"] >= 1
        assert 1 <= ex["start_entry_index"] <= len(entries)
        assert ex["end_entry_index"] >= ex["start_entry_index"]


def test_starts_are_deterministic_and_run_seeded():
    entries = _window([10] * 40)
    a = d2.select_starts("macho_meals_fg1_run01", d2.eligible_starts(entries, 50)[0])
    b = d2.select_starts("macho_meals_fg1_run01", d2.eligible_starts(entries, 50)[0])
    c = d2.select_starts("macho_meals_fg2_run01", d2.eligible_starts(entries, 50)[0])
    assert a == b, "same run id must give identical starts"
    assert a != c, "different runs must not share the same ladder"
    assert len(a) == d2.K_EXCERPTS == 10
    assert len(set(a)) == 10, "starts must be distinct"


def test_no_start_wraps_the_window_end_to_its_beginning():
    """A wrapped excerpt would splice the tail onto the head: words in an order
    that never occurred."""
    entries = _window([10] * 30)
    for start in d2.select_starts("run-x", d2.eligible_starts(entries, 50)[0]):
        ex = d2.build_excerpt(entries, start, 50)
        assert ex["end_entry_index"] >= ex["start_entry_index"], "excerpt must be contiguous"
        assert ex["end_entry_index"] <= len(entries)


def test_build_excerpt_rejects_an_out_of_range_start():
    with pytest.raises(d2.D2InputError):
        d2.build_excerpt(_window([10, 10]), 5, 20)


# ---------------------------------------------------------------------------
# The truncated-tail defect
# ---------------------------------------------------------------------------

def test_near_end_starts_are_not_eligible_when_they_cannot_reach_the_target():
    """
    Running forward only, the last few boundaries cannot reach the target however
    the ladder is spaced. They must be excluded, not sampled into stub excerpts.
    """
    entries = _window([10] * 20)          # 200 words
    target = 100                          # needs 10 entries -> starts 0..10 only
    eligible, note = d2.eligible_starts(entries, target)
    assert note == ""
    # start 11 reaches 90 of 100 words = exactly the 0.90 tolerance, so it qualifies;
    # start 12 reaches only 80 and must not.
    assert max(eligible) == 11
    assert 12 not in eligible and 19 not in eligible
    for s in eligible:
        got = d2.build_excerpt(entries, s, target)["achieved_words"]
        assert got >= d2.LENGTH_MATCH_TOLERANCE * target, f"start {s} reached only {got}"
    for s in range(12, 20):
        assert d2.build_excerpt(entries, s, target)["achieved_words"] < 90


def test_no_excerpt_is_substantially_short_while_a_better_start_exists():
    """
    The regression guard for the original defect: a modular-rotation offset near the
    end produced a stub excerpt even though far better starts were available.
    """
    entries = _window([10] * 25)
    target = 100
    rows = d2.length_matched_excerpts(
        entries, _result([_code("A.1", [1])]), _result([_code("A.1", [1])]),
        _window([10] * 10), "run-tail")
    best = max(d2.build_excerpt(entries, s, target)["achieved_words"]
               for s in range(len(entries)))
    for r in rows:
        if r["first_entry_exceeds_target"]:
            continue
        assert r["achieved_over_target"] >= d2.LENGTH_MATCH_TOLERANCE, (
            f"excerpt {r['excerpt_index']} reached only {r['achieved_words']} of "
            f"{target} words while {best} was achievable elsewhere")
        assert r["within_tolerance"] is True


def test_k_falls_below_ten_only_with_a_recorded_reason():
    entries = _window([10] * 12)           # few eligible starts
    rows = d2.length_matched_excerpts(
        entries, _result([_code("A.1", [1])]), _result([_code("A.1", [1])]),
        _window([10] * 10), "run-small")
    assert len(rows) < 10
    assert all(r["k_excerpts"] == len(rows) for r in rows)
    assert all(r["k_reason"] for r in rows), "a short K must always carry its reason"
    assert "can reach" in rows[0]["k_reason"]


def test_window_shorter_than_target_uses_the_whole_window_and_says_so():
    entries = _window([10] * 4)            # 40 words
    human = _window([10] * 10)             # target 100
    rows = d2.length_matched_excerpts(
        entries, _result([_code("A.1", [1])]), _result([_code("A.1", [1])]),
        human, "run-short")
    assert len(rows) == 1
    assert rows[0]["n_entries"] == 4, "the whole window is used"
    assert rows[0]["achieved_words"] == 40
    assert "window_shorter_than_target" in rows[0]["k_reason"]


def test_tolerance_is_explicit_and_carried_into_the_output():
    assert d2.LENGTH_MATCH_TOLERANCE == 0.90
    rows = d2.length_matched_excerpts(
        _window([10] * 30), _result([_code("A.1", [1])]),
        _result([_code("A.1", [1])]), _window([10] * 5), "run-tol")
    assert all(r["length_match_tolerance"] == 0.90 for r in rows)


def test_summary_reports_the_achieved_ratio_spread():
    rows = d2.length_matched_excerpts(
        _window([10] * 30), _result([_code("A.1", [1]), _code("A.2", [25])]),
        _result([_code("A.1", [1]), _code("A.2", [1])]), _window([10] * 5), "run-spread")
    summ = d2.summarise(rows)
    for s in summ:
        assert s["achieved_over_target_min"] is not None
        assert s["achieved_over_target_median"] is not None
        assert s["achieved_over_target_max"] is not None
        assert s["achieved_over_target_min"] <= s["achieved_over_target_median"]             <= s["achieved_over_target_max"]
        assert s["n_excerpts_within_tolerance"] == len(rows)


# ---------------------------------------------------------------------------
# tier1_coverage_by_word_count_curve
# ---------------------------------------------------------------------------

def test_coverage_curve_is_monotonic_and_hits_the_run_total():
    entries = _window([10, 10, 10, 10])
    res = _result([_code("A.1", [1]), _code("A.2", [3]), _code("B.1", [4])])
    rows = d2.coverage_curve(entries, res)
    assert [r["words_consumed"] for r in rows] == [10, 20, 30, 40]
    assert [r["cumulative_distinct_subthemes"] for r in rows] == [1, 1, 2, 3]
    assert all(rows[i]["cumulative_distinct_subthemes"]
               <= rows[i + 1]["cumulative_distinct_subthemes"]
               for i in range(len(rows) - 1))
    assert rows[-1]["proportion_of_run_total"] == 1.0


def test_coverage_curve_uses_first_evidence_not_last():
    entries = _window([10, 10, 10])
    res = _result([_code("A.1", [3, 1, 2])])
    rows = d2.coverage_curve(entries, res)
    assert rows[0]["cumulative_distinct_subthemes"] == 1, "earliest quote places the code"


def test_coverage_curve_excludes_unverified_codes():
    entries = _window([10, 10])
    res = _result([_code("A.1", [1]), _code("A.2", [2], verified=False),
                   _code("A.3", [2], present=False)])
    rows = d2.coverage_curve(entries, res)
    assert rows[-1]["cumulative_distinct_subthemes"] == 1


def test_coverage_curve_flags_codes_it_cannot_place():
    entries = _window([10, 10])
    res = _result([_code("A.1", [1]), _code("A.2", [])])       # no quote turn
    rows = d2.coverage_curve(entries, res)
    assert rows[-1]["cumulative_distinct_subthemes"] == 1
    assert "no locatable quote turn" in rows[-1]["caveat"]


def test_coverage_curve_reports_none_rather_than_dividing_by_zero():
    rows = d2.coverage_curve(_window([10, 10]), _result([]))
    assert all(r["cumulative_distinct_subthemes"] == 0 for r in rows)
    assert all(r["proportion_of_run_total"] is None for r in rows)


# ---------------------------------------------------------------------------
# tier1_length_matched_recall / _precision
# ---------------------------------------------------------------------------

def test_length_matched_uses_the_human_word_count_as_target():
    synth = _window([10] * 20)
    human = _window([10] * 5)                     # 50 words
    rows = d2.length_matched_excerpts(
        synth, _result([_code("A.1", [1])]), _result([_code("A.1", [1])]), human,
        "macho_meals_fg1_run01")
    assert len(rows) == 10
    assert all(r["target_words"] == 50 for r in rows)
    assert all(r["achieved_words"] <= 50 for r in rows)


def test_length_matched_counts_only_codes_with_evidence_inside_the_excerpt():
    synth = _window([10] * 10)
    human = _window([10, 10])                     # target 20 -> 2 entries per excerpt
    s_res = _result([_code("A.1", [1]), _code("A.2", [9])])
    h_res = _result([_code("A.1", [1]), _code("A.2", [1]), _code("B.1", [1])])
    rows = d2.length_matched_excerpts(synth, s_res, h_res, human, "run-x")
    for r in rows:
        lo, hi = r["start_entry_index"], r["end_entry_index"]
        expected = {sid for sid, t in (("A.1", 1), ("A.2", 9)) if lo <= t <= hi}
        assert r["excerpt_localized_n"] == len(expected)
        assert r["human_present_n"] == 3
        assert r["evidence_localized_length_matched_recall"] == round(len(expected & {"A.1", "A.2"}) / 3, 4)


def test_length_matched_precision_is_none_when_the_excerpt_has_no_codes():
    synth = _window([10] * 10)
    human = _window([10])
    s_res = _result([_code("A.1", [1])])
    h_res = _result([_code("A.1", [1])])
    rows = d2.length_matched_excerpts(synth, s_res, h_res, human, "run-y")
    empty = [r for r in rows if r["excerpt_localized_n"] == 0]
    assert empty, "some excerpt must contain no coded evidence in this setup"
    assert all(r["evidence_localized_length_matched_precision"] is None for r in empty), (
        "an empty denominator is undefined, not 0.0")
    assert all(r["evidence_localized_length_matched_recall"] == 0.0 for r in empty), (
        "recall IS defined: nothing matched out of a non-empty human set")


def test_summary_reports_mean_and_sd_over_all_ten_excerpts():
    synth = _window([10] * 20)
    human = _window([10, 10])
    s_res = _result([_code("A.1", [1]), _code("A.2", [11])])
    h_res = _result([_code("A.1", [1]), _code("A.2", [1])])
    rows = d2.length_matched_excerpts(synth, s_res, h_res, human, "run-z")
    summ = {s["metric_id"]: s for s in d2.summarise(rows)}
    assert set(summ) == {"evidence_localized_length_matched_recall", "evidence_localized_length_matched_precision"}
    for s in summ.values():
        assert s["k_excerpts"] == 10
        assert s["mean"] is not None
        assert s["sd"] is not None, "SD over 10 excerpts must be reported, not just the mean"
        assert s["target_words"] == 20
        assert s["achieved_over_target_median"] is not None
        assert s["n_undefined"] is not None


def test_derivation_limitation_is_carried_on_every_row():
    """The excerpt was never re-coded in isolation; that must not be implied."""
    synth = _window([10] * 12)
    human = _window([10])
    rows = d2.length_matched_excerpts(synth, _result([_code("A.1", [1])]),
                                     _result([_code("A.1", [1])]), human, "run-w")
    assert all("different estimand from coding the" in r["caveat"] for r in rows)
    cov = d2.coverage_curve(synth, _result([_code("A.1", [1])]))
    assert all("full-window Tier-1 result" in r["caveat"] for r in cov)


def test_empty_window_raises_rather_than_returning_a_silent_zero():
    with pytest.raises(d2.D2InputError):
        d2.build_excerpt([], 0, 50)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_schemas_declare_the_three_frozen_metric_ids():
    header = " ".join(sum(d2.SCHEMAS.values(), []))
    for mid in ("evidence_localized_length_matched_recall", "evidence_localized_length_matched_precision"):
        assert mid in header
    assert "metric_id" in d2.SCHEMAS["d2_coverage_by_word_count_curve.csv"]
    assert "tier1_length_matched_recall" not in header, (
        "the deferred metric name must not appear on a proxy output")
