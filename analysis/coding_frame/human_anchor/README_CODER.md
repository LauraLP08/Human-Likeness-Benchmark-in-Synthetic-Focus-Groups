# Coding Instructions

You will code three focus-group transcripts against a thematic codebook.
**Do not look at any AI output or model results while working.**

## Files

| File | What it is |
|------|------------|
| `transcript_1.txt` | Focus group transcript (anonymous, turn IDs T001…) |
| `transcript_2.txt` | Focus group transcript |
| `transcript_3.txt` | Focus group transcript |
| `worksheet_1.csv`  | Fill this for transcript_1 |
| `worksheet_2.csv`  | Fill this for transcript_2 |
| `worksheet_3.csv`  | Fill this for transcript_3 |

## Codebook

There are **11 subthemes** (A.1, A.2, A.3, B.1, B.2, B.3, B.4, C.1, C.2, C.3, D).
Each worksheet row already has the subtheme label, definition, and example —
you only need to fill the last four columns.

## Coding procedure

1. Open `transcript_1.txt` and `worksheet_1.csv` side by side.
2. For each subtheme row:
   - Read the definition and example carefully.
   - Search the transcript for relevant content.
   - In **present_YN**: write **Y** (present) or **N** (not present).
   - If **Y**: in **turn_id** write the turn label (e.g. `T034`), in **quote**
     copy-paste the EXACT verbatim text from the transcript that best
     instantiates the subtheme (do not paraphrase), and in **note** write one
     sentence explaining why it fits the definition.
   - If **N**: leave turn_id, quote, and note blank.
3. **Code in order: 1 first, then 2, then 3.**
4. A subtheme is **present** if at least one clear instance occurs anywhere in
   the transcript. Find the strongest single instance.
5. **Do NOT open** any file not listed above while coding.

## Important

- Quotes must be EXACT copy-paste from the transcript (no rephrasing).
- The turn_id must match the `[Txxx]` label at the start of the line.
- If in doubt whether a subtheme applies, mark N and note your uncertainty.
- Return all three filled worksheets when done.
