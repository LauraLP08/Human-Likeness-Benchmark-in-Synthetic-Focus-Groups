"""
Mator "Agreement among participants" — STRICT participant-follows-participant.

Why this exists
---------------
`scripts/consensus_dynamics_metrics.py` already computes mean cosine similarity
between "consecutive" participant turns inside a guide section. But `v` there
holds participant turns only, so `zip(v, v[1:])` also pairs turns separated by
an intervening moderator turn. That bridging is not symmetric between sides:
the synthetic moderator intervenes far more often, so a much larger share of the
synthetic pairs bridge a moderator turn than of the human pairs. The headline
contrast is then computed over structurally different universes.

Mator describe "subsequent participant responses". This project already froze
exactly that universe: a RESPONSE ACT in
`analysis/production_evaluation/consensus_dynamics/response_acts.csv` is a
participant turn whose immediately preceding turn, within the same guide
section, is also a participant turn (`scripts/consensus_dynamics_events.py`).
This module scores that frozen universe and reports the bridge rate per side, so
the two figures can be read against each other instead of one silently standing
in for the other.

Method matches the existing layer exactly so the numbers are commensurable:

  R2 sentence-pooled  split the turn into sentences, encode each, mean-pool,
                      renormalise. Represents the whole turn regardless of
                      length. Primary.
  R3 length-matched   truncate both turns to W words, W = median human
                      participant turn length for that FG, then encode. Same
                      rule both sides, so it isolates length.

Model: `paraphrase-multilingual-mpnet-base-v2`, the project's embedding model,
already cached. Deterministic inference, no API call.

Usage:
    py scripts/mator_agreement_strict.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consensus_dynamics_metrics import sentences, truncate_words  # noqa: E402
from mator_bertscore_metrics import (  # noqa: E402
    _sha256, _words, length_match_widths, load_units,
)

_CONSENSUS = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_dynamics"
_ACTS = _CONSENSUS / "response_acts.csv"
_BRIDGED = _CONSENSUS / "mator_d4_d5_by_unit.csv"
_OUT = _REPO_ROOT / "analysis" / "production_evaluation" / "mator_comparable"

MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"


def load_acts() -> list[dict]:
    """The frozen strict participant-follows-participant universe.

    `unit` is normalised to the same key `mator_bertscore_by_unit.csv` uses:
    the physical run for synthetic rows, the FG id for human rows.
    """
    acts = []
    for r in csv.DictReader(_ACTS.open(encoding="utf-8")):
        acts.append({
            "unit": r["run"] or r["fg"],
            "side": r["side"],
            "fg": r["fg"],
            "condition": r["condition"],
            "section_index": int(r["section_index"]),
            "prev_text": r["prev_text"],
            "resp_text": r["resp_text"],
        })
    return acts


def embed(texts: list[str], model, width: int | None = None) -> np.ndarray:
    """Sentence-pooled encoding (R2), or truncated whole-turn encoding (R3)."""
    if width is not None:
        xs = [truncate_words(t, width) for t in texts]
        return model.encode(xs, convert_to_numpy=True, batch_size=32,
                            normalize_embeddings=True, show_progress_bar=False)

    sent_lists = [sentences(t) for t in texts]
    flat, spans = [], []
    for sl in sent_lists:
        spans.append((len(flat), len(flat) + len(sl)))
        flat += sl
    ef = model.encode(flat, convert_to_numpy=True, batch_size=32,
                      normalize_embeddings=True, show_progress_bar=False)
    out = np.zeros((len(texts), ef.shape[1]), dtype=ef.dtype)
    for i, (a, b) in enumerate(spans):
        v = ef[a:b].mean(axis=0) if b > a else np.zeros(ef.shape[1], dtype=ef.dtype)
        n = np.linalg.norm(v)
        out[i] = v / n if n else v
    return out


def bridge_rates(acts: list[dict]) -> dict:
    """How much of the bridged universe is NOT strict adjacency, per side.

    The bridged count is read from the file the existing layer wrote; the strict
    count is the frozen response-act universe. The gap is the asymmetry that
    makes the two figures non-interchangeable.
    """
    strict = defaultdict(int)
    for a in acts:
        strict[a["side"]] += 1
    bridged = defaultdict(int)
    for r in csv.DictReader(_BRIDGED.open(encoding="utf-8")):
        n = r.get("mator_agreement_n_R2") or ""
        if n:
            bridged["human" if r["side"] == "human" else "synthetic"] += int(n)
    out = {}
    for side in ("human", "synthetic"):
        b, s = bridged.get(side, 0), strict.get(side, 0)
        out[side] = {
            "bridged_pairs": b,
            "strict_pairs": s,
            "pct_of_bridged_that_bridge_a_moderator_turn":
                round(100.0 * (b - s) / b, 1) if b else None,
        }
    return out


def main() -> None:
    _OUT.mkdir(parents=True, exist_ok=True)

    acts = load_acts()
    print(f"strict response acts: {len(acts)} "
          f"(human {sum(1 for a in acts if a['side'] == 'human')}, "
          f"synthetic {sum(1 for a in acts if a['side'] == 'synthetic')})", flush=True)

    # W per FG from the same source the BERTScore layer uses, so both length
    # controls in this Mator layer mean the same thing.
    units, _ = load_units()
    widths = length_match_widths(units)
    print(f"length-match W per FG: {widths}", flush=True)

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)
    print(f"model {MODEL_NAME}  max_seq_length={model.max_seq_length}", flush=True)

    prev = [a["prev_text"] for a in acts]
    resp = [a["resp_text"] for a in acts]

    print("  encoding R2 (sentence-pooled) ...", flush=True)
    p2, r2 = embed(prev, model), embed(resp, model)

    print("  encoding R3 (length-matched) ...", flush=True)
    p3 = np.zeros_like(p2)
    r3 = np.zeros_like(r2)
    by_fg: dict[str, list[int]] = defaultdict(list)
    for i, a in enumerate(acts):
        by_fg[a["fg"]].append(i)
    for fg, idxs in by_fg.items():
        w = widths[fg]
        p3[idxs] = embed([prev[i] for i in idxs], model, width=w)
        r3[idxs] = embed([resp[i] for i in idxs], model, width=w)

    by_unit: dict[str, list[int]] = defaultdict(list)
    for i, a in enumerate(acts):
        by_unit[a["unit"]].append(i)

    rows = []
    for unit, idxs in sorted(by_unit.items()):
        meta = acts[idxs[0]]
        s2 = [float(np.dot(p2[i], r2[i])) for i in idxs]
        s3 = [float(np.dot(p3[i], r3[i])) for i in idxs]
        rows.append({
            "unit": unit,
            "side": meta["side"],
            "fg": meta["fg"],
            "condition": meta["condition"],
            "n_acts": len(idxs),
            "agreement_strict_R2": round(statistics.mean(s2), 4),
            "agreement_strict_R3": round(statistics.mean(s3), 4),
            "mean_prev_words": round(statistics.mean(_words(prev[i]) for i in idxs), 1),
            "mean_resp_words": round(statistics.mean(_words(resp[i]) for i in idxs), 1),
        })

    out_csv = _OUT / "mator_agreement_strict.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    spec = {
        "namespace": "_comparable_window",
        "evidence_class": "AUTOMATIC_PROXY_EXPLORATORY",
        "api_calls": 0,
        "model": MODEL_NAME,
        "max_seq_length": int(model.max_seq_length),
        "universe": "strict participant-follows-participant response acts",
        "universe_source": str(_ACTS.relative_to(_REPO_ROOT)),
        "universe_sha256": _sha256(_ACTS),
        "n_acts": len(acts),
        "w_by_fg": widths,
        "bridge_rates_vs_the_existing_bridged_layer": bridge_rates(acts),
        "n_units": len(rows),
    }
    (_OUT / "mator_agreement_strict_spec.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")

    br = spec["bridge_rates_vs_the_existing_bridged_layer"]
    print(f"\nbridge rate — human "
          f"{br['human']['pct_of_bridged_that_bridge_a_moderator_turn']}%, synthetic "
          f"{br['synthetic']['pct_of_bridged_that_bridge_a_moderator_turn']}%")
    for side in ("human", "enriched", "demographics-only"):
        vs2 = [r["agreement_strict_R2"] for r in rows if r["condition"] == side]
        vs3 = [r["agreement_strict_R3"] for r in rows if r["condition"] == side]
        if vs2:
            print(f"  {side:20s} R2 {statistics.mean(vs2):.3f}   "
                  f"R3 {statistics.mean(vs3):.3f}   (n={len(vs2)} units)")
    print(f"\nwrote {out_csv}")
    print(f"wrote {_OUT / 'mator_agreement_strict_spec.json'}")


if __name__ == "__main__":
    main()
