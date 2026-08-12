"""
Tier 2b — discrimination control: real FG1 vs DELIBERATELY MISMATCHED synth FG5.

The FG1 pilot (`docs/findings/2026-07-29_tier2b_guide_question_pilot.md`) scored
real FG1 against synth FG1 at 21.3% mean per-section recall, and flagged that the
number is uninterpretable on its own: without a mismatched control there is no
way to tell 21.3% from the method's own floor at section granularity. This script
supplies that control, as the whole-transcript Tier 2 does for its Gate 2
(matched real FG1 vs synth FG1, mismatched real FG1 vs synth FG5).

CONTROL ARMS. `--fg5-run` accepts more than one run. Each is scored as an
INDEPENDENT control arm and reported with its own margin. Arms are never pooled
or averaged into a single mismatched figure — the commissioning instructions
require one documented run per control, and averaging replicates would hide
exactly the run-to-run spread a second arm exists to expose.
`macho_meals_fg5_run01` is the primary arm; anything further is a robustness
point on top of it.

WHAT IS AND IS NOT RE-RUN:
  - Human FG1 themes are NOT re-extracted. They are loaded verbatim from
    `analysis/coding_frame/tier2b_guide_question_human_fg1.json`, the pilot's own
    output, so every arm scores against a byte-identical human set. Re-extracting
    would inject run-to-run variation into the baseline the margin is measured from.
  - Human FG1 IS re-segmented — free, offline, deterministic — for the per-section
    counts and the data-floor check. The script asserts the re-segmentation yields
    the same section set as the stored themes.
  - Only the synthetic FG5 side is extracted fresh.

ADDITIVE. `extract_themes_tier2`, `verify_tier2_themes`, `match_tier2_themes` and
`segment_synthetic_by_guide` are called unmodified.
`validate_tier2b_guide_question.py` is imported for shared helpers and is NOT
modified — it is the artefact that produced the matched-arm numbers this control
is compared against, so it stays byte-identical.

EVALUATOR. Must be the config the pilot used, or matched-vs-mismatched stops
being apples-to-apples. The script reads the evaluator recorded in the pilot's
human-themes JSON and refuses to run against a different one.

Usage:
    py scripts/validate_tier2b_discrimination_control.py --dry-run
    py scripts/validate_tier2b_discrimination_control.py
    py scripts/validate_tier2b_discrimination_control.py --fg5-run macho_meals_fg5_run01 macho_meals_fg5_run03
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
    extract_themes_tier2,
    match_tier2_themes,
)
from tier2b_segmentation import (                 # noqa: E402
    MIN_PARTICIPANT_TURNS,
    MIN_WORDS,
    SegmentationResult,
    comparable_sections,
    crosscheck_synthetic_against_state_files,
    segment_human_by_guide,
    segment_synthetic_by_guide,
)
# Shared helpers from the pilot — imported, never modified.
from validate_tier2b_guide_question import (      # noqa: E402
    _HUMAN_FG1,
    _print_segmentation,
    _theme_to_dict,
    _with_retry,
)

_OUT_DIR  = _REPO_ROOT / "analysis" / "coding_frame"
_DOCS_DIR = _REPO_ROOT / "docs" / "findings"
_SESSION_LOGS = _REPO_ROOT / "output" / "session_logs"

_DATE = "2026-07-29"

# --- The mismatched arm -----------------------------------------------------
# macho_meals_fg5_run02 is archived (system failure during generation) and is not
# one of the three valid replicates. Of the valid runs (run01, run03, run04),
# run01 is the primary control: first valid replicate and the direct naming
# counterpart of macho_meals_fg1_run01, which the matched arm used.
_PRIMARY_FG5_RUN = "macho_meals_fg5_run01"

# Pilot artefacts supplying the human baseline and the matched-arm numbers.
_HUMAN_THEMES_JSON = _OUT_DIR / "tier2b_guide_question_human_fg1.json"
_MATCHED_PILOT_JSON = _OUT_DIR / "tier2b_guide_question_pilot_fg1_gemini25.json"
_MATCHED_ARM_RUN = "macho_meals_fg1_run01"

# Emitted as part of the generated markdown, NOT hand-patched into the .md
# afterwards: _write_md rebuilds the file from scratch on every call, so a manual
# banner would be silently erased the next time this script ran.
_SUPERSEDED_BANNER = [
    "> ## ⚠ Superseded — see final verdict",
    ">",
    "> **This document's own next-step recommendation was resolved by later diagnostics in",
    "> this same chain.** Part D below called for a human-vs-human ceiling to interpret the",
    "> wrong-signed margin found here; that ceiling was run, and the cross-section control",
    "> that followed identified the mechanism behind it.",
    ">",
    "> **Final decision:** Tier 2b's recall/precision is **retired as fidelity evidence**",
    "> (the matcher tracks the guide question, not group identity — confirmed by the",
    "> cross-section control). The per-section theme lists **remain valid as descriptive",
    "> output**: they are stable on re-extraction and quote-verified.",
    ">",
    "> The wrong-signed margin recorded here (−23.3% on the primary control arm) is now",
    "> **explained rather than anomalous**: within a guide section the topic is held",
    "> constant by construction, which removes the only variable the matcher is sensitive",
    "> to. Note this does **not** implicate `match_tier2_themes` in general — the",
    "> cross-section control showed it discriminates topic correctly, so the",
    "> whole-transcript Tier 2 is unaffected.",
    ">",
    "> Full chain and reasoning: `docs/findings/2026-07-29_tier2b_cross_section_control.md`.",
    ">",
    "> _Nothing below has been altered — this document is retained as the record of the",
    "> diagnostic process._",
    "",
]


# ---------------------------------------------------------------------------
# Rehydrating the pilot's human themes
# ---------------------------------------------------------------------------

def load_human_themes(path: Path) -> tuple[dict[int, Tier2Result], str]:
    """
    Rebuild the pilot's verified human FG1 themes as Tier2Result objects.

    `match_tier2_themes` reads only `theme_label` and `theme_definition` (for the
    judge prompt and the embedding cross-check) and returns the theme objects
    themselves in `missed_themes`, so restoring labels, definitions, verified
    quotes and participant_count reproduces the pilot's human arm exactly.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, Tier2Result] = {}
    for section in payload["sections"]:
        if not section.get("extracted"):
            continue
        out[section["section_index"]] = Tier2Result(themes=[
            Tier2Theme(
                theme_label=t["theme_label"],
                theme_definition=t["theme_definition"],
                supporting_quotes=[SupportingQuote(**q) for q in t["verified_quotes"]],
                verified_quotes=[SupportingQuote(**q) for q in t["verified_quotes"]],
                participant_count=t["participant_count"],
            )
            for t in section["themes"]
        ])
    return out, payload["evaluator"]


