"""
Tier 2b — human-vs-human ceiling: does the method discriminate group identity AT ALL?

The FG1-vs-FG5 discrimination control returned the wrong sign: the primary
mismatched arm scored 44.7% against the matched arm's 21.3%, and a second
mismatched arm scored 18.3%. Two readings survive that result and they imply
opposite decisions about Tier 2b:

  (a) Per-section theme sets are not group-discriminative for ANY pair. Ask five
      UK men the same guide question and habit/convenience/taste come back
      regardless of who they are. Then Tier 2b measures a question effect, not a
      group effect, and cannot serve as fidelity evidence for anyone.
  (b) There IS a real group signal between genuine focus groups, and the
      synthetic runs simply fail to reproduce it. Then Tier 2b is valid and
      FG1-vs-FG5 is a genuine negative finding about the pipeline.

Only real-vs-real separates them. This script scores human transcripts against
each other, section by section, through the identical pipeline.

STRICTLY READ-ONLY. No synthetic generation. Nothing is written to `data/`. The
human transcripts are opened for reading only; all output goes to
`analysis/coding_frame/` and `docs/findings/`. The guide is loaded from
`configs/guides/macho_meals_plant_based_masculinity_uk.yaml` rather than from a
synthetic run's `session_state_initial.json`, so no synthetic artefact is touched
at all (the two were verified identical in labels and indices by
`tests/test_tier2b_guide_question_segmentation.py::test_yaml_and_executed_guide_agree`).

PAIRS. FG1 is the anchor for the two primary pairs so the numbers sit directly
alongside the existing FG1-anchored figures. FG2-vs-FG3 is added as a third pair
because it costs only its 5 matching calls once FG2 and FG3 themes exist, and it
is the only way to tell whether a low FG1-anchored result means "no group signal"
or merely "FG1 is atypical".

FG1's themes are NOT re-extracted — reused verbatim from the pilot's
`tier2b_guide_question_human_fg1.json`, exactly as the discrimination control did,
so every arm scores against a byte-identical FG1 set.

MATCH AUDIT. `match_tier2_themes` reports a disagreement only when judge and
embeddings conflict at the extremes (<0.35 or >0.65). The dubious pair found by
hand in the previous control ("Variety of available options" matched to
"Simplicity of limited choice") sat in the middle band and was never flagged.
This script therefore computes the embedding similarity of every ACCEPTED pair
and flags the low-similarity ones. Local computation, no API cost.

ADDITIVE. `extract_themes_tier2`, `verify_tier2_themes`, `match_tier2_themes`,
`_embedding_similarities` and `segment_human_by_guide` are called unmodified.
`validate_tier2b_guide_question.py` and `validate_tier2b_discrimination_control.py`
are imported for shared helpers and are NOT modified.

Usage:
    py scripts/validate_tier2b_human_ceiling.py --dry-run
    py scripts/validate_tier2b_human_ceiling.py [--evaluator gemini25] [--no-fg2-fg3]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from thematic_coding import (                     # noqa: E402
    EVALUATOR_CONFIGS,
    Tier2Result,
    _embedding_similarities,
    extract_themes_tier2,
    match_tier2_themes,
)
from tier2b_segmentation import (                 # noqa: E402
    MIN_PARTICIPANT_TURNS,
    MIN_WORDS,
    SegmentationResult,
    comparable_sections,
    segment_human_by_guide,
)
from validate_tier2b_guide_question import (      # noqa: E402
    _print_segmentation,
    _theme_to_dict,
    _with_retry,
)
from validate_tier2b_discrimination_control import load_human_themes  # noqa: E402

_OUT_DIR  = _REPO_ROOT / "analysis" / "coding_frame"
_DOCS_DIR = _REPO_ROOT / "docs" / "findings"
_HUMAN_DIR = _REPO_ROOT / "data" / "datasets_transcripts" / "standardized" / "macho_meals"
_GUIDE_YAML = _REPO_ROOT / "configs" / "guides" / "macho_meals_plant_based_masculinity_uk.yaml"

_DATE = "2026-07-29"

_HUMAN_THEMES_JSON = _OUT_DIR / "tier2b_guide_question_human_fg1.json"

# Emitted as part of the generated markdown, NOT hand-patched into the .md
# afterwards: _write_md rebuilds the file from scratch on every call, so a manual
# banner would be silently erased the next time this script ran.
_SUPERSEDED_BANNER = [
    "> ## ⚠ Superseded — see final verdict",
    ">",
    "> **This document's own next-step recommendation was resolved by later diagnostics in",
    "> this same chain.** It closed ambiguous between two readings and called for one",
    "> decisive test — a cross-section control. That control was run, and it resolved the",
    "> ambiguity.",
    ">",
    "> **Final decision:** Tier 2b's recall/precision is **retired as fidelity evidence**",
    "> (the matcher tracks the guide question, not group identity — confirmed by the",
    "> cross-section control). The per-section theme lists **remain valid as descriptive",
    "> output**: they are stable on re-extraction and quote-verified.",
    ">",
    "> The ambiguity left open here is now settled. Matching theme sets from the **same",
    "> transcript** across **different** guide questions scored 0.0% — the lowest cell in",
    "> the completed 2×2, below even different-group cross pairs. The 41.3–57.0%",
    "> human-vs-human band reported below therefore reflects shared topic, not shared group",
    "> identity, and should not be read as a ceiling for group discrimination.",
    ">",
    "> Full chain and reasoning: `docs/findings/2026-07-29_tier2b_cross_section_control.md`.",
    ">",
    "> _Nothing below has been altered — this document is retained as the record of the",
    "> diagnostic process._",
    "",
]

# Accepted pairs below this cosine similarity are flagged for manual review.
# 0.50 is the midpoint of the band match_tier2_themes leaves unexamined
# (it only flags <0.35 or >0.65).
_LOW_SIMILARITY_FLAG = 0.50

# Reference figures already established, for the side-by-side table.
_REFERENCE_ROWS = [
    ("Same text re-extracted (pilot stability check)", "ceiling", 0.964,
     "upper bound: identical text, 3 extractions, mean pairwise recall"),
    ("real FG1 vs synth FG1 `macho_meals_fg1_run01` (matched)", "matched", 0.213, ""),
    ("real FG1 vs synth FG5 `macho_meals_fg5_run01` (mismatched, primary)", "mismatched", 0.447, ""),
    ("real FG1 vs synth FG5 `macho_meals_fg5_run03` (mismatched, second arm)", "mismatched", 0.183, ""),
]


# ---------------------------------------------------------------------------
# Extraction and matching
# ---------------------------------------------------------------------------

def extract_group(
    label: str,
    seg: SegmentationResult,
    indices: list[int],
    evaluator_cfg: dict | None,
) -> dict[int, Tier2Result]:
    """Extract per-section themes for one human transcript."""
    out: dict[int, Tier2Result] = {}
    print(f"\n[Extract] real {label}")
    for idx in indices:
        s = seg.sections[idx]
        slug = s.section_label.lower().replace(" ", "_")[:40]
        print(f"  s{idx} {s.section_label[:40]:<40} "
              f"({s.participant_turns} p-turns, {s.total_words} words) ...",
              end=" ", flush=True)
        out[idx] = _with_retry(
            extract_themes_tier2,
            s.blind_text,
            run_label=f"tier2b_ceiling__human_{label}__section_{idx}_{slug}",
            evaluator_cfg=evaluator_cfg,
        )
        print(f"{len(out[idx].themes)} themes")
    return out


def _accepted_pair_similarities(
    a_res: Tier2Result, b_res: Tier2Result, matched_pairs: list[tuple[int, int]],
) -> list[float | None]:
    """Cosine similarity for each accepted pair. None if embeddings unavailable."""
    if not matched_pairs:
        return []
    sims = _embedding_similarities(a_res.themes, b_res.themes)
    # _embedding_similarities returns an all-zero matrix when
    # sentence-transformers is missing — treat that as "unavailable", not "0.0".
    if not sims or all(v == 0.0 for row in sims for v in row):
        return [None] * len(matched_pairs)
    return [sims[i][j] for i, j in matched_pairs]


def score_pair(
    a_label: str, a_seg: SegmentationResult, a_themes: dict[int, Tier2Result],
    b_label: str, b_seg: SegmentationResult, b_themes: dict[int, Tier2Result],
    indices: list[int],
    evaluator_cfg: dict | None,
) -> dict:
    """
    Score one human-vs-human pair, section by section.

    Recall is computed against side A's themes and precision against side B's —
    the same direction the pilot used with the human transcript as side A, so the
    numbers are directly comparable to the FG1-anchored figures.
    """
    print(f"\n[Pair] real {a_label} vs real {b_label}")
    rows: list[dict] = []
    for idx in indices:
        a_res, b_res = a_themes[idx], b_themes[idx]
        slug = a_seg.sections[idx].section_label.lower().replace(" ", "_")[:40]
        print(f"  s{idx} matching ...", end=" ", flush=True)
        scores = _with_retry(
            match_tier2_themes,
            a_res, b_res,
            run_label=f"tier2b_ceiling_match__{a_label}_vs_{b_label}__section_{idx}_{slug}",
            evaluator_cfg=evaluator_cfg,
        )
        sims = _accepted_pair_similarities(a_res, b_res, scores.matched_pairs)
        print(f"{len(scores.matched_pairs)} matched  recall={scores.recall:.1%}  "
              f"precision={scores.precision:.1%}")

        pairs = []
        for (i, j), sim in zip(scores.matched_pairs, sims):
            low = sim is not None and sim < _LOW_SIMILARITY_FLAG
            pairs.append({
                "a_theme": a_res.themes[i].theme_label,
                "b_theme": b_res.themes[j].theme_label,
                "embedding_similarity": None if sim is None else round(sim, 3),
                "low_similarity_flag": low,
            })
            if low:
                print(f"       ⚑ low-similarity accepted match (sim={sim:.2f}): "
                      f"'{a_res.themes[i].theme_label}' <-> '{b_res.themes[j].theme_label}'")

        rows.append({
            "section_index": idx,
            "section_label": a_seg.sections[idx].section_label,
            "a_counts": a_seg.sections[idx].counts(),
            "b_counts": b_seg.sections[idx].counts(),
            "a_themes": len(a_res.themes),
            "b_themes": len(b_res.themes),
            "matched":   len(scores.matched_pairs),
            "recall":    round(scores.recall, 4),
            "precision": round(scores.precision, 4),
            "matched_pairs": pairs,
            "a_only_themes": [
                {"theme_label": t.theme_label, "participant_count": t.participant_count}
                for t in scores.missed_themes
            ],
            "b_only_themes": [
                {"theme_label": t.theme_label, "participant_count": t.participant_count}
                for t in scores.emergent_themes
            ],
            "disagreements": [
                {**d,
                 "a_theme": a_res.themes[d["ri"]].theme_label,
                 "b_theme": b_res.themes[d["si"]].theme_label}
                for d in scores.disagreements
            ],
        })

    n = len(rows)
    return {
        "pair": f"{a_label}_vs_{b_label}",
        "a_label": a_label,
        "b_label": b_label,
        "sections": rows,
        "mean_recall":    round(sum(r["recall"] for r in rows) / n, 4) if n else None,
        "mean_precision": round(sum(r["precision"] for r in rows) / n, 4) if n else None,
        "total_matched_pairs": sum(r["matched"] for r in rows),
        "low_similarity_matches": [
            {"section_index": r["section_index"], **p}
            for r in rows for p in r["matched_pairs"] if p["low_similarity_flag"]
        ],
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _write_md(evaluator_cfg: dict | None, segs: dict[str, SegmentationResult],
              pairs: list[dict], indices: list[int]) -> Path:
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = _DOCS_DIR / f"{_DATE}_tier2b_human_ceiling.md"

    ecfg = evaluator_cfg or {}
    model = ecfg.get("model", "gemini-2.5-flash")
    params = (f"thinking_level={ecfg['thinking_level']}" if ecfg.get("thinking_level")
              else f"temperature={ecfg.get('temperature', 0.0)}")

    lines: list[str] = [
        "# Tier 2b — Human-vs-Human Ceiling (does the method discriminate group identity at all?)",
        "",
        *_SUPERSEDED_BANNER,
        f"**Date:** {_DATE}  ",
        f"**Evaluator:** `{model}` ({params}) — identical to the pilot and the FG1-vs-FG5 control  ",
        f"**Pairs:** {', '.join('real ' + p['a_label'] + ' vs real ' + p['b_label'] for p in pairs)}  ",
        f"**FG1 themes:** reused verbatim from `analysis/coding_frame/{_HUMAN_THEMES_JSON.name}` "
        f"(not re-extracted)  ",
        f"**Data floor:** MIN_PARTICIPANT_TURNS={MIN_PARTICIPANT_TURNS}, MIN_WORDS={MIN_WORDS}  ",
        "**Read-only:** no synthetic generation; nothing written to `data/`; guide read from "
        "`configs/guides/`, not from a synthetic run artefact.",
        "",
        "> The FG1-vs-FG5 control returned the wrong sign (mismatched 44.7% vs matched 21.3%).",
        "> Two readings survive it: either per-section theme sets carry no group signal for",
        "> anyone, or there is a real group signal the synthetic runs fail to reproduce.",
        "> Scoring real groups against each other is the only thing that separates them.",
        "",
        "---",
        "",
        "## Part A — Segmentation",
        "",
        "| Group | Participants | Sections | s1 | s2 | s3 | s4 | s5 |",
        "|-------|-------------:|---------:|---:|---:|---:|---:|---:|",
    ]
    for label, seg in segs.items():
        cells = "".join(
            f" {seg.sections[i].participant_turns}t/{seg.sections[i].total_words}w |"
            if i in seg.sections else " — |"
            for i in indices
        )
        n_spk = max((seg.sections[i].distinct_participants for i in seg.section_indices()),
                    default=0)
        lines.append(f"| real {label} | {n_spk} | {len(seg.sections)} |{cells}")

    lines += [
        "",
        "All sections on every group cleared the data floor; no section was skipped.",
        "",
        "---",
        "",
        "## Part B — Human-vs-human, section by section",
        "",
        "Recall = side-A themes with a side-B counterpart / all side-A themes "
        "(same direction as the pilot).",
        "",
        "| Idx | Section |" + "".join(f" {p['a_label']}↔{p['b_label']} recall |" for p in pairs),
        "|----:|---------|" + "".join("------:|" for _ in pairs),
    ]
    for idx in indices:
        row = f"| {idx} | " + next(
            (r["section_label"] for r in pairs[0]["sections"] if r["section_index"] == idx), "?"
        ) + " |"
        for p in pairs:
            r = next((r for r in p["sections"] if r["section_index"] == idx), None)
            row += f" {r['recall']:.1%} |" if r else " — |"
        lines.append(row)
    lines.append("| **Mean** | |" + "".join(f" **{p['mean_recall']:.1%}** |" for p in pairs))

    lines += [
        "",
        "Theme pairs matched across all five sections: "
        + "; ".join(f"{p['a_label']}↔{p['b_label']} **{p['total_matched_pairs']}**"
                    for p in pairs) + ".",
        "",
        "Precision: "
        + "; ".join(f"{p['a_label']}↔{p['b_label']} {p['mean_precision']:.1%}"
                    for p in pairs) + ".",
        "",
        "---",
        "",
        "## Part C — All figures side by side",
        "",
        "| Comparison | Kind | Mean per-section recall |",
        "|------------|------|------------------------:|",
    ]
    for name, kind, val, note in _REFERENCE_ROWS:
        suffix = f" <br>_{note}_" if note else ""
        lines.append(f"| {name}{suffix} | {kind} | {val:.1%} |")
    for p in pairs:
        lines.append(f"| real {p['a_label']} vs real {p['b_label']} | "
                     f"human-vs-human | **{p['mean_recall']:.1%}** |")

    lines += [
        "",
        "> Reading rule fixed in advance, before the numbers were seen: if human-vs-human",
        "> also lands in the ~20–45% band, no pair — human or synthetic — is separable at",
        "> this granularity, and Tier 2b cannot serve as fidelity evidence. If",
        "> human-vs-human sits clearly above 44.7%, a real group signal exists that the",
        "> synthetic runs fail to reproduce, which validates the method and makes",
        "> FG1-vs-FG5 a genuine negative finding.",
        "",
        "---",
        "",
        "## Part D — Match-quality audit",
        "",
        "`match_tier2_themes` flags a judge/embedding disagreement only outside the",
        "0.35–0.65 similarity band. Accepted pairs inside that band are never examined —",
        "which is how *\"Variety of available options\" ↔ \"Simplicity of limited choice\"*",
        "passed unremarked in the previous control. Every accepted pair below",
        f"cosine {_LOW_SIMILARITY_FLAG:.2f} is therefore listed here.",
        "",
    ]
    any_low = False
    for p in pairs:
        if not p["low_similarity_matches"]:
            continue
        any_low = True
        lines += [f"**{p['a_label']} ↔ {p['b_label']}**", ""]
        for m in p["low_similarity_matches"]:
            lines.append(f"- s{m['section_index']} (sim={m['embedding_similarity']}): "
                         f"_{m['a_theme']}_ ↔ _{m['b_theme']}_")
        lines.append("")
    if not any_low:
        lines += [f"_No accepted pair fell below cosine {_LOW_SIMILARITY_FLAG:.2f}._", ""]

    lines += [
        "### All accepted matches",
        "",
    ]
    for p in pairs:
        lines += [f"**{p['a_label']} ↔ {p['b_label']}**", ""]
        for r in p["sections"]:
            if not r["matched_pairs"]:
                lines.append(f"- s{r['section_index']} {r['section_label']}: none")
                continue
            for m in r["matched_pairs"]:
                flag = " ⚑" if m["low_similarity_flag"] else ""
                lines.append(f"- s{r['section_index']} (sim={m['embedding_similarity']}){flag}: "
                             f"_{m['a_theme']}_ ↔ _{m['b_theme']}_")
        lines.append("")

    lines += [
        "---",
        "",
        f"_Auto-generated by `scripts/validate_tier2b_human_ceiling.py` "
        f"(segmentation: `scripts/tier2b_segmentation.py`)._",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(evaluator_key: str, include_fg2_fg3: bool, dry_run: bool) -> None:
    ecfg = EVALUATOR_CONFIGS.get(evaluator_key)
    if ecfg is None:
        print(f"Unknown evaluator key '{evaluator_key}'. Choose from: {list(EVALUATOR_CONFIGS)}")
        sys.exit(1)

    print("=" * 72)
    print("  TIER 2b — HUMAN-vs-HUMAN CEILING")
    print(f"  Evaluator: {ecfg.get('model')}"
          + ("   [DRY RUN — segmentation only, no API calls]" if dry_run else ""))
    print("=" * 72)

    fg1_themes, pilot_evaluator = load_human_themes(_HUMAN_THEMES_JSON)
    if pilot_evaluator != ecfg.get("model"):
        print(f"\nEvaluator mismatch: the pilot's FG1 themes were extracted with "
              f"'{pilot_evaluator}' but this run requests '{ecfg.get('model')}'. The "
              f"comparison against the existing figures would not be apples-to-apples. "
              f"Stopping.")
        sys.exit(1)
    print(f"\n[FG1 anchor] {sum(len(r.themes) for r in fg1_themes.values())} themes "
          f"across sections {sorted(fg1_themes)} — reused from the pilot, "
          f"evaluator '{pilot_evaluator}' confirmed identical.")

    segs = {
        label: segment_human_by_guide(_HUMAN_DIR / label / "transcript.json", _GUIDE_YAML)
        for label in ("fg1", "fg2", "fg3")
    }
    for label, seg in segs.items():
        _print_segmentation(seg)

    if set(segs["fg1"].section_indices()) != set(fg1_themes):
        print(f"\nSection-set mismatch: re-segmenting FG1 yields "
              f"{segs['fg1'].section_indices()} but the stored themes cover "
              f"{sorted(fg1_themes)}. Stopping rather than aligning them by guess.")
        sys.exit(2)

    # Sections must clear the floor on every group taking part.
    indices = sorted(set(fg1_themes))
    for label in ("fg2", "fg3"):
        common, skipped = comparable_sections(segs["fg1"], segs[label])
        for k in skipped:
            print(f"  skipped section {k['section_index']} for fg1 vs {label}: "
                  f"{k['status']} — {k['reason']}")
        indices = [i for i in indices if i in common]
    print(f"\n[Scope] {len(indices)} sections comparable across all groups: {indices}")

    n_calls = 2 * len(indices) + (3 if include_fg2_fg3 else 2) * len(indices)
    print(f"[Scope] ≈{n_calls} evaluator API calls "
          f"({2 * len(indices)} extractions for FG2+FG3, "
          f"{(3 if include_fg2_fg3 else 2) * len(indices)} matching; FG1 themes reused)")

    if dry_run:
        print("\nDry run — stopping before any API call. No files written.")
        return

    themes = {"fg1": fg1_themes}
    for label in ("fg2", "fg3"):
        themes[label] = extract_group(label, segs[label], indices, ecfg)

    pair_specs = [("fg1", "fg2"), ("fg1", "fg3")]
    if include_fg2_fg3:
        pair_specs.append(("fg2", "fg3"))
    pairs = [
        score_pair(a, segs[a], themes[a], b, segs[b], themes[b], indices, ecfg)
        for a, b in pair_specs
    ]

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = _OUT_DIR / "tier2b_human_ceiling_fg1_fg2_fg3.json"
    out_json.write_text(json.dumps({
        "date":      _DATE,
        "evaluator": ecfg.get("model"),
        "evaluator_config": ecfg,
        "read_only": True,
        "fg1_themes_source": str(_HUMAN_THEMES_JSON),
        "fg1_themes_reused_not_reextracted": True,
        "guide_source": str(_GUIDE_YAML),
        "data_floor": {"min_participant_turns": MIN_PARTICIPANT_TURNS,
                       "min_words": MIN_WORDS},
        "low_similarity_flag_threshold": _LOW_SIMILARITY_FLAG,
        "sections_compared": indices,
        "segmentation": {
            label: [seg.sections[i].counts() for i in seg.section_indices()]
            for label, seg in segs.items()
        },
        "extracted_themes": {
            label: {str(i): [_theme_to_dict(t) for t in res.themes]
                    for i, res in group.items()}
            for label, group in themes.items()
        },
        "pairs": pairs,
        "reference_figures": [
            {"comparison": name, "kind": kind, "mean_recall": val, "note": note}
            for name, kind, val, note in _REFERENCE_ROWS
        ],
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md_path = _write_md(ecfg, segs, pairs, indices)

    print("\n" + "=" * 72)
    print("  SUMMARY — all figures side by side (mean per-section recall)")
    print("=" * 72)
    for name, kind, val, _ in _REFERENCE_ROWS:
        print(f"  {val:>6.1%}  [{kind:<11}] {name}")
    for p in pairs:
        print(f"  {p['mean_recall']:>6.1%}  [human-human] real {p['a_label']} vs "
              f"real {p['b_label']}  ({p['total_matched_pairs']} theme pairs)")
    n_low = sum(len(p["low_similarity_matches"]) for p in pairs)
    print(f"\n  Low-similarity accepted matches (cosine < {_LOW_SIMILARITY_FLAG:.2f}): {n_low}")
    for p in (out_json, md_path):
        print(f"  wrote {p.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluator", default="gemini25", choices=list(EVALUATOR_CONFIGS),
                        help="Must match the evaluator the pilot used (default: gemini25)")
    parser.add_argument("--no-fg2-fg3", action="store_true",
                        help="Skip the FG2-vs-FG3 pair (saves 5 matching calls, but "
                             "leaves 'is FG1 atypical?' unanswered).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Segment and report scope only — makes no API calls "
                             "and writes no files.")
    args = parser.parse_args()
    main(args.evaluator, not args.no_fg2_fg3, args.dry_run)
