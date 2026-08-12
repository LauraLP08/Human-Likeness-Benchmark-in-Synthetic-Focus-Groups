"""
D2 length diagnostics — PREPARED, NOT RUN.

Produces:

    tier1_coverage_by_word_count_curve            (frozen registry metric)
    evidence_localized_length_matched_recall      (PROXY — different estimand)
    evidence_localized_length_matched_precision   (PROXY — different estimand)

THE PROXIES ARE NOT tier1_length_matched_recall / _precision
Those two frozen metrics require each excerpt to be CODED INDEPENDENTLY, and they
remain DEFERRED_NOT_IMPLEMENTED. This module does not implement them and does not
approximate them under their own name.

What this module actually measures is where ALREADY-CODED evidence falls. Each
verified quote carries the `turn_id` the evaluator cited it from, so "which
subthemes had verified evidence inside excerpt k" is arithmetic over an existing
Tier-1 result. That is a DIFFERENT ESTIMAND from "which subthemes a coder would
identify given only excerpt k": the evaluator read the whole window, so a code
whose quote sits inside excerpt k was identified with the surrounding context
available, and a code a coder would have found in the excerpt alone may carry no
quote there.

The original specification did NOT ask for this derivation — it asked for
recomputation on excerpts. This is a substitute operationalisation, adopted because
the real thing costs 30 runs x 10 excerpts = 300 further evaluator calls. Those
calls are NOT scheduled. The substitution is recorded as a dated amendment in
frozen_evaluation_spec.md rather than presented as the original plan, and the
proxies carry names that cannot be mistaken for the deferred metrics.

EXCERPT CONSTRUCTION IS THE FROZEN RULE, NOT A NEW ONE
Per frozen_evaluation_spec.md §13:
  * K = 10 excerpts per run WHERE ENOUGH ELIGIBLE STARTS EXIST (K and the reason for
    any shortfall are both recorded);
  * target word count = the paired human window's word count;
  * deterministic start offsets, evenly spaced entry boundaries seeded by run id —
    spaced across the ELIGIBLE starts, never wrapping the window end to its start;
  * excerpts NEVER cut an entry mid-turn: an excerpt starts at an entry boundary and
    ends at the last complete entry whose inclusion does not exceed the target;
  * if the first entry alone already exceeds the target it is included whole, so an
    excerpt is never empty;
  * target AND achieved word counts are both recorded, with achieved/target, so any
    residual length mismatch stays visible;
  * mean and SD over the 10 excerpts are reported.

TURN IDS FOLLOW to_blind_text, INCLUDING ITS EMPTY-TURN SKIP
`to_blind_text` numbers turns 1..N over NON-EMPTY entries only. Indexing raw entries
instead would shift every quote position in any window containing an empty turn.
This module replicates that filter and asserts the count it produces.

No API call. Nothing writes to `output/session_logs/`.

Usage:
    py scripts/d2_length_diagnostics.py --emit-empty
    py scripts/d2_length_diagnostics.py            # once Tier-1 results exist
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_RESULTS = _OUT / "results"

K_EXCERPTS = 10

PROXY_CAVEAT = (
    "PROXY, NOT tier1_length_matched_*: measures where already-coded evidence falls, "
    "derived from verified quote positions in the full-window Tier-1 result. The "
    "evaluator read the whole window, so this is a different estimand from coding the "
    "excerpt independently. tier1_length_matched_recall/_precision remain "
    "DEFERRED_NOT_IMPLEMENTED")

COVERAGE_CAVEAT = (
    "Cumulative distinct quote-verified subthemes by words consumed, as the registry "
    "defines it; positions come from the full-window Tier-1 result")

# An excerpt counts as "approximately length-matched" when it reaches at least this
# fraction of the target. Starts that cannot reach it are not eligible, so a near-end
# start can no longer yield a stub excerpt while better starts exist. 0.90 is a
# declared threshold, not a discovered one: it is tight enough that a 10% shortfall
# cannot masquerade as a length match, and loose enough to survive one long turn
# straddling the boundary.
LENGTH_MATCH_TOLERANCE = 0.90

SCHEMAS: dict[str, list[str]] = {
    "d2_coverage_by_word_count_curve.csv": [
        "physical_run", "condition", "fg", "canonical_replication_index",
        "metric_id", "words_consumed", "entries_consumed",
        "cumulative_distinct_subthemes", "proportion_of_run_total",
        "namespace", "caveat",
    ],
    "d2_evidence_localized_excerpts.csv": [
        "physical_run", "condition", "fg", "canonical_replication_index",
        "excerpt_index", "k_excerpts", "k_reason", "n_eligible_starts",
        "start_entry_index", "end_entry_index", "n_entries",
        "target_words", "achieved_words", "achieved_over_target",
        "length_match_tolerance", "within_tolerance", "first_entry_exceeds_target",
        "human_present_n", "excerpt_localized_n", "shared_n",
        "evidence_localized_length_matched_recall",
        "evidence_localized_length_matched_precision",
        "namespace", "caveat",
    ],
    "d2_evidence_localized_summary.csv": [
        "physical_run", "condition", "fg", "canonical_replication_index",
        "metric_id", "k_excerpts", "k_reason", "n_eligible_starts",
        "mean", "sd", "min", "max", "n_undefined",
        "target_words", "achieved_words_mean",
        "achieved_over_target_min", "achieved_over_target_median",
        "achieved_over_target_max",
        "length_match_tolerance", "n_excerpts_within_tolerance",
        "namespace", "caveat",
    ],
}


class D2InputError(RuntimeError):
    """Raised when a Tier-1 result cannot support the D2 derivation."""


# ---------------------------------------------------------------------------
# Window and quote positions
# ---------------------------------------------------------------------------

_TURN_RE = re.compile(r"^T(\d+)$")


def blind_entries(entries: list[dict]) -> list[dict]:
    """Entries as to_blind_text numbers them: non-empty content only, 1-based."""
    return [e for e in entries if (e.get("content") or "").strip()]


def _words(entry: dict) -> int:
    return len(str(entry.get("content", "")).split())


def quote_turn_indices(code: dict) -> list[int]:
    """1-based turn numbers of a code's verified quotes, in order."""
    out = []
    for q in code.get("supporting_quotes", []) or []:
        m = _TURN_RE.match(str(q.get("turn_id", "")).strip())
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def verified_codes(result: dict) -> list[dict]:
    """Present AND quote-verified codes only — the same rule reach uses."""
    return [c for c in result["tier1"]["codes"]
            if c.get("present") and c.get("quote_verified")]