# ---------------------------------------------------------------------------
# One control arm
# ---------------------------------------------------------------------------

def run_control_arm(
    run_name: str,
    human_seg: SegmentationResult,
    human_themes: dict[int, Tier2Result],
    evaluator_cfg: dict | None,
    dry_run: bool,
) -> dict:
    """Segment one FG5 run, extract its per-section themes, match against the
    reused human FG1 themes. Returns a self-contained arm record."""
    run_dir = _SESSION_LOGS / run_name
    guide_source = run_dir / "session_state_initial.json"
    synth_seg = segment_synthetic_by_guide(run_dir / "transcript.json", guide_source)
    _print_segmentation(synth_seg)

    crosscheck = crosscheck_synthetic_against_state_files(synth_seg, run_dir)
    print(f"  cross-check vs state_turn_*.json: {crosscheck['entries_agree']} agree, "
          f"{crosscheck['entries_differ_on_boundary_turn']} differ on boundary turns "
          f"(expected), {crosscheck['entries_in_conflict']} conflicts — "
          f"{'CLEAN' if crosscheck['clean'] else 'CONFLICTS PRESENT'}")
    if not crosscheck["clean"]:
        raise RuntimeError(
            f"{run_name}: boundary signals disagree — segmentation is not trustworthy."
        )

    indices, skipped = comparable_sections(human_seg, synth_seg)
    # Only score sections the pilot actually extracted human themes for.
    indices = [i for i in indices if i in human_themes]
    print(f"  comparable sections: {indices}")
    for k in skipped:
        print(f"    skipped section {k['section_index']} ({k['section_label']}): "
              f"{k['status']} — {k['reason']}")

    arm: dict = {
        "run": run_name,
        "source": str(synth_seg.source_path),
        "is_primary": run_name == _PRIMARY_FG5_RUN,
        "segmentation_crosscheck": crosscheck,
        "segmentation_warnings": synth_seg.warnings,
        "section_counts": [synth_seg.sections[i].counts()
                           for i in synth_seg.section_indices()],
        "compared_sections": [],
        "skipped_sections": skipped,
        "synthetic_sections": [],
    }
    if dry_run:
        arm["compared_section_indices"] = indices
        arm["estimated_api_calls"] = len(indices) * 2
        return arm

    label = run_name.replace("macho_meals_", "")
    for idx in indices:
        h_seg = human_seg.sections[idx]
        s_seg = synth_seg.sections[idx]
        h_res = human_themes[idx]
        slug = h_seg.section_label.lower().replace(" ", "_")[:40]

        print(f"\n  [Section {idx}] {h_seg.section_label}")
        print(f"    human FG1 (reused from pilot): {len(h_res.themes)} themes")
        print(f"    {label} ({s_seg.participant_turns} p-turns, "
              f"{s_seg.total_words} words) ...", end=" ", flush=True)
        s_res = _with_retry(
            extract_themes_tier2,
            s_seg.blind_text,
            run_label=f"tier2b_control__synth_{label}__section_{idx}_{slug}",
            evaluator_cfg=evaluator_cfg,
        )
        print(f"{len(s_res.themes)} themes")

        print(f"    matching within section {idx} ...", end=" ", flush=True)
        scores = _with_retry(
            match_tier2_themes,
            h_res, s_res,
            run_label=f"tier2b_control_match_{label}__section_{idx}_{slug}",
            evaluator_cfg=evaluator_cfg,
        )
        print(f"{len(scores.matched_pairs)} matched  recall={scores.recall:.1%}  "
              f"precision={scores.precision:.1%}")

        arm["compared_sections"].append({
            "section_index":    idx,
            "section_label":    h_seg.section_label,
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
                {"theme_label": t.theme_label, "participant_count": t.participant_count}
                for t in scores.emergent_themes
            ],
            "missed_themes": [
                {"theme_label": t.theme_label, "participant_count": t.participant_count}
                for t in scores.missed_themes
            ],
            "disagreements": [
                {**d,
                 "human_theme":     h_res.themes[d["ri"]].theme_label,
                 "synthetic_theme": s_res.themes[d["si"]].theme_label}
                for d in scores.disagreements
            ],
            "disagreement_count": len(scores.disagreements),
        })
        arm["synthetic_sections"].append({
            **s_seg.counts(),
            "themes": [_theme_to_dict(t) for t in s_res.themes],
        })

    rows = arm["compared_sections"]
    arm["mean_recall"] = (round(sum(r["recall"] for r in rows) / len(rows), 4)
                          if rows else None)
    arm["mean_precision"] = (round(sum(r["precision"] for r in rows) / len(rows), 4)
                             if rows else None)
    arm["total_matched_pairs"] = sum(r["matched"] for r in rows)
    return arm


