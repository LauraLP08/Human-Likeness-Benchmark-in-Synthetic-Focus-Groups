"""
Macho Meals production evaluation — derive the human-comparable analytical window.

WHY THIS EXISTS
The five standardized human transcripts begin directly at the moderator's
"Question 1. What's your favourite place in your city to spend time with your male
friends? ..." and contain no general introduction, no participant name/location
round, and no formal closing section. A synthetic run has all three. Comparing a
whole synthetic transcript against a human transcript therefore compares unlike
things.

THE WINDOW — one rule for all 30 runs
    START: the exact character offset, inside the moderator entry that poses
           Question 1, at which the substantive Q1 ask begins. Everything before
           it is dropped; the text from it onward is retained VERBATIM.
    END:   the last entry before the closing section.

Entry-level segmentation alone is not sufficient. The entry that opens Question 1
routinely fuses residue in front of the ask — participant names, a location recap
of the introductions, a welcome, confidentiality/instruction text, or a summary of
the presentation round — and in two runs it fuses the entire session instructions
and the Q1 ask into one entry. Sub-entry trimming is therefore applied uniformly,
so a single segmentation rule governs the corpus.

The retained boundary text is never paraphrased, normalised, reconstructed, or
replaced with the guide's scripted question. It is a character slice of the source.

NON-DESTRUCTIVE
No original transcript is modified and nothing is written into
`output/session_logs/`. Each derived transcript is written to
`analysis/production_evaluation/comparable_transcripts/<run>/comparable_transcript.json`
with a provenance block naming its source, source hash, boundary offset and both
boundary-text hashes.

BOUNDARY SIGNALS
  1. Section structure from `moderator_log.json` `action == "section_transition"`,
     cross-checked against `state_turn_*.json` `current_section_index` (which is
     off by one at every boundary, so disagreement is expected there and nowhere
     else). Used for the END boundary and for reporting.
  2. Sub-entry Q1 offset from `comparable_window_boundary.find_q1_offset`, by
     ANCHOR-AND-EXTEND: anchor on the latest sentence-aligned suffix that still
     poses Q1 (the minimal ask), then extend backward only across residue-free
     sentences positively identified as part of the ask. Never a fuzzy phrase
     match, never a fixed turn count, never an "earliest clean offset" scan —
     that variant lets an unlisted residue phrasing survive silently.
  3. Normalized guide questions, used to VALIDATE and report, never to place a
     boundary: the moderator paraphrases rather than reciting.

Any run whose boundary cannot be established, or whose retained text fails the
residue gate, is reported HUMAN_REVIEW_REQUIRED and no file is written.

Usage:
    py scripts/build_comparable_window.py
    py scripts/build_comparable_window.py --print-boundaries            # all runs
    py scripts/build_comparable_window.py --print-boundaries RUN [RUN]  # selected
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from comparable_window_boundary import (                      # noqa: E402
    Q1_DISTINCTIVE,
    find_q1_offset,
    poses_q1,
    residue_in,
    sha256_text,
)
from phase0_macho_meals_readiness_audit import WHITELIST      # noqa: E402
from tier2b_segmentation import (                             # noqa: E402
    crosscheck_synthetic_against_state_files,
    load_guide_sections,
    segment_synthetic_by_guide,
)

_SESSION_LOGS = _REPO_ROOT / "output" / "session_logs"
_OUT_DIR = _REPO_ROOT / "analysis" / "production_evaluation"
_DERIVED_DIR = _OUT_DIR / "comparable_transcripts"

_QUESTION_OVERLAP_FLAG = 0.30

_STOPWORDS = {
    "a", "about", "all", "and", "any", "anything", "are", "as", "at", "be", "been",
    "but", "by", "can", "could", "do", "else", "feel", "for", "free", "from", "get",
    "go", "going", "had", "has", "have", "how", "i", "if", "in", "is", "it", "its",
    "just", "like", "me", "more", "much", "my", "no", "not", "of", "okay", "on",
    "or", "our", "out", "over", "s", "so", "some", "someone", "something", "that",
    "thats", "the", "their", "them", "then", "there", "these", "they", "this",
    "to", "up", "us", "very", "want", "was", "we", "were", "what", "whats", "when",
    "where", "which", "who", "why", "will", "with", "would", "you", "your", "yours",
}


def _sha256_file(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def _norm_tokens(s: str) -> set[str]:
    s = unicodedata.normalize("NFKC", s or "")
    s = (s.replace("’", "'").replace("‘", "'")
           .replace("“", '"').replace("”", '"')
           .replace("–", "-").replace("—", "-"))
    s = re.sub(r"[^a-z0-9\s']", " ", s.casefold())
    return {t for t in s.split() if t and t not in _STOPWORDS and len(t) > 2}


def _overlap(utterance: str, scripted_question: str) -> float:
    q = _norm_tokens(scripted_question)
    if not q:
        return 0.0
    return round(len(q & _norm_tokens(utterance)) / len(q), 3)


def _words(entries: list[dict]) -> int:
    return sum(len((e.get("content") or "").split()) for e in entries)


def _is_moderator(e: dict) -> bool:
    return (e.get("speaker_name") or "").lower() == "moderator"


def _q1_hits(text: str) -> int:
    toks = set(re.sub(r"[^a-z0-9\s']", " ", (text or "").casefold()).split())
    return len(Q1_DISTINCTIVE & toks)


# ---------------------------------------------------------------------------
# Per-run derivation
# ---------------------------------------------------------------------------

def build_window(run_name: str) -> dict:
    run_dir = _SESSION_LOGS / run_name
    src_path = run_dir / "transcript.json"
    guide_source = run_dir / "session_state_initial.json"

    row: dict = {"physical_run": run_name}
    entries = json.loads(src_path.read_text(encoding="utf-8"))
    guide = {s["section_index"]: s for s in load_guide_sections(guide_source)}

    seg = segment_synthetic_by_guide(src_path, guide_source)
    cross = crosscheck_synthetic_against_state_files(seg, run_dir)
    row["state_crosscheck_agree"] = cross["entries_agree"]
    row["state_crosscheck_boundary_diffs"] = cross["entries_differ_on_boundary_turn"]
    row["state_crosscheck_conflicts"] = cross["entries_in_conflict"]
    row["total_source_words"] = _words(entries)
    row["total_source_entries"] = len(entries)

    problems: list[str] = []
    if seg.warnings:
        problems += [f"segmentation_warning: {w}" for w in seg.warnings]
    if not cross["clean"]:
        problems.append(f"state_crosscheck_conflicts={cross['entries_in_conflict']}")
    if problems:
        row["segmentation_verdict"] = "HUMAN_REVIEW_REQUIRED"
        row["problems"] = " ;; ".join(problems)
        return row

    # --- roster names, from the run's own state ----------------------------
    roster: set[str] = set()
    try:
        st = json.loads((run_dir / "session_state_initial.json").read_text(encoding="utf-8"))
        roster = {(p.get("name") or "").strip() for p in st.get("participants", {}).values()}
        roster = {n for n in roster if len(n) > 2}
    except Exception:                                          # noqa: BLE001
        pass
    row["roster_names"] = "|".join(sorted(roster))

    # --- START: first moderator entry that poses Q1, then sub-entry offset --
    b_idx = next((i for i, e in enumerate(entries)
                  if _is_moderator(e) and poses_q1(e.get("content") or "")), None)
    if b_idx is None:
        row["segmentation_verdict"] = "HUMAN_REVIEW_REQUIRED"
        row["problems"] = "no moderator entry in the transcript poses Question 1"
        return row

    boundary_text = entries[b_idx].get("content") or ""
    offset, review_status, review_note = find_q1_offset(boundary_text, roster)
    retained = boundary_text[offset:] if offset is not None else ""

    row.update({
        "source_entry_index": b_idx,
        "source_entry_turn": entries[b_idx].get("turn"),
        "source_character_start": offset,
        "boundary_entry_section": next(
            (s for s in seg.sections if b_idx in seg.sections[s].entry_indices), None),
        "original_boundary_entry_chars": len(boundary_text),
        "original_boundary_entry_words": len(boundary_text.split()),
        "retained_boundary_text_chars": len(retained),
        "retained_boundary_text_words": len(retained.split()),
        "original_boundary_entry_sha256": sha256_text(boundary_text),
        "retained_boundary_text_sha256": sha256_text(retained) if retained else None,
        "boundary_review_status": review_status,
        "boundary_review_note": review_note,
    })

    if offset is None:
        row["segmentation_verdict"] = "HUMAN_REVIEW_REQUIRED"
        row["problems"] = review_note
        return row

    # --- hard validation of the retained first entry (requirement 7) --------
    resid = residue_in(retained, roster)
    row["retained_residue_classes"] = "|".join(resid) or "none"
    row["retained_poses_q1"] = poses_q1(retained)
    row["q1_distinctive_tokens_in_retained"] = f"{_q1_hits(retained)}/{len(Q1_DISTINCTIVE)}"
    row["verbatim_slice_verified"] = boundary_text[offset:] == retained
    if resid or not row["retained_poses_q1"] or not row["verbatim_slice_verified"]:
        row["segmentation_verdict"] = "HUMAN_REVIEW_REQUIRED"
        row["problems"] = (f"retained boundary text failed validation: residue="
                           f"{resid or 'none'} poses_q1={row['retained_poses_q1']} "
                           f"verbatim={row['verbatim_slice_verified']}")
        return row

    # --- END: last entry before the closing section -------------------------
    if 6 not in seg.sections or not seg.sections[6].entry_indices:
        row["segmentation_verdict"] = "HUMAN_REVIEW_REQUIRED"
        row["problems"] = "closing section (6) not present; end boundary undetermined"
        return row
    closing_start = min(seg.sections[6].entry_indices)
    first_i, last_i = b_idx, closing_start - 1
    if last_i <= first_i:
        row["segmentation_verdict"] = "HUMAN_REVIEW_REQUIRED"
        row["problems"] = f"window empty or inverted (first={first_i}, last={last_i})"
        return row

    included = [dict(entries[first_i], content=retained)] + entries[first_i + 1:last_i + 1]
    pre = entries[:first_i]
    prefix_words = len(boundary_text.split()) - len(retained.split())
    closing = entries[closing_start:]

    closing_entry = entries[closing_start]
    row["closing_boundary_overlap"] = _overlap(closing_entry.get("content") or "",
                                               guide[6].get("scripted_question", ""))
    row["closing_boundary_is_moderator"] = _is_moderator(closing_entry)
    row["q1_boundary_overlap"] = _overlap(retained, guide[1].get("scripted_question", ""))

    flags = []
    if (row["closing_boundary_overlap"] or 0) < _QUESTION_OVERLAP_FLAG:
        flags.append(f"closing_overlap_low({row['closing_boundary_overlap']})")
    if not row["closing_boundary_is_moderator"]:
        flags.append("closing_boundary_not_moderator_turn")
    row["validation_flags"] = "|".join(flags) or "none"

    src_sha = _sha256_file(src_path)
    payload = {
        "_provenance": {
            "derived_by": "scripts/build_comparable_window.py",
            "generated_utc": datetime.now(UTC).isoformat(),
            "source_transcript": str(src_path.relative_to(_REPO_ROOT)),
            "source_transcript_sha256": src_sha,
            "window": "q1_ask_to_end_of_last_substantive_section",
            "excluded": "all material before the Question-1 ask, and the closing section",
            "boundary_method": (
                "Section structure from moderator_log.section_transition, cross-checked "
                "against state_turn_*.json current_section_index. Sub-entry Question-1 "
                "offset by ANCHOR-AND-EXTEND: anchor on the latest sentence-aligned "
                "suffix of the boundary entry that still poses Question 1 (the minimal "
                "ask), then extend backward one sentence at a time only across sentences "
                "that are residue-free AND positively identified as part of the ask "
                "(carrying a Q1-distinctive token, or being an ask lead-in / short "
                "discourse connective); stop at the first sentence failing either test. "
                "Residue classes excluded: participant name, moderator self-introduction, "
                "welcome, instruction/confidentiality text, presentation summary. Because "
                "the boundary only ever moves earlier over text positively identified as "
                "part of the ask, residue is excluded by construction rather than by "
                "enumeration."),
            "boundary_algorithm": "anchor_and_extend_v1",
            "source_entry_index": b_idx,
            "source_entry_turn": entries[b_idx].get("turn"),
            "source_character_start": offset,
            "original_boundary_entry_sha256": row["original_boundary_entry_sha256"],
            "retained_boundary_text_sha256": row["retained_boundary_text_sha256"],
            "boundary_review_status": review_status,
            "boundary_review_note": review_note,
            "first_source_entry_index": first_i,
            "last_source_entry_index": last_i,
            "boundary_text_is_verbatim_slice": True,
            "note": ("Derived view. The source transcript is unmodified. The first entry's "
                     "content is a verbatim character slice of the source entry from "
                     "source_character_start onward - never paraphrased, normalised, "
                     "reconstructed, or replaced with the guide's scripted question. Human "
                     "transcripts need no equivalent window: they already begin at Question 1 "
                     "and contain no introduction or closing section."),
        },
        "transcript": included,
    }
    out_dir = _DERIVED_DIR / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "comparable_transcript.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    row.update({
        "source_transcript_sha256": src_sha,
        "comparable_transcript_sha256": _sha256_file(out_path),
        "comparable_transcript_path": str(out_path.relative_to(_REPO_ROOT)),
        "first_included_entry_index": first_i,
        "last_included_entry_index": last_i,
        "first_included_turn": entries[first_i].get("turn"),
        "last_included_turn": entries[last_i].get("turn"),
        "included_sections": "q1_ask..end_of_last_substantive_section",
        "excluded_sections": "pre_q1_material|closing_section",
        "included_entries": len(included),
        "included_participant_turns": sum(1 for e in included if not _is_moderator(e)),
        "included_moderator_turns": sum(1 for e in included if _is_moderator(e)),
        "included_words": _words(included),
        "excluded_pre_q1_entries": len(pre),
        "excluded_pre_q1_words": _words(pre) + prefix_words,
        "excluded_boundary_prefix_words": prefix_words,
        "excluded_closing_entries": len(closing),
        "excluded_closing_words": _words(closing),
        "segmentation_verdict": "OK",
        "problems": "",
    })
    return row


# ---------------------------------------------------------------------------
# Boundary printing (requirement 9)
# ---------------------------------------------------------------------------

def render_boundary(run_name: str, row: dict) -> list[str]:
    """Return printable lines showing the original boundary entry and the
    retained substring, plus the window edges."""
    out: list[str] = []
    entries = json.loads((_SESSION_LOGS / run_name / "transcript.json").read_text(encoding="utf-8"))
    out.append("=" * 100)
    out.append(f"{run_name}    verdict={row['segmentation_verdict']}    "
               f"review={row.get('boundary_review_status')}")
    b = row.get("source_entry_index")
    if b is None:
        out.append(f"  {row.get('problems')}")
        return out

    original = entries[b].get("content") or ""
    off = row.get("source_character_start")
    out.append(f"  boundary entry index={b} turn={row.get('source_entry_turn')} "
               f"section={row.get('boundary_entry_section')}  offset={off}")
    out.append(f"  note: {row.get('boundary_review_note')}")
    out.append("  --- ORIGINAL BOUNDARY ENTRY (verbatim) " + "-" * 58)
    for line in re.sub(r"\s+", " ", original).strip()[:1200].split("\n"):
        out.append("    " + line)
    if off:
        out.append("  --- DROPPED PREFIX (chars 0.." + str(off) + ") " + "-" * 52)
        out.append("    " + re.sub(r"\s+", " ", original[:off]).strip()[:900])
    out.append("  --- RETAINED SUBSTRING (verbatim, sent to evaluator) " + "-" * 44)
    out.append("    " + re.sub(r"\s+", " ", original[off:]).strip()[:900])
    out.append(f"  residue={row.get('retained_residue_classes')}  "
               f"q1_tokens={row.get('q1_distinctive_tokens_in_retained')}  "
               f"verbatim_slice={row.get('verbatim_slice_verified')}")

    if row["segmentation_verdict"] == "OK":
        last_i = row["last_included_entry_index"]
        out.append("  --- LAST INCLUDED ENTRY " + "-" * 72)
        e = entries[last_i]
        out.append(f"    [{last_i}] {e.get('speaker_name')}: "
                   + re.sub(r"\s+", " ", e.get("content") or "").strip()[:220])
        out.append("  --- FIRST EXCLUDED CLOSING ENTRY " + "-" * 63)
        e = entries[last_i + 1]
        out.append(f"    [{last_i + 1}] {e.get('speaker_name')}: "
                   + re.sub(r"\s+", " ", e.get("content") or "").strip()[:220])
    return out


class IntegrityError(AssertionError):
    """Raised when a derived-window invariant fails. Never downgraded to a warning."""


def assert_integrity(rows: list[dict], expected_runs: int) -> list[str]:
    """
    Hard-fail verification of every derived window. Each check re-reads the
    artefacts from disk rather than trusting the in-memory row, so a bug in the
    builder cannot mark its own output valid.

    Raises IntegrityError listing every failure. Returns the passed-check names.
    """
    failures: list[str] = []
    passed: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        (passed if ok else failures).append(name if ok else f"{name}: {detail}")

    # 1. Row count
    check("audit_rows_is_expected", len(rows) == expected_runs,
          f"expected {expected_runs} audit rows, got {len(rows)}")

    # 2. Derived transcript count
    derived = sorted(_DERIVED_DIR.glob("*/comparable_transcript.json"))
    check("derived_transcripts_is_expected", len(derived) == expected_runs,
          f"expected {expected_runs} derived transcripts, got {len(derived)}")

    # 3. Zero review-required / non-OK verdicts
    not_ok = [r["physical_run"] for r in rows if r.get("segmentation_verdict") != "OK"]
    check("zero_review_required", not not_ok, f"{len(not_ok)} run(s) not OK: {not_ok}")
    needs_review = [r["physical_run"] for r in rows
                    if r.get("boundary_review_status") == "HUMAN_REVIEW_REQUIRED"]
    check("zero_human_review_status", not needs_review,
          f"{len(needs_review)} run(s) flagged HUMAN_REVIEW_REQUIRED: {needs_review}")

    corpus_included = corpus_pre = corpus_closing = corpus_total = 0

    for r in rows:
        run = r["physical_run"]
        if r.get("segmentation_verdict") != "OK":
            continue
        path = _DERIVED_DIR / run / "comparable_transcript.json"
        if not path.exists():
            check(f"{run}/derived_exists", False, "derived transcript missing")
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        prov = d["_provenance"]
        src = json.loads((_REPO_ROOT / prov["source_transcript"]).read_text(encoding="utf-8"))
        b = prov["source_entry_index"]
        off = prov["source_character_start"]
        original = src[b].get("content") or ""
        retained = d["transcript"][0].get("content") or ""

        # 4. Hashes valid — recomputed from source and from the retained slice
        check(f"{run}/original_boundary_sha256",
              sha256_text(original) == prov["original_boundary_entry_sha256"],
              "recorded original boundary hash does not match the source entry")
        check(f"{run}/retained_boundary_sha256",
              sha256_text(retained) == prov["retained_boundary_text_sha256"],
              "recorded retained hash does not match the retained text")
        check(f"{run}/source_transcript_sha256",
              _sha256_file(_REPO_ROOT / prov["source_transcript"]) == prov["source_transcript_sha256"],
              "source transcript hash changed since derivation")

        # 5. Verbatim boundary slice
        check(f"{run}/verbatim_boundary_slice", original[off:] == retained,
              "retained boundary text is not a verbatim slice of the source entry")
        check(f"{run}/retained_poses_q1", poses_q1(retained),
              "retained boundary text does not pose Question 1")
        roster = {n for n in (r.get("roster_names") or "").split("|") if n}
        resid = residue_in(retained, roster)
        check(f"{run}/retained_residue_free", not resid, f"residue present: {resid}")

        # 6. Subsequent entries byte-identical to source
        tail_ok = all(d["transcript"][i] == src[b + i] for i in range(1, len(d["transcript"])))
        check(f"{run}/tail_entries_byte_identical", tail_ok,
              "an entry after the boundary differs from the source transcript")

        # 7. Exact closing boundary — window ends immediately before the closing section
        last_i = prov["last_source_entry_index"]
        check(f"{run}/window_contiguous", last_i == b + len(d["transcript"]) - 1,
              "window length does not match its recorded source span")
        seg = segment_synthetic_by_guide(
            _SESSION_LOGS / run / "transcript.json",
            _SESSION_LOGS / run / "session_state_initial.json")
        closing_start = min(seg.sections[6].entry_indices)
        check(f"{run}/closing_boundary_exact", last_i == closing_start - 1,
              f"window ends at {last_i}, closing section starts at {closing_start}")

        # 8. Per-run word reconciliation
        inc = _words(d["transcript"])
        pre = _words(src[:b]) + (len(original.split()) - len(retained.split()))
        clo = _words(src[closing_start:])
        tot = _words(src)
        check(f"{run}/word_reconciliation", inc + pre + clo == tot,
              f"included({inc}) + pre({pre}) + closing({clo}) != source total({tot})")
        check(f"{run}/audit_included_words_matches", r["included_words"] == inc,
              f"audit row says {r['included_words']}, recomputed {inc}")
        corpus_included += inc
        corpus_pre += pre
        corpus_closing += clo
        corpus_total += tot

    # 9. Corpus-level word reconciliation
    check("corpus_word_reconciliation",
          corpus_included + corpus_pre + corpus_closing == corpus_total,
          f"corpus included({corpus_included}) + pre({corpus_pre}) + closing({corpus_closing}) "
          f"!= total({corpus_total})")

    if failures:
        raise IntegrityError(
            f"{len(failures)} integrity check(s) FAILED:\n  "
            + "\n  ".join(failures))
    return passed


def main(print_runs: list[str] | None) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 84)
    print("  COMPARABLE WINDOW — sub-entry Question-1 boundary, one rule for all runs")
    print(f"  {len(WHITELIST)} canonical synthetic runs; nothing under output/session_logs/ is written")
    print("=" * 84)

    rows = [build_window(run) for _c, _f, _i, run in WHITELIST]

    for r in rows:
        if r["segmentation_verdict"] == "OK":
            print(f"  {r['physical_run']:<32} OK  {r['boundary_review_status']:<12} "
                  f"e{r['first_included_entry_index']}@{r['source_character_start']:<5} "
                  f"-> e{r['last_included_entry_index']:<3} "
                  f"p={r['included_participant_turns']:<3} m={r['included_moderator_turns']:<3} "
                  f"w={r['included_words']:<6} drop_prefix_w={r['excluded_boundary_prefix_words']}")
        else:
            print(f"  {r['physical_run']:<32} {r['segmentation_verdict']}  {r.get('problems')}")

    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    out_csv = _OUT_DIR / "comparable_window_audit.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

    # Boundary listing for human inspection (requirement 9)
    lines: list[str] = [
        "# Comparable-window boundaries — all 30 synthetic runs",
        "",
        "Original boundary entry, dropped prefix and retained verbatim substring for",
        "every run. Generated by `scripts/build_comparable_window.py`; embedded in",
        "`PRE_EVALUATION_GATE_REPORT.md`.",
        "",
        "## Algorithm — anchor-and-extend (`anchor_and_extend_v1`)",
        "",
        "1. Locate the boundary entry: the first **moderator** entry that poses Question 1.",
        "2. **Anchor** on the **latest** sentence-aligned suffix of that entry that still",
        "   poses Question 1 — the minimal ask.",
        "3. **Extend backward** from the anchor, one sentence at a time, only across",
        "   sentences that are residue-free **and** positively identified as part of the",
        "   ask (carrying a Q1-distinctive token, or being an ask lead-in / short discourse",
        "   connective). Stop at the first sentence failing either test.",
        "4. Retain that substring **verbatim** — never paraphrased, normalised,",
        "   reconstructed, or replaced with the guide's scripted question.",
        "5. Include every subsequent entry through the end of the last substantive section;",
        "   exclude the closing section.",
        "",
        "Because the boundary only ever moves earlier over text positively identified as",
        "part of the ask, residue is excluded **by construction rather than by enumeration**:",
        "an unlisted phrasing of a welcome or presentation summary cannot survive. This is",
        "deliberately not an \"earliest residue-free offset\" scan, which is only as reliable",
        "as the residue vocabulary.",
        "",
        "Residue classes excluded: participant name, moderator self-introduction, welcome,",
        "instruction/confidentiality text, presentation summary.",
        "",
        "Short ask lead-ins (\"Right, let's get into it. First thing I want to ask:\") are",
        "**retained** by design: the requirement is the point at which the ask begins, not",
        "the bare question, and trimming them would discard legitimate moderator words and",
        "distort moderator word-share.",
        "",
        "```",
    ]
    for r in rows:
        lines += render_boundary(r["physical_run"], r)
    lines += ["```", ""]
    (_OUT_DIR / "comparable_window_boundaries.md").write_text("\n".join(lines), encoding="utf-8")

    ok = [r for r in rows if r["segmentation_verdict"] == "OK"]
    blocked = [r for r in rows if r["segmentation_verdict"] != "OK"]

    # --- exclusion accounting, explicit denominator ------------------------
    denom = sum(r["total_source_words"] for r in ok)
    pre_w = sum(r["excluded_pre_q1_words"] for r in ok)
    close_w = sum(r["excluded_closing_words"] for r in ok)
    inc_w = sum(r["included_words"] for r in ok)
    print(f"\nWrote {out_csv.relative_to(_REPO_ROOT)} ({len(rows)} rows) and "
          f"{(_OUT_DIR / 'comparable_window_boundaries.md').relative_to(_REPO_ROOT)}")
    print(f"\nEXCLUSION ACCOUNTING over {len(ok)} runs with an OK window")
    print(f"  Denominator = total words in the FULL source transcripts of those runs: {denom:,}")
    print(f"    included in window            {inc_w:>9,}  ({100*inc_w/denom:5.1f}%)")
    print(f"    excluded, pre-Q1 material     {pre_w:>9,}  ({100*pre_w/denom:5.1f}%)")
    print(f"      of which boundary prefix    "
          f"{sum(r['excluded_boundary_prefix_words'] for r in ok):>9,}")
    print(f"    excluded, closing section     {close_w:>9,}  ({100*close_w/denom:5.1f}%)")
    print(f"    TOTAL EXCLUDED                {pre_w + close_w:>9,}  "
          f"({100*(pre_w+close_w)/denom:5.1f}%)")
    print(f"    reconciliation (inc+exc==denom): {inc_w + pre_w + close_w == denom}")

    statuses = {}
    for r in rows:
        statuses[r.get("boundary_review_status", "n/a")] = statuses.get(
            r.get("boundary_review_status", "n/a"), 0) + 1
    print(f"\n  boundary_review_status: {statuses}")

    if blocked:
        print(f"\nSTOP — {len(blocked)} run(s) require human review:")
        for r in blocked:
            print(f"  {r['physical_run']}: {r.get('problems')}")
        sys.exit(2)

    # --- hard-fail integrity gate ------------------------------------------
    print("\nINTEGRITY GATE (hard-fail; artefacts re-read from disk)")
    try:
        passed = assert_integrity(rows, expected_runs=len(WHITELIST))
    except IntegrityError as exc:
        print(f"\n{exc}")
        sys.exit(3)
    print(f"  {len(passed)} checks passed, 0 failed.")
    print("  covered: 30 audit rows | 30 derived transcripts | zero review-required |")
    print("           source/original/retained hashes | verbatim boundary slices |")
    print("           byte-identical subsequent entries | exact closing boundary |")
    print("           per-run and corpus-level word reconciliation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-boundaries", nargs="*", default=None, metavar="RUN")
    args = parser.parse_args()
    main(args.print_boundaries)
