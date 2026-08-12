"""Render the Macho Meals deductive codebook as a publication-ready figure.

The figure is generated from the sealed codebook reference. Example quotations
are deliberately excluded; only category, theme, and scope are displayed.
"""

from pathlib import Path
import re
import textwrap

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / "production_evaluation" / "gold_standard_sealed" / "codebook_reference.csv"
OUTPUT = HERE / "macho_meals_codebook.png"

WIDTH, HEIGHT = 3600, 3500
BG, INK, MUTED, LINE = "#FFFFFF", "#222222", "#626262", "#D9D9D9"
THEME_COLORS = {
    "A": "#176B87",
    "B": "#D27D2D",
    "C": "#2A8C82",
    "D": "#6B6574",
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / filename), size)


def clean_text(value: object) -> str:
    """Repair common mojibake and normalise whitespace in the sealed CSV."""
    text = str(value)
    replacements = {
        "â€œ": "\u201c",
        "â€\u009d": "\u201d",
        "â€™": "\u2019",
        "â€“": "\u2013",
    }
    for broken, repaired in replacements.items():
        text = text.replace(broken, repaired)
    return re.sub(r"\s+", " ", text).strip()


def theme_parts(raw: str) -> tuple[str, str]:
    match = re.match(r"^([A-D])\)\s*(.+)$", clean_text(raw))
    if not match:
        raise ValueError(f"Unexpected theme label: {raw!r}")
    return match.group(1), match.group(2)


def wrap_for_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    face: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """Wrap text using measured pixel width rather than a fixed character count."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=face)
        if current and bbox[2] - bbox[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def rounded_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str,
    outline: str | None = None,
    width: int = 1,
    radius: int = 24,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def main() -> None:
    codebook = pd.read_csv(INPUT, encoding="utf-8")
    required = {"subtheme_id", "subtheme_label", "theme", "description", "example"}
    if not required.issubset(codebook.columns):
        raise ValueError(f"Codebook columns changed: {list(codebook.columns)}")

    # The example field is intentionally never read into the plotted records.
    records: dict[str, dict[str, object]] = {}
    for row in codebook[["subtheme_id", "subtheme_label", "theme", "description"]].itertuples(index=False):
        theme_id, theme_label = theme_parts(row.theme)
        subtheme_id = clean_text(row.subtheme_id)
        subtheme_label = clean_text(row.subtheme_label)
        # Theme D is stored as "D) Extreme cases" in both label fields.
        subtheme_label = re.sub(rf"^{re.escape(subtheme_id)}\)\s*", "", subtheme_label)
        entry = records.setdefault(theme_id, {"label": theme_label, "subthemes": []})
        entry["subthemes"].append(
            {
                "id": subtheme_id,
                "label": subtheme_label,
                "description": clean_text(row.description),
            }
        )

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # At a 6.5-inch Word text width these sizes render at roughly 9–11 pt.
    theme_face = font(68, True)
    code_face = font(62, True)
    label_face = font(70, True)
    description_face = font(68)

    margin_x, top, gap_x, gap_y = 90, 70, 70, 60
    panel_w = (WIDTH - 2 * margin_x - gap_x) // 2
    header_h, row_gap = 165, 24
    row_heights = {}
    for key in ("A", "B", "C", "D"):
        row_heights[key] = []
        for item in records[key]["subthemes"]:
            lines = wrap_for_width(draw, item["description"], description_face, panel_w - 245)
            row_heights[key].append(max(320, 145 + len(lines) * 78))
    panel_heights = {
        key: header_h + 42 + sum(row_heights[key])
        + max(0, len(records[key]["subthemes"]) - 1) * row_gap + 34
        for key in ("A", "B", "C", "D")
    }
    left_x, right_x = margin_x, margin_x + panel_w + gap_x
    positions = {
        "A": (left_x, top),
        "B": (right_x, top),
        "C": (left_x, top + panel_heights["A"] + gap_y),
        "D": (right_x, top + panel_heights["B"] + gap_y),
    }

    for theme_id in ("A", "B", "C", "D"):
        x, y = positions[theme_id]
        color = THEME_COLORS[theme_id]
        theme = records[theme_id]
        subthemes = theme["subthemes"]
        panel_h = panel_heights[theme_id]

        rounded_panel(draw, (x, y, x + panel_w, y + panel_h), BG, LINE, width=3, radius=28)
        rounded_panel(draw, (x, y, x + panel_w, y + header_h), color, radius=28)
        # Square the lower header corners while keeping the panel's rounded top.
        draw.rectangle((x, y + 75, x + panel_w, y + header_h), fill=color)

        header = f"CATEGORY {theme_id}   {theme['label']}"
        header_lines = wrap_for_width(draw, header, theme_face, panel_w - 70)
        header_y = y + 42 if len(header_lines) == 1 else y + 10
        for line in header_lines[:2]:
            draw.text((x + 35, header_y), line, font=theme_face, fill="#FFFFFF")
            header_y += 72

        inner_top = y + header_h + 30
        inner_bottom = y + panel_h - 30

        row_y = inner_top
        for idx, item in enumerate(subthemes):
            row_h = row_heights[theme_id][idx]
            rounded_panel(
                draw,
                (x + 28, row_y, x + panel_w - 28, row_y + row_h),
                "#F7F7F7",
                LINE,
                width=2,
                radius=18,
            )
            badge_w = 145
            rounded_panel(
                draw,
                (x + 35, row_y + 30, x + 35 + badge_w, row_y + 115),
                color,
                radius=14,
            )
            badge_box = draw.textbbox((0, 0), item["id"], font=code_face)
            draw.text(
                (
                    x + 35 + (badge_w - (badge_box[2] - badge_box[0])) / 2,
                    row_y + 40,
                ),
                item["id"],
                font=code_face,
                fill="#FFFFFF",
            )

            text_x = x + 205
            draw.text((text_x, row_y + 28), item["label"], font=label_face, fill=INK)
            description_lines = wrap_for_width(
                draw,
                item["description"],
                description_face,
                panel_w - 245,
            )
            line_y = row_y + 115
            for line in description_lines:
                draw.text((text_x, line_y), line, font=description_face, fill=MUTED)
                line_y += 78
            row_y += row_h + row_gap

    image.save(OUTPUT, dpi=(300, 300))
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
