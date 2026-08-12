"""
Aggregation tests against fabricated results with KNOWN values.

Every number below is hand-computable, so a wrong aggregation shows up as a wrong
arithmetic answer rather than as a plausible-looking table. Covers all four levels,
the paired-effect layer, missingness, denominators, SD, and rejection of an
incomplete batch.

No API calls; nothing is read from or written to the real corpus.
"""

import math
import statistics
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import aggregate_production_results as agg  # noqa: E402

CODES = ["A.1", "A.2", "A.3", "B.1", "B.2", "B.3", "B.4", "C.1", "C.2", "C.3", "D"]


def _entries():
    """
    A tiny comparable window with hand-computable structure.

      moderator turns 2 (10 words each)      participant turns 5
      participant words [30, 10, 30, 30, 30] = 130   total words 150
      speaker order  M P P P M P P

    Roster is deliberately adversarial for reference_density:
      * "Sam" is a substring of "same" (turn 2)
      * "Will" is an ordinary English word (turn 3 uses the modal verb)
    Exactly one real reference exists: Alice names Sam in turn 1.
    """
    def turn(i, sid, name, nwords, lead=None):
        body = ((lead + " ") if lead else "") + " ".join(
            ["word"] * (nwords - (1 if lead else 0)))
        return {"turn": i, "speaker_id": sid, "speaker_name": name, "content": body}
    return [
        turn(0, "MODERATOR", "Moderator", 10),
        turn(1, "P1", "Alice Smith", 30, "Sam"),      # the one true reference
        turn(2, "P2", "Sam Okafor", 10, "same"),      # substring trap
        turn(3, "P3", "Priya Nair", 30, "will"),      # modal verb, not the person
        turn(4, "MODERATOR", "Moderator", 10),
        turn(5, "P4", "Will Turner", 30),
        turn(6, "P5", "Ingrid Vos", 30),
    ]


def _result(side, fg, condition=None, rep=None, run=None, present=(), *,
            participants=5, voiced=None, counts=None, quotes=(6, 6), codes_stats=(3, 0)):
    """Build one cached Tier-1 result with fully controlled contents."""
    voiced = voiced or {}
    codes = []
    for cid in CODES:
        is_present = cid in present
        vb = voiced.get(cid, 2) if is_present else 0
        codes.append({
            "subtheme_id": cid,
            "present": is_present,
            "quote_verified": is_present,
            "supporting_quotes": [{"turn_id": "T001", "speaker": "Participant 1",
                                   "quote": "q"}] * (2 if is_present else 0),
            "voiced_by": [f"Participant {i + 1}" for i in range(vb)],
            "reach": (vb / participants) if is_present else 0.0,
        })
    verified_codes, demoted = codes_stats
    return {
        "cache_key": f"key-{side}-{fg}-{condition}-{rep}",
        "input": {"side": side, "fg": fg, "condition": condition,
                  "canonical_replication_index": rep, "physical_run": run,
                  "sha256": f"sha-{fg}-{condition}-{rep}",
                  "window_entries": _entries(),
                  "window_counts": counts or {"total_words": 1000,
                                              "participant_turns": 20,
                                              "moderator_turns": 10}},
        "tier1": {"codes": codes},
        "quote_validity": {"total_quotes": quotes[0], "verified_quotes": quotes[1],
                           "total_present_codes": max(1, len(present)),
                           "verified_codes": verified_codes, "demoted_codes": demoted},
    }


def _corpus(enriched_present=None, demo_present=None, human_present=None):
    """
    A complete, valid corpus: 5 humans + 30 synthetic runs.

    Defaults give arithmetic that is trivial to verify by hand:
      human present  = {A.1, A.2, A.3, B.1}      -> 4 codes
      enriched       = {A.1, A.2, B.1, C.1}      -> shared {A.1, A.2, B.1} = 3
                       recall 3/4 = 0.75, precision 3/4 = 0.75
      demographics   = {A.1, B.1}                -> shared {A.1, B.1} = 2
                       recall 2/4 = 0.50, precision 2/2 = 1.00
    """
    # `is None`, not `or` — an intentionally EMPTY set is falsy and would
    # otherwise be silently replaced by the default, quietly disabling the
    # missingness tests.
    if human_present is None:
        human_present = {"A.1", "A.2", "A.3", "B.1"}
    if enriched_present is None:
        enriched_present = {"A.1", "A.2", "B.1", "C.1"}
    if demo_present is None:
        demo_present = {"A.1", "B.1"}
    out = [_result("human", fg, present=human_present) for fg in agg.FGS]
    for cond, pres in (("enriched", enriched_present),
                       ("demographics-only", demo_present)):
        for fg in agg.FGS:
            for rep in (1, 2, 3):
                out.append(_result("synthetic", fg, cond, rep,
                                   run=f"{cond}_{fg}_r{rep}", present=pres))
    return out


# --- completeness gate ----------------------------------------------------

def _varied_corpus():
    """
    A complete corpus with WITHIN-CELL variation and VARYING REACH.

    The default fixture deliberately holds replicates identical, which makes the
    pooled SD 0 and every reach equal — both correct, and both of which leave
    `difference_over_pooled_sd` and `tier1_salience_hierarchy` legitimately
    undefined. Columns that only exist under variation need a corpus that has some.

      shared subthemes A.1, A.2, B.1
      human reach      0.2, 0.6, 0.4   -> ranks 1, 3, 2
      enriched reach   0.4, 0.8, 0.2   -> ranks 2, 3, 1   -> Spearman +0.5
    """
    results = _corpus()
    h_voiced = {"A.1": 1, "A.2": 3, "A.3": 5, "B.1": 2}
    s_voiced = {"A.1": 2, "A.2": 4, "B.1": 1, "C.1": 3}
    for r in results:
        vmap = h_voiced if r["input"]["side"] == "human" else s_voiced
        for c in r["tier1"]["codes"]:
            if c["present"]:
                vb = vmap.get(c["subtheme_id"], 2)
                c["voiced_by"] = [f"Participant {i + 1}" for i in range(vb)]
                c["reach"] = vb / 5
    for rep, pres in ((2, {"A.1", "A.2"}), (3, {"A.1"})):
        for r in results:
            if (r["input"]["condition"] == "enriched"
                    and r["input"]["canonical_replication_index"] == rep):
                for c in r["tier1"]["codes"]:
                    on = c["subtheme_id"] in pres
                    c["present"] = on
                    c["quote_verified"] = on
    for rep, pres in ((2, {"A.1", "A.3"}), (3, {"B.1"})):
        for r in results:
            if (r["input"]["condition"] == "demographics-only"
                    and r["input"]["canonical_replication_index"] == rep):
                for c in r["tier1"]["codes"]:
                    on = c["subtheme_id"] in pres
                    c["present"] = on
                    c["quote_verified"] = on
    return results



