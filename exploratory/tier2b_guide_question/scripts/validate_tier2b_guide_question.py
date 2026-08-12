"""
Tier 2b — emergent thematic fidelity PER GUIDE QUESTION (FG1 pilot).

Answers a question neither existing layer answers: for each concrete question in
the discussion guide, what themes emerge in the human responses versus the
synthetic ones? Tier 2 extracts themes over the whole transcript with no notion
of which question a turn belongs to; guide coverage (§5, Appendix I) is a binary
covered/omitted label, not content coding.

ADDITIVE. `extract_themes_tier2`, `verify_tier2_themes`, `match_tier2_themes`
and `_embedding_similarities` are called unmodified — just with a section's
`blind_text` instead of a whole transcript's. The whole-transcript Tier 2 is not
touched and is not re-run here.

BLIND AND SYMMETRIC. Both sides are rendered by the same `to_blind_text()` into
the same `[T00N] Speaker: ...` form, sliced by `scripts/tier2b_segmentation.py`
with global turn ids preserved. The evaluator sees only transcript text: no
names, no provenance, no section label, no side marker. `run_label` is an
internal audit key written to gemini_calls.jsonl — it never enters a prompt.

STATUS: exploratory. Per-section extraction has none of the validation gates the
whole-transcript Tier 2 has (5-run repeatability, discrimination). The stability
check below is a noise floor, not a Gate-1 substitute.

Usage:
    py scripts/validate_tier2b_guide_question.py --dry-run     # segmentation only, no API calls
    py scripts/validate_tier2b_guide_question.py [--evaluator gemini25|gemininext]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from thematic_coding import (          # noqa: E402
    EVALUATOR_CONFIGS,
    Tier2Result,
    extract_themes_tier2,
    match_tier2_themes,
)
from tier2b_segmentation import (      # noqa: E402
    MIN_PARTICIPANT_TURNS,
    MIN_WORDS,
    SegmentationResult,
    comparable_sections,
    crosscheck_synthetic_against_state_files,
    segment_human_by_guide,
    segment_synthetic_by_guide,
)

_OUT_DIR  = _REPO_ROOT / "analysis" / "coding_frame"
_DOCS_DIR = _REPO_ROOT / "docs" / "findings"

_DATE = "2026-07-29"

# --- Pilot scope (Phase 3): FG1 only, one designated synthetic run -----------
_HUMAN_FG1 = (_REPO_ROOT / "data" / "datasets_transcripts" / "standardized"
              / "macho_meals" / "fg1" / "transcript.json")

# macho_meals_fg1_run01 is the designated principal run: after the 2026-07-29
# replicate renumbering it is replicate 1 of the three production FG1 runs, it
# is the longest and most complete (72 entries, all 7 guide sections reached),
# and its section boundaries cross-check clean against its own state files.
_SYNTH_RUN_DIR = _REPO_ROOT / "output" / "session_logs" / "macho_meals_fg1_run01"

_HUMAN_LABEL = "human_fg1"
_SYNTH_LABEL = "synth_fg1_run01"

_STABILITY_EXTRA_RUNS = 2   # 2 extra extractions on top of the main pass


# ---------------------------------------------------------------------------
# Superseded banner
# ---------------------------------------------------------------------------
# Emitted as part of the generated markdown, NOT hand-patched into the .md
# afterwards: _write_md rebuilds the file from scratch on every call, so a manual
# banner would be silently erased the next time this script (or its offline
# regeneration path) ran.
_SUPERSEDED_BANNER = [
    "> ## ⚠ Superseded — see final verdict",
    ">",
    "> **This document's own next-step recommendation was resolved by later diagnostics in",
    "> this same chain.** Part D below called for a discrimination control before scaling;",
    "> that control was run, and it — together with the human-ceiling and cross-section",
    "> controls that followed — settled the question against this layer.",
    ">",
    "> **Final decision:** Tier 2b's recall/precision is **retired as fidelity evidence**",
    "> (the matcher tracks the guide question, not group identity — confirmed by the",
    "> cross-section control). The per-section theme lists below **remain valid as",
    "> descriptive output**: they are stable on re-extraction and quote-verified.",
    ">",
    "> The 21.3% mean recall reported here must **not** be cited as evidence about",
    "> synthetic fidelity.",
    ">",
    "> Full chain and reasoning: `docs/findings/2026-07-29_tier2b_cross_section_control.md`.",
    ">",
    "> _Nothing below has been altered — this document is retained as the record of the",
    "> diagnostic process._",
    "",
]


# ---------------------------------------------------------------------------
# Transient-error backoff
# ---------------------------------------------------------------------------
# thematic_coding._generate_with_fallback retries 429 (quota) onto the backup
# key, but a 503 UNAVAILABLE ("model experiencing high demand") is a transient
# server-side spike with no key to fall back to, and it aborts a run mid-way.
# Retrying here rather than in thematic_coding keeps Tier 2's call path
# untouched, as required.

_RETRY_DELAYS = (5, 15, 45, 90)


def _with_retry(fn, *args, **kwargs):
    from google.genai import errors as genai_errors

    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            return fn(*args, **kwargs)
        except genai_errors.ServerError as exc:
            if delay is None:
                raise
            print(f"\n  [transient] {str(exc)[:90]} — retrying in {delay}s "
                  f"(attempt {attempt + 1}/{len(_RETRY_DELAYS)}) ...", flush=True)
            time.sleep(delay)


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _print_segmentation(result: SegmentationResult) -> None:
    print(f"\n[{result.side}] {Path(result.source_path).parent.name} "
          f"— boundaries from {result.boundary_method}")
    for w in result.warnings:
        print(f"  ⚑ {w}")
    if result.unassigned_entry_indices:
        print(f"  {len(result.unassigned_entry_indices)} entries unassigned "
              f"(no guide counterpart)")
    print(f"  {'idx':>3}  {'section':<44} {'p-turns':>7} {'words':>6} "
          f"{'spk':>3}  {'turn ids':<12} floor")
    for idx in result.section_indices():
        c = result.sections[idx].counts()
        print(f"  {c['section_index']:>3}  {c['section_label'][:44]:<44} "
              f"{c['participant_turns']:>7} {c['total_words']:>6} "
              f"{c['distinct_participants']:>3}  "
              f"{c['first_turn_id']}-{c['last_turn_id']:<6} "
              f"{'ok' if c['meets_floor'] else 'BELOW'}")


def _theme_to_dict(t) -> dict:
    return {
        "theme_label":       t.theme_label,
        "theme_definition":  t.theme_definition,
        "participant_count": t.participant_count,
        "verified_quotes": [
            {"turn_id": q.turn_id, "speaker": q.speaker, "quote": q.quote}
            for q in t.verified_quotes
        ],
        "unverified_quote_count": len(t.supporting_quotes) - len(t.verified_quotes),
        # position_thirds is deliberately omitted: verify_tier2_themes computes it
        # from the *section's* line count while turn ids stay global, so the
        # thirds would be meaningless here. Position bias remains a
        # whole-transcript Tier 2 measure.
    }


def _pick_stability_sections(human: SegmentationResult, indices: list[int]) -> list[int]:
    """
    Choose up to 3 sections for the stability re-runs (cost-capped, per Phase 3).

    Picks the smallest, median and largest comparable section by human word
    count — extraction noise is most likely to track section size, so spanning
    the range is more informative than sampling adjacent sections.
    """
    if len(indices) <= 3:
        return list(indices)
    by_words = sorted(indices, key=lambda i: human.sections[i].total_words)
    return sorted({by_words[0], by_words[len(by_words) // 2], by_words[-1]})


# ---------------------------------------------------------------------------
# Per-section extraction and matching
# ---------------------------------------------------------------------------

def run_sections(
    human: SegmentationResult,
    synthetic: SegmentationResult,
    indices: list[int],
    evaluator_cfg: dict | None,
) -> tuple[list[dict], dict[int, Tier2Result], dict[int, Tier2Result]]:
    """Extract themes on both sides of every comparable section, then match
    within — and only within — the same section."""
    rows: list[dict] = []
    human_results: dict[int, Tier2Result] = {}
    synth_results: dict[int, Tier2Result] = {}

    for idx in indices:
        h_seg = human.sections[idx]
        s_seg = synthetic.sections[idx]
        label_slug = h_seg.section_label.lower().replace(" ", "_")[:40]

        print(f"\n[Section {idx}] {h_seg.section_label}")
        print(f"  human    ({h_seg.participant_turns} p-turns, {h_seg.total_words} words) ...",
              end=" ", flush=True)
        h_res = _with_retry(
            extract_themes_tier2,
            h_seg.blind_text,
            run_label=f"tier2b_{_HUMAN_LABEL}__section_{idx}_{label_slug}",
            evaluator_cfg=evaluator_cfg,
        )
        print(f"{len(h_res.themes)} themes")

        print(f"  synthetic ({s_seg.participant_turns} p-turns, {s_seg.total_words} words) ...",
              end=" ", flush=True)
        s_res = _with_retry(
            extract_themes_tier2,
            s_seg.blind_text,
            run_label=f"tier2b_{_SYNTH_LABEL}__section_{idx}_{label_slug}",
            evaluator_cfg=evaluator_cfg,
        )
        print(f"{len(s_res.themes)} themes")

        print(f"  matching within section {idx} ...", end=" ", flush=True)
        scores = _with_retry(
            match_tier2_themes,
            h_res, s_res,
            run_label=f"tier2b_match__section_{idx}_{label_slug}",
            evaluator_cfg=evaluator_cfg,
        )
        print(f"{len(scores.matched_pairs)} matched  "
              f"recall={scores.recall:.1%}  precision={scores.precision:.1%}")

        human_results[idx] = h_res
        synth_results[idx] = s_res
        rows.append({
            "section_index":   idx,
            "section_label":   h_seg.section_label,
            "human_counts":     h_seg.counts(),
            "synthetic_counts": s_seg.counts(),
            "human_themes":     len(h_res.themes),
            "synthetic_themes": len(s_res.themes),
            "matched":          len(scores.matched_pairs),
            "recall":           round(scores.recall, 4),
            "precision":        round(scores.precision, 4),
            "matched_pairs": [
                {"human": h_res.themes[i].theme_label,
                 "synthetic": s_res.themes[j].theme_label}
                for i, j in scores.matched_pairs
            ],
            "emergent_themes": [
                {"theme_label": t.theme_label,
                 "participant_count": t.participant_count}
                for t in scores.emergent_themes
            ],
            "missed_themes": [
                {"theme_label": t.theme_label,
                 "participant_count": t.participant_count}
                for t in scores.missed_themes
            ],
            # Full detail, not just a count: when a section scores 0 matched,
            # these judge-vs-embedding disagreements are the only way to tell a
            # genuinely divergent section from an over-strict semantic judge.
            "disagreements": [
                {**d,
                 "human_theme":     h_res.themes[d["ri"]].theme_label,
                 "synthetic_theme": s_res.themes[d["si"]].theme_label}
                for d in scores.disagreements
            ],
            "disagreement_count": len(scores.disagreements),
        })

    return rows, human_results, synth_results


# ---------------------------------------------------------------------------
# Minimum stability check
# ---------------------------------------------------------------------------

def run_stability_check(
    human: SegmentationResult,
    synthetic: SegmentationResult,
    stability_indices: list[int],
    human_run1: dict[int, Tier2Result],
    synth_run1: dict[int, Tier2Result],
    evaluator_cfg: dict | None,
) -> list[dict]:
    """
    Re-extract each chosen section `_STABILITY_EXTRA_RUNS` more times per side
    and report mean pairwise agreement across the 3 runs. Run 1 is reused from
    the main pass, so this costs 2 extra extractions per section per side.

    This is a noise floor, NOT a validation gate: it says whether the numbers
    above are worth reading, not whether the method is validated.
    """
    out: list[dict] = []
    for idx in stability_indices:
        for side, seg, run1 in (
            ("human", human.sections[idx], human_run1[idx]),
            ("synthetic", synthetic.sections[idx], synth_run1[idx]),
        ):
            print(f"\n[Stability] section {idx} ({seg.section_label}) — {side}")
            runs: list[Tier2Result] = [run1]
            for k in range(2, _STABILITY_EXTRA_RUNS + 2):
                print(f"  extraction {k}/{_STABILITY_EXTRA_RUNS + 1} ...", end=" ", flush=True)
                runs.append(_with_retry(
                    extract_themes_tier2,
                    seg.blind_text,
                    run_label=f"tier2b_stability_{side}__section_{idx}_run{k}",
                    evaluator_cfg=evaluator_cfg,
                ))
                print(f"{len(runs[-1].themes)} themes")

            pairwise: list[dict] = []
            for a in range(len(runs)):
                for b in range(a + 1, len(runs)):
                    sc = _with_retry(
                        match_tier2_themes,
                        runs[a], runs[b],
                        run_label=f"tier2b_stability_match_{side}__section_{idx}_r{a+1}_r{b+1}",
                        evaluator_cfg=evaluator_cfg,
                    )
                    pairwise.append({
                        "pair": f"run{a+1}_vs_run{b+1}",
                        "matched": len(sc.matched_pairs),
                        "recall": round(sc.recall, 3),
                        "precision": round(sc.precision, 3),
                    })
                    print(f"  run{a+1} vs run{b+1}: {len(sc.matched_pairs)} matched, "
                          f"recall={sc.recall:.1%}")

            mean_recall = (sum(p["recall"] for p in pairwise) / len(pairwise)
                           if pairwise else 0.0)
            # Same thresholds the whole-transcript Tier-2 repeatability uses.
            if mean_recall >= 0.75:
                verdict = "stable"
            elif mean_recall >= 0.50:
                verdict = "moderately stable"
            else:
                verdict = "unstable"
            print(f"  → mean pairwise recall {mean_recall:.1%} — {verdict}")

            out.append({
                "section_index": idx,
                "section_label": seg.section_label,
                "side": side,
                "theme_counts": [len(r.themes) for r in runs],
                "pairwise": pairwise,
                "mean_pairwise_recall": round(mean_recall, 3),
                "verdict": verdict,
            })
    return out


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def _write_transcript_json(
    label: str,
    seg_result: SegmentationResult,
    theme_results: dict[int, Tier2Result],
    evaluator: str,
) -> Path:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUT_DIR / f"tier2b_guide_question_{label}.json"
    payload = {
        "label":            label,
        "side":             seg_result.side,
        "source_path":      seg_result.source_path,
        "evaluator":        evaluator,
        "boundary_method":  seg_result.boundary_method,
        "segmentation_warnings": seg_result.warnings,
        "sections": [
            {
                **seg_result.sections[idx].counts(),
                "turn_ids": seg_result.sections[idx].turn_ids,
                "extracted": idx in theme_results,
                "themes": ([_theme_to_dict(t) for t in theme_results[idx].themes]
                           if idx in theme_results else []),
            }
            for idx in seg_result.section_indices()
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_md(
    evaluator_label: str,
    evaluator_cfg: dict | None,
    human: SegmentationResult,
    synthetic: SegmentationResult,
    rows: list[dict],
    skipped: list[dict],
    stability: list[dict],
    crosscheck: dict,
) -> Path:
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = _DOCS_DIR / f"{_DATE}_tier2b_guide_question_pilot.md"

    ecfg = evaluator_cfg or {}
    model = ecfg.get("model", "gemini-2.5-flash")
    params = (f"thinking_level={ecfg['thinking_level']}" if ecfg.get("thinking_level")
              else f"temperature={ecfg.get('temperature', 0.0)}")

    lines: list[str] = [
        "# Tier 2b — Emergent Thematic Fidelity by Guide Question (FG1 pilot)",
        "",
        *_SUPERSEDED_BANNER,
        f"**Date:** {_DATE}  ",
        f"**Evaluator:** `{model}` ({params})  ",
        f"**Human:** `{Path(human.source_path).relative_to(_REPO_ROOT)}`  ",
        f"**Synthetic:** `{Path(synthetic.source_path).relative_to(_REPO_ROOT)}` "
        f"(designated principal FG1 run)  ",
        f"**Data floor:** MIN_PARTICIPANT_TURNS={MIN_PARTICIPANT_TURNS}, MIN_WORDS={MIN_WORDS}",
        "",
        "> **Exploratory.** Per-section extraction is a new method without the validation",
        "> gates the whole-transcript Tier 2 has (5-run repeatability, discrimination).",
        "> The stability check in Part C is a noise floor, not a Gate-1 substitute.",
        "> All figures are n=1 group, n=1 synthetic run.",
        "",
        "---",
        "",
        "## Part A — Segmentation",
        "",
        "| Side | Boundary signal | Sections found | Entries unassigned |",
        "|------|----------------|---------------|--------------------|",
        f"| Human | {human.boundary_method} | {len(human.sections)} | "
        f"{len(human.unassigned_entry_indices)} |",
        f"| Synthetic | {synthetic.boundary_method} | {len(synthetic.sections)} | "
        f"{len(synthetic.unassigned_entry_indices)} |",
        "",
        f"Synthetic boundaries cross-checked against `state_turn_*.json` "
        f"(`current_section_index`): **{crosscheck['entries_agree']} entries agree**, "
        f"{crosscheck['entries_differ_on_boundary_turn']} differ only on a boundary turn "
        f"(expected — the per-turn state index is off by one there), "
        f"**{crosscheck['entries_in_conflict']} genuine conflicts**.",
        "",
        "### Per-section data volume",
        "",
        "| Idx | Section | Human p-turns | Human words | Synth p-turns | Synth words | Status |",
        "|----:|---------|-------------:|-----------:|-------------:|-----------:|--------|",
    ]

    by_idx = {r["section_index"]: r for r in rows}
    skip_by_idx = {s["section_index"]: s for s in skipped}
    for idx in sorted(set(by_idx) | set(skip_by_idx)):
        if idx in by_idx:
            r = by_idx[idx]
            h, s, status = r["human_counts"], r["synthetic_counts"], "compared"
            label = r["section_label"]
        else:
            k = skip_by_idx[idx]
            h, s = k["human_counts"], k["synthetic_counts"]
            status = f"`{k['status']}`"
            label = k["section_label"]
        lines.append(
            f"| {idx} | {label} | {h['participant_turns'] if h else '—'} | "
            f"{h['total_words'] if h else '—'} | "
            f"{s['participant_turns'] if s else '—'} | "
            f"{s['total_words'] if s else '—'} | {status} |"
        )

    if skipped:
        lines += ["", "**Skipped sections (reported, not silently dropped):**", ""]
        for k in skipped:
            lines.append(f"- Section {k['section_index']} — {k['section_label']}: "
                         f"`{k['status']}` — {k['reason']}")

    lines += [
        "",
        "---",
        "",
        "## Part B — Emergent themes by guide question",
        "",
        "Recall = human themes with a synthetic counterpart / all human themes.  ",
        "Precision = synthetic themes with a human counterpart / all synthetic themes.  ",
        "Themes are matched **only within the same section** — never across sections.",
        "",
        "| Idx | Section | Human themes | Synth themes | Matched | Emergent | Missed | Recall | Precision |",
        "|----:|---------|------------:|------------:|--------:|---------:|-------:|-------:|----------:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['section_index']} | {r['section_label']} | {r['human_themes']} | "
            f"{r['synthetic_themes']} | {r['matched']} | {len(r['emergent_themes'])} | "
            f"{len(r['missed_themes'])} | {r['recall']:.1%} | {r['precision']:.1%} |"
        )

    if rows:
        mr = sum(r["recall"] for r in rows) / len(rows)
        mp = sum(r["precision"] for r in rows) / len(rows)
        lines += ["", f"Mean across compared sections: recall **{mr:.1%}**, "
                      f"precision **{mp:.1%}**."]

    lines += [
        "",
        "### Emergent themes (synthetic-only, per section)",
        "",
        "> n=1 caveat: 'emergent' means absent from the matched human group only — ",
        "> not automatically false. `participant_count` is evidence-constrained ",
        "> (distinct participants with a verified quote); 1 flags a possible artifact.",
        "",
    ]
    any_emergent = False
    for r in rows:
        if not r["emergent_themes"]:
            continue
        any_emergent = True
        lines.append(f"**Section {r['section_index']} — {r['section_label']}**")
        lines.append("")
        for e in r["emergent_themes"]:
            flag = " ⚑ single-voice" if e["participant_count"] <= 1 else ""
            lines.append(f"- {e['theme_label']} (participants={e['participant_count']}){flag}")
        lines.append("")
    if not any_emergent:
        lines += ["_No synthetic-only themes in any compared section._", ""]

    lines += ["### Missed themes (human-only, per section)", ""]
    any_missed = False
    for r in rows:
        if not r["missed_themes"]:
            continue
        any_missed = True
        lines.append(f"**Section {r['section_index']} — {r['section_label']}**")
        lines.append("")
        for m in r["missed_themes"]:
            lines.append(f"- {m['theme_label']} (participants={m['participant_count']})")
        lines.append("")
    if not any_missed:
        lines += ["_No human themes went unmatched in any compared section._", ""]

    lines += [
        "---",
        "",
        "## Part C — Minimum stability check",
        "",
        f"{_STABILITY_EXTRA_RUNS + 1} independent extractions of the same section text, "
        "aligned pairwise by the same semantic matcher. Run on a cost-capped subset "
        "(smallest / median / largest compared section by human word count).",
        "",
        "| Idx | Section | Side | Themes per run | Mean pairwise recall | Verdict |",
        "|----:|---------|------|---------------|---------------------:|---------|",
    ]
    for s in stability:
        lines.append(
            f"| {s['section_index']} | {s['section_label']} | {s['side']} | "
            f"{s['theme_counts']} | {s['mean_pairwise_recall']:.1%} | {s['verdict']} |"
        )

    if stability:
        overall = sum(s["mean_pairwise_recall"] for s in stability) / len(stability)
        lines += [
            "",
            f"Overall mean pairwise recall across the checked sections: **{overall:.1%}**.",
            "",
            "Compare against the whole-transcript Tier 2 repeatability reported in "
            "`docs/findings/2026-07-20_tier1reach_tier2.md`: if per-section agreement is "
            "materially lower, the per-section numbers in Part B carry more run-to-run "
            "noise than the whole-transcript layer and should be read as directional only.",
        ]

    lines += [
        "",
        "---",
        "",
        "## Part D — How far these numbers can be read",
        "",
        "**Per-section recall is not comparable to whole-transcript Tier 2 recall.** "
        "Over a whole transcript the matcher may pair a synthetic theme with a human "
        "theme drawn from anywhere in the session; Tier 2b forbids that by "
        "construction. It is a strictly harder test, so a lower number here is "
        "expected and is not by itself evidence of worse fidelity.",
        "",
        "**No discrimination control has been run for Tier 2b.** The whole-transcript "
        "layer establishes its floor by scoring a deliberately mismatched pair (real "
        "FG1 vs synthetic FG5) and showing the matched pair scores higher. Without the "
        "equivalent per-section control, a low per-section recall cannot be separated "
        "from the method's own floor — an unrelated group might score the same. Treat "
        "Part B as descriptive until that control exists.",
        "",
        "**Section-level theme sets are small** (3–5 per side), so one match moves "
        "recall by 20–33 points. Differences between sections of a few points carry "
        "no weight.",
        "",
        "**`participant_count` is evidence-constrained**: distinct non-moderator "
        "speakers with a quote verified as a substring of the section text. A count of "
        "0 means no participant quote survived verification — the theme rests on "
        "moderator turns or unverifiable quotes and should be discounted.",
        "",
        "**Data volume is not matched across sides**, which is itself a finding rather "
        "than a nuisance: see the per-section word counts in Part A.",
        "",
        "---",
        "",
        f"_Auto-generated by `scripts/validate_tier2b_guide_question.py` "
        f"(segmentation: `scripts/tier2b_segmentation.py`)._",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(evaluator_key: str = "gemini25", dry_run: bool = False) -> None:
    ecfg = EVALUATOR_CONFIGS.get(evaluator_key)
    if ecfg is None:
        print(f"Unknown evaluator key '{evaluator_key}'. Choose from: {list(EVALUATOR_CONFIGS)}")
        sys.exit(1)

    print("=" * 72)
    print("  TIER 2b — EMERGENT THEMATIC FIDELITY BY GUIDE QUESTION (FG1 pilot)")
    print(f"  Evaluator: {ecfg.get('model')}"
          + ("   [DRY RUN — segmentation only, no API calls]" if dry_run else ""))
    print("=" * 72)

    guide_source = _SYNTH_RUN_DIR / "session_state_initial.json"
    human = segment_human_by_guide(_HUMAN_FG1, guide_source)
    synthetic = segment_synthetic_by_guide(_SYNTH_RUN_DIR / "transcript.json", guide_source)

    _print_segmentation(human)
    _print_segmentation(synthetic)

    crosscheck = crosscheck_synthetic_against_state_files(synthetic, _SYNTH_RUN_DIR)
    print(f"\n[Cross-check vs state_turn_*.json] {crosscheck['entries_agree']} agree, "
          f"{crosscheck['entries_differ_on_boundary_turn']} differ on boundary turns "
          f"(expected), {crosscheck['entries_in_conflict']} conflicts — "
          f"{'CLEAN' if crosscheck['clean'] else 'CONFLICTS PRESENT'}")
    if not crosscheck["clean"]:
        print("  Boundary signals disagree — segmentation is not trustworthy. Stopping.")
        for c in crosscheck["conflicts"]:
            print(f"    {c}")
        sys.exit(2)

    indices, skipped = comparable_sections(human, synthetic)
    print(f"\n[Scope] {len(indices)} comparable sections: {indices}")
    for k in skipped:
        print(f"  skipped section {k['section_index']} ({k['section_label']}): "
              f"{k['status']} — {k['reason']}")

    if not indices:
        print("\nNo comparable sections. Nothing to extract.")
        sys.exit(1)

    stability_indices = _pick_stability_sections(human, indices)
    n_calls = len(indices) * 3 + len(stability_indices) * 2 * (_STABILITY_EXTRA_RUNS + 3)
    print(f"[Scope] stability re-runs on sections {stability_indices}")
    print(f"[Scope] ≈{n_calls} evaluator API calls")

    if dry_run:
        print("\nDry run — stopping before any API call. No files written.")
        return

    rows, human_results, synth_results = run_sections(human, synthetic, indices, ecfg)
    stability = run_stability_check(
        human, synthetic, stability_indices, human_results, synth_results, ecfg
    )

    model = ecfg.get("model", "?")
    h_json = _write_transcript_json(_HUMAN_LABEL, human, human_results, model)
    s_json = _write_transcript_json(_SYNTH_LABEL, synthetic, synth_results, model)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    pilot_json = _OUT_DIR / f"tier2b_guide_question_pilot_fg1_{evaluator_key}.json"
    pilot_json.write_text(json.dumps({
        "date":       _DATE,
        "evaluator":  model,
        "human_source":     str(human.source_path),
        "synthetic_source": str(synthetic.source_path),
        "data_floor": {"min_participant_turns": MIN_PARTICIPANT_TURNS,
                       "min_words": MIN_WORDS},
        "segmentation_crosscheck": crosscheck,
        "compared_sections": rows,
        "skipped_sections":  skipped,
        "stability_check":   stability,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md_path = _write_md(evaluator_key, ecfg, human, synthetic, rows, skipped,
                        stability, crosscheck)

    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    for r in rows:
        print(f"  s{r['section_index']} {r['section_label'][:38]:<38} "
              f"H={r['human_themes']:>2} S={r['synthetic_themes']:>2} "
              f"matched={r['matched']:>2}  recall={r['recall']:.0%}  "
              f"precision={r['precision']:.0%}")
    if rows:
        print(f"  mean recall={sum(r['recall'] for r in rows)/len(rows):.1%}  "
              f"mean precision={sum(r['precision'] for r in rows)/len(rows):.1%}")
    if stability:
        print(f"  stability (mean pairwise recall): "
              f"{sum(s['mean_pairwise_recall'] for s in stability)/len(stability):.1%}")
    for p in (h_json, s_json, pilot_json, md_path):
        print(f"  wrote {p.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluator", default="gemini25", choices=list(EVALUATOR_CONFIGS),
                        help="Which evaluator config to use (default: gemini25)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Segment and report scope only — makes no API calls "
                             "and writes no files.")
    args = parser.parse_args()
    main(args.evaluator, args.dry_run)
