"""
Intra-turn semantic dispersion — formalises the coder's observation that
synthetic turns "cover every side at once, address the extremes, and land on a
balance", while human turns take fewer points at a time with clearer positions.

Independent of the D1 dictionary: this measures geometry, not vocabulary. Where
the two agree, the observation has convergent support from a lexical and a
geometric instrument.

Per participant turn with >= MIN_SENTS sentences:
  spread          mean pairwise cosine DISTANCE between its sentence embeddings
  max_pairwise    the widest distance inside the turn -- "does it hold two far
                  apart positions at once?" (the 'extremes' part of the claim)
  centroid_disp   mean distance of each sentence to the turn centroid
  closing_central closeness of the LAST sentence to the centroid, minus the
                  average closeness. Positive = the turn ends nearer its own
                  middle than it travelled -- the 'lands on a balance' part.

Sentence count is the obvious confound: a 15-sentence turn has more room to
spread than a 3-sentence one, and synthetic turns are ~3.4x longer (median 17
sentences vs 5). Views reported together:
  ALL       every eligible turn, no matching
  MATCHED   turns inside a sentence-count band populated on BOTH sides
  FIRST3    first 3 sentences of every eligible turn -- identical rule per side

The matching bands are 6-9 and 6-14 sentences, chosen from the observed
distributions, not a priori: human turns run 3-21 sentences and synthetic ones
6-38, so the two corpora overlap only from 6 up. The 6-9 band is where the
counts are near-balanced (48 human vs 53 synthetic). A first pass used a 3-5
band, which contains 101 human turns and ZERO synthetic ones -- that emptiness
is itself a result and is reported: the corpora are not matchable at the short
end, because synthetic turns are never short.

Model: paraphrase-multilingual-mpnet-base-v2 (cached). No API call.

Usage:
    py scripts/consensus_intraturn_dispersion.py
"""

from __future__ import annotations

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consensus_dynamics_metrics import (  # noqa: E402
    MODEL_NAME, build_turns, sentences,
)

_OUT = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_dynamics"
MIN_SENTS = 3
MATCH_BANDS = [(6, 9), (6, 14)]
EMPTY_BAND = (3, 5)   # reported for the record: 101 human turns, 0 synthetic


def _turn_stats(E: np.ndarray) -> dict[str, float]:
    n = len(E)
    d = 1.0 - (E @ E.T)
    iu = np.triu_indices(n, k=1)
    pair = d[iu]
    cen = E.mean(axis=0)
    nrm = np.linalg.norm(cen)
    cen = cen / nrm if nrm else cen
    to_cen = 1.0 - (E @ cen)
    return {
        "spread": float(pair.mean()),
        "max_pairwise": float(pair.max()),
        "centroid_disp": float(to_cen.mean()),
        "closing_central": float(to_cen.mean() - to_cen[-1]),
    }


def _load_cached() -> list[dict] | None:
    p = _OUT / "intraturn_dispersion_by_turn.csv"
    if not p.exists():
        return None
    rows = []
    for r in csv.DictReader(p.open(encoding="utf-8")):
        for k, v in list(r.items()):
            if k in ("n_sentences", "n_words", "section_index"):
                r[k] = int(v)
            elif k not in ("unit", "side", "fg", "condition", "speaker"):
                r[k] = float(v) if v not in ("", None) else None
        rows.append(r)
    return rows