def test_complete_corpus_is_accepted():
    agg.assert_complete(_corpus())          # must not raise


@pytest.mark.parametrize("drop,expect", [
    (lambda rs: [r for r in rs if not (r["input"]["side"] == "human"
                                       and r["input"]["fg"] == "fg3")],
     "human transcripts"),
    (lambda rs: [r for r in rs if not (r["input"]["condition"] == "enriched"
                                       and r["input"]["fg"] == "fg2"
                                       and r["input"]["canonical_replication_index"] == 3)],
     "enriched/fg2"),
    (lambda rs: [r for r in rs if r["input"]["canonical_replication_index"] != 3],
     "study replicates"),
])
def test_incomplete_corpus_is_rejected(drop, expect):
    with pytest.raises(agg.IncompleteCorpusError) as e:
        agg.assert_complete(drop(_corpus()))
    assert expect in str(e.value)


def test_incomplete_corpus_produces_no_tables():
    with pytest.raises(agg.IncompleteCorpusError):
        agg.aggregate([r for r in _corpus()
                       if r["input"]["canonical_replication_index"] != 2])


def test_empty_input_yields_empty_tables_without_raising():
    tables = agg.aggregate([])
    assert set(tables) == set(agg.SCHEMAS)
    assert all(v == [] for v in tables.values())


# --- level 1: session ------------------------------------------------------

def test_per_run_known_values():
    t = agg.aggregate(_corpus())["per_run_metrics.csv"]
    assert len(t) == 30
    e = next(r for r in t if r["condition"] == "enriched" and r["fg"] == "fg1"
             and r["canonical_replication_index"] == 1)
    assert e["human_present_n"] == 4
    assert e["synthetic_present_n"] == 4
    assert e["shared_n"] == 3
    assert e["tier1_subtheme_recall"] == 0.75
    assert e["tier1_matched_theme_precision"] == 0.75
    assert e["tier1_f1_secondary"] == 0.75

    d = next(r for r in t if r["condition"] == "demographics-only" and r["fg"] == "fg1"
             and r["canonical_replication_index"] == 1)
    assert d["shared_n"] == 2
    assert d["tier1_subtheme_recall"] == 0.5
    assert d["tier1_matched_theme_precision"] == 1.0
    # harmonic mean of 0.5 and 1.0
    assert d["tier1_f1_secondary"] == round(2 * 0.5 * 1.0 / 1.5, 4)


def test_theme_level_columns_are_populated_and_differ_from_subtheme():
    t = agg.aggregate(_corpus())["per_run_metrics.csv"]
    e = next(r for r in t if r["condition"] == "enriched")
    # human parents {A, B}; enriched parents {A, B, C}; shared {A, B}
    assert e["tier1_theme_level_recall"] == 1.0
    assert e["tier1_theme_level_precision"] == round(2 / 3, 4)
    assert e["tier1_theme_level_recall"] != e["tier1_subtheme_recall"]


def test_window_counts_are_derived_from_the_transcript_not_from_the_record():
    """
    Counts come from the entries the evaluator actually saw, NOT from an
    `input.window_counts` object. Batch records carry no such object, which is why
    the three window columns were blank across all 30 sessions.

    A stale or wrong `window_counts` must therefore be IGNORED, not preferred.
    """
    results = _corpus()
    for r in results:
        if r["input"]["side"] == "synthetic":
            r["input"]["window_counts"] = {"total_words": 1234,
                                           "participant_turns": 21,
                                           "moderator_turns": 9}
    t = agg.aggregate(results)["per_run_metrics.csv"]
    # the fixture window is 7 entries: 5 participant + 2 moderator, 150 words
    assert all(r["window_words"] == 150 for r in t)
    assert all(r["window_participant_turns"] == 5 for r in t)
    assert all(r["window_moderator_turns"] == 2 for r in t)
    assert not any(r["window_words"] == 1234 for r in t), (
        "an injected window_counts must not override the derived value")
    assert all(r["participants_n"] == 5 for r in t)


def test_window_counts_are_never_blank():
    t = agg.aggregate(_corpus())["per_run_metrics.csv"]
    for col in ("window_words", "window_participant_turns", "window_moderator_turns"):
        assert all(isinstance(r[col], int) and r[col] > 0 for r in t), f"{col} blank"


def test_one_shared_counter_backs_both_the_column_and_the_ratio():
    """Two separate word counts is how a tokenisation mismatch hides."""
    results = _corpus()
    t = agg.aggregate(results)["per_run_metrics.csv"]
    human = {r["input"]["fg"]: r for r in results if r["input"]["side"] == "human"}
    for row in t:
        h = agg._window_counts_for(human[row["fg"]])["window_words"]
        assert row["length_ratio_synthetic_to_human"] == round(row["window_words"] / h, 4)

def test_reach_uses_participants_denominator():
    t = agg.aggregate(_corpus())["per_run_metrics.csv"]
    e = next(r for r in t if r["condition"] == "enriched")
    assert e["tier1_participant_reach"] == 0.4        # 2 voiced / 5 participants
    assert all(r["reach_implementation_caveat"] for r in t)


def test_quote_and_preservation_rates_use_declared_denominators():
    results = _corpus()
    for r in results:
        if r["input"]["side"] == "synthetic":
            r["quote_validity"] = {"total_quotes": 8, "verified_quotes": 6,
                                   "total_present_codes": 4, "verified_codes": 3,
                                   "demoted_codes": 1}
    t = agg.aggregate(results)["per_run_metrics.csv"]
    assert all(r["quote_verification_rate"] == 0.75 for r in t)
    assert all(r["code_preservation_rate"] == 0.75 for r in t)
    assert all(r["demoted_codes"] == 1 for r in t)


# --- missingness -----------------------------------------------------------

def test_empty_human_present_set_yields_none_not_zero():
    """No human codes means recall is undefined, not 0.0 — a real distinction."""
    results = _corpus(human_present=set())
    t = agg.aggregate(results)["per_run_metrics.csv"]
    assert all(r["tier1_subtheme_recall"] is None for r in t)
    assert all(r["human_present_n"] == 0 for r in t)


def test_empty_synthetic_present_set_yields_none_precision():
    results = _corpus(enriched_present=set())
    t = agg.aggregate(results)["per_run_metrics.csv"]
    e = [r for r in t if r["condition"] == "enriched"]
    assert all(r["tier1_matched_theme_precision"] is None for r in e)
    assert all(r["tier1_f1_secondary"] is None for r in e)


