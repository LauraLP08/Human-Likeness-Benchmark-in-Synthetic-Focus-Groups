"""
Mator et al. (2025) Table 4 — side-by-side comparison table for this corpus.

Pure reporting: reads `mator_comparable/mator_bertscore_by_unit.csv` and
`mator_bertscore_spec.json` (written by `scripts/mator_bertscore_metrics.py`)
and writes

    analysis/production_evaluation/mator_comparable/MATOR_TABLE4_COMPARISON.md
    analysis/production_evaluation/mator_comparable/mator_example_pairs.md

No model, no API, no recomputation.

AGGREGATION follows the convention already fixed for this corpus: the unit of
analysis is the FG pair (n=5). The three replicates of a condition are generator
variability, never 15 independent observations. Two readings are reported side
by side because they answer different questions:

  envelope  does the synthetic condition mean fall inside the [min-max] range of
            the five human groups -- i.e. outside natural between-group human
            variation?
  paired    is each synthetic group higher/lower than ITS OWN human counterpart,
            and in how many of the 5 pairs does the sign hold?

No significance tests. Directional consistency only.

Usage:
    py scripts/mator_comparison_table.py
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mator_bertscore_metrics import MATOR_PUBLISHED  # noqa: E402

_OUT = _REPO_ROOT / "analysis" / "production_evaluation" / "mator_comparable"

CONDITIONS = ["enriched", "demographics-only"]

# (column, Mator row key, label, format). A Mator key of None means the row is a
# companion reading of the row above it, not a separate Mator row.
ROWS = [
    ("completeness", "conversational_completeness",
     "Conversational completeness (guide topics reached / 5)", "pct"),

    ("relevance_bertscore_f1", "relevance_of_response",
     "Relevance of Response — BERTScore F1, raw", "pct"),
    ("relevance_bertscore_f1_rescaled", None,
     "  ... baseline-rescaled", "num"),
    ("relevance_bertscore_f1_length_matched", None,
     "  ... raw, length-matched (both sides truncated to W)", "pct"),
    ("relevance_bertscore_f1_vs_section_opener", None,
     "  ... raw, vs the section-opening question only", "pct"),

    ("between_participant_bertscore_f1", "between_participant_similarity",
     "Response similarity between participants — BERTScore F1, raw", "pct"),
    ("between_participant_bertscore_f1_rescaled", None,
     "  ... baseline-rescaled", "num"),
    ("between_participant_bertscore_f1_length_matched", None,
     "  ... raw, length-matched (both sides truncated to W)", "pct"),

    ("agreement_strict_R2", "agreement",
     "Agreement among participants — cosine, strict adjacency, whole turn [PRIMARY]", "pct"),
    ("agreement_strict_R3", None,
     "  ... strict adjacency, length-matched", "pct"),
    ("agreement_bridged_R2", None,
     "  ... bridged universe (existing consensus layer), whole turn", "pct"),
    ("agreement_bridged_R3", None,
     "  ... bridged universe, length-matched", "pct"),

    ("moderator_word_share", None,
     "Conversational distribution — moderator word share", "pct"),
]

PAIRED_ROWS = [
    "relevance_bertscore_f1",
    "relevance_bertscore_f1_length_matched",
    "between_participant_bertscore_f1",
    "between_participant_bertscore_f1_length_matched",
    "agreement_strict_R2",
    "agreement_strict_R3",
]


def _f(row: dict, key: str):
    v = row.get(key, "")
    if v in ("", None):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt(v, style: str) -> str:
    if v is None:
        return "—"
    return f"{100 * v:.1f}%" if style == "pct" else f"{v:+.3f}"


def _label_of(key: str) -> str:
    for k, _, label, _ in ROWS:
        if k == key:
            return label.strip().lstrip(". ")
    return key


def _style_of(key: str) -> str:
    for k, _, _, style in ROWS:
        if k == key:
            return style
    return "pct"


def load_rows() -> list[dict]:
    """One row per unit, joining the three producers on `unit`.

    Kept as a join rather than one wide producer because the three run at
    completely different costs: completeness is instant structural arithmetic,
    strict agreement is one sentence-transformer pass, BERTScore is a two-hour
    scoring pass. Coupling them would mean re-running the expensive one to fix a
    typo in the cheap one.
    """
    path = _OUT / "mator_bertscore_by_unit.csv"
    if not path.exists():
        raise SystemExit(f"{path} not found — run scripts/mator_bertscore_metrics.py first")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))

    comp_path = _OUT / "mator_completeness_by_unit.csv"
    if not comp_path.exists():
        raise SystemExit(f"{comp_path} not found — run scripts/mator_completeness.py first")
    comp = {r["unit"]: r for r in csv.DictReader(comp_path.open(encoding="utf-8"))}

    missing = [r["unit"] for r in rows if r["unit"] not in comp]
    if missing:
        raise SystemExit(f"units present in the BERTScore table but not the completeness "
                         f"table: {missing}")
    for r in rows:
        c = comp[r["unit"]]
        r["completeness"] = c["completeness"]
        r["completeness_sections_covered"] = c["sections_covered"]
        r["completeness_sections_missing"] = c["sections_missing"]
    return rows


def envelope_table(rows: list[dict]) -> list[str]:
    human = [r for r in rows if r["side"] == "human"]
    out = [
        "| Metric | Human mean [min–max] | Enriched | Demographics-only | "
        "Inside human envelope | Mator AI | Mator Human | n units (H / E / D) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, mator_key, label, style in ROWS:
        hv = [v for v in (_f(r, key) for r in human) if v is not None]
        if not hv:
            continue
        lo, hi = min(hv), max(hv)
        cells, inside, counts = [], [], [len(hv)]
        for c in CONDITIONS:
            cv = [v for v in (_f(r, key) for r in rows if r["condition"] == c)
                  if v is not None]
            m = statistics.mean(cv) if cv else None
            cells.append(_fmt(m, style))
            inside.append(m is not None and lo <= m <= hi)
            counts.append(len(cv))
        flag = "yes" if all(inside) else ("no" if not any(inside) else "partial")
        m_ai = MATOR_PUBLISHED[mator_key]["ai"] if mator_key else ""
        m_hu = MATOR_PUBLISHED[mator_key]["human"] if mator_key else ""
        out.append(
            f"| {label} | {_fmt(statistics.mean(hv), style)} "
            f"[{_fmt(lo, style)}–{_fmt(hi, style)}] | {cells[0]} | {cells[1]} | "
            f"{flag} | {m_ai} | {m_hu} | {counts[0]} / {counts[1]} / {counts[2]} |")
    return out


def paired_table(rows: list[dict], key: str) -> list[str]:
    style = _style_of(key)
    human = {r["fg"]: r for r in rows if r["side"] == "human"}
    by_fg_cond: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        if r["side"] != "synthetic":
            continue
        v = _f(r, key)
        if v is not None:
            by_fg_cond[(r["fg"], r["condition"])].append(v)

    out = [f"\n**{_label_of(key)}** — Δ = synthetic condition mean minus its own "
           f"human pair\n",
           "| FG | human | enriched | demographics-only | Δ enr | Δ demo |",
           "|---|---|---|---|---|---|"]
    signs: dict[str, list[int]] = {c: [] for c in CONDITIONS}
    for fg in sorted(human):
        h = _f(human[fg], key)
        cells = [_fmt(h, style)]
        deltas = []
        for c in CONDITIONS:
            vals = by_fg_cond.get((fg, c), [])
            m = statistics.mean(vals) if vals else None
            cells.append(_fmt(m, style))
            if h is None or m is None:
                deltas.append("—")
            else:
                deltas.append(f"{100 * (m - h):+.1f} pp" if style == "pct"
                              else f"{m - h:+.3f}")
                signs[c].append(1 if m > h else (-1 if m < h else 0))
        out.append("| " + " | ".join([fg] + cells + deltas) + " |")

    dirline = []
    for c in CONDITIONS:
        s = signs[c]
        up = sum(1 for x in s if x > 0)
        down = sum(1 for x in s if x < 0)
        tie = len(s) - up - down
        if not s:
            dirline.append("—")
        elif up >= down:
            dirline.append(f"{up}/{len(s)} higher" + (f" ({tie} tied)" if tie else ""))
        else:
            dirline.append(f"{down}/{len(s)} lower" + (f" ({tie} tied)" if tie else ""))
    out.append(f"| **direction** | | | | **{dirline[0]}** | **{dirline[1]}** |")
    return out


def distribution_block(rows: list[dict]) -> list[str]:
    """Mator's row format: moderator share plus the per-participant share range."""
    out = ["\n### Conversational distribution — Mator's row format\n",
           "| Side | Moderator word share | Participants (word share, min–max across "
           "participants, mean over units) | n participants |",
           "|---|---|---|---|"]
    groups = [("Human (5 FG)", [r for r in rows if r["side"] == "human"])]
    for c in CONDITIONS:
        groups.append((f"Synthetic — {c} (15 runs)",
                       [r for r in rows if r["condition"] == c]))
    for label, sub in groups:
        mods = [v for v in (_f(r, "moderator_word_share") for r in sub) if v is not None]
        mins, maxs, ns = [], [], []
        for r in sub:
            shares = [float(x) for x in (r.get("participant_word_shares") or "").split("|")
                      if x]
            if shares:
                mins.append(min(shares))
                maxs.append(max(shares))
                ns.append(len(shares))
        if not mods or not ns:
            out.append(f"| {label} | — | — | — |")
            continue
        out.append(
            f"| {label} | {100 * statistics.mean(mods):.0f}% | "
            f"{100 * statistics.mean(mins):.0f}–{100 * statistics.mean(maxs):.0f}% each | "
            f"{min(ns)}–{max(ns)} |")
    out.append("")
    out.append(f"*Mator et al.: AI — {MATOR_PUBLISHED['conversational_distribution']['ai']}; "
               f"Human — {MATOR_PUBLISHED['conversational_distribution']['human']}. "
               "Rosters here are 3–5 participants, not their fixed 3, so the "
               "per-participant column is not directly comparable to theirs.*")
    return out


