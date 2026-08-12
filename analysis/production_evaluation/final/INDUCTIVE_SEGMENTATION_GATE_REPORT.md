# Inductive segmentation gate report

**Status: PASS — ready for Phase A extraction. No API call has been made.**

## Gate result

- Frozen corpus: 35 documents (5 human, 30 canonical synthetic).
- Segmented units: 174/174.
- Synthetic runs anchored: 30/30.
- Source documents reconciled: 35/35.
- Unresolved question boundaries: 0.
- Positional fallback: never used.
- Synthetic source: comparable windows only; full transcripts are never substituted.
- Human FG5 Q4: not asked in fieldwork, retained as missing rather than coded as zero.

The final synthetic rule scans every non-empty spoken moderator-log utterance and uses the
latest explicit guide-question ask. Reformulations remain inside the current section;
closing residue is excluded. The two researcher-reviewed cases reproduce these binding
boundaries:

| Run | Q1 | Q2 | Q3 | Q4 | Q5 | Closing excluded |
|---|---:|---:|---:|---:|---:|---:|
| `macho_meals_fg1_demoonly_run01` | 0–8 | 9–18 | 19–33 | 34–45 | 46–51 | 52+ |
| `macho_meals_fg4_demoonly_run01` | 0–5 | 6–14 | 15–19 | 20–23 | 24–27 | 28+ |

## Corrected measured inventory

| Question | Units | Words | Mean words |
|---|---:|---:|---:|
| Q1 | 35 | 30,132 | 861 |
| Q2 | 35 | 39,514 | 1,129 |
| Q3 | 35 | 64,575 | 1,845 |
| Q4 | 34 | 69,851 | 2,054 |
| Q5 | 35 | 68,208 | 1,949 |

Q4 contains 34 extracted units, but its accumulation curve is restricted to FG1–FG4:
28 units and 24 focus-group orderings. The six synthetic FG5 Q4 units remain outside that
curve because there is no paired human FG5 Q4.

## Phase A

Phase A is now technically ready: 174 codebook-blind Gemini Batch extraction requests,
one for each segmented unit. This report does **not** authorise or execute those calls.
Stages B–F remain deferred until the observed raw-theme inventory is available.

## Reproducibility

`inductive_inventory.build()`, `inductive_segments.build()` and
`inductive_budget.plan()` are read-only computations. Persistence requires an explicit
`write()` call, preventing tests from rewriting frozen artefacts as a side effect.

