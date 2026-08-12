"""
Tier 2b — cross-section control: does the matcher follow the QUESTION or the GROUP?

Closing diagnostic. Three facts are already established:

  96.4%   same text, re-extracted           (pilot stability check)
  41-57%  different group, SAME question    (human-vs-human ceiling: FG1/FG2/FG3)
  21.3%   real FG1 vs its own synthetic replica

Two mechanisms explain that pattern and they imply different verdicts:

  (i)  The matcher tracks the guide QUESTION. Section-scoped extraction yields
       topic-level themes ("Gender's influence on food choices" — defined as
       "participants' differing views on WHETHER gender plays a role"), and the
       topic is fixed by the question every group was asked. Then the defect is
       Tier 2b's per-question design.
  (ii) `match_tier2_themes` is simply permissive. Then the defect reaches the
       whole-transcript Tier 2 as well, not just Tier 2b.

This script separates them by completing a 2x2 over {same/different group} x
{same/different question}. The two new cells are scored here:

                       | same question        | different question
    -------------------+----------------------+---------------------
    same group         | 96.4% (known)        | THIS SCRIPT
    different group    | 41-57% (known)       | THIS SCRIPT

  - If both new cells collapse toward 0%  -> mechanism (i): question-driven.
  - If same-group/different-question stays high -> the matcher tracks the group,
    and the per-question design is not the problem.
  - If both new cells land at 20-40%      -> mechanism (ii): general permissiveness,
    which implicates match_tier2_themes itself.

TOPIC DISTANCE IS GRADED, not binary. Guide sections 4 ("Imagining a plant-based
shift") and 5 ("Making plant-based foods more appealing") are adjacent topics, so
an s4-vs-s5 pair is NOT a clean different-topic test. Rather than drop it, two
such pairs are included and labelled `related_topic`: under mechanism (i) they
should score between the unrelated cross pairs and the same-section baseline.
A monotone gradient is itself evidence for (i).

RECALL HERE IS A CONTROL FIGURE, NOT FIDELITY. The two sides answer different
guide questions by construction, so there is no sense in which one "should"
reproduce the other. The number means only "how readily does the matcher pair
these theme sets".

NO NEW EXTRACTION. Every theme set is loaded from
`analysis/coding_frame/tier2b_human_ceiling_fg1_fg2_fg3.json`, which carries the
verified FG1, FG2 and FG3 themes for all five sections — the identical sets the
human-vs-human ceiling scored. Only `match_tier2_themes` is called.

ADDITIVE AND READ-ONLY. `thematic_coding.py` extraction functions are not touched
or called. Nothing is written to `data/`. The pilot, discrimination-control and
ceiling scripts are imported for helpers and left unmodified.

Usage:
    py scripts/validate_tier2b_cross_section_control.py --dry-run
    py scripts/validate_tier2b_cross_section_control.py [--evaluator gemini25]
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
    SupportingQuote,
    Tier2Result,
    Tier2Theme,
    match_tier2_themes,
)
from validate_tier2b_human_ceiling import _accepted_pair_similarities  # noqa: E402

_OUT_DIR  = _REPO_ROOT / "analysis" / "coding_frame"
_DOCS_DIR = _REPO_ROOT / "docs" / "findings"

_DATE = "2026-07-29"

_CEILING_JSON = _OUT_DIR / "tier2b_human_ceiling_fg1_fg2_fg3.json"

# Emitted as part of the generated markdown, NOT hand-patched into the .md
# afterwards: _write_md rebuilds the file from scratch on every call, so a manual
# banner would be silently erased the next time this script ran. This is the final
# document in the chain, so it carries an orientation header rather than a
# superseded notice.
_CHAIN_HEADER = [
    "> ## Final document in the Tier 2b diagnostic chain",
    ">",
    "> This document carries the verdict. It is the fourth and last of four, each of which",
    "> raised the question the next one answered:",
    ">",
    "> 1. **Pilot** — `2026-07-29_tier2b_guide_question_pilot.md`. Real FG1 vs synth FG1,",
    ">    per guide question: **21.3%** mean recall, extraction stable at **96.4%** on",
    ">    re-extraction. Uninterpretable without a floor → asked for a discrimination control.",
    "> 2. **Discrimination control** — `2026-07-29_tier2b_discrimination_control.md`. Real",
    ">    FG1 vs deliberately mismatched synth FG5: **44.7%** (run01, primary) and **18.3%**",
    ">    (run03). The primary control scored *above* the matched pair — margin **−23.3%**,",
    ">    the wrong sign → asked for a human-vs-human ceiling.",
    "> 3. **Human ceiling** — `2026-07-29_tier2b_human_ceiling.md`. Real groups scored",
    ">    against each other on the same questions: **57.0%** (FG1↔FG2), **43.7%**",
    ">    (FG1↔FG3), **41.3%** (FG2↔FG3). Ambiguous — above the matched synthetic pair, but",
    ">    overlapping the mismatched one → asked for this cross-section control.",
    "> 4. **Cross-section control** — this document. Same transcript, *different* guide",
    ">    questions: **0.0%**. Different groups, different questions: **8.0%**. Different",
    ">    groups, *related* questions: **50.0%**.",
    ">",
    "> **Verdict:** the matcher tracks the guide question, not group identity. Tier 2b's",
    "> recall/precision is **retired as fidelity evidence**; the per-section theme lists",
    "> **remain valid as descriptive output**. `match_tier2_themes` is *not* implicated in",
    "> general — it returned exactly 0.0% on 7 of 8 genuinely unrelated-topic comparisons,",
    "> so the whole-transcript Tier 2 and its Gate 2 margin are unaffected.",
    "",
]

# The pilot's _with_retry tops out at 155s of cumulative backoff, which the
# endpoint outlasted on the first attempt at this run (sustained 503 UNAVAILABLE,
# "high demand"). This run is only 10 calls and each is idempotent, so it can
# afford to be far more patient. Defined locally rather than by widening the
# pilot's helper, which stays byte-identical.
_RETRY_DELAYS = (20, 60, 120, 240, 300, 300)


def _patient_retry(fn, *args, **kwargs):
    import time
    from google.genai import errors as genai_errors

    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            return fn(*args, **kwargs)
        except genai_errors.ServerError as exc:
            if delay is None:
                raise
            print(f"\n      [transient] {str(exc)[:70]} — retrying in {delay}s "
                  f"(attempt {attempt + 1}/{len(_RETRY_DELAYS)}) ...", flush=True)
            time.sleep(delay)


_SECTION_LABELS = {
    1: "Opening discussion: male friendship and place",
    2: "Everyday food decision-making",
    3: "Gender and food choice",
    4: "Imagining a plant-based shift",
    5: "Making plant-based foods more appealing",
}

# Sections 4 and 5 are both about plant-based eating — a pair spanning them is a
# related-topic test, not an unrelated-topic one.
_RELATED_SECTIONS = {frozenset({4, 5})}


def _topic_relation(sec_a: int, sec_b: int) -> str:
    if sec_a == sec_b:
        return "same_topic"
    if frozenset({sec_a, sec_b}) in _RELATED_SECTIONS:
        return "related_topic"
    return "unrelated_topic"


# --- The pair grid ----------------------------------------------------------
# (group_a, section_a, group_b, section_b, cell)
#
# Same group / different question — the cell that separates "tracks the group"
# from "tracks the question". One pair per group so no single transcript drives it.
_SAME_GROUP_CROSS = [
    ("fg1", 2, "fg1", 4),
    ("fg2", 1, "fg2", 3),
    ("fg3", 3, "fg3", 5),
]

# Different group / different question, unrelated topics. The first three are the
# pairs requested; the last two vary the group combination and section distance so
# the result does not rest on one arrangement.
_CROSS_GROUP_CROSS = [
    ("fg1", 2, "fg2", 4),
    ("fg1", 3, "fg3", 5),
    ("fg2", 1, "fg3", 4),
    ("fg1", 1, "fg3", 3),
    ("fg1", 5, "fg2", 2),
]

# Different group / different question, RELATED topics (s4 vs s5) — intermediate rung.
_CROSS_GROUP_RELATED = [
    ("fg1", 4, "fg2", 5),
    ("fg2", 4, "fg3", 5),
]


def build_pair_grid() -> list[dict]:
    grid: list[dict] = []
    for cell, pairs in (
        ("same_group_diff_question", _SAME_GROUP_CROSS),
        ("diff_group_diff_question", _CROSS_GROUP_CROSS),
        ("diff_group_related_question", _CROSS_GROUP_RELATED),
    ):
        for ga, sa, gb, sb in pairs:
            grid.append({
                "cell": cell,
                "group_a": ga, "section_a": sa,
                "group_b": gb, "section_b": sb,
                "topic_relation": _topic_relation(sa, sb),
            })
    return grid


# ---------------------------------------------------------------------------
# Theme loading — no extraction
# ---------------------------------------------------------------------------

def load_all_themes(path: Path) -> tuple[dict[str, dict[int, Tier2Result]], str]:
    """Load the verified FG1/FG2/FG3 per-section themes from the ceiling run."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[int, Tier2Result]] = {}
    for label, sections in payload["extracted_themes"].items():
        out[label] = {
            int(idx): Tier2Result(themes=[
                Tier2Theme(
                    theme_label=t["theme_label"],
                    theme_definition=t["theme_definition"],
                    supporting_quotes=[SupportingQuote(**q) for q in t["verified_quotes"]],
                    verified_quotes=[SupportingQuote(**q) for q in t["verified_quotes"]],
                    participant_count=t["participant_count"],
                )
                for t in themes
            ])
            for idx, themes in sections.items()
        }
    return out, payload["evaluator"]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_cross_pair(
    spec: dict,
    themes: dict[str, dict[int, Tier2Result]],
    evaluator_cfg: dict | None,
) -> dict:
    ga, sa, gb, sb = spec["group_a"], spec["section_a"], spec["group_b"], spec["section_b"]
    a_res, b_res = themes[ga][sa], themes[gb][sb]

    tag = f"{ga}_s{sa} x {gb}_s{sb}"
    print(f"  {tag:<24} [{spec['cell']}, {spec['topic_relation']}] ...", end=" ", flush=True)
    scores = _patient_retry(
        match_tier2_themes,
        a_res, b_res,
        run_label=f"tier2b_crosssection__{ga}_s{sa}__vs__{gb}_s{sb}",
        evaluator_cfg=evaluator_cfg,
    )
    sims = _accepted_pair_similarities(a_res, b_res, scores.matched_pairs)
    print(f"{len(scores.matched_pairs)} matched  recall={scores.recall:.1%}  "
          f"precision={scores.precision:.1%}")

    pairs = []
    for (i, j), sim in zip(scores.matched_pairs, sims):
        pairs.append({
            "a_theme": a_res.themes[i].theme_label,
            "a_definition": a_res.themes[i].theme_definition,
            "b_theme": b_res.themes[j].theme_label,
            "b_definition": b_res.themes[j].theme_definition,
            "embedding_similarity": None if sim is None else round(sim, 3),
        })
        print(f"      sim={pairs[-1]['embedding_similarity']}  "
              f"'{pairs[-1]['a_theme']}' <-> '{pairs[-1]['b_theme']}'")

    return {
        **spec,
        "section_a_label": _SECTION_LABELS.get(sa, "?"),
        "section_b_label": _SECTION_LABELS.get(sb, "?"),
        "a_themes": len(a_res.themes),
        "b_themes": len(b_res.themes),
        "matched":   len(scores.matched_pairs),
        "recall":    round(scores.recall, 4),
        "precision": round(scores.precision, 4),
        "matched_pairs": pairs,
        "disagreements": [
            {**d,
             "a_theme": a_res.themes[d["ri"]].theme_label,
             "b_theme": b_res.themes[d["si"]].theme_label}
            for d in scores.disagreements
        ],
    }


