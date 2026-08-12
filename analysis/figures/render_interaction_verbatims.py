"""Render three illustrative verbatims used in the interaction-process results."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("interaction_turn_structure_verbatims.png")
W, H = 3300, 1750
COL = {"human": "#52525B", "enriched": "#176B87", "demo": "#D27D2D"}
INK, MUTED, GRID, BG, SOFT = "#222222", "#626262", "#D8D8D8", "#FFFFFF", "#F6F6F6"

PANELS = [
    {
        "title": "Demographics-only",
        "source": "Ibrahim · FG1",
        "color": COL["demo"],
        "quote": ("“I get what Will’s saying about it being cold and transactional, "
                  "and I do miss that kind of thing. [...] But it’s also like... it’s "
                  "convenient, isn’t it? [...] But I think the thing is [...] we’re "
                  "choosing it too. [...] You feel powerless [...] but you’re also kind "
                  "of complicit in killing off the thing you’re saying you miss.”"),
        "structure": "ACKNOWLEDGES  →  COUNTERPOINT  →  BALANCES",
    },
    {
        "title": "Enriched",
        "source": "Will · FG1",
        "color": COL["enriched"],
        "quote": ("“Yeah, fair point actually. You’re right — there’s a difference "
                  "between ‘preference is shaped by context’ and ‘your preference will "
                  "change if context changes.’ [...] But I think the thing I was pushing "
                  "on is slightly different. [...] The preference is real. It’s just not "
                  "untouchable. [...] Preference is both real and contextual at the same "
                  "time.”"),
        "structure": "ACKNOWLEDGES  →  QUALIFIES  →  BALANCES",
    },
    {
        "title": "Human",
        "source": "Henry · FG2",
        "color": COL["human"],
        "quote": ("“I agree that gender doesn’t play any role whatsoever [...] There’s "
                  "no manly or womanly food. Food is food [...] It doesn’t influence me "
                  "whatsoever.”"),
        "structure": "CLEAR STANCE",
    },
]
# User-facing terminology used throughout the thesis figures.
PANELS[0]["title"] = "Basic"


def font(size, bold=False):
    candidates = ([r"C:\Windows\Fonts\arialbd.ttf"] if bold else []) + [r"C:\Windows\Fonts\arial.ttf"]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and draw.textbbox((0, 0), trial, font=fnt)[2] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def render():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((90, 48), "Illustrative structure of participant turns", fill=INK, font=font(76, True))

    margin, gap = 90, 42
    panel_w = (W - 2 * margin - 2 * gap) // 3
    panel_h = 1430
    top = 180
    for i, panel in enumerate(PANELS):
        x0 = margin + i * (panel_w + gap)
        x1 = x0 + panel_w
        panel_top = top
        bottom = panel_top + panel_h
        d.rounded_rectangle((x0, panel_top, x1, bottom), radius=24, fill=SOFT, outline=GRID, width=3)
        d.rectangle((x0, panel_top, x1, panel_top + 20), fill=panel["color"])
        d.text((x0 + 42, panel_top + 48), panel["title"], fill=INK, font=font(56, True))
        d.text((x0 + 42, panel_top + 124), panel["source"], fill=MUTED, font=font(43))

        y = panel_top + 220
        quote_font = font(52)
        for line in wrap(d, panel["quote"], quote_font, panel_w - 84):
            d.text((x0 + 42, y), line, fill=INK, font=quote_font)
            y += 69

        sy = bottom - 100
        d.line((x0 + 42, sy - 28, x1 - 42, sy - 28), fill=GRID, width=3)
        structure_font = font(32 if len(panel["structure"]) > 35 else 36, True)
        d.text((x0 + 42, sy), panel["structure"], fill=panel["color"],
               font=structure_font)

    d.text((90, 1665), "Illustrative excerpts; ellipses indicate omitted text.", fill=MUTED, font=font(42))
    img.save(OUT, dpi=(300, 300))
    return OUT


if __name__ == "__main__":
    print(render())
