"""
Consensus dynamics — embedding metrics (namespace: CONSENSUS_DYNAMICS_EXPLORATORY).

Three things in one pass over the same turn-level data:

  MATOR   Replication of Mator et al. (2025) Table 4, plus the two checks they
          could not run: the human-human envelope of their own metric (they had
          one human group; this corpus has five) and a length control.
  D4      Anchoring to the first speaker -- does the group converge on whoever
          spoke first? Distinguishes negotiated consensus from echo.
  D5      Movement asymmetry -- who actually moves? Displacement of each
          participant's position within a section, and whether it heads toward
          the group centroid.

Three turn representations, reported side by side, because the difference
between them IS the finding:

  R1 naive      encode the turn as one string. The encoder silently truncates at
                max_seq_length=128 tokens (~90-100 words), so a 230-word synthetic
                turn is represented by its first ~40%. This is what an
                unexamined replication computes.
  R2 pooled     split into sentences, encode each, mean-pool. Represents the
                WHOLE turn regardless of length. The honest representation.
  R3 matched    truncate every turn on BOTH sides to W words, W = median human
                participant turn length for that FG, then encode. Identical rule
                per side, so it isolates length.

If Mator-style "agreement" collapses from R1/R2 to R3, the metric was measuring
verbosity and completeness, not consensus.

Model: paraphrase-multilingual-mpnet-base-v2 (already the project's embedding
model, already cached). Deterministic inference, no API call.

TWO CAVEATS BEFORE RE-RUNNING THIS SCRIPT:

1. `MATOR_D4_D5_RESULTS.md` carries hand-authored sections ("What holds and what
   does not", "Limits of this layer") that this script does NOT generate. A
   re-run overwrites the file and drops them. Preserve them before re-running.
2. `build_turns()` enumerates runs by listing `comparable_transcripts/`, which
   now also holds the twin-population arm, and `_condition_of()` labels anything
   without `demoonly` as `enriched`. A re-run today would therefore fold that arm
   into the enriched condition mean. The committed outputs predate those
   directories and are unaffected. `scripts/mator_bertscore_metrics.py::load_units`
   shows the safe pattern: read the run list from `frozen_evaluator_inputs.json`
   and SHA-verify every input.

Usage:
    py scripts/consensus_dynamics_metrics.py
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consensus_dynamics_events import (  # noqa: E402
    _HUMAN_DIR, _SESSION_LOGS, _COMPARABLE, _condition_of, _is_moderator,
)
from tier2b_segmentation import (  # noqa: E402
    comparable_sections, load_guide_sections,
    segment_human_by_guide, segment_synthetic_by_guide,
)

_OUT = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_dynamics"
MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'‘“])|\n+")


def sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENT.split(text or "") if s and s.strip()]
    return parts or ([text.strip()] if text and text.strip() else [])


def truncate_words(text: str, w: int) -> str:
    return " ".join((text or "").split()[:w])


# ---------------------------------------------------------------------------
# Turn-level corpus
# ---------------------------------------------------------------------------

def build_turns() -> tuple[list[dict], dict[int, str]]:
    """One record per participant turn inside a comparable section."""
    runs = sorted(p.name for p in _COMPARABLE.iterdir() if p.is_dir())
    turns: list[dict] = []
    human_done: set[str] = set()
    questions: dict[int, str] = {}

    for run in runs:
        fg = re.search(r"(fg\d)", run).group(1)
        guide_src = _SESSION_LOGS / run / "session_state_initial.json"
        if not questions:
            for s in load_guide_sections(guide_src):
                questions[s["section_index"]] = s.get("scripted_question", "")

        h_seg = segment_human_by_guide(_HUMAN_DIR / fg / "transcript.json", guide_src)
        s_seg = segment_synthetic_by_guide(_SESSION_LOGS / run / "transcript.json", guide_src)
        comparable, _ = comparable_sections(h_seg, s_seg)

        s_entries = json.loads((_SESSION_LOGS / run / "transcript.json").read_text(encoding="utf-8"))
        for sidx in comparable:
            for order, i in enumerate(sorted(s_seg.sections[sidx].entry_indices)):
                e = s_entries[i]
                if _is_moderator(e):
                    continue
                turns.append({
                    "unit": run, "side": "synthetic", "fg": fg,
                    "condition": _condition_of(run), "section_index": sidx,
                    "speaker": e.get("speaker_id", ""), "order": order,
                    "text": e.get("content", ""),
                    "selection_mode": e.get("selection_mode", "") or "",
                })

        if fg not in human_done:
            h_entries = json.loads((_HUMAN_DIR / fg / "transcript.json").read_text(encoding="utf-8"))
            union = set(comparable)
            for other in runs:
                if re.search(r"(fg\d)", other).group(1) != fg:
                    continue
                o = segment_synthetic_by_guide(
                    _SESSION_LOGS / other / "transcript.json",
                    _SESSION_LOGS / other / "session_state_initial.json")
                c2, _ = comparable_sections(h_seg, o)
                union |= set(c2)
            for sidx in sorted(union):
                for order, i in enumerate(sorted(h_seg.sections[sidx].entry_indices)):
                    e = h_entries[i]
                    if _is_moderator(e):
                        continue
                    turns.append({
                        "unit": fg, "side": "human", "fg": fg, "condition": "human",
                        "section_index": sidx, "speaker": e.get("speaker_id", ""),
                        "order": order, "text": e.get("content", ""), "selection_mode": "",
                    })
            human_done.add(fg)
    return turns, questions


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def embed_all(turns: list[dict], questions: dict[int, str]) -> dict:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    print(f"model {MODEL_NAME}  max_seq_length={model.max_seq_length}")

    # W per FG = median human participant turn length in that FG
    w_by_fg = {}
    for fg in sorted({t["fg"] for t in turns}):
        hw = [len(t["text"].split()) for t in turns if t["side"] == "human" and t["fg"] == fg]
        w_by_fg[fg] = int(statistics.median(hw)) if hw else 40
    print("length-match W per FG:", w_by_fg)

    r1_texts = [t["text"] for t in turns]
    r3_texts = [truncate_words(t["text"], w_by_fg[t["fg"]]) for t in turns]
    sent_lists = [sentences(t["text"]) for t in turns]
    flat, spans = [], []
    for sl in sent_lists:
        spans.append((len(flat), len(flat) + len(sl)))
        flat += sl

    def enc(xs, tag):
        print(f"  encoding {tag}: {len(xs)} strings ...", flush=True)
        return model.encode(xs, convert_to_numpy=True, batch_size=32,
                            normalize_embeddings=True, show_progress_bar=False)

    e1 = enc(r1_texts, "R1 naive")
    e3 = enc(r3_texts, "R3 length-matched")
    ef = enc(flat, "R2 sentences")
    e2 = np.zeros_like(e1)
    for i, (a, b) in enumerate(spans):
        v = ef[a:b].mean(axis=0) if b > a else e1[i]
        n = np.linalg.norm(v)
        e2[i] = v / n if n else v

    q_idx = sorted(questions)
    eq = enc([questions[i] for i in q_idx], "guide questions")
    return {"R1": e1, "R2": e2, "R3": e3, "W": w_by_fg,
            "questions": {i: eq[k] for k, i in enumerate(q_idx)},
            "max_seq_length": model.max_seq_length}


def _cos(a, b) -> float:
    return float(np.dot(a, b))


def _gini(xs: list[float]) -> float:
    xs = sorted(max(0.0, x) for x in xs)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2 * cum) / (n * sum(xs)) - (n + 1) / n


def _spearman(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 3:
        return float("nan")

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(x), rank(y)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else float("nan")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute(turns: list[dict], emb: dict) -> list[dict]:
    by_unit: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(turns):
        by_unit[t["unit"]].append(i)

    rows = []
    for unit, idxs in sorted(by_unit.items()):
        meta = turns[idxs[0]]
        rec = {"unit": unit, "side": meta["side"], "fg": meta["fg"],
               "condition": meta["condition"], "n_turns": len(idxs)}

        by_sec: dict[int, list[int]] = defaultdict(list)
        for i in idxs:
            by_sec[turns[i]["section_index"]].append(i)
        for v in by_sec.values():
            v.sort(key=lambda i: turns[i]["order"])

        for rep in ("R1", "R2", "R3"):
            E = emb[rep]
            # --- MATOR 1: agreement = similarity between consecutive responses
            cons = [_cos(E[a], E[b])
                    for v in by_sec.values() for a, b in zip(v, v[1:])]
            rec[f"mator_agreement_{rep}"] = round(float(np.mean(cons)), 4) if cons else ""
            rec[f"mator_agreement_n_{rep}"] = len(cons)

            # --- MATOR 2: response similarity between participants, per section
            sims = []
            for v in by_sec.values():
                for a in range(len(v)):
                    for b in range(a + 1, len(v)):
                        if turns[v[a]]["speaker"] != turns[v[b]]["speaker"]:
                            sims.append(_cos(E[v[a]], E[v[b]]))
            rec[f"mator_between_participants_{rep}"] = round(float(np.mean(sims)), 4) if sims else ""

            # --- MATOR 3: relevance of response to the moderator's question
            rel = [_cos(E[i], emb["questions"][turns[i]["section_index"]])
                   for i in idxs if turns[i]["section_index"] in emb["questions"]]
            rec[f"mator_relevance_{rep}"] = round(float(np.mean(rel)), 4) if rel else ""

            # --- D4: anchoring to the first speaker of each section
            anch, rhos = [], []
            for v in by_sec.values():
                if len(v) < 4:
                    continue
                a0 = v[0]
                pos, sim = [], []
                for p, i in enumerate(v[1:], start=1):
                    if turns[i]["speaker"] == turns[a0]["speaker"]:
                        continue
                    pos.append(float(p))
                    sim.append(_cos(E[i], E[a0]))
                if len(sim) >= 3:
                    anch.append(float(np.mean(sim)))
                    rhos.append(_spearman(pos, sim))
            rec[f"d4_anchor_similarity_{rep}"] = round(float(np.mean(anch)), 4) if anch else ""
            rr = [r for r in rhos if not np.isnan(r)]
            rec[f"d4_rho_position_anchor_{rep}"] = round(float(np.mean(rr)), 4) if rr else ""
            rec[f"d4_n_sections_{rep}"] = len(anch)

            # --- D5: movement of each participant within a section
            disp, toward = [], []
            for v in by_sec.values():
                spk: dict[str, list[int]] = defaultdict(list)
                for i in v:
                    spk[turns[i]["speaker"]].append(i)
                if len(spk) < 2:
                    continue
                for s, iv in spk.items():
                    if len(iv) < 2:
                        continue
                    others = [i for i in v if turns[i]["speaker"] != s]
                    if not others:
                        continue
                    cen = E[others].mean(axis=0)
                    n = np.linalg.norm(cen)
                    if not n:
                        continue
                    cen = cen / n
                    first, last = E[iv[0]], E[iv[-1]]
                    disp.append(1.0 - _cos(first, last))
                    toward.append(_cos(last, cen) - _cos(first, cen))
            rec[f"d5_displacement_mean_{rep}"] = round(float(np.mean(disp)), 4) if disp else ""
            rec[f"d5_displacement_gini_{rep}"] = round(_gini(disp), 4) if disp else ""
            rec[f"d5_prop_moving_toward_{rep}"] = (
                round(sum(1 for t in toward if t > 0) / len(toward), 4) if toward else "")
            rec[f"d5_n_participant_sections_{rep}"] = len(disp)
        rows.append(rec)
    return rows


# ---------------------------------------------------------------------------

def summarise(rows: list[dict]) -> list[str]:
    out: list[str] = []
    human = [r for r in rows if r["side"] == "human"]
    conds = ["enriched", "demographics-only"]

    def agg(sub, key):
        vs = [r[key] for r in sub if r.get(key) not in ("", None)]
        return vs

    metrics = [
        ("mator_agreement", "Mator: agreement (similarity between consecutive responses)"),
        ("mator_between_participants", "Mator: similarity between participants"),
        ("mator_relevance", "Mator: relevance to the question"),
        ("d4_anchor_similarity", "D4: mean similarity to the first speaker"),
        ("d4_rho_position_anchor", "D4: rho(position, similarity to the first speaker)"),
        ("d5_displacement_mean", "D5: mean displacement"),
        ("d5_displacement_gini", "D5: Gini of displacement"),
        ("d5_prop_moving_toward", "D5: proportion moving toward the centroid"),
    ]

    for rep, tag in (("R1", "R1 naive (encoder truncates at 128 tokens)"),
                     ("R2", "R2 sentence-pooled (whole turn)"),
                     ("R3", "R3 length-matched (same rule on both sides)")):
        out.append(f"\n### {tag}\n")
        out.append("| Metric | Human mean [min-max] | Enriched | Demo-only | "
                   "Synthetic inside human envelope |")
        out.append("|---|---|---|---|---|")
        for key, label in metrics:
            k = f"{key}_{rep}"
            hv = agg(human, k)
            if not hv:
                continue
            hlo, hhi = min(hv), max(hv)
            cells = []
            inside = []
            for c in conds:
                cv = agg([r for r in rows if r["condition"] == c], k)
                m = statistics.mean(cv) if cv else float("nan")
                cells.append(f"{m:.3f}")
                inside.append(hlo <= m <= hhi)
            flag = ("yes" if all(inside) else "no" if not any(inside) else "partial")
            out.append(f"| {label} | {statistics.mean(hv):.3f} [{hlo:.3f}-{hhi:.3f}] "
                       f"| {cells[0]} | {cells[1]} | {flag} |")
    return out


def main() -> None:
    _OUT.mkdir(parents=True, exist_ok=True)
    turns, questions = build_turns()
    print(f"turns: {len(turns)}  "
          f"(human {sum(1 for t in turns if t['side']=='human')}, "
          f"synthetic {sum(1 for t in turns if t['side']=='synthetic')})")

    emb = embed_all(turns, questions)
    rows = compute(turns, emb)

    fields = list(rows[0].keys())
    with (_OUT / "mator_d4_d5_by_unit.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# Automatic consensus metrics — Mator replicated, D4 and D5",
        "",
        "*Namespace CONSENSUS_DYNAMICS_EXPLORATORY. Zero API calls.*",
        f"*Modelo: `{MODEL_NAME}`, max_seq_length={emb['max_seq_length']} tokens.*",
        f"*Units: 5 human groups, 30 synthetic sessions. W per FG: {emb['W']}.*",
        "",
        "The human envelope is the [min-max] range of the five human groups: the question",
        "is not whether the synthetic side differs from the human mean, but whether it",
        "falls outside the natural variation between human groups. Mator et al. had a",
        "single human group and could not compute it.",
    ] + summarise(rows)
    (_OUT / "MATOR_D4_D5_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(summarise(rows)))
    print(f"\nwrote {_OUT / 'mator_d4_d5_by_unit.csv'}")
    print(f"wrote {_OUT / 'MATOR_D4_D5_RESULTS.md'}")


if __name__ == "__main__":
    main()
