"""Render the cross-model contested-as-present thematic-salience sensitivity heatmap."""
from __future__ import annotations

import csv
import json
import os
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "analysis/production_evaluation/salience_absence_audit"
SENSITIVITY = AUDIT / "across_group_recurrence_sensitivity.csv"
COMBINED = AUDIT / "combined_recurrence_sensitivity.csv"
OCA = ROOT / "analysis/production_evaluation/open_coding_adjudication/oca_integration.json"
CODEBOOK = (ROOT / "analysis/production_evaluation/gold_standard_sealed/"
            "codebook_reference.csv")
OUTPUT = Path(__file__).resolve().parent / "thematic_salience_sensitivity_heatmap.png"


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
    value = value.strip()
    if len(value) > 2 and value[0] in "ABCD" and value[1] == ")":
        return value[2:].strip()
    return value


def render() -> Path:
    with CODEBOOK.open(encoding="utf-8-sig", newline="") as handle:
        codebook = {row["subtheme_id"]: row for row in csv.DictReader(handle)}
    codes = list(codebook)

    # The combined treatment is read from a SET-BASED artefact, never recomputed here by
    # addition. Across-group recurrence counts distinct focus groups, and two independent
    # reviews may point at the same one: the blinded auditor contested A.3 in
    # macho_meals_fg4_demoonly_run01 and the human coding review proposes A.3 for that
    # same run. An earlier version of this renderer did `values[add_key] += 1`, which
    # counted fg4 twice and showed A.3 at 4 focus groups in demographics-only R1 where
    # the correct figure is 3. The A.1 removal (5 -> 4) was unaffected.
    oca = json.loads(OCA.read_text(encoding="utf-8"))
    if oca["import"]["verdict"] != "DOES_NOT_SUPPORT_A1":
        raise ValueError("the human coding review does not carry the A.1 verdict")

    with COMBINED.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    originals: dict[tuple[str, str, str], int] = {}
    values: dict[tuple[str, str, str], int] = {}
    deltas: dict[tuple[str, str, str], int] = {}
    for row in rows:
        key = (row["condition"], row["canonical_replication_index"] or "human",
               row["subtheme_id"])
        originals[key] = int(row["n_fgs_ORIGINAL"])
        values[key] = int(row["n_fgs_COMBINED"])
        deltas[key] = int(row["delta_combined"])

    columns = [("human", "human", "Human\nstudy")]
    for condition, label in (("enriched", "Enriched"),
                             ("demographics-only", "Demographics-\nonly")):
        for replicate in ("1", "2", "3"):
            columns.append((condition, replicate, f"{label}\nR{replicate}"))

    theme_w, subtheme_w, cell_w, cell_h = 330, 260, 185, 58
    margin, top = 28, 176
    grid_left = margin + theme_w + subtheme_w
    width = grid_left + cell_w * len(columns) + 35
    height = top + cell_h * len(codes) + 185

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(32, bold=True)
    subtitle_font = _font(21)
    header_font = _font(19, bold=True)
    theme_font = _font(18, bold=True)
    label_font = _font(19)
    value_font = _font(28, bold=True)
    delta_font = _font(18, bold=True)
    note_font = _font(17)

    draw.text((margin, 20), "Thematic salience sensitivity: across-group recurrence",
              fill="#172033", font=title_font)
    draw.text((margin, 66),
              "Sensitivity analysis incorporating independently reviewed coding alternatives",
              fill="#475569", font=subtitle_font)
    draw.text((margin, top - 40), "Theme", fill="#172033", font=header_font)
    draw.text((margin + theme_w, top - 40), "Subtheme", fill="#172033",
              font=header_font)

    for index, (_condition, _replicate, label) in enumerate(columns):
        box = draw.multiline_textbbox((0, 0), label, font=header_font,
                                      spacing=2, align="center")
        tw = box[2] - box[0]
        draw.multiline_text(
            (grid_left + index * cell_w + (cell_w - tw) / 2, top - 62),
            label, fill="#172033", font=header_font, spacing=2, align="center")

    groups: list[tuple[str, str, int, int]] = []
    for row_index, code in enumerate(codes):
        theme_code = code.split(".")[0]
        theme_label = _clean_theme(codebook[code]["theme"])
        if groups and groups[-1][0] == theme_code:
            prior = groups[-1]
            groups[-1] = (prior[0], prior[1], prior[2], row_index)
        else:
            groups.append((theme_code, theme_label, row_index, row_index))

    theme_colours = {"A": "#E8EEFF", "B": "#E9F7EF",
                     "C": "#FFF3DE", "D": "#F4EAFE"}
    for theme_code, theme_label, first, last in groups:
        y0, y1 = top + first * cell_h, top + (last + 1) * cell_h - 5
        draw.rounded_rectangle([margin, y0, margin + theme_w - 10, y1], radius=8,
                               fill=theme_colours.get(theme_code, "#EEF2F7"),
                               outline="#CBD5E1", width=2)
        wrapped = "\n".join(textwrap.wrap(theme_label, width=28))
        text = f"Theme {theme_code}\n{wrapped}"
        box = draw.multiline_textbbox((0, 0), text, font=theme_font,
                                      spacing=5, align="center")
        tw, th = box[2] - box[0], box[3] - box[1]
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
            key = (condition, replicate, code)
            value, delta = values[key], deltas[key]
            fraction = value / 5.0
            colour = tuple(round(low[k] + (high[k] - low[k]) * fraction)
                           for k in range(3))
            x0 = grid_left + col_index * cell_w
            border = "#F97316" if delta else "#CBD5E1"
            border_width = 4 if delta else 2
            draw.rectangle([x0, y0, x0 + cell_w - 5, y0 + cell_h - 5],
                           fill=colour, outline=border, width=border_width)
            value_text = str(value)
            box = draw.textbbox((0, 0), value_text, font=value_font)
            tw, th = box[2] - box[0], box[3] - box[1]
            draw.text((x0 + (cell_w - 5 - tw) / 2,
                       y0 + (cell_h - 5 - th) / 2 - 2), value_text,
                      fill="white" if fraction >= 0.6 else "#172033",
                      font=value_font)
            if delta:
                badge = f"{originals[key]}→{value}"
                box = draw.textbbox((0, 0), badge, font=delta_font)
                draw.text((x0 + cell_w - 11 - (box[2] - box[0]), y0 + 4), badge,
                          fill="white" if fraction >= 0.6 else "#C2410C",
                          font=delta_font)

    note_y = top + cell_h * len(codes) + 24
    notes = [
        "Orange borders and labels show original Gemini coding → sensitivity value (for example, 2→4).",
        "Themes are added when Claude found participant evidence in both blinded reviews; inconclusive cases are not added.",
        "The sensitivity analysis reclassifies FG4 demographics-only R1 from A.1 to A.3 following independent human coding review.",
        "Counts are distinct focus groups: where the blinded audit and the human review point at the same group, it is counted once.",
        "Values are focus-group recurrence counts (0–5), not mention frequency or human-validated thematic centrality.",
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
