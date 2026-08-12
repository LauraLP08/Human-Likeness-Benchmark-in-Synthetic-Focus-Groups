"""
Aggregation for the Macho Meals production evaluation — PREPARED, NOT RUN.

Reads Tier-1 results from the pipeline's evaluator cache and rolls them up at four
levels. Run with `--emit-empty` it writes the tables with headers and zero rows, so
the schema is fixed and reviewable before any scoring exists.

AGGREGATION LEVELS
  1. session          one synthetic run vs the single human transcript for its FG
  2. group            FG x condition over the 3 canonical replicates — individual
                      values retained, then mean/median/SD/min-max
  2b. paired effect   enriched minus demographics-only, per FG
  3. study replicate  five groups assembled by canonical_replication_index
  4. condition        across the 3 study replicates

COMPLETENESS IS A HARD GATE, NOT A WARNING
An incomplete OR unexpected corpus cannot produce a summary. `assert_complete`
requires exactly 5 human transcripts and exactly 30 synthetic runs; 3 runs per
FG x condition with indices [1,2,3]; 5 FGs per study replicate; 3 study replicates
per condition; every synthetic FG paired to a human transcript. It also rejects any
FG, condition or replication index outside the frozen design, and enforces
uniqueness of physical runs, (condition, FG, index) cells, human FGs and cache keys.
Per-cell counting alone is not enough: 30 rows that are really 29 runs plus a
duplicate would fill every cell correctly while not being the frozen corpus.

ZERO IS A MEASUREMENT; MISSING IS NOT
`f1_score` returns None only when recall or precision could not be computed at all
(empty denominator). Two non-empty but disjoint code sets give recall 0.0,
precision 0.0 and F1 0.0 — a measured total mismatch, not a missing measurement.
Likewise `_rate` returns None on a genuinely zero denominator instead of clamping
it to 1, which would turn "nothing was observed" into a confident 0.0 or 1.0.

STRUCTURAL METRICS HAVE A SOURCE
`structural_interaction_metrics_long.csv` is computed by `compute_structural_metrics`
from the same comparable-window transcript the evaluator was given. It is arithmetic
over turns and words — no evaluator, no API call. If that transcript cannot be
read, aggregation raises rather than emitting the table with a header and no rows.

EVERY DECLARED COLUMN IS POPULATED
A header that is never filled is worse than an absent one: it looks like a measured
quantity. Theme-level metrics, window counts, study-replicate F1/reach/distinct
subthemes and `participants_n` are all computed here.

POOLED SD
`within_cell_sd_pooled` is the variance-weighted pooled SD with degrees of freedom,
sqrt( ((n1-1)s1^2 + (n2-1)s2^2) / (n1+n2-2) ) — not the mean of two SDs, which is
not a pooled estimator. The standardised effect is emitted only when that pooled SD
is defined and non-zero.

DISCIPLINE ENCODED HERE, NOT LEFT TO THE WRITE-UP
  * FG is the primary comparative unit; runs are nested within FG x condition.
  * Replicates estimate GENERATOR variability — never independent focus groups, and
    the 15 transcripts of a condition are never concatenated against 5 humans.
  * Recall and precision are emitted separately and before F1; the F1 column is
    named `tier1_f1_secondary`.
  * `_comparable_window` and `_full_run_operational` never share a table.
  * Reach carries the engagement-path caveat wherever it appears.
  * `tier1_salience_hierarchy` uses only codes that are present, quote-verified and
  carry a non-null reach on both sides. A missing reach is never read as 0.0; the
  excluded counts and an explicit undefinition reason are separate columns.
* Interpretive metrics have no column until the gold standard returns.

No API call. Nothing writes to `output/session_logs/`.

Usage:
    py scripts/aggregate_production_results.py --emit-empty
    py scripts/aggregate_production_results.py            # once results exist
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_CACHE = _OUT / "evaluator_cache"
_RESULTS = _OUT / "results"

REACH_CAVEAT = ("14 canonical enriched runs executed the pre-fix engagement path; "
                "reach depends on who spoke — see frozen_evaluation_spec.md §9")

EXPECTED_HUMAN_TRANSCRIPTS = 5
EXPECTED_SYNTHETIC_RUNS = 30
EXPECTED_RUNS_PER_GROUP_CONDITION = 3
EXPECTED_FGS_PER_STUDY_REPLICATE = 5
EXPECTED_STUDY_REPLICATES_PER_CONDITION = 3
CONDITIONS = ("enriched", "demographics-only")
FGS = ("fg1", "fg2", "fg3", "fg4", "fg5")


class IncompleteCorpusError(RuntimeError):
    """Raised when the result set cannot support the declared aggregation levels."""


SCHEMAS: dict[str, list[str]] = {
    "per_run_metrics.csv": [
        "physical_run", "condition", "fg", "canonical_replication_index",
        "namespace", "human_present_n", "synthetic_present_n", "shared_n",
        "tier1_subtheme_recall", "tier1_matched_theme_precision", "tier1_f1_secondary",
        "tier1_theme_level_recall", "tier1_theme_level_precision",
        "tier1_participant_reach", "tier1_salience_hierarchy",
        "tier1_salience_hierarchy_n_shared", "tier1_salience_hierarchy_n_excluded",
        "tier1_salience_hierarchy_n_excluded_unverified",
        "tier1_salience_hierarchy_n_excluded_reach_missing",
        "tier1_salience_hierarchy_undefined_reason",
        "length_ratio_synthetic_to_human",
        "participants_n", "reach_implementation_caveat",
        "quote_verification_rate", "code_preservation_rate", "demoted_codes",
        "window_words", "window_participant_turns", "window_moderator_turns",
        "transcript_sha256", "cache_key",
    ],
    "per_group_condition_summary.csv": [
        "fg", "condition", "n_replicates", "namespace",
        "recall_values", "recall_mean", "recall_median", "recall_sd",
        "recall_min", "recall_max",
        "precision_values", "precision_mean", "precision_median", "precision_sd",
        "precision_min", "precision_max",
        "f1_secondary_values", "f1_secondary_mean",
        "reach_values", "reach_mean", "reach_implementation_caveat",
        "human_present_n", "participants_n",
    ],
    "group_level_paired_effects.csv": [
        "fg", "metric", "namespace",
        "enriched_n", "demographics_only_n",
        "enriched_mean", "demographics_only_mean", "difference_enriched_minus_demo",
        "enriched_sd", "demographics_only_sd",
        "within_cell_sd_pooled", "difference_over_pooled_sd",
        "favours", "note",
    ],
    "study_replication_summary.csv": [
        "study_replicate", "condition", "namespace", "n_fgs", "fgs_included",
        "recall_mean_across_5_fgs", "precision_mean_across_5_fgs",
        "f1_secondary_mean", "reach_mean", "reach_implementation_caveat",
        "distinct_subthemes_across_study", "distinct_subtheme_ids", "note",
    ],
    "condition_level_summary.csv": [
        "condition", "namespace", "n_study_replicates",
        "recall_mean", "recall_sd", "recall_min", "recall_max",
        "precision_mean", "precision_sd", "precision_min", "precision_max",
        "between_replicate_variation_note",
    ],
    "condition_comparison.csv": [
        "metric", "namespace", "n_fgs_compared",
        "n_fgs_favouring_enriched", "n_fgs_favouring_demographics_only", "n_ties",
        "fgs_favouring_enriched", "mean_difference_enriched_minus_demo", "note",
    ],
    "thematic_code_presence_long.csv": [
        "side", "physical_run", "condition", "fg", "canonical_replication_index",
        "subtheme_id", "parent_theme", "present", "quote_verified",
        "n_verified_quotes", "voiced_by_n", "namespace",
    ],
    "thematic_reach_long.csv": [
        "side", "physical_run", "condition", "fg", "canonical_replication_index",
        "subtheme_id", "voiced_by_n", "participants_n", "reach",
        "implementation_caveat", "namespace",
    ],
    "structural_interaction_metrics_long.csv": [
        "side", "physical_run", "condition", "fg", "canonical_replication_index",
        "metric_id", "registry_status", "value", "numerator", "denominator",
        "namespace", "caveat",
    ],
    "structural_distributions_long.csv": [
        "side", "physical_run", "condition", "fg", "canonical_replication_index",
        "distribution_id", "element_index", "element_label", "value",
        "supports_metric", "namespace",
    ],
}

_EMERGENT_JSON_SKELETON = {
    "_schema": {
        "description": ("Themes not observed in the paired human transcript, and human "
                        "themes not observed in the synthetic window. Reported as NOT "
                        "OBSERVED — never as false, hallucinated or invalid."),
        "namespace": "_comparable_window",
        "record": {
            "fg": "fg1..fg5", "condition": "enriched | demographics-only",
            "physical_run": "run directory name",
            "canonical_replication_index": "1|2|3",
            "direction": ("synthetic_only_not_observed_in_human | "
                          "human_only_missed_by_synthetic"),
            "theme_label": "", "participant_count": "evidence-constrained",
            "verified_quotes": [], "single_voice_flag": "participant_count <= 1",
        },
    },
    "records": [],
}


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _sd(values: list[float]) -> float | None:
    return round(statistics.stdev(values), 4) if len(values) > 1 else None


def _rate(numerator: float | None, denominator: float | None,
          ndigits: int | None = 4) -> float | None:
    """
    A rate with a real denominator of zero is UNDEFINED, not zero.

    Clamping the denominator (`max(1, n)`) invents an observation that was never
    made and turns "we measured nothing" into a confident-looking 0.0 or 1.0.
    """
    if numerator is None or denominator is None or denominator == 0:
        return None
    q = numerator / denominator
    return q if ndigits is None else round(q, ndigits)


def f1_score(recall: float | None, precision: float | None,
             ndigits: int | None = 4) -> float | None:
    """
    F1 is None only when one of its inputs is undefined — i.e. when recall or
    precision had an empty denominator and could not be computed at all.

    When both ARE defined but the code sets are disjoint, recall and precision are
    genuinely 0.0 and F1 is genuinely 0.0. Returning None there would report a
    measured total mismatch as a missing measurement, which is a different and much
    weaker claim.

    `ndigits` mirrors `_rate`: 4 for tables, `None` for downstream arithmetic. The
    formula lives here only. Rounding F1 before it reaches the effect calculation
    would decide F1 signs and ties on 4-dp values, exactly the defect corrected for
    recall, precision and reach.
    """
    if recall is None or precision is None:
        return None
    if recall + precision == 0:
        return 0.0
    f1 = 2 * recall * precision / (recall + precision)
    return f1 if ndigits is None else round(f1, ndigits)


def pooled_sd(a: list[float], b: list[float]) -> float | None:
    """
    Variance-weighted pooled SD with degrees of freedom:
        sqrt( ((n1-1)s1^2 + (n2-1)s2^2) / (n1+n2-2) )
    Undefined unless both groups have n >= 2. Averaging two SDs is not a pooled
    estimator and is not used.
    """
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return None
    v1, v2 = statistics.variance(a), statistics.variance(b)
    denom = n1 + n2 - 2
    if denom <= 0:
        return None
    return round(math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / denom), 4)


def unrounded_run_metrics(human_rec: dict, synth_rec: dict) -> dict:
    """
    Session metrics at FULL precision, using the same definitions `aggregate()` uses.

    `aggregate()` rounds to 4 dp for its tables, which is right for presentation and
    wrong for arithmetic done downstream. Differencing two 4-dp means and then
    rounding again decides signs and ties on twice-rounded numbers: a true difference
    below 5e-5 could be recorded as an exact tie it is not.

    This shares `_present_set`, `_participants_n` and `_rate` with the table path, so
    the definitions cannot drift apart — only the rounding differs.
    """
    hp, sp = _present_set(human_rec), _present_set(synth_rec)
    shared = hp & sp
    reaches = [c.get("reach", 0.0) for c in synth_rec["tier1"]["codes"]
               if c.get("present") and c.get("quote_verified")]
    return {
        "recall": _rate(len(shared), len(hp), ndigits=None),
        "precision": _rate(len(shared), len(sp), ndigits=None),
        "reach": (sum(reaches) / len(reaches)) if reaches else None,
        "f1_secondary": f1_score(_rate(len(shared), len(hp), ndigits=None),
                                 _rate(len(shared), len(sp), ndigits=None),
                                 ndigits=None),
        "human_present_n": len(hp), "synthetic_present_n": len(sp),
        "shared_n": len(shared),
    }


def _parent(subtheme_id: str) -> str:
    return subtheme_id.split(".")[0] if "." in subtheme_id else subtheme_id[:1]


EVALUATION_EXECUTION_MODE = "batch"


def load_results() -> list[dict]:
    """
    The evaluation corpus: COMPLETE results from ONE execution mode.

    The cache also holds synchronous results (two human FG1 evaluations produced
    during the preflight investigation). Loading everything would put 37 records in
    front of a gate expecting 35, and would pool two serving paths inside a single
    comparison. Execution mode is part of the keyed configuration precisely so this
    filter can be exact rather than approximate.

    Incomplete results never reach here — they are quarantined, not cached.
    """
    if not _CACHE.exists():
        return []
    out = []
    for p in sorted(_CACHE.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        eff = rec.get("effective_request_config") or {}
        if eff.get("execution_mode") != EVALUATION_EXECUTION_MODE:
            continue
        if (rec.get("completeness") or {}).get("status") not in (None, "COMPLETE"):
            continue
        out.append(rec)
    return out



# ---------------------------------------------------------------------------
# Structural / interaction metrics
#
# Metric IDs here are IDENTICAL to `metric_registry.csv`. Anything this module
# emits that is NOT a frozen registry ID is listed in DERIVED_SUPPORT_METRICS with
# the registry metric it supports, so a reader can tell a frozen measure from a
# convenience count at a glance.
#
# All of it is arithmetic over turns and words — no evaluator, no API call.
# ---------------------------------------------------------------------------

SHORT_TURN_THRESHOLDS = (25, 10, 50)   # 25 = frozen primary; 10/50 = sensitivities

# Emitted by this module but not frozen registry IDs. Each is a raw input to a
# registry metric, retained so the registry value can be recomputed by hand.
DERIVED_SUPPORT_METRICS = {
    "participant_turns": "denominator of short_turn_proportion_*, reference_density",
    "moderator_turns": "numerator of moderator_turn_share",
    "participant_words": "denominator of word_balance_gini",
    "total_words": "denominator of moderator_word_share",
    "chain_depth_max": "the maximum the registry requires alongside chain_depth's mean",
    "chain_depth_n_chains": "denominator of chain_depth",
    "reference_density_ambiguous_names_excluded": (
        "roster names dropped as ambiguous — reference_density is a LOWER BOUND "
        "whenever this is > 0"),
}

# Distributions the registry requires be reported alongside a summary statistic
# ("report the full distribution", "also report the raw per-participant vector",
# "report the distribution and the maximum"). Retained per run in
# structural_distributions_long.csv so no summary stands unaudited.
DISTRIBUTIONS_REQUIRED_BY_REGISTRY = {
    "words_per_turn": "words_per_turn_median, words_per_turn_iqr",
    "participant_turn_counts": "turn_balance_gini",
    "participant_word_counts": "word_balance_gini",
    "chain_depth": "chain_depth",
}

# First names that are also ordinary English words. Token-equality matching alone
# cannot separate the participant Will from the modal verb "will", so these are
# excluded from reference_density rather than guessed at. Exclusion is counted and
# reported, which makes the metric a conservative lower bound instead of a silently
# inflated one.
AMBIGUOUS_FIRST_NAMES = {
    "will", "mark", "bill", "art", "may", "june", "april", "august", "grace",
    "hope", "faith", "joy", "rose", "daisy", "dawn", "summer", "sunny", "frank",
    "rich", "chase", "drew", "sky", "star", "angel", "earl", "duke", "king",
    "guy", "max", "don", "van", "lane", "reed", "brook", "gene", "jack", "bob",
    "pat", "rob", "ray", "wade", "cliff", "dale", "glen", "heath", "miles",
    "penny", "sage", "scout", "trace", "ash", "bear", "buck", "colt", "dot",
}

_WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")


def _tokens(text: str) -> list[str]:
    """Lowercase word tokens with possessive clitics stripped ("bob's" -> "bob")."""
    return [t[:-2] if t.endswith("'s") else t for t in _WORD_RE.findall(text.lower())]


def _gini(values: list[float]) -> float | None:
    """Concentration across participants. Undefined for <2 speakers or zero total."""
    n = len(values)
    if n < 2:
        return None
    total = sum(values)
    if total == 0:
        return None
    ordered = sorted(values)
    weighted = sum((i + 1) * v for i, v in enumerate(ordered))
    return round((2 * weighted - (n + 1) * total) / (n * total), 4)


def _ranks(values: list[float]) -> list[float]:
    """Average ranks, so ties do not create a spurious ordering."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(x: list[float], y: list[float]) -> tuple[float | None, str]:
    """
    Spearman rank correlation, with the undefinition rules stated rather than
    implied. Returns (rho, reason) — reason is "" when rho is defined.

      * fewer than 2 shared observations   -> None ("n<2"): a single pair has no
        ranking to correlate, and returning 0.0 would read as "no relationship".
      * either vector completely tied      -> None ("no_variance"): the Spearman
        denominator is 0; the correlation does not exist.
    """
    if len(x) != len(y):
        raise ValueError("spearman: vectors of different length")
    if len(x) < 2:
        return None, "n<2"
    rx, ry = _ranks(x), _ranks(y)
    if len(set(rx)) == 1 or len(set(ry)) == 1:
        return None, "no_variance"
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    if den == 0:
        return None, "no_variance"
    return round(num / den, 4), ""


