"""Show when each study replicate stopped adding new deductive themes."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "analysis/production_evaluation/final/saturation_analysis.json"
OUTPUT = Path(__file__).resolve().parent / "repertoire_saturation_by_replicate.png"

COLORS = {"human": "#52525B", "enriched": "#176B87", "basic": "#D27D2D"}
SOFT = {"human": "#EEEEF0", "enriched": "#E7F3F6", "basic": "#FBEFDF"}
SAT_FILL, SAT_EDGE = "#E6F4EA", "#2E7D4F"


def font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


def centered(draw, text, cx, y, face, fill):
    box = draw.textbbox((0, 0), text, font=face)
    draw.text((cx - (box[2] - box[0]) / 2, y), text, font=face, fill=fill)


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))["accumulation_curves"]
    rows = []
    specs = [
        ("human", "human", "Human study"),
        ("enriched", "1", "Enriched R1"),
        ("enriched", "2", "Enriched R2"),
        ("enriched", "3", "Enriched R3"),
        ("demographics-only", "1", "Basic R1"),
        ("demographics-only", "2", "Basic R2"),
        ("demographics-only", "3", "Basic R3"),
    ]
    for condition, replicate, label in specs:
        record = data[condition][replicate]
        cumulative = record["observed_order"]
        increments = [cumulative[0]] + [cumulative[i] - cumulative[i - 1] for i in range(1, 5)]
        last_new = max(i for i, value in enumerate(increments) if value > 0)
        # Saturation is displayed only when at least one later FG confirms no additions.
        saturation_after = last_new + 1 if last_new < 4 else None
        key = "basic" if condition == "demographics-only" else condition
        rows.append((label, key, cumulative, increments, record["final_total_codes"], saturation_after))

    width, height = 2350, 1540
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_f, subtitle_f = font(46, True), font(30)
    header_f, row_f = font(31, True), font(31, True)
    new_f, cum_f, result_f, note_f = font(32, True), font(24), font(27, True), font(25)

    draw.text((55, 35), "When did each study stop adding new themes?", font=title_f, fill="#202124")
    draw.text(
        (55, 100),
        "Actual FG order; each row is evaluated against that replicate’s own final repertoire",
        font=subtitle_f,
        fill="#59636F",
    )

    label_x, grid_x, cell_w, cell_h = 55, 475, 285, 132
    result_x = grid_x + 5 * cell_w + 35
    top = 235
    draw.text((label_x, top - 55), "Study replicate", font=header_f, fill="#202124")
    for i in range(5):
        centered(draw, f"FG{i + 1}", grid_x + i * cell_w + (cell_w - 10) / 2, top - 58, header_f, "#202124")
    draw.text((result_x, top - 55), "Result", font=header_f, fill="#202124")

    for row_index, (label, key, cumulative, increments, total, saturation_after) in enumerate(rows):
        y = top + row_index * cell_h
        draw.rounded_rectangle(
            (label_x, y + 5, grid_x - 25, y + cell_h - 7),
            radius=18,
            fill=SOFT[key],
        )
        draw.rectangle((label_x, y + 5, label_x + 12, y + cell_h - 7), fill=COLORS[key])
        draw.text((label_x + 30, y + 28), label, font=row_f, fill="#202124")
        draw.text((label_x + 30, y + 70), f"Final repertoire: {total} themes", font=cum_f, fill="#59636F")

        for i in range(5):
            x = grid_x + i * cell_w
            in_confirmed_plateau = saturation_after is not None and i + 1 > saturation_after
            fill = SAT_FILL if in_confirmed_plateau else ("#F5F6F8" if increments[i] == 0 else SOFT[key])
            outline = SAT_EDGE if in_confirmed_plateau else "#CBD5E1"
            draw.rounded_rectangle(
                (x, y + 5, x + cell_w - 10, y + cell_h - 7),
                radius=16,
                fill=fill,
                outline=outline,
                width=4 if in_confirmed_plateau else 2,
            )
            centered(draw, f"+{increments[i]} new", x + (cell_w - 10) / 2, y + 24, new_f,
                     SAT_EDGE if in_confirmed_plateau else COLORS[key])
            centered(draw, f"{cumulative[i]}/{total} accumulated", x + (cell_w - 10) / 2, y + 72, cum_f, "#4B5563")

        if saturation_after is None:
            draw.text((result_x, y + 28), "Not observed", font=result_f, fill="#9A3412")
            draw.text((result_x, y + 70), "New themes at FG5", font=cum_f, fill="#59636F")
        else:
            draw.text((result_x, y + 28), f"After FG{saturation_after}", font=result_f, fill=SAT_EDGE)
            draw.text((result_x, y + 70), "No later additions", font=cum_f, fill="#59636F")

    note_y = top + len(rows) * cell_h + 35
    draw.rounded_rectangle((55, note_y, 2295, note_y + 78), radius=18, fill=SAT_FILL)
    draw.text(
        (80, note_y + 23),
        "Green cells confirm repetition: zero new themes in every remaining focus group.",
        font=note_f,
        fill=SAT_EDGE,
    )
    notes = [
        "Operational saturation point: the last focus group that added a new codebook theme, followed only by zero-addition groups.",
        "‘Not observed’ means FG5 still added themes; the study ended before a stable plateau could be demonstrated.",
        "This is retrospective codebook-theme saturation within the observed sample, not meaning saturation.",
    ]
    for i, note in enumerate(notes):
        draw.text((55, note_y + 105 + i * 34), note, font=note_f, fill="#4B5563")

    image.save(OUTPUT, dpi=(300, 300))
    print(OUTPUT)


if __name__ == "__main__":
    main()
