"""
Mator et al. (2025) Table 4 — comparable metrics on this corpus.

Namespace `_comparable_window`. Evidence class `AUTOMATIC_PROXY_EXPLORATORY`.
Fully offline: one local model, zero API calls, zero cost.

WHAT IS NEW HERE AND WHAT IS REUSED
-----------------------------------
Three of Mator's five rows already exist in this repository and are NOT
recomputed:

  * "Agreement among participants"  -> `scripts/consensus_dynamics_metrics.py`
    already computes mean sentence-transformer cosine similarity between
    consecutive participant turns inside a guide section. Read here from
    `consensus_dynamics/mator_d4_d5_by_unit.csv`, and reported BESIDE the strict
    participant-follows-participant variant produced by
    `scripts/mator_agreement_strict.py` -- see the note on universes below.
    Mator do not specify their "stance-aware sentence similarity", so cosine is
    a legitimate approximation of their construct; it is cosine, not BERTScore,
    and is labelled as such everywhere.
  * "Conversational distribution"   -> `moderator_word_share` /
    `moderator_turn_share` are already AUTOMATIC_VALIDATED registry metrics and
    the per-participant word vector is already retained in
    `results/structural_distributions_long.csv`. This module only reshapes them
    into Mator's row format; it does not recount words.
  * Guide-section boundaries        -> `scripts/tier2b_segmentation.py`
    (moderator-log transitions on the synthetic side, `Question N.` headers on
    the human side).

Genuinely new, and the reason this module exists: the two rows Mator label
BERTScore (Zhang et al., 2019) are computed here with the actual `bert-score`
package, not with sentence-transformer cosine. They are different methods and
produce different numbers; calling cosine "BERTScore" would misname the method
against a published benchmark.

  * "Relevance of Response"                    -> BERTScore F1, participant turn
    vs. the most recent preceding moderator turn inside the window.
  * "Response similarity between participants" -> BERTScore F1 over all
    cross-speaker participant-turn pairs inside a guide section.

Both are reported twice: untruncated, and under the length control this project
already established (truncate every turn on BOTH sides to W words, W = median
human participant turn length for that FG). The untruncated figure is what a
naive replication produces; the length-matched one is what survives the control
that showed roughly two thirds of Mator's published agreement gap is turn
length rather than consensus.

CORPUS
------
Pinned to `analysis/production_evaluation/frozen_evaluator_inputs.json`: the
5 complete standardized human transcripts and the 30 derived synthetic
`comparable_transcript.json` windows. The run list is read from that file and
every input's SHA-256 is verified before use -- deliberately NOT from a
directory listing of `comparable_transcripts/`, which now also holds the
twin-population arm (`*_twinpop_*`) that is not part of the frozen corpus.

SECTION-LABEL MISALIGNMENT
--------------------------
In 2 of the 30 runs the moderator asked guide question 1 while the session was
still in guide section 0, so every later section LABEL carries a different
guide question's material than its index suggests (and in both runs two
consecutive labels carry the same guide question). Detected here rather than
assumed away: any run with a participant turn labelled section 0 inside the
comparable window is flagged and excluded from the section-indexed metric, with
the reason recorded. The turn-indexed metric does not depend on section labels
and keeps all 30 runs.

Usage:
    py scripts/mator_bertscore_metrics.py
    py scripts/mator_bertscore_metrics.py --self-check   # validation only
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tier2b_segmentation import (  # noqa: E402
    MIN_PARTICIPANT_TURNS,
    MIN_WORDS,
    load_guide_sections,
    segment_human_by_guide,
    segment_synthetic_by_guide,
)

_FROZEN = _REPO_ROOT / "analysis" / "production_evaluation" / "frozen_evaluator_inputs.json"
_SESSION_LOGS = _REPO_ROOT / "output" / "session_logs"
_CONSENSUS = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_dynamics"
_RESULTS = _REPO_ROOT / "analysis" / "production_evaluation" / "results"
_OUT = _REPO_ROOT / "analysis" / "production_evaluation" / "mator_comparable"

# BERTScore configuration. `lang="en"` selects roberta-large layer 17, the
# package default for English and therefore the configuration a paper citing
# "BERTScore" without further qualification is most likely using.
#
# PRIMARY IS RAW F1, not baseline-rescaled, because that is the scale Mator's
# published 82-91% figures live on. Raw roberta-large F1 for a pair of unrelated
# fluent English sentences is ~0.83 -- that is the package's own rescaling
# baseline, i.e. the EXPECTED value over a random-pair corpus, not a hard floor;
# individual unrelated pairs fall on both sides of it. So a raw value in the
# 0.80-0.95 band is not by itself evidence of relevance. The baseline-rescaled
# value,
#     rescaled = (raw - b) / (1 - b),
# is therefore reported alongside every raw figure as the interpretable
# companion. The affine constant is read from the package's own baseline table
# and checked against a rescaling scorer in `self_check`.
BERTSCORE_LANG = "en"
BERTSCORE_RESCALE = False

# Substantive guide sections. 0 = "Introduction and instructions" and
# 6 = "Closing remarks" have no counterpart in the human transcripts.
SUBSTANTIVE_SECTIONS = [1, 2, 3, 4, 5]

# Mator et al. (2025), Table 4. Quoted for side-by-side reporting only.
MATOR_PUBLISHED = {
    "conversational_completeness": {"ai": "100%", "human": "100%"},
    "relevance_of_response": {"ai": "83%", "human": "82%"},
    "between_participant_similarity": {"ai": "91%", "human": "83%"},
    "agreement": {"ai": "92%", "human": "42%"},
    "conversational_distribution": {
        "ai": "M 18%, 3 participants 24-29% each",
        "human": "M 32%, 3 participants 18-26% each",
    },
}


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_moderator(entry: dict) -> bool:
    """Same rule as scripts/consensus_dynamics_events.py.

    The human standardized transcripts carry `speaker_role`; the synthetic
    windows do not, and mark the moderator with `speaker_id == "MODERATOR"`.
    """
    if entry.get("speaker_role"):
        return entry["speaker_role"] == "moderator"
    return entry.get("speaker_id") == "MODERATOR"


def _speaker(entry: dict) -> str:
    return str(entry.get("speaker_id") or entry.get("speaker_name") or "")


def _words(text: str) -> int:
    return len((text or "").split())


def truncate_words(text: str, w: int) -> str:
    """Same rule as consensus_dynamics_metrics.truncate_words (the R3 control)."""
    return " ".join((text or "").split()[:w])


class Unit:
    """One analysis unit: a human focus group or one synthetic run."""

    def __init__(self, unit_id: str, side: str, fg: str, condition: str,
                 entries: list[dict], section_of: dict[int, int],
                 guide_questions: dict[int, str], notes: list[str],
                 section_labels_misaligned: bool = False):
        self.unit_id = unit_id
        self.side = side
        self.fg = fg
        self.condition = condition
        self.entries = entries                # window entries, in order
        self.section_of = section_of          # window entry index -> section index
        self.guide_questions = guide_questions
        self.notes = notes
        self.section_labels_misaligned = section_labels_misaligned

    def participant_indices(self) -> list[int]:
        return [i for i, e in enumerate(self.entries) if not _is_moderator(e)]


def _guide_source_for(fg: str) -> Path:
    """The executed guide of any run of this FG.

    All 30 canonical runs share one `guide_in_config_sha256`, so any run's
    executed guide is the same guide; `run01` is used for the human side.
    """
    return _SESSION_LOGS / f"macho_meals_{fg}_run01" / "session_state_initial.json"


def load_units() -> tuple[list[Unit], dict]:
    frozen = json.loads(_FROZEN.read_text(encoding="utf-8"))
    units: list[Unit] = []
    provenance = {
        "frozen_evaluator_inputs_sha256": _sha256(_FROZEN),
        "frozen_status": frozen["status"],
        "verified_inputs": [],
        "excluded_from_universe": [],
        "section_label_misaligned_runs": [],
    }

    # Anything sitting in comparable_transcripts/ that the frozen file does not
    # list is recorded as excluded, never silently skipped.
    frozen_runs = {s["physical_run"] for s in frozen["synthetic_inputs"]}
    comparable_dir = _REPO_ROOT / "analysis" / "production_evaluation" / "comparable_transcripts"
    if comparable_dir.exists():
        for d in sorted(p.name for p in comparable_dir.iterdir() if p.is_dir()):
            if d not in frozen_runs:
                provenance["excluded_from_universe"].append({
                    "run": d,
                    "reason": "present on disk but not in frozen_evaluator_inputs.json",
                })

    guide_questions_by_fg: dict[str, dict[int, str]] = {}

    # --- human -------------------------------------------------------------
    for h in frozen["human_inputs"]:
        path = _REPO_ROOT / h["path"]
        actual = _sha256(path)
        if actual != h["sha256"]:
            raise SystemExit(f"SHA mismatch for {path}: {actual} != {h['sha256']}")
        provenance["verified_inputs"].append({"unit": h["fg"], "path": h["path"], "sha256": actual})

        guide_src = _guide_source_for(h["fg"])
        if h["fg"] not in guide_questions_by_fg:
            guide_questions_by_fg[h["fg"]] = {
                s["section_index"]: s.get("scripted_question", "")
                for s in load_guide_sections(guide_src)
            }

        entries = json.loads(path.read_text(encoding="utf-8"))
        seg = segment_human_by_guide(path, guide_src)
        section_of = {i: k for k in seg.sections for i in seg.sections[k].entry_indices}

        notes = list(seg.warnings)
        missing = [k for k in SUBSTANTIVE_SECTIONS if k not in seg.sections]
        if missing:
            notes.append(
                f"guide section(s) {missing} have no `Question N.` header in this "
                "transcript; their material, if present, is carried inside the "
                "preceding section")
        units.append(Unit(h["fg"], "human", h["fg"], "human", entries, section_of,
                          guide_questions_by_fg[h["fg"]], notes))

    # --- synthetic ---------------------------------------------------------
    for s in frozen["synthetic_inputs"]:
        path = _REPO_ROOT / s["path"]
        actual = _sha256(path)
        if actual != s["sha256"]:
            raise SystemExit(f"SHA mismatch for {path}: {actual} != {s['sha256']}")
        provenance["verified_inputs"].append(
            {"unit": s["physical_run"], "path": s["path"], "sha256": actual})

        window = json.loads(path.read_text(encoding="utf-8"))["transcript"]
        if len(window) != s["entries"]:
            raise SystemExit(f"{s['physical_run']}: window has {len(window)} entries, "
                             f"frozen record says {s['entries']}")

        src_path = _REPO_ROOT / s["source_transcript"]
        if _sha256(src_path) != s["source_transcript_sha256"]:
            raise SystemExit(f"source transcript SHA mismatch for {src_path}")
        src = json.loads(src_path.read_text(encoding="utf-8"))
        i0 = s["source_entry_index"]

        # The window is the contiguous slice src[i0 : i0 + len(window)], with the
        # single exception of its first entry, whose moderator prefix was trimmed
        # by the anchor-and-extend boundary. Verified rather than assumed, because
        # the section map below is built on source indices.
        for k in range(1, len(window)):
            if window[k].get("content") != src[i0 + k].get("content"):
                raise SystemExit(
                    f"{s['physical_run']}: window entry {k} does not match source "
                    f"entry {i0 + k}; the contiguous-slice assumption is broken")
        if window[0].get("content", "") not in src[i0].get("content", ""):
            raise SystemExit(f"{s['physical_run']}: boundary entry is not a suffix of "
                             f"source entry {i0}")

        guide_src = _SESSION_LOGS / s["physical_run"] / "session_state_initial.json"
        if s["fg"] not in guide_questions_by_fg:
            guide_questions_by_fg[s["fg"]] = {
                sec["section_index"]: sec.get("scripted_question", "")
                for sec in load_guide_sections(guide_src)
            }
        seg = segment_synthetic_by_guide(src_path, guide_src)

        section_of: dict[int, int] = {}
        for k, segment in seg.sections.items():
            for src_i in segment.entry_indices:
                w_i = src_i - i0
                if 0 <= w_i < len(window):
                    section_of[w_i] = k

        notes = list(seg.warnings)
        unmapped = [i for i in range(len(window)) if i not in section_of]
        if unmapped:
            notes.append(f"{len(unmapped)} window entries carry no section assignment")

        # The window begins at the guide-question-1 ask by construction. A
        # PARTICIPANT turn still labelled section 0 therefore means Q1 was asked
        # before the section-1 transition fired, so from that point on every
        # label names a different guide question than its index implies.
        sec0_participants = [i for i in range(len(window))
                             if section_of.get(i) == 0 and not _is_moderator(window[i])]
        misaligned = bool(sec0_participants)
        if misaligned:
            notes.append(
                f"SECTION LABELS MISALIGNED: {len(sec0_participants)} participant turns "
                "inside the window are labelled guide section 0, i.e. question 1 was "
                "asked before the section-1 transition. Section labels do not name "
                "their guide question in this run; excluded from the section-indexed "
                "metric")
            provenance["section_label_misaligned_runs"].append({
                "run": s["physical_run"],
                "participant_turns_labelled_section_0": len(sec0_participants),
            })

        units.append(Unit(s["physical_run"], "synthetic", s["fg"], s["condition"],
                          window, section_of, guide_questions_by_fg[s["fg"]], notes,
                          section_labels_misaligned=misaligned))

    provenance["n_human_units"] = sum(1 for u in units if u.side == "human")
    provenance["n_synthetic_units"] = sum(1 for u in units if u.side == "synthetic")
    return units, provenance


def length_match_widths(units: list[Unit]) -> dict[str, int]:
    """W per FG = median human participant turn length, the R3 control's rule.

    Applied identically to BOTH sides, so it truncates roughly half of the human
    turns as well; that is the point of the control, and the reason the
    untruncated figure is reported beside it.
    """
    w: dict[str, int] = {}
    for u in units:
        if u.side != "human":
            continue
        lens = [_words(u.entries[i].get("content", "")) for i in u.participant_indices()]
        w[u.fg] = int(statistics.median(lens)) if lens else 40
    return w


# ---------------------------------------------------------------------------
# Pair construction
# ---------------------------------------------------------------------------

def relevance_pairs(unit: Unit) -> list[dict]:
    """Each participant turn against the most recent preceding moderator turn.

    Does NOT depend on section labels naming the right guide question: the
    `opener` sensitivity variant anchors on the moderator turn that opened each
    labelled block, which is a real topic-shift question turn regardless of
    which guide index the log assigned it.
    """
    pairs = []
    last_mod: int | None = None
    last_opener: int | None = None
    seen_sections: set[int] = set()
    for i, e in enumerate(unit.entries):
        sec = unit.section_of.get(i)
        if _is_moderator(e):
            last_mod = i
            if sec is not None and sec not in seen_sections:
                seen_sections.add(sec)
                last_opener = i
            continue
        if last_mod is None:
            continue
        pairs.append({
            "unit": unit.unit_id, "kind": "relevance",
            "section_index": sec,
            "cand_index": i, "cand_role": "participant",
            "ref_index": last_mod, "ref_role": "moderator",
            "opener_index": last_opener,
            "cand": e.get("content", ""),
            "ref": unit.entries[last_mod].get("content", ""),
            "ref_opener": (unit.entries[last_opener].get("content", "")
                           if last_opener is not None else None),
        })
    return pairs


def between_participant_pairs(unit: Unit) -> tuple[list[dict], list[int], list[dict]]:
    """All cross-speaker participant-turn pairs, within each guide section.

    Two exclusions, both reported and neither silent:
      * a run whose section labels are misaligned (see `load_units`) contributes
        nothing, because "the same guide section" is exactly what the label can
        no longer certify;
      * a section below the data floor the Tier 2b segmenter already applies
        (>= 3 participant turns and >= 150 words).
    """
    if unit.section_labels_misaligned:
        return [], [], [{
            "unit": unit.unit_id, "section_index": "", "participant_turns": "",
            "participant_words": "",
            "reason": "whole run excluded: section labels do not name their guide "
                      "question (question 1 asked inside guide section 0)",
        }]

    by_section: dict[int, list[int]] = defaultdict(list)
    for i in unit.participant_indices():
        sec = unit.section_of.get(i)
        if sec in SUBSTANTIVE_SECTIONS:
            by_section[sec].append(i)

    pairs: list[dict] = []
    used: list[int] = []
    skipped: list[dict] = []
    for sec in sorted(by_section):
        idxs = sorted(by_section[sec])
        n_words = sum(_words(unit.entries[i].get("content", "")) for i in idxs)
        if len(idxs) < MIN_PARTICIPANT_TURNS or n_words < MIN_WORDS:
            skipped.append({"unit": unit.unit_id, "section_index": sec,
                            "participant_turns": len(idxs), "participant_words": n_words,
                            "reason": f"below floor (>= {MIN_PARTICIPANT_TURNS} turns, "
                                      f">= {MIN_WORDS} words)"})
            continue
        n_before = len(pairs)
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                ia, ib = idxs[a], idxs[b]
                if _speaker(unit.entries[ia]) == _speaker(unit.entries[ib]):
                    continue
                pairs.append({
                    "unit": unit.unit_id, "kind": "between",
                    "section_index": sec,
                    "cand_index": ia, "cand_role": "participant",
                    "ref_index": ib, "ref_role": "participant",
                    "cand": unit.entries[ia].get("content", ""),
                    "ref": unit.entries[ib].get("content", ""),
                })
        if len(pairs) > n_before:
            used.append(sec)
        else:
            skipped.append({"unit": unit.unit_id, "section_index": sec,
                            "participant_turns": len(idxs), "participant_words": n_words,
                            "reason": "no cross-speaker pair (single speaker in section)"})
    return pairs, used, skipped


# ---------------------------------------------------------------------------
# BERTScore
# ---------------------------------------------------------------------------

def baseline_f1(model_type: str, num_layers: int) -> float:
    """The package's own rescaling baseline for this (lang, model, layer).

    Read from `bert_score/rescale_baseline/<lang>/<model>.tsv`, the same file
    `BERTScorer(rescale_with_baseline=True)` uses.
    """
    import bert_score
    tsv = (Path(bert_score.__file__).parent / "rescale_baseline"
           / BERTSCORE_LANG / f"{model_type}.tsv")
    for line in tsv.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split(",")
        if parts and parts[0].strip() == str(num_layers):
            return float(parts[3])
    raise SystemExit(f"no baseline row for layer {num_layers} in {tsv}")


def baseline_spread() -> dict[str, float]:
    """Layer-default baselines across common BERTScore backbones.

    Reported because the single most load-bearing inference in the write-up --
    where Mator's published percentages sit relative to the unrelated-pair
    expectation -- is conditional on a configuration their paper does not state,
    and the expectation ranges from 0.35 to 0.83 across ordinary choices.
    """
    import bert_score
    from bert_score.utils import model2layers
    out = {}
    root = Path(bert_score.__file__).parent / "rescale_baseline" / BERTSCORE_LANG
    for name in ("roberta-large", "roberta-base", "bert-base-uncased",
                 "bert-large-uncased", "bert-base-multilingual-cased",
                 "distilbert-base-uncased"):
        tsv = root / f"{name}.tsv"
        layer = model2layers.get(name)
        if not tsv.exists() or layer is None:
            continue
        try:
            out[f"{name}_L{layer}"] = baseline_f1(name, layer)
        except SystemExit:
            continue
    return out


def make_scorer(batch_size: int = 32):
    import os
    import torch
    from bert_score import BERTScorer

    # Deterministic: model.eval() with no dropout, and the (unused) randomly
    # initialised RoBERTa pooler is seeded rather than left to chance.
    torch.manual_seed(0)
    torch.set_num_threads(os.cpu_count() or 4)
    return BERTScorer(lang=BERTSCORE_LANG, rescale_with_baseline=BERTSCORE_RESCALE,
                      device="cpu", batch_size=batch_size)


def score_batches(scorer, batches: list[tuple[list[str], list[str]]]) -> list[list[float]]:
    """BERTScore F1 for several pair lists in ONE call, then split back apart.

    `bert_cos_score_idf` deduplicates `refs + hyps` before encoding, so a single
    call over every pair list of a unit encodes each distinct turn exactly once
    -- and the same turn text appears in the relevance list, the opener list and
    dozens of between-participant pairs. Scoring the lists separately re-encodes
    all of it once per list.

    F1 is symmetric in (candidate, reference) -- P and R swap -- so the direction
    of a pair does not affect the reported value.
    """
    flat_c: list[str] = []
    flat_r: list[str] = []
    spans: list[tuple[int, int]] = []
    for cands, refs in batches:
        spans.append((len(flat_c), len(flat_c) + len(cands)))
        flat_c += cands
        flat_r += refs
    if not flat_c:
        return [[] for _ in batches]
    _, _, f1 = scorer.score(flat_c, flat_r, verbose=False)
    f1 = [float(x) for x in f1]
    return [f1[a:b] for a, b in spans]


def pair_texts(pairs: list[dict], key_cand="cand", key_ref="ref",
               width: int | None = None) -> tuple[list[str], list[str]]:
    """(candidates, references) for a pair list.

    `width` applies the length control: both sides truncated to the same number
    of words by the same rule.
    """
    cands = [p[key_cand] for p in pairs]
    refs = [p[key_ref] for p in pairs]
    if width is not None:
        cands = [truncate_words(c, width) for c in cands]
        refs = [truncate_words(r, width) for r in refs]
    return cands, refs


def truncation_report(scorer, texts: list[str]) -> dict:
    """How many turns reach the encoder's 512-token limit.

    The existing consensus layer documents that a naive replication with a
    128-token encoder silently applies a partial length control. The same
    question has to be answered for this encoder rather than assumed away.
    """
    from bert_score.utils import sent_encode

    tok = scorer._tokenizer
    limit = tok.model_max_length
    lens = [len(sent_encode(tok, t)) for t in texts]
    at_limit = sum(1 for n in lens if n >= limit)
    return {
        "max_seq_length": int(limit),
        "n_texts": len(texts),
        "n_truncated": at_limit,
        "pct_truncated": round(100.0 * at_limit / len(texts), 2) if texts else 0.0,
        "max_tokens_observed": max(lens) if lens else 0,
        "median_tokens": int(statistics.median(lens)) if lens else 0,
    }


# ---------------------------------------------------------------------------
# Reused layers: agreement, distribution
# ---------------------------------------------------------------------------

def load_agreement() -> dict:
    """Read the already-computed consecutive-turn cosine similarity.

    Not recomputed. Two universes are read and both are reported, because they
    differ asymmetrically between sides:

      BRIDGED (`consensus_dynamics/mator_d4_d5_by_unit.csv`, produced by
        scripts/consensus_dynamics_metrics.py) pairs turns that are consecutive
        in the participant-only sequence, which bridges over any moderator turn
        in between. On the human side ~1% of pairs bridge; on the synthetic side
        ~40% do, because the synthetic moderator intervenes far more often.
      STRICT (`mator_comparable/mator_agreement_strict.csv`, produced by
        scripts/mator_agreement_strict.py) uses only genuine
        participant-follows-participant adjacency -- the universe already frozen
        as `response_acts.csv` -- which is what Mator's "subsequent participant
        responses" describes and what section 2 of the instruction specifies.

    STRICT is the primary. BRIDGED is retained as the sensitivity and as the
    link to the existing consensus layer.
    """
    bridged_path = _CONSENSUS / "mator_d4_d5_by_unit.csv"
    rows: dict[str, dict] = {}
    for r in csv.DictReader(bridged_path.open(encoding="utf-8")):
        rows[r["unit"]] = {
            "agreement_bridged_R2": r.get("mator_agreement_R2", ""),
            "agreement_bridged_R3": r.get("mator_agreement_R3", ""),
            "agreement_bridged_n": r.get("mator_agreement_n_R2", ""),
        }

    out = {"rows": rows,
           "bridged_source": str(bridged_path.relative_to(_REPO_ROOT)),
           "bridged_sha256": _sha256(bridged_path)}

    strict_path = _OUT / "mator_agreement_strict.csv"
    if strict_path.exists():
        for r in csv.DictReader(strict_path.open(encoding="utf-8")):
            rows.setdefault(r["unit"], {}).update({
                "agreement_strict_R2": r.get("agreement_strict_R2", ""),
                "agreement_strict_R3": r.get("agreement_strict_R3", ""),
                "agreement_strict_n": r.get("n_acts", ""),
            })
        out["strict_source"] = str(strict_path.relative_to(_REPO_ROOT))
        out["strict_sha256"] = _sha256(strict_path)
    else:
        out["strict_source"] = None
        out["strict_missing_note"] = (
            "run scripts/mator_agreement_strict.py to produce the primary "
            "(strict-adjacency) agreement figure")
    return out


def load_distribution() -> dict:
    """Reshape the already-frozen structural counts into Mator's row format.

    Word counts are read, not recounted: `moderator_word_share` is an
    AUTOMATIC_VALIDATED registry metric and the per-participant word vector is
    already retained as `participant_word_counts`.
    """
    interaction = _RESULTS / "structural_interaction_metrics_long.csv"
    distributions = _RESULTS / "structural_distributions_long.csv"

    mod_share: dict[str, float] = {}
    total_words: dict[str, float] = {}
    for r in csv.DictReader(interaction.open(encoding="utf-8")):
        unit = r["physical_run"] or r["fg"]
        if r["metric_id"] == "moderator_word_share" and r["value"]:
            mod_share[unit] = float(r["value"])
        elif r["metric_id"] == "total_words" and r["value"]:
            total_words[unit] = float(r["value"])

    per_participant: dict[str, list[float]] = defaultdict(list)
    for r in csv.DictReader(distributions.open(encoding="utf-8")):
        if r["distribution_id"] != "participant_word_counts":
            continue
        unit = r["physical_run"] or r["fg"]
        per_participant[unit].append(float(r["value"]))

    shares: dict[str, dict] = {}
    for unit, counts in per_participant.items():
        tw = total_words.get(unit)
        if not tw:
            continue
        p = sorted((c / tw for c in counts), reverse=True)
        shares[unit] = {
            "moderator_word_share": mod_share.get(unit),
            "participant_word_shares": [round(x, 4) for x in p],
            "n_participants": len(p),
        }
    return {"rows": shares,
            "sources": [str(interaction.relative_to(_REPO_ROOT)),
                        str(distributions.relative_to(_REPO_ROOT))],
            "sha256": {"interaction": _sha256(interaction),
                       "distributions": _sha256(distributions)}}


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

def self_check() -> dict:
    """Prove the batched path equals the package's own per-pair result.

    Everything below is computed by one `scorer.score()` call per unit, which
    relies on `bert_cos_score_idf` deduplicating its inputs. This asserts that
    the batched, deduplicated call returns exactly what pair-at-a-time scoring
    returns; that F1 is symmetric so pair direction is immaterial; and that the
    affine rescaling used throughout reproduces what the package does when asked
    for rescaled scores directly.

    The two scorers are created and released one at a time: holding two
    roberta-large instances is ~2.8 GB for no reason.
    """
    from bert_score import BERTScorer

    a = ("I usually just go to the pub with my mates, nothing fancy, just somewhere "
         "we can all sit down and talk for a few hours.")
    b = ("For me it is always someone's flat rather than a pub, because you can "
         "actually hear each other and it costs nothing.")
    c = "The mean annual rainfall in the Atacama desert is close to zero millimetres."
    q = ("What is your favourite place in your city to spend time with your male "
         "friends? Why - feel free to be specific?")
    cands = [a, b, c, a, b]
    refs = [q, q, q, b, a]

    rescaling = BERTScorer(lang=BERTSCORE_LANG, rescale_with_baseline=True,
                           device="cpu", batch_size=32)
    _, _, pkg_rescaled = rescaling.score(cands, refs, verbose=False)
    pkg_rescaled = [float(x) for x in pkg_rescaled]
    model_type, num_layers = rescaling._model_type, rescaling._num_layers
    del rescaling
    gc.collect()

    scorer = make_scorer()
    _, _, batched = scorer.score(cands, refs, verbose=False)
    batched = [round(float(x), 6) for x in batched]
    one_by_one = []
    for cd, rf in zip(cands, refs):
        _, _, f = scorer.score([cd], [rf], verbose=False)
        one_by_one.append(round(float(f[0]), 6))

    base = baseline_f1(model_type, num_layers)
    ours = [rescale(x, base) for x in batched]
    max_delta = max(abs(x - y) for x, y in zip(batched, one_by_one))
    symmetry_delta = abs(batched[3] - batched[4])
    rescale_delta = max(abs(x - y) for x, y in zip(ours, pkg_rescaled))

    return {
        "scorer": scorer,
        "batched": batched,
        "one_by_one": one_by_one,
        "max_abs_delta_batched_vs_single": max_delta,
        "f1_symmetry_delta": symmetry_delta,
        "batched_equals_single": max_delta < 1e-5,
        "f1_is_symmetric": symmetry_delta < 1e-5,
        "related_pair_f1": batched[0],
        "unrelated_pair_f1": batched[2],
        "related_above_unrelated": batched[0] > batched[2],
        "baseline_f1": base,
        "unrelated_pair_f1_rescaled": round(rescale(batched[2], base), 6),
        "unrelated_pair_lands_below_baseline": batched[2] < base,
        "package_rescaled": [round(x, 6) for x in pkg_rescaled],
        "affine_rescaled": [round(x, 6) for x in ours],
        "max_abs_delta_rescaling": rescale_delta,
        "affine_rescaling_matches_package": rescale_delta < 1e-5,
        "baseline_across_backbones": baseline_spread(),
    }


def rescale(raw: float, base: float) -> float:
    return (raw - base) / (1.0 - base)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true",
                    help="run only the validation block and exit")
    args = ap.parse_args()

    _OUT.mkdir(parents=True, exist_ok=True)

    print("loading BERTScore (roberta-large, English default) ...", flush=True)
    check = self_check()
    scorer = check.pop("scorer")
    print(f"  hash: {scorer.hash}", flush=True)
    print(f"  self-check: batched==single {check['batched_equals_single']}  "
          f"F1 symmetric {check['f1_is_symmetric']}  "
          f"affine rescaling matches package "
          f"{check['affine_rescaling_matches_package']}", flush=True)
    for k in ("batched_equals_single", "f1_is_symmetric",
              "affine_rescaling_matches_package"):
        if not check[k]:
            raise SystemExit(f"self-check failed: {k}")
    base = check["baseline_f1"]
    print(f"  unrelated-pair expectation at this layer: {base:.4f}; the deliberately "
          f"unrelated probe scored {check['unrelated_pair_f1']:.4f} raw "
          f"({check['unrelated_pair_f1_rescaled']:+.3f} rescaled)", flush=True)
    if args.self_check:
        print(json.dumps(check, indent=2))
        return

    units, provenance = load_units()
    print(f"corpus: {provenance['n_human_units']} human units, "
          f"{provenance['n_synthetic_units']} synthetic units", flush=True)
    for ex in provenance["excluded_from_universe"]:
        print(f"  EXCLUDED {ex['run']}: {ex['reason']}", flush=True)
    for m in provenance["section_label_misaligned_runs"]:
        print(f"  SECTION LABELS MISALIGNED {m['run']}: "
              f"{m['participant_turns_labelled_section_0']} participant turns in "
              f"guide section 0 inside the window", flush=True)

    widths = length_match_widths(units)
    print(f"length-match W per FG (median human participant turn): {widths}", flush=True)

    agreement = load_agreement()
    if agreement.get("strict_source") is None:
        print("  WARNING: strict-adjacency agreement not found; "
              "run scripts/mator_agreement_strict.py first", flush=True)
    distribution = load_distribution()

    rows: list[dict] = []
    all_pairs: list[dict] = []
    all_skips: list[dict] = []
    all_texts: list[str] = []
    section_rows: list[dict] = []

    for n, unit in enumerate(units, 1):
        w = widths[unit.fg]
        rel = relevance_pairs(unit)
        btw, _, skips = between_participant_pairs(unit)
        all_skips += skips

        print(f"[{n}/{len(units)}] {unit.unit_id}: "
              f"{len(rel)} relevance pairs, {len(btw)} between-participant pairs, W={w}",
              flush=True)

        rel_open = [p for p in rel if p.get("ref_opener")]
        rel_f1, open_f1, btw_f1, rel_lm, btw_lm = score_batches(scorer, [
            pair_texts(rel),
            pair_texts(rel_open, key_ref="ref_opener"),
            pair_texts(btw),
            pair_texts(rel, width=w),
            pair_texts(btw, width=w),
        ])

        for p, v, vl in zip(rel, rel_f1, rel_lm):
            p["bertscore_f1"] = round(v, 6)
            p["bertscore_f1_length_matched"] = round(vl, 6)
            p["cand_words"] = _words(p["cand"])
            p["ref_words"] = _words(p["ref"])
        for p, v in zip(rel_open, open_f1):
            p["bertscore_f1_vs_section_opener"] = round(v, 6)
        for p, v, vl in zip(btw, btw_f1, btw_lm):
            p["bertscore_f1"] = round(v, 6)
            p["bertscore_f1_length_matched"] = round(vl, 6)
            p["cand_words"] = _words(p["cand"])
            p["ref_words"] = _words(p["ref"])
        all_pairs += rel + btw

        # Mator averages within a question, then across questions.
        def section_mean(scores):
            by_section: dict[int, list[float]] = defaultdict(list)
            for p, v in zip(btw, scores):
                by_section[p["section_index"]].append(v)
            means = {k: statistics.mean(v) for k, v in by_section.items() if v}
            return means, (statistics.mean(means.values()) if means else None)

        sec_means, between_value = section_mean(btw_f1)
        _, between_lm = section_mean(btw_lm)

        agg = agreement["rows"].get(unit.unit_id, {})
        dist = distribution["rows"].get(unit.unit_id, {})

        for sec in sorted(sec_means):
            section_rows.append({
                "unit": unit.unit_id, "side": unit.side, "fg": unit.fg,
                "condition": unit.condition, "section_index": sec,
                "n_pairs": sum(1 for p in btw if p["section_index"] == sec),
                "between_participant_bertscore_f1": round(sec_means[sec], 4),
            })

        all_texts += [p["cand"] for p in rel] + [p["ref"] for p in rel] \
            + [p["cand"] for p in btw] + [p["ref"] for p in btw]

        rows.append({
            "unit": unit.unit_id,
            "side": unit.side,
            "fg": unit.fg,
            "condition": unit.condition,
            "n_entries": len(unit.entries),
            "n_participant_turns": len(unit.participant_indices()),
            "section_labels_misaligned": unit.section_labels_misaligned,
            "length_match_w": w,

            "relevance_bertscore_f1": round(statistics.mean(rel_f1), 4) if rel_f1 else "",
            "relevance_bertscore_f1_rescaled":
                round(rescale(statistics.mean(rel_f1), base), 4) if rel_f1 else "",
            "relevance_bertscore_f1_length_matched":
                round(statistics.mean(rel_lm), 4) if rel_lm else "",
            "relevance_bertscore_f1_vs_section_opener":
                round(statistics.mean(open_f1), 4) if open_f1 else "",
            "relevance_n_pairs": len(rel_f1),
            "relevance_mean_cand_words":
                round(statistics.mean([p["cand_words"] for p in rel]), 1) if rel else "",
            "relevance_mean_ref_words":
                round(statistics.mean([p["ref_words"] for p in rel]), 1) if rel else "",

            "between_participant_bertscore_f1":
                round(between_value, 4) if between_value is not None else "",
            "between_participant_bertscore_f1_rescaled":
                round(rescale(between_value, base), 4) if between_value is not None else "",
            "between_participant_bertscore_f1_length_matched":
                round(between_lm, 4) if between_lm is not None else "",
            "between_participant_n_pairs": len(btw_f1),
            "between_participant_n_sections": len(sec_means),
            "between_participant_sections": "|".join(str(x) for x in sorted(sec_means)),
            "between_participant_mean_turn_words":
                round(statistics.mean([p["cand_words"] for p in btw]), 1) if btw else "",

            "agreement_strict_R2": agg.get("agreement_strict_R2", ""),
            "agreement_strict_R3": agg.get("agreement_strict_R3", ""),
            "agreement_strict_n": agg.get("agreement_strict_n", ""),
            "agreement_bridged_R2": agg.get("agreement_bridged_R2", ""),
            "agreement_bridged_R3": agg.get("agreement_bridged_R3", ""),
            "agreement_bridged_n": agg.get("agreement_bridged_n", ""),

            "moderator_word_share": dist.get("moderator_word_share", ""),
            "participant_word_shares": "|".join(
                f"{x:.4f}" for x in dist.get("participant_word_shares", [])),
            "n_participants": dist.get("n_participants", ""),

            "notes": "; ".join(unit.notes),
        })

    trunc = truncation_report(scorer, sorted(set(all_texts)))
    print(f"encoder max_seq_length={trunc['max_seq_length']}; "
          f"{trunc['n_truncated']}/{trunc['n_texts']} distinct turns truncated "
          f"({trunc['pct_truncated']}%); longest turn {trunc['max_tokens_observed']} tokens",
          flush=True)

    _write_csv(_OUT / "mator_bertscore_by_unit.csv", rows)
    _write_csv(_OUT / "mator_bertscore_by_section.csv", section_rows)
    _write_csv(_OUT / "mator_bertscore_pairs.csv", [
        {k: v for k, v in p.items() if k != "ref_opener"} for p in all_pairs])
    if all_skips:
        _write_csv(_OUT / "mator_section_floor_skips.csv", all_skips)

    import transformers
    spec = {
        "namespace": "_comparable_window",
        "evidence_class": "AUTOMATIC_PROXY_EXPLORATORY",
        "api_calls": 0,
        "bertscore": {
            "package": "bert-score",
            "package_version": _dist_version("bert-score"),
            "transformers_version": transformers.__version__,
            "torch_version": _dist_version("torch"),
            "hash": scorer.hash,
            "model_type": scorer._model_type,
            "num_layers": scorer._num_layers,
            "lang": BERTSCORE_LANG,
            "rescale_with_baseline": BERTSCORE_RESCALE,
            "baseline_f1_for_rescaling": base,
            "idf": False,
            "device": "cpu",
            **trunc,
        },
        "length_control": {
            "rule": "truncate every turn on BOTH sides to W words, W = median human "
                    "participant turn length for that FG (the R3 rule already used by "
                    "scripts/consensus_dynamics_metrics.py)",
            "w_by_fg": widths,
        },
        "reused_not_recomputed": {
            "agreement": agreement,
            "conversational_distribution": distribution,
            "segmentation": "scripts/tier2b_segmentation.py",
        },
        "corpus": provenance,
        "self_check": check,
        "counts": {
            "relevance_pairs": sum(1 for p in all_pairs if p["kind"] == "relevance"),
            "between_participant_pairs": sum(1 for p in all_pairs if p["kind"] == "between"),
            "distinct_turn_texts_encoded": trunc["n_texts"],
            "units_in_relevance": sum(1 for r in rows if r["relevance_n_pairs"]),
            "units_in_between_participant":
                sum(1 for r in rows if r["between_participant_n_pairs"]),
        },
        "section_floor_skips": all_skips,
    }
    (_OUT / "mator_bertscore_spec.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")

    for name in ("mator_bertscore_by_unit.csv", "mator_bertscore_by_section.csv",
                 "mator_bertscore_pairs.csv", "mator_bertscore_spec.json"):
        print(f"wrote {_OUT / name}")


def _dist_version(name: str) -> str:
    from importlib.metadata import version
    try:
        return version(name)
    except Exception:  # pragma: no cover
        return "unknown"


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