def salience_hierarchy(human_result: dict, synth_result: dict) -> dict:
    """
    tier1_salience_hierarchy — Spearman between human and synthetic reach vectors.

    ELIGIBILITY IS STRICT. A subtheme enters the correlation only if, on BOTH sides,
    it is present=true AND quote_verified=true AND carries a non-null reach.

      * unverified codes are excluded because reach is only meaningful over
        quote-verified evidence — the same rule tier1_participant_reach uses;
      * a missing reach is NOT read as 0.0. Absent evidence and evidence of zero
        breadth are different claims, and coercing one into the other silently
        moves a subtheme to the bottom of the ranking.

    Returns a dict with the correlation, the shared n, the number of codes dropped
    at each stage, and an explicit reason whenever rho cannot be computed.
    """
    def eligible(res):
        keep, dropped = {}, {"not_present": 0, "not_quote_verified": 0, "reach_missing": 0}
        for c in res["tier1"]["codes"]:
            if not c.get("present"):
                dropped["not_present"] += 1
                continue
            if not c.get("quote_verified"):
                dropped["not_quote_verified"] += 1
                continue
            if c.get("reach") is None:
                dropped["reach_missing"] += 1
                continue
            keep[c["subtheme_id"]] = c["reach"]
        return keep, dropped

    hm, hdrop = eligible(human_result)
    sm, sdrop = eligible(synth_result)
    shared = sorted(set(hm) & set(sm))
    excluded = {k: hdrop[k] + sdrop[k] for k in hdrop}
    n_excluded = excluded["not_quote_verified"] + excluded["reach_missing"]

    out = {
        "rho": None, "n_shared": len(shared),
        "n_excluded_unverified": excluded["not_quote_verified"],
        "n_excluded_reach_missing": excluded["reach_missing"],
        "n_excluded_total": n_excluded,
        "undefined_reason": "",
    }
    if len(shared) < 2:
        out["undefined_reason"] = (
            f"fewer_than_2_shared_eligible_subthemes (n={len(shared)}; "
            f"{n_excluded} code(s) excluded as unverified or reach-missing)")
        return out
    rho, reason = spearman([hm[s] for s in shared], [sm[s] for s in shared])
    out["rho"] = rho
    if rho is None:
        out["undefined_reason"] = ("reach_ranks_fully_tied — the Spearman "
                                   "denominator is 0, so no correlation exists")
    return out


