"""
Feasibility report for the Level 3 agent-fidelity analyses.

    py scripts/agent_fidelity_preflight.py

This runs BEFORE any metric. Its only job is to establish what the corpus can and cannot
support, so that a budget is chosen from the data rather than from a round number.

THE BINDING CONSTRAINT
----------------------
Every analysis here compares a participant against their fellow participants at the level
of ONE GUIDE QUESTION. That makes the unit of text a participant x question cell, and
human cells are small: the smallest holds 27 words. A 100-word budget at that level is
not viable on the human side, and a budget that only the synthetic sessions can meet
would compare five human focus groups against thirty synthetic ones on unequal text.

So the main budget is the LARGEST value at which all five human focus groups still
support the design, and a lower budget is run as sensitivity.

ELIGIBILITY - AND WHY THE OBVIOUS RULE HAD TO BE REJECTED
---------------------------------------------------------
The natural rule is STRICT_ALL_QUESTIONS: a participant counts only if they meet the
budget in EVERY question the document asked. It is balanced by construction and it is
what this module tried first.

It cannot be used. Synthetic participants are frequently silent in a question: across the
thirty synthetic sessions, most have ZERO, one or two participants present in all five
questions, against three or four in every human session. The strict rule would therefore
compare five human focus groups against roughly three synthetic documents - the synthetic
side, not the human side, collapses. That is the same defect the study has already ruled
out in the other direction, so the rule is reported and set aside.

PER_FOLD (main): a participant is eligible for the fold that holds out question q if they
meet the budget in q and in at least two other questions, so a profile can be built from
at least two questions. The eligible set varies by fold, which is why the chance baseline
is computed per fold rather than assumed.

A fold needs at least two eligible participants, otherwise there is nothing to
discriminate.

Human FG5 Q4 is NOT_ASKED_IN_FIELDWORK. It is not a fold, not a zero and not an
exclusion caused by the budget.

Offline. No API call.
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

import agent_fidelity_corpus as afc

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "analysis/production_evaluation/agent_fidelity"

BUDGETS = (20, 25, 30, 40, 50, 60, 75, 100, 150)
MIN_PARTICIPANTS_PER_FOLD = 2
MIN_PROFILE_QUESTIONS = 2


def cells_by_document(corpus):
    by = defaultdict(lambda: defaultdict(dict))
    for (d, q, p), rec in corpus["cells"].items():
        by[d][p][q] = rec
    return by


def strict_eligible(by_doc, doc_questions, budget):
    """Participants meeting the budget in every question the document asked."""
    out = {}
    for d, parts in by_doc.items():
        qs = doc_questions[d]
        out[d] = sorted(p for p, cells in parts.items()
                        if all(q in cells and cells[q]["n_words"] >= budget for q in qs))
    return out


def per_fold_eligible(by_doc, doc_questions, budget):
    """(doc, held-out question) -> participants eligible for that fold only."""
    out = {}
    for d, parts in by_doc.items():
        for q in doc_questions[d]:
            ok = []
            for p, cells in parts.items():
                if q not in cells or cells[q]["n_words"] < budget:
                    continue
                others = sum(1 for o in doc_questions[d]
                             if o != q and o in cells and cells[o]["n_words"] >= budget)
                if others >= MIN_PROFILE_QUESTIONS:
                    ok.append(p)
            out[(d, q)] = sorted(ok)
    return out


def build() -> dict:
    corpus = afc.build()
    leak = afc.leakage_report(corpus)
    by_doc = cells_by_document(corpus)
    doc_questions = {d: sorted(set(v["questions"])) for d, v in corpus["docs"].items()}
    cond = {d: v["condition"] for d, v in corpus["docs"].items()}

    # ---- absences that are not budget exclusions -------------------------
    silent = []
    for d, parts in by_doc.items():
        for p, cells in parts.items():
            for q in doc_questions[d]:
                if q not in cells:
                    silent.append({"doc": d, "participant": p, "question": q,
                                   "reason": "PARTICIPANT_SILENT_IN_THIS_QUESTION"})

    # ---- per-cell token table -------------------------------------------
    long_rows = []
    for (d, q, p), r in sorted(corpus["cells"].items()):
        long_rows.append({"doc_id": d, "condition": r["condition"], "fg": r["fg"],
                          "replicate": r["replicate"] or "human", "question": q,
                          "participant": p, "n_words": r["n_words"],
                          "n_turns": r["n_turns"],
                          "n_names_scrubbed": r["n_names_scrubbed"]})

    def _dist(vals):
        return {"n": len(vals), "min": min(vals), "p25": round(
            statistics.quantiles(vals, n=4)[0], 1) if len(vals) > 3 else None,
            "median": statistics.median(vals), "max": max(vals)}

    per_condition_cells = {c: _dist([r["n_words"] for r in long_rows
                                     if r["condition"] == c])
                           for c in afc.CONDITIONS}

    # ---- budget curve ----------------------------------------------------
    curve = {}
    for b in BUDGETS:
        strict = strict_eligible(by_doc, doc_questions, b)
        folds = {}
        for d, ps in strict.items():
            for q in doc_questions[d]:
                folds[(d, q)] = ps if len(ps) >= MIN_PARTICIPANTS_PER_FOLD else []
        pf = per_fold_eligible(by_doc, doc_questions, b)

        ok_folds = {k: v for k, v in pf.items()
                    if len(v) >= MIN_PARTICIPANTS_PER_FOLD}

        by_cond = {}
        for c in afc.CONDITIONS:
            docs_c = [d for d in strict if cond[d] == c]
            mine = {k: v for k, v in ok_folds.items() if cond[k[0]] == c}
            fgs = sorted({d.split("::")[1] for d, _ in mine})
            total_folds = sum(len(doc_questions[d]) for d in docs_c)
            by_cond[c] = {
                "n_documents_total": len(docs_c),
                "n_documents_with_an_eligible_fold": len({d for d, _ in mine}),
                "focus_groups_covered": fgs,
                "n_focus_groups_covered": len(fgs),
                "n_folds_total": total_folds,
                "n_folds_eligible": len(mine),
                "median_participants_per_eligible_fold": (
                    statistics.median([len(v) for v in mine.values()]) if mine else 0),
                # The rule that had to be rejected, kept visible.
                "strict_rule_n_documents_with_two_eligible_participants": sum(
                    1 for d in docs_c if len(strict[d]) >= MIN_PARTICIPANTS_PER_FOLD),
                "strict_rule_eligible_participants_per_document": {
                    d: len(strict[d]) for d in sorted(docs_c)},
            }
        curve[b] = {
            "budget_words": b,
            "by_condition": by_cond,
            "all_human_folds_retained":
                by_cond["human"]["n_folds_eligible"]
                == by_cond["human"]["n_folds_total"],
            "five_focus_groups_in_every_condition": all(
                by_cond[c]["n_focus_groups_covered"] == 5 for c in afc.CONDITIONS),
        }

    # The main budget is the largest that costs no human fold at all. A budget that
    # silently drops human folds would let the human side be represented by whichever
    # participants happened to talk most.
    viable = [b for b in BUDGETS
              if curve[b]["all_human_folds_retained"]
              and curve[b]["five_focus_groups_in_every_condition"]]
    main_budget = max(viable) if viable else None
    lower = [b for b in BUDGETS if main_budget and b <= main_budget // 2]
    sensitivity_budget = max(lower) if lower else None
    thin = [b for b in BUDGETS
            if main_budget and b > main_budget
            and curve[b]["five_focus_groups_in_every_condition"]]

    out = {
        "built_utc": datetime.now(UTC).isoformat(),
        "id": "AGENT_FIDELITY_PREFLIGHT",
        "status": "FEASIBILITY_ONLY_NO_METRICS_COMPUTED",
        "no_api_calls": True,
        "no_new_human_tasks": True,
        "property_under_study": "LEXICALLY_INDIVIDUALISABLE_AGENT_VOICE",
        "property_definition": (
            "the capacity to distinguish one participant's text from that of their "
            "fellow participants, and to recognise the same participant across "
            "different guide questions"),
        "unit_of_text": "participant x guide question",
        "unit_of_comparison": "focus group; the three synthetic replicates estimate "
                              "generator variability and are never pooled into one FG",
        "source_segmentation":
            "analysis/production_evaluation/final/inductive_segments.json",
        "n_documents": len(by_doc),
        "n_cells": len(corpus["cells"]),
        "all_units_reconcile_against_segmentation": corpus["all_units_reconcile"],
        "leakage": {k: v for k, v in leak.items()
                    if k in ("n_cells", "n_name_leaks", "n_identifier_leaks",
                             "n_turn_id_leaks", "clean")},
        "n_name_mentions_scrubbed": sum(r["n_names_scrubbed"]
                                        for r in corpus["cells"].values()),
        "not_asked_in_fieldwork": [
            {"condition": c, "fg": f, "question": q,
             "status": "NOT_ASKED_IN_FIELDWORK",
             "note": "an absence in the field, never a zero and never a fold"}
            for (c, f, q) in sorted(afc.NOT_ASKED_IN_FIELDWORK)],
        "participants_silent_in_a_question": silent,
        "n_participants_silent_in_a_question": len(silent),
        "cell_word_distribution_by_condition": per_condition_cells,
        "eligibility_rules": {
            "main": "PER_FOLD",
            "rejected": "STRICT_ALL_QUESTIONS",
            "why_strict_rejected": (
                "synthetic participants are frequently silent in a question: most "
                "synthetic sessions have zero, one or two participants present in all "
                "five questions, against three or four in every human session. The "
                "strict rule would compare five human focus groups against roughly "
                "three synthetic documents."),
            "min_participants_per_fold": MIN_PARTICIPANTS_PER_FOLD,
            "min_profile_questions": MIN_PROFILE_QUESTIONS,
        },
        "budget_curve": {str(k): v for k, v in curve.items()},
        "budget_selection": {
            "rule": ("the largest budget that costs no human fold and keeps all five "
                     "focus groups in every condition"),
            "budgets_examined": list(BUDGETS),
            "viable_budgets": viable,
            "main_budget_words": main_budget,
            "sensitivity_budget_words": sensitivity_budget,
            "thin_budgets_reported_but_not_decisive": thin,
            "one_hundred_words_costs_human_folds": (
                curve["100"]["by_condition"]["human"]["n_folds_eligible"]
                if "100" in curve else
                curve[100]["by_condition"]["human"]["n_folds_eligible"]),
            "why_budget_binds_on_the_human_side": (
                "human participant x question cells are small - the smallest holds "
                "27 words, median 145 - while the smallest synthetic cell holds 123 "
                "and the median is around 400. Any budget the human side can meet is "
                "met by the synthetic side with room to spare, so equalisation removes "
                "text from synthetic participants, not from human ones."),
        },
        "per_cell_long_table": long_rows,
    }
    return out


def write(out: dict) -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    (_OUT / "agent_fidelity_preflight.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    rows = out["per_cell_long_table"]
    with (_OUT / "agent_fidelity_cell_tokens.csv").open(
            "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    o = build()
    write(o)
    print(f"documents {o['n_documents']}   cells {o['n_cells']}   "
          f"units reconcile {o['all_units_reconcile_against_segmentation']}")
    print(f"leakage clean: {o['leakage']['clean']}   "
          f"name mentions scrubbed: {o['n_name_mentions_scrubbed']}")
    print(f"participants silent in some question: "
          f"{o['n_participants_silent_in_a_question']}")
    print("\n=== words per participant x question cell ===")
    for c, d in o["cell_word_distribution_by_condition"].items():
        print(f"  {c:18s} n={d['n']:>3d}  min {d['min']:>4d}  p25 {d['p25']}  "
              f"median {d['median']:>6.1f}  max {d['max']:>5d}")
    print("\n=== budget curve (PER_FOLD; folds eligible / folds total) ===")
    print(f"  {'B':>4s}   {'human':>9s}  {'enriched':>9s}  {'demo-only':>9s}   "
          f"{'FGs H/E/D':>10s}")
    for b in BUDGETS:
        bc = o["budget_curve"][str(b)]["by_condition"]
        cells = []
        for c in afc.CONDITIONS:
            cells.append(f"{bc[c]['n_folds_eligible']:>4d}/{bc[c]['n_folds_total']:<4d}")
        fgs = "/".join(str(bc[c]["n_focus_groups_covered"]) for c in afc.CONDITIONS)
        print(f"  {b:>4d}   {cells[0]:>9s}  {cells[1]:>9s}  {cells[2]:>9s}   {fgs:>10s}")

    print("\n=== the rejected rule: documents whose participants all speak in every "
          "question ===")
    bc = o["budget_curve"][str(BUDGETS[0])]["by_condition"]
    for c in afc.CONDITIONS:
        print(f"  {c:18s} {bc[c]['strict_rule_n_documents_with_two_eligible_participants']}"
              f"/{bc[c]['n_documents_total']} documents keep 2+ participants")

    s = o["budget_selection"]
    print(f"\nviable budgets (no human fold lost): {s['viable_budgets']}")
    print(f"MAIN BUDGET  {s['main_budget_words']} words   "
          f"SENSITIVITY  {s['sensitivity_budget_words']} words   "
          f"thin arms {s['thin_budgets_reported_but_not_decisive']}")
    print(f"at 100 words the human side keeps "
          f"{s['one_hundred_words_costs_human_folds']} of 24 folds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
