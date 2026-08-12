"""Render the final English-labelled thematic-salience recurrence heatmap."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "analysis/production_evaluation/final"
SALIENCE = FINAL / "salience_hierarchy.json"
CODEBOOK = (ROOT / "analysis/production_evaluation/gold_standard_sealed/"
            "codebook_reference.csv")
OUTPUT = FINAL / "salience_recurrence_heatmap.png"


def _font(size: int, bold: bool = False):
    candidates = ([Path("C:/Windows/Fonts/arialbd.ttf")] if bold else []) + [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def render() -> Path:
    data = json.loads(SALIENCE.read_text(encoding="utf-8"))
    with CODEBOOK.open(encoding="utf-8") as handle:
        labels = {row["subtheme_id"]: row["subtheme_label"]
                  for row in csv.DictReader(handle)}

    codes = data["codes"]
    columns = [("human", "human", "Human study")]
    for condition, label in (("enriched", "Enriched"),
                             ("demographics-only", "Demographics-\nonly")):
        for replicate in ("1", "2", "3"):
            columns.append((condition, replicate, f"{label} R{replicate}"))

    profiles = {("human", "human"):
                data["human_study_profile"]["n_fgs_present"]}
    for row in data["study_replicates"]:
        profiles[(row["condition"], str(row["canonical_replication_index"]))] = \
            row["synthetic_n_fgs_present"]

    cell_w, cell_h, left, top = 175, 54, 410, 170
    width = left + cell_w * len(columns) + 55
    height = top + cell_h * len(codes) + 155
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(32, bold=True)
    subtitle_font = _font(21)
    header_font = _font(20, bold=True)
    label_font = _font(20)
    value_font = _font(22, bold=True)
    note_font = _font(17)

    draw.text((28, 20), "Thematic salience: across-group recurrence",
              fill="#172033", font=title_font)
    draw.text((28, 66),
              "Number of focus groups (0–5) in which each deductive subtheme was present",
              fill="#475569", font=subtitle_font)
    draw.text((28, top - 38), "Subtheme", fill="#172033", font=header_font)

    for index, (_condition, _replicate, label) in enumerate(columns):
        bbox = draw.multiline_textbbox((0, 0), label, font=header_font,
                                       spacing=2, align="center")
        text_w = bbox[2] - bbox[0]
        draw.multiline_text((left + index * cell_w + (cell_w - text_w) / 2,
                             top - 58), label, fill="#172033", font=header_font,
                            spacing=2, align="center")

    low, high = (241, 245, 249), (30, 64, 175)
    for row_index, code in enumerate(codes):
        label = labels[code]
        if code == "D" and label.startswith("D) "):
            label = label[3:]
        draw.text((28, top + row_index * cell_h + 15),
                  f"{code} — {label}", fill="#172033", font=label_font)
        for col_index, (condition, replicate, _label) in enumerate(columns):
            value = profiles[(condition, replicate)][code]
            fraction = value / 5.0
            colour = tuple(round(low[k] + (high[k] - low[k]) * fraction)
                           for k in range(3))
            x0 = left + col_index * cell_w
            y0 = top + row_index * cell_h
            draw.rectangle([x0, y0, x0 + cell_w - 5, y0 + cell_h - 5],
                           fill=colour, outline="#CBD5E1", width=2)
            value_text = str(value)
            bbox = draw.textbbox((0, 0), value_text, font=value_font)
            text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((x0 + (cell_w - 5 - text_w) / 2,
                       y0 + (cell_h - 5 - text_h) / 2 - 2), value_text,
                      fill="white" if fraction >= 0.6 else "#172033",
                      font=value_font)

    note_y = top + cell_h * len(codes) + 25
    draw.text((28, note_y),
              "0 indicates measured absence from all focus groups in that study realisation; "
              "it is not missing data.", fill="#334155", font=note_font)
    draw.text((28, note_y + 30),
              "The human column represents the single human study. Each synthetic column is "
              "one complete five-group study realisation; sessions are never pooled.",
              fill="#334155", font=note_font)
    draw.text((28, note_y + 60),
              "Salience is operationalised as recurrence across focus groups, not as validated "
              "interpretive importance or centrality.", fill="#334155", font=note_font)

    temporary = OUTPUT.with_suffix(".tmp.png")
    image.save(temporary)
    os.replace(temporary, OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(render())
