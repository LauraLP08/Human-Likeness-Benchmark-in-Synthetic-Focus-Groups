"""Create the Level 1 thematic-fidelity comparison figure from scratch.

Large markers are condition means and small hollow markers are the three
stochastic executions. Replicates are not treated as independent observations.
The script uses Pillow so the exported PNG has no plotting-library dependency.
"""

from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
INPUT = HERE.parents[1] / "results" / "primary_effects_by_fg.csv"
OUTPUT = HERE / "level1_fidelidad_por_grupo.png"

METRICS = [
    ("recall", "Recuperación de subtemas", "recall"),
    ("precision", "Precisión temática", ""),
    ("reach", "Alcance entre participantes", ""),
]
COLORS = {"enriched": "#176B87", "demo": "#D27D2D"}
INK, MUTED, GRID, LINK, BG = "#222222", "#626262", "#D8D8D8", "#A6A6A6", "#FFFFFF"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


def centered(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
             face: ImageFont.FreeTypeFont, fill: str = INK) -> None:
    box = draw.textbbox((0, 0), text, font=face)
    draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2),
              text, font=face, fill=fill)


def main() -> None:
    data = pd.read_csv(INPUT)
    width, height = 3300, 1420
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    title_f, subtitle_f = font(43, True), font(27)
    panel_f, label_f, tick_f, note_f = font(31, True), font(28), font(24), font(24)
    centered(draw, (width / 2, 55), "Fidelidad temática por grupo focal y condición", title_f)

    # Legend
    legend_y = 132
    entries = [
        ("circle", COLORS["enriched"], "Perfiles enriquecidos"),
        ("square", COLORS["demo"], "Perfiles sociodemográficos"),
        ("hollow", MUTED, "Ejecuciones individuales"),
    ]
    starts = [650, 1450, 2390]
    for start, (shape, color, text) in zip(starts, entries):
        if shape == "circle":
            draw.ellipse((start, legend_y - 13, start + 26, legend_y + 13), fill=color)
        elif shape == "square":
            draw.rectangle((start, legend_y - 13, start + 26, legend_y + 13), fill=color)
        else:
            draw.ellipse((start, legend_y - 11, start + 22, legend_y + 11), outline=color, width=3)
        draw.text((start + 40, legend_y - 17), text, font=subtitle_f, fill=INK)

    left_margin, right_margin, gap = 190, 70, 65
    panel_w = (width - left_margin - right_margin - 2 * gap) / 3
    plot_top, plot_bottom = 295, 1140
    x_padding = 55
    groups = ["fg1", "fg2", "fg3", "fg4", "fg5"]
    ys = [390, 555, 720, 885, 1050]

    for panel, (metric, heading, suffix) in enumerate(METRICS):
        panel_x = left_margin + panel * (panel_w + gap)
        x0, x1 = panel_x + x_padding, panel_x + panel_w - x_padding
        subset = data[data["metric"] == metric].set_index("fg")

        centered(draw, (panel_x + panel_w / 2, 225), heading, panel_f)
        if suffix:
            centered(draw, (panel_x + panel_w / 2, 263), f"({suffix})", tick_f, MUTED)

        for tick in (0, 0.25, 0.50, 0.75, 1.00):
            tx = x0 + tick * (x1 - x0)
            draw.line((tx, plot_top, tx, plot_bottom), fill=GRID, width=2)
            centered(draw, (tx, 1191), f"{tick:.2f}", tick_f, MUTED)

        for fg, y in zip(groups, ys):
            row = subset.loc[fg]
            enriched_mean = float(row["enriched_mean"])
            demo_mean = float(row["demographics_only_mean"])
            ex = x0 + enriched_mean * (x1 - x0)
            dx = x0 + demo_mean * (x1 - x0)
            draw.line((dx, y, ex, y), fill=LINK, width=5)

            for prefix, offset, color in (
                ("enriched", -25, COLORS["enriched"]),
                ("demographics_only", 25, COLORS["demo"]),
            ):
                for i in (1, 2, 3):
                    value = float(row[f"{prefix}_r{i}"])
                    px = x0 + value * (x1 - x0)
                    draw.ellipse((px - 9, y + offset - 9, px + 9, y + offset + 9),
                                 outline=color, width=3)

            draw.rectangle((dx - 17, y - 17, dx + 17, y + 17), fill=COLORS["demo"],
                           outline=BG, width=2)
            draw.ellipse((ex - 19, y - 19, ex + 19, y + 19), fill=COLORS["enriched"],
                         outline=BG, width=2)

            if panel == 0:
                box = draw.textbbox((0, 0), fg.upper(), font=label_f)
                draw.text((x0 - 42 - (box[2] - box[0]), y - 17), fg.upper(), font=label_f, fill=INK)

        centered(draw, (panel_x + panel_w / 2, 1240), "Proporción", label_f, MUTED)

    centered(
        draw,
        (width / 2, 1325),
        "Marcadores grandes: media de tres ejecuciones. Marcadores pequeños: cada ejecución estocástica.",
        note_f,
        MUTED,
    )
    centered(
        draw,
        (width / 2, 1365),
        "Una línea hacia la derecha indica un valor mayor en los perfiles enriquecidos.",
        note_f,
        MUTED,
    )
    image.save(OUTPUT, dpi=(300, 300))


if __name__ == "__main__":
    main()
