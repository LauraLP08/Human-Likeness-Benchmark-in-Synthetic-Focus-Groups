"""
Agent fidelity - speaker attribution against each condition's own chance baseline.

    py analysis/figures/render_agent_fidelity_attribution_lift.py

Reads `agent_fidelity_stylometry.json` and draws one panel: for each condition, the
accuracy expected by chance and the accuracy actually observed when a 50-word fragment
is attributed to its speaker, leaving one question out at a time.

WHY THE GAP AND NOT THE ACCURACY. The eligible participant set differs by condition, so
the chance baseline differs too (a human focus group has more speakers than a synthetic
one). Reading 0.468 against 0.325 compares two numbers drawn on different scales. What is
comparable is the distance each condition travels from its own baseline, so that distance
is the mark: the connector IS the finding.

Small hollow markers are individual sessions. They are not connected and are not pooled -
the condition figure is a mean over documents, and the spread around it is wide enough
that it must be visible rather than described.

Offline. No API call.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "analysis/production_evaluation/agent_fidelity"
_PNG = Path(__file__).resolve().parent / "agent_fidelity_attribution_lift.png"
_CSV = Path(__file__).resolve().parent / "agent_fidelity_attribution_lift.csv"

CONDS = ("human", "enriched", "demographics-only")
SHORT = {"human": "human", "enriched": "enriched", "demographics-only": "demo-only"}
COL = {"human": "#1d4ed8", "enriched": "#dc2626", "demographics-only": "#047857"}
W, H = 1900, 940

INK, SUB, MUTED, HINT = "#111827", "#334155", "#64748b", "#94a3b8"
AXIS, GRID, BG = "#cbd5e1", "#f1f5f9", "white"

X_LO, X_HI = 0.0, 0.75
TICKS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)


def _font(sz, bold=False):
    for p in ([r"C:\Windows\Fonts\arialbd.ttf"] if bold else []) + [
            r"C:\Windows\Fonts\arial.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def _w(d, text, face):
    b = d.textbbox((0, 0), text, font=face)
    return b[2] - b[0]


def _right(d, xy, text, face, fill):
    d.text((xy[0] - _w(d, text, face), xy[1]), text, fill=fill, font=face)


def _centred(d, xy, text, face, fill):
    d.text((xy[0] - _w(d, text, face) / 2, xy[1]), text, fill=fill, font=face)


def load():
    return json.loads((_SRC / "agent_fidelity_stylometry.json").read_text(
        encoding="utf-8"))


def render(out_png: Path = _PNG, out_csv: Path = _CSV):
    m = load()
    budget = m["budget_words"]
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.text((70, 24), "Agent fidelity: can a fragment be traced back to its speaker?",
           fill=INK, font=_font(38, True))
    d.text((72, 76), f"leave-one-question-out attribution of {budget}-word fragments "
           f"(words, not model tokens); character n-gram TF-IDF; each condition read "
           f"against its OWN chance baseline",
           fill=MUTED, font=_font(17))

    # ------------------------------------------------------------------ legend
    ly, lx = 132, 72
    d.ellipse([lx, ly - 9, lx + 18, ly + 9], fill=BG, outline=SUB, width=4)
    d.text((lx + 28, ly - 11), "expected by chance", fill=SUB, font=_font(16))
    lx += 260
    d.ellipse([lx, ly - 9, lx + 18, ly + 9], fill=SUB, outline=BG, width=3)
    d.text((lx + 28, ly - 11), "observed", fill=SUB, font=_font(16))
    lx += 190
    d.ellipse([lx + 3, ly - 6, lx + 15, ly + 6], fill=BG, outline=HINT, width=2)
    d.text((lx + 28, ly - 11), "one session (not pooled, not connected)",
           fill=SUB, font=_font(16))

    # -------------------------------------------------------------------- axes
    px, py, pw, ph = 300, 214, 1140, 400
    d.rectangle([px, py, px + pw, py + ph], outline=AXIS)
    for t in TICKS:
        tx = px + pw * (t - X_LO) / (X_HI - X_LO)
        d.line([tx, py, tx, py + ph], fill=GRID)
        _centred(d, (tx, py + ph + 12), f"{t:.1f}", _font(15), MUTED)
    _centred(d, (px + pw / 2, py + ph + 44),
             "proportion of fragments attributed to the right speaker",
             _font(16), MUTED)

    _right(d, (px + pw + 214, py - 34), "observed ÷ chance", _font(14, True), SUB)

    rows = []
    for i, c in enumerate(CONDS):
        b = m["by_condition"][c]
        chance, obs = b["chance_baseline"], b["accuracy"]
        docs = [v for v in b["per_document_accuracy"].values() if v is not None]
        # the session strip sits tight under its own connector, so a row reads as one
        # object and never lends its points to the row below
        cy = py + ph * (i + 0.5) / 3
        line_y, dot_y = cy - 26, cy + 6
        cx = px + pw * (chance - X_LO) / (X_HI - X_LO)
        ox = px + pw * (obs - X_LO) / (X_HI - X_LO)

        # the connector is the finding
        d.line([cx, line_y, ox, line_y], fill=COL[c], width=10)
        d.ellipse([cx - 13, line_y - 13, cx + 13, line_y + 13], fill=BG,
                  outline=COL[c], width=5)
        d.ellipse([ox - 14, line_y - 14, ox + 14, line_y + 14], fill=COL[c],
                  outline=BG, width=4)

        for v in docs:
            vx = px + pw * (v - X_LO) / (X_HI - X_LO)
            d.ellipse([vx - 6, dot_y - 6, vx + 6, dot_y + 6], fill=BG,
                      outline=COL[c], width=2)

        gain = (obs - chance) * 100
        _centred(d, ((cx + ox) / 2, line_y - 44), f"+{gain:.1f} pp",
                 _font(19, True), INK)

        _right(d, (px - 26, cy - 42), SHORT[c], _font(20, True), INK)
        _right(d, (px - 26, cy - 14), f"n = {len(docs)} sessions", _font(14), MUTED)
        _right(d, (px - 26, cy + 6), f"{b['n_speakers']} speakers", _font(14), MUTED)

        ratio = obs / chance
        _right(d, (px + pw + 214, line_y - 12), f"{ratio:.2f}\u00d7", _font(21, True),
               COL[c])

        rows.append({"condition": c, "metric": "chance_baseline", "document": "",
                     "value": round(chance, 4)})
        rows.append({"condition": c, "metric": "observed_accuracy", "document": "",
                     "value": round(obs, 4)})
        rows.append({"condition": c, "metric": "gain_over_chance_pp", "document": "",
                     "value": round(gain, 1)})
        rows.append({"condition": c, "metric": "ratio_to_chance", "document": "",
                     "value": round(ratio, 3)})
        for doc, v in b["per_document_accuracy"].items():
            if v is not None:
                rows.append({"condition": c, "metric": "per_document_accuracy",
                             "document": doc, "value": round(v, 4)})

    # ------------------------------------------------------------------- notes
    notes = [
        "Chance differs by condition because the eligible participant set varies by "
        "fold: each baseline is the mean of the per-fold 1/n_participants. Raw "
        "accuracies are therefore NOT comparable across conditions - the distance from "
        "a condition's own baseline is.",
        "Human fragments carry roughly twice the attributable signal of chance; "
        "enriched profiles are barely separable from it. Enrichment did not buy a more "
        "recognisable voice.",
        "Small hollow markers are individual sessions and are never pooled or joined. "
        "The spread is wide in both synthetic conditions, so the condition figure is a "
        "mean over documents, not a stable per-session property.",
        "One demographics-only session produced no eligible fold and is absent (n=14, "
        "not 15). It is missing, not imputed and not scored as zero.",
        "One deterministic centred window per participant x question; offsets are never "
        "repeated to manufacture observations.",
        "EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC. No human validation of "
        "stylometry exists. Lexical continuity is not psychological continuity, and "
        "nothing here shows that a model represents an agent as an independent person.",
    ]
    for i, n in enumerate(notes):
        d.text((72, 712 + i * 34), "\u2022  " + n, fill=MUTED, font=_font(15))

    img.save(out_png)
    with Path(out_csv).open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["condition", "metric", "document", "value"])
        w.writeheader()
        w.writerows(rows)
    return Path(out_png), Path(out_csv), rows


if __name__ == "__main__":
    png, csvp, rows = render()
    print("figure:", png.name, " values:", csvp.name, " rows:", len(rows))
    m = load()
    for c in CONDS:
        b = m["by_condition"][c]
        print(f"  {c:18s} chance {b['chance_baseline']:.3f}  observed "
              f"{b['accuracy']:.3f}  gain {(b['accuracy'] - b['chance_baseline']) * 100:+.1f} pp"
              f"  ratio {b['accuracy'] / b['chance_baseline']:.2f}x")
