"""
Main figure: Theme accumulation across focus groups.

    py analysis/figures/render_inductive_theme_accumulation_main.py

Reads the frozen curve artefacts and writes the figure plus the CSV of every plotted
value. No API call, no recomputation of any result.

PANEL A - percentage of the final observed repertoire accumulated.
Two rules shape it:
1. Percentages are computed WITHIN one study realisation and only then summarised across
   realisations. Replicates are never pooled before a percentage is taken.
2. Q4 ends at four focus groups. When the five questions are combined, Q4 contributes its
   position-4 value again at position 5 - it holds its endpoint rather than being dropped
   or extrapolated.
The combined quantity is a SUM OF QUESTION-SPECIFIC REPERTOIRE ENDPOINTS within each
study realisation. It is not a count of distinct themes in the study: cluster ids belong
to a different taxonomy for each question.

PANEL B - final classified repertoire per guide question. Endpoints are read straight
from `inductive_endpoints_by_replicate.csv`, the authoritative endpoint table, and
cross-checked against the curve JSON. Synthetic ranges are min-max across three study
realisations and are deliberately NOT connected across questions: joining them would
read as a confidence band, which they are not.
"""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_ROOT = Path(__file__).resolve().parents[2]
_CURVES = _ROOT / "analysis/production_evaluation/inductive_curves"
_OUT_PNG = Path(__file__).resolve().parent / "inductive_theme_accumulation_main.png"
_OUT_CSV = Path(__file__).resolve().parent / "inductive_theme_accumulation_main.csv"

SCENARIO = "CANONICAL_RESOLVED_LOWER"
CONDITIONS = ("human", "enriched", "demographics-only")
N_REP = {"human": 1, "enriched": 3, "demographics-only": 3}

# Short titles taken verbatim from the literal moderator headers in the human
# transcripts. Nothing here is invented.
GUIDE_TITLES = {
    "1": "Favourite place\nwith male friends",
    "2": "How you decide\nwhat to eat",
    "3": "Whether gender\ninfluences\nwhat you eat",
    "4": "What would need\nto change to go\nplant-based",
    "5": "What might make\nplant-based foods\nmore appealing",
}

# Shared condition palette used in level1_thematic_fidelity_by_focus_group.
COL = {"human": "#52525B", "enriched": "#176B87", "demographics-only": "#D27D2D"}
FILL = {"enriched": "#D8E9EE", "demographics-only": "#F4E4D3"}
DRAW = ("demographics-only", "enriched", "human")   # human last, never hidden

W, H = 1900, 760
B_YMAX = 12          # headroom above the largest endpoint (10)