def _is_moderator(entry: dict) -> bool:
    return str(entry.get("speaker_id", "")).upper() == "MODERATOR"


def compute_structural_metrics(entries: list[dict]) -> dict[str, list[dict]]:
    """
    Registry-aligned structural and interaction metrics over one comparable window.

    Returns {"metrics": [...], "distributions": [...]}. A metric whose denominator
    is genuinely zero yields value None — never 0.0.
    """
    entries = blind_included_entries(entries)      # same rule as every other count
    mods = [e for e in entries if _is_moderator(e)]
    parts = [e for e in entries if not _is_moderator(e)]
    p_words = [len(str(e.get("content", "")).split()) for e in parts]
    m_words = [len(str(e.get("content", "")).split()) for e in mods]
    total_turns, total_words = len(entries), sum(p_words) + sum(m_words)

    # Stable anonymous labels by first appearance — the audit table must never
    # carry participant names, least of all from the human transcripts.
    order: list[str] = []
    by_speaker: dict[str, list[int]] = {}
    for e, w in zip(parts, p_words):
        key = str(e.get("speaker_name") or e.get("speaker_id"))
        if key not in by_speaker:
            by_speaker[key] = []
            order.append(key)
        by_speaker[key].append(w)
    labels = {k: f"Participant {i + 1}" for i, k in enumerate(order)}
    turn_counts = [len(by_speaker[k]) for k in order]
    word_counts = [sum(by_speaker[k]) for k in order]

    flags = [not _is_moderator(e) for e in entries]
    adjacent = sum(1 for i in range(1, len(flags)) if flags[i] and flags[i - 1])
    chains, run = [], 0
    for f in flags:
        if f:
            run += 1
        elif run:
            chains.append(run); run = 0
    if run:
        chains.append(run)

    # --- reference_density -------------------------------------------------
    # Token equality, not substring: "same" must not match Sam, "start" must not
    # match Art. Names that are ordinary words are excluded outright.
    firsts, ambiguous = {}, []
    for key in order:
        first = key.split()[0].lower() if key.split() else ""
        if not first or len(first) < 3:
            continue
        if first in AMBIGUOUS_FIRST_NAMES:
            ambiguous.append(first)
            continue
        firsts[key] = first
    refs = 0
    for e in parts:
        me = str(e.get("speaker_name") or e.get("speaker_id"))
        toks = set(_tokens(str(e.get("content", ""))))
        if any(fn in toks for k, fn in firsts.items() if k != me):
            refs += 1

    def rec(mid, value, num, den, caveat=""):
        return {"metric_id": mid, "value": value, "numerator": num,
                "denominator": den, "caveat": caveat}

    q = statistics.quantiles(p_words, n=4) if len(p_words) >= 4 else None
    metrics = [
        rec("words_per_turn_median",
            round(statistics.median(p_words), 4) if p_words else None, None, len(parts),
            "report with IQR and the full distribution; never the mean alone"),
        rec("words_per_turn_iqr",
            round(q[2] - q[0], 4) if q else None, None, len(parts)),
    ]
    for thr in SHORT_TURN_THRESHOLDS:
        n = sum(1 for w in p_words if w < thr)
        metrics.append(rec(
            f"short_turn_proportion_{thr}w", _rate(n, len(p_words)), n, len(p_words),
            "" if thr == 25 else f"sensitivity variant of the frozen 25-word threshold"))
    metrics += [
        rec("turn_balance_gini", _gini([float(c) for c in turn_counts]), None, len(parts),
            "raw per-participant turn vector retained in structural_distributions_long"),
        rec("word_balance_gini", _gini([float(c) for c in word_counts]), None, sum(p_words),
            "raw per-participant word vector retained in structural_distributions_long"),
        rec("moderator_turn_share", _rate(len(mods), total_turns), len(mods), total_turns,
            "affected by the sub-entry Q1 boundary: the dropped prefix is moderator text"),
        rec("moderator_word_share", _rate(sum(m_words), total_words), sum(m_words), total_words,
            "affected by the sub-entry Q1 boundary: the dropped prefix is moderator text"),
        rec("participant_participant_adjacency",
            _rate(adjacent, max(0, total_turns - 1)), adjacent, max(0, total_turns - 1)),
        rec("reference_density", _rate(refs, len(parts)), refs, len(parts),
            "DIAGNOSTIC. Explicit first-name token match on the run roster only: misses "
            "pronominal, positional and indirect reference, so it understates real "
            "referencing. "
            + (f"LOWER BOUND — {len(ambiguous)} ambiguous roster name(s) excluded: "
               f"{sorted(set(ambiguous))}." if ambiguous
               else "No roster name required exclusion.")),
        rec("chain_depth",
            round(statistics.mean(chains), 4) if chains else None, None, len(chains),
            "mean; the maximum and the full distribution are reported alongside"),
        # --- derived support (not frozen registry IDs) ---
        rec("participant_turns", len(parts), len(parts), None),
        rec("moderator_turns", len(mods), len(mods), None),
        rec("participant_words", sum(p_words), sum(p_words), None),
        rec("total_words", total_words, total_words, None),
        rec("chain_depth_max", max(chains) if chains else None, None, len(chains)),
        rec("chain_depth_n_chains", len(chains), len(chains), None),
        rec("reference_density_ambiguous_names_excluded", len(ambiguous), len(ambiguous), None,
            f"excluded: {sorted(set(ambiguous))}" if ambiguous else ""),
    ]

    # --- distributions the registry requires be retained --------------------
    dists: list[dict] = []
    for i, (e, w) in enumerate(zip(parts, p_words)):
        dists.append({"distribution_id": "words_per_turn", "element_index": i,
                      "element_label": labels[str(e.get("speaker_name") or e.get("speaker_id"))],
                      "value": w})
    for i, k in enumerate(order):
        dists.append({"distribution_id": "participant_turn_counts", "element_index": i,
                      "element_label": labels[k], "value": turn_counts[i]})
        dists.append({"distribution_id": "participant_word_counts", "element_index": i,
                      "element_label": labels[k], "value": word_counts[i]})
    for i, c in enumerate(chains):
        dists.append({"distribution_id": "chain_depth", "element_index": i,
                      "element_label": f"chain {i + 1}", "value": c})

    return {"metrics": metrics, "distributions": dists}