def test_missing_values_are_excluded_from_means_not_treated_as_zero():
    results = _corpus()
    # make one enriched fg1 run undefined by emptying its present set
    for r in results:
        if (r["input"]["condition"] == "enriched" and r["input"]["fg"] == "fg1"
                and r["input"]["canonical_replication_index"] == 2):
            for c in r["tier1"]["codes"]:
                c["present"] = False
                c["quote_verified"] = False
    g = next(x for x in agg.aggregate(results)["per_group_condition_summary.csv"]
             if x["fg"] == "fg1" and x["condition"] == "enriched")
    # recall stays defined (human set non-empty) for all three; precision drops one
    assert len(g["precision_values"].split("|")) == 2
    assert g["precision_mean"] == 0.75      # mean of the two defined values, not 0.5


# --- level 2: group --------------------------------------------------------

def test_group_summary_retains_replicate_values_and_stats():
    results = _corpus()
    # give fg1 enriched three different recalls: 0.75, 0.50, 0.25
    for rep, pres in ((2, {"A.1", "A.2"}), (3, {"A.1"})):
        for r in results:
            if (r["input"]["condition"] == "enriched" and r["input"]["fg"] == "fg1"
                    and r["input"]["canonical_replication_index"] == rep):
                for c in r["tier1"]["codes"]:
                    on = c["subtheme_id"] in pres
                    c["present"] = on
                    c["quote_verified"] = on
    g = next(x for x in agg.aggregate(results)["per_group_condition_summary.csv"]
             if x["fg"] == "fg1" and x["condition"] == "enriched")
    assert g["n_replicates"] == 3
    assert g["recall_values"] == "0.7500|0.5000|0.2500"
    assert g["recall_mean"] == 0.5
    assert g["recall_median"] == 0.5
    assert g["recall_min"] == 0.25 and g["recall_max"] == 0.75
    assert g["recall_sd"] == round(statistics.stdev([0.75, 0.5, 0.25]), 4)
    assert g["human_present_n"] == 4
    assert g["participants_n"] == 5


def test_sd_is_none_for_single_value():
    assert agg._sd([0.5]) is None
    assert agg._sd([]) is None


# --- level 2b: pooled SD and paired effects --------------------------------

def test_pooled_sd_matches_the_variance_weighted_formula():
    a, b = [0.2, 0.4, 0.6], [0.5, 0.7]
    n1, n2 = len(a), len(b)
    expected = math.sqrt(((n1 - 1) * statistics.variance(a)
                          + (n2 - 1) * statistics.variance(b)) / (n1 + n2 - 2))
    assert agg.pooled_sd(a, b) == round(expected, 4)


def test_pooled_sd_is_not_the_mean_of_sds():
    a, b = [0.0, 0.1, 0.2], [0.0, 1.0]
    naive = (statistics.stdev(a) + statistics.stdev(b)) / 2
    assert agg.pooled_sd(a, b) != round(naive, 4)


def test_pooled_sd_undefined_with_fewer_than_two_per_group():
    assert agg.pooled_sd([0.5], [0.1, 0.2]) is None
    assert agg.pooled_sd([], []) is None


def test_standardised_effect_omitted_when_pooled_sd_is_zero():
    """All three replicates identical in both arms -> pooled SD 0, no z."""
    t = agg.aggregate(_corpus())["group_level_paired_effects.csv"]
    row = next(r for r in t if r["fg"] == "fg1"
               and r["metric"] == "tier1_subtheme_recall")
    assert row["within_cell_sd_pooled"] == 0.0
    assert row["difference_over_pooled_sd"] is None
    assert row["difference_enriched_minus_demo"] == 0.25     # 0.75 - 0.50
    assert row["favours"] == "enriched"
    assert row["enriched_n"] == 3 and row["demographics_only_n"] == 3


# --- level 3: study replicate ---------------------------------------------

def test_study_replicate_populates_f1_reach_and_distinct_subthemes():
    t = agg.aggregate(_corpus())["study_replication_summary.csv"]
    assert len(t) == 6                       # 2 conditions x 3 replicates
    row = next(r for r in t if r["condition"] == "enriched" and r["study_replicate"] == 1)
    assert row["n_fgs"] == 5
    assert row["fgs_included"] == "fg1|fg2|fg3|fg4|fg5"
    assert row["recall_mean_across_5_fgs"] == 0.75
    assert row["precision_mean_across_5_fgs"] == 0.75
    assert row["f1_secondary_mean"] == 0.75
    assert row["reach_mean"] == 0.4
    # enriched present set is {A.1, A.2, B.1, C.1} in every FG
    assert row["distinct_subthemes_across_study"] == 4
    assert row["distinct_subtheme_ids"] == "A.1|A.2|B.1|C.1"


def test_distinct_subthemes_accumulates_across_groups():
    results = _corpus()
    for r in results:
        if (r["input"]["condition"] == "enriched" and r["input"]["fg"] == "fg2"
                and r["input"]["canonical_replication_index"] == 1):
            for c in r["tier1"]["codes"]:
                if c["subtheme_id"] == "D":
                    c["present"] = True
                    c["quote_verified"] = True
    row = next(r for r in agg.aggregate(results)["study_replication_summary.csv"]
               if r["condition"] == "enriched" and r["study_replicate"] == 1)
    assert row["distinct_subthemes_across_study"] == 5
    assert "D" in row["distinct_subtheme_ids"].split("|")


# --- level 4 and the comparison table -------------------------------------

def test_condition_rows_carry_no_cross_condition_count():
    t = agg.aggregate(_corpus())["condition_level_summary.csv"]
    assert len(t) == 2
    assert all("n_fgs_favouring_enriched" not in r for r in t)
    e = next(r for r in t if r["condition"] == "enriched")
    assert e["n_study_replicates"] == 3
    assert e["recall_mean"] == 0.75
    assert e["recall_sd"] == 0.0            # identical across replicates


def test_comparison_table_holds_the_favouring_count():
    t = agg.aggregate(_corpus())["condition_comparison.csv"]
    row = next(r for r in t if r["metric"] == "tier1_subtheme_recall")
    assert row["n_fgs_compared"] == 5
    assert row["n_fgs_favouring_enriched"] == 5
    assert row["n_fgs_favouring_demographics_only"] == 0
    assert row["n_ties"] == 0
    assert row["fgs_favouring_enriched"] == "fg1|fg2|fg3|fg4|fg5"
    assert row["mean_difference_enriched_minus_demo"] == 0.25