def build_comparison(matched_rows: list[dict], arms: list[dict]) -> dict:
    """
    Side-by-side matched arm vs EACH control arm, per section and aggregate.

    Deliberately no pooled mismatched figure: each arm keeps its own margin so
    run-to-run spread across FG5 replicates stays visible.
    """
    matched_by = {r["section_index"]: r for r in matched_rows}
    section_indices = sorted(matched_by)

    per_section = []
    for idx in section_indices:
        m = matched_by[idx]
        row = {
            "section_index": idx,
            "section_label": m["section_label"],
            "matched_recall":    m["recall"],
            "matched_precision": m["precision"],
            "matched_matched":   m["matched"],
            "arms": {},
        }
        for arm in arms:
            c = next((r for r in arm["compared_sections"] if r["section_index"] == idx), None)
            row["arms"][arm["run"]] = None if c is None else {
                "recall":    c["recall"],
                "precision": c["precision"],
                "matched":   c["matched"],
                "recall_margin": round(m["recall"] - c["recall"], 4),
            }
        per_section.append(row)

    mean_matched_recall = round(
        sum(matched_by[i]["recall"] for i in section_indices) / len(section_indices), 4)
    mean_matched_precision = round(
        sum(matched_by[i]["precision"] for i in section_indices) / len(section_indices), 4)

    return {
        "matched_arm": {
            "run": _MATCHED_ARM_RUN,
            "mean_recall": mean_matched_recall,
            "mean_precision": mean_matched_precision,
            "total_matched_pairs": sum(matched_by[i]["matched"] for i in section_indices),
        },
        "control_arms": [
            {
                "run": arm["run"],
                "is_primary": arm["is_primary"],
                "mean_recall": arm["mean_recall"],
                "mean_precision": arm["mean_precision"],
                "total_matched_pairs": arm["total_matched_pairs"],
                "mean_recall_margin": round(mean_matched_recall - arm["mean_recall"], 4),
            }
            for arm in arms
        ],
        "per_section": per_section,
        "arms_not_pooled": (
            "Each control arm keeps its own margin. No averaged mismatched figure is "
            "reported: the commissioning instructions require one documented FG5 run "
            "per control, and pooling replicates would hide the run-to-run spread."
        ),
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _write_md(
    evaluator_cfg: dict | None,
    human_seg: SegmentationResult,
    arms: list[dict],
    comparison: dict,
) -> Path:
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = _DOCS_DIR / f"{_DATE}_tier2b_discrimination_control.md"

    ecfg = evaluator_cfg or {}
    model = ecfg.get("model", "gemini-2.5-flash")
    params = (f"thinking_level={ecfg['thinking_level']}" if ecfg.get("thinking_level")
              else f"temperature={ecfg.get('temperature', 0.0)}")
    arm_runs = [a["run"] for a in arms]

    lines: list[str] = [
        "# Tier 2b — Discrimination Control (real FG1 vs mismatched synth FG5)",
        "",
        *_SUPERSEDED_BANNER,
        f"**Date:** {_DATE}  ",
        f"**Evaluator:** `{model}` ({params}) — identical to the matched pilot  ",
        f"**Human arm:** real FG1 themes reused verbatim from "
        f"`analysis/coding_frame/{_HUMAN_THEMES_JSON.name}` (not re-extracted)  ",
        f"**Matched arm (from pilot):** `{_MATCHED_ARM_RUN}`  ",
        f"**Control arms:** {', '.join(f'`{r}`' for r in arm_runs)} "
        f"(primary: `{_PRIMARY_FG5_RUN}`)  ",
        f"**Data floor:** MIN_PARTICIPANT_TURNS={MIN_PARTICIPANT_TURNS}, MIN_WORDS={MIN_WORDS}",
        "",
        "> Purpose: establish Tier 2b's own floor. The matched pilot scored 21.3% mean",
        "> per-section recall; on its own that could be genuine partial fidelity or it",
        "> could be what the method returns for *any* two focus groups on the same guide.",
        "> Scoring deliberately unrelated groups separates the two.",
        "",
        "> **Control arms are not pooled.** Each FG5 run is an independent control with",
        "> its own margin. No averaged mismatched figure is reported — pooling replicates",
        "> would hide the run-to-run spread a second arm exists to expose.",
        "",
        "---",
        "",
        "## Part A — Segmentation of the control arms",
        "",
    ]

    for arm in arms:
        cc = arm["segmentation_crosscheck"]
        tag = " (primary)" if arm["is_primary"] else ""
        lines += [
            f"### `{arm['run']}`{tag}",
            "",
            f"Cross-checked against `state_turn_*.json`: **{cc['entries_agree']} entries "
            f"agree**, {cc['entries_differ_on_boundary_turn']} differ only on a boundary "
            f"turn (expected), **{cc['entries_in_conflict']} genuine conflicts**.",
            "",
            "| Idx | Section | p-turns | words | speakers | Floor |",
            "|----:|---------|--------:|------:|---------:|-------|",
        ]
        for c in arm["section_counts"]:
            lines.append(
                f"| {c['section_index']} | {c['section_label']} | "
                f"{c['participant_turns']} | {c['total_words']} | "
                f"{c['distinct_participants']} | "
                f"{'ok' if c['meets_floor'] else '**BELOW**'} |"
            )
        if arm["skipped_sections"]:
            lines += ["", "Skipped (reported, not silently dropped):", ""]
            for k in arm["skipped_sections"]:
                lines.append(f"- Section {k['section_index']} — {k['section_label']}: "
                             f"`{k['status']}` — {k['reason']}")
        lines.append("")

    lines += [
        "Human FG1 per-section volume (unchanged from the pilot): "
        + ", ".join(
            f"s{i} {human_seg.sections[i].participant_turns}t/"
            f"{human_seg.sections[i].total_words}w"
            for i in human_seg.section_indices()
        ) + ".",
        "",
        "---",
        "",
        "## Part B — Matched vs mismatched, section by section",
        "",
        f"Matched arm = real FG1 vs synth FG1 (`{_MATCHED_ARM_RUN}`), from the pilot.  ",
        "Control arms = the same real FG1 themes vs synth FG5.  ",
        "Same evaluator, same human baseline, same matcher — only the synthetic group differs.",
        "",
    ]

    header = "| Idx | Section | Matched recall |"
    divider = "|----:|---------|---------------:|"
    for run in arm_runs:
        header += f" {run.replace('macho_meals_fg5_', 'FG5 ')} recall | margin |"
        divider += "-----:|-------:|"
    lines += [header, divider]

    for p in comparison["per_section"]:
        row = f"| {p['section_index']} | {p['section_label']} | {p['matched_recall']:.1%} |"
        for run in arm_runs:
            a = p["arms"].get(run)
            if a is None:
                row += " — | — |"
            else:
                row += f" {a['recall']:.1%} | {a['recall_margin']:+.1%} |"
        lines.append(row)

    mean_row = f"| **Mean** | | **{comparison['matched_arm']['mean_recall']:.1%}** |"
    for arm in comparison["control_arms"]:
        mean_row += (f" **{arm['mean_recall']:.1%}** | "
                     f"**{arm['mean_recall_margin']:+.1%}** |")
    lines += ["", mean_row, ""]

    lines += [
        "Theme pairs matched across all five sections:",
        "",
        f"- matched arm (`{_MATCHED_ARM_RUN}`): "
        f"**{comparison['matched_arm']['total_matched_pairs']}**",
    ]
    for arm in comparison["control_arms"]:
        lines.append(f"- control arm (`{arm['run']}`): **{arm['total_matched_pairs']}**")

    lines += [
        "",
        "Precision, for completeness: "
        f"matched {comparison['matched_arm']['mean_precision']:.1%}; "
        + "; ".join(f"`{a['run']}` {a['mean_precision']:.1%}"
                    for a in comparison["control_arms"]) + ".",
        "",
        "> No pass/fail threshold is applied. At n=5 sections with 3–5 themes per side,",
        "> a single theme pairing moves a section's recall by 20–33 points, so the margin",
        "> is interpreted, not tested against a fixed cut.",
        "",
        "---",
        "",
        "## Part C — Themes extracted from the control arms",
        "",
    ]
    for arm in arms:
        lines += [f"### `{arm['run']}`", ""]
        for r in arm["compared_sections"]:
            lines.append(f"**Section {r['section_index']} — {r['section_label']}** "
                         f"({r['matched']} matched of {r['human_themes']} human / "
                         f"{r['synthetic_themes']} synthetic)")
            lines.append("")
            for p in r["matched_pairs"]:
                lines.append(f"- matched: _{p['human']}_ ↔ _{p['synthetic']}_")
            for e in r["emergent_themes"]:
                flag = " ⚑ single-voice" if e["participant_count"] <= 1 else ""
                lines.append(f"- FG5-only: {e['theme_label']} "
                             f"(participants={e['participant_count']}){flag}")
            lines.append("")

    lines += [
        "---",
        "",
        "## Part D — Reading the margin",
        "",
        "The comparison is tightly controlled: the human theme set is byte-identical",
        "across all arms (reused, not re-extracted), the evaluator config is the same,",
        "and the matcher is unmodified. The only thing that varies is which synthetic",
        "group is scored.",
        "",
        "Limits that still apply:",
        "",
        "- **All groups follow the same discussion guide**, so a mismatched pair is not",
        "  an unrelated-topic control — it is a same-topic, different-people control.",
        "  That is the right test for this question, but it makes a large margin",
        "  inherently unlikely: both sides are answering the same question.",
        "- **The matched arm is n=1 synthetic run**, so its 21.3% carries its own",
        "  run-to-run uncertainty, which the pilot's stability check bounded (96.4% mean",
        "  pairwise recall on re-extraction) but did not remove.",
        f"- **{len(arms)} control arm(s)** — enough to see whether the margin survives a",
        "  change of FG5 replicate, not enough to put a confidence interval on it.",
        "",
        "---",
        "",
        f"_Auto-generated by `scripts/validate_tier2b_discrimination_control.py` "
        f"(segmentation: `scripts/tier2b_segmentation.py`; matched-arm figures from "
        f"`{_MATCHED_PILOT_JSON.name}`)._",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(evaluator_key: str, fg5_runs: list[str], dry_run: bool) -> None:
    ecfg = EVALUATOR_CONFIGS.get(evaluator_key)
    if ecfg is None:
        print(f"Unknown evaluator key '{evaluator_key}'. Choose from: {list(EVALUATOR_CONFIGS)}")
        sys.exit(1)

    print("=" * 72)
    print("  TIER 2b — DISCRIMINATION CONTROL (real FG1 vs mismatched synth FG5)")
    print(f"  Evaluator: {ecfg.get('model')}"
          + ("   [DRY RUN — segmentation only, no API calls]" if dry_run else ""))
    print(f"  Control arms: {', '.join(fg5_runs)}")
    print("=" * 72)

    for run in fg5_runs:
        if not (_SESSION_LOGS / run / "transcript.json").exists():
            print(f"\nNo transcript.json for run '{run}'. Stopping.")
            sys.exit(1)

    human_themes, pilot_evaluator = load_human_themes(_HUMAN_THEMES_JSON)
    if pilot_evaluator != ecfg.get("model"):
        print(f"\nEvaluator mismatch: the pilot's human themes were extracted with "
              f"'{pilot_evaluator}' but this run requests '{ecfg.get('model')}'. The "
              f"matched-vs-mismatched comparison would not be apples-to-apples. Stopping.")
        sys.exit(1)
    print(f"\n[Human arm] {sum(len(r.themes) for r in human_themes.values())} themes "
          f"across sections {sorted(human_themes)} — reused from the pilot, "
          f"evaluator '{pilot_evaluator}' confirmed identical.")

    # Human FG1 is re-segmented (offline, free) for counts and the floor check.
    guide_source = _SESSION_LOGS / fg5_runs[0] / "session_state_initial.json"
    human_seg = segment_human_by_guide(_HUMAN_FG1, guide_source)
    if set(human_seg.section_indices()) != set(human_themes):
        print(f"\nSection-set mismatch: re-segmenting human FG1 yields "
              f"{human_seg.section_indices()} but the stored themes cover "
              f"{sorted(human_themes)}. Stopping rather than aligning them by guess.")
        sys.exit(2)
    _print_segmentation(human_seg)

    arms = [run_control_arm(run, human_seg, human_themes, ecfg, dry_run)
            for run in fg5_runs]

    if dry_run:
        total = sum(a["estimated_api_calls"] for a in arms)
        print(f"\n[Scope] ≈{total} evaluator API calls across {len(arms)} control arm(s) "
              f"(FG5 extraction + matching only; human side reused)")
        print("\nDry run — stopping before any API call. No files written.")
        return

    matched_pilot = json.loads(_MATCHED_PILOT_JSON.read_text(encoding="utf-8"))
    comparison = build_comparison(matched_pilot["compared_sections"], arms)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = _OUT_DIR / "tier2b_discrimination_control_fg1_vs_fg5.json"
    out_json.write_text(json.dumps({
        "date":      _DATE,
        "evaluator": ecfg.get("model"),
        "evaluator_config": ecfg,
        "human_arm": {
            "source": str(_HUMAN_THEMES_JSON),
            "reused_not_reextracted": True,
            "evaluator_confirmed": pilot_evaluator,
        },
        "matched_arm_source": str(_MATCHED_PILOT_JSON),
        "primary_control_run": _PRIMARY_FG5_RUN,
        "control_run_selection_note": (
            "macho_meals_fg5_run02 archived (generation failure, not a valid replicate). "
            "Valid runs: run01, run03, run04. run01 is the primary control — first valid "
            "replicate and naming counterpart of macho_meals_fg1_run01. Any additional "
            "arm is an independent robustness point and is never pooled with run01."
        ),
        "data_floor": {"min_participant_turns": MIN_PARTICIPANT_TURNS,
                       "min_words": MIN_WORDS},
        "control_arms": arms,
        "comparison_vs_matched_pilot": comparison,
    }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md_path = _write_md(ecfg, human_seg, arms, comparison)

    print("\n" + "=" * 72)
    print("  SUMMARY — matched vs mismatched (arms kept separate)")
    print("=" * 72)
    for p in comparison["per_section"]:
        line = (f"  s{p['section_index']} {p['section_label'][:34]:<34} "
                f"matched={p['matched_recall']:>5.0%}")
        for arm in comparison["control_arms"]:
            a = p["arms"].get(arm["run"])
            short = arm["run"].replace("macho_meals_fg5_", "")
            line += (f"   {short}={a['recall']:>4.0%} (margin {a['recall_margin']:+.0%})"
                     if a else f"   {short}=  —")
        print(line)
    m = comparison["matched_arm"]
    print(f"\n  MEAN matched recall = {m['mean_recall']:.1%}  "
          f"({m['total_matched_pairs']} theme pairs)")
    for arm in comparison["control_arms"]:
        tag = " [primary]" if arm["is_primary"] else ""
        print(f"  MEAN {arm['run']}{tag}: recall = {arm['mean_recall']:.1%}  "
              f"margin = {arm['mean_recall_margin']:+.1%}  "
              f"({arm['total_matched_pairs']} theme pairs)")
    for p in (out_json, md_path):
        print(f"  wrote {p.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluator", default="gemini25", choices=list(EVALUATOR_CONFIGS),
                        help="Must match the evaluator the pilot used (default: gemini25)")
    parser.add_argument("--fg5-run", nargs="+", default=[_PRIMARY_FG5_RUN],
                        metavar="RUN",
                        help=f"FG5 run(s) to score as independent control arms "
                             f"(default: {_PRIMARY_FG5_RUN}). Arms are never pooled.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Segment and report scope only — makes no API calls "
                             "and writes no files.")
    args = parser.parse_args()
    main(args.evaluator, args.fg5_run, args.dry_run)