def _window_entries(rec: dict) -> list[dict] | None:
    """Entries injected by tests, else the exact file the evaluator was given."""
    inp = rec["input"]
    if inp.get("window_entries") is not None:
        return inp["window_entries"]
    if not inp.get("path"):
        return None
    fp = _REPO_ROOT / inp["path"]
    if not fp.exists():
        return None
    payload = json.loads(fp.read_text(encoding="utf-8"))
    return payload["transcript"] if isinstance(payload, dict) else payload


def blind_included_entries(entries: list[dict]) -> list[dict]:
    """
    Exactly the entries `to_blind_text` renders: non-empty content only.

    The evaluator never saw an empty turn, so it must not appear in a window count
    either. (In the present corpus there are zero empty entries, so this filter
    changes no current value — it is here so the rule cannot drift.)
    """
    return [e for e in entries if (e.get("content") or "").strip()]


def window_counts(entries: list[dict]) -> dict:
    """
    THE window counter. One function, used by every window figure.

    `window_words` here is the same number `length_ratio_synthetic_to_human`
    divides, because the ratio calls this function too. Two separate word counts —
    one for the column, one for the ratio — is exactly how a tokenisation
    discrepancy gets into a table and is never noticed.
    """
    inc = blind_included_entries(entries)
    return {
        "window_words": sum(len(str(e.get("content", "")).split()) for e in inc),
        "window_participant_turns": sum(1 for e in inc if not _is_moderator(e)),
        "window_moderator_turns": sum(1 for e in inc if _is_moderator(e)),
        "window_entries_included": len(inc),
        "window_entries_skipped_empty": len(entries) - len(inc),
    }


def _window_counts_for(rec: dict) -> dict | None:
    """
    Counts derived from `input.path` — the transcript this result was actually
    computed from.

    Batch cache records carry no `input.window_counts`; reading that key left
    window_words, window_participant_turns and window_moderator_turns blank on all
    30 session rows. Deriving from the recorded path cannot go stale, and it points
    at the comparable window for synthetic inputs because that is what the path is.
    """
    entries = _window_entries(rec)
    return None if entries is None else window_counts(entries)


def _window_word_count(rec: dict) -> int | None:
    counts = _window_counts_for(rec)
    return None if counts is None else counts["window_words"]

def assert_complete(results: list[dict]) -> None:
    """
    Hard gate. An incomplete OR unexpected set cannot produce summaries.

    Checks totals, membership and uniqueness — not just per-cell counts. Counting
    only within expected cells would let a stray FG, a misspelt condition or a
    duplicated run pass unnoticed: the 30 cells would each look right while the
    corpus was not the frozen one.
    """
    problems: list[str] = []
    sides = {r["input"]["side"] for r in results}
    if sides - {"human", "synthetic"}:
        problems.append(f"unexpected side values: {sorted(sides - {'human', 'synthetic'})}")

    humans = [r for r in results if r["input"]["side"] == "human"]
    synth = [r for r in results if r["input"]["side"] == "synthetic"]

    # --- totals -------------------------------------------------------------
    if len(humans) != EXPECTED_HUMAN_TRANSCRIPTS:
        problems.append(f"human transcripts: {len(humans)} — expected exactly "
                        f"{EXPECTED_HUMAN_TRANSCRIPTS}")
    if len(synth) != EXPECTED_SYNTHETIC_RUNS:
        problems.append(f"synthetic runs: {len(synth)} — expected exactly "
                        f"{EXPECTED_SYNTHETIC_RUNS}")

    # --- membership: nothing outside the frozen design ----------------------
    bad_fg = sorted({r["input"]["fg"] for r in results} - set(FGS))
    if bad_fg:
        problems.append(f"unexpected FG identifiers: {bad_fg} — expected {list(FGS)}")
    bad_cond = sorted({r["input"]["condition"] for r in synth} - set(CONDITIONS))
    if bad_cond:
        problems.append(f"unexpected conditions: {bad_cond} — expected {list(CONDITIONS)}")
    bad_idx = sorted(
        {r["input"]["canonical_replication_index"] for r in synth} - {1, 2, 3},
        key=str)
    if bad_idx:
        problems.append(f"unexpected canonical_replication_index values: {bad_idx} "
                        f"— expected [1, 2, 3]")
    stray_idx = [r["input"].get("physical_run") for r in humans
                 if r["input"].get("canonical_replication_index") is not None]
    if stray_idx:
        problems.append(f"human results carrying a replication index: {stray_idx}")

    # --- uniqueness ---------------------------------------------------------
    human_fgs = [r["input"]["fg"] for r in humans]
    if len(set(human_fgs)) != len(human_fgs):
        dupes = sorted({f for f in human_fgs if human_fgs.count(f) > 1})
        problems.append(f"duplicate human transcripts for FG(s): {dupes}")
    runs = [r["input"].get("physical_run") for r in synth]
    if None in runs:
        problems.append("synthetic result(s) with no physical_run identifier")
    named = [x for x in runs if x is not None]
    if len(set(named)) != len(named):
        dupes = sorted({x for x in named if named.count(x) > 1})
        problems.append(f"duplicate physical_run identifiers: {dupes}")
    cells = [(r["input"]["condition"], r["input"]["fg"],
              r["input"]["canonical_replication_index"]) for r in synth]
    if len(set(cells)) != len(cells):
        dupes = sorted({c for c in cells if cells.count(c) > 1}, key=str)
        problems.append(f"duplicate (condition, fg, replication index) cells: {dupes}")
    keys = [r.get("cache_key") for r in results if r.get("cache_key")]
    if len(set(keys)) != len(keys):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        problems.append(f"duplicate cache keys — same evaluation counted twice: {dupes}")

    # --- per-cell and per-replicate structure -------------------------------
    for cond in CONDITIONS:
        for fg in FGS:
            rows = [r for r in synth
                    if r["input"]["condition"] == cond and r["input"]["fg"] == fg]
            if len(rows) != EXPECTED_RUNS_PER_GROUP_CONDITION:
                problems.append(f"{cond}/{fg}: {len(rows)} runs — expected "
                                f"{EXPECTED_RUNS_PER_GROUP_CONDITION}")
            idx = sorted((r["input"]["canonical_replication_index"] for r in rows), key=str)
            if idx != [1, 2, 3]:
                problems.append(f"{cond}/{fg}: replication indices {idx} — expected [1, 2, 3]")

    for cond in CONDITIONS:
        reps = sorted({r["input"]["canonical_replication_index"] for r in synth
                       if r["input"]["condition"] == cond}, key=str)
        if reps != [1, 2, 3]:
            problems.append(f"{cond}: study replicates {reps} — expected "
                            f"{EXPECTED_STUDY_REPLICATES_PER_CONDITION} ([1, 2, 3])")
        for rep in (1, 2, 3):
            fgs = sorted({r["input"]["fg"] for r in synth
                          if r["input"]["condition"] == cond
                          and r["input"]["canonical_replication_index"] == rep})
            if len(fgs) != EXPECTED_FGS_PER_STUDY_REPLICATE:
                problems.append(f"{cond}/study replicate {rep}: {len(fgs)} FGs {fgs} "
                                f"— expected {EXPECTED_FGS_PER_STUDY_REPLICATE}")

    # --- every synthetic FG must have its human pair ------------------------
    missing_pair = sorted({r["input"]["fg"] for r in synth} - {r["input"]["fg"] for r in humans})
    if missing_pair:
        problems.append(f"synthetic FGs with no paired human transcript: {missing_pair}")

    if problems:
        raise IncompleteCorpusError(
            "Corpus incomplete or unexpected — refusing to aggregate. A partial or "
            "contaminated set would produce means indistinguishable from complete ones:\n  - "
            + "\n  - ".join(problems))