def completeness_block(rows: list[dict]) -> list[str]:
    out = ["\n### Conversational completeness — which topics were reached\n",
           "| Unit | side | topics reached | missing |",
           "|---|---|---|---|"]
    n_flagged = 0
    for r in rows:
        missing = r.get("completeness_sections_missing", "")
        if not missing:
            continue
        n_flagged += 1
        cov = [x for x in (r.get("completeness_sections_covered") or "").split("|") if x]
        out.append(f"| {r['unit']} | {r['side']} | {len(cov)}/5 | {missing} |")
    if n_flagged == 0:
        out.append("| — | — | every unit reached 5/5 | — |")
    out += [
        "",
        "A topic counts as reached when its guide section carries at least one "
        "participant turn. A missing `Question N.` header on the human side makes the "
        "topic **unmeasurable, not proven absent**. Every section-opening moderator turn "
        "in every unit is listed in `mator_completeness_openers.csv` so the section→"
        "question correspondence can be checked by eye; an automatic token-overlap "
        "cross-check was built and removed because it flagged all 35 units and "
        "discriminated nothing (see `scripts/mator_completeness.py`).",
    ]
    return out


def exclusions_block(rows: list[dict], spec: dict) -> list[str]:
    misaligned = [r["unit"] for r in rows
                  if str(r.get("section_labels_misaligned", "")).lower() == "true"]
    excluded = spec["corpus"].get("excluded_from_universe", [])
    out = ["\n### What is not in these numbers\n"]
    out.append(f"- **{len(excluded)} run directories on disk are outside the frozen "
               "corpus** and were excluded by name: "
               + (", ".join(f"`{e['run']}`" for e in excluded) or "none") + ". "
               "The run list comes from `frozen_evaluator_inputs.json` and every input "
               "is SHA-256 verified, so the twin-population arm cannot leak in.")
    if misaligned:
        out.append(
            f"- **{len(misaligned)} run(s) are excluded from the section-indexed metric** "
            "(`Response similarity between participants`) because the moderator asked "
            "guide question 1 while still inside guide section 0, so from that point "
            "every section label names a different guide question than its index — and "
            "in both runs two consecutive labels carry the same question. Affected: "
            + ", ".join(f"`{u}`" for u in misaligned) + ". They remain in the "
            "turn-indexed metric (`Relevance of Response`), which does not use section "
            "labels. Counts per row are in the `n units` column.")
    skips = spec.get("section_floor_skips", [])
    floor_skips = [s for s in skips if s.get("section_index") != ""]
    if floor_skips:
        out.append(f"- **{len(floor_skips)} section×unit cells** fell below the Tier 2b "
                   "data floor (≥3 participant turns, ≥150 words) or held a single "
                   "speaker; each is listed individually in "
                   "`mator_section_floor_skips.csv`.")
    return out


