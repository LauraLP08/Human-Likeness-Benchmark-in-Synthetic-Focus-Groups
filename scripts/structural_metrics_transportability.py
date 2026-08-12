"""
Structural metrics for the cross-domain transportability check (DS05 mindfulness).

Offline only. No API calls.

The metric definitions are NOT new. They are re-implementations of the frozen
registry entries in analysis/production_evaluation/metric_registry.csv
(structural and interaction tiers). Because a re-implementation is only as
trustworthy as its agreement with the original, this script FIRST reproduces the
frozen human Macho Meals values from
analysis/production_evaluation/results/structural_interaction_metrics_long.csv
and refuses to report mindfulness numbers if that reproduction fails.

Only metrics whose evidence_class is AUTOMATIC_VALIDATED or
AUTOMATIC_DIAGNOSTIC are computed here. Every NOT_IN_REPORTED_INSTRUMENT
metric (agreement, disagreement, challenge, specificity, profile_*, ...) is
deliberately absent: those are withheld from substantive reporting pending the
two-coder gold standard, and nothing about a new domain changes that.

Usage:
    py scripts/structural_metrics_transportability.py --validate
    py scripts/structural_metrics_transportability.py
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.session_state import count_words  # noqa: E402

# ---------------------------------------------------------------------------
# Constants and helpers replicated EXACTLY from scripts/aggregate_production_
# results.py, which produced the frozen values. They are copied rather than
# imported so that importing this module cannot execute that script's
# module-level work, and rather than rewritten so the numbers stay comparable.
#
# NOTE, recorded because it is a real inconsistency in the frozen apparatus and
# not something to silently "fix" here: the structural metrics count words with
# a plain str.split(), NOT with core.session_state.count_words (the project's
# documented uniform word-counting rule, docs/length_measurement_rule.md).
# str.split() counts transcription annotations such as "(.)" and "[inaudible]"
# as words. Reproducing the frozen values requires str.split(); using
# count_words instead shifts total_words by roughly 0.3% on these transcripts.
# Comparability with the existing results wins, so str.split() is used and the
# discrepancy is reported rather than corrected.
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")

AMBIGUOUS_FIRST_NAMES = {
    "will", "mark", "bill", "art", "may", "june", "april", "august", "grace",
    "hope", "faith", "joy", "rose", "daisy", "dawn", "summer", "sunny", "frank",
    "rich", "chase", "drew", "sky", "star", "angel", "earl", "duke", "king",
    "guy", "max", "don", "van", "lane", "reed", "brook", "gene", "jack", "bob",
    "pat", "rob", "ray", "wade", "cliff", "dale", "glen", "heath", "miles",
    "penny", "sage", "scout", "trace", "ash", "bear", "buck", "colt", "dot",
}


def _tokens(text: str) -> list[str]:
    """Lowercase word tokens with possessive clitics stripped ("bob's" -> "bob")."""
    return [t[:-2] if t.endswith("'s") else t for t in _WORD_RE.findall(text.lower())]


# _WORD_RE is [a-z]+ only, so a roster label containing a digit or underscore
# (MF_P2, P1.1) cannot be produced by _tokens at all: "MF_P2" tokenizes to
# ["mf", "p"] and the roster key "mf_p2" can never match. The frozen
# reference_density therefore returns 0.0 for such a dataset SILENTLY — not as a
# declared lower bound, but as a measurement that could not run. On this corpus
# the true value is 0.60, not 0.0.
#
# Both are reported: `reference_density` keeps the frozen tokenizer so the number
# stays comparable with the Macho Meals values, and
# `reference_density_label_aware` uses the tokenizer below. Whenever a roster
# name is unrepresentable, `reference_density_unrepresentable_names` is non-zero
# and the frozen figure must not be interpreted.
_LABEL_RE = re.compile(r"[a-z][a-z0-9_.']*")


def _label_tokens(text: str) -> list[str]:
    """Tokens that can represent alphanumeric participant labels (mf_p2, p1.1)."""
    return [t[:-2] if t.endswith("'s") else t.rstrip(".") for t in _LABEL_RE.findall(text.lower())]


def _wc(text: str) -> int:
    """The frozen structural word count: plain whitespace split. See note above."""
    return len(str(text).split())

_FROZEN = _ROOT / "analysis/production_evaluation/results/structural_interaction_metrics_long.csv"
_MACHO = _ROOT / "data/datasets_transcripts/standardized/macho_meals"
_MINDFULNESS = _ROOT / "data/datasets_transcripts/standardized/mindfulness/fg1"
_OUT_DIR = _ROOT / "analysis/transportability_mindfulness"

# The human mindfulness transcript opens with a welcome and instructions block,
# then poses Question 1 inside the SAME moderator turn. The human Macho Meals
# transcripts begin at Question 1 already, which is why no trimming was needed
# there. To put the two human corpora on the same footing this anchor marks
# where the Q1 ask begins; the text before it is dropped from the trimmed view.
# Recorded verbatim, never paraphrased, per the anchor-and-extend convention in
# analysis/production_evaluation/comparable_window_boundaries.md.
_MINDFULNESS_Q1_ANCHOR = "So I will start with the first set of questions."


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


def _iqr(values: list[float]) -> float | None:
    """statistics.quantiles default method ("exclusive"), as the frozen run used."""
    if len(values) < 4:
        return None
    quartiles = statistics.quantiles(values, n=4)
    return quartiles[2] - quartiles[0]


def compute(turns: list[dict], roster_names: list[str]) -> dict:
    """Compute the frozen structural/interaction metrics over a turn list."""
    participant_turns = [t for t in turns if t["speaker_role"] == "participant"]
    moderator_turns = [t for t in turns if t["speaker_role"] == "moderator"]

    p_words = [_wc(t["content"]) for t in participant_turns]
    m_words = [_wc(t["content"]) for t in moderator_turns]

    per_speaker_turns: dict[str, int] = {}
    per_speaker_words: dict[str, int] = {}
    for t in participant_turns:
        sid = t["canonical_speaker_id"]
        per_speaker_turns[sid] = per_speaker_turns.get(sid, 0) + 1
        per_speaker_words[sid] = per_speaker_words.get(sid, 0) + _wc(t["content"])

    # Adjacency and chains over the turn sequence.
    roles = [t["speaker_role"] for t in turns]
    transitions = len(roles) - 1
    pp_transitions = sum(
        1 for i in range(transitions) if roles[i] == "participant" and roles[i + 1] == "participant"
    )

    chains: list[int] = []
    current = 0
    for role in roles:
        if role == "participant":
            current += 1
        else:
            if current:
                chains.append(current)
            current = 0
    if current:
        chains.append(current)

    # reference_density: token equality, not substring, so "same" does not match
    # Sam and "start" does not match Art. Roster names that are ordinary English
    # words are excluded outright, which makes the metric a LOWER BOUND.
    firsts: dict[str, str] = {}
    ambiguous: list[str] = []
    for key in roster_names:
        first = key.split()[0].lower() if key.split() else ""
        if not first or len(first) < 3:
            continue
        if first in AMBIGUOUS_FIRST_NAMES:
            ambiguous.append(first)
            continue
        firsts[key] = first
    ref_hits = 0
    for t in participant_turns:
        me = str(t.get("speaker_name") or t.get("speaker_id"))
        toks = set(_tokens(str(t.get("content", ""))))
        if any(fn in toks for k, fn in firsts.items() if k != me):
            ref_hits += 1
    excluded_names = ambiguous

    # Label-aware recomputation, plus a loud flag for names the frozen tokenizer
    # cannot represent at all (see the note beside _label_tokens).
    # Two ways this metric fails silently, both found on this corpus:
    #   (a) a label the frozen tokenizer cannot produce at all (MF_P2 -> mf, p);
    #   (b) labels that collapse to the same first token, because the frozen code
    #       keys on key.split()[0] — "Speaker 2".."Speaker 6" all reduce to
    #       "speaker", so the five participants become mutually indistinguishable
    #       and the metric silently measures whether a turn contains the word
    #       "speaker". Neither case is flagged by the frozen implementation.
    unrepresentable = sorted(fn for fn in firsts.values() if not _WORD_RE.fullmatch(fn))
    collapsed = len(set(firsts.values())) < len(firsts)
    ref_hits_label = 0
    for t in participant_turns:
        me = str(t.get("speaker_name") or t.get("speaker_id"))
        toks = set(_label_tokens(str(t.get("content", ""))))
        if any(fn in toks for k, fn in firsts.items() if k != me):
            ref_hits_label += 1

    total_words = sum(p_words) + sum(m_words)
    metrics = {
        "participant_turns": len(participant_turns),
        "moderator_turns": len(moderator_turns),
        "participant_words": sum(p_words),
        "total_words": total_words,
        "words_per_turn_median": round(statistics.median(p_words), 4) if p_words else None,
        "words_per_turn_iqr": round(_iqr(p_words), 4) if _iqr(p_words) is not None else None,
        "short_turn_proportion_25w": round(sum(1 for w in p_words if w < 25) / len(p_words), 4) if p_words else None,
        "short_turn_proportion_10w": round(sum(1 for w in p_words if w < 10) / len(p_words), 4) if p_words else None,
        "short_turn_proportion_50w": round(sum(1 for w in p_words if w < 50) / len(p_words), 4) if p_words else None,
        "turn_balance_gini": _gini(list(per_speaker_turns.values())),
        "word_balance_gini": _gini(list(per_speaker_words.values())),
        "moderator_turn_share": round(len(moderator_turns) / len(turns), 4) if turns else None,
        "moderator_word_share": round(sum(m_words) / total_words, 4) if total_words else None,
        "participant_participant_adjacency": round(pp_transitions / transitions, 4) if transitions else None,
        "reference_density": round(ref_hits / len(participant_turns), 4) if participant_turns else None,
        "reference_density_ambiguous_names_excluded": len(excluded_names),
        "reference_density_label_aware": round(ref_hits_label / len(participant_turns), 4) if participant_turns else None,
        "reference_density_unrepresentable_names": len(unrepresentable),
        "reference_density_valid": (not unrepresentable) and (not collapsed),
        "reference_density_labels_collapsed": collapsed,
        "length_ratio_note": "length_ratio_synthetic_to_human is total_words(synthetic)/total_words(human)",
        "chain_depth": round(statistics.mean(chains), 4) if chains else None,
        "chain_depth_max": max(chains) if chains else None,
        "chain_depth_n_chains": len(chains),
    }
    metrics["_per_speaker_turns"] = per_speaker_turns
    metrics["_per_speaker_words"] = per_speaker_words
    return metrics


def _load_baseline(directory: Path) -> tuple[list[dict], list[str]]:
    turns = json.loads((directory / "transcript.json").read_text(encoding="utf-8"))
    people = json.loads((directory / "participant_metadata.json").read_text(encoding="utf-8"))
    names = [p["speaker_name"] for p in people if p["speaker_role"] == "participant"]
    return turns, names


def _frozen_human_values() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    with _FROZEN.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["side"] != "human":
                continue
            out.setdefault(row["fg"], {})[row["metric_id"]] = row["value"]
    return out


def validate() -> tuple[bool, list[str]]:
    """Reproduce the frozen human Macho Meals values. Returns (ok, lines)."""
    frozen = _frozen_human_values()
    lines: list[str] = []
    ok = True
    for fg in sorted(frozen):
        directory = _MACHO / fg
        if not directory.exists():
            lines.append(f"{fg}: SKIP (no standardized dir)")
            continue
        turns, names = _load_baseline(directory)
        mine = compute(turns, names)
        for metric_id, frozen_value in sorted(frozen[fg].items()):
            if metric_id not in mine:
                continue
            got = mine[metric_id]
            want = float(frozen_value)
            if got is None:
                lines.append(f"  {fg} {metric_id}: MISMATCH got None want {want}")
                ok = False
                continue
            # Frozen values carry varying precision; compare at the frozen value's.
            decimals = len(frozen_value.split(".")[1]) if "." in frozen_value else 0
            if round(float(got), decimals) != round(want, decimals):
                lines.append(f"  {fg} {metric_id}: MISMATCH got {got} want {want}")
                ok = False
    return ok, lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true", help="only reproduce the frozen values")
    args = parser.parse_args()

    ok, lines = validate()
    print("=" * 78)
    print("VALIDATION — reproducing frozen human Macho Meals structural values")
    print("=" * 78)
    for line in lines:
        print(line)
    print("PASS: implementation reproduces every frozen human value" if ok
          else f"FAIL: {len(lines)} mismatches — mindfulness numbers withheld")
    if args.validate or not ok:
        return 0 if ok else 2

    # ---- Human mindfulness, full transcript and Q1-anchored trim ----
    turns, names = _load_baseline(_MINDFULNESS)
    full = compute(turns, names)

    trimmed_turns = [dict(t) for t in turns]
    anchor_turn = next(
        (i for i, t in enumerate(trimmed_turns) if _MINDFULNESS_Q1_ANCHOR in t["content"]), None
    )
    trim_note = None
    if anchor_turn is None:
        trim_note = "Q1 anchor not found; trimmed view not produced"
        trimmed = None
    else:
        entry = trimmed_turns[anchor_turn]
        offset = entry["content"].index(_MINDFULNESS_Q1_ANCHOR)
        dropped = entry["content"][:offset]
        entry["content"] = entry["content"][offset:].strip()
        trimmed_turns = trimmed_turns[anchor_turn:]
        trimmed = compute(trimmed_turns, names)
        trim_note = {
            "anchor_verbatim": _MINDFULNESS_Q1_ANCHOR,
            "boundary_turn_index": anchor_turn,
            "dropped_chars": len(dropped),
            "dropped_words": count_words(dropped),
            "dropped_prefix_verbatim": dropped.strip(),
        }

    # ---- Human Macho Meals reference band ----
    band = {}
    for fg_dir in sorted(_MACHO.glob("fg*")):
        fg_turns, fg_names = _load_baseline(fg_dir)
        band[fg_dir.name] = compute(fg_turns, fg_names)

    report = {
        "record_type": "CROSS_DOMAIN_STRUCTURAL_COMPARISON_HUMAN_SIDE",
        "classification": "EXPLORATORY_OUT_OF_DOMAIN_TRANSPORTABILITY_CHECK",
        "no_api_calls": True,
        "implementation_validated_against_frozen_values": ok,
        "metric_source": "analysis/production_evaluation/metric_registry.csv (structural + interaction, AUTOMATIC_* only)",
        "withheld": (
            "All NOT_IN_REPORTED_INSTRUMENT metrics are absent by design; "
            "they remain withheld pending the two-coder gold standard."
        ),
        "mindfulness_human_full": full,
        "mindfulness_human_q1_trimmed": trimmed,
        "mindfulness_trim_note": trim_note,
        "macho_meals_human_band": band,
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = _OUT_DIR / "structural_human_side.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {out.relative_to(_ROOT)}")

    keys = [
        "participant_turns", "moderator_turns", "total_words",
        "words_per_turn_median", "words_per_turn_iqr",
        "short_turn_proportion_25w", "turn_balance_gini", "word_balance_gini",
        "moderator_turn_share", "moderator_word_share",
        "participant_participant_adjacency", "chain_depth", "chain_depth_max",
    ]
    band_fgs = sorted(band)
    header = f"\n{'metric':38s} {'MF(full)':>10s} {'MF(trim)':>10s} " + " ".join(f"{fg:>8s}" for fg in band_fgs)
    print(header)
    print("-" * len(header))
    for key in keys:
        row = f"{key:38s} {str(full.get(key)):>10s} {str(trimmed.get(key) if trimmed else '-'):>10s} "
        row += " ".join(f"{str(band[fg].get(key)):>8s}" for fg in band_fgs)
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