def _present_set(rec: dict) -> set[str]:
    return {c["subtheme_id"] for c in rec["tier1"]["codes"]
            if c.get("present") and c.get("quote_verified")}


def _participants_n(rec: dict) -> int | None:
    """Participants in the transcript, recovered from any code's reach denominator."""
    for c in rec["tier1"]["codes"]:
        reach, voiced = c.get("reach"), len(c.get("voiced_by") or [])
        if reach and voiced:
            return round(voiced / reach)
    return rec["input"].get("participants_n")



# ---------------------------------------------------------------------------
# Registry parity
#
# Every AUTOMATIC_* metric in metric_registry.csv must be accounted for: either
# this aggregator produces it, or it is produced somewhere else and named here.
# The frozen registry is the authority; silence is not an acceptable answer for a
# metric that was frozen into the specification.
# ---------------------------------------------------------------------------

_REGISTRY_CSV = _OUT / "metric_registry.csv"

# Registry metric -> the per_run_metrics column carrying it. The registry froze the
# id `tier1_f1`; the column is `tier1_f1_secondary` because the reclassification to
# secondary is part of the column name. That divergence is declared, not silent.
REGISTRY_METRIC_COLUMNS = {
    "tier1_subtheme_recall": "tier1_subtheme_recall",
    "tier1_matched_theme_precision": "tier1_matched_theme_precision",
    "tier1_f1": "tier1_f1_secondary",
    "tier1_theme_level_recall": "tier1_theme_level_recall",
    "tier1_theme_level_precision": "tier1_theme_level_precision",
    "tier1_participant_reach": "tier1_participant_reach",
    "tier1_salience_hierarchy": "tier1_salience_hierarchy",
    "length_ratio_synthetic_to_human": "length_ratio_synthetic_to_human",
}

# AUTOMATIC_* registry metrics this aggregator does NOT produce.
#
# Each entry names a VERIFIABLE location: an artifact that exists on disk and the
# column in it that carries the metric. Registry ids and artifact column names
# diverge in several places (the audits were written first), so the mapping is
# recorded rather than assumed — "produced elsewhere" with no file and no column
# is indistinguishable from "forgotten".
#
# status="not_implemented" means exactly that: no producer exists yet. These are
# listed so the parity test reports them every run instead of letting them pass as
# somebody else's problem.
PRODUCED_ELSEWHERE = {
    # D2 diagnostics. The producer exists and is tested, but has NOT been run:
    # it needs Tier-1 results, which the batch has not yet generated. "Producer
    # written" is not "metric produced", and the status says which.
    "tier1_coverage_by_word_count_curve": {
        "status": "producer_ready_not_yet_run",
        "producer": "scripts/d2_length_diagnostics.py",
        "artifact": "results/d2_coverage_by_word_count_curve.csv",
        "column": "cumulative_distinct_subthemes", "namespace": "_comparable_window",
        "note": "Derived from verified quote positions; runs after the batch.",
    },

    "forced_silence_count": {
        "status": "implemented", "artifact": "run_readiness_audit.csv",
        "column": "forced_silences", "namespace": "_full_run_operational",
    },
    "forced_silence_rate": {
        "status": "implemented", "artifact": "run_readiness_audit.csv",
        "column": "forced_silence_rate", "namespace": "_full_run_operational",
    },
    "api_error_rate": {
        "status": "implemented", "artifact": "api_failure_and_fallback_audit.csv",
        "column": "error_rate_of_all_calls", "namespace": "_full_run_operational",
    },
    "response_truncation_rate": {
        "status": "implemented", "artifact": "api_failure_and_fallback_audit.csv",
        "column": "truncation_rate_of_responses", "namespace": "_full_run_operational",
    },
    "full_run_total_words": {
        "status": "implemented", "artifact": "run_readiness_audit.csv",
        "column": "transcript_words", "namespace": "_full_run_operational",
    },

    # Mator et al. (2025) Table 4 comparability layer. AUTOMATIC_PROXY_EXPLORATORY
    # is inside the AUTOMATIC_* family for parity purposes, so these must be
    # declared here or the parity check reports them as frozen-but-unproduced.
    # None of them is produced by this module: two are computed with the
    # `bert-score` package, one is reshaped from this module's own frozen
    # structural output, and one is read from the consensus-dynamics layer.
    "mator_conversational_completeness": {
        "status": "implemented",
        "artifact": "mator_comparable/mator_completeness_by_unit.csv",
        "column": "completeness", "namespace": "_comparable_window",
    },
    "mator_relevance_of_response_bertscore_f1": {
        "status": "implemented", "artifact": "mator_comparable/mator_bertscore_by_unit.csv",
        "column": "relevance_bertscore_f1", "namespace": "_comparable_window",
    },
    "mator_between_participant_similarity_bertscore_f1": {
        "status": "implemented", "artifact": "mator_comparable/mator_bertscore_by_unit.csv",
        "column": "between_participant_bertscore_f1", "namespace": "_comparable_window",
    },
    "mator_agreement_consecutive_turn_similarity": {
        "status": "implemented", "artifact": "mator_comparable/mator_agreement_strict.csv",
        "column": "agreement_strict_R2", "namespace": "_comparable_window",
    },
    "mator_conversational_distribution": {
        "status": "implemented", "artifact": "mator_comparable/mator_bertscore_by_unit.csv",
        "column": "participant_word_shares", "namespace": "_comparable_window",
    },
}

# Metrics the pipeline still EMITS but that the frozen registry has deliberately
# reclassified out of the AUTOMATIC_* family. The column and its values are unchanged and
# still produced; what changed is the evidence class, and with it the metric's standing.
#
# tier1_salience_hierarchy was reclassified to LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC
# because it correlates ranks only over subthemes present on BOTH sides, silently
# dropping every synthetic omission. It is retained as a diagnostic, is never a primary
# result, and is superseded for reporting by the participant-breadth hierarchy.
#
# Declaring it here keeps the AUTOMATIC parity check meaningful: the check compares the
# AUTOMATIC family with what the pipeline claims under that family, and a retained legacy
# diagnostic belongs to neither side of that comparison. Without this declaration the
# check fails on a metric that is behaving exactly as intended.
RETAINED_LEGACY_DIAGNOSTICS = {
    "tier1_salience_hierarchy": {
        "evidence_class": "LEGACY_SHARED-ONLY_AUTOMATIC_DIAGNOSTIC",
        "still_produced": True,
        "values_unchanged": True,
        "is_primary": False,
        "superseded_for_reporting_by":
            "PARTICIPANT_BREADTH_AND_RECURRENCE_HIERARCHY_SIMILARITY",
        "registry_row_retained": True,
    },
}