def _font(sz, bold=False):
    for p in ([r"C:\Windows\Fonts\arialbd.ttf"] if bold else []) + [
            r"C:\Windows\Fonts\arial.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def _wrap(d, text, font, width):
    lines, line = [], ""
    for w in text.split():
        t = (line + " " + w).strip()
        if d.textbbox((0, 0), t, font=font)[2] > width:
            lines.append(line)
            line = w
        else:
            line = t
    lines.append(line)
    return lines


def load():
    return json.loads((_CURVES / "inductive_curves_v2_full.json").read_text(
        encoding="utf-8"))[SCENARIO]


def endpoints_by_question():
    """
    Panel B's source of truth: the authoritative endpoint table, not the figure script.
    Cross-checked against the curve JSON so the two can never drift apart silently.
    """
    rows = [r for r in csv.DictReader(
        (_CURVES / "inductive_endpoints_by_replicate.csv").open(encoding="utf-8"))
        if r["scenario"] == SCENARIO]
    by = {}
    for q in "12345":
        by[q] = {}
        for cond in CONDITIONS:
            order = ["human"] if cond == "human" else ["R1", "R2", "R3"]
            m = {r["replicate"]: int(r["endpoint"]) for r in rows
                 if r["question"] == q and r["condition"] == cond}
            vals = [m[k] for k in order]
            by[q][cond] = {"values": vals, "median": statistics.median(vals),
                           "min": min(vals), "max": max(vals)}

    L = load()
    for q in "12345":
        for cond in CONDITIONS:
            src = [r["endpoint"] for r in L[q][cond]["realisations"]]
            if by[q][cond]["values"] != src:
                raise ValueError(f"Q{q} {cond}: endpoint CSV {by[q][cond]['values']} "
                                 f"does not match the curve JSON {src}")
    return by


def percentage_curves(L):
    """
    Per realisation: cumulative combined repertoire as a percentage of that same
    realisation's endpoint. Q4 holds its position-4 value at position 5.
    """
    out = {}
    for cond in CONDITIONS:
        per_rep = []
        for i in range(N_REP[cond]):
            cum = []
            for pos in range(5):
                tot = 0.0
                for q in "12345":
                    r = L[q][cond]["realisations"][i]
                    v = r["mean_cumulative_by_position"]
                    tot += v[min(pos, len(v) - 1)]      # Q4 holds its endpoint
                cum.append(tot)
            ep = sum(L[q][cond]["realisations"][i]["endpoint"] for q in "12345")
            per_rep.append([100.0 * c / ep for c in cum])
        out[cond] = per_rep
    return out


def final_increments(L):
    """Retained in the CSV for use in the external caption and narrative."""
    out = {}
    for q in "12345":
        out[q] = {}
        for cond in CONDITIONS:
            vals = [r["mean_new_at_position"][-1]
                    for r in L[q][cond]["realisations"]]
            out[q][cond] = {"values": vals, "median": statistics.median(vals),
                            "min": min(vals), "max": max(vals)}
    return out


def _panel_a(d, pct):
    ax, ay, aw, ah = 150, 190, 700, 380
    d.text((ax - 60, ay - 62), "A   Cumulative share of final repertoire",
           fill="#111827", font=_font(24, True))
    d.rectangle([ax, ay, ax + aw, ay + ah], outline="#cbd5e1")
    for v in range(0, 101, 20):
        y = ay + ah - ah * v / 100
        d.line([ax, y, ax + aw, y], fill="#f1f5f9")
        d.text((ax - 46, y - 9), f"{v}%", fill="#64748b", font=_font(15))
    for k in range(5):
        x = ax + aw * k / 4
        d.text((x - 5, ay + ah + 12), str(k + 1), fill="#64748b", font=_font(16))
    d.text((ax + aw / 2 - 80, ay + ah + 42), "Number of focus groups",
           fill="#334155", font=_font(18, True))

    for cond in DRAW:
        reps = pct[cond]
        px = [ax + aw * i / 4 for i in range(5)]
        if len(reps) > 1:
            hi = [max(r[i] for r in reps) for i in range(5)]
            lo = [min(r[i] for r in reps) for i in range(5)]
            up = [(px[i], ay + ah - ah * hi[i] / 100) for i in range(5)]
            dn = [(px[i], ay + ah - ah * lo[i] / 100) for i in range(5)]
            d.polygon(up + dn[::-1], fill=FILL[cond])
    for cond in DRAW:
        reps = pct[cond]
        med = [statistics.median(r[i] for r in reps) for i in range(5)]
        px = [ax + aw * i / 4 for i in range(5)]
        pts = [(px[i], ay + ah - ah * med[i] / 100) for i in range(5)]
        d.line(pts, fill=COL[cond], width=4 if cond == "human" else 3)
        for p in pts:
            r_ = 6 if cond == "human" else 5
            d.ellipse([p[0] - r_, p[1] - r_, p[0] + r_, p[1] + r_],
                      fill=COL[cond], outline="white")

def _panel_b(d, ends):
    bx, by, bw, bh = 1010, 190, 760, 380
    d.text((bx - 60, by - 62), "B   Final repertoire by guide question",
           fill="#111827", font=_font(24, True))
    d.text((bx, by - 28), "Classified clusters", fill="#475569", font=_font(16))
    d.rectangle([bx, by, bx + bw, by + bh], outline="#cbd5e1")
    for v in range(0, B_YMAX + 1, 2):
        y = by + bh - bh * v / B_YMAX
        d.line([bx, y, bx + bw, y], fill="#f1f5f9")
        d.text((bx - 34, y - 9), str(v), fill="#64748b", font=_font(15))

    slot = bw / 5
    offs = {"human": -34, "enriched": 0, "demographics-only": 34}

    def _xy(qi, cond, value):
        return (bx + slot * (qi + 0.5) + offs[cond],
                by + bh - bh * value / B_YMAX)

    # The human line is connected across questions: its question-to-question variation
    # is the finding. Synthetic points stay unconnected so no reader can mistake the
    # min-max ranges for an interval estimate.
    human_pts = [_xy(qi, "human", ends[q]["human"]["median"])
                 for qi, q in enumerate("12345")]
    d.line(human_pts, fill=COL["human"], width=3)

    for qi, q in enumerate("12345"):
        for cond in CONDITIONS:
            s = ends[q][cond]
            if s["max"] > B_YMAX:
                raise ValueError(f"Q{q} {cond}: {s['max']} exceeds the axis")
            x = _xy(qi, cond, 0)[0]
            if len(s["values"]) > 1:
                y1 = _xy(qi, cond, s["max"])[1]
                y2 = _xy(qi, cond, s["min"])[1]
                d.line([x, y1, x, y2], fill=COL[cond], width=3)
                d.line([x - 7, y1, x + 7, y1], fill=COL[cond], width=3)
                d.line([x - 7, y2, x + 7, y2], fill=COL[cond], width=3)
            y = _xy(qi, cond, s["median"])[1]
            d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=COL[cond], outline="white",
                      width=2)

        cx = bx + slot * (qi + 0.5)
        d.text((cx - 12, by + bh + 12), f"Q{q}", fill="#111827", font=_font(18, True))
        for li, line in enumerate(GUIDE_TITLES[q].split("\n")):
            tw = d.textbbox((0, 0), line, font=_font(13))[2]
            # Adjacent question titles must not touch: a label wider than its slot would
            # run into the neighbouring question and misattribute the caption.
            if tw > slot - 10:
                raise ValueError(f"Q{q} title line {line!r} is {tw:.0f}px wide, "
                                 f"slot is {slot:.0f}px")
            d.text((cx - tw / 2, by + bh + 38 + li * 17), line, fill="#64748b",
                   font=_font(13))

