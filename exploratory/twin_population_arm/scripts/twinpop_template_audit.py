#!/usr/bin/env python3
"""
twinpop_template_audit.py — independent diagnostic: how much of the narrative
similarity comes from the shared generation template?

The 8 twin narratives are produced by one prompt with three fixed fields, so they
are obliged to share genre and opening formulas. That confound sits underneath
the narrative-level distance and must be sized before anyone reads that distance
as evidence about the personas.

Procedure (ADENDUM v5 entry 11):
  1. Identify a priori the structural elements the renderer introduces.
  2. Compute the narrative distance on the FULL text.
  3. Recompute excluding ONLY those structural elements.
  4. Substantive content is NOT removed merely for being repeated.
  5. Keep both results; document exactly what was excluded.

This is a diagnostic. It does NOT replace R4 and cannot become a selection gate.

No API calls.

Usage:
    py scripts/twinpop_template_audit.py --out-dir analysis/production_evaluation/twinpop
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from collapse_metric import build_tfidf, cosine_distance  # noqa: E402

# ---------------------------------------------------------------------------
# Structural elements, fixed A PRIORI from the frozen prompt (entry 1) and the
# rendering path — NOT from looking at which n-grams happened to recur.
#
# The prompt dictates: three paragraphs, one per field, plain British English,
# neutral third-person-free description. What that produces structurally is a
# positional opener per field plus the connectives the genre imposes. Those are
# listed here. Occupational and household vocabulary is SUBSTANTIVE and stays,
# however often it recurs.
# ---------------------------------------------------------------------------
STRUCTURAL_PATTERNS = [
    # positional openers the three-field format forces
    r"^\s*(a|an)\s+[a-z\-]+-year-old\b",
    r"^\s*home is\b", r"^\s*the home is\b",
    r"^\s*weekdays?\s+(follow|are|tend)\b",
    r"^\s*days?\s+(follow|are)\b",
    r"^\s*the household consists of\b",
    r"^\s*weekends?\s+(leave|are|tend|allow)\b",
    # genre connectives imposed by "neutral description, not speech"
    r"\bthe role (carries|involves|places)\b",
    r"\bthe work(place)? (is|sits|involves)\b",
    r"\bthere (is|are) at least\b",
]
STRUCTURAL_RE = [re.compile(p, re.I | re.M) for p in STRUCTURAL_PATTERNS]


def strip_structural(text: str) -> tuple[str, list[str]]:
    removed = []
    out = text
    for rx in STRUCTURAL_RE:
        for m in rx.finditer(out):
            removed.append(m.group(0).strip())
        out = rx.sub(" ", out)
    return re.sub(r"\s+", " ", out).strip(), removed


def mean_pairwise(docs: list[str]) -> float:
    matrix, _ = build_tfidf(docs)
    n = len(docs)
    d = [cosine_distance(matrix[i], matrix[j]) for i in range(n) for j in range(i + 1, n)]
    return float(sum(d) / len(d)) if d else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    nar = json.loads((args.out_dir / "persona_narratives.json").read_text(encoding="utf-8"))
    selected = [r for r in nar["results"] if r["branch"] == "real" and r["candidate_index"] == 1]
    # N-3: joining the three fields with a SPACE put them all on one line, so with
    # re.M the "^" anchor only matched at position 0 and the positional openers —
    # the largest structural component of the list — never executed at all
    # (10 occurrences instead of 21). Each field is its own paragraph; join on \n.
    full = ["\n".join(r["narrative"].values()) for r in selected]

    stripped, all_removed = [], []
    for t in full:
        s, rem = strip_structural(t)
        stripped.append(s)
        all_removed.extend(rem)

    # descriptive: which 4-grams recur across narratives (NOT used to exclude —
    # shown so the reader can judge whether the a priori list missed anything)
    grams = Counter()
    for t in full:
        w = re.findall(r"[a-z\-']+", t.lower())
        grams.update(" ".join(w[i:i + 4]) for i in range(len(w) - 3))
    recurring = [(g, c) for g, c in grams.most_common(25) if c >= 4]

    d_full = mean_pairwise(full)
    d_strip = mean_pairwise(stripped)
    words_full = sum(len(t.split()) for t in full)
    words_strip = sum(len(t.split()) for t in stripped)

    print("AUDITORIA DE EFECTO DE PLANTILLA (diagnostico, no puerta)\n")
    print(f"  distancia media por pares, texto COMPLETO   : {d_full:.4f}")
    print(f"  distancia media por pares, SIN estructurales: {d_strip:.4f}")
    print(f"  delta: {d_strip - d_full:+.4f}")
    print(f"  palabras: {words_full} -> {words_strip} "
          f"({(words_full - words_strip) / words_full * 100:.1f}% excluido)\n")
    print(f"  elementos estructurales eliminados ({len(all_removed)} ocurrencias):")
    for frag, c in Counter(all_removed).most_common():
        print(f"     x{c:2d}  {frag[:70]}")
    print(f"\n  [descriptivo, NO excluido] 4-gramas que recurren en >=4 de 8:")
    if not recurring:
        print("     ninguno")
    for g, c in recurring:
        print(f"     x{c:2d}  {g}")

    out = {
        "diagnostic": "template_effect",
        "is_gate": False,
        "note": ("Diagnostic only. Does not replace R4 and must not become a selection "
                 "gate retrospectively."),
        "structural_patterns_fixed_a_priori": STRUCTURAL_PATTERNS,
        "distance_full_text": round(d_full, 4),
        "distance_structural_removed": round(d_strip, 4),
        "delta": round(d_strip - d_full, 4),
        "words_full": words_full, "words_after_strip": words_strip,
        "removed_occurrences": Counter(all_removed).most_common(),
        "recurring_4grams_reported_not_removed": recurring,
        "metric": "project build_tfidf + cosine_distance, shared space over the 8 narratives",
    }
    (args.out_dir / "template_effect_audit.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n-> {args.out_dir / 'template_effect_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