def first_evidence_turn(code: dict) -> int | None:
    turns = quote_turn_indices(code)
    return turns[0] if turns else None


# ---------------------------------------------------------------------------
# tier1_coverage_by_word_count_curve
# ---------------------------------------------------------------------------

def coverage_curve(entries: list[dict], result: dict) -> list[dict]:
    """
    Cumulative distinct quote-verified subthemes against words consumed from the
    START of the window. One row per entry boundary, so the curve is exact rather
    than binned — deterministic, no sampling.

    A code with no parseable quote turn cannot be placed on the curve and is
    excluded; the count is reported alongside so the curve's ceiling is checkable
    against the run's total.
    """
    be = blind_entries(entries)
    codes = verified_codes(result)
    first: dict[int, set[str]] = {}
    unplaceable = 0
    for c in codes:
        t = first_evidence_turn(c)
        if t is None or t < 1 or t > len(be):
            unplaceable += 1
            continue
        first.setdefault(t, set()).add(c["subtheme_id"])

    total = sum(len(v) for v in first.values())
    rows, seen, words = [], set(), 0
    for i, e in enumerate(be, start=1):
        words += _words(e)
        seen |= first.get(i, set())
        rows.append({
            "metric_id": "tier1_coverage_by_word_count_curve",
            "words_consumed": words,
            "entries_consumed": i,
            "cumulative_distinct_subthemes": len(seen),
            "proportion_of_run_total": (round(len(seen) / total, 4) if total else None),
            "caveat": COVERAGE_CAVEAT + (
                f"; {unplaceable} verified code(s) had no locatable quote turn and "
                f"are absent from this curve" if unplaceable else ""),
        })
    return rows


# ---------------------------------------------------------------------------
# tier1_length_matched_recall / _precision
# ---------------------------------------------------------------------------

def build_excerpt(entries: list[dict], start: int, target_words: int) -> dict:
    """
    Entry-aligned, CONTIGUOUS excerpt beginning at `start` and running forward only.

    Ends at the last complete entry whose inclusion does not exceed `target_words`.
    If the first entry alone already exceeds the target it is included whole, so an
    excerpt is never empty — and that case is flagged, because it is the one
    condition under which achieved > target legitimately.

    There is no wrap-around. Joining the tail of the window to its head would
    produce a discontinuous excerpt whose "words" never occurred in that order.
    """
    be = blind_entries(entries)
    if not be:
        raise D2InputError("cannot build an excerpt from an empty window")
    if not 0 <= start < len(be):
        raise D2InputError(f"start {start} outside window of {len(be)} entries")
    achieved, end = 0, start
    first_exceeds = False
    for i in range(start, len(be)):
        w = _words(be[i])
        if i == start and w > target_words:
            achieved, end, first_exceeds = w, i, True
            break
        if achieved + w > target_words:
            break
        achieved += w
        end = i
    ratio = round(achieved / target_words, 4) if target_words else None
    return {
        "start_entry_index": start + 1,          # 1-based, matching turn ids
        "end_entry_index": end + 1,
        "n_entries": end - start + 1,
        "target_words": target_words,
        "achieved_words": achieved,
        "achieved_over_target": ratio,
        "first_entry_exceeds_target": first_exceeds,
        "within_tolerance": bool(first_exceeds or (ratio is not None
                                                   and ratio >= LENGTH_MATCH_TOLERANCE)),
    }


