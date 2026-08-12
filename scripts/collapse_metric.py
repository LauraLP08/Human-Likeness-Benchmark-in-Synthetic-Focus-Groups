"""
Inter-agent distinctiveness ("persona-manifold collapse") metric.

Method (documented, fixed): TF-IDF lexical embedding, numpy-only.
This is a LEXICAL embedding, not a semantic/transformer embedding — chosen
because this environment has no installed sentence-transformer/sklearn
library and no configured OpenAI/Voyage embedding API key (only an
Anthropic key, and Anthropic does not expose a public embeddings endpoint).
This is a documented methodological limitation, not a silent substitution.

Metric definition:
  1. Build a TF-IDF vector space over all participant utterances in scope
     (one corpus per analysis — e.g. one run, or the real-transcript
     reference set).
  2. For each agent/speaker, compute the centroid (mean vector) of their
     utterance TF-IDF vectors.
  3. Inter-agent distinctiveness = mean pairwise cosine DISTANCE
     (1 - cosine similarity) between agent centroids. Higher = more
     distinct personas; collapse = this shrinks.
  4. Within-agent spread = mean cosine distance of each agent's own
     utterances to their own centroid. Distinguishes "agents converging
     toward each other" (collapse) from "every agent individually became
     vaguer" (rising within-agent spread without necessarily collapsing
     between agents).
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ɏ]+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def build_tfidf(documents: list[str]) -> tuple[np.ndarray, list[str]]:
    """
    documents: one string per utterance.
    Returns (matrix [n_docs x n_vocab], vocab list).
    """
    tokenized = [tokenize(d) for d in documents]
    vocab_counts: Counter = Counter()
    for toks in tokenized:
        vocab_counts.update(set(toks))
    vocab = sorted(vocab_counts.keys())
    vocab_index = {w: i for i, w in enumerate(vocab)}
    n_docs = len(documents)
    n_vocab = len(vocab)

    # document frequency -> idf
    df = np.array([vocab_counts[w] for w in vocab], dtype=float)
    idf = np.log((1 + n_docs) / (1 + df)) + 1.0

    matrix = np.zeros((n_docs, n_vocab), dtype=float)
    for i, toks in enumerate(tokenized):
        if not toks:
            continue
        tf = Counter(toks)
        length = len(toks)
        for w, c in tf.items():
            j = vocab_index[w]
            matrix[i, j] = (c / length) * idf[j]

    # L2-normalize each row
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms

    return matrix, vocab


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 1.0
    sim = float(np.dot(a, b) / denom)
    sim = max(-1.0, min(1.0, sim))
    return 1.0 - sim


def compute_collapse_metric(
    utterances_by_speaker: dict[str, list[str]],
) -> dict:
    """
    utterances_by_speaker: {speaker_name: [utterance_text, ...]}

    Returns:
      {
        "inter_agent_distance": float,   # mean pairwise centroid distance
        "within_agent_spread": {speaker: float, ...},
        "mean_within_agent_spread": float,
        "n_speakers": int,
        "n_utterances_total": int,
        "per_speaker_n": {speaker: int, ...},
      }
    """
    speakers = list(utterances_by_speaker.keys())
    all_docs = []
    doc_speaker = []
    for sp in speakers:
        for u in utterances_by_speaker[sp]:
            all_docs.append(u)
            doc_speaker.append(sp)

    if len(all_docs) < 2:
        return {"error": "insufficient utterances", "n_utterances_total": len(all_docs)}

    matrix, vocab = build_tfidf(all_docs)

    # Centroids
    centroids = {}
    speaker_doc_indices = {sp: [] for sp in speakers}
    for i, sp in enumerate(doc_speaker):
        speaker_doc_indices[sp].append(i)
    for sp in speakers:
        idxs = speaker_doc_indices[sp]
        if idxs:
            centroids[sp] = matrix[idxs].mean(axis=0)

    valid_speakers = [sp for sp in speakers if sp in centroids and len(speaker_doc_indices[sp]) > 0]

    # Inter-agent distance: mean pairwise cosine distance between centroids
    pair_distances = []
    for i in range(len(valid_speakers)):
        for j in range(i + 1, len(valid_speakers)):
            d = cosine_distance(centroids[valid_speakers[i]], centroids[valid_speakers[j]])
            pair_distances.append(d)
    inter_agent_distance = float(np.mean(pair_distances)) if pair_distances else float("nan")

    # Within-agent spread
    within_spread = {}
    for sp in valid_speakers:
        idxs = speaker_doc_indices[sp]
        if len(idxs) < 2:
            within_spread[sp] = float("nan")
            continue
        c = centroids[sp]
        dists = [cosine_distance(matrix[i], c) for i in idxs]
        within_spread[sp] = float(np.mean(dists))

    valid_within = [v for v in within_spread.values() if not math.isnan(v)]
    mean_within = float(np.mean(valid_within)) if valid_within else float("nan")

    return {
        "inter_agent_distance": inter_agent_distance,
        "within_agent_spread": within_spread,
        "mean_within_agent_spread": mean_within,
        "n_speakers": len(valid_speakers),
        "n_utterances_total": len(all_docs),
        "per_speaker_n": {sp: len(speaker_doc_indices[sp]) for sp in valid_speakers},
        "pair_distances": pair_distances,
    }
