#!/usr/bin/env python3
"""
twinpop_g2_g3b_gates.py — G3(b), the evaluator-variance probe, G2 layer 2 and
G2 layer 3, in the order that avoids rework.

EXECUTION ORDER (deliberate — the previous order was the worst possible)
-----------------------------------------------------------------------
G3(b) is the ONLY gate whose firing forces the narratives to be regenerated
(entry 6). Running layers 2 and 3 first would throw away every call made against
narratives that then get replaced. So:

  1. G3(b)                 24 calls  — cheapest, and the only one that can force regen
  2. evaluator variance     3 calls  — decides whether layer 2 needs 3 passes or 1
  3. G2 layer 2        24 or 72      — plus 24 if the shuffled control is used
  4. G2 layer 3            48 calls  — most expensive per unit, and only descriptive

Ceiling drops from 144 to 99 if the frozen evaluator turns out deterministic.

WHAT THE AUDIT CAUGHT BEFORE ANY CALL WAS MADE
----------------------------------------------
* G3(b) would have fired on PRONOUNS, not caricature. The narratives carry
  he 43 / his 35 on the male branch and her 73 / she 65 on the inverted one, so
  the evaluator only had to pick the one saying "he". It would have returned
  ~24/24, cleared the 17/24 threshold and ordered a resample of all 8 narratives
  for a pronoun artefact. The frozen entry 6 requires neutralisation of names and
  pronouns; it was simply not implemented. It is now, with its own verification
  sub-gate and a planted-pronoun control.
* G3(b) had no position counterbalancing. LLM judges have documented position
  bias; assigning real=A in all 24 pairs lets a position-preferring judge return
  24/24 on its own. A/B assignment is now randomised per pair with the mapping
  recorded, and the answer is de-mapped before scoring.
* G3(b) had no prompt in the code at all. It is written here.
* The no-narrative negative control was not comparable: 415-418 words against
  241-256 (1.7x), and its content is the behaviour-instruction block, not a life
  sketch. The differential "twinpop > control" was guaranteed by construction.
  It is demoted to an explicitly non-matched floor reading; control_inverted
  (same prompt, same fields, same length) becomes primary, and a SHUFFLED
  control is added — same genre, same register, same vocabulary, no coherent
  person — which is the only control that isolates what layer 2 claims to measure.
* Layer 3's redaction list contained "building" and "training", which sit on top
  of codebook subtheme B.3 (gym / protein / strength). Removed: redacting them
  would have destroyed signal the probe exists to detect.

Evaluator: the frozen one (frozen_evaluation_spec.md §2-§4). Never Claude.

Usage:
    py scripts/twinpop_g2_g3b_gates.py --out-dir <dir> --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CODEBOOK = ROOT / "analysis" / "production_evaluation" / "gold_standard_sealed" / "codebook_reference.csv"
N_PASSES = 3
VALID_AT = 2
PROBE_SAMPLES = 3
GUIDE_Q3 = "Do you think your gender influences what you eat? Tell us more about why or why not."
COUNTERBALANCE_SEED = 20260805

# Gender surface forms. Neutralised on BOTH branches equally, then verified to
# be zero — the sub-gate, not a hope.
GENDER_MAP = {
    "he": "they", "she": "they", "him": "them", "her": "their", "hers": "theirs",
    "his": "their", "himself": "themselves", "herself": "themselves",
    "man": "person", "woman": "person", "men": "people", "women": "people",
    "male": "adult", "female": "adult", "wife": "partner", "husband": "partner",
    "mr": "mx", "mrs": "mx", "ms": "mx",
}
GENDER_TOKENS = sorted(GENDER_MAP)

# Biographical give-aways redacted for the layer-3 secondary read.
# "building" and "training" were REMOVED: "building muscle" and "training" are
# gym language, i.e. codebook B.3 "Necessary", which the probe must be able to
# detect. Redacting them would have suppressed the signal being measured.
BIOGRAPHIC_REDACTION = [
    r"\b(manager|managers|logistics|warehousing|warehouse|welding|welder|electrician|"
    r"electrical|construction|builder|driver|driving|hgv|lorry|plumber|joiner|"
    r"finishing|trades?|vocational)\b",
    r"\b(terraced|semi-detached|detached|bungalow|mortgage|rented|tenant|landlord)\b",
    r"\b(suburban|rural|village|north west|south east|south west|east of england)\b",
]

G3B_PROMPT = (
    "Below are two short descriptions of a person's life, A and B. They were written "
    "from the same underlying facts.\n\n"
    "A:\n{a}\n\nB:\n{b}\n\n"
    "Which of these two descriptions corresponds to someone who would more strongly "
    "endorse traditional masculine norms?\n"
    'Answer with JSON only: {{"choice": "A"}} or {{"choice": "B"}}.'
)


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
                 ("–", "-"), ("—", "-"), ("…", "...")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).casefold().strip(" .,;:!?-")


def quote_verifies(quote: str, source: str) -> bool:
    q = normalise(quote)
    return bool(q) and q in normalise(source)


def neutralise_gender(text: str) -> str:
    def sub(m):
        w = m.group(0)
        repl = GENDER_MAP[w.lower()]
        return repl.capitalize() if w[0].isupper() else repl
    return re.sub(r"\b(" + "|".join(GENDER_TOKENS) + r")\b", sub, text, flags=re.I)


def count_gender_tokens(text: str) -> int:
    return len(re.findall(r"\b(" + "|".join(GENDER_TOKENS) + r")\b", text, flags=re.I))


def neutralisation_controls() -> list[tuple[str, str, str]]:
    """Positive and negative controls for the neutralisation sub-gate."""
    out = []
    clean = neutralise_gender("He drives his van. His wife works nearby.")
    out.append(("negative: neutralised text has 0 gender tokens", "PASS",
                "PASS" if count_gender_tokens(clean) == 0 else "FAIL"))
    planted = clean + " She is his husband."          # planted, must be caught
    out.append(("positive: planted pronouns detected", "FAIL",
                "PASS" if count_gender_tokens(planted) == 0 else "FAIL"))
    return out


def load_codebook() -> list[dict]:
    with CODEBOOK.open(encoding="utf-8") as fh:
        return [{"id": r["subtheme_id"], "label": r["subtheme_label"],
                 "description": r["description"]} for r in csv.DictReader(fh)]


def layer2_prompt(codebook: list[dict], text: str) -> str:
    items = "\n".join(f"  {c['id']} — {c['label']}: {c['description']}" for c in codebook)
    return (
        "You are auditing a short biographical life-sketch written for a research "
        "simulation. Below are 11 subtheme definitions from a codebook about food, "
        f"gender and eating.\n\n{items}\n\nTEXT:\n{text}\n\n"
        "For each subtheme that this text makes MORE LIKELY to be raised by its subject, "
        "return the subtheme id and a VERBATIM fragment copied exactly from the TEXT. "
        "Do not paraphrase the fragment. If none applies, return an empty list.\n"
        'Return JSON: {"hits": [{"subtheme_id": "...", "quote": "..."}]}'
    )


def shuffled_controls(narratives: list[dict], rng: random.Random) -> list[str]:
    """Sentence-level recombination across agents: same genre, same register,
    same length, same vocabulary — no coherent person. The only control that
    isolates whether layer 2 tracks the PERSONA rather than the genre."""
    pool = []
    for r in narratives:
        for field in r["narrative"].values():
            pool.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", field) if s.strip())
    rng.shuffle(pool)
    per = max(1, len(pool) // len(narratives))
    return [" ".join(pool[i * per:(i + 1) * per]) for i in range(len(narratives))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rng = random.Random(COUNTERBALANCE_SEED)
    codebook = load_codebook()
    nar = json.loads((args.out_dir / "persona_narratives.json").read_text(encoding="utf-8"))
    res = nar["results"]
    selected = [r for r in res if r["branch"] == "real" and r["candidate_index"] == 1]
    inv_sel = [r for r in res if r["branch"] == "inverted" and r["candidate_index"] == 1]

    # ---- STEP 1: G3(b), neutralised and counterbalanced --------------------
    pairs, gender_after = [], 0
    for real in [r for r in res if r["branch"] == "real"]:
        inv = next(r for r in res if r["branch"] == "inverted"
                   and r["agent_id"] == real["agent_id"]
                   and r["candidate_index"] == real["candidate_index"])
        a_txt = neutralise_gender(" ".join(real["narrative"].values()))
        b_txt = neutralise_gender(" ".join(inv["narrative"].values()))
        gender_after += count_gender_tokens(a_txt) + count_gender_tokens(b_txt)
        male_is_a = rng.random() < 0.5          # position counterbalancing
        shown_a, shown_b = (a_txt, b_txt) if male_is_a else (b_txt, a_txt)
        pairs.append({
            "agent_id": real["agent_id"], "candidate_index": real["candidate_index"],
            "male_branch_shown_as": "A" if male_is_a else "B",
            "prompt": G3B_PROMPT.format(a=shown_a, b=shown_b),
        })

    ctl = neutralisation_controls()
    subgate_ok = gender_after == 0 and all(e == g for _, e, g in ctl)

    # ---- STEP 3: G2 layer 2, four arms -------------------------------------
    shuffled = shuffled_controls(selected, rng)
    l2 = []
    for arm, texts in (
        ("twinpop", [" ".join(r["narrative"].values()) for r in selected]),
        ("control_inverted", [" ".join(r["narrative"].values()) for r in inv_sel]),
        ("control_shuffled", shuffled),
    ):
        for i, text in enumerate(texts):
            for p in range(1, N_PASSES + 1):
                l2.append({"arm": arm, "idx": i, "pass": p, "source_text": text,
                           "prompt": layer2_prompt(codebook, text)})

    # ---- STEP 4: G2 layer 3 ------------------------------------------------
    l3 = [{"arm": arm, "agent_dir": folder, "agent_id": r["agent_id"], "sample": s,
           "question": GUIDE_Q3,
           "params": {"conversation_history": [], "recent_transcript": None, "hook": "",
                      "participant_response_max_tokens": 800, "temperature": 1.0}}
          for arm, folder in (("twinpop", "macho_meals_twinpop"),
                              ("demoonly", "macho_meals_demoonly"))
          for r in selected for s in range(1, PROBE_SAMPLES + 1)]

    spec = {
        "gate": "G3(b) + evaluator variance + G2 layer2 + G2 layer3 — repaired",
        "evaluator": "frozen_evaluation_spec.md §2-§4. Never Claude.",
        "execution_order": ["G3(b) 24", "variance probe 3", "layer2 24 or 72", "layer3 48"],
        "order_rationale": ("G3(b) is the only gate whose firing forces regeneration of the "
                            "narratives, so it runs first; every layer-2/3 call made before it "
                            "would be discarded if it fired."),
        "g3b": {
            "n_pairs": len(pairs),
            "neutralisation": {"tokens_mapped": GENDER_TOKENS,
                               "gender_tokens_remaining": gender_after,
                               "subgate_pass": subgate_ok,
                               "controls": [{"name": n, "expected": e, "observed": g}
                                            for n, e, g in ctl]},
            "counterbalanced": True, "seed": COUNTERBALANCE_SEED,
            "reported": ["binomial over 24 pairs", "per-cell majority over n=8"],
            "non_independence": "3 candidates per cell share one census row",
            "pre_declared_caveat": ("REWRITTEN after neutralisation. Before it, the evaluator was "
                                    "at CEILING by construction (pronouns); the earlier caveat "
                                    "claimed the opposite. With gender surface removed and the "
                                    "census attributes held fixed, the two texts of a pair are "
                                    "near-paraphrases, so the evaluator sits near chance BY "
                                    "CONSTRUCTION: a non-firing G3(b) is WEAK EVIDENCE, never "
                                    "evidence of absence of caricature."),
        },
        "layer2": {
            "arms": {"twinpop": "target",
                     "control_inverted": "PRIMARY control — same prompt, fields and length",
                     "control_shuffled": ("sentence-level recombination across agents: same genre, "
                                          "register, length and vocabulary, no coherent person"),
                     "control_no_narrative": ("DEMOTED — 415-418 words vs 241-256 (1.7x) and a "
                                              "different genre entirely (behaviour instructions). "
                                              "Kept only as an explicitly non-matched floor reading.")},
            "n_calls": len(l2), "passes": N_PASSES, "valid_at": VALID_AT,
            "quote_verification": "substring after project normalisation; unverifiable = discarded",
            "stop_condition": "DIFFERENTIAL against control_inverted and control_shuffled",
            "pre_declared_limit": ("control_inverted is near-paraphrase (too strong) and "
                                   "control_no_narrative is another genre (too weak), so layer 2 "
                                   "may yield a floor and a ceiling rather than a decision."),
            "variance_probe": "3 calls on one text first; if the frozen evaluator is deterministic, "
                              "the >=2/3 rule is decorative and this drops to 24 calls",
        },
        "layer3": {
            "n_calls": len(l3),
            "blindness": "NOT ACHIEVABLE — declared, not claimed",
            "reported_twice": ["raw", "with biographical redaction"],
            "redaction_note": "'building' and 'training' removed from the list: they sit on B.3",
            "threshold": "DESCRIPTIVE — exact counts, no gate, no implicit alpha",
        },
        "total_calls_max": len(pairs) + 3 + len(l2) + len(l3),
    }

    print(f"1. G3(b)            {len(pairs)} llamadas   neutralizado, contrapesado")
    print(f"   tokens de genero restantes: {gender_after}   sub-puerta: "
          f"{'PASS' if subgate_ok else 'FAIL'}")
    for n, e, g in ctl:
        print(f"      {'OK ' if e == g else 'ROTO'} {n:48s} esperado={e} obtenido={g}")
    print(f"2. sonda de varianza  3 llamadas")
    print(f"3. G2 capa 2       {len(l2)} llamadas   twinpop + invertido + barajado")
    print(f"4. G2 capa 3       {len(l3)} llamadas")
    print(f"   TOTAL MAX      {spec['total_calls_max']} llamadas\n")

    if not subgate_ok:
        print("SUB-PUERTA DE NEUTRALIZACION FALLA — no ejecutar")
        return 1

    if args.dry_run:
        (args.out_dir / "G2_G3b_spec_dryrun.json").write_text(
            json.dumps({**spec, "sample_g3b_prompt": pairs[0]["prompt"][:1200]},
                       indent=1, ensure_ascii=False), encoding="utf-8")
        print("--- DRY RUN: ninguna llamada. Prompt de G3(b) neutralizado (recortado) ---\n")
        print(pairs[0]["prompt"][:700])
        print(f"\n-> {args.out_dir / 'G2_G3b_spec_dryrun.json'}")
        return 0

    # ---- LIVE: G3(b) only. Frozen evaluator, reusing the project's config ----
    from dotenv import load_dotenv
    load_dotenv()
    sys.path.insert(0, str(ROOT / "scripts"))
    from thematic_coding import EVALUATOR_CONFIGS, _client_for_evaluator, _generate_with_fallback

    cfg = EVALUATOR_CONFIGS["gemininext"]          # frozen_evaluation_spec.md §2
    client = _client_for_evaluator(cfg)
    print(f"G3(b) EN VIVO - evaluador {cfg['model']} (config congelada)\n")

    answers, unparsed = [], 0
    for i, pair in enumerate(pairs, start=1):
        resp = _generate_with_fallback(client, model=cfg["model"], contents=pair["prompt"])
        raw = (getattr(resp, "text", "") or "").strip()
        m = re.search(r'"choice"\s*:\s*"([AB])"', raw) or re.search(r"([AB])", raw)
        if not m:
            unparsed += 1
            answers.append({**{k: v for k, v in pair.items() if k != "prompt"},
                            "raw": raw[:120], "chose_male": None})
            print(f"  [{i:2d}/24] {pair['agent_id']:16s} SIN PARSEAR: {raw[:60]}")
            continue
        chose = m.group(1)
        chose_male = (chose == pair["male_branch_shown_as"])   # de-map the counterbalance
        answers.append({**{k: v for k, v in pair.items() if k != "prompt"},
                        "raw_choice": chose, "chose_male": chose_male})
        print(f"  [{i:2d}/24] {pair['agent_id']:16s} c{pair['candidate_index']} "
              f"eligio {chose} (varon estaba en {pair['male_branch_shown_as']}) -> "
              f"{'MASCULINO' if chose_male else 'femenino'}")

    scored = [a for a in answers if a["chose_male"] is not None]
    n_male = sum(1 for a in scored if a["chose_male"])
    by_cell = {}
    for a in scored:
        by_cell.setdefault(a["agent_id"], []).append(a["chose_male"])
    cell_major = sum(1 for v in by_cell.values() if sum(v) > len(v) / 2)

    fired = n_male >= 17
    print(f"\n  binomial 24 pares : {n_male}/{len(scored)} eligieron la rama masculina "
          f"(umbral 17)  -> {'DISPARA' if fired else 'no dispara'}")
    print(f"  mayoria por celda : {cell_major}/{len(by_cell)}")
    if unparsed:
        print(f"  sin parsear: {unparsed}")

    (args.out_dir / "G3b_result.json").write_text(json.dumps({
        "gate": "G3(b)", "evaluator": cfg["model"],
        "neutralised": True, "counterbalanced": True, "seed": COUNTERBALANCE_SEED,
        "n_scored": len(scored), "n_chose_male": n_male, "threshold": 17,
        "fired": fired, "cells_majority_male": cell_major, "n_cells": len(by_cell),
        "unparsed": unparsed,
        "pre_declared_caveat": spec["g3b"]["pre_declared_caveat"],
        "answers": answers,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {args.out_dir / 'G3b_result.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