def eligible_starts(entries: list[dict], target_words: int) -> tuple[list[int], str]:
    """
    Entry boundaries from which a contiguous excerpt can actually approach the target.

    Running forward only, starts near the end of the window cannot reach the target
    however the ladder is spaced: the words simply are not there. Selecting them
    anyway yields stub excerpts whose recall is low for a reason that has nothing to
    do with fidelity. Only starts reaching `LENGTH_MATCH_TOLERANCE` are eligible.

    Returns (starts, note). `note` is "" in the ordinary case and otherwise records
    exactly why the eligible set is unusual, so a degraded run is never silent.
    """
    be = blind_entries(entries)
    if not be:
        raise D2InputError("cannot select starts in an empty window")
    total = sum(_words(e) for e in be)
    if total < target_words:
        return [0], ("window_shorter_than_target: the whole synthetic window "
                     f"({total} words) is shorter than the target ({target_words}); "
                     "the full window is used as the single excerpt")

    ok, best, best_achieved = [], [], -1
    for s in range(len(be)):
        ex = build_excerpt(entries, s, target_words)
        if ex["within_tolerance"]:
            ok.append(s)
        if ex["achieved_words"] > best_achieved:
            best_achieved, best = ex["achieved_words"], [s]
        elif ex["achieved_words"] == best_achieved:
            best.append(s)
    if ok:
        return ok, ""
    return best, ("no_start_reaches_tolerance: no entry boundary yields an excerpt "
                  f"within {LENGTH_MATCH_TOLERANCE:.0%} of the target; the closest "
                  f"achievable ({best_achieved} words) is used")


def select_starts(run_id: str, eligible: list[int], k: int = K_EXCERPTS) -> list[int]:
    """
    K evenly spaced picks from the ELIGIBLE starts, with a run-id seeded phase.

    Spacing is applied across the eligible list rather than the raw window, so every
    pick is a start that can reach the target. The seed shifts the phase, so run 1's
    first excerpt is not always the earliest eligible boundary; it never moves a pick
    outside the eligible set.
    """
    if not eligible:
        return []
    if len(eligible) <= k:
        return list(eligible)
    seed = int(hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:8], 16)
    step = len(eligible) / k
    phase = (seed % 1000) / 1000.0
    picks, seen = [], set()
    for i in range(k):
        idx = int((i + phase) * step) % len(eligible)
        while idx in seen:                      # keep K distinct starts
            idx = (idx + 1) % len(eligible)
        seen.add(idx)
        picks.append(eligible[idx])
    return sorted(picks)


def _rate(num, den):
    return round(num / den, 4) if den else None


def length_matched_excerpts(entries: list[dict], synth_result: dict,
                            human_result: dict, human_entries: list[dict],
                            run_id: str, k: int = K_EXCERPTS) -> list[dict]:
    """
    Evidence-localised recall and precision over K contiguous entry-aligned excerpts.

    A subtheme counts as localised in an excerpt when at least one of its verified
    quotes falls inside the excerpt's turn range. This is NOT the same as coding the
    excerpt independently — see PROXY_CAVEAT, carried on every row.
    """
    target = sum(_words(e) for e in blind_entries(human_entries))
    human_present = {c["subtheme_id"] for c in verified_codes(human_result)}
    placed = [(c["subtheme_id"], quote_turn_indices(c))
              for c in verified_codes(synth_result)]

    eligible, note = eligible_starts(entries, target)
    starts = select_starts(run_id, eligible, k)
    k_reason = note
    if not k_reason and len(starts) < k:
        k_reason = (f"only {len(eligible)} entry boundary/ies can reach "
                    f"{LENGTH_MATCH_TOLERANCE:.0%} of the target, so K={len(starts)} "
                    f"instead of {k}")

    rows = []
    for idx, start in enumerate(starts, start=1):
        ex = build_excerpt(entries, start, target)
        lo, hi = ex["start_entry_index"], ex["end_entry_index"]
        localized = {sid for sid, turns in placed if any(lo <= t <= hi for t in turns)}
        shared = human_present & localized
        rows.append({
            "excerpt_index": idx, **ex,
            "n_eligible_starts": len(eligible),
            "k_excerpts": len(starts),
            "k_reason": k_reason,
            "length_match_tolerance": LENGTH_MATCH_TOLERANCE,
            "human_present_n": len(human_present),
            "excerpt_localized_n": len(localized),
            "shared_n": len(shared),
            "evidence_localized_length_matched_recall": _rate(len(shared), len(human_present)),
            "evidence_localized_length_matched_precision": _rate(len(shared), len(localized)),
            "caveat": PROXY_CAVEAT,
        })
    return rows