def main() -> None:
    if "--reuse" in sys.argv:
        rows = _load_cached()
        if rows is None:
            raise SystemExit("no per-turn CSV to reuse; run without --reuse")
        print(f"reusing {len(rows)} turns already embedded")
        _report(rows)
        return

    turns, _ = build_turns()
    sent_lists = [sentences(t["text"]) for t in turns]
    keep = [i for i, s in enumerate(sent_lists) if len(s) >= MIN_SENTS]
    print(f"eligible turns (>={MIN_SENTS} sentences): {len(keep)} of {len(turns)}")
    for side in ("human", "synthetic"):
        k = [i for i in keep if turns[i]["side"] == side]
        ns = [len(sent_lists[i]) for i in k]
        print(f"  {side:<10} {len(k):>4}  median sentences/turn {statistics.median(ns):.0f}")

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)

    flat, spans = [], {}
    for i in keep:
        spans[i] = (len(flat), len(flat) + len(sent_lists[i]))
        flat += sent_lists[i]
    print(f"encoding {len(flat)} sentences ...", flush=True)
    E = model.encode(flat, convert_to_numpy=True, batch_size=64,
                     normalize_embeddings=True, show_progress_bar=False)

    rows = []
    for i in keep:
        a, b = spans[i]
        t = turns[i]
        n_s = b - a
        rec = {"unit": t["unit"], "side": t["side"], "fg": t["fg"],
               "condition": t["condition"], "section_index": t["section_index"],
               "speaker": t["speaker"], "n_sentences": n_s,
               "n_words": len(t["text"].split())}
        for tag, sl in (("all", E[a:b]), ("first3", E[a:a + 3])):
            if len(sl) >= 3:
                for k, v in _turn_stats(sl).items():
                    rec[f"{k}_{tag}"] = round(v, 4)
        rows.append(rec)

    with (_OUT / "intraturn_dispersion_by_turn.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    _report(rows)
    print(f"\nwrote {_OUT / 'intraturn_dispersion_by_turn.csv'}")


METRICS = [("spread_all", "mean intra-turn dispersion"),
           ("max_pairwise_all", "maximum intra-turn distance (extremes)"),
           ("centroid_disp_all", "dispersion around the turn centroid"),
           ("closing_central_all", "centrality of the closing sentence (lands in the middle)"),
           ("spread_first3", "dispersion, first 3 sentences"),
           ("max_pairwise_first3", "maximum distance, first 3 sentences")]


def _table(vrows: list[dict]) -> list[str]:
    """Aggregate per (fg, condition) so each side yields 5 values -- one per FG.

    Aggregating per RUN would give the synthetic side ~2 turns per unit inside a
    matched band, which is too thin to average; pooling runs within FG x
    condition keeps the paired structure (5 human values vs 5 per condition).
    """
    out = ["| Metric | Human mean [min-max by FG] | Enriched | Demo-only | "
           "Inside envelope |", "|---|---|---|---|---|"]
    for key, label in METRICS:
        cells_by_group: dict[tuple[str, str], list[float]] = defaultdict(list)
        for r in vrows:
            if r.get(key) is not None:
                cells_by_group[(r["fg"], r["condition"])].append(r[key])
        gm = {g: statistics.mean(v) for g, v in cells_by_group.items() if v}
        hv = [v for (fg, c), v in gm.items() if c == "human"]
        if len(hv) < 2:
            continue
        lo, hi = min(hv), max(hv)
        cells, inside = [], []
        for c in ("enriched", "demographics-only"):
            cv = [v for (fg, cc), v in gm.items() if cc == c]
            if not cv:
                cells.append("no data")
                inside.append(None)
                continue
            m = statistics.mean(cv)
            cells.append(f"{m:.3f}")
            inside.append(lo <= m <= hi)
        known = [i for i in inside if i is not None]
        flag = ("no overlap" if not known
                else "yes" if all(known) else "no" if not any(known) else "partial")
        out.append(f"| {label} | {statistics.mean(hv):.3f} [{lo:.3f}-{hi:.3f}] "
                   f"| {cells[0]} | {cells[1]} | {flag} |")
    return out


def _report(rows: list[dict]) -> None:
    counts = {s: sorted(r["n_sentences"] for r in rows if r["side"] == s)
              for s in ("human", "synthetic")}
    eb = {s: sum(1 for n in counts[s] if EMPTY_BAND[0] <= n <= EMPTY_BAND[1])
          for s in counts}

    lines = [
        "# Intra-turn semantic dispersion",
        "",
        "*Namespace CONSENSUS_DYNAMICS_EXPLORATORY. Zero API calls.*",
        f"*Model `{MODEL_NAME}`. Turns with >={MIN_SENTS} sentences.*",
        "",
        "Formalises, geometrically and independently of the D1 dictionary, the coder's observation:",
        "synthetic turns traverse several positions at once and land on a midpoint; human turns take",
        "fewer positions and hold a clearer stance.",
        "",
        "The human envelope is the [min-max] range of the five human groups.",
        "",
        "## Distribution of sentences per turn",
        "",
        "| Side | n turns | min | p25 | median | p75 | max |",
        "|---|---|---|---|---|---|---|",
    ]
    for s, n in counts.items():
        q = lambda p: n[int(p * (len(n) - 1))]  # noqa: E731
        lines.append(f"| {s} | {len(n)} | {min(n)} | {q(.25)} | "
                     f"{statistics.median(n):.0f} | {q(.75)} | {max(n)} |")
    lines += [
        "",
        f"**The two corpora only overlap from 6 sentences upward.** The "
        f"{EMPTY_BAND[0]}–{EMPTY_BAND[1]} band contains {eb['human']} human
"
        f"turns and {eb['synthetic']} synthetic ones: at the short end they are not matchable, "
        "because synthetic turns
are never short. That limits what can be controlled by "
        "matching and what only by truncation.",
    ]

    lines += ["", "## ALL (unmatched)", ""]
    hu = sum(1 for r in rows if r["side"] == "human")
    lines += [f"*turns: human {hu}, synthetic {len(rows) - hu}*", ""]
    lines += _table(rows)

    for band in MATCH_BANDS:
        sub = [r for r in rows if band[0] <= r["n_sentences"] <= band[1]]
        hu = sum(1 for r in sub if r["side"] == "human")
        lines += ["", f"## MATCHED {band[0]}–{band[1]} sentences", "",
                  f"*turns: human {hu}, synthetic {len(sub) - hu}*", ""]
        lines += _table(sub)

    (_OUT / "INTRATURN_DISPERSION_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {_OUT / 'INTRATURN_DISPERSION_RESULTS.md'}")


if __name__ == "__main__":
    main()