def summarise_cells(rows: list[dict]) -> dict:
    cells: dict[str, dict] = {}
    for cell in ("same_group_diff_question", "diff_group_diff_question",
                 "diff_group_related_question"):
        subset = [r for r in rows if r["cell"] == cell]
        if not subset:
            continue
        cells[cell] = {
            "n_pairs": len(subset),
            "mean_recall":    round(sum(r["recall"] for r in subset) / len(subset), 4),
            "mean_precision": round(sum(r["precision"] for r in subset) / len(subset), 4),
            "total_matched":  sum(r["matched"] for r in subset),
            "recall_range": [min(r["recall"] for r in subset),
                             max(r["recall"] for r in subset)],
        }
    return cells


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

_KNOWN = [
    ("Same text, re-extracted (pilot stability)", "same group, same question", 0.964),
    ("real FG1 ↔ real FG2 (human ceiling)", "diff group, same question", 0.570),
    ("real FG1 ↔ real FG3 (human ceiling)", "diff group, same question", 0.437),
    ("real FG2 ↔ real FG3 (human ceiling)", "diff group, same question", 0.413),
    ("real FG1 ↔ synth FG1 run01 (matched)", "synthetic, same question", 0.213),
    ("real FG1 ↔ synth FG5 run01 (mismatched)", "synthetic, same question", 0.447),
    ("real FG1 ↔ synth FG5 run03 (mismatched)", "synthetic, same question", 0.183),
]


