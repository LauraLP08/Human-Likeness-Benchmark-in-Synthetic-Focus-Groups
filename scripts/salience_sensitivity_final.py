"""
Cross-model salience sensitivity, completed, and the three-panel recurrence figure.

    py scripts/salience_sensitivity_final.py

Recomputes all 30 Kendall tau-b values under ORIGINAL/LOWER, MID and UPPER, computes the
recurrence sensitivity ORIGINAL vs CONTESTED_AS_PRESENT, and reports every
undefined -> defined and defined -> undefined transition explicitly.

  * ORIGINAL / LOWER remains the PRIMARY result and is not modified.
  * Unresolved cells enter NO treatment, in either direction.
  * The figure is written to a NEW file. The existing heatmap is not replaced.
  * The OCA human adjudication is kept out of this figure entirely — it is a separate,
    human-adjudicated sensitivity and mixing the two would misrepresent both.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import salience_hierarchy as sh      # noqa: E402
import absence_audit_rules as R      # noqa: E402
import absence_audit_stage1 as S1    # noqa: E402

_PE = _ROOT / "analysis/production_evaluation"
_AUD = _PE / "salience_absence_audit"
_OUT = _AUD

TREATMENTS = ("ORIGINAL_LOWER", "MID", "UPPER")
PRIMARY = "ORIGINAL_LOWER"


def contested_cells() -> list[dict]:
    b = json.loads((_AUD / "absence_audit_complete.json").read_text(encoding="utf-8"))
    return b["salience_cells_that_would_change"]


def _key(doc_key: str, code: str, rows_by_doc: dict):
    """Map a doc_key to the (condition, fg, rep) key salience_hierarchy uses."""
    meta = rows_by_doc[doc_key]
    rep = "human" if meta["side"] == "human" else str(
        meta["canonical_replication_index"])
    return (meta["condition"], meta["fg"], rep, code)


def apply_treatment(P, R, cells, rows_by_doc, treatment: str):
    """
    Contested absences are given a reach under MID/UPPER. Unresolved cells are not in
    `cells` at all and therefore enter no treatment.
    """
    P, R = deepcopy(P), deepcopy(R)
    if treatment == PRIMARY:
        return P, R, 0
    n = 0
    for c in cells:
        k = _key(c["doc_key"], c["subtheme_id"], rows_by_doc)
        reach = c["MID_reach"] if treatment == "MID" else c["UPPER_reach"]
        P[k]["present"] = "True"
        P[k]["voiced_by_n"] = str(round(reach * c["n_participants"]))
        R[k] = {**P[k], "voiced_by_n": str(round(reach * c["n_participants"])),
                "participants_n": str(c["n_participants"]), "reach": str(reach)}
        n += 1
    return P, R, n


def build() -> dict:
    codes, P0, R0 = sh.load()
    cells = contested_cells()

    rows_by_doc = {}
    for r in csv.DictReader(
            (_PE / "results/thematic_code_presence_long.csv").open(encoding="utf-8")):
        k = f"human::{r['fg']}" if r["side"] == "human" else r["physical_run"]
        rows_by_doc[k] = {"side": r["side"], "condition": r["condition"],
                          "fg": r["fg"], "canonical_replication_index":
                              r["canonical_replication_index"]}

    per_treatment, applied = {}, {}
    for t in TREATMENTS:
        P, R, n = apply_treatment(P0, R0, cells, rows_by_doc, t)
        per_treatment[t] = sh.group_level(codes, P, R)
        applied[t] = n

    base = {(r["fg"], r["condition"], r["canonical_replication_index"]): r
            for r in per_treatment[PRIMARY]}
    if len(base) != 30:
        raise RuntimeError(f"{len(base)} runs, expected 30")

    tau_table, transitions = [], []
    for key, b in sorted(base.items()):
        fg, cond, rep = key
        row = {"fg": fg, "condition": cond, "canonical_replication_index": rep}
        for t in TREATMENTS:
            r = next(x for x in per_treatment[t]
                     if (x["fg"], x["condition"], x["canonical_replication_index"])
                     == key)
            row[f"tau_b_{t}"] = r["kendall_tau_b"]
            row[f"undefined_reason_{t}"] = r["undefined_reason"]
        row["changed_MID"] = row["tau_b_MID"] != row["tau_b_ORIGINAL_LOWER"]
        row["changed_UPPER"] = row["tau_b_UPPER"] != row["tau_b_ORIGINAL_LOWER"]
        tau_table.append(row)

        for t in ("MID", "UPPER"):
            was, now = row["tau_b_ORIGINAL_LOWER"], row[f"tau_b_{t}"]
            if was is None and now is not None:
                transitions.append({"fg": fg, "condition": cond,
                                    "canonical_replication_index": rep,
                                    "treatment": t,
                                    "transition": "UNDEFINED_TO_DEFINED",
                                    "was_undefined_because":
                                        row["undefined_reason_ORIGINAL_LOWER"],
                                    "becomes": now})
            elif was is not None and now is None:
                transitions.append({"fg": fg, "condition": cond,
                                    "canonical_replication_index": rep,
                                    "treatment": t,
                                    "transition": "DEFINED_TO_UNDEFINED",
                                    "was": was,
                                    "now_undefined_because":
                                        row[f"undefined_reason_{t}"]})

    n_def = {t: sum(1 for r in tau_table if r[f"tau_b_{t}"] is not None)
             for t in TREATMENTS}

    rec = json.loads((_AUD / "absence_audit_complete.json").read_text(
        encoding="utf-8"))["across_group_recurrence_sensitivity"]

    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": "CROSS_MODEL_SALIENCE_SENSITIVITY",
        "primary": PRIMARY,
        "primary_unmodified": True,
        "unresolved_cells_enter_any_treatment": False,
        "n_contested_cells_applied": applied,
        "n_runs": len(tau_table),
        "n_defined_by_treatment": n_def,
        "tau_b_table": tau_table,
        "n_changed_MID": sum(1 for r in tau_table if r["changed_MID"]),
        "n_changed_UPPER": sum(1 for r in tau_table if r["changed_UPPER"]),
        "transitions": transitions,
        "n_undefined_to_defined": sum(1 for t in transitions
                                      if t["transition"] == "UNDEFINED_TO_DEFINED"),
        "n_defined_to_undefined": sum(1 for t in transitions
                                      if t["transition"] == "DEFINED_TO_UNDEFINED"),
        "recurrence": rec,
        "oca_kept_separate": ("the OCA human adjudication is not applied in this "
                              "analysis or in the figure; it is a separate "
                              "human-adjudicated sensitivity"),
        "existing_heatmap_replaced": False,
    }


# ------------------------------------------------------------------ figure
def figure(b: dict, path: Path) -> None:
    """Three panels, drawn with PIL. Written to a NEW file."""
    from PIL import Image, ImageDraw, ImageFont

    rec = b["recurrence"]["rows"]
    conds = ["human", "enriched", "demographics-only"]
    codes = sorted({r["subtheme_id"] for r in rec})
    cols = []
    for c in conds:
        reps = sorted({r["canonical_replication_index"] for r in rec
                       if r["condition"] == c}, key=lambda x: str(x))
        for rp in reps:
            cols.append((c, rp))

    orig = {(r["condition"], r["canonical_replication_index"], r["subtheme_id"]):
            r["n_fgs_original"] for r in rec}
    flip = {(r["condition"], r["canonical_replication_index"], r["subtheme_id"]):
            r["n_fgs_contested_as_present"] for r in rec}

    CELL, PAD, TOP, LEFT = 34, 26, 78, 92
    PANEL_W = LEFT + len(cols) * CELL + PAD
    PANEL_H = TOP + len(codes) * CELL + 54
    W, H = PANEL_W * 3, PANEL_H + 46
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("arial.ttf", 11)
        fb = ImageFont.truetype("arialbd.ttf", 13)
        ft = ImageFont.truetype("arial.ttf", 9)
    except OSError:
        f = fb = ft = ImageFont.load_default()

    def blue(v, vmax=5):
        t = 0 if vmax == 0 else min(1.0, v / vmax)
        return (int(247 - 150 * t), int(251 - 120 * t), int(255 - 60 * t))

    def red(v, vmax=2):
        if v <= 0:
            return (245, 245, 245)
        t = min(1.0, v / vmax)
        return (255, int(235 - 150 * t), int(230 - 160 * t))

    def panel(ox, title, sub, getval, colour, vmax):
        d.text((ox + 12, 14), title, fill="black", font=fb)
        d.text((ox + 12, 34), sub, fill=(90, 90, 90), font=ft)
        for j, (c, rp) in enumerate(cols):
            lab = "H" if c == "human" else ("E" if c == "enriched" else "D")
            lab += "" if c == "human" else f"R{rp}"
            d.text((ox + LEFT + j * CELL + 6, TOP - 16), lab, fill="black", font=ft)
        for i, code in enumerate(codes):
            d.text((ox + 12, TOP + i * CELL + 10), code, fill="black", font=f)
            for j, (c, rp) in enumerate(cols):
                v = getval(c, rp, code)
                x, y = ox + LEFT + j * CELL, TOP + i * CELL
                d.rectangle([x, y, x + CELL - 2, y + CELL - 2],
                            fill=colour(v, vmax), outline=(215, 215, 215))
                if v:
                    d.text((x + CELL // 2 - 4, y + CELL // 2 - 7), str(v),
                           fill="black", font=f)

    panel(0, "A · Original Gemini-coded recurrence",
          "focus groups per subtheme, as coded",
          lambda c, rp, k: orig.get((c, rp, k), 0), blue, 5)
    panel(PANEL_W, "B · Cross-model CONTESTED_AS_PRESENT",
          "sensitivity treatment, not a result",
          lambda c, rp, k: flip.get((c, rp, k), 0), blue, 5)
    panel(PANEL_W * 2, "C · Difference (B − A)",
          "added focus-group counts",
          lambda c, rp, k: flip.get((c, rp, k), 0) - orig.get((c, rp, k), 0), red, 2)

    d.text((12, H - 34),
           "SENSITIVITY FIGURE — not a result. Panel A is the primary coding and is "
           "unchanged. Panel B applies the 16 cross-model contested absences; the 64 "
           "unresolved cells enter no treatment.",
           fill=(70, 70, 70), font=ft)
    d.text((12, H - 20),
           "The OCA human adjudication is NOT applied in this figure. "
           "H = human, E = enriched, D = demographics-only, R = replicate.",
           fill=(70, 70, 70), font=ft)
    img.save(path)


def main() -> int:
    b = build()
    S1._atomic(_OUT / "salience_sensitivity_final.json", b)

    with (_OUT / "kendall_tau_b_by_treatment.csv").open(
            "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(b["tau_b_table"][0]))
        w.writeheader()
        w.writerows(b["tau_b_table"])
    if b["transitions"]:
        with (_OUT / "tau_b_definedness_transitions.csv").open(
                "w", encoding="utf-8", newline="") as f:
            keys = sorted({k for t in b["transitions"] for k in t})
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(b["transitions"])

    fig = _OUT / "recurrence_sensitivity_three_panel.png"
    figure(b, fig)

    print("=== cross-model salience sensitivity ===")
    print(f"  primary {b['primary']} (unmodified: {b['primary_unmodified']})")
    print(f"  contested cells applied {b['n_contested_cells_applied']}")
    print(f"  unresolved enter a treatment: "
          f"{b['unresolved_cells_enter_any_treatment']}")
    print(f"  defined tau-b by treatment {b['n_defined_by_treatment']}")
    print(f"  changed under MID {b['n_changed_MID']}/30   "
          f"under UPPER {b['n_changed_UPPER']}/30")
    print(f"\n  undefined -> defined  {b['n_undefined_to_defined']}")
    print(f"  defined -> undefined  {b['n_defined_to_undefined']}")
    for t in b["transitions"]:
        if t["transition"] == "UNDEFINED_TO_DEFINED":
            print(f"    {t['fg']} {t['condition']:20s} R"
                  f"{t['canonical_replication_index']} {t['treatment']:6s} "
                  f"{t['was_undefined_because']} -> {t['becomes']}")
        else:
            print(f"    {t['fg']} {t['condition']:20s} R"
                  f"{t['canonical_replication_index']} {t['treatment']:6s} "
                  f"{t['was']} -> undefined ({t['now_undefined_because']})")

    print("\n  tau-b that move (ORIGINAL/LOWER -> MID -> UPPER):")
    for r in b["tau_b_table"]:
        if r["changed_MID"] or r["changed_UPPER"]:
            def s(x):
                return "undef" if x is None else f"{x:+.4f}"
            print(f"    {r['fg']} {r['condition']:20s} R"
                  f"{r['canonical_replication_index']}   "
                  f"{s(r['tau_b_ORIGINAL_LOWER'])} -> {s(r['tau_b_MID'])} -> "
                  f"{s(r['tau_b_UPPER'])}")
    print(f"\n  figure written: {fig.name} (existing heatmap replaced: "
          f"{b['existing_heatmap_replaced']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