def render(out_png: Path = _OUT_PNG, out_csv: Path = _OUT_CSV):
    """Draw the figure and emit every plotted value. Paths are parameters so tests can
    render into tmp_path instead of rewriting the committed artefacts."""
    L = load()
    pct = percentage_curves(L)
    ends = endpoints_by_question()
    inc = final_increments(L)

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((70, 26), "Theme accumulation across focus groups",
           fill="#111827", font=_font(40, True))

    _panel_a(d, pct)
    _panel_b(d, ends)

    # ----------------------------------------------------------------- legend
    ly, lx = 700, 150
    for cond, lab in (("human", "Human"),
                      ("enriched", "Enriched (median)"),
                      ("demographics-only", "Demographics-only (median)")):
        d.line([lx, ly, lx + 46, ly], fill=COL[cond], width=4)
        d.ellipse([lx + 18, ly - 6, lx + 30, ly + 6], fill=COL[cond], outline="white")
        d.text((lx + 58, ly - 11), lab, fill="#334155", font=_font(18))
        lx += 420
    d.text((lx, ly - 11), "Range = R1\u2013R3", fill="#64748b", font=_font(15))
    img.save(out_png)

    # ------------------------------------------------------------------- CSV
    rows = []
    for cond in CONDITIONS:
        for i, rep in enumerate(pct[cond]):
            for pos, v in enumerate(rep, start=1):
                rows.append({"panel": "A", "condition": cond,
                             "realisation": "single" if cond == "human"
                             else f"R{i + 1}",
                             "position": pos, "metric": "pct_of_final_repertoire",
                             "value": round(v, 4)})
    for q in "12345":
        for cond in CONDITIONS:
            s = ends[q][cond]
            for i, v in enumerate(s["values"]):
                rows.append({"panel": "B", "condition": cond,
                             "realisation": "single" if cond == "human"
                             else f"R{i + 1}",
                             "position": f"Q{q}",
                             "metric": "final_classified_clusters", "value": v})
            rows.append({"panel": "B", "condition": cond, "realisation": "median",
                         "position": f"Q{q}",
                         "metric": "final_classified_clusters",
                         "value": round(s["median"], 4)})
    for q in "12345":
        for cond in CONDITIONS:
            s = inc[q][cond]
            for i, v in enumerate(s["values"]):
                rows.append({"panel": "caption_table", "condition": cond,
                             "realisation": "single" if cond == "human"
                             else f"R{i + 1}",
                             "position": f"Q{q}",
                             "metric": "new_clusters_final_pos", "value": round(v, 4)})
            rows.append({"panel": "caption_table", "condition": cond,
                         "realisation": "median", "position": f"Q{q}",
                         "metric": "new_clusters_final_pos",
                         "value": round(s["median"], 4)})
    with Path(out_csv).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return Path(out_png), Path(out_csv), pct, ends, inc


if __name__ == "__main__":
    png, csvp, pct, ends, inc = render()
    print("figure:", png.name)
    print("values:", csvp.name)
    for cond in CONDITIONS:
        p3 = [round(r[2], 1) for r in pct[cond]]
        p4 = [round(r[3], 1) for r in pct[cond]]
        print(f"  A {cond:18s} after 3 FGs {p3}   after 4 FGs {p4}")
    for q in "12345":
        parts = [f"{c.split('-')[0]:8s} {ends[q][c]['values']} med "
                 f"{ends[q][c]['median']:g}" for c in CONDITIONS]
        print(f"  B Q{q} " + " | ".join(parts))
