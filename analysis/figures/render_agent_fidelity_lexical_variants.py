"""Render two thesis-ready variants of the exploratory lexical-fidelity result.

Run with the bundled workspace Python. Source: the frozen 50-word stylometric
analysis. No API calls are made.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "analysis/production_evaluation/agent_fidelity/agent_fidelity_stylometry.json"
OUT = Path(__file__).resolve().parent
W, H = 1800, 940

COLORS = {
    "human": "#52525B",
    "enriched": "#176B87",
    "demographics-only": "#D27D2D",
}
LABELS = {
    "human": "Human",
    "enriched": "Enriched",
    "demographics-only": "Demographics-only",
}
ORDER = ("human", "enriched", "demographics-only")


def font(size: int, bold: bool = False):
    paths = ([r"C:\Windows\Fonts\arialbd.ttf"] if bold else []) + [
        r"C:\Windows\Fonts\arial.ttf"
    ]
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_data() -> dict:
    return json.loads(SRC.read_text(encoding="utf-8"))


def text_center(draw, xy, value, fnt, fill):
    box = draw.textbbox((0, 0), value, font=fnt)
    draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1]), value, font=fnt, fill=fill)


def text_right(draw, xy, value, fnt, fill):
    box = draw.textbbox((0, 0), value, font=fnt)
    draw.text((xy[0] - (box[2] - box[0]), xy[1]), value, font=fnt, fill=fill)


def render_variant_a(data: dict) -> Path:
    """Observed speaker-identification accuracy versus fold-specific chance."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((95, 55), "Recognising individual voices across questions",
           font=font(42, True), fill="#18181B")
    d.text((97, 118),
           "50-word excerpts; coloured circle = observed accuracy; hollow square = chance",
           font=font(24), fill="#71717A")

    left, right, top, bottom = 470, 1660, 235, 700
    lo, hi = 20, 52
    for tick in range(20, 51, 5):
        x = left + (tick - lo) / (hi - lo) * (right - left)
        d.line((x, top, x, bottom), fill="#E4E4E7", width=2)
        text_center(d, (x, bottom + 20), f"{tick}%", font(22), "#52525B")

    rows_y = [300, 465, 630]
    for y, condition in zip(rows_y, ORDER):
        row = data["by_condition"][condition]
        chance = 100 * row["chance_baseline"]
        observed = 100 * row["accuracy"]
        xc = left + (chance - lo) / (hi - lo) * (right - left)
        xo = left + (observed - lo) / (hi - lo) * (right - left)
        text_right(d, (left - 45, y - 18), LABELS[condition], font(28, True), "#27272A")
        d.line((xc, y, xo, y), fill="#A1A1AA", width=7)
        d.rectangle((xc - 12, y - 12, xc + 12, y + 12), fill="white",
                    outline="#71717A", width=4)
        d.ellipse((xo - 17, y - 17, xo + 17, y + 17), fill=COLORS[condition],
                  outline="white", width=3)
        text_center(d, (xc, y - 55), f"{chance:.1f}%", font(23), "#71717A")
        text_center(d, (xo, y + 28), f"{observed:.1f}%", font(23, True), COLORS[condition])

    text_center(d, ((left + right) / 2, 775), "Correctly attributed excerpts",
                font(25), "#3F3F46")
    d.text((97, 865),
           "Exploratory, trial-weighted diagnostic; chance varies with the number of eligible speakers.",
           font=font(20), fill="#71717A")
    path = OUT / "agent_fidelity_lexical_variant_a_voice_recognition.png"
    img.save(path, dpi=(300, 300))
    return path


def render_variant_b(data: dict) -> Path:
    """One dot per session: between-speaker lexical similarity."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((95, 70), "How similar were participants within each session?",
           font=font(42, True), fill="#18181B")
    d.text((97, 133),
           "Each point is one FG session; higher values indicate more similar lexical patterns",
           font=font(24), fill="#71717A")

    left, right, top, bottom = 245, 1690, 220, 710
    lo, hi = 0.15, 0.35
    d.text((95, top - 15), "Lexical similarity", font=font(21), fill="#3F3F46")
    for tick in (0.16, 0.20, 0.24, 0.28, 0.32):
        y = bottom - (tick - lo) / (hi - lo) * (bottom - top)
        d.line((left, y, right, y), fill="#E4E4E7", width=2)
        text_right(d, (left - 25, y - 14), f"{tick:.2f}", font(21), "#52525B")

    centers = [500, 970, 1440]
    offsets = [-92, -61, -31, 0, 31, 61, 92, -76, -46, -15, 15, 46, 76, -53, 53]
    for x, condition in zip(centers, ORDER):
        vals = list(data["by_condition"][condition][
            "between_speaker_similarity_per_document"].values())
        for i, value in enumerate(vals):
            px = x + offsets[i]
            py = bottom - (value - lo) / (hi - lo) * (bottom - top)
            d.ellipse((px - 11, py - 11, px + 11, py + 11),
                      fill=COLORS[condition], outline="white", width=2)
        median = statistics.median(vals)
        my = bottom - (median - lo) / (hi - lo) * (bottom - top)
        d.line((x - 130, my, x + 130, my), fill="#18181B", width=8)
        d.text((x + 145, my - 15), f"median {median:.3f}",
               font=font(21, True), fill="#3F3F46")
        text_center(d, (x, top - 42), f"n={len(vals)} sessions", font(20), "#71717A")
        text_center(d, (x, bottom + 28), LABELS[condition], font(27, True), "#27272A")

    d.text((97, 865),
           "Black line = median. Values use equal 50-word excerpts and are exploratory.",
           font=font(20), fill="#71717A")
    path = OUT / "agent_fidelity_lexical_variant_b_session_similarity.png"
    img.save(path, dpi=(300, 300))
    return path


if __name__ == "__main__":
    metrics = load_data()
    print(render_variant_a(metrics))
    print(render_variant_b(metrics))
