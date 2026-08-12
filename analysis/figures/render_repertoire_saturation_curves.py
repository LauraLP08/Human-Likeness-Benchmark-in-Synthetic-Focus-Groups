"""Plot absolute cumulative-theme curves and their observed plateaus by replicate."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "analysis/production_evaluation/final/saturation_analysis.json"
OUTPUT = Path(__file__).resolve().parent / "repertoire_saturation_curves.png"

COLORS = {"human": "#52525B", "enriched": "#176B87", "basic": "#D27D2D"}
GREEN, RED, GRID, INK, MUTED = "#2E7D4F", "#B54728", "#D9DEE5", "#202124", "#59636F"


def font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


def centered(draw, text, cx, y, face, fill=INK):
    box = draw.textbbox((0, 0), text, font=face)
    draw.text((cx - (box[2] - box[0]) / 2, y), text, font=face, fill=fill)


def main() -> None:
    curves = json.loads(SOURCE.read_text(encoding="utf-8"))["accumulation_curves"]
    specs = [
        ("human", "human", "Human study"),
        ("enriched", "1", "Enriched R1"),
        ("enriched", "2", "Enriched R2"),
        ("enriched", "3", "Enriched R3"),
        ("demographics-only", "1", "Basic R1"),
        ("demographics-only", "2", "Basic R2"),
        ("demographics-only", "3", "Basic R3"),
    ]

    width, height = 2400, 1810
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_f, subtitle_f = font(48, True), font(30)
    panel_f, status_f, tick_f, value_f, note_f = font(34, True), font(27, True), font(24), font(27, True), font(25)

    draw.text((70, 38), "Absolute theme accumulation and observed saturation", font=title_f, fill=INK)
    draw.text(
        (70, 108),
        "Actual FG order • absolute repertoires • green segments show confirmed zero-addition plateaus",
        font=subtitle_f,
        fill=MUTED,
    )

    panel_w, panel_h = 1085, 350
    gap_x, gap_y = 90, 35
    start_x, start_y = 70, 215

    for idx, (condition, replicate, label) in enumerate(specs):
        col, row = idx % 2, idx // 2
        px = start_x + col * (panel_w + gap_x)
        py = start_y + row * (panel_h + gap_y)
        record = curves[condition][replicate]
        values = record["observed_order"]
        increments = [values[0]] + [values[i] - values[i - 1] for i in range(1, 5)]
        last_new = max(i for i, v in enumerate(increments) if v > 0)
        saturated = last_new < 4
        sat_after = last_new + 1 if saturated else None
        key = "basic" if condition == "demographics-only" else condition
        color = COLORS[key]

        draw.text((px, py), label, font=panel_f, fill=INK)
        status = f"Saturation after FG{sat_after}" if saturated else "Saturation not observed"
        status_color = GREEN if saturated else RED
        box = draw.textbbox((0, 0), status, font=status_f)
        draw.text((px + panel_w - (box[2] - box[0]), py + 5), status, font=status_f, fill=status_color)

        left, right = px + 75, px + panel_w - 55
        top, bottom = py + 72, py + panel_h - 53

        def xy(i: int, value: float):
            return left + i * (right - left) / 4, bottom - value * (bottom - top) / 11

        for value in (0, 5, 10):
            y = xy(0, value)[1]
            draw.line((left, y, right, y), fill=GRID, width=2)
            text = str(value)
            b = draw.textbbox((0, 0), text, font=tick_f)
            draw.text((left - 18 - (b[2] - b[0]), y - 13), text, font=tick_f, fill=MUTED)
        for i in range(5):
            x, _ = xy(i, 0)
            centered(draw, f"FG{i + 1}", x, bottom + 15, tick_f, MUTED)

        # Step curve: horizontal segment represents what was known until the next FG.
        for i in range(4):
            x1, y1 = xy(i, values[i])
            x2, y2 = xy(i + 1, values[i + 1])
            segment_color = GREEN if saturated and i >= last_new else color
            draw.line((x1, y1, x2, y1), fill=segment_color, width=8)
            draw.line((x2, y1, x2, y2), fill=segment_color, width=8)
        for i, value in enumerate(values):
            x, y = xy(i, value)
            marker_color = GREEN if saturated and i > last_new else color
            draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=marker_color, outline="white", width=3)
            if i == 4:
                outline = GREEN if saturated else RED
                draw.ellipse((x - 17, y - 17, x + 17, y + 17), outline=outline, width=5)
                draw.text((x - 8, y - 48), str(value), font=value_f, fill=outline)

        draw.text((left, top - 35), "Cumulative themes", font=tick_f, fill=MUTED)

    # The eighth grid position is used for the interpretation key.
    px = start_x + (panel_w + gap_x)
    py = start_y + 3 * (panel_h + gap_y)
    draw.rounded_rectangle((px, py, px + panel_w, py + panel_h - 30), radius=22, fill="#F7F8FA")
    draw.text((px + 35, py + 30), "How to read the curves", font=panel_f, fill=INK)
    draw.line((px + 40, py + 115, px + 185, py + 115), fill=GREEN, width=9)
    draw.text((px + 220, py + 94), "Confirmed plateau", font=status_f, fill=GREEN)
    draw.text((px + 220, py + 130), "No later focus group added a theme", font=tick_f, fill=MUTED)
    draw.ellipse((px + 45, py + 195, px + 75, py + 225), outline=RED, width=5)
    draw.text((px + 220, py + 190), "No plateau observed", font=status_f, fill=RED)
    draw.text((px + 220, py + 226), "FG5 still added at least one theme", font=tick_f, fill=MUTED)

    note_y = 1750
    centered(
        draw,
        "Retrospective codebook-theme saturation within the observed sample; this does not assess meaning saturation.",
        width / 2,
        note_y,
        note_f,
        MUTED,
    )
    image.save(OUTPUT, dpi=(300, 300))
    print(OUTPUT)


if __name__ == "__main__":
    main()
