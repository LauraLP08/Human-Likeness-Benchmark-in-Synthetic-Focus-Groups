"""
LEXICALLY_INDIVIDUALISABLE_AGENT_VOICE - offline stylometric analysis.

    py scripts/agent_fidelity_stylometry.py

WHAT IS AND IS NOT BEING MEASURED
---------------------------------
The observable property is whether a participant's text can be told apart from that of
their fellow participants, and whether the same participant can be recognised across
different guide questions. That is all. It is not evidence that a model "understands each
agent as an independent person", and lexical diversity, MATTR, TTR and lower vocabulary
overlap are not evidence of an individual identity either.

Four quantities are kept strictly separate:

  BETWEEN_SPEAKER_LEXICAL_DIFFERENTIATION - how much participants within one session
      resemble each other. Says nothing about whether one participant keeps a
      recognisable voice from question to question.
  WITHIN_SPEAKER_CROSS_QUESTION_CONTINUITY - the leave-one-question-out speaker
      identification below. This is the primary estimand.
  TOPICAL / SEMANTIC DIFFERENCE - guide questions differ in subject matter, so any
      cross-question comparison is confounded unless the question pair is held fixed.
      That is why the identity gap is computed within question pairs.
  SUBSTANTIVE PROFILE CONSISTENCY - not measured here at all; it needs contextual
      interpretation, not lexical geometry.

METHOD
------
Character n-gram TF-IDF (char_wb, 3-5), lowercase, fitted on the TRAINING fold only.
Nearest-centroid cosine, chosen for transparency and because the per-fold sample is
small. No embeddings, no LLM call, no speaker labels, no provenance in any analysed
string - the corpus module strips those and proves it.

One deterministic window per participant x question cell. Windows are never repeated at
different offsets: repeated overlapping windows would multiply the apparent number of
observations while resampling the same text.

Offline. No API call.
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from datetime import datetime, UTC
from itertools import combinations
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

import agent_fidelity_corpus as afc
import agent_fidelity_preflight as pre

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "analysis/production_evaluation/agent_fidelity"

MAIN_BUDGET = 50
SENSITIVITY_BUDGET = 25
THIN_BUDGETS = (75, 100)

# Representations. The first is the main analysis; the rest are sensitivity arms.
REPRESENTATIONS = {
    "char_wb_3_5": dict(analyzer="char_wb", ngram_range=(3, 5), lowercase=True,
                        min_df=1),
    "char_wb_3_5_alpha_only": dict(analyzer="char_wb", ngram_range=(3, 5),
                                   lowercase=True, min_df=1,
                                   preprocessor=lambda s: " ".join(
                                       "".join(ch for ch in s if ch.isalpha() or
                                               ch == " ").split())),
    "word_content": dict(analyzer="word", ngram_range=(1, 1), lowercase=True,
                         min_df=1, stop_words=sorted(afc._WORD.findall(
                             " ".join(sorted({"the", "and", "that", "have", "for",
                                              "not", "with", "you", "this", "but",
                                              "his", "from", "they", "she", "her",
                                              "been", "than", "its", "who", "yeah",
                                              "like", "just", "know", "think",
                                              "really", "actually", "sort", "kind"}))))),
}
MAIN_REPRESENTATION = "char_wb_3_5"


def window(text: str, budget: int) -> str | None:
    """
    ONE deterministic, centred window per cell. Centred rather than leading because turn
    openers are positionally confounded; the same rule applies to every cell in every
    condition, so no condition is advantaged.
    """
    w = afc.words(text)
    if len(w) < budget:
        return None
    off = (len(w) - budget) // 2
    return " ".join(w[off:off + budget])


def _vectorizer(name):
    return TfidfVectorizer(**REPRESENTATIONS[name])


# ---------------------------------------------------- C3 speaker identification
def loqo_document(cells, doc, questions, participants_by_q, budget, rep):
    """
    LEAVE_ONE_QUESTION_OUT_SPEAKER_IDENTIFICATION for one document.

    For each held-out question: build every eligible participant's profile from their
    OTHER questions only, then classify the held-out text against those profiles. The
    vectorizer is fitted on the training documents alone, so no held-out token influences
    the vocabulary or the idf weights.
    """
    trials, folds = [], []
    for q in questions:
        eligible = participants_by_q.get((doc, q), [])
        if len(eligible) < pre.MIN_PARTICIPANTS_PER_FOLD:
            continue
        train_txt, train_lab = [], []
        for p in eligible:
            for o in questions:
                if o == q:
                    continue
                c = cells.get((doc, o, p))
                if c is None:
                    continue
                w = window(c["text"], budget)
                if w:
                    train_txt.append(w)
                    train_lab.append(p)
        test = {}
        for p in eligible:
            w = window(cells[(doc, q, p)]["text"], budget)
            if w:
                test[p] = w
        present = sorted(set(train_lab))
        if len(present) < pre.MIN_PARTICIPANTS_PER_FOLD or len(test) < 1:
            continue

        vec = _vectorizer(rep)
        X = vec.fit_transform(train_txt).toarray()
        cent = {}
        for p in present:
            idx = [i for i, lab in enumerate(train_lab) if lab == p]
            v = X[idx].mean(axis=0)
            n = np.linalg.norm(v)
            cent[p] = v / n if n else v
        Y = vec.transform([test[p] for p in sorted(test)]).toarray()
        chance = 1.0 / len(present)
        n_correct = 0
        for row, p in zip(Y, sorted(test)):
            n = np.linalg.norm(row)
            row = row / n if n else row
            sims = {c_: float(row @ cent[c_]) for c_ in present}
            pred = max(sims, key=sims.get)
            ok = pred == p
            n_correct += ok
            trials.append({"doc": doc, "question": q, "true": p, "predicted": pred,
                           "correct": bool(ok), "n_classes": len(present),
                           "chance": round(chance, 4),
                           "margin": round(sims[pred] - sorted(sims.values())[-2], 4)
                           if len(sims) > 1 else None})
        folds.append({"doc": doc, "question": q, "n_classes": len(present),
                      "n_trials": len(test), "n_correct": n_correct,
                      "chance": round(chance, 4)})
    return trials, folds


def _macro_f1(trials, labels):
    f1s = []
    for lab in labels:
        tp = sum(1 for t in trials if t["true"] == lab and t["predicted"] == lab)
        fp = sum(1 for t in trials if t["true"] != lab and t["predicted"] == lab)
        fn = sum(1 for t in trials if t["true"] == lab and t["predicted"] != lab)
        if tp + fn == 0:
            continue
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn)
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return statistics.mean(f1s) if f1s else None


def _balanced_accuracy(trials, labels):
    recs = []
    for lab in labels:
        n = sum(1 for t in trials if t["true"] == lab)
        if not n:
            continue
        recs.append(sum(1 for t in trials
                        if t["true"] == lab and t["predicted"] == lab) / n)
    return statistics.mean(recs) if recs else None


def summarise(trials):
    """Chance is averaged over trials because the eligible set varies by fold."""
    if not trials:
        return None
    labels = sorted({t["true"] for t in trials})
    acc = sum(t["correct"] for t in trials) / len(trials)
    chance = statistics.mean(t["chance"] for t in trials)
    corrected = (acc - chance) / (1 - chance) if chance < 1 else None
    return {"n_trials": len(trials), "n_speakers": len(labels),
            "accuracy": round(acc, 4),
            "chance_baseline": round(chance, 4),
            "chance_corrected_accuracy": round(corrected, 4)
            if corrected is not None else None,
            "macro_f1": round(_macro_f1(trials, labels), 4)
            if _macro_f1(trials, labels) is not None else None,
            "balanced_accuracy": round(_balanced_accuracy(trials, labels), 4)
            if _balanced_accuracy(trials, labels) is not None else None,
            "chance_note": ("the eligible participant set varies by fold, so the "
                            "baseline is the mean of the per-fold 1/n_participants")}


def confusion(trials, doc):
    t = [x for x in trials if x["doc"] == doc]
    labels = sorted({x["true"] for x in t} | {x["predicted"] for x in t})
    m = {a: {b: 0 for b in labels} for a in labels}
    for x in t:
        m[x["true"]][x["predicted"]] += 1
    return {"labels": labels, "matrix": m}


# ------------------------------------------------------------ C4 identity gap
def identity_similarities(cells, doc, questions, eligible_any, budget, rep):
    """
    Same-speaker and different-speaker similarity, WITH THE QUESTION PAIR HELD FIXED.

    A same-speaker observation always spans two different questions, so comparing it
    against different-speaker pairs drawn from the SAME question would let topic do the
    work: two people answering one question share subject matter that one person answering
    two questions does not. Every contrast below therefore fixes an unordered question
    pair {qa, qb} and compares, inside that pair only:

        same speaker      cos( cell(p, qa),  cell(p, qb) )
        different speaker cos( cell(p, qa),  cell(p', qb) )   p != p'

    The topical distance between qa and qb is then common to both sides.
    """
    texts, keys = [], []
    for q in questions:
        for p in eligible_any:
            c = cells.get((doc, q, p))
            if c is None:
                continue
            w = window(c["text"], budget)
            if w:
                texts.append(w)
                keys.append((p, q))
    if len(texts) < 4:
        return None
    vec = _vectorizer(rep)
    X = vec.fit_transform(texts).toarray()
    X = X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    idx = {k: i for i, k in enumerate(keys)}

    per_pair = []
    for qa, qb in combinations(questions, 2):
        have = [p for p in eligible_any if (p, qa) in idx and (p, qb) in idx]
        if len(have) < 2:
            continue
        same = [float(X[idx[(p, qa)]] @ X[idx[(p, qb)]]) for p in have]
        diff = []
        for a, b in combinations(have, 2):
            diff.append(float(X[idx[(a, qa)]] @ X[idx[(b, qb)]]))
            diff.append(float(X[idx[(b, qa)]] @ X[idx[(a, qb)]]))
        per_pair.append({"question_pair": f"Q{qa}-Q{qb}", "n_speakers": len(have),
                         "n_same": len(same), "n_different": len(diff),
                         "same_speaker_median": round(statistics.median(same), 4),
                         "different_speaker_median": round(statistics.median(diff), 4),
                         "gap": round(statistics.median(same)
                                      - statistics.median(diff), 4)})
    if not per_pair:
        return None
    gaps = [p["gap"] for p in per_pair]
    return {"per_question_pair": per_pair,
            "n_question_pairs": len(per_pair),
            "same_speaker_median": round(statistics.median(
                [p["same_speaker_median"] for p in per_pair]), 4),
            "different_speaker_median": round(statistics.median(
                [p["different_speaker_median"] for p in per_pair]), 4),
            "identity_gap_median": round(statistics.median(gaps), 4),
            "identity_gap_min": round(min(gaps), 4),
            "identity_gap_max": round(max(gaps), 4),
            "pairs_are_not_independent_observations": True,
            "close_to_zero_is_not_an_equivalence_result": (
                "no equivalence margin was defined and no equivalence test was run; a "
                "gap close to zero does not demonstrate absence of difference")}


def between_speaker_similarity(cells, doc, questions, eligible_any, budget, rep):
    """
    BETWEEN_SPEAKER_LEXICAL_DIFFERENTIATION_DIAGNOSTICS, computed WITHIN a question so
    topic is common to both speakers. Higher = participants resemble each other more.

    This measures how alike the members of one session are. It says nothing about whether
    any one of them keeps a recognisable voice from question to question, which is the
    separate quantity the speaker-identification analysis estimates.
    """
    per_q = []
    for q in questions:
        txt, who = [], []
        for p in eligible_any:
            c = cells.get((doc, q, p))
            if c is None:
                continue
            w = window(c["text"], budget)
            if w:
                txt.append(w)
                who.append(p)
        if len(txt) < 2:
            continue
        vec = _vectorizer(rep)
        X = vec.fit_transform(txt).toarray()
        X = X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
        sims = [float(X[i] @ X[j]) for i, j in combinations(range(len(txt)), 2)]
        per_q.append({"question": q, "n_speakers": len(txt), "n_pairs": len(sims),
                      "median_pairwise_cosine": round(statistics.median(sims), 4),
                      "min": round(min(sims), 4), "max": round(max(sims), 4)})
    if not per_q:
        return None
    med = [p["median_pairwise_cosine"] for p in per_q]
    return {"per_question": per_q, "n_questions": len(per_q),
            "median_pairwise_cosine": round(statistics.median(med), 4),
            "min": round(min(med), 4), "max": round(max(med), 4),
            "higher_means_participants_resemble_each_other_more": True,
            "not_evidence_of_individual_identity": True}


def hierarchical(per_doc, cond, fg, repl) -> dict:
    """
    The comparative estimand, aggregated at the level the design actually has.

    trial -> document -> focus group -> study replicate. Never trial -> condition: a
    pooled mean over trials weights each document by how many speakers and eligible folds
    it happens to contain, so a session with five talkative participants counts for more
    than one with two. That is a property of the transcript, not of the condition.

    Human keeps five values, one per focus group - it is one realisation. Each synthetic
    replicate is summarised from ITS OWN five focus groups, and the three replicates are
    reported separately, never merged into one sample.

    A focus group with no eligible fold is absent. It is not imputed and not zero: the
    replicate simply reports the coverage it has.
    """
    out = {}
    for c in afc.CONDITIONS:
        reps = ["human"] if c == "human" else [1, 2, 3]
        out[c] = {}
        for r in reps:
            per_fg, missing = {}, []
            for f in ("fg1", "fg2", "fg3", "fg4", "fg5"):
                docs = [d for d in per_doc if cond[d] == c and fg[d] == f
                        and (repl[d] or "human") == r]
                if not docs:
                    missing.append(f)
                    continue
                per_fg[f] = per_doc[docs[0]]["chance_corrected_accuracy"]
            vals = [v for v in per_fg.values() if v is not None]
            out[c][str(r)] = {
                "per_focus_group": per_fg,
                "n_focus_groups": len(vals),
                "n_focus_groups_expected": 5,
                "focus_groups_without_an_eligible_fold": missing,
                "coverage": f"{len(vals)}/5",
                "mean_chance_corrected_accuracy": round(statistics.mean(vals), 4)
                if vals else None,
                "median_chance_corrected_accuracy": round(statistics.median(vals), 4)
                if vals else None,
                "observed_range": [round(min(vals), 4), round(max(vals), 4)]
                if vals else None,
                "missing_focus_groups_are_absent_not_zero": True,
            }
        vals = [v["mean_chance_corrected_accuracy"] for v in out[c].values()
                if v["mean_chance_corrected_accuracy"] is not None]
        out[c]["_across_realisations"] = {
            "n_realisations": len(vals),
            "values": vals,
            "median": round(statistics.median(vals), 4) if vals else None,
            "observed_range": [round(min(vals), 4), round(max(vals), 4)]
            if vals else None,
            "replicates_are_not_pooled": True,
            "no_inferential_test_is_derived_from_five_focus_groups_or_three_"
            "realisations": True,
        }
    return out


# --------------------------------------------------------------------- build
def build(budget=MAIN_BUDGET, rep=MAIN_REPRESENTATION) -> dict:
    corpus = afc.build()
    by_doc = pre.cells_by_document(corpus)
    doc_q = {d: sorted(set(v["questions"])) for d, v in corpus["docs"].items()}
    cond = {d: v["condition"] for d, v in corpus["docs"].items()}
    fg = {d: v["fg"] for d, v in corpus["docs"].items()}
    repl = {d: v["replicate"] for d, v in corpus["docs"].items()}
    elig = pre.per_fold_eligible(by_doc, doc_q, budget)

    all_trials, all_folds, gaps, between = [], [], {}, {}
    for d in sorted(by_doc):
        t, f = loqo_document(corpus["cells"], d, doc_q[d], elig, budget, rep)
        all_trials += t
        all_folds += f
        any_elig = sorted({p for (dd, q), ps in elig.items() if dd == d for p in ps})
        if len(any_elig) >= 2:
            g = identity_similarities(corpus["cells"], d, doc_q[d], any_elig,
                                      budget, rep)
            if g:
                gaps[d] = g
            b = between_speaker_similarity(corpus["cells"], d, doc_q[d], any_elig,
                                           budget, rep)
            if b:
                between[d] = b

    per_doc = {}
    for d in sorted({t["doc"] for t in all_trials}):
        t = [x for x in all_trials if x["doc"] == d]
        per_doc[d] = {"condition": cond[d], "fg": fg[d],
                      "replicate": repl[d] or "human",
                      **(summarise(t) or {}),
                      "confusion": confusion(all_trials, d),
                      "identity_gap": gaps.get(d),
                      "between_speaker": between.get(d)}

    by_condition = {}
    for c in afc.CONDITIONS:
        t = [x for x in all_trials if cond[x["doc"]] == c]
        s = summarise(t)
        docs_c = sorted(d for d in per_doc if cond[d] == c)
        by_condition[c] = {
            **(s or {}),
            "n_documents": len(docs_c),
            "per_document_accuracy": {d: per_doc[d]["accuracy"] for d in docs_c},
            "per_document_chance_corrected": {
                d: per_doc[d]["chance_corrected_accuracy"] for d in docs_c},
            "identity_gap_per_document": {d: (gaps[d]["identity_gap_median"]
                                              if d in gaps else None)
                                          for d in docs_c},
            "between_speaker_similarity_per_document": {
                d: (between[d]["median_pairwise_cosine"] if d in between else None)
                for d in docs_c},
        }

    # The focus group is the comparative unit; the three synthetic replicates estimate
    # generator variability and are never pooled into a single focus-group value.
    by_fg = {}
    for c in afc.CONDITIONS:
        by_fg[c] = {}
        for f in ("fg1", "fg2", "fg3", "fg4", "fg5"):
            docs_f = sorted(d for d in per_doc if cond[d] == c and fg[d] == f)
            by_fg[c][f] = [{"document": d, "replicate": per_doc[d]["replicate"],
                            "accuracy": per_doc[d]["accuracy"],
                            "chance_baseline": per_doc[d]["chance_baseline"],
                            "chance_corrected_accuracy":
                                per_doc[d]["chance_corrected_accuracy"],
                            "macro_f1": per_doc[d]["macro_f1"],
                            "balanced_accuracy": per_doc[d]["balanced_accuracy"],
                            "n_trials": per_doc[d]["n_trials"],
                            "identity_gap_median": (gaps[d]["identity_gap_median"]
                                                    if d in gaps else None),
                            "between_speaker_median_cosine":
                                (between[d]["median_pairwise_cosine"]
                                 if d in between else None)}
                           for d in docs_f]

    by_question = {}
    for q in afc.QUESTIONS:
        by_question[f"Q{q}"] = {}
        for c in afc.CONDITIONS:
            t = [x for x in all_trials if x["question"] == q and cond[x["doc"]] == c]
            by_question[f"Q{q}"][c] = summarise(t) if t else {
                "n_trials": 0, "status": "NOT_ASKED_IN_FIELDWORK"
                if (c, "fg5", q) in [(a, b, cc) for a, b, cc in
                                     afc.NOT_ASKED_IN_FIELDWORK] else "NO_ELIGIBLE_FOLD"}

    hier = hierarchical(per_doc, cond, fg, repl)

    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "id": "LEXICALLY_INDIVIDUALISABLE_AGENT_VOICE",
        "analysis": "LEAVE_ONE_QUESTION_OUT_SPEAKER_IDENTIFICATION",
        "status": "EXPLORATORY_AUTOMATIC_STYLOMETRIC_DIAGNOSTIC",
        "no_api_calls": True, "no_new_human_coding": True, "no_embeddings": True,
        "budget_words": budget, "representation": rep,
        "representation_params": {k: str(v) for k, v in REPRESENTATIONS[rep].items()},
        "window_rule": ("one deterministic centred window of WORDS per participant x "
                        "question cell, cut with the project lexical tokeniser; these "
                        "are words, not model tokens; offsets are never repeated to "
                        "manufacture observations"),
        "budget_unit": "words",
        "budget_unit_note": ("the budget is applied in WORDS by the project lexical "
                             "tokeniser. It is not a model-token budget. 'Token' is "
                             "reserved for API cost and model tokenisation."),
        "eligibility_rule": "PER_FOLD",
        "unit_of_comparison": ("focus group; the three synthetic replicates are reported "
                               "separately and estimate generator variability"),
        "identity_gap_interpretation": (
            "The median identity-separation gap was close to zero in all three "
            "conditions and did not provide additional evidence of persistent speaker "
            "differentiation."),
        "identity_gap_is_not_an_equivalence_claim": (
            "no equivalence margin was defined and no equivalence test was run"),
        "primary_estimand_rationale": (
            "speaker identification remains the primary estimand because it evaluates "
            "directly whether a held-out text can be attributed to its own speaker "
            "among the eligible participants of the same session"),
        "what_this_does_not_show": [
            "it does not show that a model understands each agent as an independent "
            "person",
            "lexical diversity, MATTR and TTR are not evidence of individual identity",
            "between-speaker differentiation and cross-question continuity are distinct "
            "properties and are reported separately",
            "no human validation of stylometry exists; the two-coder exercise validated "
            "thematic extraction in Q3 only",
        ],
        "n_trials": len(all_trials), "n_folds": len(all_folds),

        # -------- primary comparative estimand ---------------------------------
        "primary_estimand": "HIERARCHICAL_DOCUMENT_TO_FOCUS_GROUP_TO_STUDY_REPLICATE",
        "hierarchy": ["trial", "document", "focus group", "study replicate"],
        "hierarchical": hier,

        # -------- secondary, trial-weighted ------------------------------------
        "pooled_label": "TRIAL_WEIGHTED_DIAGNOSTIC_NOT_PRIMARY_CONDITION_ESTIMATE",
        "pooled_caveat": (
            "pooling over trials weights each document by how many speakers and "
            "eligible folds it contains, which is a property of the transcript rather "
            "than of the condition; these figures are technical information only and "
            "are not the comparative result"),
        "overall": summarise(all_trials),
        "by_condition": by_condition,
        "by_focus_group": by_fg,
        "by_question": by_question,
        "per_document": per_doc,
        "folds": all_folds,
        "trials": all_trials,
    }


def sensitivity() -> dict:
    """Budgets and representations, each recomputed end to end."""
    out = {}
    for b in (MAIN_BUDGET, SENSITIVITY_BUDGET, *THIN_BUDGETS):
        for rep in REPRESENTATIONS:
            if b != MAIN_BUDGET and rep != MAIN_REPRESENTATION:
                continue          # vary one axis at a time
            o = build(budget=b, rep=rep)
            out[f"{rep}@{b}"] = {
                "budget_words": b, "representation": rep,
                "is_main": b == MAIN_BUDGET and rep == MAIN_REPRESENTATION,
                "is_thin_human_coverage": b in THIN_BUDGETS,
                "overall": o["overall"],
                "by_condition": {c: {k: v for k, v in o["by_condition"][c].items()
                                     if not isinstance(v, dict)}
                                 for c in afc.CONDITIONS},
            }
    return out


def write(main: dict, sens: dict) -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    (_OUT / "agent_fidelity_stylometry.json").write_text(
        json.dumps(main, indent=1, ensure_ascii=False), encoding="utf-8")
    (_OUT / "agent_fidelity_stylometry_sensitivity.json").write_text(
        json.dumps(sens, indent=1, ensure_ascii=False), encoding="utf-8")

    rows = []
    for c, fgs in main["by_focus_group"].items():
        for f, recs in fgs.items():
            for r in recs:
                rows.append({"condition": c, "fg": f, **r})
    with (_OUT / "agent_fidelity_speaker_id_by_document.csv").open(
            "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    hrows = []
    for c, reps in main["hierarchical"].items():
        for r, v in reps.items():
            if r == "_across_realisations":
                continue
            for f, val in v["per_focus_group"].items():
                hrows.append({"level": "focus_group", "condition": c,
                              "study_replicate": r, "fg": f,
                              "chance_corrected_accuracy": val, "coverage": ""})
            hrows.append({"level": "study_replicate", "condition": c,
                          "study_replicate": r, "fg": "",
                          "chance_corrected_accuracy":
                              v["mean_chance_corrected_accuracy"],
                          "coverage": v["coverage"]})
    with (_OUT / "agent_fidelity_hierarchical_estimates.csv").open(
            "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(hrows[0]))
        w.writeheader()
        w.writerows(hrows)

    with (_OUT / "agent_fidelity_trials_long.csv").open(
            "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(main["trials"][0]))
        w.writeheader()
        w.writerows(main["trials"])


def main_() -> int:
    m = build()
    s = sensitivity()
    write(m, s)
    o = m["overall"]
    print(f"trials {o['n_trials']}   folds {m['n_folds']}   "
          f"budget {m['budget_words']}w   representation {m['representation']}")
    print(f"OVERALL accuracy {o['accuracy']:.4f}  chance {o['chance_baseline']:.4f}  "
          f"chance-corrected {o['chance_corrected_accuracy']:.4f}  "
          f"macro-F1 {o['macro_f1']:.4f}")
    print("\n=== by condition ===")
    for c in afc.CONDITIONS:
        b = m["by_condition"][c]
        print(f"  {c:18s} n={b['n_trials']:>3d}  acc {b['accuracy']:.4f}  "
              f"chance {b['chance_baseline']:.4f}  corrected "
              f"{b['chance_corrected_accuracy']:.4f}  macroF1 {b['macro_f1']:.4f}  "
              f"balacc {b['balanced_accuracy']:.4f}")
    print("\n=== PRIMARY: document -> focus group -> study replicate ===")
    for c in afc.CONDITIONS:
        for r, v in m["hierarchical"][c].items():
            if r == "_across_realisations":
                continue
            lab = "human" if r == "human" else f"R{r}"
            miss = v["focus_groups_without_an_eligible_fold"]
            print(f"  {c:18s} {lab:6s} mean {v['mean_chance_corrected_accuracy']:+.4f}"
                  f"   coverage {v['coverage']}"
                  + (f"   MISSING {miss}" if miss else ""))
    print(f"  (the pooled-over-trials figures above are {m['pooled_label']})")

    print("\n=== by focus group (replicates separate) ===")
    for c in afc.CONDITIONS:
        for f in ("fg1", "fg2", "fg3", "fg4", "fg5"):
            recs = m["by_focus_group"][c][f]
            if not recs:
                continue
            vals = "  ".join(f"{r['replicate']}:{r['accuracy']:.2f}"
                             f"(cc {r['chance_corrected_accuracy']:+.2f})"
                             for r in recs)
            print(f"  {c:18s} {f}  {vals}")
    print("\n=== between-speaker similarity within a question (higher = more alike) ===")
    for c in afc.CONDITIONS:
        v = [x for x in m["by_condition"][c][
            "between_speaker_similarity_per_document"].values() if x is not None]
        if v:
            print(f"  {c:18s} median {statistics.median(v):.4f}  "
                  f"range {min(v):.4f} .. {max(v):.4f}  n_documents {len(v)}")

    print("\n=== identity gap (question pair held fixed) ===")
    for c in afc.CONDITIONS:
        g = [v for v in m["by_condition"][c]["identity_gap_per_document"].values()
             if v is not None]
        if g:
            print(f"  {c:18s} median {statistics.median(g):+.4f}  "
                  f"range {min(g):+.4f} .. {max(g):+.4f}  n_documents {len(g)}")
    print("\n=== sensitivity ===")
    for k, v in s.items():
        oo = v["overall"]
        flag = " (MAIN)" if v["is_main"] else (" (thin human coverage)"
                                               if v["is_thin_human_coverage"] else "")
        print(f"  {k:28s} acc {oo['accuracy']:.4f}  corrected "
              f"{oo['chance_corrected_accuracy']:+.4f}  n={oo['n_trials']}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_())
