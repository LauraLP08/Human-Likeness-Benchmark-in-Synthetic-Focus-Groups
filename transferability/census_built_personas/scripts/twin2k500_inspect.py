"""
Inspect the structure of Twin-2K-500 personas.

Prints:
  - All block names in the persona_json
  - All QuestionID / QuestionText / QuestionType triples in the first participant
  - A frequency count of block names across the first N participants

This is read-only. It does not write any files.
"""
import json
from collections import Counter
from pathlib import Path
from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "twin2k500" / "raw"
SAMPLE_N = 20


def _parse_persona_json(raw):
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def main() -> None:
    ds = load_dataset(
        "LLM-Digital-Twin/Twin-2K-500",
        "full_persona",
        cache_dir=str(CACHE_DIR),
    )
    rows = ds["data"]

    first = rows[0]
    pj = _parse_persona_json(first["persona_json"])

    print(f"=== Participant {first['pid']} — full block + question inventory ===")
    for block in pj:
        bname = block.get("BlockName", "<no name>")
        btype = block.get("BlockType", "<no type>")
        questions = block.get("Questions", []) or []
        print(f"\n[Block] {bname}  ({btype})  — {len(questions)} questions")
        for q in questions:
            qid = q.get("QuestionID", "?")
            qtype = q.get("QuestionType", "?")
            qtext = (q.get("QuestionText", "") or "").replace("\n", " ").strip()
            if len(qtext) > 120:
                qtext = qtext[:117] + "..."
            print(f"  {qid}  [{qtype}]  {qtext}")

    print(f"\n=== Block frequency across first {SAMPLE_N} participants ===")
    block_counter = Counter()
    for row in rows.select(range(min(SAMPLE_N, len(rows)))):
        for block in _parse_persona_json(row["persona_json"]):
            block_counter[block.get("BlockName", "<no name>")] += 1
    for name, count in block_counter.most_common():
        print(f"  {count:>4d}  {name}")


if __name__ == "__main__":
    main()
