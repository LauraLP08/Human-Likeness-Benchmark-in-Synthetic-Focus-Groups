"""
Focused tests for the Level 2 coverage-accumulation and lexical diagnostics.

Both are derived from existing artefacts: no API call, no new human coding, no
embeddings. These tests guard the properties most at risk of being overstated:

  * that accumulation runs per STUDY REPLICATE, not over replicates unioned within a
    focus group (the defect these modules were rebuilt to correct);
  * that the 15-session union is never presented as a study replicate's repertoire;
  * that a curve endpoint is not treated as a plateau without an explicit criterion;
  * that a budget-equalised specification whose human side rests on one focus group
    cannot carry the sensitivity verdict;
  * that MATTR is described as less length-sensitive rather than length-insensitive;
  * that the numeral count never discharges the registry indicator.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

_FINAL = _ROOT / "analysis/production_evaluation/final"
_RES = _ROOT / "analysis/production_evaluation/results"

pytestmark = pytest.mark.skipif(
    not (_FINAL / "saturation_analysis.json").exists(),
    reason="analyses have not been built yet")

FGS = ["fg1", "fg2", "fg3", "fg4", "fg5"]
REPS = ["1", "2", "3"]
SYNTH = ["enriched", "demographics-only"]


def _L(p):
    return json.loads((_FINAL / p).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sat():
    return _L("saturation_analysis.json")


@pytest.fixture(scope="module")
def lex():
    return _L("lexical_analysis.json")


# ---------------------------------------------------------- shared status
def test_both_analyses_are_exploratory_and_temporally_declared(sat, lex):
    for o in (sat, lex):
        assert o["status"] == "EXPLORATORY"
        t = o["temporal_transparency"].lower()
        assert "after the main results were known" in t
        assert o["no_api_calls"] is True and o["no_new_human_coding"] is True


def test_source_shape_is_35_documents(sat):
    assert "35 documents x 11 subthemes = 385 rows" == sat["source_shape"]
    assert sat["documents"] == "5 human focus groups + 30 synthetic runs = 35"
    import csv
    rows = list(csv.DictReader(
        (_RES / "thematic_code_presence_long.csv").open(encoding="utf-8")))
    docs = {(r["physical_run"] if r["side"] == "synthetic" else "human::" + r["fg"])
            for r in rows}
    assert len(docs) == 35 and len(rows) == 385


# ------------------------------------------------ accumulation, per replicate
def test_accumulation_is_per_study_replicate(sat):
    """
    The defect this rebuild corrects: unioning the three replicates within each focus
    group produces a different, larger object than one study of five groups.
    """
    assert "study replicate" in sat["unit_of_accumulation"]
    c = sat["accumulation_curves"]
    assert set(c) == {"human", "enriched", "demographics-only"}
    assert list(c["human"]) == ["human"]
    for cond in SYNTH:
        assert sorted(c[cond]) == REPS, cond
        for r in REPS:
            assert len(c[cond][r]["mean"]) == 5, f"{cond}/{r}"
            assert c[cond][r]["n_orderings"] == 120


def test_each_replicate_curve_is_monotonic_and_ends_at_its_own_total(sat):
    for cond, reps in sat["accumulation_curves"].items():
        for r, v in reps.items():
            m = v["mean_exact"]
            assert all(m[i] <= m[i + 1] + 1e-9 for i in range(4)), f"{cond}/{r}"
            assert v["min"][-1] == v["max"][-1] == v["final_total_codes"], f"{cond}/{r}"
            assert v["final_total_codes"] <= sat["codebook_size"]


def test_replicate_totals_never_exceed_the_15_session_union(sat):
    """
    The union is an upper bound over the same sessions, so no replicate can exceed it.
    A replicate MAY equal it — demographics-only R1 does, reaching all 6 codes that
    condition ever produces — which is a property of the data, not a defect. The
    substantive claim is that the typical replicate sits below the union, so the union
    must not be reported as what a study would recover.
    """
    for cond, a in sat["across_replicates"].items():
        union = a["CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS"]
        totals = list(a["final_total_codes_per_replicate"].values())
        assert max(totals) <= union["value"], cond
        assert a["final_total_mean"] < union["value"], cond
        assert min(totals) < union["value"], cond
        assert "is_NOT" in union
        assert "never be reported" in union["is_NOT"]


def test_the_union_figure_is_named_and_not_called_a_repertoire(sat):
    for cond, a in sat["across_replicates"].items():
        assert "CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS" in a
    u_e = sat["across_replicates"]["enriched"][
        "CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS"]["value"]
    u_d = sat["across_replicates"]["demographics-only"][
        "CONDITION_WIDE_MAXIMUM_OBSERVED_REPERTOIRE_ACROSS_15_SESSIONS"]["value"]
    assert (u_e, u_d) == (9, 6)          # retained only under this name


def test_replicates_are_summarised_as_mean_and_range(sat):
    for cond, a in sat["across_replicates"].items():
        assert a["n_study_replicates"] == 3
        totals = list(a["final_total_codes_per_replicate"].values())
        assert len(totals) == 3
        assert a["final_total_min"] == min(totals)
        assert a["final_total_max"] == max(totals)
        assert a["final_total_range"] == f"{min(totals)}-{max(totals)}"
        assert "never treated as extra FGs" in \
            a["replicates_are_not_independent_focus_groups"]


def test_plateau_is_defined_explicitly_and_marked_post_hoc(sat):
    p = sat["plateau_criterion"]
    assert "< 0.5 codes" in p["rule"]
    assert "POST HOC" in p["status"]
    assert "NOT evidence of a plateau" in sat["endpoint_interpretation"]
    # every curve must expose the increments the criterion reads
    for cond, reps in sat["accumulation_curves"].items():
        for r, v in reps.items():
            assert len(v["marginal_mean_increment"]) == 4, f"{cond}/{r}"


def test_estimand_caveats_are_present(sat):
    assert sat["codebook_is_fixed_a_priori"] is True
    assert "coverage accumulation" in sat["estimand"]
    assert "Guest" in sat["not_equivalent_to"]
    assert sat["meaning_saturation"].startswith("NOT COMPUTED")


def test_derived_quantities_use_unrounded_operands(sat):
    for cond, reps in sat["accumulation_curves"].items():
        for r, v in reps.items():
            assert v["mean"] == [round(x, 4) for x in v["mean_exact"]], f"{cond}/{r}"
            assert v["marginal_mean_increment"] == [
                round(v["mean_exact"][i + 1] - v["mean_exact"][i], 4)
                for i in range(4)], f"{cond}/{r}"


# ------------------------------------------------------- theme recurrence
def test_theme_recurrence_is_reported_per_replicate(sat):
    rec = sat["theme_recurrence"]
    assert len(rec) == sat["codebook_size"]
    for code, e in rec.items():
        assert 0 <= e["human"] <= 5, code
        for cond in SYNTH:
            for r in REPS:
                assert 0 <= e[f"{cond}_R{r}"] <= 5, f"{code}/{cond}/{r}"
            assert f"{cond}_mean" in e and f"{cond}_range" in e


def test_recurrence_reconciles_with_the_presence_table(sat):
    import csv
    from collections import defaultdict
    rows = list(csv.DictReader(
        (_RES / "thematic_code_presence_long.csv").open(encoding="utf-8")))
    cell = defaultdict(set)
    for r in rows:
        if r["present"] == "True":
            rep = r["canonical_replication_index"] if r["side"] == "synthetic" else "human"
            cell[(r["condition"], rep, r["fg"])].add(r["subtheme_id"])
    for code, e in sat["theme_recurrence"].items():
        assert e["human"] == sum(1 for f in FGS if code in cell[("human", "human", f)])
        for cond in SYNTH:
            for r in REPS:
                assert e[f"{cond}_R{r}"] == sum(
                    1 for f in FGS if code in cell[(cond, r, f)]), f"{code}/{cond}/{r}"


def test_never_observed_flag_is_consistent(sat):
    for code, e in sat["theme_recurrence"].items():
        expected = all(e[f"{c}_R{r}"] == 0 for c in SYNTH for r in REPS)
        assert e["never_observed_in_any_synthetic_session"] is expected, code


# ------------------------------------------------------------- prevalence
def test_terciles_are_withdrawn_and_bands_preserve_ties(sat):
    p = sat["prevalence"]
    assert p["reported_code_by_code"] is True
    assert "alphabetical" in p["terciles_withdrawn"]
    assert "EXPLORATORY" in p["tie_preserving_bands_status"]
    # every band must contain codes of exactly one prevalence value
    for value, codes in p["tie_preserving_bands"].items():
        for c in codes:
            assert p["human_prevalence_per_code"][c] == int(value), c
    flat = [c for v in p["tie_preserving_bands"].values() for c in v]
    assert sorted(flat) == sorted(p["human_prevalence_per_code"])


# ---------------------------------------------------------------- lexical
def test_lexical_window_reconciles_with_the_structural_results(lex):
    import csv
    pub = {}
    for r in csv.DictReader(
            (_RES / "structural_interaction_metrics_long.csv").open(encoding="utf-8")):
        if r["side"] == "synthetic" and r["metric_id"] == "total_words":
            pub[r["physical_run"]] = float(r["value"])
    n = 0
    for s in lex["per_session"]:
        if s["condition"] == "human":
            continue
        tag = ("macho_meals_" + s["fg"]
               + ("_demoonly" if s["condition"] == "demographics-only" else "")
               + "_run0" + s["replicate"])
        assert s["total_words"] == pub[tag], tag
        n += 1
    assert n == 30


def test_no_embeddings_were_used(lex):
    assert lex["no_embeddings"] is True


# ------------------------------------------------- plateau criterion placement


def test_criterion_is_retained_for_audit_and_flagged(sat):
    """Removing it from the drafts must not delete the audit trail."""
    p = sat["plateau_criterion"]
    assert "0.5 codes" in p["rule"] or "0.5" in p["rule"]
    assert "POST HOC" in p["status"].upper()
    idx = (_FINAL / "RESULTS_TRACEABILITY_INDEX.md").read_text(encoding="utf-8")
    assert "POST_HOC_ARBITRARY_NON_SUBSTANTIVE" in idx
    assert "0.5 subthemes" in idx
    assert "absent" in idx and "Results and Discussion drafts" in idx


def test_correction_log_does_not_misstate_where_the_criterion_lived():
    """
    §14 previously claimed the criterion was already confined to the artefact and index.
    It was not — it was still quoted in both drafts until round three.
    """
    t = " ".join((_FINAL / "LEVEL2_LEXICAL_CORRECTION_LOG.md")
                 .read_text(encoding="utf-8").split())
    assert "remains in the artefact and in the traceability index only. It appears in " \
           "no conclusion" not in t
    assert "That was inaccurate when written" in t
    assert "Round three removed it; see §15." in t
    assert "# Third correction round" in t


# ------------------------------------------------------------- claim matrix


def _claims():
    import csv
    return {r["claim_id"]: r for r in csv.DictReader(_MATRIX.open(encoding="utf-8"))}


# ------------------------------------------------- subsample offset integrity
def _budgeted(lex, cond, fg, rep, arm, budget):
    s = next(x for x in lex["per_session"]
             if x["condition"] == cond and x["fg"] == fg and x["replicate"] == rep)
    return s["budgeted"][arm][str(budget)]


def test_offsets_never_repeat_in_any_session(lex):
    """
    The defect: a speaker with fewer feasible start positions than requested had their
    offsets cycled to reach a fixed count, so identical text was resampled and counted
    as new evidence while n_subsamples was still recorded as 10.
    """
    checked = 0
    for s in lex["per_session"]:
        for arm, by in s["budgeted"].items():
            for b, v in by.items():
                if v is None:
                    continue
                assert v["subsamples_were_padded_by_repetition"] is False
                for sp, offs in v["offsets_used"].items():
                    assert len(offs) == len(set(offs)), (s["fg"], arm, b, sp)
                    assert len(offs) == v["n_unique_subsamples"], (s["fg"], arm, b, sp)
                    checked += 1
    assert checked > 1000, checked


def test_unique_subsample_count_is_recorded_separately_from_the_request(lex):
    for s in lex["per_session"]:
        for arm, by in s["budgeted"].items():
            for b, v in by.items():
                if v is None:
                    continue
                assert v["n_requested_subsamples"] == 10
                assert 1 <= v["n_unique_subsamples"] <= 10
                assert v["jaccard"]["n_values"] == v["n_unique_subsamples"]
                assert v["jensen_shannon_distance"]["n_values"] == v["n_unique_subsamples"]
                assert v["cosine_similarity"]["n_values"] == v["n_unique_subsamples"]


@pytest.mark.parametrize("arm", ["content_min3_nostop", "content_min1_nostop"])
def test_human_fg2_at_budget_100_has_exactly_five_unique_offsets(lex, arm):
    """The concrete case that exposed the defect: one speaker has 104 tokens."""
    v = _budgeted(lex, "human", "fg2", None, arm, 100)
    assert v["n_requested_subsamples"] == 10
    assert v["n_unique_subsamples"] == 5
    assert v["limiting_speaker"] == "mm_fg2_bilal"
    assert v["offsets_used"]["mm_fg2_bilal"] == [0, 1, 2, 3, 4]
    assert v["tokens_available_per_speaker"]["mm_fg2_bilal"] == 104
    for sp, offs in v["offsets_used"].items():
        assert len(offs) == 5 and len(set(offs)) == 5, sp


def test_a_session_with_ten_unique_offsets_exists_and_is_full(lex):
    v = _budgeted(lex, "enriched", "fg3", "1", "content_min3_nostop", 100)
    assert v["n_unique_subsamples"] == 10
    assert v["jaccard"]["n_values"] == 10
    for sp, offs in v["offsets_used"].items():
        assert len(set(offs)) == 10, sp


def test_single_feasible_offset_is_handled(lex):
    """
    No real session degenerates this far — the observed minimum is 3 — so the boundary
    is exercised directly on the production functions rather than asserted from data
    that cannot reach it.
    """
    import lexical_analysis as lx
    assert lx._offsets(100, 100, 10) == [0]          # exactly one window fits
    assert lx._max_unique_offsets(100, 100, 10) == 1
    assert lx._offsets(101, 100, 10) == [0, 1]       # two positions only
    # tokens must clear the tokeniser's minimum length or they are filtered out and the
    # budget becomes infeasible
    turns = [{"role": "participant", "speaker": "a",
              "text": " ".join(f"aaa{i}" for i in range(100))},
             {"role": "participant", "speaker": "b",
              "text": " ".join(f"bbb{i}" for i in range(100))}]
    v = lx._budgeted_overlap(turns, lx.TOKENISERS["all_min3_withstop"], 100)
    assert v is not None
    assert v["n_unique_subsamples"] == 1
    assert v["n_requested_subsamples"] == 10
    assert v["jaccard"]["n_values"] == 1
    assert v["jaccard"]["sd_across_unique_windows"] is None
    observed = {x["budgeted"][a][b]["n_unique_subsamples"]
                for x in lex["per_session"] for a in x["budgeted"]
                for b in x["budgeted"][a] if x["budgeted"][a][b]}
    assert min(observed) >= 2, f"a real session degenerated to {min(observed)}"


def test_window_spread_is_not_treated_as_independent_observations(lex):
    for s in lex["per_session"]:
        for arm, by in s["budgeted"].items():
            for b, v in by.items():
                if v is None:
                    continue
                assert "NOT independent" in v["independence_note"]
                assert "no CI" in v["independence_note"]
                assert "windows_overlap_per_speaker" in v
                # no inferential quantity may be emitted from the window spread. Check
                # KEYS, not substrings: the note itself contains the letters "ci".
                for m in ("jaccard", "jensen_shannon_distance", "cosine_similarity"):
                    keys = set(v[m])
                    assert keys == {"mean", "sd_across_unique_windows", "min", "max",
                                    "n_values"}, (m, keys)
                    for k in keys:
                        assert not any(bad in k.lower() for bad in
                                       ("ci_", "conf", "pval", "p_value", "stderr",
                                        "sem", "tstat")), (m, k)


def test_budget_design_is_deterministic_and_feasibility_gated(lex):
    b = lex["budget_design"]
    assert b["budgets_tokens"] == [100, 200, 400]
    assert b["n_subsamples"] == 10
    assert "no RNG" in b["subsample_scheme"]
    assert "EVERY compared participant" in b["feasibility_rule"]
    assert len(b["tokenisation_arms"]) == 3
    for m in ("jaccard", "jensen_shannon_distance", "cosine_similarity"):
        assert m in b["measures"]


def test_thin_specifications_cannot_carry_the_verdict(lex):
    """
    Budgets above ~100 tokens are feasible for only one human focus group. Those
    specifications compare 1 human FG against 5 synthetic FGs and must be excluded from
    the verdict, not counted toward it.
    """
    v = lex["sensitivity_verdict"]
    assert v["decisive_specifications_require"] == "n_fg == 5 in every condition"
    assert v["n_excluded_thin"] > 0
    for key, rec in v["per_specification"].items():
        assert all(n == 5 for n in rec["n_fg"].values()), key
    for key, rec in v["excluded_thin_specifications"].items():
        assert min(rec["n_fg"].values()) < 5, key
    assert v["n_specifications"] + v["n_excluded_thin"] == \
        len(lex["summary"]["budget_equalised"])


def test_verdict_direction_logic_is_correct_per_measure(lex):
    """
    Jaccard and cosine rise with similarity; Jensen-Shannon distance falls with it. A
    single direction rule across all three would invert one of them.
    """
    both = {**lex["sensitivity_verdict"]["per_specification"],
            **lex["sensitivity_verdict"]["excluded_thin_specifications"]}
    for key, rec in both.items():
        measure = key.split("::")[1]
        e, d = rec["enriched_minus_human"], rec["demo_minus_human"]
        expected = (e < 0 and d < 0) if measure == "jensen_shannon_distance" \
            else (e > 0 and d > 0)
        assert rec["synthetic_less_distinct_than_human"] is expected, key


def test_unadjusted_diagnostic_is_labelled_confounded(lex):
    assert "partly measures output" in lex["confound_addressed"]
    for name, s in lex["summary"]["unadjusted_jaccard"].items():
        for c in ("human", "enriched", "demographics-only"):
            assert s[c]["n_fg"] == 5, f"{name}/{c}"


def test_budget_equalisation_shrinks_the_gap(lex):
    """
    If equalising tokens did not change the gap at all, the budget machinery would be
    doing nothing and the confound claim would be idle.
    """
    un = lex["summary"]["unadjusted_jaccard"]["content_min3_nostop"]
    eq = lex["summary"]["budget_equalised"]["content_min3_nostop@100::jaccard"]
    assert eq["enriched_minus_human"] < un["enriched_minus_human"]
    assert eq["demo_minus_human"] < un["demo_minus_human"]


def test_mattr_is_reported_at_three_windows_and_correctly_described(lex):
    for w in (50, 100, 200):
        assert f"mattr_w{w}" in lex["diversity"]
        for c in ("human", "enriched", "demographics-only"):
            assert lex["diversity"][f"mattr_w{w}"][c]["n_fg"] == 5
    note = lex["diversity_note"]
    assert "LESS length-sensitive" in note
    assert "not\nlength-insensitive" in note or "not length-insensitive" in note
    assert "NOT evidence about voice distinctiveness" in note


def test_numeral_proxy_does_not_discharge_the_registry_indicator(lex):
    n = lex["numeral_proxy_note"]
    assert "PROXY only" in n
    assert "does NOT discharge" in n
    assert "NOT_IN_REPORTED_INSTRUMENT" in n


def test_fg_is_the_unit_of_analysis(lex):
    assert "focus group" in lex["unit_of_analysis"]
    for group in ("unadjusted_jaccard", "budget_equalised"):
        for name, s in lex["summary"][group].items():
            for c in ("human", "enriched", "demographics-only"):
                assert len(s[c]["fg_means"]) == s[c]["n_fg"], f"{name}/{c}"
