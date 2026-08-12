"""
Window counts must be derived from `input.path`, not from a key Batch records lack.

`aggregate()` read `input.window_counts`. Synchronous records carried it; Batch
records do not. The result was that window_words, window_participant_turns and
window_moderator_turns were blank on all 30 session rows — three declared columns
silently empty in a table that otherwise looked complete.

These tests use fixtures with the REAL Batch record shape (no `window_counts`) and
real transcript files, so the defect cannot come back disguised as a schema
difference.

No API calls.
"""

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import aggregate_production_results as agg   # noqa: E402
import production_eval_pipeline as pep       # noqa: E402

OUT = ROOT / "analysis" / "production_evaluation"
RESULTS = OUT / "results"
WINDOW_COLS = ("window_words", "window_participant_turns", "window_moderator_turns")


@pytest.fixture(scope="module")
def corpus():
    res = agg.load_results()
    if len(res) != 35:
        pytest.skip(f"corpus not complete ({len(res)}/35)")
    return res


# ---------------------------------------------------------------------------
# The Batch record shape
# ---------------------------------------------------------------------------

def test_batch_records_really_lack_window_counts(corpus):
    """The premise of the bug — assert it rather than assume it."""
    assert all("window_counts" not in r["input"] for r in corpus), (
        "if Batch records started carrying window_counts, these tests would pass "
        "for the wrong reason")


def test_counts_are_derived_from_the_recorded_path(corpus):
    for r in corpus:
        entries = pep._entries_for({"path": r["input"]["path"],
                                    "side": r["input"]["side"]})
        expected = agg.window_counts(entries)
        got = agg._window_counts_for(r)
        assert got["window_words"] == expected["window_words"]
        assert got["window_participant_turns"] == expected["window_participant_turns"]
        assert got["window_moderator_turns"] == expected["window_moderator_turns"]


def test_synthetic_counts_come_from_the_comparable_window_not_the_full_transcript(corpus):
    """
    A comparable window must never be silently replaced by the full session
    transcript — that would inflate every synthetic word count and every ratio.
    """
    for r in corpus:
        if r["input"]["side"] != "synthetic":
            continue
        path = r["input"]["path"].replace("\\", "/")
        assert "comparable_transcript.json" in path
        assert "output/session_logs" not in path

        full = ROOT / "output" / "session_logs" / r["input"]["physical_run"] / "transcript.json"
        if not full.exists():
            continue
        payload = json.loads(full.read_text(encoding="utf-8"))
        full_entries = payload["transcript"] if isinstance(payload, dict) else payload
        full_words = agg.window_counts(full_entries)["window_words"]
        window_words = agg._window_counts_for(r)["window_words"]
        assert window_words < full_words, (
            f"{r['input']['physical_run']}: window {window_words} words is not "
            f"smaller than the full transcript {full_words} — the window may have "
            f"been replaced by the full session")


def test_empty_entries_follow_the_to_blind_text_rule():
    entries = [{"speaker_id": "MODERATOR", "content": "a b c"},
               {"speaker_id": "P1", "content": "   "},
               {"speaker_id": "P1", "content": ""},
               {"speaker_id": "P2", "content": "d e"}]
    c = agg.window_counts(entries)
    assert c["window_entries_included"] == 2
    assert c["window_entries_skipped_empty"] == 2
    assert c["window_words"] == 5
    assert c["window_participant_turns"] == 1
    assert c["window_moderator_turns"] == 1


# ---------------------------------------------------------------------------
# One shared function — no second word count
# ---------------------------------------------------------------------------

def test_length_ratio_uses_the_same_word_count_as_the_column(corpus):
    """A separate tokenisation for the ratio is how an inconsistency hides."""
    human = {r["input"]["fg"]: r for r in corpus if r["input"]["side"] == "human"}
    tables = agg.aggregate(corpus)
    by_run = {r["physical_run"]: r for r in tables["per_run_metrics.csv"]}
    for r in corpus:
        if r["input"]["side"] != "synthetic":
            continue
        row = by_run[r["input"]["physical_run"]]
        h_words = agg._window_counts_for(human[r["input"]["fg"]])["window_words"]
        expected = round(row["window_words"] / h_words, 4)
        assert row["length_ratio_synthetic_to_human"] == expected, (
            f"{r['input']['physical_run']}: ratio does not reconcile with window_words")