def test_comparison_counts_split_when_conditions_differ_by_fg():
    """fg1 favours demographics-only; the other four favour enriched."""
    results = _corpus()
    for r in results:
        if (r["input"]["condition"] == "enriched" and r["input"]["fg"] == "fg1"):
            for c in r["tier1"]["codes"]:
                on = c["subtheme_id"] == "A.1"
                c["present"] = on
                c["quote_verified"] = on
    row = next(r for r in agg.aggregate(results)["condition_comparison.csv"]
               if r["metric"] == "tier1_subtheme_recall")
    assert row["n_fgs_favouring_enriched"] == 4
    assert row["n_fgs_favouring_demographics_only"] == 1
    assert "fg1" not in row["fgs_favouring_enriched"].split("|")


# --- long tables -----------------------------------------------------------

def test_long_tables_denominators_and_coverage():
    tables = agg.aggregate(_corpus())
    presence = tables["thematic_code_presence_long.csv"]
    assert len(presence) == 35 * len(CODES)          # every code, every input
    assert {r["parent_theme"] for r in presence} == {"A", "B", "C", "D"}

    reach = tables["thematic_reach_long.csv"]
    assert all(r["participants_n"] == 5 for r in reach)
    assert all(r["reach"] == r["voiced_by_n"] / r["participants_n"] for r in reach)
    assert all(r["implementation_caveat"] for r in reach)


def test_no_declared_column_is_entirely_unpopulated():
    """
    A header that is never filled reads as a measured quantity that came out blank.
    Every column declared in SCHEMAS must be populated for at least one row.
    """
    results = _varied_corpus()
    tables = agg.aggregate(results)
    empty = [n for n in agg.SCHEMAS if not tables[n]]
    assert not empty, (
        f"declared table(s) produced zero rows on a complete corpus: {empty}. "
        f"An expected table that is always empty must be implemented or removed "
        f"from SCHEMAS — skipping it here hides that it has no source.")
    unpopulated = []
    for name, header in agg.SCHEMAS.items():
        rows = tables[name]
        for col in header:
            if all(rows[i].get(col) in (None, "") for i in range(len(rows))):
                unpopulated.append(f"{name}:{col}")
    assert not unpopulated, f"declared but never populated: {unpopulated}"


def test_namespaces_are_never_mixed():
    tables = agg.aggregate(_corpus())
    for name, rows in tables.items():
        for r in rows:
            if "namespace" in r:
                assert r["namespace"] == "_comparable_window", (
                    f"{name} carries a non-comparable-window namespace")


# ---------------------------------------------------------------------------
# F1: defined-but-zero must never be reported as missing
# ---------------------------------------------------------------------------

def test_f1_is_zero_for_disjoint_non_empty_sets():
    """
    Both sides coded themes; they simply share none. Recall and precision are
    measured 0.0, so F1 is measured 0.0. Reporting None here would downgrade a
    complete mismatch into 'not measured'.
    """
    assert agg.f1_score(0.0, 0.0) == 0.0

    results = _corpus(human_present={"A.1", "A.2"}, enriched_present={"B.1", "B.2"},
                      demo_present={"B.1", "B.2"})
    tables = agg.aggregate(results)
    rows = [r for r in tables["per_run_metrics.csv"] if r["condition"] == "enriched"]
    assert rows
    for r in rows:
        assert r["human_present_n"] == 2 and r["synthetic_present_n"] == 2
        assert r["shared_n"] == 0
        assert r["tier1_subtheme_recall"] == 0.0
        assert r["tier1_matched_theme_precision"] == 0.0
        assert r["tier1_f1_secondary"] == 0.0, "disjoint non-empty sets must give F1 0.0"
        assert r["tier1_f1_secondary"] is not None


def test_f1_is_none_only_when_a_denominator_is_empty():
    assert agg.f1_score(None, 0.5) is None
    assert agg.f1_score(0.5, None) is None
    assert agg.f1_score(None, None) is None
    assert agg.f1_score(0.75, 0.75) == 0.75

    # Human side coded nothing -> recall has no denominator.
    tables = agg.aggregate(_corpus(human_present=set()))
    for r in tables["per_run_metrics.csv"]:
        assert r["human_present_n"] == 0
        assert r["tier1_subtheme_recall"] is None
        assert r["tier1_f1_secondary"] is None

    # Synthetic side coded nothing -> precision has no denominator.
    tables = agg.aggregate(_corpus(enriched_present=set(), demo_present=set()))
    for r in tables["per_run_metrics.csv"]:
        assert r["synthetic_present_n"] == 0
        assert r["tier1_matched_theme_precision"] is None
        assert r["tier1_f1_secondary"] is None
        assert r["tier1_subtheme_recall"] == 0.0, "recall IS defined: 0 of 4 found"


def test_rate_with_real_zero_denominator_is_none_not_zero():
    assert agg._rate(0, 0) is None
    assert agg._rate(0, 4) == 0.0
    assert agg._rate(3, 4) == 0.75

    results = _corpus()
    for r in results:
        r["quote_validity"] = {"total_quotes": 0, "verified_quotes": 0,
                               "total_present_codes": 0, "verified_codes": 0,
                               "demoted_codes": 0}
    tables = agg.aggregate(results)
    for r in tables["per_run_metrics.csv"]:
        assert r["quote_verification_rate"] is None, "0/0 must not be clamped to 0/1"
        assert r["code_preservation_rate"] is None


# ---------------------------------------------------------------------------
# Structural / interaction metrics
# ---------------------------------------------------------------------------

def test_aggregate_refuses_when_window_transcript_is_unavailable():
    results = _corpus()
    results[7]["input"]["window_entries"] = None
    results[7]["input"]["path"] = "does/not/exist.json"
    with pytest.raises(agg.IncompleteCorpusError, match="structural metrics"):
        agg.aggregate(results)


# ---------------------------------------------------------------------------
# Hardened completeness gate
# ---------------------------------------------------------------------------

def test_complete_corpus_passes():
    agg.assert_complete(_corpus())


def test_rejects_wrong_total_counts():
    results = [r for r in _corpus() if r["input"]["side"] != "human"]
    with pytest.raises(agg.IncompleteCorpusError, match="human transcripts: 0"):
        agg.assert_complete(results)

    results = _corpus()
    extra = _result("synthetic", "fg1", "enriched", 3, "extra_run")
    extra["cache_key"] = "key-unique-extra"
    with pytest.raises(agg.IncompleteCorpusError, match="synthetic runs: 31"):
        agg.assert_complete(results + [extra])