def automatic_parity_produced() -> set:
    """What the pipeline claims under the AUTOMATIC_* family, for the parity check."""
    return ((structural_registry_metric_ids() | set(REGISTRY_METRIC_COLUMNS))
            - set(RETAINED_LEGACY_DIAGNOSTICS))


# Frozen metrics with no producer anywhere.
UNIMPLEMENTED_REGISTRY_METRICS = frozenset(
    k for k, v in PRODUCED_ELSEWHERE.items() if v["status"] == "not_implemented")

# Registry metrics DEFERRED: specified, not implemented, and NOT approximated under
# their own name. tier1_length_matched_* need each excerpt coded independently
# (~300 evaluator calls, not scheduled). The offline proxies
# evidence_localized_length_matched_* answer a different question and are
# EXPLORATORY, so they are outside the AUTOMATIC_* parity set by construction.
# See frozen_evaluation_spec.md Amendment A1 (2026-07-30).
DEFERRED_REGISTRY_METRICS = {
    "tier1_length_matched_recall": "requires independent coding of each excerpt",
    "tier1_length_matched_precision": "requires independent coding of each excerpt",
}

# Proxies that must NEVER be reported under a deferred metric's name.
PROXY_FOR_DEFERRED = {
    "evidence_localized_length_matched_recall": "tier1_length_matched_recall",
    "evidence_localized_length_matched_precision": "tier1_length_matched_precision",
}


def registry_deferred_metrics() -> set[str]:
    with _REGISTRY_CSV.open(encoding="utf-8-sig", newline="") as fh:
        return {r["metric_id"] for r in csv.DictReader(fh)
                if r["evidence_class"] == "DEFERRED_NOT_IMPLEMENTED"}


def registry_metric_ids() -> set[str]:
    with _REGISTRY_CSV.open(encoding="utf-8-sig", newline="") as fh:
        return {r["metric_id"] for r in csv.DictReader(fh)}

# Frozen metrics whose producer exists and is tested but has NOT been executed, so
# no value exists yet. Kept separate from "implemented" on purpose: parity between
# the registry and the code is NOT evidence that a metric has been computed.
NOT_YET_RUN_REGISTRY_METRICS = frozenset(
    k for k, v in PRODUCED_ELSEWHERE.items()
    if v["status"] == "producer_ready_not_yet_run")


def external_producer_problems() -> list[str]:
    """Check every 'implemented elsewhere' claim against the artifact on disk."""
    problems = []
    for mid, spec in PRODUCED_ELSEWHERE.items():
        if spec["status"] == "producer_ready_not_yet_run":
            if not (_REPO_ROOT / spec["producer"]).exists():
                problems.append(f"{mid}: producer {spec['producer']} does not exist")
            continue
        if spec["status"] != "implemented":
            continue
        path = _OUT / spec["artifact"]
        if not path.exists():
            problems.append(f"{mid}: artifact {spec['artifact']} does not exist")
            continue
        with path.open(encoding="utf-8-sig", newline="") as fh:
            header = next(csv.reader(fh), [])
        if spec["column"] not in header:
            problems.append(
                f"{mid}: column {spec['column']!r} not in {spec['artifact']}")
    return problems


def registry_automatic_metrics() -> dict[str, str]:
    """metric_id -> evidence_class for every AUTOMATIC_* row in the frozen registry."""
    with _REGISTRY_CSV.open(encoding="utf-8-sig", newline="") as fh:
        return {r["metric_id"]: r["evidence_class"] for r in csv.DictReader(fh)
                if r["evidence_class"].startswith("AUTOMATIC")}


def structural_registry_metric_ids() -> set[str]:
    """Registry-id metrics this module emits into the structural table."""
    probe = [{"turn": 0, "speaker_id": "MODERATOR", "speaker_name": "Moderator",
              "content": "a b c"},
             {"turn": 1, "speaker_id": "P1", "speaker_name": "Aaa", "content": "d e"},
             {"turn": 2, "speaker_id": "P2", "speaker_name": "Bbb", "content": "f g"}]
    return {m["metric_id"] for m in compute_structural_metrics(probe)["metrics"]
            if m["metric_id"] not in DERIVED_SUPPORT_METRICS}


