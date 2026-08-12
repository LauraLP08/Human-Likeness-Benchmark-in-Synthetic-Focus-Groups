"""
Agent fidelity - lexical distinctiveness.

    py analysis/figures/render_agent_fidelity_lexical_distinctiveness.py

Reads `agent_fidelity_stylometry.json` and draws four panels. Every panel shows points
and ranges rather than a bar of means, and every point is one document, so the reader can
see how much three runs of the same design differed.

Replicates are NEVER connected: R1, R2 and R3 are three independent realisations of the
same generator, not a sequence, and a line between them would read as a trend.

Offline. No API call.
"""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "analysis/production_evaluation/agent_fidelity"
_PNG = Path(__file__).resolve().parent / "agent_fidelity_lexical_distinctiveness.png"
_CSV = Path(__file__).resolve().parent / "agent_fidelity_lexical_distinctiveness.csv"

CONDS = ("human", "enriched", "demographics-only")
SHORT = {"human": "human", "enriched": "enriched", "demographics-only": "demo-only"}
COL = {"human": "#1d4ed8", "enriched": "#dc2626", "demographics-only": "#047857"}
FGS = ("fg1", "fg2", "fg3", "fg4", "fg5")
W, H = 1900, 1230


def _font(sz, bold=False):
    for p in ([r"C:\Windows\Fonts\arialbd.ttf"] if bold else []) + [
            r"C:\Windows\Fonts\arial.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def _axes(d, x, y, w, h, lo, hi, ticks, title, sub, note=None):
    d.text((x - 60, y - 76), title, fill="#111827", font=_font(22, True))
    d.text((x - 60, y - 46), sub, fill="#475569", font=_font(15))
    if note:
        d.text((x - 60, y - 26), note, fill="#94a3b8", font=_font(13))
    d.rectangle([x, y, x + w, y + h], outline="#cbd5e1")
    for t in ticks:
        yy = y + h - h * (t - lo) / (hi - lo)
        d.line([x, yy, x + w, yy], fill="#f1f5f9")
        lab = f"{t:g}"
        tw = d.textbbox((0, 0), lab, font=_font(14))[2]
        d.text((x - 10 - tw, yy - 8), lab, fill="#64748b", font=_font(14))


def _dots(d, xs, vals, y, h, lo, hi, colour, r=5):
    for x, v in zip(xs, vals):
        yy = y + h - h * (v - lo) / (hi - lo)
        d.ellipse([x - r, yy - r, x + r, yy + r], fill=colour, outline="white", width=2)


def _range_bar(d, x, vals, y, h, lo, hi, colour):
    if len(vals) < 2:
        return
    y1 = y + h - h * (max(vals) - lo) / (hi - lo)
    y2 = y + h - h * (min(vals) - lo) / (hi - lo)
    d.line([x, y1, x, y2], fill=colour, width=3)
    for yy in (y1, y2):
        d.line([x - 7, yy, x + 7, yy], fill=colour, width=3)


def load():
    return json.loads((_SRC / "agent_fidelity_stylometry.json").read_text(
        encoding="utf-8"))


def render(out_png: Path = _PNG, out_csv: Path = _CSV):
    m = load()
    budget = m["budget_words"]
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((70, 24), "Agent fidelity: lexical distinctiveness",
           fill="#111827", font=_font(38, True))
    d.text((72, 74), f"one point = one focus-group session; {budget}-WORD budget per "
f"participant and question (words, not model tokens); character n-gram TF-IDF",
           fill="#64748b", font=_font(17))

    rows = []

    # ------------------------------------------------------ Panel A
    ax, ay, aw, ah = 150, 220, 620, 300
    _axes(d, ax, ay, aw, ah, 0.10, 0.36, [0.10, 0.15, 0.20, 0.25, 0.30, 0.35],
          "A   Between-speaker lexical similarity",
          "median pairwise cosine within a question (higher = participants more alike)",
          "diagnostic only; not evidence of individual identity")
    for i, c in enumerate(CONDS):
        vals = [v for v in m["by_condition"][c][
            "between_speaker_similarity_per_document"].values() if v is not None]
        cx = ax + aw * (i + 0.5) / 3
        xs = [cx - 26 + 52 * k / max(1, len(vals) - 1) for k in range(len(vals))] \
            if len(vals) > 1 else [cx]
        _range_bar(d, cx + 46, vals, ay, ah, 0.10, 0.36, COL[c])
        _dots(d, xs, vals, ay, ah, 0.10, 0.36, COL[c])
        d.text((cx - 30, ay + ah + 12), f"{SHORT[c]}  n={len(vals)}",
               fill="#334155", font=_font(15, True))
        for v in vals:
            rows.append({"panel": "A", "condition": c, "fg": "", "replicate": "",
                         "metric": "between_speaker_median_cosine", "value": v})

    # ------------------------------------------------------ Panel B
    bx, by, bw, bh = 1020, 220, 620, 300
    _axes(d, bx, by, bw, bh, -0.4, 0.6, [-0.4, -0.2, 0.0, 0.2, 0.4, 0.6],
          "B   Speaker identification, chance-corrected",
          "(observed - chance) / (1 - chance) per session; 0 = chance",
          "each session has its own baseline, so no averaged chance line is drawn")
    yz = by + bh - bh * 0.4 / 1.0
    d.line([bx, yz, bx + bw, yz], fill="#334155", width=2)
    d.text((bx + 8, yz - 20), "0 = chance", fill="#334155", font=_font(13))
    for i, c in enumerate(CONDS):
        vals = [v for v in m["by_condition"][c][
            "per_document_chance_corrected"].values() if v is not None]
        cx = bx + bw * (i + 0.5) / 3
        xs = [cx - 26 + 52 * k / max(1, len(vals) - 1) for k in range(len(vals))]             if len(vals) > 1 else [cx]
        _range_bar(d, cx + 46, vals, by, bh, -0.4, 0.6, COL[c])
        _dots(d, xs, vals, by, bh, -0.4, 0.6, COL[c])
        d.text((cx - 34, by + bh + 12), f"{SHORT[c]}  n={len(vals)}",
               fill="#334155", font=_font(15, True))
        for v in vals:
            rows.append({"panel": "B", "condition": c, "fg": "", "replicate": "",
                         "metric": "chance_corrected_accuracy", "value": v})
    d.text((bx + 4, by + bh + 42),
           "one demographics-only session produced no eligible fold and is absent "
           "(n=14, not 15)", fill="#94a3b8", font=_font(13))

    # ------------------------------------------------------ Panel C
    cx0, cy, cw, chh = 150, 700, 620, 300
    _axes(d, cx0, cy, cw, chh, -0.05, 0.05, [-0.04, -0.02, 0.0, 0.02, 0.04],
          "C   Identity-separation gap",
          "same-speaker minus different-speaker similarity, inside a fixed question pair",
          "close to zero is not an equivalence result; internal pairs are not independent")
    y0 = cy + chh - chh * (0.0 + 0.05) / 0.10
    d.line([cx0, y0, cx0 + cw, y0], fill="#334155", width=2)
    for i, c in enumerate(CONDS):
        vals = [v for v in m["by_condition"][c]["identity_gap_per_document"].values()
                if v is not None]
        ccx = cx0 + cw * (i + 0.5) / 3
        xs = [ccx - 26 + 52 * k / max(1, len(vals) - 1) for k in range(len(vals))] \
            if len(vals) > 1 else [ccx]
        _range_bar(d, ccx + 46, vals, cy, chh, -0.05, 0.05, COL[c])
        _dots(d, xs, vals, cy, chh, -0.05, 0.05, COL[c])
        d.text((ccx - 30, cy + chh + 12), f"{SHORT[c]}  n={len(vals)}",
               fill="#334155", font=_font(15, True))
        for v in vals:
            rows.append({"panel": "C", "condition": c, "fg": "", "replicate": "",
                         "metric": "identity_gap_median", "value": v})

    # ------------------------------------------------------ Panel D
    dx, dy, dw, dh = 1020, 700, 620, 300
    _axes(d, dx, dy, dw, dh, -0.4, 0.6, [-0.4, -0.2, 0.0, 0.2, 0.4, 0.6],
          "D   Chance-corrected accuracy by focus group",
          "R1, R2 and R3 shown separately and never joined",
          "(observed - chance) / (1 - chance)")
    yz = dy + dh - dh * (0.0 + 0.4) / 1.0
    d.line([dx, yz, dx + dw, yz], fill="#334155", width=2)
    slot = dw / 5
    for fi, f in enumerate(FGS):
        base = dx + slot * (fi + 0.5)
        for ci, c in enumerate(CONDS):
            recs = m["by_focus_group"][c][f]
            off = (ci - 1) * 30
            vals = [r["chance_corrected_accuracy"] for r in recs
                    if r["chance_corrected_accuracy"] is not None]
            if not vals:
                continue
            xs = ([base + off - 8 + 16 * k / max(1, len(vals) - 1)
                   for k in range(len(vals))] if len(vals) > 1 else [base + off])
            _range_bar(d, base + off, vals, dy, dh, -0.4, 0.6, COL[c])
            _dots(d, xs, vals, dy, dh, -0.4, 0.6, COL[c], r=4)
            for r in recs:
                rows.append({"panel": "D", "condition": c, "fg": f,
                             "replicate": r["replicate"],
                             "metric": "chance_corrected_accuracy",
                             "value": r["chance_corrected_accuracy"]})
        d.text((base - 14, dy + dh + 12), f.upper(), fill="#111827", font=_font(15, True))

    # Study-replicate roll-ups sit beside the panel, at the level of the primary
    # estimand. Each is the mean of that replicate's OWN focus groups.
    ry = dy + 4
    d.text((dx + dw + 18, ry - 22), "study replicate", fill="#334155",
           font=_font(13, True))
    for c in CONDS:
        for r, v in m["hierarchical"][c].items():
            if r == "_across_realisations":
                continue
            lab = "human" if r == "human" else f"R{r}"
            cov = "" if v["coverage"] == "5/5" else f"  {v['coverage']} FGs"
            d.text((dx + dw + 18, ry),
                   f"{SHORT[c][:9]:<9s} {lab:<5s} "
                   f"{v['mean_chance_corrected_accuracy']:+.3f}{cov}",
                   fill=COL[c], font=_font(12))
            ry += 17

    # ------------------------------------------------------ legend + notes
    ly = 1058
    lx = 150
    for c in CONDS:
        d.ellipse([lx, ly - 6, lx + 12, ly + 6], fill=COL[c], outline="white", width=2)
        d.text((lx + 22, ly - 10), SHORT[c], fill="#334155", font=_font(17))
        lx += 200
    d.text((lx + 20, ly - 10), "vertical bar = observed range across sessions "
           "(not a confidence interval)", fill="#64748b", font=_font(15))

    notes = [
        "Unit of analysis: document, then focus group, then study replicate. Trials, "
        "folds, pairs and participants are not independent observations about a "
        "condition.",
        "R1, R2 and R3 are three separate realisations and are never pooled into one "
        "sample. demographics-only R2 rests on 4/5 focus groups; the missing one is "
        "absent, not imputed and not zero.",
        "Panels A and B measure different things: A is how alike the members of a "
        "session are, B is whether one participant stays recognisable across questions.",
        "Human FG5 Q4 was NOT_ASKED_IN_FIELDWORK and is excluded as an absence, not "
        "scored as zero.",
        "Budgets are in WORDS cut by the project lexical tokeniser, not model tokens.",
        "EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC. No human validation of "
        "stylometry exists; nothing here shows that a model represents an agent as an "
        "independent person, and lexical continuity is not psychological continuity.",
    ]
    for i, n in enumerate(notes):
        d.text((150, 1090 + i * 21), "\u2022  " + n, fill="#64748b", font=_font(14))

    for c in CONDS:
        for r, v in m["hierarchical"][c].items():
            if r == "_across_realisations":
                continue
            rows.append({"panel": "D_summary", "condition": c, "fg": "",
                         "replicate": r,
                         "metric": "study_replicate_mean_chance_corrected",
                         "value": v["mean_chance_corrected_accuracy"]})
            rows.append({"panel": "D_summary", "condition": c, "fg": "",
                         "replicate": r, "metric": "coverage_focus_groups",
                         "value": v["coverage"]})

    img.save(out_png)
    with Path(out_csv).open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return Path(out_png), Path(out_csv), rows


if __name__ == "__main__":
    png, csvp, rows = render()
    print("figure:", png.name, " values:", csvp.name, " rows:", len(rows))
    m = load()
    for c in CONDS:
        b = m["by_condition"][c]
        print(f"  {c:18s} acc {b['accuracy']:.3f}  chance {b['chance_baseline']:.3f}  "
              f"corrected {b['chance_corrected_accuracy']:+.3f}")