# A turn of this many words or fewer ("Yeah.", "Incompatibility, isn't it?")
# carries almost no lexical content, and BERTScore's greedy matching over one or
# two content tokens is dominated by sentence-structure tokens. The threshold is
# reported rather than tuned, and the sensitivity is computed from the
# already-scored pairs file, so it costs nothing to re-derive.
MINIMAL_TURN_WORDS = 5


def short_turn_sensitivity(rows: list[dict]) -> list[str]:
    """What the two BERTScore rows look like once minimal turns are dropped.

    Re-aggregated exactly as the metric is -- mean over pairs for relevance,
    mean within section then across sections for between-participants -- so the
    two columns are comparable.
    """
    path = _OUT / "mator_bertscore_pairs.csv"
    if not path.exists():
        return []
    side_of = {r["unit"]: (r["side"], r["condition"]) for r in rows}

    keep: dict[tuple, list] = defaultdict(list)
    drop_share: dict[tuple, list] = defaultdict(list)
    per_unit_all: dict[tuple, dict] = defaultdict(lambda: defaultdict(list))
    per_unit_keep: dict[tuple, dict] = defaultdict(lambda: defaultdict(list))

    for r in csv.DictReader(path.open(encoding="utf-8")):
        if r["unit"] not in side_of or not r.get("bertscore_f1"):
            continue
        cond = side_of[r["unit"]][1]
        key = (r["kind"], cond)
        minimal = min(int(r["cand_words"]), int(r["ref_words"])) <= MINIMAL_TURN_WORDS
        drop_share[key].append(1 if minimal else 0)
        sec = r["section_index"]
        per_unit_all[(r["kind"], r["unit"])][sec].append(float(r["bertscore_f1"]))
        if not minimal:
            per_unit_keep[(r["kind"], r["unit"])][sec].append(float(r["bertscore_f1"]))
        keep[key].append(float(r["bertscore_f1"]))

    def unit_value(kind: str, unit: str, store) -> float | None:
        by_sec = store.get((kind, unit))
        if not by_sec:
            return None
        if kind == "between":
            means = [statistics.mean(v) for v in by_sec.values() if v]
            return statistics.mean(means) if means else None
        flat = [x for v in by_sec.values() for x in v]
        return statistics.mean(flat) if flat else None

    out = [f"\n### Sensitivity: minimal turns (≤{MINIMAL_TURN_WORDS} words)\n",
           "Short turns are not distributed evenly between the sides, and they do not "
           "score like ordinary turns, so this is a property of the corpus rather than "
           "a nuisance to be silently trimmed. Both columns are shown; the metric "
           "reported everywhere else is the *all pairs* one.",
           "",
           "| Metric | Side | share of pairs that are minimal | all pairs | excluding "
           "minimal | Δ |",
           "|---|---|---|---|---|---|"]
    groups = [("human", [r for r in rows if r["side"] == "human"])]
    for c in CONDITIONS:
        groups.append((c, [r for r in rows if r["condition"] == c]))
    for kind, label in (("relevance", "Relevance of Response"),
                        ("between", "Between participants")):
        for cond, sub in groups:
            share = drop_share.get((kind, "human" if cond == "human" else cond), [])
            a = [v for v in (unit_value(kind, r["unit"], per_unit_all) for r in sub)
                 if v is not None]
            k = [v for v in (unit_value(kind, r["unit"], per_unit_keep) for r in sub)
                 if v is not None]
            if not a or not k:
                continue
            ma, mk = statistics.mean(a), statistics.mean(k)
            out.append(f"| {label} | {cond} | "
                       f"{100 * statistics.mean(share):.1f}% | {100 * ma:.1f}% | "
                       f"{100 * mk:.1f}% | {100 * (mk - ma):+.1f} pp |")
    return out