def aggregate(results: list[dict]) -> dict[str, list[dict]]:
    tables: dict[str, list[dict]] = {k: [] for k in SCHEMAS}
    if not results:
        return tables
    assert_complete(results)

    human = {r["input"]["fg"]: r for r in results if r["input"]["side"] == "human"}
    synth = [r for r in results if r["input"]["side"] == "synthetic"]

    # --- level 1: session ---------------------------------------------------
    per_run: list[dict] = []
    for r in synth:
        inp = r["input"]
        h = human[inp["fg"]]
        hp, sp = _present_set(h), _present_set(r)
        shared = hp & sp
        recall = _rate(len(shared), len(hp))
        prec = _rate(len(shared), len(sp))
        f1 = f1_score(recall, prec)

        hpt, spt = {_parent(s) for s in hp}, {_parent(s) for s in sp}
        sh_t = hpt & spt
        t_rec = _rate(len(sh_t), len(hpt))
        t_pre = _rate(len(sh_t), len(spt))

        reaches = [c.get("reach", 0.0) for c in r["tier1"]["codes"]
                   if c.get("present") and c.get("quote_verified")]
        sal = salience_hierarchy(h, r)
        s_words, h_words = _window_word_count(r), _window_word_count(h)
        length_ratio = _rate(s_words, h_words)
        # Derived from input.path, never from a key the record may not have.
        counts = _window_counts_for(r) or {}
        per_run.append({
            "physical_run": inp["physical_run"], "condition": inp["condition"],
            "fg": inp["fg"],
            "canonical_replication_index": inp["canonical_replication_index"],
            "namespace": "_comparable_window",
            "human_present_n": len(hp), "synthetic_present_n": len(sp),
            "shared_n": len(shared),
            "tier1_subtheme_recall": recall,
            "tier1_matched_theme_precision": prec,
            "tier1_f1_secondary": f1,
            "tier1_theme_level_recall": t_rec,
            "tier1_theme_level_precision": t_pre,
            "tier1_participant_reach": (round(sum(reaches) / len(reaches), 4)
                                        if reaches else None),
            "tier1_salience_hierarchy": sal["rho"],
            "tier1_salience_hierarchy_n_shared": sal["n_shared"],
            "tier1_salience_hierarchy_n_excluded": sal["n_excluded_total"],
            "tier1_salience_hierarchy_n_excluded_unverified": sal["n_excluded_unverified"],
            "tier1_salience_hierarchy_n_excluded_reach_missing": sal["n_excluded_reach_missing"],
            "tier1_salience_hierarchy_undefined_reason": sal["undefined_reason"],
            "length_ratio_synthetic_to_human": length_ratio,
            "participants_n": _participants_n(r),
            "reach_implementation_caveat": REACH_CAVEAT,
            # Real zero denominators stay None — no clamping to 1.
            "quote_verification_rate": _rate(r["quote_validity"]["verified_quotes"],
                                             r["quote_validity"]["total_quotes"]),
            "code_preservation_rate": _rate(r["quote_validity"]["verified_codes"],
                                            r["quote_validity"]["total_present_codes"]),
            "demoted_codes": r["quote_validity"]["demoted_codes"],
            "window_words": counts.get("window_words"),
            "window_participant_turns": counts.get("window_participant_turns"),
            "window_moderator_turns": counts.get("window_moderator_turns"),
            "transcript_sha256": inp["sha256"], "cache_key": r["cache_key"],
        })
    tables["per_run_metrics.csv"] = per_run

    # --- level 2: FG x condition -------------------------------------------
    def _vals(rows, key):
        return [x[key] for x in rows if x[key] is not None]

    for cond in CONDITIONS:
        for fg in FGS:
            rows = [x for x in per_run if x["fg"] == fg and x["condition"] == cond]
            if not rows:
                continue
            rec, pre = _vals(rows, "tier1_subtheme_recall"), _vals(rows, "tier1_matched_theme_precision")
            f1s, rch = _vals(rows, "tier1_f1_secondary"), _vals(rows, "tier1_participant_reach")
            tables["per_group_condition_summary.csv"].append({
                "fg": fg, "condition": cond, "n_replicates": len(rows),
                "namespace": "_comparable_window",
                # individual replicate values retained — the mean never replaces them
                "recall_values": "|".join(f"{v:.4f}" for v in rec),
                "recall_mean": round(sum(rec) / len(rec), 4) if rec else None,
                "recall_median": round(statistics.median(rec), 4) if rec else None,
                "recall_sd": _sd(rec),
                "recall_min": min(rec) if rec else None, "recall_max": max(rec) if rec else None,
                "precision_values": "|".join(f"{v:.4f}" for v in pre),
                "precision_mean": round(sum(pre) / len(pre), 4) if pre else None,
                "precision_median": round(statistics.median(pre), 4) if pre else None,
                "precision_sd": _sd(pre),
                "precision_min": min(pre) if pre else None, "precision_max": max(pre) if pre else None,
                "f1_secondary_values": "|".join(f"{v:.4f}" for v in f1s),
                "f1_secondary_mean": round(sum(f1s) / len(f1s), 4) if f1s else None,
                "reach_values": "|".join(f"{v:.4f}" for v in rch),
                "reach_mean": round(sum(rch) / len(rch), 4) if rch else None,
                "reach_implementation_caveat": REACH_CAVEAT,
                "human_present_n": rows[0]["human_present_n"],
                "participants_n": rows[0]["participants_n"],
            })

    # --- level 2b: paired effect per FG ------------------------------------
    METRICS = ("tier1_subtheme_recall", "tier1_matched_theme_precision",
               "tier1_participant_reach")
    for fg in FGS:
        for metric in METRICS:
            e = _vals([x for x in per_run if x["fg"] == fg and x["condition"] == "enriched"], metric)
            d = _vals([x for x in per_run if x["fg"] == fg
                       and x["condition"] == "demographics-only"], metric)
            if not e or not d:
                continue
            em, dm = sum(e) / len(e), sum(d) / len(d)
            psd = pooled_sd(e, d)
            tables["group_level_paired_effects.csv"].append({
                "fg": fg, "metric": metric, "namespace": "_comparable_window",
                "enriched_n": len(e), "demographics_only_n": len(d),
                "enriched_mean": round(em, 4), "demographics_only_mean": round(dm, 4),
                "difference_enriched_minus_demo": round(em - dm, 4),
                "enriched_sd": _sd(e), "demographics_only_sd": _sd(d),
                "within_cell_sd_pooled": psd,
                "difference_over_pooled_sd": (round((em - dm) / psd, 3)
                                              if psd not in (None, 0) else None),
                "favours": ("enriched" if em > dm else
                            "demographics-only" if dm > em else "tie"),
                "note": ("Descriptive difference. Pooled SD is variance-weighted with "
                         "df; the standardised effect is omitted when it is undefined "
                         "or zero. Not a significance test — with n=5 FGs no strong "
                         "inference is drawn, and absence of a difference is never "
                         "reported as equivalence."),
            })

    # --- level 3: study replicate ------------------------------------------
    for cond in CONDITIONS:
        for rep in (1, 2, 3):
            rows = [x for x in per_run
                    if x["condition"] == cond and x["canonical_replication_index"] == rep]
            if not rows:
                continue
            runs = {x["physical_run"] for x in rows}
            distinct = set()
            for r in synth:
                if r["input"]["physical_run"] in runs:
                    distinct |= _present_set(r)
            rec, pre = _vals(rows, "tier1_subtheme_recall"), _vals(rows, "tier1_matched_theme_precision")
            f1s, rch = _vals(rows, "tier1_f1_secondary"), _vals(rows, "tier1_participant_reach")
            tables["study_replication_summary.csv"].append({
                "study_replicate": rep, "condition": cond,
                "namespace": "_comparable_window", "n_fgs": len(rows),
                "fgs_included": "|".join(sorted(x["fg"] for x in rows)),
                "recall_mean_across_5_fgs": round(sum(rec) / len(rec), 4) if rec else None,
                "precision_mean_across_5_fgs": round(sum(pre) / len(pre), 4) if pre else None,
                "f1_secondary_mean": round(sum(f1s) / len(f1s), 4) if f1s else None,
                "reach_mean": round(sum(rch) / len(rch), 4) if rch else None,
                "reach_implementation_caveat": REACH_CAVEAT,
                "distinct_subthemes_across_study": len(distinct),
                "distinct_subtheme_ids": "|".join(sorted(distinct)),
                "note": ("One complete five-group realisation assembled by "
                         "canonical_replication_index. Replicates estimate generator "
                         "variability, not additional focus groups."),
            })

    # --- level 4: condition (independent rows, no cross-condition counts) ----
    for cond in CONDITIONS:
        srows = [x for x in tables["study_replication_summary.csv"] if x["condition"] == cond]
        rec = [x["recall_mean_across_5_fgs"] for x in srows
               if x["recall_mean_across_5_fgs"] is not None]
        pre = [x["precision_mean_across_5_fgs"] for x in srows
               if x["precision_mean_across_5_fgs"] is not None]
        tables["condition_level_summary.csv"].append({
            "condition": cond, "namespace": "_comparable_window",
            "n_study_replicates": len(srows),
            "recall_mean": round(sum(rec) / len(rec), 4) if rec else None,
            "recall_sd": _sd(rec), "recall_min": min(rec) if rec else None,
            "recall_max": max(rec) if rec else None,
            "precision_mean": round(sum(pre) / len(pre), 4) if pre else None,
            "precision_sd": _sd(pre), "precision_min": min(pre) if pre else None,
            "precision_max": max(pre) if pre else None,
            "between_replicate_variation_note": (
                "Report alongside any condition effect: prior work on this corpus showed "
                "between-run spread can exceed group-level differences."),
        })

    # --- the enriched-vs-demographics comparison, in its own table ----------
    # "How many FGs favour enriched" is a COMPARISON, not a property of either
    # condition. Putting it on a per-condition row implied the demographics-only
    # row somehow had its own count of FGs favouring enriched.
    for metric in METRICS:
        rows = [x for x in tables["group_level_paired_effects.csv"] if x["metric"] == metric]
        if not rows:
            continue
        fav_e = [x["fg"] for x in rows if x["favours"] == "enriched"]
        fav_d = [x["fg"] for x in rows if x["favours"] == "demographics-only"]
        ties = [x["fg"] for x in rows if x["favours"] == "tie"]
        diffs = [x["difference_enriched_minus_demo"] for x in rows]
        tables["condition_comparison.csv"].append({
            "metric": metric, "namespace": "_comparable_window",
            "n_fgs_compared": len(rows),
            "n_fgs_favouring_enriched": len(fav_e),
            "n_fgs_favouring_demographics_only": len(fav_d),
            "n_ties": len(ties),
            "fgs_favouring_enriched": "|".join(sorted(fav_e)),
            "mean_difference_enriched_minus_demo": round(sum(diffs) / len(diffs), 4),
            "note": ("Direction across the five groups. A count out of 5 is descriptive "
                     "only and is not a test."),
        })

    # --- long tables --------------------------------------------------------
    for r in results:
        inp = r["input"]
        pn = _participants_n(r)
        for c in r["tier1"]["codes"]:
            tables["thematic_code_presence_long.csv"].append({
                "side": inp["side"], "physical_run": inp.get("physical_run"),
                "condition": inp.get("condition", "human"), "fg": inp["fg"],
                "canonical_replication_index": inp.get("canonical_replication_index"),
                "subtheme_id": c["subtheme_id"], "parent_theme": _parent(c["subtheme_id"]),
                "present": c.get("present"), "quote_verified": c.get("quote_verified"),
                "n_verified_quotes": len(c.get("supporting_quotes", [])),
                "voiced_by_n": len(c.get("voiced_by", [])),
                "namespace": "_comparable_window",
            })
            if c.get("present"):
                tables["thematic_reach_long.csv"].append({
                    "side": inp["side"], "physical_run": inp.get("physical_run"),
                    "condition": inp.get("condition", "human"), "fg": inp["fg"],
                    "canonical_replication_index": inp.get("canonical_replication_index"),
                    "subtheme_id": c["subtheme_id"],
                    "voiced_by_n": len(c.get("voiced_by", [])),
                    "participants_n": pn, "reach": c.get("reach"),
                    "implementation_caveat": REACH_CAVEAT,
                    "namespace": "_comparable_window",
                })

        entries = _window_entries(r)
        if entries is None:
            raise IncompleteCorpusError(
                f"{inp.get('physical_run') or inp['fg']}: comparable-window transcript "
                f"unavailable ({inp.get('path')!r}) � structural metrics cannot be "
                f"computed. Refusing to emit a table with a header and no rows.")
        stem = {"side": inp["side"], "physical_run": inp.get("physical_run"),
                "condition": inp.get("condition", "human"), "fg": inp["fg"],
                "canonical_replication_index": inp.get("canonical_replication_index"),
                "namespace": "_comparable_window"}
        computed = compute_structural_metrics(entries)
        for m in computed["metrics"]:
            tables["structural_interaction_metrics_long.csv"].append({
                **stem,
                "registry_status": ("derived_support"
                                    if m["metric_id"] in DERIVED_SUPPORT_METRICS
                                    else "registry"),
                **m,
            })
        for d in computed["distributions"]:
            tables["structural_distributions_long.csv"].append({
                **stem,
                "supports_metric": DISTRIBUTIONS_REQUIRED_BY_REGISTRY[d["distribution_id"]],
                **d,
            })
    return tables