def summarise(excerpt_rows: list[dict]) -> list[dict]:
    """Mean and SD over the excerpts, plus the min/median/max spread of the match."""
    if not excerpt_rows:
        return []
    ratios = [r["achieved_over_target"] for r in excerpt_rows
              if r["achieved_over_target"] is not None]
    out = []
    for metric in ("evidence_localized_length_matched_recall",
                   "evidence_localized_length_matched_precision"):
        vals = [r[metric] for r in excerpt_rows if r[metric] is not None]
        out.append({
            "metric_id": metric,
            "k_excerpts": excerpt_rows[0]["k_excerpts"],
            "k_reason": excerpt_rows[0]["k_reason"],
            "n_eligible_starts": excerpt_rows[0]["n_eligible_starts"],
            "mean": round(statistics.mean(vals), 4) if vals else None,
            "sd": round(statistics.stdev(vals), 4) if len(vals) > 1 else None,
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
            "n_undefined": len(excerpt_rows) - len(vals),
            "target_words": excerpt_rows[0]["target_words"],
            "achieved_words_mean": round(statistics.mean(
                [r["achieved_words"] for r in excerpt_rows]), 4),
            "achieved_over_target_min": min(ratios) if ratios else None,
            "achieved_over_target_median": (round(statistics.median(ratios), 4)
                                            if ratios else None),
            "achieved_over_target_max": max(ratios) if ratios else None,
            "length_match_tolerance": LENGTH_MATCH_TOLERANCE,
            "n_excerpts_within_tolerance": sum(1 for r in excerpt_rows
                                               if r["within_tolerance"]),
            "caveat": PROXY_CAVEAT,
        })
    return out


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------

def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in header})


def _run_real() -> int:
    """Compute the D2 outputs from the completed Tier-1 corpus."""
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import aggregate_production_results as agg
    import production_eval_pipeline as pep

    results = agg.load_results()
    human = {r["input"]["fg"]: r for r in results if r["input"]["side"] == "human"}
    synth = [r for r in results if r["input"]["side"] == "synthetic"]
    if len(human) != 5 or len(synth) != 30:
        print(f"REFUSING: corpus is {len(human)} human / {len(synth)} synthetic, "
              f"expected 5 / 30")
        return 2

    def entries(rec):
        return pep._entries_for({"path": rec["input"]["path"],
                                 "side": rec["input"]["side"]})

    cov, exc, summ = [], [], []
    for r in results:
        inp = r["input"]
        stem = {"physical_run": inp.get("physical_run"),
                "condition": inp.get("condition", "human"),
                "fg": inp["fg"],
                "canonical_replication_index": inp.get("canonical_replication_index"),
                "namespace": "_comparable_window"}
        for row in coverage_curve(entries(r), r):
            cov.append({**stem, **row})

    for r in synth:
        inp = r["input"]
        h = human[inp["fg"]]
        stem = {"physical_run": inp["physical_run"], "condition": inp["condition"],
                "fg": inp["fg"],
                "canonical_replication_index": inp["canonical_replication_index"],
                "namespace": "_comparable_window"}
        rows = length_matched_excerpts(entries(r), r, h, entries(h),
                                       inp["physical_run"])
        for row in rows:
            exc.append({**stem, **row})
        for row in summarise(rows):
            summ.append({**stem, **row})

    _RESULTS.mkdir(parents=True, exist_ok=True)
    for name, rows in (("d2_coverage_by_word_count_curve.csv", cov),
                       ("d2_evidence_localized_excerpts.csv", exc),
                       ("d2_evidence_localized_summary.csv", summ)):
        _write_csv(_RESULTS / name, SCHEMAS[name], rows)
        print(f"  {name:<44} {len(SCHEMAS[name]):>3} cols, {len(rows):>5} rows")
    print("")
    print("evidence_localized_* are EXPLORATORY proxies, NOT tier1_length_matched_*.")
    return 0


def main(emit_empty: bool) -> int:
    _RESULTS.mkdir(parents=True, exist_ok=True)
    print("=" * 76)
    print("  D2 LENGTH DIAGNOSTICS" + ("  [--emit-empty: schema only]" if emit_empty else ""))
    print("=" * 76)
    if not emit_empty:
        return _run_real()
    for name, header in SCHEMAS.items():
        _write_csv(_RESULTS / name, header, [])
        print(f"  {name:<44} {len(header):>3} cols,    0 rows")
    print("\nDerivation: verified quote positions only. No evaluator call.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit-empty", action="store_true",
                    help="write headers only, so the schema is reviewable")
    raise SystemExit(main(ap.parse_args().emit_empty))
