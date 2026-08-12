"""
Derivation and B+ evaluation from the researcher's completed matching workbook.

The workbook is READ ONLY and is never modified.

GATE STATUS
-----------
READY. The single cross-unit key on row 20 (U03::C09) was corrected by the researcher
under MATCHING_AMENDMENT_01: U02::M2 -> U03::M2, one cell, decision left UNCERTAIN and
reasoning untouched. No interpretation is applied to any row.

TAXONOMY OF UNCONFIRMED MACHINE THEMES
--------------------------------------
A machine theme with no confirmed match is NOT automatically "absent from the human
reference":

  CONFIRMED_UNLINKED_WITH_HUMAN_CANDIDATE - no confirmed match, but a human row named it
      while marking the correspondence UNCERTAIN. A human saw it and related it to her
      own theme; she did not settle the relation.
  PURE_MACHINE_ONLY - no confirmed match and no human candidate at all.

METHODOLOGICAL CONSTRAINTS FROM THE RESEARCHER
----------------------------------------------
Human coding asked for ONE representative quote per theme; the extractor could supply
several per theme. Quote counts are therefore NEVER comparable, and no metric here is
based on how many quotes either side cited. Quotes are used only to check groundedness.
Correspondence is decided by substantive equivalence of the claim — not by label equality
and not by quantity of evidence.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import emergent_matching_researcher as mr   # noqa: E402
import emergent_calibration_q3 as cal       # noqa: E402

_DIR = cal._DIR

# RESOLVED by MATCHING_AMENDMENT_01 (2026-08-02): the researcher confirmed the intended
# key was U03::M2 and authorised the one-cell correction. The gate is now READY and no
# interpretation is applied to any row. The rule is retained because it still governs
# what would happen to a future invalid candidate key.
INTERPRETATION = {
    "status": "NO_LONGER_APPLIED — resolved by MATCHING_AMENDMENT_01",
    "rule": "INVALID_CANDIDATE_KEY_ON_AN_UNCERTAIN_ROW_IS_DROPPED",
    "row": "U03::C09",
    "as_written": "U02::M2",
    "why_droppable_without_a_substantive_choice": (
        "the row is UNCERTAIN; candidate keys are optional there and count for nothing, "
        "so excluding an invalid one changes no match, no recall figure, no queue entry "
        "and no fusion/fragmentation finding"),
    "likely_intent_recorded_but_NOT_used": (
        "U03::M2 — same local id, wrong unit prefix; her reasoning clause 'could not "
        "tell the difference between wanting or being pressured' corresponds to "
        "U03::M2, and the sibling rows U02::C09 and U04::C09 both use their own unit's "
        "key. NOT substituted: confirm in one line."),
    "effect_on_results": "none — the row remains UNCERTAIN and unresolved either way",
}


def load():
    rows = mr.read_rows()
    res = json.loads((_DIR / "extraction_results_q3.json").read_text(encoding="utf-8"))
    ref = json.loads((_DIR / "human_reference_q3.json").read_text(encoding="utf-8"))
    themes = {cal.machine_key(u["unit_id"], t["machine_theme_id"]): t
              for u in res["results"] for t in u["themes"]}
    humans = {h["human_key"]: h for h in ref["union_reference"]}
    return rows, themes, humans


def derive() -> dict:
    rows, themes, humans = load()
    valid = {}
    for k in themes:
        valid.setdefault(k.split("::")[0], set()).add(k)

    confirmed: dict[str, list[str]] = {}
    candidates: dict[str, list[str]] = {}
    per_row, uncertain, dropped = [], [], []

    for r in rows:
        unit = str(r["unit_id"]).strip()
        hk = str(r["human_key"]).strip()
        dec = str(r["human_decision"]).strip()
        why = str(r.get("researcher_reasoning") or "").strip()
        raw = [k.strip() for k in
               str(r.get("matched_machine_keys") or "").split(";") if k.strip()]
        keys = [k for k in raw if k in valid.get(unit, set())]
        invalid = [k for k in raw if k not in valid.get(unit, set())]

        if invalid:
            if dec != "UNCERTAIN":
                raise RuntimeError(
                    f"{hk}: invalid key {invalid} on a {dec} row — that would be a "
                    f"substantive defect and cannot be interpreted away")
            dropped.append({"human_key": hk, "invalid_keys": invalid,
                            "decision": dec, "reasoning": why})

        if dec == "MATCHED":
            for k in keys:
                confirmed.setdefault(k, []).append(hk)
            rel = "one_to_one" if len(keys) == 1 else "one_to_many"
        elif dec == "NO_MATCH_HUMAN_ONLY":
            rel = "no_match_human_only"
        else:
            for k in keys:
                candidates.setdefault(k, []).append(hk)
            rel = "unresolved"
            uncertain.append({"unit_id": unit, "human_key": hk,
                              "candidate_machine_keys": keys,
                              "invalid_keys_dropped": invalid, "reasoning": why})

        per_row.append({"unit_id": unit, "human_key": hk, "decision": dec,
                        "confirmed_machine_keys": keys if dec == "MATCHED" else [],
                        "candidate_machine_keys": keys if dec == "UNCERTAIN" else [],
                        "relation": rel, "reasoning": why})

    all_machine = sorted(themes)
    linked = sorted(confirmed)
    unlinked = [k for k in all_machine if k not in confirmed]

    # TAXONOMY OF UNCONFIRMED THEMES.
    #
    # A machine theme with no confirmed match is not automatically "absent from the
    # human reference". If a human row named it while marking the correspondence
    # UNCERTAIN, a human DID see it and DID relate it to one of her own themes — she
    # simply did not settle the relation. Calling that "no human counterpart" would
    # misreport her judgement as an absence.
    with_candidate = {}
    for k in unlinked:
        humans = candidates.get(k, [])
        if humans:
            with_candidate[k] = sorted(humans)
    pure = [k for k in unlinked if k not in with_candidate]

    n_matched = sum(1 for r in per_row if r["decision"] == "MATCHED")
    n_human_only = sum(1 for r in per_row if r["decision"] == "NO_MATCH_HUMAN_ONLY")
    n_uncertain = len(uncertain)

    by_unit = {}
    for r in per_row:
        u = r["unit_id"]
        d = by_unit.setdefault(u, {"n_human": 0, "matched": 0, "human_only": 0,
                                   "uncertain": 0, "n_machine": len(valid.get(u, ())),
                                   "machine_linked": set()})
        d["n_human"] += 1
        d["matched"] += r["decision"] == "MATCHED"
        d["human_only"] += r["decision"] == "NO_MATCH_HUMAN_ONLY"
        d["uncertain"] += r["decision"] == "UNCERTAIN"
        for k in r["confirmed_machine_keys"]:
            d["machine_linked"].add(k)
    for u, d in by_unit.items():
        d["machine_linked"] = len(d["machine_linked"])
        d["recall"] = {"numerator": d["matched"], "denominator": d["n_human"]}
        d["precision"] = {"numerator": d["machine_linked"], "denominator": d["n_machine"]}

    return {
        "derived_utc": datetime.now(UTC).isoformat(),
        "workbook": mr._WB.name,
        "interpretation_applied": INTERPRETATION,
        "invalid_candidate_keys_dropped": dropped,

        "n_human_instances": len(per_row),
        "n_machine_themes": len(all_machine),
        "rows": per_row,

        "confirmed_links": {k: sorted(v) for k, v in sorted(confirmed.items())},
        "candidate_uncertain_links": {k: sorted(v)
                                      for k, v in sorted(candidates.items())},
        "human_only_instances": [r["human_key"] for r in per_row
                                 if r["decision"] == "NO_MATCH_HUMAN_ONLY"],
        "machine_themes_linked": linked,
        "machine_themes_unlinked": unlinked,
        "unconfirmed_theme_taxonomy": {
            "CONFIRMED_UNLINKED_WITH_HUMAN_CANDIDATE": with_candidate,
            "PURE_MACHINE_ONLY": pure,
            "rule": ("A = no confirmed match BUT named on a human UNCERTAIN row; a "
                     "human saw it and related it to her own theme without settling "
                     "the relation. It must NOT be described as absent from the human "
                     "reference. B = no confirmed match and no human candidate at all."),
        },
        "uncertain_rows": uncertain,

        "possible_fusion_one_machine_many_human": {
            k: sorted(v) for k, v in confirmed.items() if len(v) > 1},
        "possible_fragmentation_one_human_many_machine": {
            r["human_key"]: r["confirmed_machine_keys"] for r in per_row
            if len(r["confirmed_machine_keys"]) > 1},

        "coverage": {
            "recall_vs_union_reference": {
                "numerator_matched_human_instances": n_matched,
                "denominator_human_instances": len(per_row),
                "value": n_matched / len(per_row),
                "note": ("UNCERTAIN rows are NOT in the numerator; they are neither "
                         "correct nor incorrect until resolved"),
            },
            "strict_precision_vs_union_reference": {
                "numerator_machine_themes_linked": len(linked),
                "denominator_machine_themes": len(all_machine),
                "value": len(linked) / len(all_machine),
                "note": ("strict: a machine theme not linked to any human instance "
                         "counts against precision here even if it is later adjudicated "
                         "VALID_NOVEL_THEME"),
            },
            "human_only": {"count": n_human_only, "denominator": len(per_row)},
            "uncertain": {"count": n_uncertain, "denominator": len(per_row)},
        },
        "per_unit": by_unit,
        "metrics_exclude_quote_counts": (
            "Human coding asked for ONE representative quote per theme; the extractor "
            "could supply several. No metric here uses quote number, density or "
            "coverage. Quotes are used only for groundedness."),
    }


def main() -> int:
    out = derive()
    dst = _DIR / "matching_derivation_q3.json"
    tmp = dst.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()
    c = out["coverage"]
    print(f"human instances : {out['n_human_instances']}")
    print(f"machine themes  : {out['n_machine_themes']}")
    print(f"recall          : {c['recall_vs_union_reference']['numerator_matched_human_instances']}"
          f"/{c['recall_vs_union_reference']['denominator_human_instances']} = "
          f"{c['recall_vs_union_reference']['value']:.4f}")
    print(f"strict precision: {c['strict_precision_vs_union_reference']['numerator_machine_themes_linked']}"
          f"/{c['strict_precision_vs_union_reference']['denominator_machine_themes']} = "
          f"{c['strict_precision_vs_union_reference']['value']:.4f}")
    print(f"human-only      : {c['human_only']['count']}")
    print(f"uncertain       : {c['uncertain']['count']}")
    print(f"unlinked machine: {len(out['machine_themes_unlinked'])}")
    print(f"wrote {dst.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