def test_structural_total_words_matches_the_window_counter(corpus):
    for r in corpus:
        entries = pep._entries_for({"path": r["input"]["path"],
                                    "side": r["input"]["side"]})
        metrics = {m["metric_id"]: m["value"]
                   for m in agg.compute_structural_metrics(entries)["metrics"]}
        c = agg.window_counts(entries)
        assert metrics["total_words"] == c["window_words"]
        assert metrics["participant_turns"] == c["window_participant_turns"]
        assert metrics["moderator_turns"] == c["window_moderator_turns"]


# ---------------------------------------------------------------------------
# The emitted table
# ---------------------------------------------------------------------------

def test_all_thirty_session_rows_carry_window_counts(corpus):
    rows = agg.aggregate(corpus)["per_run_metrics.csv"]
    assert len(rows) == 30
    for col in WINDOW_COLS:
        populated = [r for r in rows if r.get(col) not in (None, "")]
        assert len(populated) == 30, f"{col}: {len(populated)}/30 populated"
        assert all(isinstance(r[col], int) and r[col] > 0 for r in populated)


def test_emitted_csv_has_no_empty_window_cells():
    """Checked on the REAL emitted file, not only in memory."""
    path = RESULTS / "per_run_metrics.csv"
    if not path.exists():
        pytest.skip("per_run_metrics.csv not generated")
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert len(rows) == 30
    for col in WINDOW_COLS:
        blanks = [r["physical_run"] for r in rows if r[col] in ("", None)]
        assert not blanks, f"{col} blank for: {blanks}"


def test_no_declared_column_is_empty_on_the_real_corpus(corpus):
    """
    The completeness check run against the real Batch corpus, not a hand-built
    fixture — a fixture can accidentally reproduce the schema it was written from.
    """
    tables = agg.aggregate(corpus)
    empty_tables = [n for n in agg.SCHEMAS if not tables[n]]
    assert not empty_tables, f"tables with zero rows: {empty_tables}"
    unpopulated = []
    for name, header in agg.SCHEMAS.items():
        rows = tables[name]
        for col in header:
            if all(r.get(col) in (None, "") for r in rows):
                unpopulated.append(f"{name}:{col}")
    assert not unpopulated, f"declared but never populated: {unpopulated}"


THEMATIC_KEYS = ("tier1_subtheme_recall", "tier1_matched_theme_precision",
                 "tier1_f1_secondary", "tier1_participant_reach",
                 "tier1_salience_hierarchy", "length_ratio_synthetic_to_human",
                 "shared_n", "human_present_n", "synthetic_present_n")

SNAPSHOT = OUT / "snapshots" / "per_run_metrics_prefix_window_counts.csv"


def test_aggregation_is_deterministic_post_fix(corpus):
    """
    Two runs of the CURRENT code agree.

    This demonstrates determinism only. It says nothing about whether the fix
    changed historical values — for that see the snapshot test below.
    """
    a = agg.aggregate(corpus)["per_run_metrics.csv"]
    b = agg.aggregate(corpus)["per_run_metrics.csv"]
    for x, y in zip(a, b):
        assert x["physical_run"] == y["physical_run"]
        for k in THEMATIC_KEYS:
            assert x[k] == y[k]


def test_thematic_metrics_identical_to_the_authentic_pre_fix_snapshot(corpus):
    """
    Compared against per_run_metrics.csv as it was emitted BEFORE the fix.

    The snapshot is a real historical artifact from the completed 35/35 corpus, in
    which all 30 window cells are blank. That is what makes this a test of identity
    across the change rather than of determinism within it.
    """
    if not SNAPSHOT.exists():
        pytest.skip("no authentic pre-fix snapshot available")
    prev = list(csv.DictReader(SNAPSHOT.read_text(encoding="utf-8-sig").splitlines()))
    assert len(prev) == 30
    assert all(r["window_words"] == "" for r in prev), (
        "the snapshot must be the PRE-fix artifact, i.e. window columns blank")

    now = list(csv.DictReader(
        (RESULTS / "per_run_metrics.csv").read_text(encoding="utf-8-sig").splitlines()))
    assert len(now) == 30
    changed = []
    for a, b in zip(prev, now):
        assert a["physical_run"] == b["physical_run"]
        for k in THEMATIC_KEYS:
            if a[k] != b[k]:
                changed.append(f"{a['physical_run']}.{k}: {a[k]} -> {b[k]}")
    assert not changed, f"the fix altered thematic values: {changed}"
