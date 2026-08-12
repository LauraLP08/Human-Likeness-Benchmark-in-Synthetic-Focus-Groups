"""
Phase 1: Generate blind materials for the human gold-standard coder.

Writes to analysis/coding_frame/human_anchor/:
  blind_real_fg1.txt     — exact blind transcript fed to Gemini
  blind_synth_fg1.txt
  blind_synth_fg5.txt
  worksheet_real_fg1.csv — 11 rows, one per subtheme; human fills present_YN/turn_id/quote/note
  worksheet_synth_fg1.csv
  worksheet_synth_fg5.csv
  README_CODER.md        — coding instructions for the human

No model codings, no provenance labels beyond the neutral file name.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from thematic_coding import load_codebook, to_blind_text

_OUT_DIR = _REPO_ROOT / "analysis" / "coding_frame" / "human_anchor"


# ---------------------------------------------------------------------------
# Transcript loading (identical to validate_thematic_measure.py)
# ---------------------------------------------------------------------------

def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_TRANSCRIPTS = {
    "real_fg1":  _REPO_ROOT / "data" / "datasets_transcripts" / "standardized"
                 / "macho_meals" / "fg1" / "transcript.json",
    "synth_fg1": _REPO_ROOT / "output" / "session_logs"
                 / "costfix_validation_fg1" / "transcript.json",
    "synth_fg5": _REPO_ROOT / "output" / "session_logs"
                 / "costfix_validation_fg5" / "transcript.json",
}


# ---------------------------------------------------------------------------
# Write worksheet CSV
# ---------------------------------------------------------------------------

_CSV_COLS = [
    "subtheme_id",
    "subtheme_label",
    "definition",
    "example",
    "present_YN",   # human fills: Y / N
    "turn_id",      # human fills: e.g. T034
    "quote",        # human fills: exact verbatim quote
    "note",         # human fills: one-line rationale
]


def _write_worksheet(codebook: list[dict], label: str) -> Path:
    path = _OUT_DIR / f"worksheet_{label}.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for entry in codebook:
            w.writerow({
                "subtheme_id":    entry["subtheme_id"],
                "subtheme_label": entry["subtheme_label"],
                "definition":     entry.get("description") or "",
                "example":        entry.get("example") or "",
                "present_YN":     "",
                "turn_id":        "",
                "quote":          "",
                "note":           "",
            })
    return path


# ---------------------------------------------------------------------------
# README for the human coder
# ---------------------------------------------------------------------------

_README = """\
# Coding Instructions — Human Anchor Validity Check

You will code THREE focus-group transcripts against the Macho Meals codebook.
This is a BLIND coding: you must not look at any AI model output while working.

## Files

| File | What it is |
|------|------------|
| `blind_real_fg1.txt`  | Real focus group 1 (anonymous, turn IDs T001…) |
| `blind_synth_fg1.txt` | Synthetic focus group 1 |
| `blind_synth_fg5.txt` | Synthetic focus group 5 |
| `worksheet_real_fg1.csv`  | Fill this for real_fg1  |
| `worksheet_synth_fg1.csv` | Fill this for synth_fg1 |
| `worksheet_synth_fg5.csv` | Fill this for synth_fg5 |

## Codebook

There are **11 subthemes** (A.1, A.2, A.3, B.1, B.2, B.3, B.4, C.1, C.2, C.3, D).
Each worksheet row already has the subtheme label, definition, and example — you
only need to fill the last four columns.

## Coding procedure

1. Open `blind_real_fg1.txt` and `worksheet_real_fg1.csv` side by side.
2. For each subtheme row in the worksheet:
   - Read the definition and example carefully.
   - Search the transcript for relevant content.
   - In **present_YN**: write **Y** (present) or **N** (not present).
   - If **Y**: in **turn_id** write the turn label (e.g. `T034`), in **quote**
     copy-paste the EXACT verbatim text from the transcript that best
     instantiates the subtheme (do not paraphrase), and in **note** write one
     sentence explaining why it fits the subtheme definition.
   - If **N**: leave turn_id, quote, and note blank.
3. Code **real_fg1 FIRST** (calibration), then **synth_fg1**, then **synth_fg5**.
4. A subtheme is **present** if at least one clear instance occurs anywhere in
   the transcript. You do not need to find all instances — just the strongest one.
5. **Do NOT open** any file named `validation_stage1_*.json` or any other AI
   model output while coding. Blind coding is essential for validity.

## Important

- Quotes must be EXACT substrings of the transcript (copy-paste, do not rephrase).
- The turn_id must match the `[Txxx]` label in the transcript.
- If in doubt whether a subtheme applies, mark N and note your uncertainty.
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    codebook = load_codebook()
    print(f"Codebook loaded: {len(codebook)} subthemes")

    for label, tpath in _TRANSCRIPTS.items():
        entries = _load(tpath)
        blind_text, speaker_map = to_blind_text(entries)
        n_turns = len(blind_text.splitlines())

        # Write blind transcript
        txt_path = _OUT_DIR / f"blind_{label}.txt"
        txt_path.write_text(blind_text, encoding="utf-8")
        print(f"  {txt_path.name}: {n_turns} turns, speakers: {set(speaker_map.values())}")

        # Write worksheet
        ws_path = _write_worksheet(codebook, label)
        print(f"  {ws_path.name}: {len(codebook)} rows")

    # README
    readme_path = _OUT_DIR / "README_CODER.md"
    readme_path.write_text(_README, encoding="utf-8")
    print(f"  {readme_path.name}: written")

    print("\nPhase 1 complete. No model data in any output file.")
    print(f"All files in: {_OUT_DIR.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
