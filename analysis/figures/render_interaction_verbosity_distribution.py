"""Render the participant-turn length distribution from the frozen structural data.

Each focus group has equal weight. For synthetic conditions, bin percentages are
first averaged across the three replications of a focus group and then across the
five focus groups.
"""
from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = (
    REPO
    / "analysis"
    / "production_evaluation"
    / "results"
    / "structural_distributions_long.csv"
)
OUT = HERE / "interaction_verbosity_distribution.png"

W, H = 2200, 1320
BG, INK, MUTED, GRID = "#FFFFFF", "#222222", "#626262", "#D8D8D8"
COLORS = {
    "human": "#52525B",
    "enriched": "#176B87",
    "demographics-only": "#D27D2D",
}
LABELS = {
    "human": "Human (5 FGs)",
    "enriched": "Enriched (5 FGs × 3 replicates)",
    "demographics-only": "Demographics-only (5 FGs × 3 replicates)",
}
CONDITIONS = ["human", "enriched", "demographics-only"]
# User-facing terminology used throughout the thesis figures.
LABELS["enriched"] = "Enriched (5 FGs × 3 runs)"
LABELS["demographics-only"] = "Basic (5 FGs × 3 runs)"
BINS = [
    (1, 10, "1–10"),
    (11, 20, "11–20"),
    (21, 40, "21–40"),
    (41, 80, "41–80"),
    (81, 150, "81–150"),
    (151, 250, "151–250"),
    (251, 400, "251–400"),
    (401, None, "401+"),
]


def font(size: int, bold: bool = False):
    candidates = ([r"C:\Windows\Fonts\arialbd.ttf"] if bold else []) + [
        r"C:\Windows\Fonts\arial.ttf"
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def bin_index(value: int) -> int:
    for index, (lower, upper, _) in enumerate(BINS):
        if value >= lower and (upper is None or value <= upper):
            return index
    raise ValueError(f"Turn length outside declared bins: {value}")


def load_distribution():
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["distribution_id"] == "words_per_turn"
        ]

    sessions: dict[str, dict[tuple[str, str], list[int]]] = {
        condition: defaultdict(list) for condition in CONDITIONS
    }
    for row in rows:
        condition = row["condition"]
        if condition not in sessions:
            continue
        value = int(float(row["value"]))
        run_id = row["physical_run"] or f"human_{row['fg']}"
        sessions[condition][(row["fg"], run_id)].append(value)

    distributions: dict[str, list[float]] = {}
    mean_fg_medians: dict[str, float] = {}
    for condition in CONDITIONS:
        by_fg: dict[str, list[list[float]]] = defaultdict(list)
        medians_by_fg: dict[str, list[float]] = defaultdict(list)
        for (fg, _), values in sessions[condition].items():
            percentages = [
                100 * sum(bin_index(value) == i for value in values) / len(values)
                for i in range(len(BINS))
            ]
            by_fg[fg].append(percentages)
            medians_by_fg[fg].append(statistics.median(values))

        if set(by_fg) != {"fg1", "fg2", "fg3", "fg4", "fg5"}:
            raise ValueError(f"Incomplete focus-group coverage for {condition}: {sorted(by_fg)}")

        fg_means = [
            [statistics.mean(rep[i] for rep in replications) for i in range(len(BINS))]
            for replications in by_fg.values()
        ]
        distributions[condition] = [
            statistics.mean(fg[i] for fg in fg_means) for i in range(len(BINS))
        ]
        mean_fg_medians[condition] = statistics.mean(
            statistics.mean(replication_medians)
            for replication_medians in medians_by_fg.values()
        )

    return distributions, mean_fg_medians


def render() -> Path:
    distributions, medians = load_distribution()
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw.text((85, 45), "Distribution of participant turn length", fill=INK, font=font(58, True))
    draw.text(
        (85, 122),
        "Mean of five FG-level percentages; each synthetic FG first averages its three runs",
        fill=MUTED,
        font=font(32),
    )

    legend_y = 205
    legend_positions = {"human": 85, "enriched": 600, "demographics-only": 1320}
    for condition in CONDITIONS:
        legend_x = legend_positions[condition]
        draw.rounded_rectangle(
            (legend_x, legend_y, legend_x + 30, legend_y + 30),
            radius=5,
            fill=COLORS[condition],
        )
        draw.text((legend_x + 45, legend_y - 4), LABELS[condition], fill=INK, font=font(31))

    left, right, top, bottom = 155, 2135, 315, 1040
    y_max = 60
    for tick in range(0, y_max + 1, 10):
        y = bottom - (bottom - top) * tick / y_max
        draw.line((left, y, right, y), fill=GRID, width=1)
        label = f"{tick}%"
        box = draw.textbbox((0, 0), label, font=font(30))
        draw.text((left - 20 - (box[2] - box[0]), y - 17), label, fill=MUTED, font=font(30))

    group_width = (right - left) / len(BINS)
    bar_width = 54
    gap = 10
    cluster_width = len(CONDITIONS) * bar_width + (len(CONDITIONS) - 1) * gap

    for bin_i, (_, _, bin_label) in enumerate(BINS):
        centre = left + group_width * (bin_i + 0.5)
        cluster_left = centre - cluster_width / 2
        for condition_i, condition in enumerate(CONDITIONS):
            value = distributions[condition][bin_i]
            x0 = cluster_left + condition_i * (bar_width + gap)
            x1 = x0 + bar_width
            y0 = bottom - (bottom - top) * value / y_max
            draw.rounded_rectangle(
                (round(x0), round(y0), round(x1), bottom),
                radius=5,
                fill=COLORS[condition],
            )
            if value >= 1.0:
                value_label = f"{round(value)}%"
                box = draw.textbbox((0, 0), value_label, font=font(27, True))
                draw.text(
                    ((x0 + x1 - (box[2] - box[0])) / 2, y0 - 38),
                    value_label,
                    fill=COLORS[condition],
                    font=font(27, True),
                )

        box = draw.textbbox((0, 0), bin_label, font=font(30))
        draw.text((centre - (box[2] - box[0]) / 2, bottom + 24), bin_label, fill=INK, font=font(30))

    draw.line((left, bottom, right, bottom), fill=MUTED, width=2)
    x_title = "Words per participant turn"
    box = draw.textbbox((0, 0), x_title, font=font(34))
    draw.text(((left + right - (box[2] - box[0])) / 2, 1120), x_title, fill=MUTED, font=font(34))

    median_note = (
        "Mean of FG-level medians (words per turn): "
        f"Human {round(medians['human'])}  |  "
        f"Enriched {round(medians['enriched'])}  |  "
        f"Basic {round(medians['demographics-only'])}"
    )
    draw.text((155, 1240), median_note, fill=MUTED, font=font(31))

    image.save(OUT, dpi=(300, 300))
    return OUT


if __name__ == "__main__":
    print(render())
