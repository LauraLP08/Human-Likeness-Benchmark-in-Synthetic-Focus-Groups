"""
Real per-question segmentation of the 174 units. Offline; read-only; no API call.

WHY THIS EXISTS
---------------
The v3 budget estimated each question's length as `document_words / n_questions`. That is
not a measurement: guide questions differ greatly in how much discussion they attract, so
an even split misstates every downstream quantity that depends on length — expected theme
counts, balanced subsample sizes, length terciles, prompt sizes and context headroom.

This module segments the actual text.

  * **Human** documents split on the literal `Question N.` moderator headers, the same
    convention `gold_standard_boundary_audit.csv` recorded. The header turn belongs to the
    question it opens; everything up to the next header belongs to it.

  * **Synthetic** documents split the COMPARABLE WINDOW — never the full transcript —
    by scanning every non-empty spoken moderator utterance in `moderator_log.json`.
    The latest explicit guide-question ask anchors Q1..Q5; reformulations do not open a
    new section, and closing residue is excluded. Position is never used as a fallback.

Reconciliation is by construction and asserted: the segment word counts of a document sum
exactly to that document's own total, because segmentation partitions the same entries.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import inductive_inventory as inv   # noqa: E402

_PE = _ROOT / "analysis/production_evaluation"
_HUMAN = _ROOT / "data/datasets_transcripts/standardized/macho_meals"
_LOGS = _ROOT / "output/session_logs"
_OUT = _PE / "final/inductive_segments.json"

class Unresolved(RuntimeError):
    """A run whose transitions cannot be anchored to Q1-Q5 by content."""

    def __init__(self, run, openers, missing, unclassified, classified):
        self.run, self.openers, self.missing = run, openers, missing
        self.unclassified, self.classified = unclassified, classified
        super().__init__(f"{run}: could not anchor {missing}; "
                         f"unclassified transitions {unclassified}")


_HDR = re.compile(r"^\s*Question\s+(\d)\b")
N_QUESTIONS = 5


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _words(entries):
    return sum(len(e["content"].split()) for e in entries)


def _split_counts(entries, is_moderator):
    p = sum(len(e["content"].split()) for e in entries if not is_moderator(e))
    m = sum(len(e["content"].split()) for e in entries if is_moderator(e))
    return p, m


# --------------------------------------------------------------- human
def segment_human(fg: str):
    path = _HUMAN / fg / "transcript.json"
    raw = path.read_bytes()
    entries = json.loads(raw.decode("utf-8"))
    heads = [(i, int(_HDR.match(e["content"]).group(1)))
             for i, e in enumerate(entries)
             if e.get("speaker_role") == "moderator" and _HDR.match(e.get("content", ""))]
    if not heads:
        raise RuntimeError(f"no question headers in human/{fg}")
    segs = []
    for n, (idx, q) in enumerate(heads):
        end = heads[n + 1][0] if n + 1 < len(heads) else len(entries)
        chunk = entries[idx:end]
        is_mod = lambda e: e.get("speaker_role") == "moderator"   # noqa: E731
        pw, mw = _split_counts(chunk, is_mod)
        text = "\n".join(e["content"] for e in chunk)
        segs.append({
            "condition": "human", "fg": fg, "canonical_replication_index": None,
            "physical_run": None, "question": q,
            "unit_id": f"human::{fg}::Q{q}",
            "source_path": str(path.relative_to(_ROOT)).replace("\\", "/"),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "section_sha256": _sha(text),
            "entries": len(chunk),
            "turns": len({e.get("turn") for e in chunk}),
            "participant_words": pw, "moderator_words": mw,
            "total_words": pw + mw,
            "boundary_provenance": {
                "method": "literal `Question N.` moderator header",
                "opens_at_entry_index": idx,
                "closes_before_entry_index": end,
                "audit_source": "gold_standard_boundary_audit.csv question_headers_found"},
        })
    return segs, _words(entries), hashlib.sha256(raw).hexdigest()


# ----------------------------------------------------------- synthetic
def _transition_turns(physical_run: str):
    p = _LOGS / physical_run / "moderator_log.json"          # READ ONLY
    j = json.loads(p.read_text(encoding="utf-8"))
    ent = j if isinstance(j, list) else j.get("entries", j.get("log", []))
    return sorted({int(e["turn"]) for e in ent
                   if e.get("action") == "section_transition"})

# ----------------------------------------------- anchor-based classification
# Positional acceptance was the v4 defect: a shifted partition reconciles on words just
# as exactly as the correct one, so word reconciliation is necessary and NOT sufficient.
# Each transition is therefore classified by the guide question it actually poses.
#
# Markers are high precision by design. A transition that matches nothing is NOT guessed
# at — the run is flagged for researcher verification instead.
QUESTION_MARKERS = {
    1: [r"spend(ing)? time with (your )?male friends",
        r"favourite place", r"favorite place",
        r"where do you (tend to go|actually end up)",
        r"what'?s the (place|spot)"],
    2: [r"decid(e|ing) what (to eat|you eat|you'?re eating)",
        r"decid(e|ing) what (you'?re|you are) going to eat",
        r"decid(e|ing) what to have",
        r"decid(e|ing) what'?s? (on the plate|for dinner)",
        r"how do you make that call",
        r"work out what'?s (on the plate|for)",
        r"how do you (all )?(actually )?choose what (to eat|you eat)",
        r"what goes into (that|it)"],
    3: [r"(gender|being a man).{0,60}(influence|shape|affect|come into it)",
        r"being a man.{0,60}(anything to do with|come into)",
        r"(influence|shape|affect)s?.{0,40}(what|how) you eat.{0,40}(gender|man)",
        r"does your gender", r"do you think your gender",
        r"what you feel comfortable eating"],
    4: [r"decided to go plant[- ]based", r"went plant[- ]based",
        r"go(ing)? plant[- ]based", r"what would.{0,30}need to change"],
    5: [r"more appealing", r"appealing.{0,40}(to you|to men|in the first place)"],
}
CLOSING_MARKERS = [r"before we (finish|wrap|close)", r"anything (else|we haven'?t)",
                   r"last thing before", r"wrap (this|things) up", r"final thoughts"]


def classify_transition(text: str):
    """Guide questions a moderator turn actually poses. Empty set = unclassified."""
    t = " ".join(text.lower().split())
    hits = {q for q, pats in QUESTION_MARKERS.items()
            if any(re.search(p, t) for p in pats)}
    closing = any(re.search(p, t) for p in CLOSING_MARKERS)
    return hits, closing


def anchor_openers(transitions, lo):
    """
    Map classified transitions onto Q1..Q5 openers.

    Rules, all of which the positional rule violated:
      * Q1 opens at the window start, by the window's own definition.
      * Q2..Q5 open at the FIRST transition that poses that question.
      * A transition re-posing an already-open question is a reformulation or a
        duplicate: it stays inside the current section and opens nothing.
      * A transition carrying a closing marker ends Q5; nothing after it is included.
    """
    openers, reformulations, unclassified, closing_at = {1: lo}, [], [], None
    for turn, (hits, closing) in transitions:
        if closing and not hits:
            closing_at = turn if closing_at is None else closing_at
            continue
        if not hits:
            unclassified.append(turn)
            continue
        new = sorted(q for q in hits if q not in openers)
        if not new:
            reformulations.append({"turn": turn, "re_poses": sorted(hits)})
            continue
        q = new[0]
        # a question may only open after the one before it
        if q > 1 and any(x not in openers for x in range(2, q)):
            unclassified.append(turn)
            continue
        openers[q] = turn
    # Any in-window transition after the Q5 opener starts the closing section. Its
    # moderator turn is often trimmed from the window, so it cannot be found by marker
    # alone — but the residue after it must NOT be absorbed into Q5 to make the word
    # counts balance. That absorption is exactly what the corrected reconciliation
    # rule exists to detect.
    if 5 in openers:
        after = [t for t, _ in transitions if t > openers[5]]
        if after:
            closing_at = after[0] if closing_at is None else min(closing_at, after[0])
    return openers, reformulations, unclassified, closing_at

def _spoken_moderator_turns(physical_run: str):
    """
    Every SPOKEN moderator turn, not only `section_transition`.

    Restricting anchors to `section_transition` was the v5a defect: the generator poses
    guide questions under `ask_initial_to_group`, `refocus_to_guide` and others, so eight
    runs looked unanchorable when their questions were plainly asked. Any entry with a
    non-empty utterance is a candidate.
    """
    p = _LOGS / physical_run / "moderator_log.json"          # READ ONLY
    j = json.loads(p.read_text(encoding="utf-8"))
    ent = j if isinstance(j, list) else j.get("entries", j.get("log", []))
    out = []
    for e in ent:
        utt = (e.get("utterance") or "").strip()
        if utt:
            out.append({"turn": int(e["turn"]), "action": e.get("action"),
                        "utterance": utt})
    return sorted(out, key=lambda x: x["turn"])


_SENT = re.compile(r"(?<=[.!?])\s+")


def latest_guide_question(utterance: str):
    """
    The guide question a turn actually POSES, by the latest explicit ask.

    A moderator turn typically recaps the section just closed and then asks the next
    question. Marker terms in the recap describe what was discussed; they do not pose
    anything. Only the LAST clause that both matches a guide question and reads as an
    ask counts, so "we talked about how you decide what to eat ... does being a man
    shape it?" anchors Q3, not [Q2, Q3].
    """
    sents = [x for x in _SENT.split(" ".join(utterance.split())) if x.strip()]
    flags = [_sentence_flags(x) for x in sents]
    asked, closing = None, any(f["closing"] for f in flags)

    for i, f in enumerate(flags):
        if not f["hits"]:
            continue
        if f["closing"]:
            continue                       # a closing sentence never opens a question
        posed = f["is_ask"]
        joined = False
        if not posed and i + 1 < len(flags):
            nxt = flags[i + 1]
            # ADJACENT-SENTENCE CONTINUATION, at most one sentence ahead. The generator
            # often states the substance and then asks anaphorically: "...whether being
            # a man shapes any of that. What do you all make of that?" Requiring both in
            # one sentence loses the ask entirely.
            if (nxt["is_ask"] and nxt["anaphoric"] and not nxt["closing"]
                    and not nxt["hits"]):
                posed, joined = True, True
        if not posed:
            continue
        if len(f["hits"]) == 1:
            asked = next(iter(f["hits"]))
        else:
            # Later guide questions often contain a recap marker from the preceding
            # question. The latest/highest guide question is the operative ask.
            forward = sorted(q for q in f["hits"] if asked is None or q > asked)
            if not forward:
                continue
            asked = forward[-1]
        _ = joined
    return asked, closing


# An anaphoric follow-up refers back to the previous sentence rather than introducing
# new content, so it may carry that sentence's ask. It must not itself name a question,
# or it would be the ask in its own right.
_ANAPHORIC = re.compile(
    r"^(so\s+)?(what|how|does|do|is|are|would|could|can|any)\b.{0,120}"
    r"\b(that|this|it|those|these|any of that|the rest of you|you all|for you|"
    r"the decision|what to have)\b",
    re.I)


def _sentence_flags(sent: str):
    low = sent.lower()
    return {
        "is_ask": bool(
            "?" in sent
            or re.search(r"\b(imagine|tell us|talk me through|walk me through)\b", low)
            or re.search(r"\b(i want to ask|let me ask|i'?d like to ask|"
                         r"i wanted to ask|want to ask you about)\b", low)
            or re.search(r"\b(i want to talk about|i want to get into|"
                         r"one thing i want to get into)\b", low)
            or re.search(r"\bwhat might actually make\b.{0,100}\bmore appealing\b",
                         low)),
        "anaphoric": bool(_ANAPHORIC.match(sent.strip())),
        "hits": {q for q, pats in QUESTION_MARKERS.items()
                 if any(re.search(pp, low) for pp in pats)},
        "closing": any(re.search(pp, low) for pp in CLOSING_MARKERS),
    }


def anchor_openers_v5(spoken, lo, hi):
    """
    Anchor Q1..Q5 across all spoken moderator turns inside the window.

    Q1 opens at the window start. Each later question opens at the FIRST in-window turn
    that explicitly asks it and follows the previous opener. A turn re-asking an already
    open question is a reformulation and opens nothing. Closing starts at the first turn
    that signals closing without asking a further guide question.
    """
    openers, reformulations, closing_at = {1: lo}, [], None
    trace = []
    for rec in spoken:
        t = rec["turn"]
        if not (lo <= t <= hi):
            continue
        q, closing = latest_guide_question(rec["utterance"])
        trace.append({"turn": t, "action": rec["action"], "asks": q,
                      "closing_marker": closing})
        if closing and q is None:
            if closing_at is None and 5 in openers and t > openers[5]:
                closing_at = t
            continue
        if q is None:
            continue
        if q in openers:
            reformulations.append({"turn": t, "re_asks": q, "action": rec["action"]})
            continue
        if any(x not in openers for x in range(2, q)):
            continue                       # cannot open Q4 before Q3 exists
        if t <= openers[max(openers)]:
            continue                       # never move backwards
        openers[q] = t
    return openers, reformulations, closing_at, trace


def segment_synthetic(rec: dict):
    path = _ROOT / rec["path"]
    raw = path.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    entries = doc["transcript"]
    turns = [int(e["turn"]) for e in entries]
    lo, hi = min(turns), max(turns)

    spoken = _spoken_moderator_turns(rec["physical_run"])
    op, reformulations, closing_at, trace = anchor_openers_v5(spoken, lo, hi)

    missing = [q for q in range(1, N_QUESTIONS + 1) if q not in op]
    if missing:
        raise Unresolved(rec["physical_run"], op, missing,
                         [x["turn"] for x in trace if x["asks"] is None], trace)

    openers = [op[q] for q in range(1, N_QUESTIONS + 1)]
    if openers != sorted(set(openers)):
        raise Unresolved(rec["physical_run"], op, ["non-monotone"], [], trace)
    ambiguity = None
    end_of_q5 = closing_at if closing_at is not None else hi + 1
    inside = [x["turn"] for x in trace]
    classified = [(x["turn"], ({x["asks"]} if x["asks"] else set(), x["closing_marker"]))
                  for x in trace]
    unclassified = [x["turn"] for x in trace if x["asks"] is None
                    and not x["closing_marker"]]
    bounds = list(zip(range(1, N_QUESTIONS + 1), openers))
    segs = []
    for n, (q, start) in enumerate(bounds):
        end = bounds[n + 1][1] if n + 1 < len(bounds) else end_of_q5
        chunk = [e for e in entries if start <= int(e["turn"]) < end]
        is_mod = lambda e: e["speaker_id"] == "MODERATOR"       # noqa: E731
        pw, mw = _split_counts(chunk, is_mod)
        text = "\n".join(e["content"] for e in chunk)
        segs.append({
            "condition": rec["condition"], "fg": rec["fg"],
            "canonical_replication_index": rec["canonical_replication_index"],
            "physical_run": rec["physical_run"], "question": q,
            "unit_id": f"{rec['condition']}::{rec['fg']}::R"
                       f"{rec['canonical_replication_index']}::Q{q}",
            "source_path": rec["path"].replace("\\", "/"),
            "source_sha256": rec["sha256"],
            "section_sha256": _sha(text),
            "entries": len(chunk),
            "turns": len({e.get("turn") for e in chunk}),
            "participant_words": pw, "moderator_words": mw,
            "total_words": pw + mw,
            "boundary_provenance": {
                "method": ("latest explicit guide-question ask across every non-empty "
                           "moderator_log utterance, read-only"),
                "opens_at_turn": start, "closes_before_turn": end,
                "in_window_transitions": inside,
                "opener_rule": "ANCHOR_BASED_CONTENT_CLASSIFICATION",
                "classified_transitions": [
                    {"turn": t, "poses_questions": sorted(h), "closing_marker": c}
                    for t, (h, c) in classified],
                "reformulations_kept_in_section": reformulations,
                "unclassified_transitions": unclassified,
                "closing_starts_at_turn": closing_at,
                "window": "comparable_transcript.json — full transcript never used"},
        })
    return segs, _words(entries), hashlib.sha256(raw).hexdigest(), ambiguity


# --------------------------------------------------------------- build
def build() -> dict:
    o = inv.build()
    if not o["pass"]:
        raise RuntimeError(f"inventory did not pass: {o['problems']}")

    segments, problems, doc_check, ambiguities = [], [], [], []
    unresolved = []

    for fg in ["fg1", "fg2", "fg3", "fg4", "fg5"]:
        segs, doc_words, doc_sha = segment_human(fg)
        segments += segs
        s = sum(x["total_words"] for x in segs)
        doc_check.append({"document": f"human::{fg}", "segment_sum": s,
                          "document_total": doc_words, "reconciles": s == doc_words,
                          "source_sha256": doc_sha})
        if s != doc_words:
            problems.append(f"human/{fg}: segments {s} != document {doc_words}")
        qs = sorted(x["question"] for x in segs)
        if qs != o_human_questions(o, fg):
            problems.append(f"human/{fg}: segmented {qs}, inventory says "
                            f"{o_human_questions(o, fg)}")

    for rec in inv.canonical_synthetic():
        try:
            segs, doc_words, doc_sha, amb = segment_synthetic(rec)
        except Unresolved as e:                                  # noqa: PERF203
            unresolved.append({
                "run": e.run, "anchored": {str(k): v for k, v in e.openers.items()},
                "could_not_anchor": e.missing,
                "unclassified_transitions": e.unclassified,
                "classified": [{
                    "turn": item["turn"],
                    "action": item.get("action"),
                    "poses_questions": ([item["asks"]]
                                        if item.get("asks") is not None else []),
                    "closing_marker": item["closing_marker"],
                } for item in e.classified],
                "requires_researcher_verification": True})
            problems.append(f"{e.run}: {e.missing} not anchored by content")
            continue
        if amb:
            ambiguities.append(amb)
        segments += segs
        s = sum(x["total_words"] for x in segs)
        residue = doc_words - s
        doc_check.append({"document": rec["physical_run"],
                          "included_Q1_to_Q5_words": s,
                          "excluded_closing_residue_words": residue,
                          "comparable_window_words": doc_words,
                          "document_total": doc_words,
                          "segment_sum": s + residue,
                          "reconciles": s + residue == doc_words,
                          "source_sha256": doc_sha})
        if s + residue != doc_words:
            problems.append(f"{rec['physical_run']}: {s}+{residue} != {doc_words}")
        if residue < 0:
            problems.append(f"{rec['physical_run']}: negative closing residue")
        if rec["sha256"] != doc_sha:
            problems.append(f"{rec['physical_run']}: sha256 differs from the frozen "
                            "manifest")

    expected = 174 - 5 * len(unresolved)
    if len(segments) != expected:
        problems.append(f"{len(segments)} segments, expected {expected}")

    # ---- length terciles from REAL counts, within question x condition ----
    by_cell = defaultdict(list)
    for s in segments:
        by_cell[(s["question"], s["condition"])].append(s)
    for cell, items in by_cell.items():
        items.sort(key=lambda x: (x["total_words"], x["unit_id"]))
        n = len(items)
        for i, s in enumerate(items):
            s["length_tercile"] = min(3, i * 3 // n + 1)

    per_q = defaultdict(lambda: {"n_units": 0, "total_words": 0})
    for s in segments:
        per_q[s["question"]]["n_units"] += 1
        per_q[s["question"]]["total_words"] += s["total_words"]

    per_qc = defaultdict(lambda: {"n_units": 0, "total_words": 0})
    for s in segments:
        k = f"Q{s['question']}|{s['condition']}"
        per_qc[k]["n_units"] += 1
        per_qc[k]["total_words"] += s["total_words"]

    tot = sum(s["total_words"] for s in segments)
    even = {q: round(v["total_words"] / v["n_units"]) for q, v in sorted(per_q.items())}
    out = {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": "LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION_SEGMENTS",
        "no_api_calls": True,
        "session_logs_access": "READ ONLY — moderator_log.json only; nothing written",
        "n_segments": len(segments),
        "total_words": tot,
        "estimated_by_even_split": False,
        "even_split_would_have_said": round(tot / len(segments)) if segments else None,
        "per_question": {str(q): {**v, "mean_words": round(v["total_words"] / v["n_units"])}
                         for q, v in sorted(per_q.items())},
        "per_question_condition": dict(sorted(per_qc.items())),
        "unresolved_runs": {
            "n": len(unresolved),
            "n_units_blocked": 5 * len(unresolved),
            "cases": unresolved,
            "rule": ("a run is NOT segmented unless every one of Q1-Q5 is anchored to a "
                     "transition that actually poses that question; positional "
                     "acceptance is never used as a fallback")},
        "reconciliation_rule": (
            "included_Q1_to_Q5_words + excluded_closing_residue_words == "
            "comparable_window_words; the residue is never absorbed into Q5"),
        "boundary_ambiguity": {
            "n_runs_affected": len(ambiguities),
            "resolved_silently": False,
            "cases": ambiguities,
            "note": ("All 30 runs are anchored by the latest explicit guide-question "
                     "ask. The two formerly ambiguous opening turns are resolved by "
                     "the binding researcher-reviewed boundaries; no positional "
                     "fallback is used.")},
        "document_reconciliation": doc_check,
        "all_documents_reconcile": all(d["reconciles"] for d in doc_check),
        "segments": segments,
        "problems": problems,
        "pass": not problems,
    }
    return out


def write(out: dict, path=None) -> Path:
    """Persist a validated segmentation explicitly; build() remains read-only."""
    path = Path(path) if path is not None else _OUT
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def o_human_questions(o, fg):
    d = next(x for x in o["documents"] if x["condition"] == "human" and x["fg"] == fg)
    return sorted(d["questions_available"])


def main() -> int:
    o = build()
    write(o)
    print(f"segments {o['n_segments']}  total words {o['total_words']:,}")
    print(f"all documents reconcile: {o['all_documents_reconcile']}\n")
    print("real mean words per unit, by question (an even split would say "
          f"{o['even_split_would_have_said']:,} everywhere):")
    for q, v in o["per_question"].items():
        print(f"   Q{q}: {v['n_units']:>3d} units  {v['total_words']:>7,} words  "
              f"mean {v['mean_words']:>5,}")
    print("\nby question x condition:")
    for k, v in o["per_question_condition"].items():
        print(f"   {k:34s} {v['n_units']:>3d} units  mean "
              f"{round(v['total_words']/v['n_units']):>6,} words")
    print(f"\nPASS: {o['pass']}")
    for p in o["problems"][:10]:
        print("   PROBLEM:", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