def main(emit_empty: bool) -> int:
    _RESULTS.mkdir(parents=True, exist_ok=True)
    results = [] if emit_empty else load_results()

    print("=" * 76)
    print("  AGGREGATION" + ("  [--emit-empty: schema only, no scoring read]"
                             if emit_empty else ""))
    print("=" * 76)
    print(f"\nTier-1 results loaded from cache: {len(results)}")

    try:
        tables = aggregate(results)
    except IncompleteCorpusError as exc:
        print(f"\n{exc}")
        return 2

    for name, header in SCHEMAS.items():
        _write_csv(_RESULTS / name, header, tables.get(name, []))
        print(f"  {name:<44} {len(header):>2} cols, {len(tables.get(name, [])):>4} rows")
    (_RESULTS / "emergent_and_missed_theme_evidence.json").write_text(
        json.dumps(_EMERGENT_JSON_SKELETON, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {'emergent_and_missed_theme_evidence.json':<44} schema, "
          f"{len(_EMERGENT_JSON_SKELETON['records']):>4} records")

    (_RESULTS / "AGGREGATION_README.md").write_text(f"""# Result tables — schema fixed, {'unpopulated' if emit_empty else 'populated'}

Generated {datetime.now(UTC).isoformat()} by `scripts/aggregate_production_results.py`.

## Levels

| Level | Table | Unit |
|---|---|---|
| 1 | `per_run_metrics.csv` | one synthetic run vs its paired human transcript |
| 2 | `per_group_condition_summary.csv` | FG x condition over 3 canonical replicates |
| 2b | `group_level_paired_effects.csv` | enriched - demographics-only, per FG |
| 3 | `study_replication_summary.csv` | five-group realisation by replication index |
| 4 | `condition_level_summary.csv` | across the 3 study replicates, per condition |
| 4b | `condition_comparison.csv` | enriched vs demographics-only, across the 5 FGs |
| long | `thematic_code_presence_long.csv`, `thematic_reach_long.csv` | one row per code per result |
| long | `structural_interaction_metrics_long.csv` | one row per structural/interaction metric per result |
| long | `structural_distributions_long.csv` | the raw vectors behind the structural summaries |
| evidence | `emergent_and_missed_theme_evidence.json` | not-observed and missed themes |

**10 CSV tables in total**, plus the JSON evidence file.

## `structural_distributions_long.csv`

The registry does not accept a bare summary statistic: `words_per_turn_median` must
be reported "with IQR and the full distribution, never the mean alone", both Gini
coefficients must carry "the raw per-participant vector", and `chain_depth` must
report "the distribution and the maximum, not only the mean". This table holds
those raw vectors so every summary above can be recomputed by hand.

| `distribution_id` | one row per | supports |
|---|---|---|
| `words_per_turn` | participant turn | `words_per_turn_median`, `words_per_turn_iqr` |
| `participant_turn_counts` | participant | `turn_balance_gini` |
| `participant_word_counts` | participant | `word_balance_gini` |
| `chain_depth` | uninterrupted participant chain | `chain_depth` |

`element_label` is `Participant N` by order of first appearance, never a speaker
name: the human transcripts carry pseudonyms and an audit table is the wrong place
to reintroduce them.

## Metrics NOT produced here

`structural_interaction_metrics_long.csv` marks each row `registry` or
`derived_support`, so a frozen measure is distinguishable from a convenience count.
Of the 28 frozen `AUTOMATIC_*` metrics, 20 are computed here. The rest:

* 5 `_full_run_operational` metrics live in `run_readiness_audit.csv` and
  `api_failure_and_fallback_audit.csv` (artifact and column verified by test);
* 1 D2 diagnostic (`tier1_coverage_by_word_count_curve`) comes from
  `scripts/d2_length_diagnostics.py`, which is written and tested but **has not been
  run** — it needs Tier-1 results. Accounting for a metric is not having computed it.

`tier1_length_matched_recall` / `_precision` are **`DEFERRED_NOT_IMPLEMENTED`** and
are therefore no longer in the `AUTOMATIC_*` set at all. They require each excerpt to
be coded independently (~300 further evaluator calls, not scheduled). The offline
`evidence_localized_length_matched_*` metrics are a **different estimand**, not an
approximation of them, are classified `EXPLORATORY`, and a test forbids the deferred
names from appearing in any proxy output. See frozen_evaluation_spec.md Amendment A1
(2026-07-30).

## Hard completeness gate

Aggregation refuses to run unless the result set has exactly
{EXPECTED_HUMAN_TRANSCRIPTS} human transcripts,
{EXPECTED_RUNS_PER_GROUP_CONDITION} runs per FG x condition,
{EXPECTED_FGS_PER_STUDY_REPLICATE} FGs per study replicate and
{EXPECTED_STUDY_REPLICATES_PER_CONDITION} study replicates per condition.
A partial batch would otherwise produce a mean over 2 replicates that reads exactly
like a mean over 3.

## Rules encoded in the schema

* Replicate values are retained in `*_values` columns — the mean never replaces them.
* The F1 column is `tier1_f1_secondary`; recall and precision precede it everywhere.
* Every reach row carries `reach_implementation_caveat`, and `participants_n` is the
  explicit denominator.
* `within_cell_sd_pooled` is the variance-weighted pooled SD with df; the
  standardised effect is omitted when it is undefined or zero.
* `n_fgs_favouring_enriched` lives in `condition_comparison.csv`, because it is a
  comparison between conditions, not a property of one.
* `namespace` is an explicit column; `_full_run_operational` metrics stay in
  `api_failure_and_fallback_audit.csv` and are never joined here.
* `tier1_salience_hierarchy` uses only codes that are present, quote-verified and
  carry a non-null reach on both sides. A missing reach is never read as 0.0; the
  excluded counts and an explicit undefinition reason are separate columns.
* Interpretive metrics have no column until the gold standard returns.
* A synthetic-only theme is recorded as `synthetic_only_not_observed_in_human`.
""", encoding="utf-8")
    print(f"\nWrote {(_RESULTS / 'AGGREGATION_README.md').relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-empty", action="store_true",
                    help="Write the tables with headers and no rows, to fix and review "
                         "the schema before any scoring exists.")
    a = ap.parse_args()
    sys.exit(main(a.emit_empty))
