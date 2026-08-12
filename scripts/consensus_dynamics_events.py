"""
Consensus dynamics — event layer (namespace: CONSENSUS_DYNAMICS_EXPLORATORY).

Builds the response-act table that every consensus metric and the N1 human
triage sample are computed from. Fully deterministic: a closed lexicon, no
model, no API call. Re-running on unchanged inputs reproduces the file
byte-for-byte (repeatability = 1.0 by construction).

A RESPONSE ACT is a participant turn whose immediately preceding turn, WITHIN
THE SAME GUIDE SECTION, is also a participant turn. It is the only unit where
"responding to someone" is defined without assumption, and it is the unit
already behind `participant_participant_adjacency` in the production pipeline.

Sections come from scripts/tier2b_segmentation.py (the Tier 2B segmenter):
human boundaries from the `Question N` headers, synthetic boundaries from the
moderator log cross-checked against the guide. Only sections comparable on both
sides of a pair are retained.

Design rationale, threats and the frozen spec:
    diseno_facilidad_de_consenso_2026-08-03.md
    analysis/production_evaluation/consensus_dynamics/FROZEN_SPEC.md

Usage:
    py scripts/consensus_dynamics_events.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tier2b_segmentation import (  # noqa: E402
    SegmentationResult,
    comparable_sections,
    segment_human_by_guide,
    segment_synthetic_by_guide,
)

_HUMAN_DIR = _REPO_ROOT / "data" / "datasets_transcripts" / "standardized" / "macho_meals"
_SESSION_LOGS = _REPO_ROOT / "output" / "session_logs"
_COMPARABLE = _REPO_ROOT / "analysis" / "production_evaluation" / "comparable_transcripts"
_OUT_DIR = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_dynamics"

FGS = ["fg1", "fg2", "fg3", "fg4", "fg5"]

# ---------------------------------------------------------------------------
# D1 — closed lexicon. FROZEN: any edit invalidates the spec hash.
#
# Counted as cue phrases in turn-initial or clause-initial position only. We
# COUNT markers; we never classify stance (the ablation lesson: the sycophancy
# classifier failed at classifying, a marker count is auditable line by line).
#
# The dictionary deliberately mixes formal registers ("I disagree") and British
# colloquial speech ("nah", "yeah but", "I dunno about that"), because the
# corpus mixes them asymmetrically. Whether it still under-detects one side is
# an empirical question answered by the N1 triage, not by argument.
# ---------------------------------------------------------------------------

DIVERGENCE_MARKERS: list[str] = [
    # explicit
    "i disagree", "i don't agree", "i dont agree", "i'd disagree", "id disagree",
    "i'd push back", "id push back", "i have to disagree", "i'm not sure i agree",
    "im not sure i agree", "not sure i agree", "i wouldn't say", "i wouldnt say",
    "i don't think that's", "i dont think thats", "that's not", "thats not",
    "i don't buy", "i dont buy",
    # concessive pivot (the canonical spoken disagreement frame)
    "yeah but", "yeah, but", "yes but", "yes, but", "true but", "true, but",
    "i see what you mean but", "i get that but", "fair enough but",
    "i take your point but", "that's fair but", "thats fair but",
    "i hear you but", "agree but",
    # colloquial negation / doubt
    "nah", "no,", "not really", "i dunno about that", "i don't know about that",
    "i dont know about that", "i'm not convinced", "im not convinced",
    "actually, no", "actually no", "see i", "hmm, i", "well, i'd say",
    # contrastive self-positioning
    "for me it's different", "for me its different", "that's not my experience",
    "thats not my experience", "i'd say the opposite", "id say the opposite",
    "the other way round", "other way around", "whereas i", "but i think",
    "but for me", "personally i'd", "personally id",
]

ALIGNMENT_MARKERS: list[str] = [
    "i agree", "agreed", "exactly", "same here", "same for me", "that's true",
    "thats true", "so true", "definitely", "absolutely", "100%", "spot on",
    "yeah, exactly", "yeah exactly", "yeah, definitely", "couldn't agree more",
    "couldnt agree more", "that's it", "thats it", "same", "me too",
    "i'm the same", "im the same", "like you said", "as you said",
    "as x said", "that's a good point", "thats a good point", "good point",
    "i'd echo", "id echo", "building on", "to add to that", "same boat",
    "yeah, i think so too", "i think so too", "totally",
]

HEDGE_MARKERS: list[str] = [
    "i suppose", "i guess", "kind of", "sort of", "maybe", "perhaps",
    "i think maybe", "possibly", "to be fair", "i mean", "in a way",
    "it depends", "not necessarily",
]

# Clause boundary: start of turn, or after sentence punctuation / conjunction.
_CLAUSE_SPLIT = re.compile(r"(?:^|[.!?;:\n]+|\s+(?:and|but|so|because|although|though)\s+)", re.I)


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


# Opening window, in clauses. PRIMARY variant.
#
# Chosen after inspecting D1's behaviour on the corpus, and documented as an
# instrument-construction decision (not a result-dependent one): whole-turn
# counting gave 33.7% divergence-flagged on the synthetic side vs 5.0% human,
# and manual inspection showed the gap was carried by mid-turn contrastive
# constructions ("that's not the same as saying...", 155 hits synthetic vs 3
# human) that mark internal argument structure, not stance toward the previous
# speaker. Mean clauses per act is 6.4 human vs 24.0 synthetic (3.75x), so
# whole-turn counting hands the longer side ~4x the opportunities to fire.
#
# Restricting to the turn opening equalises opportunity and targets the
# construct: uptake stance toward the preceding speaker is signalled at the
# start of a response, not in the middle of a monologue. The whole-turn variant
# is retained and reported as the sensitivity analysis, never dropped.
OPENING_CLAUSES = 2


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE_SPLIT.split(_norm(text)) if c and c.strip()]


def count_markers(text: str, markers: list[str],
                  n_clauses: int | None = None) -> tuple[int, list[str]]:
    """
    Count clause-initial occurrences of any marker. Returns (count, hits).

    n_clauses limits the scan to the first N clauses (the opening window);
    None scans the whole turn.
    """
    clauses = _clauses(text)
    if n_clauses is not None:
        clauses = clauses[:n_clauses]
    n, hits = 0, []
    for clause in clauses:
        for m in markers:
            if clause.startswith(m):
                n += 1
                hits.append(m)
                break  # one marker per clause; longest-prefix ambiguity is not resolved,
                       # the first match in dictionary order wins (deterministic).
    return n, hits


# ---------------------------------------------------------------------------
# Transcript access
# ---------------------------------------------------------------------------

@dataclass
class Act:
    side: str
    fg: str
    run: str                  # "" for human
    condition: str            # "human" | "enriched" | "demographics-only"
    section_index: int
    section_label: str
    act_index_in_section: int
    prev_turn_id: str
    prev_speaker: str
    prev_text: str
    resp_turn_id: str
    resp_speaker: str
    resp_text: str
    selection_mode: str       # "" for human (label does not exist on that side)
    n_clauses: int = 0
    # PRIMARY: opening window
    d1_div: int = 0
    d1_align: int = 0
    d1_hedge: int = 0
    d1_div_hits: list[str] = field(default_factory=list)
    d1_align_hits: list[str] = field(default_factory=list)
    # SENSITIVITY: whole turn
    d1_div_full: int = 0
    d1_align_full: int = 0


def _is_moderator(entry: dict) -> bool:
    if entry.get("speaker_role"):
        return entry["speaker_role"] == "moderator"
    return entry.get("speaker_id") == "MODERATOR"


def _acts_from_segments(
    entries: list[dict],
    seg: SegmentationResult,
    sections: list[int],
    *,
    side: str,
    fg: str,
    run: str,
    condition: str,
) -> list[Act]:
    acts: list[Act] = []
    for sidx in sections:
        sec = seg.sections[sidx]
        idxs = sorted(sec.entry_indices)
        k = 0
        for a, b in zip(idxs, idxs[1:]):
            prev, resp = entries[a], entries[b]
            if _is_moderator(prev) or _is_moderator(resp):
                continue
            k += 1
            text = resp.get("content", "")
            div, div_hits = count_markers(text, DIVERGENCE_MARKERS, OPENING_CLAUSES)
            align, align_hits = count_markers(text, ALIGNMENT_MARKERS, OPENING_CLAUSES)
            hedge, _ = count_markers(text, HEDGE_MARKERS, OPENING_CLAUSES)
            div_f, _ = count_markers(text, DIVERGENCE_MARKERS)
            align_f, _ = count_markers(text, ALIGNMENT_MARKERS)
            acts.append(Act(
                side=side, fg=fg, run=run, condition=condition,
                section_index=sidx, section_label=sec.section_label,
                act_index_in_section=k,
                prev_turn_id=f"T{a:03d}",
                prev_speaker=prev.get("speaker_name", prev.get("speaker_id", "")),
                prev_text=prev.get("content", ""),
                resp_turn_id=f"T{b:03d}",
                resp_speaker=resp.get("speaker_name", resp.get("speaker_id", "")),
                resp_text=resp.get("content", ""),
                selection_mode=resp.get("selection_mode", "") or "",
                n_clauses=len(_clauses(text)),
                d1_div=div, d1_align=align, d1_hedge=hedge,
                d1_div_hits=div_hits, d1_align_hits=align_hits,
                d1_div_full=div_f, d1_align_full=align_f,
            ))
    return acts


def _condition_of(run: str) -> str:
    return "demographics-only" if "demoonly" in run else "enriched"


def build() -> tuple[list[Act], list[dict]]:
    runs = sorted(p.name for p in _COMPARABLE.iterdir() if p.is_dir())
    acts: list[Act] = []
    skipped: list[dict] = []
    human_done: set[str] = set()

    for run in runs:
        fg = re.search(r"(fg\d)", run).group(1)
        guide = _SESSION_LOGS / run / "session_state_initial.json"
        syn_path = _SESSION_LOGS / run / "transcript.json"
        hum_path = _HUMAN_DIR / fg / "transcript.json"

        h_seg = segment_human_by_guide(hum_path, guide)
        s_seg = segment_synthetic_by_guide(syn_path, guide)
        comparable, skips = comparable_sections(h_seg, s_seg)
        for s in skips:
            skipped.append({"run": run, "fg": fg, **{
                k: v for k, v in s.items() if k in ("section_index", "section_label", "status", "reason")}})

        syn_entries = json.loads(syn_path.read_text(encoding="utf-8"))
        acts += _acts_from_segments(
            syn_entries, s_seg, comparable,
            side="synthetic", fg=fg, run=run, condition=_condition_of(run))

        # The human side of a pair is the same transcript for all runs of that FG.
        # Emit it once, over the union of sections comparable in ANY pair of that FG,
        # so the human denominator does not silently depend on run ordering.
        if fg not in human_done:
            hum_entries = json.loads(hum_path.read_text(encoding="utf-8"))
            all_comparable = set(comparable)
            for other in runs:
                if re.search(r"(fg\d)", other).group(1) != fg:
                    continue
                o_seg = segment_synthetic_by_guide(
                    _SESSION_LOGS / other / "transcript.json",
                    _SESSION_LOGS / other / "session_state_initial.json")
                c2, _ = comparable_sections(h_seg, o_seg)
                all_comparable |= set(c2)
            acts += _acts_from_segments(
                hum_entries, h_seg, sorted(all_comparable),
                side="human", fg=fg, run="", condition="human")
            human_done.add(fg)

    return acts, skipped


_FIELDS = [
    "act_id", "side", "fg", "run", "condition", "section_index", "section_label",
    "act_index_in_section", "selection_mode",
    "prev_turn_id", "prev_speaker", "prev_words",
    "resp_turn_id", "resp_speaker", "resp_words", "n_clauses",
    "d1_div", "d1_align", "d1_hedge", "d1_div_hits", "d1_align_hits",
    "d1_label", "d1_div_full", "d1_align_full", "d1_label_full",
    "prev_text", "resp_text",
]


def _label(div: int, align: int) -> str:
    if div > 0 and align > 0:
        return "mixed"
    if div > 0:
        return "divergence"
    if align > 0:
        return "alignment"
    return "none"


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    acts, skipped = build()

    rows = []
    for a in acts:
        key = f"{a.side}|{a.fg}|{a.run}|{a.section_index}|{a.prev_turn_id}|{a.resp_turn_id}"
        rows.append({
            "act_id": hashlib.sha256(key.encode()).hexdigest()[:12],
            "side": a.side, "fg": a.fg, "run": a.run, "condition": a.condition,
            "section_index": a.section_index, "section_label": a.section_label,
            "act_index_in_section": a.act_index_in_section,
            "selection_mode": a.selection_mode,
            "prev_turn_id": a.prev_turn_id, "prev_speaker": a.prev_speaker,
            "prev_words": len(a.prev_text.split()),
            "resp_turn_id": a.resp_turn_id, "resp_speaker": a.resp_speaker,
            "resp_words": len(a.resp_text.split()), "n_clauses": a.n_clauses,
            "d1_div": a.d1_div, "d1_align": a.d1_align, "d1_hedge": a.d1_hedge,
            "d1_div_hits": "|".join(a.d1_div_hits),
            "d1_align_hits": "|".join(a.d1_align_hits),
            "d1_label": _label(a.d1_div, a.d1_align),
            "d1_div_full": a.d1_div_full, "d1_align_full": a.d1_align_full,
            "d1_label_full": _label(a.d1_div_full, a.d1_align_full),
            "prev_text": a.prev_text, "resp_text": a.resp_text,
        })
    rows.sort(key=lambda r: (r["side"], r["fg"], r["run"], r["section_index"],
                             r["act_index_in_section"]))

    out = _OUT_DIR / "response_acts.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader()
        w.writerows(rows)

    (_OUT_DIR / "section_skips.json").write_text(
        json.dumps(skipped, indent=2, ensure_ascii=False), encoding="utf-8")

    h = [r for r in rows if r["side"] == "human"]
    s = [r for r in rows if r["side"] == "synthetic"]
    print(f"response acts: {len(rows)}  (human {len(h)}, synthetic {len(s)})")
    for side, sub in (("human", h), ("synthetic", s)):
        n = max(1, len(sub))
        cl = sum(r["n_clauses"] for r in sub) / n
        for col, tag in (("d1_label", "opening (primary)"), ("d1_label_full", "whole turn (sens.)")):
            n_div = sum(1 for r in sub if r[col] == "divergence")
            n_al = sum(1 for r in sub if r[col] == "alignment")
            n_mx = sum(1 for r in sub if r[col] == "mixed")
            print(f"  {side:<10} {tag:<19} divergence {n_div:>4} ({100*n_div/n:5.1f}%)  "
                  f"alignment {n_al:>4} ({100*n_al/n:5.1f}%)  mixed {n_mx:>3}")
        print(f"  {side:<10} mean clauses/act {cl:.1f}")
    print(f"section skips: {len(skipped)}  ->  {_OUT_DIR / 'section_skips.json'}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
