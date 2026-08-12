"""A visual, example-led explanation of deductive and inductive coding."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "codebook_vs_open_coding.png"
WIDTH, HEIGHT = 3200, 2000
BG, INK, MUTED, LINE = "#FFFFFF", "#202020", "#5B5B5B", "#D6D6D6"
BLUE, BLUE_SOFT = "#176B87", "#E7F3F6"
GREEN, GREEN_SOFT = "#2A8C82", "#E7F4F1"
YELLOW = "#F3C969"


def font(size, bold=False):
    return ImageFont.truetype(
        str(Path("C:/Windows/Fonts") / ("arialbd.ttf" if bold else "arial.ttf")), size
    )


def text_center(draw, text, cx, y, face, fill=INK):
    b = draw.textbbox((0, 0), text, font=face)
    draw.text((cx - (b[2] - b[0]) / 2, y), text, font=face, fill=fill)


def rounded(draw, box, fill, outline=None, width=1, radius=25):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def arrow(draw, x1, y1, x2, y2, color, width=10):
    draw.line((x1, y1, x2, y2), fill=color, width=width)
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 30
    pts = [(x2, y2)]
    for off in (2.55, -2.55):
        pts.append((x2 + size * math.cos(angle + off), y2 + size * math.sin(angle + off)))
    draw.polygon(pts, fill=color)


def speech(draw, x, y, w, text, accent):
    rounded(draw, (x, y, x + w, y + 118), "#F6F6F6", LINE, 3, 22)
    draw.polygon([(x + 70, y + 118), (x + 105, y + 118), (x + 78, y + 148)], fill="#F6F6F6")
    draw.rectangle((x + 20, y + 20, x + 32, y + 98), fill=accent)
    draw.text((x + 55, y + 31), f'“{text}”', font=font(31), fill=INK)


def tag(draw, x, y, w, text, color, filled=False):
    rounded(draw, (x, y, x + w, y + 76), color if filled else BG, color, 4, 18)
    text_center(draw, text, x + w / 2, y + 20, font(29, True), BG if filled else INK)


def sticky(draw, x, y, text, color):
    rounded(draw, (x, y, x + 245, y + 105), color, radius=12)
    draw.polygon([(x + 210, y), (x + 245, y), (x + 245, y + 35)], fill="#FFFFFF")
    text_center(draw, text, x + 122, y + 34, font(28, True))


def main():
    im = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(im)
    title, subtitle = font(62, True), font(35)
    head, subhead, small = font(42, True), font(31, True), font(29)

    text_center(d, "Same conversation, two different starting points", WIDTH / 2, 48, title)
    text_center(d, "Watch what happens to the same two comments", WIDTH / 2, 130, subtitle, MUTED)

    # Shared evidence: the same comments feed both paths.
    rounded(d, (1020, 215, 2180, 690), "#FAFAFA", LINE, 4, 30)
    text_center(d, "WHAT PEOPLE SAID", 1600, 245, head)
    speech(d, 1080, 330, 1040, "Meat gives me the protein I need.", BLUE)
    speech(d, 1080, 475, 1040, "Plant-based food never fills me up.", GREEN)
    d.text((1250, 620), "The evidence is identical in both approaches", font=small, fill=MUTED)

    # Branch arrows.
    arrow(d, 1280, 690, 760, 790, BLUE, 12)
    arrow(d, 1920, 690, 2440, 790, GREEN, 12)

    # Left path: labels visibly exist first.
    rounded(d, (90, 770, 1535, 1885), BLUE_SOFT, LINE, 4, 30)
    rounded(d, (90, 770, 1535, 900), BLUE, radius=30)
    d.rectangle((90, 835, 1535, 900), fill=BLUE)
    text_center(d, "CODEBOOK CODING (DEDUCTIVE)", 812, 808, head, BG)
    text_center(d, "The boxes have names before reading", 812, 930, subhead)

    # A small codebook appears before the quotes are sorted.
    rounded(d, (180, 1015, 650, 1395), BG, BLUE, 5, 22)
    d.text((235, 1050), "LABELS READY", font=subhead, fill=BLUE)
    tag(d, 245, 1140, 340, "Necessary", BLUE, True)
    tag(d, 245, 1245, 340, "Insufficient", BLUE, True)
    d.text((270, 1345), "chosen in advance", font=small, fill=MUTED)

    arrow(d, 700, 1205, 845, 1205, BLUE)
    rounded(d, (890, 1005, 1435, 1405), BG, LINE, 3, 22)
    d.text((940, 1040), "READ AND SORT", font=subhead, fill=BLUE)
    d.text((940, 1120), "protein needed", font=small, fill=INK)
    arrow(d, 1190, 1165, 1190, 1215, BLUE, 7)
    tag(d, 960, 1230, 455, "NECESSARY", BLUE, True)
    d.text((940, 1330), "never fills me up", font=small, fill=INK)
    arrow(d, 1190, 1370, 1190, 1420, BLUE, 7)
    tag(d, 960, 1435, 455, "INSUFFICIENT", BLUE, True)

    rounded(d, (180, 1640, 1445, 1800), BG, BLUE, 4, 24)
    text_center(d, "Question answered: Did the expected ideas appear?", 812, 1682, font(33, True))
    text_center(d, "LOOK FOR WHAT WAS DEFINED BEFORE", 812, 1740, font(29, True), BLUE)

    # Right path: observations visibly appear first, then group, then name.
    rounded(d, (1665, 770, 3110, 1885), GREEN_SOFT, LINE, 4, 30)
    rounded(d, (1665, 770, 3110, 900), GREEN, radius=30)
    d.rectangle((1665, 835, 3110, 900), fill=GREEN)
    text_center(d, "OPEN CODING (INDUCTIVE)", 2387, 808, head, BG)
    text_center(d, "The names are created after reading", 2387, 930, subhead)

    d.text((1745, 1030), "1  NOTICE", font=subhead, fill=GREEN)
    sticky(d, 1745, 1100, "needs protein", YELLOW)
    sticky(d, 1745, 1230, "not filling", YELLOW)
    arrow(d, 2020, 1190, 2160, 1190, GREEN)

    d.text((2185, 1030), "2  GROUP", font=subhead, fill=GREEN)
    rounded(d, (2180, 1090, 2565, 1390), BG, GREEN, 4, 22)
    sticky(d, 2250, 1135, "needs protein", YELLOW)
    sticky(d, 2250, 1260, "not filling", YELLOW)
    d.line((2205, 1370, 2540, 1370), fill=GREEN, width=6)
    arrow(d, 2595, 1190, 2715, 1190, GREEN)

    d.text((2730, 1030), "3  NAME", font=subhead, fill=GREEN)
    rounded(d, (2715, 1110, 3030, 1365), BG, GREEN, 5, 30)
    # Simple lightbulb icon.
    d.ellipse((2805, 1140, 2940, 1275), outline=GREEN, width=10)
    d.rectangle((2845, 1260, 2900, 1310), fill=GREEN)
    text_center(d, "SATIETY", 2872, 1320, font(31, True), GREEN)

    rounded(d, (1755, 1640, 3020, 1800), BG, GREEN, 4, 24)
    text_center(d, "Question answered: What ideas emerge from the data?", 2387, 1682, font(33, True))
    text_center(d, "LET THE DATA SUGGEST THE NAMES", 2387, 1740, font(29, True), GREEN)

    # Bottom memory hook.
    text_center(d, "In short: deductive = labels first   •   inductive = observations first", 1600, 1920, font(37, True))
    im.save(OUTPUT, dpi=(300, 300))
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
