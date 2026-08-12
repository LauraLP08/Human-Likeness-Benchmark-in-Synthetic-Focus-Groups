"""Render the reader-facing specificity figure from frozen reported values."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("interaction_specificity_density.png")
W, H = 2200, 2200
COL = {"human": "#52525B", "enriched": "#176B87", "demo": "#D27D2D"}
INK, MUTED, GRID, BG = "#222222", "#626262", "#D8D8D8", "#FFFFFF"

# Overall values exclude mentions of participants' stated origin geography,
# following the frozen correction in SPECIFICITY_PLACE_CORRECTED.md.
PANELS = [
    ("Contextual references",
     "All seven reference categories combined",
     3.168, (2.784, 3.680), 1.674, (1.594, 1.768), 1.273, (0.968, 1.499), 4.0),
    ("Subset - proper names or quantities", "",
     0.347, (0.249, 0.555), 0.141, (0.120, 0.166), 0.227, (0.103, 0.335), 0.8),
    ("Subset - named foods or dishes", "",
     2.016, (1.478, 2.303), 0.886, (0.580, 1.132), 0.238, (0.025, 0.406), 2.5),
    ("Subset - brands or organisations", "",
     0.158, (0.083, 0.229), 0.043, (0.010, 0.075), 0.060, (0.016, 0.129), 0.25),
]


def font(size, bold=False):
    paths = ([r"C:\Windows\Fonts\arialbd.ttf"] if bold else []) + [
        r"C:\Windows\Fonts\arial.ttf"
    ]
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def fmt(value, xmax):
    # Display-only rounding; all positions and comparisons use full precision.
    return f"{value:.2f}"


def marker(draw, x, y, kind, color):
    if kind == "diamond":
        draw.polygon([(x, y - 18), (x + 18, y), (x, y + 18), (x - 18, y)],
                     fill=color, outline=BG)
    elif kind == "square":
        draw.rectangle((x - 17, y - 17, x + 17, y + 17), fill=color, outline=BG)
    else:
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=color, outline=BG)


def render():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((75, 38), "Specific detail density in participant turns",
           fill=INK, font=font(60, True))
    d.text((75, 116), "References per 100 participant words; stated origin geography excluded",
           fill=MUTED, font=font(34))

    panel_fills = ["#EDF4FA", "#EDF7F3", "#FFF4E5", "#F4EFF8"]
    panel_edges = ["#8DB7CE", "#8EC5AE", "#D9B06C", "#B5A2C8"]
    panel_letters = ["A", "B", "C", "D"]
    px, pw, ph, gap = 75, 2050, 410, 40
    positions = [(px, 220 + i * (ph + gap)) for i in range(4)]
    for panel_i, ((title, detail, human, hrange, enriched, erange, demo, drange, xmax), (px, py)) in enumerate(zip(PANELS, positions)):
        d.rounded_rectangle(
            (px, py, px + pw, py + ph), radius=24,
            fill=panel_fills[panel_i], outline=panel_edges[panel_i], width=4,
        )
        d.rectangle((px, py + 82, px + pw, py + ph - 2), fill=BG)
        d.text((px + 30, py + 20), f"{panel_letters[panel_i]}   {title}", fill=INK, font=font(42, True))
        if detail:
            d.text((px + 820, py + 29), detail, fill=MUTED, font=font(28))
        x0, x1 = px + 455, px + pw - 65
        y0 = py + 130
        for i in range(5):
            x = x0 + (x1 - x0) * i / 4
            d.line((x, y0, x, y0 + 180), fill=GRID, width=2)
            tick = xmax * i / 4
            label = fmt(tick, xmax)
            tick_font = font(29)
            box = d.textbbox((0, 0), label, font=tick_font)
            d.text((x - (box[2] - box[0]) / 2, y0 + 195), label, fill=MUTED, font=tick_font)

        rows = [
            ("Human", human, hrange, "diamond", COL["human"]),
            ("Enriched", enriched, erange, "circle", COL["enriched"]),
            ("Basic", demo, drange, "square", COL["demo"]),
        ]
        for j, (label, value, value_range, kind, color) in enumerate(rows):
            y = y0 + 30 + j * 70
            d.line((x0, y, x1, y), fill="#ECEFF2", width=2)
            d.text((px + 35, y - 20), label, fill=INK, font=font(35))
            lo = x0 + (x1 - x0) * value_range[0] / xmax
            hi = x0 + (x1 - x0) * value_range[1] / xmax
            d.line((lo, y, hi, y), fill=color, width=7)
            d.line((lo, y - 12, lo, y + 12), fill=color, width=5)
            d.line((hi, y - 12, hi, y + 12), fill=color, width=5)
            x = x0 + (x1 - x0) * value / xmax
            marker(d, x, y, kind, color)
            value_text = fmt(value, xmax)
            value_font = font(30, True)
            value_box = d.textbbox((0, 0), value_text, font=value_font)
            tx = min(x + 28, x1 - (value_box[2] - value_box[0]))
            value_y = y - 52
            d.text((tx, value_y), value_text, fill=color, font=value_font)

    # Compact legend for the only interval in the figure.
    legend_y = 2070
    d.line((80, legend_y, 155, legend_y), fill=COL["human"], width=7)
    d.line((80, legend_y - 12, 80, legend_y + 12), fill=COL["human"], width=5)
    d.line((155, legend_y - 12, 155, legend_y + 12), fill=COL["human"], width=5)
    d.text((180, legend_y - 35), "Ranges show the minimum and maximum across the five focus groups.",
           fill=MUTED, font=font(31))
    d.text((180, legend_y + 5), "Human uses each observed FG value; Enriched and Basic use the R1–R3 mean for each FG.",
           fill=MUTED, font=font(31))
    img.save(OUT, dpi=(300, 300))
    return OUT


if __name__ == "__main__":
    print(render())