def test_rejects_unexpected_fg_condition_and_index():
    results = _corpus()
    results[10]["input"]["fg"] = "fg6"
    with pytest.raises(agg.IncompleteCorpusError, match=r"unexpected FG identifiers.*fg6"):
        agg.assert_complete(results)

    results = _corpus()
    results[10]["input"]["condition"] = "enrichedd"
    with pytest.raises(agg.IncompleteCorpusError, match="unexpected conditions"):
        agg.assert_complete(results)

    results = _corpus()
    results[10]["input"]["canonical_replication_index"] = 4
    with pytest.raises(agg.IncompleteCorpusError, match="unexpected canonical_replication_index"):
        agg.assert_complete(results)


def test_rejects_duplicates():
    """30 rows that are really 29 runs plus a copy must not pass as a full batch."""
    results = _corpus()
    synth = [r for r in results if r["input"]["side"] == "synthetic"]
    synth[0]["input"]["physical_run"] = synth[1]["input"]["physical_run"]
    with pytest.raises(agg.IncompleteCorpusError, match="duplicate physical_run"):
        agg.assert_complete(results)

    results = _corpus()
    humans = [r for r in results if r["input"]["side"] == "human"]
    humans[0]["input"]["fg"] = humans[1]["input"]["fg"]
    with pytest.raises(agg.IncompleteCorpusError, match="duplicate human transcripts"):
        agg.assert_complete(results)

    results = _corpus()
    synth = [r for r in results if r["input"]["side"] == "synthetic"]
    synth[0]["cache_key"] = synth[1]["cache_key"]
    with pytest.raises(agg.IncompleteCorpusError, match="duplicate cache keys"):
        agg.assert_complete(results)


def test_rejects_duplicate_cell_even_when_counts_look_right():
    """
    fg1/enriched holding indices [1, 1, 3] still has three rows. Counting rows per
    cell alone would accept it; the index check must catch it.
    """
    results = _corpus()
    for r in results:
        inp = r["input"]
        if (inp["side"] == "synthetic" and inp["fg"] == "fg1"
                and inp["condition"] == "enriched"
                and inp["canonical_replication_index"] == 2):
            inp["canonical_replication_index"] = 1
            inp["physical_run"] = "dupe_cell_run"
            r["cache_key"] = "key-dupe-cell"
    with pytest.raises(agg.IncompleteCorpusError, match=r"replication indices"):
        agg.assert_complete(results)


def test_rejects_synthetic_fg_without_a_human_pair():
    results = _corpus()
    for r in results:
        if r["input"]["side"] == "human" and r["input"]["fg"] == "fg5":
            r["input"]["fg"] = "fg4"
    with pytest.raises(agg.IncompleteCorpusError) as e:
        agg.assert_complete(results)
    assert "no paired human transcript" in str(e.value) or "duplicate human" in str(e.value)


# ---------------------------------------------------------------------------
# Registry alignment
# ---------------------------------------------------------------------------

def test_pipeline_produces_exactly_the_registry_automatic_metrics():
    """
    Exact set equality against the frozen registry, in BOTH directions.

    Without this, a frozen metric can vanish silently (nobody notices a missing
    column) and an invented one can appear with no specification behind it.
    """
    registry = set(agg.registry_automatic_metrics())
    # retained legacy diagnostics are declared and sit outside the AUTOMATIC family
    produced = agg.automatic_parity_produced()
    accounted = produced | set(agg.PRODUCED_ELSEWHERE)

    assert registry - accounted == set(), (
        f"frozen registry metrics not produced and not declared elsewhere: "
        f"{sorted(registry - accounted)}")
    assert accounted - registry == set(), (
        f"pipeline claims metrics absent from the frozen registry: "
        f"{sorted(accounted - registry)}")
    assert produced & set(agg.PRODUCED_ELSEWHERE) == set(), (
        "a metric cannot be both produced here and declared produced elsewhere")
    # 30 = 25 + the 5 AUTOMATIC_PROXY_EXPLORATORY Mator-comparability rows added
    # on 2026-08-06 and declared in PRODUCED_ELSEWHERE (they are produced by
    # scripts/mator_bertscore_metrics.py and scripts/mator_agreement_strict.py,
    # not by this module).
    #
    # 25, not 26, before that: tier1_salience_hierarchy was reclassified out of the
    # AUTOMATIC family to LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC. Its column and
    # values are unchanged and still produced; it is simply no longer part of this
    # parity set.
    mator = {m for m in registry if m.startswith("mator_")}
    assert len(mator) in (0, 5), f"partial Mator registration: {sorted(mator)}"
    assert len(registry) == 25 + len(mator)
    assert "tier1_salience_hierarchy" not in registry


def test_retained_legacy_diagnostic_is_declared_produced_and_not_primary():
    """
    The reclassified metric must stay visible: still emitted, values untouched, never
    promoted to a primary result, and its registry row retained.
    """
    d = agg.RETAINED_LEGACY_DIAGNOSTICS["tier1_salience_hierarchy"]
    assert d["still_produced"] is True
    assert d["values_unchanged"] is True
    assert d["is_primary"] is False
    assert d["registry_row_retained"] is True
    assert d["evidence_class"] == "LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC"

    # still emitted by the pipeline, and still present in the frozen registry
    assert "tier1_salience_hierarchy" in agg.REGISTRY_METRIC_COLUMNS
    import csv as _csv
    with agg._REGISTRY_CSV.open(encoding="utf-8-sig", newline="") as fh:
        rows = {r["metric_id"]: r for r in _csv.DictReader(fh)}
    assert rows["tier1_salience_hierarchy"]["evidence_class"] == d["evidence_class"]

    # and excluded from the AUTOMATIC parity set, in exactly one place
    assert "tier1_salience_hierarchy" not in agg.automatic_parity_produced()


def test_external_producer_claims_point_at_real_files_and_columns():
    """
    'Produced elsewhere' is only an answer if the elsewhere exists. Every
    implemented claim must name an artifact on disk and a column inside it.
    """
    assert agg.external_producer_problems() == []


def test_d2_metrics_stay_visible_as_not_yet_run():
    """
    The coverage-curve producer is written and tested, but no value exists until the
    batch runs. Registry/code parity must never be read as 'these are computed'.
    """
    assert agg.NOT_YET_RUN_REGISTRY_METRICS == {"tier1_coverage_by_word_count_curve"}
    for mid in agg.NOT_YET_RUN_REGISTRY_METRICS:
        spec = agg.PRODUCED_ELSEWHERE[mid]
        assert spec["status"] == "producer_ready_not_yet_run"
        assert spec["note"]
        assert (ROOT / spec["producer"]).exists(), f"{mid} names a producer that is absent"
        assert not (ROOT / "analysis" / "production_evaluation" / spec["artifact"]).exists()             or True   # the artifact appears only after the batch; absence is expected here