def relationship_block(spec: dict) -> list[str]:
    """The repo already contains a Mator replication. Say so, explicitly."""
    return [
        "\n## Relationship to the existing cosine replication\n",
        "`analysis/production_evaluation/consensus_dynamics/MATOR_D4_D5_RESULTS.md` "
        "(3 August 2026, `scripts/consensus_dynamics_metrics.py`) already reports three "
        "Mator rows under Mator's own names, computed with "
        "`paraphrase-multilingual-mpnet-base-v2` **cosine similarity**. This document "
        "does not supersede it wholesale; the two answer different questions and both "
        "should be cited:",
        "",
        "| Row | Existing cosine layer | Here |",
        "|---|---|---|",
        "| Agreement | consecutive participant turns, **bridged** universe, R1/R2/R3 | "
        "same model and R2/R3 rule on the **strict** participant-follows-participant "
        "universe; the bridged figures are carried across unchanged for comparison |",
        "| Relevance | cosine of the turn against the guide's **scripted question** | "
        "**BERTScore** of the turn against the **actual preceding moderator turn** — a "
        "different construct as well as a different method |",
        "| Between participants | cosine over all cross-speaker pairs, pooled flat | "
        "**BERTScore**, averaged within section then across sections, as Mator describe |",
        "",
        "The numbers therefore differ by construction and are not interchangeable. "
        "Cosine and BERTScore are different methods on different scales: only the two "
        "rows Mator explicitly attribute to BERTScore (Zhang et al., 2019) are "
        "comparable to their published 83/82% and 91/83%, and only the versions in this "
        "document are computed with the actual `bert-score` package.",
        "",
        "**A hazard worth recording while the consensus layer is open:** both "
        "`scripts/consensus_dynamics_events.py` and `scripts/consensus_dynamics_metrics.py` "
        "enumerate runs by listing `comparable_transcripts/`, which now holds 7 "
        "`*_twinpop_*` directories that did not exist when those scripts last ran. "
        "`_condition_of()` labels anything without `demoonly` as `enriched`, so "
        "re-running them today would fold the twin-population arm into the enriched "
        "condition mean. The committed outputs (35 units, no twinpop) are clean; the "
        "hazard is prospective. Nothing here modifies those scripts.",
    ]


