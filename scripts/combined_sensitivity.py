"""
Combined thematic-salience sensitivity: blinded cross-model audit + human coding review.

    py scripts/combined_sensitivity.py

Emits `combined_recurrence_sensitivity.csv` with three columns per cell:

    ORIGINAL      the primary Gemini coding, unchanged
    CROSS_MODEL   the 16 ABSENCE_CONTESTED cells treated as present
    COMBINED      CROSS_MODEL plus the human coding review's reclassification of
                  FG4 demographics-only R1 from A.1 to A.3

WHY THIS IS COMPUTED OVER SETS
------------------------------
Across-group recurrence counts DISTINCT FOCUS GROUPS. It cannot be produced by adding or
subtracting one from a previous count, because two independent sources may point at the
SAME focus group.

That is exactly what happens here. The blinded auditor contested A.3 in
`macho_meals_fg4_demoonly_run01`, and the human coding review independently proposes A.3
for that same run. Incrementing the cross-model count would count fg4 twice and report
A.3 at 4 focus groups in demographics-only R1 when the correct figure is 3. The
convergence of two independent reviews on one cell is a finding, not an extra group.

Every count here is therefore the cardinality of a set of focus-group ids.

The primary analysis is unchanged: this module writes a sensitivity artefact only.
NO API CALLS.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

_PE = _ROOT / "analysis/production_evaluation"
_AUD = _PE / "salience_absence_audit"
_OCA = _PE / "open_coding_adjudication"
_OUT = _AUD / "combined_recurrence_sensitivity.csv"

# The human coding review's reclassification, as adjudicated.
RECLASS_RUN = "macho_meals_fg4_demoonly_run01"
RECLASS_REMOVE = "A.1"      # explicit human verdict: the evidence does not support A.1
RECLASS_ADD = "A.3"         # the reviewer-proposed alternative

TREATMENTS = ("ORIGINAL", "CROSS_MODEL", "COMBINED")


def build() -> dict:
    pres = list(csv.DictReader(
        (_PE / "results/thematic_code_presence_long.csv").open(encoding="utf-8")))
    aud = json.loads((_AUD / "absence_audit_complete.json").read_text(encoding="utf-8"))
    oca = json.loads((_OCA / "oca_integration.json").read_text(encoding="utf-8"))

    if oca["import"]["verdict"] != "DOES_NOT_SUPPORT_A1":
        raise RuntimeError("the human coding review does not carry the A.1 verdict")
    if oca["import"]["alternative_subtheme"] != RECLASS_ADD:
        raise RuntimeError("the proposed alternative is not A.3")

    contested = {(c["doc_key"], c["subtheme_id"])
                 for c in aud["salience_cells_that_would_change"]}

    cells = {}
    for r in pres:
        doc = (f"human::{r['fg']}" if r["side"] == "human" else r["physical_run"])
        rep = r["canonical_replication_index"] or "human"
        key = (r["condition"], rep, r["subtheme_id"])
        present = (r["present"] == "True" and r["quote_verified"] == "True")
        cells.setdefault(key, []).append(
            {"fg": r["fg"], "doc_key": doc, "subtheme_id": r["subtheme_id"],
             "present": present})

    rows, convergence = [], []
    for key in sorted(cells, key=lambda k: (k[0], str(k[1]), k[2])):
        cond, rep, code = key
        orig, cross, comb = set(), set(), set()
        for c in cells[key]:
            p = c["present"]
            orig.update({c["fg"]} if p else set())

            x = p or (c["doc_key"], code) in contested
            cross.update({c["fg"]} if x else set())

            y = x
            if c["doc_key"] == RECLASS_RUN:
                if code == RECLASS_REMOVE:
                    y = False
                elif code == RECLASS_ADD:
                    y = True
                    if (c["doc_key"], code) in contested:
                        convergence.append(
                            {"doc_key": c["doc_key"], "subtheme_id": code,
                             "fg": c["fg"],
                             "note": ("the blinded auditor and the human coding review "
                                      "independently point at the same focus group; it "
                                      "is counted once")})
            comb.update({c["fg"]} if y else set())

        rows.append({
            "condition": cond, "canonical_replication_index": rep,
            "subtheme_id": code,
            "n_fgs_ORIGINAL": len(orig), "n_fgs_CROSS_MODEL": len(cross),
            "n_fgs_COMBINED": len(comb),
            "delta_cross_model": len(cross) - len(orig),
            "delta_combined": len(comb) - len(orig),
            "fgs_ORIGINAL": "|".join(sorted(orig)),
            "fgs_COMBINED": "|".join(sorted(comb)),
        })

    changed_cross = sum(1 for r in rows if r["delta_cross_model"])
    changed_comb = sum(1 for r in rows if r["delta_combined"])
    return {"rows": rows, "n_rows": len(rows),
            "n_changed_cross_model": changed_cross,
            "n_changed_combined": changed_comb,
            "convergence": convergence,
            "counted_over_sets": True,
            "why_sets": ("recurrence counts distinct focus groups; incrementing a "
                         "previous count would double-count a focus group that two "
                         "independent reviews both point at"),
            "primary_unchanged": True}


def main() -> int:
    b = build()
    with _OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(b["rows"][0]))
        w.writeheader()
        w.writerows(b["rows"])

    print("=== combined recurrence sensitivity (set-based) ===")
    print(f"  rows {b['n_rows']}  changed under CROSS_MODEL {b['n_changed_cross_model']}"
          f"  changed under COMBINED {b['n_changed_combined']}")
    print("\n  the reclassified cell:")
    for r in b["rows"]:
        if (r["condition"], r["canonical_replication_index"]) == \
                ("demographics-only", "1") and r["subtheme_id"] in ("A.1", "A.3"):
            print(f"    {r['subtheme_id']:4s} ORIGINAL {r['n_fgs_ORIGINAL']}"
                  f"  CROSS_MODEL {r['n_fgs_CROSS_MODEL']}"
                  f"  COMBINED {r['n_fgs_COMBINED']}   [{r['fgs_COMBINED']}]")
    for c in b["convergence"]:
        print(f"\n  CONVERGENCE: {c['subtheme_id']} in {c['doc_key']} — {c['note']}")
    print(f"\n  written: {_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