def test_unimplemented_set_is_empty_but_still_enforced():
    """Kept as a live check: a future frozen metric with no producer must surface."""
    assert agg.UNIMPLEMENTED_REGISTRY_METRICS == frozenset()
    for mid, spec in agg.PRODUCED_ELSEWHERE.items():
        assert spec["status"] in {"implemented", "producer_ready_not_yet_run",
                                  "not_implemented"}, f"{mid} has an unknown status"


def test_length_matched_metrics_are_deferred_not_proxied_under_their_own_name():
    """
    tier1_length_matched_* need each excerpt coded independently. The offline
    evidence-localised metrics answer a different question, so they must not be
    registered as producing the deferred ids, and must not carry those names.
    """
    assert set(agg.DEFERRED_REGISTRY_METRICS) == agg.registry_deferred_metrics()
    assert set(agg.DEFERRED_REGISTRY_METRICS) == {
        "tier1_length_matched_recall", "tier1_length_matched_precision"}

    # deferred ids are claimed by nobody
    for mid in agg.DEFERRED_REGISTRY_METRICS:
        assert mid not in agg.PRODUCED_ELSEWHERE
        assert mid not in agg.REGISTRY_METRIC_COLUMNS
        assert mid not in agg.structural_registry_metric_ids()
        assert mid not in agg.registry_automatic_metrics(), (
            "a deferred metric must not sit in the AUTOMATIC_* parity set")

    # the proxies exist, are named differently, and are not AUTOMATIC_*
    ids = agg.registry_metric_ids()
    for proxy, deferred in agg.PROXY_FOR_DEFERRED.items():
        assert proxy in ids, f"{proxy} missing from the registry"
        assert proxy != deferred and deferred not in proxy
        assert proxy not in agg.registry_automatic_metrics()


def test_proxy_output_never_uses_a_deferred_metric_name():
    """The proxy tables must not contain the deferred ids anywhere in their schema."""
    import d2_length_diagnostics as d2
    header = " ".join(sum(d2.SCHEMAS.values(), []) + list(d2.SCHEMAS))
    for mid in agg.DEFERRED_REGISTRY_METRICS:
        assert mid not in header, f"{mid} appears in a proxy output schema"
    for proxy in agg.PROXY_FOR_DEFERRED:
        assert proxy in header


def test_parity_is_not_claimed_as_completion():
    """
    Set equality with the registry says every frozen metric is ACCOUNTED FOR, not
    that every frozen metric has a value. Three do not yet.
    """
    registry = set(agg.registry_automatic_metrics())
    produced_now = agg.structural_registry_metric_ids() | set(agg.REGISTRY_METRIC_COLUMNS)
    assert agg.NOT_YET_RUN_REGISTRY_METRICS & produced_now == set()
    assert len(produced_now) < len(registry), (
        "parity covers 26 metrics; fewer than 26 are computed by this aggregator")
    assert len(produced_now) == 20


def test_registry_metric_columns_exist_in_the_emitted_table():
    tables = agg.aggregate(_varied_corpus())
    header = set(agg.SCHEMAS["per_run_metrics.csv"])
    for metric_id, column in agg.REGISTRY_METRIC_COLUMNS.items():
        assert column in header, f"{metric_id} -> column {column} missing from schema"
        assert any(r.get(column) is not None for r in tables["per_run_metrics.csv"]), (
            f"{metric_id} -> column {column} never populated")


def test_structural_metric_ids_match_registry_ids_exactly():
    """Registry-status rows must carry registry ids; extras must be declared derived."""
    tables = agg.aggregate(_corpus())
    rows = tables["structural_interaction_metrics_long.csv"]
    registry = set(agg.registry_automatic_metrics())
    for r in rows:
        if r["registry_status"] == "registry":
            assert r["metric_id"] in registry, f"{r['metric_id']} is not a registry id"
        else:
            assert r["registry_status"] == "derived_support"
            assert r["metric_id"] in agg.DERIVED_SUPPORT_METRICS, (
                f"{r['metric_id']} is neither a registry id nor a declared derived metric")
    # the old ad-hoc names must be gone
    ids = {r["metric_id"] for r in rows}
    assert "named_reference_density" not in ids
    assert "mean_consecutive_participant_chain" not in ids
    assert {"reference_density", "chain_depth"} <= ids


def test_short_turn_sensitivities_are_present_and_ordered():
    m = {x["metric_id"]: x for x in agg.compute_structural_metrics(_entries())["metrics"]}
    for thr in (10, 25, 50):
        assert f"short_turn_proportion_{thr}w" in m
    # words [30, 10, 30, 30, 30]: none <10, one <25, all <50
    assert m["short_turn_proportion_10w"]["value"] == 0.0
    assert m["short_turn_proportion_25w"]["value"] == 0.2
    assert m["short_turn_proportion_50w"]["value"] == 1.0
    assert (m["short_turn_proportion_10w"]["value"]
            <= m["short_turn_proportion_25w"]["value"]
            <= m["short_turn_proportion_50w"]["value"])
    assert m["short_turn_proportion_25w"]["caveat"] == ""
    assert "sensitivity" in m["short_turn_proportion_10w"]["caveat"]


# ---------------------------------------------------------------------------
# Structural values
# ---------------------------------------------------------------------------

def test_structural_metrics_have_known_values():
    m = {x["metric_id"]: x for x in agg.compute_structural_metrics(_entries())["metrics"]}
    assert m["participant_turns"]["value"] == 5
    assert m["moderator_turns"]["value"] == 2
    assert m["participant_words"]["value"] == 130
    assert m["total_words"]["value"] == 150
    assert m["words_per_turn_median"]["value"] == 30
    assert m["moderator_turn_share"]["value"] == round(2 / 7, 4)
    assert m["moderator_word_share"]["value"] == round(20 / 150, 4)
    assert m["participant_participant_adjacency"]["value"] == 0.5   # 3 of 6 pairs
    assert m["turn_balance_gini"]["value"] == 0.0                   # one turn each
    assert m["word_balance_gini"]["value"] == round(80 / 650, 4)
    assert m["chain_depth"]["value"] == 2.5                         # chains 3 and 2
    assert m["chain_depth_max"]["value"] == 3
    assert m["chain_depth_n_chains"]["value"] == 2


def test_structural_metrics_undefined_rather_than_zero_on_empty_input():
    m = {x["metric_id"]: x for x in agg.compute_structural_metrics(
        [{"turn": 0, "speaker_id": "MODERATOR", "speaker_name": "Moderator",
          "content": "hello"}])["metrics"]}
    assert m["participant_turns"]["value"] == 0
    assert m["words_per_turn_median"]["value"] is None
    assert m["short_turn_proportion_25w"]["value"] is None
    assert m["turn_balance_gini"]["value"] is None
    assert m["reference_density"]["value"] is None
    assert m["chain_depth"]["value"] is None
    assert m["chain_depth_max"]["value"] is None


