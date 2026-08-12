# Gold-standard package — 15 blind excerpts

Two sequential parts over the **same** 15 excerpts.

| Stage | Workbook | Released |
|---|---|---|
| **Part 1 — emergent** | `Coder_A_Part1_Emergent.xlsx`, `Coder_B_Part1_Emergent.xlsx` | now |
| **Part 2 — deductive** | `Coder_A_Part2_Deductive.xlsx`, `Coder_B_Part2_Deductive.xlsx` | **only after that coder returns Part 1** |

Part 1 contains **no codebook**, deliberately. Coders describe the principal ideas
in their own words. Part 2 then codes the same excerpts against the study codebook.
Running it the other way round would let the study's categories shape the emergent
reading, and that cannot be undone once the codebook has been seen.

`U01.txt` … `U15.txt` are plain-text copies of the same excerpts
that appear on each workbook's **Units** sheet, for convenience.

## After the coding returns

| Stage | Workbook |
|---|---|
| cluster emergent themes | `../gold_standard_adjudication/Adjudication_Part1_Emergent.xlsx` |
| resolve deductive disagreements | `../gold_standard_adjudication/Adjudication_Part2_Deductive.xlsx` |

Scoring: `scripts/score_gold_standard.py`.

## Scope of what this validates

Guide section 3 is where subthemes **A.1–A.3** are *directly elicited*, so those are
the codes this exercise can genuinely validate. **B–D** are not directly elicited
here: their absence is evidence about **specificity / false-positive rate**, and
their presence is **opportunistic detection**. This is not a complete recall
validation for B–D, and no pooled statistic should be read as though it were.

The id → source mapping is sealed and is not part of this package.
