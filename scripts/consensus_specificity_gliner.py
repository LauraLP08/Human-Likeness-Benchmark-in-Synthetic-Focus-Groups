"""
Specificity via GLiNER — the framework §H indicator with a real NER model.

Why GLiNER rather than spaCy. spaCy's NER emits a fixed OntoNotes label set, so
the construct has to be bent to fit the model. GLiNER takes entity types as
natural-language prompts, so the label set is written straight from the study's
own definition of specificity ("times, places, actions, people, decisions").
It also runs on CPU. The cost is that the prompts are a researcher choice, so
they are frozen here and listed in full -- the same discipline as the D1
dictionary.

This replaces the regex proxy in consensus_specificity_proxy.py, whose weakest
part was a ~60-word stoplist chosen by hand. Both are kept: the regex version is
the auditable floor, this one is the instrument. Where they disagree, report the
band.

Frozen decisions
----------------
MODEL       urchade/gliner_medium-v2.1
THRESHOLD   0.40
LABELS      see LABELS below
EXCLUDED    pronouns (GLiNER tags "I"/"we" as `named person` at ~0.8 confidence,
            and a pronoun is not a concrete detail); participant first names
            (naming who you are answering is direct address, not detail about
            the world -- and the two sides do it at very different rates).

Long turns are chunked to <= CHUNK_WORDS words on sentence boundaries. Feeding a
230-word synthetic turn to a model with a token limit would truncate it silently
and reintroduce the length confound this whole analysis exists to control.

Usage:
    py scripts/consensus_specificity_gliner.py
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from consensus_dynamics_metrics import sentences  # noqa: E402

_OUT = _REPO_ROOT / "analysis" / "production_evaluation" / "consensus_dynamics"
_ACTS = _OUT / "response_acts.csv"

MODEL = "urchade/gliner_medium-v2.1"
THRESHOLD = 0.40
CHUNK_WORDS = 80
FIRST_N_WORDS = 40

LABELS = [
    "place or location",
    "date or time",
    "named person",
    "brand or organisation",
    "amount of money",
    "number or quantity",
    "named food or dish",
]

_PRONOUNS = {
    "i", "we", "you", "he", "she", "it", "they", "me", "us", "him", "her",
    "them", "my", "our", "your", "his", "their", "myself", "everyone",
    "someone", "somebody", "anyone", "people", "everybody", "one", "us all",
}


def slug(label: str) -> str:
    """Column-safe key for a label.

    Must use the WHOLE label: 'named person' and 'named food or dish' both start
    with 'named', so keying on the first word silently collapsed them into one
    column and made the per-label breakdown report the same figure twice.
    """
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def chunks(text: str) -> list[str]:
    out, cur, n = [], [], 0
    for s in sentences(text):
        w = len(s.split())
        if cur and n + w > CHUNK_WORDS:
            out.append(" ".join(cur))
            cur, n = [], 0
        cur.append(s)
        n += w
    if cur:
        out.append(" ".join(cur))
    return out or [text]


def _keep(ent: dict, speaker_names: set[str]) -> bool:
    t = ent["text"].strip()
    if not t or t.lower() in _PRONOUNS:
        return False
    if t.split()[0] in speaker_names:
        return False
    return True


def _is_concrete(text: str) -> bool:
    """Proper noun or quantified -- 'Wetherspoons', '15 quid' vs bare 'pub'."""
    return bool(re.search(r"\d", text)) or bool(re.match(r"[A-Z][a-z]", text.strip()))


def main() -> None:
    rows = list(csv.DictReader(_ACTS.open(encoding="utf-8")))
    speaker_names = set()
    for r in rows:
        for n in (r["resp_speaker"], r["prev_speaker"]):
            if n and n != "Moderator":
                speaker_names.add(n.split()[0])

    from gliner import GLiNER
    model = GLiNER.from_pretrained(MODEL)
    print(f"modelo {MODEL}  umbral {THRESHOLD}  etiquetas {len(LABELS)}")
    print(f"nombres de participantes excluidos: {len(speaker_names)}")

    recs, ent_dump = [], []
    for i, r in enumerate(rows):
        if i % 100 == 0:
            print(f"  {i}/{len(rows)}", flush=True)
        full, head = r["resp_text"], " ".join(r["resp_text"].split()[:FIRST_N_WORDS])

        def run(text: str) -> list[dict]:
            found = []
            for ch in chunks(text):
                for e in model.predict_entities(ch, LABELS, threshold=THRESHOLD):
                    if _keep(e, speaker_names):
                        found.append(e)
            return found

        ents = run(full)
        head_ents = run(head)
        by_label = defaultdict(int)
        for e in ents:
            by_label[e["label"]] += 1
        concrete = [e for e in ents if _is_concrete(e["text"])]

        recs.append({
            "act_id": r["act_id"], "side": r["side"], "fg": r["fg"],
            "run": r["run"], "condition": r["condition"],
            "section_index": int(r["section_index"]),
            "resp_words": int(r["resp_words"]),
            "n_anchors": len(ents), "n_concrete": len(concrete),
            "specific_raw": int(len(ents) > 0),
            "specific_concrete": int(len(concrete) > 0),
            "specific_first40": int(len(head_ents) > 0),
            **{"n_" + slug(lab): by_label.get(lab, 0) for lab in LABELS},
        })
        for e in ents:
            ent_dump.append({"act_id": r["act_id"], "side": r["side"],
                             "text": e["text"], "label": e["label"],
                             "score": round(e["score"], 3),
                             "concrete": int(_is_concrete(e["text"]))})

    with (_OUT / "specificity_gliner_by_act.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(recs[0]))
        w.writeheader()
        w.writerows(recs)
    with (_OUT / "specificity_gliner_entities.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ent_dump[0]))
        w.writeheader()
        w.writerows(ent_dump)

    grp: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in recs:
        grp[(r["fg"], r["condition"])].append(r)

    views = [
        ("proportion of turns with >=1 anchor (raw)",
         lambda v: sum(r["specific_raw"] for r in v) / len(v)),
        ("proportion with >=1 concrete anchor (proper or quantified)",
         lambda v: sum(r["specific_concrete"] for r in v) / len(v)),
        ("anchors per 100 words",
         lambda v: 100 * sum(r["n_anchors"] for r in v) / sum(r["resp_words"] for r in v)),
        ("concrete anchors per 100 words",
         lambda v: 100 * sum(r["n_concrete"] for r in v) / sum(r["resp_words"] for r in v)),
        (f"proportion with >=1 anchor in the first {FIRST_N_WORDS} words",
         lambda v: sum(r["specific_first40"] for r in v) / len(v)),
    ] + [
        (f"  {lab} per 100 words",
         (lambda key: lambda v: 100 * sum(r["n_" + key] for r in v)
          / sum(r["resp_words"] for r in v))(slug(lab)))
        for lab in LABELS
    ]

    lines = [
        "# Specificity with GLiNER (framework §H)",
        "",
        "*Namespace CONSENSUS_DYNAMICS_EXPLORATORY. Local model, zero API calls.*",
        f"*`{MODEL}`, threshold {THRESHOLD}. Turns chunked to <= {CHUNK_WORDS} words "
        "at sentence boundaries so that no long turn is silently truncated.*",
        "",
        f"Labels (frozen, written from the study's own definition): "
        f"{', '.join('`' + lab + '`' for lab in LABELS)}.",
        "",
        "Excluded: pronouns (GLiNER labels \"I\"/\"we\" as `named person` with ~0.8 "
        "confidence) and participant names (naming the person you are answering is direct "
        "address, not detail about the world).",
        "",
        "\"Concrete anchor\" = the span is a proper noun or contains a number: this "
        "distinguishes `Wetherspoons` and `15 quid` from a generic `pub`.",
        "",
        "| Measure | Human mean [min-max by FG] | Enriched | Demo-only | Inside envelope |",
        "|---|---|---|---|---|",
    ]
    for label, fn in views:
        vals = {g: fn(v) for g, v in grp.items() if v}
        hv = [v for (fg, c), v in vals.items() if c == "human"]
        lo, hi = min(hv), max(hv)
        cells, inside = [], []
        for c in ("enriched", "demographics-only"):
            cv = [v for (fg, cc), v in vals.items() if cc == c]
            m = statistics.mean(cv)
            cells.append(m)
            inside.append(lo <= m <= hi)
        flag = "yes" if all(inside) else ("no" if not any(inside) else "partial")
        lines.append(f"| {label} | {statistics.mean(hv):.3f} [{lo:.3f}-{hi:.3f}] "
                     f"| {cells[0]:.3f} | {cells[1]:.3f} | {flag} |")

    (_OUT / "SPECIFICITY_GLINER_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    (_OUT / "specificity_gliner_spec.json").write_text(json.dumps({
        "model": MODEL, "threshold": THRESHOLD, "labels": LABELS,
        "chunk_words": CHUNK_WORDS, "excluded_pronouns": sorted(_PRONOUNS),
        "excluded_speaker_names": sorted(speaker_names),
    }, indent=2), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {_OUT / 'specificity_gliner_by_act.csv'}")
    print(f"wrote {_OUT / 'SPECIFICITY_GLINER_RESULTS.md'}")


if __name__ == "__main__":
    main()