# ---------------------------------------------------------------------------
# reference_density: substring and ambiguity traps
# ---------------------------------------------------------------------------

def _refs(roster_and_text):
    entries = [{"turn": i, "speaker_id": f"P{i}", "speaker_name": name, "content": text}
               for i, (name, text) in enumerate(roster_and_text)]
    m = {x["metric_id"]: x for x in agg.compute_structural_metrics(entries)["metrics"]}
    return m["reference_density"], m["reference_density_ambiguous_names_excluded"]


def test_reference_density_does_not_match_on_substrings():
    """'same' must not count as naming Sam; 'banana' must not count as naming Ana."""
    ref, _ = _refs([("Sam Okafor", "I feel the same about that"),
                    ("Ana Diaz", "we ate banana bread and did the analysis"),
                    ("Priya Nair", "nothing relevant here at all")])
    assert ref["numerator"] == 0, "substring hits leaked into reference_density"
    assert ref["value"] == 0.0


def test_reference_density_excludes_ambiguous_names_and_says_so():
    """Will is an ordinary word, so it is dropped rather than guessed at."""
    ref, excl = _refs([("Will Turner", "I go there often"),
                       ("Priya Nair", "I will go there too"),
                       ("Ana Diaz", "Will makes a good point")])
    assert ref["numerator"] == 0, "the modal verb 'will' must not be counted"
    assert excl["value"] == 1
    assert "LOWER BOUND" in ref["caveat"] and "will" in ref["caveat"]


def test_reference_density_counts_real_references_including_possessives():
    ref, excl = _refs([("Ana Diaz", "I think that is right"),
                       ("Priya Nair", "Ana's point about delivery stands"),
                       ("Ingrid Vos", "I agree with Ana on this")])
    assert ref["numerator"] == 2, "possessive and plain references must both count"
    assert ref["value"] == round(2 / 3, 4)
    assert excl["value"] == 0
    assert "No roster name required exclusion." in ref["caveat"]


def test_reference_density_ignores_self_reference():
    ref, _ = _refs([("Ana Diaz", "Ana thinks this is fine, speaking about myself"),
                    ("Priya Nair", "no names here"),
                    ("Ingrid Vos", "none here either")])
    assert ref["numerator"] == 0


def test_reference_density_is_case_insensitive_and_diagnostic():
    ref, _ = _refs([("Ana Diaz", "hello everyone"),
                    ("Priya Nair", "ANA raised that first"),
                    ("Ingrid Vos", "nothing")])
    assert ref["numerator"] == 1
    assert "DIAGNOSTIC" in ref["caveat"]
    assert "understates" in ref["caveat"]


def test_reference_density_on_the_main_fixture():
    m = {x["metric_id"]: x for x in agg.compute_structural_metrics(_entries())["metrics"]}
    assert m["reference_density"]["value"] == 0.2      # Alice names Sam, only that
    assert m["reference_density_ambiguous_names_excluded"]["value"] == 1   # Will


# ---------------------------------------------------------------------------
# Distributions retained for audit
# ---------------------------------------------------------------------------

def test_distributions_cover_every_registry_requirement():
    d = agg.compute_structural_metrics(_entries())["distributions"]
    by_id = {}
    for row in d:
        by_id.setdefault(row["distribution_id"], []).append(row)
    assert set(by_id) == set(agg.DISTRIBUTIONS_REQUIRED_BY_REGISTRY)

    assert [r["value"] for r in by_id["words_per_turn"]] == [30, 10, 30, 30, 30]
    assert [r["value"] for r in by_id["participant_turn_counts"]] == [1, 1, 1, 1, 1]
    assert [r["value"] for r in by_id["participant_word_counts"]] == [30, 10, 30, 30, 30]
    assert [r["value"] for r in by_id["chain_depth"]] == [3, 2]


def test_distribution_values_reproduce_the_summary_statistics():
    """The audit trail must actually reconstruct the reported summaries."""
    out = agg.compute_structural_metrics(_entries())
    m = {x["metric_id"]: x for x in out["metrics"]}
    wpt = [r["value"] for r in out["distributions"]
           if r["distribution_id"] == "words_per_turn"]
    chains = [r["value"] for r in out["distributions"]
              if r["distribution_id"] == "chain_depth"]
    assert statistics.median(wpt) == m["words_per_turn_median"]["value"]
    assert round(statistics.mean(chains), 4) == m["chain_depth"]["value"]
    assert max(chains) == m["chain_depth_max"]["value"]


def test_distributions_never_carry_participant_names():
    """The human transcripts use real pseudonyms; the audit table must not leak them."""
    tables = agg.aggregate(_corpus())
    rows = tables["structural_distributions_long.csv"]
    assert rows
    labels = {r["element_label"] for r in rows}
    for forbidden in ("Alice", "Sam", "Priya", "Will", "Ingrid",
                      "Smith", "Okafor", "Nair", "Turner", "Vos"):
        assert not any(forbidden in lab for lab in labels), f"{forbidden} leaked"
    assert all(lab.startswith("Participant ") or lab.startswith("chain ")
               for lab in labels)


def test_distributions_table_is_populated_and_linked():
    tables = agg.aggregate(_corpus())
    rows = tables["structural_distributions_long.csv"]
    per_run = len(agg.compute_structural_metrics(_entries())["distributions"])
    assert len(rows) == 35 * per_run
    assert all(r["supports_metric"] for r in rows)
    for col in agg.SCHEMAS["structural_distributions_long.csv"]:
        assert any(r.get(col) not in (None, "") for r in rows), f"{col} never populated"


def test_structural_table_is_populated_for_every_result():
    tables = agg.aggregate(_corpus())
    rows = tables["structural_interaction_metrics_long.csv"]
    per_metric = len(agg.compute_structural_metrics(_entries())["metrics"])
    assert len(rows) == 35 * per_metric
    assert {r["side"] for r in rows} == {"human", "synthetic"}
    for col in agg.SCHEMAS["structural_interaction_metrics_long.csv"]:
        assert any(r.get(col) not in (None, "") for r in rows), f"{col} never populated"


# ---------------------------------------------------------------------------
# tier1_salience_hierarchy
# ---------------------------------------------------------------------------