def example_pairs(spec: dict, n_per_kind: int = 3) -> list[str]:
    """Concrete pairs a human reader can sanity-check by eye.

    Deterministic selection: the lowest, median and highest scoring pair of each
    kind, so the examples bracket the range instead of flattering it.
    """
    path = _OUT / "mator_bertscore_pairs.csv"
    if not path.exists():
        return []
    rows = [r for r in csv.DictReader(path.open(encoding="utf-8")) if r.get("bertscore_f1")]
    base = spec["bertscore"]["baseline_f1_for_rescaling"]

    out = ["# Mator-comparable BERTScore — example pairs for eye-checking", "",
           "Deterministic selection: lowest, median and highest scoring pair of each "
           "kind, so the examples bracket the observed range rather than flatter it.",
           "",
           f"Raw F1 is shown with its baseline-rescaled companion. The expected raw F1 "
           f"for a pair of *unrelated* fluent English sentences at this layer is "
           f"**{base:.4f}** (the package's own rescaling baseline — an expectation over "
           f"a random-pair corpus, not a hard floor: individual unrelated pairs land on "
           f"both sides of it).", ""]
    for kind, title in (("relevance", "Relevance of Response (participant turn vs. "
                                      "preceding moderator turn)"),
                        ("between", "Response similarity between participants "
                                    "(cross-speaker pair inside one guide section)")):
        sub = sorted((r for r in rows if r["kind"] == kind),
                     key=lambda r: float(r["bertscore_f1"]))
        if not sub:
            continue
        picks = [("lowest", sub[0]), ("median", sub[len(sub) // 2]), ("highest", sub[-1])]
        out.append(f"\n## {title}\n")
        for tag, r in picks[:n_per_kind]:
            raw = float(r["bertscore_f1"])
            lm = r.get("bertscore_f1_length_matched")
            out += [
                f"**{tag}** — `{r['unit']}`, guide section {r['section_index']}, "
                f"raw F1 **{raw:.4f}** (rescaled {(raw - base) / (1 - base):+.3f}"
                + (f", length-matched {float(lm):.4f}" if lm else "") + ")",
                "",
                f"- *reference* ({r.get('ref_role', '?')}, {r.get('ref_words', '?')} words): "
                f"{_clip(r['ref'])}",
                f"- *candidate* ({r.get('cand_role', '?')}, {r.get('cand_words', '?')} words): "
                f"{_clip(r['cand'])}",
                "",
            ]
    return out


def _clip(text: str, n: int = 400) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + " […]"


def main() -> None:
    rows = load_rows()
    spec = json.loads((_OUT / "mator_bertscore_spec.json").read_text(encoding="utf-8"))
    bs = spec["bertscore"]
    sc = spec["self_check"]
    lc = spec["length_control"]

    lines = [
        "# Mator et al. (2025) Table 4 — comparable metrics on this corpus",
        "",
        "> **Read `MATOR_REPLICATION_REPORT.md` alongside this file.** It records what was "
        "attempted, how each row was operationalised, what the figures mean, and why this "
        "layer was retained as a documented exploration rather than adopted as evaluation "
        "evidence. This document holds the numbers only.",
        "",
        "**What this is.** Mator et al. (2025) published a five-row table comparing one "
        "AI-generated focus group against one human focus group on automatic measures. "
        "This is an attempt to compute the same five measures over the present corpus "
        "(5 human groups, 30 synthetic sessions) as an external point of comparison.",
        "",
        "*Namespace `_comparable_window`. Evidence class `AUTOMATIC_PROXY_EXPLORATORY`. "
        "Zero API calls. GENERATED FILE — edit `scripts/mator_comparison_table.py`, not "
        "this document.*",
        f"*BERTScore: `bert-score` {bs['package_version']} on transformers "
        f"{bs['transformers_version']} / torch {bs['torch_version']}, hash "
        f"`{bs['hash']}` ({bs['model_type']}, layer {bs['num_layers']}, no idf), CPU, "
        f"fully local.*",
        f"*Agreement rows use `paraphrase-multilingual-mpnet-base-v2` cosine, not "
        f"BERTScore; the bridged variant is read unchanged from "
        f"`scripts/consensus_dynamics_metrics.py`.*",
        f"*Corpus: {spec['corpus']['n_human_units']} human focus groups and "
        f"{spec['corpus']['n_synthetic_units']} synthetic sessions, pinned by SHA-256 "
        f"to `frozen_evaluator_inputs.json`. "
        f"{spec['counts']['relevance_pairs']} relevance pairs and "
        f"{spec['counts']['between_participant_pairs']} between-participant pairs over "
        f"{spec['counts']['distinct_turn_texts_encoded']} distinct turns.*",
        "",
        "## How to read the raw BERTScore column",
        "",
        "**Short version: a raw BERTScore of 83% does not mean 83% of anything.** Two "
        "sentences of fluent English that have nothing to do with each other already score "
        "about 0.83, because they share grammar, function words and register. The number "
        "to read is the *rescaled* one directly underneath each raw row, where 0 means "
        "\"like two unrelated sentences\" and 1 means \"identical\".",
        "",
        f"With this model the *expected* raw F1 for a pair of **unrelated** fluent "
        f"English sentences is **{bs['baseline_f1_for_rescaling']:.4f}** — that is the "
        "package's own rescaling baseline, i.e. a mean over a random-pair corpus, **not "
        "a hard floor**. The self-check demonstrates the point: a deliberately unrelated "
        f"pair scored {sc['unrelated_pair_f1']:.4f} raw, which is *below* the baseline "
        f"({sc['unrelated_pair_f1_rescaled']:+.3f} rescaled). So a raw figure inside the "
        "0.80–0.95 band is **not** by itself evidence of relevance or similarity. The "
        "raw column is kept as the primary because it is the scale Mator's published "
        "82–91% figures live on; the rescaled row underneath each is what should carry "
        "any substantive claim.",
        "",
        "**Do not over-read the comparison with Mator's absolute percentages.** Mator "
        "do not report which BERTScore backbone or layer they used, and the "
        "unrelated-pair expectation varies enormously across ordinary choices:",
        "",
        "| backbone (default layer) | unrelated-pair expectation (F1) |",
        "|---|---|",
    ] + [f"| {k} | {v:.4f} |" for k, v in sorted(sc["baseline_across_backbones"].items(),
                                                 key=lambda kv: -kv[1])] + [
        "",
        "*If* they used the package's default English configuration without rescaling, "
        "their 83%/82% relevance figures would sit essentially at the unrelated-pair "
        "expectation. If they used `bert-base-uncased` — the obvious naive choice for a "
        "paper that says only \"BERTScore\" — 83% would be far above it. Their "
        "configuration is not reported, so this comparison is conditional and is stated "
        "that way wherever it appears.",
        "",
        f"**Length control.** {lc['rule']}. W per FG: "
        + ", ".join(f"{k} {v}" for k, v in sorted(lc["w_by_fg"].items())) + ".",
        "",
        "## Envelope reading",
        "",
    ]
    lines += envelope_table(rows)
    lines += ["", "## Paired reading (n=5 FG pairs)", ""]
    for key in PAIRED_ROWS:
        lines += paired_table(rows, key)
    lines += ["", "No significance tests. n=5 pairs; replicates are generator "
                  "variability, never 15 independent observations. Directional "
                  "consistency only.", ""]
    lines += short_turn_sensitivity(rows)
    lines += completeness_block(rows)
    lines += distribution_block(rows)
    lines += exclusions_block(rows, spec)
    lines += relationship_block(spec)
    lines += [
        "",
        "## Encoder truncation",
        "",
        f"`{bs['model_type']}` truncates at {bs['max_seq_length']} tokens. "
        f"{bs['n_truncated']} of {bs['n_texts']} distinct turns ({bs['pct_truncated']}%) "
        f"reach that limit; the longest turn observed is {bs['max_tokens_observed']} "
        f"tokens, median {bs['median_tokens']}. The caveat the consensus layer raised "
        "for a 128-token encoder applies here at a higher ceiling: where truncation "
        "bites, it bites the long (synthetic) side.",
        "",
    ]
    (_OUT / "MATOR_TABLE4_COMPARISON.md").write_text("\n".join(lines) + "\n",
                                                     encoding="utf-8")

    ex = example_pairs(spec)
    if ex:
        (_OUT / "mator_example_pairs.md").write_text("\n".join(ex) + "\n", encoding="utf-8")

    # stdout may be a pipe with a legacy codepage on Windows; the artefacts are
    # already on disk, so the echo must never be what fails the run.
    try:
        print("\n".join(lines))
    except UnicodeEncodeError:
        print("(table written; console codepage cannot render it)")
    print(f"\nwrote {_OUT / 'MATOR_TABLE4_COMPARISON.md'}")
    if ex:
        print(f"wrote {_OUT / 'mator_example_pairs.md'}")


if __name__ == "__main__":
    main()
