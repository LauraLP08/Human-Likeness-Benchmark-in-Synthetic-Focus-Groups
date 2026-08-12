"""Render the Word-optimised salience heatmap using category/theme terminology."""
from __future__ import annotations

import csv
import json
import os
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "analysis/production_evaluation/final"
SALIENCE = FINAL / "salience_hierarchy.json"
CODEBOOK = ROOT / "analysis/production_evaluation/gold_standard_sealed/codebook_reference.csv"
OUTPUT = Path(__file__).resolve().parent / "thematic_salience_categories_heatmap.png"


def _font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size=size)


def _clean_category(value: str) -> str:
    value = value.strip()
    if len(value) > 2 and value[0] in "ABCD" and value[1] == ")":
        return value[2:].strip()
    return value


def render() -> Path:
    data = json.loads(SALIENCE.read_text(encoding="utf-8"))
    with CODEBOOK.open(encoding="utf-8-sig", newline="") as handle:
        codebook = {row["subtheme_id"]: row for row in csv.DictReader(handle)}

    codes = data["codes"]
    columns = [("human", "human", "Human\nstudy")]
    for condition, label in (("enriched", "Enriched"), ("demographics-only", "Basic")):
        for replicate in ("1", "2", "3"):
            columns.append((condition, replicate, f"{label}\nR{replicate}"))

    profiles = {("human", "human"): data["human_study_profile"]["n_fgs_present"]}
    for row in data["study_replicates"]:
        profiles[(row["condition"], str(row["canonical_replication_index"]))] = dict(
            row["synthetic_n_fgs_present"]
        )

    # Two human readjustments requested for Basic R1.
    profiles[("demographics-only", "1")]["A.1"] = 4
    profiles[("demographics-only", "1")]["A.3"] = 3
    adjusted = {("demographics-only", "1", "A.1"), ("demographics-only", "1", "A.3")}

    category_w, theme_w, cell_w, cell_h = 300, 390, 160, 88
    margin, top = 30, 205
    grid_left = margin + category_w + theme_w
    width = grid_left + cell_w * len(columns) + 35
    height = top + cell_h * len(codes) + 185

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(42, True)
    subtitle_font = _font(29)
    header_font = _font(30, True)
    category_font = _font(30, True)
    label_font = _font(32)
    value_font = _font(36, True)
    note_font = _font(28)

    draw.text((margin, 22), "Thematic salience: across-group recurrence", fill="#172033", font=title_font)
    draw.text(
        (margin, 82),
        "Number of focus groups (0–5) in which each deductive theme was present",
        fill="#475569",
        font=subtitle_font,
    )
    draw.text((margin, top - 48), "Category", fill="#172033", font=header_font)
    draw.text((margin + category_w, top - 48), "Theme", fill="#172033", font=header_font)

    for index, (_condition, _replicate, label) in enumerate(columns):
        box = draw.multiline_textbbox((0, 0), label, font=header_font, spacing=3, align="center")
        tw = box[2] - box[0]
        draw.multiline_text(
            (grid_left + index * cell_w + (cell_w - tw) / 2, top - 76),
            label,
            fill="#172033",
            font=header_font,
            spacing=3,
            align="center",
        )

    groups = []
    for row_index, code in enumerate(codes):
        category_code = code.split(".")[0]
        category_label = _clean_category(codebook[code]["theme"])
        if groups and groups[-1][0] == category_code:
            old = groups[-1]
            groups[-1] = (old[0], old[1], old[2], row_index)
        else:
            groups.append((category_code, category_label, row_index, row_index))

    category_colours = {"A": "#E8EEFF", "B": "#E9F7EF", "C": "#FFF3DE", "D": "#F4EAFE"}
    for category_code, category_label, first, last in groups:
        y0, y1 = top + first * cell_h, top + (last + 1) * cell_h - 6
        draw.rounded_rectangle(
            [margin, y0, margin + category_w - 10, y1],
            radius=10,
            fill=category_colours[category_code],
            outline="#CBD5E1",
            width=2,
        )
        wrapped = "\n".join(textwrap.wrap(category_label, width=22))
        text = f"Category {category_code}\n{wrapped}"
        box = draw.multiline_textbbox((0, 0), text, font=category_font, spacing=6, align="center")
        tw, th = box[2] - box[0], box[3] - box[1]
        draw.multiline_text(
            (margin + (category_w - 10 - tw) / 2, y0 + (y1 - y0 - th) / 2),
            text,
            fill="#172033",
            font=category_font,
            spacing=6,
            align="center",
        )

    low, high = (241, 245, 249), (30, 64, 175)
    for row_index, code in enumerate(codes):
        label = codebook[code]["subtheme_label"]
        if code == "D" and label.startswith("D) "):
            label = label[3:]
        y0 = top + row_index * cell_h
        draw.text((margin + category_w, y0 + 25), f"{code} — {label}", fill="#172033", font=label_font)
        for col_index, (condition, replicate, _label) in enumerate(columns):
            value = profiles[(condition, replicate)][code]
            fraction = value / 5.0
            colour = tuple(round(low[k] + (high[k] - low[k]) * fraction) for k in range(3))
            x0 = grid_left + col_index * cell_w
            is_adjusted = (condition, replicate, code) in adjusted
            draw.rectangle(
                [x0, y0, x0 + cell_w - 6, y0 + cell_h - 6],
                fill=colour,
                outline="#F97316" if is_adjusted else "#CBD5E1",
                width=6 if is_adjusted else 2,
            )
            value_text = str(value)
            box = draw.textbbox((0, 0), value_text, font=value_font)
            tw, th = box[2] - box[0], box[3] - box[1]
            draw.text(
                (x0 + (cell_w - 6 - tw) / 2, y0 + (cell_h - 6 - th) / 2 - 3),
                value_text,
                fill="white" if fraction >= 0.6 else "#172033",
                font=value_font,
            )

    note_y = top + cell_h * len(codes) + 25
    notes = [
        "Orange borders indicate a human readjustment following uncertainty flagged by Gemini.",
        "0 indicates measured absence from all focus groups in that study replicate; it is not missing data.",
        "Each synthetic column is one complete five-group study replicate; sessions are never pooled.",
        "Salience is recurrence across focus groups, not mention frequency or interpretive centrality.",
    ]
    for offset, note in enumerate(notes):
        draw.text((margin, note_y + 37 * offset), note, fill="#334155", font=note_font)

    temporary = OUTPUT.with_suffix(".tmp.png")
    image.save(temporary, dpi=(300, 300))
    os.replace(temporary, OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(render())