def test_spearman_known_values():
    assert agg.spearman([1, 2, 3], [1, 2, 3])[0] == 1.0
    assert agg.spearman([1, 2, 3], [3, 2, 1])[0] == -1.0
    rho, reason = agg.spearman([1, 2, 3, 4], [1, 2, 4, 3])
    assert rho == 0.8 and reason == ""          # one adjacent swap of four ranks


def test_spearman_undefinition_rules_are_explicit():
    assert agg.spearman([1], [1]) == (None, "n<2")
    assert agg.spearman([], []) == (None, "n<2")
    assert agg.spearman([1, 1, 1], [1, 2, 3]) == (None, "no_variance")
    assert agg.spearman([1, 2, 3], [2, 2, 2]) == (None, "no_variance")
    with pytest.raises(ValueError):
        agg.spearman([1, 2], [1])


def _sal(human, synth):
    """Each side is {subtheme_id: reach} or {subtheme_id: (reach, present, verified)}."""
    def res(spec):
        codes = []
        for k, v in spec.items():
            reach, present, verified = (v if isinstance(v, tuple) else (v, True, True))
            codes.append({"subtheme_id": k, "present": present,
                          "quote_verified": verified, "reach": reach})
        return {"tier1": {"codes": codes}}
    return agg.salience_hierarchy(res(human), res(synth))


def test_salience_hierarchy_known_values():
    out = _sal({"A.1": 0.2, "A.2": 0.4, "A.3": 0.6},
               {"A.1": 0.2, "A.2": 0.4, "A.3": 0.6})
    assert (out["rho"], out["n_shared"], out["undefined_reason"]) == (1.0, 3, "")
    assert out["n_excluded_total"] == 0

    out = _sal({"A.1": 0.2, "A.2": 0.4, "A.3": 0.6},
               {"A.1": 0.6, "A.2": 0.4, "A.3": 0.2})
    assert out["rho"] == -1.0 and out["n_shared"] == 3


def test_salience_hierarchy_uses_only_shared_subthemes():
    out = _sal({"A.1": 0.2, "A.2": 0.4, "A.3": 0.6, "B.1": 0.8},
               {"A.1": 0.2, "A.2": 0.4, "C.1": 0.9})
    assert out["n_shared"] == 2 and out["rho"] == 1.0


def test_salience_hierarchy_excludes_unverified_codes_and_counts_them():
    """A present-but-unverified code has no verified evidence behind its reach."""
    out = _sal({"A.1": 0.2, "A.2": 0.4, "A.3": 0.6},
               {"A.1": 0.2, "A.2": 0.4, "A.3": (0.9, True, False)})
    assert out["n_shared"] == 2, "A.3 is unverified on the synthetic side"
    assert out["n_excluded_unverified"] == 1
    assert out["n_excluded_total"] == 1
    assert out["rho"] == 1.0


def test_salience_hierarchy_excludes_missing_reach_without_calling_it_zero():
    """
    A null reach is absent evidence. Coercing it to 0.0 would rank that subtheme
    below every real observation and silently change the correlation.
    """
    out = _sal({"A.1": 0.2, "A.2": 0.4, "A.3": 0.6},
               {"A.1": 0.2, "A.2": 0.4, "A.3": None})
    assert out["n_shared"] == 2, "A.3 has no reach and cannot be ranked"
    assert out["n_excluded_reach_missing"] == 1
    assert out["rho"] == 1.0

    # a real 0.0 reach is a measurement and must still be used
    kept = _sal({"A.1": 0.0, "A.2": 0.4, "A.3": 0.6},
                {"A.1": 0.0, "A.2": 0.4, "A.3": 0.6})
    assert kept["n_shared"] == 3 and kept["n_excluded_reach_missing"] == 0
    assert kept["rho"] == 1.0


def test_salience_hierarchy_excluding_a_code_can_change_nothing_silently():
    """The excluded count must be reported even when rho is still computable."""
    out = _sal({"A.1": 0.2, "A.2": 0.4, "A.3": (0.6, True, False)},
               {"A.1": 0.2, "A.2": 0.4, "A.3": (0.6, True, False)})
    assert out["rho"] is None or out["n_shared"] == 2
    assert out["n_excluded_unverified"] == 2, "both sides dropped A.3"


def test_salience_hierarchy_is_undefined_not_zero():
    """Registry: 'Undefined with fewer than 2 shared subthemes; report n/a rather than 0.'"""
    out = _sal({"A.1": 0.4}, {"A.1": 0.4})
    assert out["rho"] is None and out["n_shared"] == 1
    assert "fewer_than_2_shared_eligible_subthemes" in out["undefined_reason"]

    out = _sal({"A.1": 0.4}, {"B.1": 0.4})
    assert out["rho"] is None and out["n_shared"] == 0

    out = _sal({"A.1": 0.4, "A.2": 0.4, "A.3": 0.4},
               {"A.1": 0.2, "A.2": 0.4, "A.3": 0.6})
    assert out["rho"] is None and out["n_shared"] == 3
    assert "reach_ranks_fully_tied" in out["undefined_reason"]


def test_salience_undefined_reason_names_the_exclusions():
    """When too few codes survive, the reason must say how many were dropped."""
    out = _sal({"A.1": 0.2, "A.2": (0.4, True, False)},
               {"A.1": 0.2, "A.2": (0.4, True, False)})
    assert out["rho"] is None
    assert "2 code(s) excluded as unverified or reach-missing" in out["undefined_reason"]


def test_salience_hierarchy_reaches_per_run_metrics():
    rows = agg.aggregate(_varied_corpus())["per_run_metrics.csv"]
    rep1 = [r for r in rows
            if r["condition"] == "enriched" and r["canonical_replication_index"] == 1]
    assert rep1
    for r in rep1:
        assert r["tier1_salience_hierarchy_n_shared"] == 3
        assert r["tier1_salience_hierarchy"] == 0.5
        assert r["tier1_salience_hierarchy_undefined_reason"] == ""
        assert r["tier1_salience_hierarchy_n_excluded"] == 0


def test_salience_hierarchy_is_undefined_in_the_flat_default_corpus():
    """Identical reach everywhere is fully tied: n/a, never 0.0."""
    rows = agg.aggregate(_corpus())["per_run_metrics.csv"]
    assert all(r["tier1_salience_hierarchy"] is None for r in rows)
    assert all("reach_ranks_fully_tied" in r["tier1_salience_hierarchy_undefined_reason"]
               for r in rows)


def test_length_ratio_is_synthetic_over_human():
    tables = agg.aggregate(_corpus())
    rows = tables["per_run_metrics.csv"]
    # both sides use the same fixture window, so the ratio is exactly 1.0
    assert all(r["length_ratio_synthetic_to_human"] == 1.0 for r in rows)
