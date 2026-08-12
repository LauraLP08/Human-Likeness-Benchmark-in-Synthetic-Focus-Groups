"""Plot retrospective accumulation as a percentage of each corpus' final repertoire.

Each synthetic curve is first normalised by the final number of distinct subthemes
observed in that study replicate. The displayed condition line is the mean of the
three normalised replicate curves; the shaded band is their full range. The human
curve is based on the single human study. Curves average all 120 FG orderings.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "analysis/production_evaluation/final/saturation_analysis.json"
OUTPUT = Path(__file__).resolve().parent / "level2_normalized_theme_accumulation.png"

COLORS = {
    "human": "#52525B",
    "enriched": "#176B87",
    "demographics-only": "#D27D2D",
}


def font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    curves = source["accumulation_curves"]

    human_raw = curves["human"]["human"]["mean_exact"]
    human_total = curves["human"]["human"]["final_total_codes"]
    human = [100 * value / human_total for value in human_raw]

    synthetic: dict[str, dict[str, list[float]]] = {}
    for condition in ("enriched", "demographics-only"):
        replicate_curves = []
        for replicate in ("1", "2", "3"):
            record = curves[condition][replicate]
            total = record["final_total_codes"]
            replicate_curves.append([100 * value / total for value in record["mean_exact"]])
        synthetic[condition] = {
            "mean": [mean([curve[i] for curve in replicate_curves]) for i in range(5)],
            "min": [min(curve[i] for curve in replicate_curves) for i in range(5)],
            "max": [max(curve[i] for curve in replicate_curves) for i in range(5)],
        }

    width, height = 2100, 1320
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image, "RGBA")

    title_f, subtitle_f = font(42, True), font(27)
    label_f, tick_f, note_f, legend_f = font(28, True), font(24), font(23), font(26)

    draw.text((95, 45), "Retrospective theme accumulation across focus groups",
              fill="#202124", font=title_f)
    draw.text((95, 105), "Percentage of each study replicate's final observed repertoire",
              fill="#59636F", font=subtitle_f)

    left, right, top, bottom = 210, 1950, 255, 1050
    plot_w, plot_h = right - left, bottom - top

    def xy(index: int, value: float) -> tuple[float, float]:
        return left + index * plot_w / 4, bottom - value * plot_h / 100

    for value in (0, 20, 40, 60, 80, 100):
        y = xy(0, value)[1]
        draw.line((left, y, right, y), fill="#D9DEE5", width=2)
        label = f"{value}%"
        box = draw.textbbox((0, 0), label, font=tick_f)
        draw.text((left - 25 - (box[2] - box[0]), y - 14), label,
                  fill="#59636F", font=tick_f)

    for index in range(5):
        x = xy(index, 0)[0]
        draw.line((x, top, x, bottom), fill="#EEF1F4", width=2)
        label = str(index + 1)
        box = draw.textbbox((0, 0), label, font=tick_f)
        draw.text((x - (box[2] - box[0]) / 2, bottom + 28), label,
                  fill="#59636F", font=tick_f)

    draw.text((left + plot_w / 2 - 135, bottom + 42), "Focus groups included",
              fill="#30343B", font=label_f)
    draw.text((left, top - 55), "Cumulative share of final repertoire",
              fill="#30343B", font=label_f)

    # Range bands for the three synthetic study replicates.
    for condition in ("enriched", "demographics-only"):
        record = synthetic[condition]
        upper = [xy(i, record["max"][i]) for i in range(5)]
        lower = [xy(i, record["min"][i]) for i in reversed(range(5))]
        rgb = tuple(int(COLORS[condition][j:j + 2], 16) for j in (1, 3, 5))
        draw.polygon(upper + lower, fill=(*rgb, 34))

    series = [
        ("Human study", human, "human", 6, -52),
        ("Enriched profiles", synthetic["enriched"]["mean"], "enriched", 7, -34),
        ("Demographics-only profiles", synthetic["demographics-only"]["mean"],
         "demographics-only", 7, 20),
    ]
    for _label, values, key, line_width, label_offset in series:
        points = [xy(i, value) for i, value in enumerate(values)]
        draw.line(points, fill=COLORS[key], width=line_width, joint="curve")
        for x, y in points:
            draw.ellipse((x - 10, y - 10, x + 10, y + 10),
                         fill=COLORS[key], outline="white", width=3)
        for index, value in enumerate(values[:3]):
            x, y = points[index]
            text = f"{value:.0f}%"
            box = draw.textbbox((0, 0), text, font=tick_f)
            draw.text((x - (box[2] - box[0]) / 2, y + label_offset), text,
                      fill=COLORS[key], font=tick_f)

    legend_y = 190
    legend_entries = [
        ("Human study", "human", 470),
        ("Enriched profiles", "enriched", 850),
        ("Demographics-only profiles", "demographics-only", 1320),
    ]
    for label, key, x in legend_entries:
        draw.line((x, legend_y, x + 50, legend_y), fill=COLORS[key], width=7)
        draw.ellipse((x + 15, legend_y - 10, x + 35, legend_y + 10),
                     fill=COLORS[key], outline="white", width=2)
        draw.text((x + 65, legend_y - 17), label, fill="#30343B", font=legend_f)

    notes = [
        "All curves end at 100% by definition: the denominator is the final repertoire observed in that same study replicate.",
        "Synthetic lines are means of three study replicates; shaded bands show their full range.",
        "Each point averages all 120 possible orders of FG1–FG5. This is fixed-codebook coverage, not inductive or meaning saturation.",
    ]
    for index, note in enumerate(notes):
        draw.text((95, 1155 + index * 38), note, fill="#4B5563", font=note_f)

    image.save(OUTPUT, dpi=(300, 300))


if __name__ == "__main__":
    main()
