"""Render the English thematic-salience heatmap with theme and subtheme labels."""
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
CODEBOOK = (ROOT / "analysis/production_evaluation/gold_standard_sealed/"
            "codebook_reference.csv")
OUTPUT = Path(__file__).resolve().parent / "thematic_salience_heatmap.png"


def _font(size: int, bold: bool = False):
    candidates = ([Path("C:/Windows/Fonts/arialbd.ttf")] if bold else []) + [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _clean_theme(value: str) -> str:
    """Remove the code prefix because it is displayed in its own column."""
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
    for condition, label in (("enriched", "Enriched"),
                             ("demographics-only", "Demographics-\nonly")):
        for replicate in ("1", "2", "3"):
            columns.append((condition, replicate, f"{label}\nR{replicate}"))

    profiles = {("human", "human"):
                data["human_study_profile"]["n_fgs_present"]}
    for row in data["study_replicates"]:
        profiles[(row["condition"], str(row["canonical_replication_index"]))] = \
            row["synthetic_n_fgs_present"]

    theme_w, subtheme_w, cell_w, cell_h = 330, 260, 185, 58
    margin, top = 28, 178
    grid_left = margin + theme_w + subtheme_w
    width = grid_left + cell_w * len(columns) + 35
    height = top + cell_h * len(codes) + 160

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(32, bold=True)
    subtitle_font = _font(21)
    header_font = _font(19, bold=True)
    theme_font = _font(18, bold=True)
    label_font = _font(19)
    value_font = _font(22, bold=True)
    note_font = _font(17)

    draw.text((margin, 20), "Thematic salience: across-group recurrence",
              fill="#172033", font=title_font)
    draw.text((margin, 66),
              "Number of focus groups (0–5) in which each deductive subtheme was present",
              fill="#475569", font=subtitle_font)
    draw.text((margin, top - 40), "Theme", fill="#172033", font=header_font)
    draw.text((margin + theme_w, top - 40), "Subtheme", fill="#172033",
              font=header_font)

    for index, (_condition, _replicate, label) in enumerate(columns):
        bbox = draw.multiline_textbbox((0, 0), label, font=header_font,
                                       spacing=2, align="center")
        text_w = bbox[2] - bbox[0]
        draw.multiline_text(
            (grid_left + index * cell_w + (cell_w - text_w) / 2, top - 62),
            label, fill="#172033", font=header_font, spacing=2, align="center")

    # Draw one merged visual band for each parent theme.
    groups: list[tuple[str, str, int, int]] = []
    for row_index, code in enumerate(codes):
        theme_code = code.split(".")[0]
        theme_label = _clean_theme(codebook[code]["theme"])
        if groups and groups[-1][0] == theme_code:
            old = groups[-1]
            groups[-1] = (old[0], old[1], old[2], row_index)
        else:
            groups.append((theme_code, theme_label, row_index, row_index))

    theme_colours = {"A": "#E8EEFF", "B": "#E9F7EF",
                     "C": "#FFF3DE", "D": "#F4EAFE"}
    for theme_code, theme_label, first, last in groups:
        y0, y1 = top + first * cell_h, top + (last + 1) * cell_h - 5
        draw.rounded_rectangle([margin, y0, margin + theme_w - 10, y1], radius=8,
                               fill=theme_colours.get(theme_code, "#EEF2F7"),
                               outline="#CBD5E1", width=2)
        wrapped_theme = "\n".join(textwrap.wrap(theme_label, width=28))
        text = f"Theme {theme_code}\n{wrapped_theme}"
        bbox = draw.multiline_textbbox((0, 0), text, font=theme_font,
                                       spacing=5, align="center")
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.multiline_text((margin + (theme_w - 10 - tw) / 2,
                             y0 + (y1 - y0 - th) / 2), text,
                            fill="#172033", font=theme_font, spacing=5,
                            align="center")

    low, high = (241, 245, 249), (30, 64, 175)
    for row_index, code in enumerate(codes):
        label = codebook[code]["subtheme_label"]
        if code == "D" and label.startswith("D) "):
            label = label[3:]
        y0 = top + row_index * cell_h
        draw.text((margin + theme_w, y0 + 17), f"{code} — {label}",
                  fill="#172033", font=label_font)
        for col_index, (condition, replicate, _label) in enumerate(columns):
            value = profiles[(condition, replicate)][code]
            fraction = value / 5.0
            colour = tuple(round(low[k] + (high[k] - low[k]) * fraction)
                           for k in range(3))
            x0 = grid_left + col_index * cell_w
            draw.rectangle([x0, y0, x0 + cell_w - 5, y0 + cell_h - 5],
                           fill=colour, outline="#CBD5E1", width=2)
            value_text = str(value)
            bbox = draw.textbbox((0, 0), value_text, font=value_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((x0 + (cell_w - 5 - tw) / 2,
                       y0 + (cell_h - 5 - th) / 2 - 2), value_text,
                      fill="white" if fraction >= 0.6 else "#172033",
                      font=value_font)

    note_y = top + cell_h * len(codes) + 24
    notes = [
        "0 indicates measured absence from all focus groups in that study realisation; it is not missing data.",
        "The human column represents the single human study. Each synthetic column is one complete five-group study realisation; sessions are never pooled.",
        "Salience is operationalised as LLM-coded recurrence across focus groups, not as mention frequency or validated interpretive centrality.",
    ]
    for offset, note in enumerate(notes):
        draw.text((margin, note_y + 30 * offset), note,
                  fill="#334155", font=note_font)

    temporary = OUTPUT.with_suffix(".tmp.png")
    image.save(temporary)
    os.replace(temporary, OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    print(render())
