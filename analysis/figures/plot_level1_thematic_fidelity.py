"""Create the Level 1 thematic-fidelity comparison figure from scratch.

Large markers are condition means and small hollow markers are the three
individual runs. Runs are shown to characterise generator variability and are
not treated as independent focus groups.
"""

from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / "production_evaluation" / "results" / "primary_effects_by_fg.csv"
REACH_INPUT = HERE.parent / "production_evaluation" / "results" / "thematic_reach_long.csv"
OUTPUT = HERE / "level1_thematic_fidelity_by_focus_group.png"

METRICS = [
    ("recall", "Theme recall", ""),
    ("precision", "Thematic precision", ""),
    ("reach", "Participant reach vs human", ""),
]
COLORS = {"enriched": "#176B87", "demo": "#D27D2D", "human": "#52525B"}
INK, MUTED, GRID, LINK, BG = "#222222", "#626262", "#D8D8D8", "#A6A6A6", "#FFFFFF"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


def centered(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    face: ImageFont.FreeTypeFont,
    fill: str = INK,
) -> None:
    box = draw.textbbox((0, 0), text, font=face)
    draw.text(
        (xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2),
        text,
        font=face,
        fill=fill,
    )


def main() -> None:
    data = pd.read_csv(INPUT)
    reach_data = pd.read_csv(REACH_INPUT)
    human_reach = (
        reach_data.loc[reach_data["side"] == "human"]
        .groupby("fg", as_index=True)["reach"]
        .mean()
    )
    width, height = 2400, 2320
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    title_f, legend_f = font(62, True), font(38)
    panel_f, label_f, tick_f, note_f = font(47, True), font(40), font(34), font(32)
    centered(draw, (width / 2, 65), "Thematic fidelity and participant reach by focus group", title_f)

    legend_y = 155
    entries = [
        ("circle", COLORS["enriched"], "Enriched profiles"),
        ("square", COLORS["demo"], "Basic profiles"),
        ("diamond", COLORS["human"], "Human reference (reach only)"),
        ("hollow", MUTED, "Individual runs (R1–R3)"),
    ]
    starts = [90, 650, 1210, 1860]
    for start, (shape, color, text) in zip(starts, entries):
        if shape == "circle":
            draw.ellipse((start, legend_y - 13, start + 26, legend_y + 13), fill=color)
        elif shape == "square":
            draw.rectangle((start, legend_y - 13, start + 26, legend_y + 13), fill=color)
        elif shape == "diamond":
            draw.polygon(
                [(start + 13, legend_y - 15), (start + 28, legend_y),
                 (start + 13, legend_y + 15), (start - 2, legend_y)],
                fill=color,
            )
        else:
            draw.ellipse((start, legend_y - 11, start + 22, legend_y + 11), outline=color, width=3)
        draw.text((start + 40, legend_y - 23), text, font=legend_f, fill=INK)

    left_margin, right_margin = 85, 60
    panel_w = width - left_margin - right_margin
    panel_h, panel_gap = 560, 55
    panel_top = 245
    x_padding_left, x_padding_right = 190, 70
    groups = ["fg1", "fg2", "fg3", "fg4", "fg5"]
    panel_fills = ["#EDF4FA", "#EDF7F3", "#F4EFF8"]
    panel_edges = ["#8DB7CE", "#8EC5AE", "#B5A2C8"]
    panel_letters = ["A", "B", "C"]

    for panel, (metric, heading, _) in enumerate(METRICS):
        panel_x = left_margin
        panel_y = panel_top + panel * (panel_h + panel_gap)
        x0, x1 = panel_x + x_padding_left, panel_x + panel_w - x_padding_right
        plot_top, plot_bottom = panel_y + 125, panel_y + panel_h - 82
        ys = [plot_top + i * (plot_bottom - plot_top) / 4 for i in range(5)]
        subset = data[data["metric"] == metric].set_index("fg")

        draw.rounded_rectangle(
            (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h),
            radius=25,
            fill=panel_fills[panel],
            outline=panel_edges[panel],
            width=4,
        )
        draw.rectangle((panel_x, panel_y + 82, panel_x + panel_w, panel_y + panel_h - 2), fill=BG)
        draw.text((panel_x + 35, panel_y + 20), f"{panel_letters[panel]}   {heading}", font=panel_f, fill=INK)

        for tick in (0, 0.25, 0.50, 0.75, 1.00):
            tx = x0 + tick * (x1 - x0)
            draw.line((tx, plot_top, tx, plot_bottom), fill=GRID, width=2)
            centered(draw, (tx, panel_y + panel_h - 45), f"{round(tick * 100)}%", tick_f, MUTED)

        for fg, y in zip(groups, ys):
            row = subset.loc[fg]
            # A visible row guide ties every small run marker to its focus group.
            draw.line((x0, y, x1, y), fill="#E8EBEF", width=3)
            enriched_mean = float(row["enriched_mean"])
            demo_mean = float(row["demographics_only_mean"])
            ex = x0 + enriched_mean * (x1 - x0)
            dx = x0 + demo_mean * (x1 - x0)
            if metric == "reach":
                hx = x0 + float(human_reach.loc[fg]) * (x1 - x0)
                draw.line((min(dx, ex, hx), y, max(dx, ex, hx), y), fill=LINK, width=5)
            else:
                draw.line((dx, y, ex, y), fill=LINK, width=5)

            for prefix, offset, color in (
                ("enriched", -16, COLORS["enriched"]),
                ("demographics_only", 16, COLORS["demo"]),
            ):
                for i in (1, 2, 3):
                    value = float(row[f"{prefix}_r{i}"])
                    px = x0 + value * (x1 - x0)
                    draw.ellipse(
                        (px - 9, y + offset - 9, px + 9, y + offset + 9),
                        outline=color,
                        width=3,
                    )

            draw.rectangle(
                (dx - 17, y - 17, dx + 17, y + 17),
                fill=COLORS["demo"],
                outline=BG,
                width=2,
            )
            draw.ellipse(
                (ex - 19, y - 19, ex + 19, y + 19),
                fill=COLORS["enriched"],
                outline=BG,
                width=2,
            )
            if metric == "reach":
                draw.polygon(
                    [(hx, y - 22), (hx + 22, y), (hx, y + 22), (hx - 22, y)],
                    fill=COLORS["human"],
                    outline=BG,
                )

            box = draw.textbbox((0, 0), fg.upper(), font=label_f)
            draw.text(
                (x0 - 42 - (box[2] - box[0]), y - 23),
                fg.upper(),
                font=label_f,
                fill=INK,
            )

    centered(
        draw,
        (width / 2, 2155),
        "Large markers show the mean of three runs; small markers show individual runs R1–R3.",
        note_f,
        MUTED,
    )
    centered(
        draw,
        (width / 2, 2205),
        "In the reach panel, diamonds show the paired human reference for each focus group.",
        note_f,
        MUTED,
    )
    image.save(OUTPUT, dpi=(300, 300))


if __name__ == "__main__":
    main()
