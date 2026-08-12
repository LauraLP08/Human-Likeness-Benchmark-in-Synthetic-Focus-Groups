"""
The remaining-input count must be DERIVED, never asserted.

A report once said "the remaining 27 evaluations". The preflight had completed 3 of
35, so 32 remained. The sentence was written by hand and nothing checked it. These
tests recompute the count from `frozen_evaluator_inputs.json` and the COMPLETE
batch-mode cache keys on disk, so a stale number in prose cannot survive.

No API calls.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import batch_corpus_manifest as bcm     # noqa: E402
import production_eval_pipeline as pep  # noqa: E402

OUT = ROOT / "analysis" / "production_evaluation"


def _frozen():
    f = pep.load_inputs()
    return f["human_inputs"], f["synthetic_inputs"]


def test_frozen_corpus_is_five_human_and_thirty_synthetic():
    h, s = _frozen()
    assert len(h) == 5
    assert len(s) == 30
    assert len(h) + len(s) == 35


def test_remaining_count_is_derived_from_disk_not_a_constant():
    """35 frozen minus the COMPLETE batch results actually present."""
    h, s = _frozen()
    done = bcm.completed_batch_keys()
    remaining = (len(h) + len(s)) - len(done)
    assert remaining == 35 - len(done)
    # with the preflight's 3 complete, this is 32 — but the assertion is on the
    # derivation, so it stays true as the corpus fills up.
    assert 0 <= remaining <= 35


def test_completion_counts_only_complete_batch_entries():
    """Synchronous and quarantined entries must not count as done."""
    for key, rec in bcm.completed_batch_keys().items():
        assert rec["effective_request_config"]["execution_mode"] == "batch"
        assert rec["completeness"]["status"] == "COMPLETE"
        assert rec["cache_key"] == key


def test_synchronous_results_do_not_reduce_the_remaining_count():
    cache = OUT / "evaluator_cache"
    sync = [json.loads(p.read_text(encoding="utf-8")) for p in cache.glob("*.json")]
    sync = [j for j in sync
            if j["effective_request_config"]["execution_mode"] == "synchronous"]
    done_keys = set(bcm.completed_batch_keys())
    for j in sync:
        assert j["cache_key"] not in done_keys, (
            "a synchronous result must never count towards batch completion")


def test_manifest_counts_match_the_derivation():
    m = json.loads((OUT / "batch_corpus_manifest.json").read_text(encoding="utf-8"))
    c = m["counts"]
    assert c["frozen_total"] == 35
    assert c["frozen_human"] == 5
    assert c["frozen_synthetic"] == 30
    assert c["pending_total"] == c["frozen_total"] - c["already_complete_from_preflight"]
    assert c["pending_total"] == c["pending_human"] + c["pending_synthetic"]
    assert len(m["requests"]) == c["pending_total"]


def test_the_documented_split_is_four_human_and_twenty_eight_synthetic():
    """The specific correction: not 27, and not 3 human + 29 synthetic either."""
    m = json.loads((OUT / "batch_corpus_manifest.json").read_text(encoding="utf-8"))
    c = m["counts"]
    assert c["already_complete_from_preflight"] == 3
    assert c["pending_total"] == 32
    assert c["pending_human"] == 4
    assert c["pending_synthetic"] == 28


STALE_PHRASES = ("remaining 27", "27 evaluations", "other 27", "27 inputs")


def _claims(node, path=""):
    """Yield (path, text) for values that ASSERT something.

    A field recording a corrected error — anything under a `*correction*` key — is a
    record of what was wrong, not a live claim, and is excluded. Nothing else is.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if "correction" in str(k).lower():
                continue
            yield from _claims(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _claims(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def test_no_document_still_claims_twenty_seven_remaining():
    """Prose and derived counts must not disagree."""
    offenders = []

    md = OUT / "PRE_EVALUATION_GATE_REPORT.md"
    if md.exists():
        text = md.read_text(encoding="utf-8", errors="replace")
        for phrase in STALE_PHRASES:
            if phrase in text:
                offenders.append(f"{md.name}: {phrase!r}")

    js = OUT / "preflight_batch_result.json"
    if js.exists():
        data = json.loads(js.read_text(encoding="utf-8"))
        for where, text in _claims(data):
            for phrase in STALE_PHRASES:
                if phrase in text:
                    offenders.append(f"{js.name}{where}: {phrase!r}")

    assert not offenders, f"stale counts still asserted: {offenders}"


def test_the_correction_record_itself_is_retained():
    """The wrong figure stays on record, so the correction is auditable."""
    data = json.loads((OUT / "preflight_batch_result.json").read_text(encoding="utf-8"))
    rec = data["count_correction"]
    assert "27" in rec["was"]
    assert "32" in rec["is"]
    assert rec["arithmetic"] and rec["now_derived"]


def test_final_set_covers_the_whole_design():
    """preflight + production must reconstitute exactly the frozen corpus."""
    m = json.loads((OUT / "batch_corpus_manifest.json").read_text(encoding="utf-8"))
    final = m["final_set_all_35"]
    assert len(final) == 35
    assert len({r["expected_cache_key"] for r in final}) == 35
    assert sum(1 for r in final if r["side"] == "human") == 5
    assert sum(1 for r in final if r["side"] == "synthetic") == 30
    for cond in ("enriched", "demographics-only"):
        for fg in ("fg1", "fg2", "fg3", "fg4", "fg5"):
            rows = [r for r in final
                    if r["side"] == "synthetic" and r["condition"] == cond
                    and r["fg"] == fg]
            assert len(rows) == 3, f"{cond}/{fg} has {len(rows)} replicates"
            assert sorted(r["canonical_replication_index"] for r in rows) == [1, 2, 3]


def test_archived_runs_stay_excluded():
    m = json.loads((OUT / "batch_corpus_manifest.json").read_text(encoding="utf-8"))
    runs = {r["physical_run"] for r in m["final_set_all_35"]}
    assert "macho_meals_fg4_run02" not in runs
    assert "macho_meals_fg5_run02" not in runs
    for fg, expected in (("fg4", bcm.FG4_ENRICHED_EXPECTED),
                         ("fg5", bcm.FG5_ENRICHED_EXPECTED)):
        got = sorted(r["physical_run"] for r in m["final_set_all_35"]
                     if r["fg"] == fg and r["condition"] == "enriched")
        assert got == sorted(expected)