def _write_md(evaluator_cfg: dict | None, rows: list[dict], cells: dict) -> Path:
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = _DOCS_DIR / f"{_DATE}_tier2b_cross_section_control.md"

    ecfg = evaluator_cfg or {}
    model = ecfg.get("model", "gemini-2.5-flash")
    params = (f"thinking_level={ecfg['thinking_level']}" if ecfg.get("thinking_level")
              else f"temperature={ecfg.get('temperature', 0.0)}")

    lines = [
        "# Tier 2b — Cross-Section Control (does the matcher follow the question or the group?)",
        "",
        *_CHAIN_HEADER,
        f"**Date:** {_DATE}  ",
        f"**Evaluator:** `{model}` ({params}) — identical to every prior Tier 2b run  ",
        f"**Themes:** reused verbatim from `analysis/coding_frame/{_CEILING_JSON.name}` — "
        f"**no new extraction**; only `match_tier2_themes` was called  ",
        "**Read-only:** no synthetic generation; nothing written to `data/`.",
        "",
        "> **Recall here is a control figure, not fidelity.** The two sides answer",
        "> different guide questions by construction, so neither \"should\" reproduce the",
        "> other. The number means only: how readily does the matcher pair these two",
        "> theme sets?",
        "",
        "---",
        "",
        "## Part A — The 2×2",
        "",
        "| | same question | different question |",
        "|---|---|---|",
        f"| **same group** | 96.4% _(pilot stability)_ | "
        f"**{cells['same_group_diff_question']['mean_recall']:.1%}** _(this run, "
        f"{cells['same_group_diff_question']['n_pairs']} pairs)_ |",
        f"| **different group** | 41.3–57.0% _(human ceiling)_ | "
        f"**{cells['diff_group_diff_question']['mean_recall']:.1%}** _(this run, "
        f"{cells['diff_group_diff_question']['n_pairs']} pairs)_ |",
        "",
        f"Intermediate rung — different group, **related** question (guide sections 4↔5, "
        f"both about plant-based eating): "
        f"**{cells['diff_group_related_question']['mean_recall']:.1%}** "
        f"({cells['diff_group_related_question']['n_pairs']} pairs).",
        "",
        "---",
        "",
        "## Part B — Every cross pair",
        "",
        "| Cell | Pair | Section A | Section B | Topic | A themes | B themes | Matched | Recall | Precision |",
        "|------|------|-----------|-----------|-------|---------:|---------:|--------:|-------:|----------:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['cell']} | {r['group_a']} s{r['section_a']} × {r['group_b']} s{r['section_b']} | "
            f"{r['section_a_label']} | {r['section_b_label']} | {r['topic_relation']} | "
            f"{r['a_themes']} | {r['b_themes']} | {r['matched']} | "
            f"{r['recall']:.1%} | {r['precision']:.1%} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Part C — All figures on one scale",
        "",
        "| Comparison | Condition | Mean recall |",
        "|------------|-----------|------------:|",
    ]
    for name, cond, val in _KNOWN:
        lines.append(f"| {name} | {cond} | {val:.1%} |")
    for cell, label in (
        ("same_group_diff_question", "same group, DIFFERENT question"),
        ("diff_group_related_question", "diff group, RELATED question"),
        ("diff_group_diff_question", "diff group, DIFFERENT question"),
    ):
        if cell in cells:
            lines.append(f"| **Cross-section control ({cell})** | {label} | "
                         f"**{cells[cell]['mean_recall']:.1%}** |")

    lines += [
        "",
        "---",
        "",
        "## Part D — Accepted matches across different questions",
        "",
        "Any pairing here joins themes drawn from answers to *different* guide",
        "questions, so every accepted match is worth inspecting on its own terms.",
        "",
    ]
    any_match = False
    for r in rows:
        if not r["matched_pairs"]:
            continue
        any_match = True
        lines += [f"**{r['group_a']} s{r['section_a']} ({r['section_a_label']}) × "
                  f"{r['group_b']} s{r['section_b']} ({r['section_b_label']})** "
                  f"— {r['topic_relation']}", ""]
        for m in r["matched_pairs"]:
            lines.append(f"- sim={m['embedding_similarity']}: _{m['a_theme']}_ ↔ "
                         f"_{m['b_theme']}_")
            lines.append(f"  - A: {m['a_definition']}")
            lines.append(f"  - B: {m['b_definition']}")
        lines.append("")
    if not any_match:
        lines += ["_No pair was accepted in any cross-question comparison._", ""]

    lines += [
        "---",
        "",
        f"_Auto-generated by `scripts/validate_tier2b_cross_section_control.py`. "
        f"Theme sets from `{_CEILING_JSON.name}`; no extraction call was made._",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(evaluator_key: str, dry_run: bool) -> None:
    ecfg = EVALUATOR_CONFIGS.get(evaluator_key)
    if ecfg is None:
        print(f"Unknown evaluator key '{evaluator_key}'. Choose from: {list(EVALUATOR_CONFIGS)}")
        sys.exit(1)

    print("=" * 72)
    print("  TIER 2b — CROSS-SECTION CONTROL (question-driven or group-driven?)")
    print(f"  Evaluator: {ecfg.get('model')}"
          + ("   [DRY RUN — no API calls]" if dry_run else ""))
    print("=" * 72)

    themes, ceiling_evaluator = load_all_themes(_CEILING_JSON)
    if ceiling_evaluator != ecfg.get("model"):
        print(f"\nEvaluator mismatch: stored themes were extracted with "
              f"'{ceiling_evaluator}' but this run requests '{ecfg.get('model')}'. "
              f"Stopping.")
        sys.exit(1)
    print(f"\n[Themes] groups {sorted(themes)}, sections "
          f"{sorted(themes['fg1'])} — reused, evaluator '{ceiling_evaluator}' confirmed. "
          f"No extraction call will be made.")

    grid = build_pair_grid()
    for spec in grid:
        for g, s in ((spec["group_a"], spec["section_a"]), (spec["group_b"], spec["section_b"])):
            if s not in themes.get(g, {}):
                print(f"\nMissing themes for {g} section {s}. Stopping.")
                sys.exit(2)

    print(f"[Scope] {len(grid)} cross pairs = {len(grid)} matching calls "
          f"(no extraction)")
    for cell in ("same_group_diff_question", "diff_group_diff_question",
                 "diff_group_related_question"):
        n = sum(1 for s in grid if s["cell"] == cell)
        print(f"          {cell}: {n}")

    if dry_run:
        for spec in grid:
            print(f"    {spec['group_a']} s{spec['section_a']} × "
                  f"{spec['group_b']} s{spec['section_b']}  "
                  f"[{spec['cell']}, {spec['topic_relation']}]")
        print("\nDry run — stopping before any API call. No files written.")
        return

    print()
    rows = [score_cross_pair(spec, themes, ecfg) for spec in grid]
    cells = summarise_cells(rows)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = _OUT_DIR / "tier2b_cross_section_control.json"
    out_json.write_text(json.dumps({
        "date":      _DATE,
        "evaluator": ecfg.get("model"),
        "evaluator_config": ecfg,
        "themes_source": str(_CEILING_JSON),
        "no_extraction_performed": True,
        "read_only": True,
        "recall_is_control_not_fidelity": (
            "The two sides of every pair answer different guide questions by "
            "construction. Recall here measures only how readily the matcher pairs "
            "two theme sets; it is not a fidelity measure."
        ),
        "related_topic_note": (
            "Guide sections 4 and 5 are both about plant-based eating, so pairs "
            "spanning them are labelled related_topic and reported as an "
            "intermediate rung rather than as unrelated-topic controls."
        ),
        "cross_pairs": rows,
        "cells": cells,
        "known_figures": [
            {"comparison": n, "condition": c, "mean_recall": v} for n, c, v in _KNOWN
        ],
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md_path = _write_md(ecfg, rows, cells)

    print("\n" + "=" * 72)
    print("  SUMMARY — 2x2 completed")
    print("=" * 72)
    print(f"  {'':<34} {'same question':>16} {'different question':>20}")
    print(f"  {'same group':<34} {'96.4%':>16} "
          f"{cells['same_group_diff_question']['mean_recall']:>19.1%}")
    print(f"  {'different group':<34} {'41.3-57.0%':>16} "
          f"{cells['diff_group_diff_question']['mean_recall']:>19.1%}")
    print(f"\n  different group, RELATED question (s4x s5): "
          f"{cells['diff_group_related_question']['mean_recall']:.1%}")
    for cell, c in cells.items():
        print(f"  {cell}: mean recall {c['mean_recall']:.1%} "
              f"(range {c['recall_range'][0]:.0%}-{c['recall_range'][1]:.0%}), "
              f"{c['total_matched']} theme pairs over {c['n_pairs']} comparisons")
    for p in (out_json, md_path):
        print(f"  wrote {p.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluator", default="gemini25", choices=list(EVALUATOR_CONFIGS),
                        help="Must match the evaluator used throughout (default: gemini25)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show the pair grid and stop — no API calls, no files.")
    args = parser.parse_args()
    main(args.evaluator, args.dry_run)
