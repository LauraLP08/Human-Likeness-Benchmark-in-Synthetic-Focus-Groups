# Hybrid transportability protocol — S01–S06

**Classification: `EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK`**

Not a formal validation. **Never pooled numerically with U01–U07/Q3.** Frozen in full
before any API call; the machine-readable form is `hybrid_evaluation/hybrid_manifest.json`.

---

## 1. Scope

Six units, four guide questions, one coder, 18 human themes.

| Unit | Question | Human themes |
|---|---|---|
| S01 | Q1 | 4 |
| S03 | Q1 | 2 |
| S05 | Q2 | 4 |
| S02 | Q4 | 3 |
| S04 | Q4 | 1 |
| S06 | Q5 | 4 |
| | | **18** |

Per-question denominators: **Q1 = 6, Q2 = 4, Q4 = 4, Q5 = 4.**

Results are reported **per unit and per question**. Any six-unit summary is descriptive
only and must keep the per-question values visible. Never pooled with U01–U07/Q3, never
mixed with the deductive strand.

## 2. Analytic units

- human theme → `(blind_unit_id, human_theme_id)`
- machine theme → `(blind_unit_id, machine_theme_id)`

A local id is never used without its `blind_unit_id`.

## 3. Gemini extraction — identical to Q3

| | |
|---|---|
| Model | `gemini-3.5-flash` |
| Execution | Batch, 6 requests (one per unit) |
| Prompt SHA-256 | `4424eec734ce7c05…` — the Q3 emergent prompt, unchanged |
| Response schema SHA-256 | `eed4e1b03b546b03…` |
| `max_output_tokens` | 16384 |
| Temperature / thinking | not transmitted |
| Human coding shown | **no** |

Cache keys are new and incorporate the unit text hash, prompt hash, schema hash, model,
effective configuration and execution mode. Quote policy is the Q3 policy: verbatim,
attributed to a turn, never the moderator.

## 4. Claude audit

Claude Opus 5, Batch, `effort=high`, structured output, **two independent repetitions per
case**, `repetition_index` inside the cache key. Sides are labelled **REFERENCE** and
**CANDIDATE**; unit labels are opaque. The auditor is shown no model name, no Q3 result,
no benchmark, no experimental condition and no provenance.

Status: **`USABLE_FOR_CORROBORATION_ONLY`** — never an arbiter, never a human replacement.

## 5. Frozen decision rules

### Correspondence

`HYBRID_CONFIRMED_MATCH` requires **all** of:

1. both repetitions give an accepted correspondence category;
2. neither repetition is LOW confidence;
3. every cited quotation is literally verifiable in the unit;
4. no quotation comes from the moderator;
5. no unknown ids;
6. no contradiction between the two repetitions.

Accepted as correspondence: `SAME_SUBSTANTIVE_THEME`,
`PARTIAL_OVERLAP_REFERENCE_MORE_SPECIFIC`, `PARTIAL_OVERLAP_CANDIDATE_MORE_SPECIFIC`.

`RELATED_BUT_DISTINCT` and `NO_CORRESPONDENCE` **never** enter a recall or precision
numerator.

Anything else — disagreement, invalid evidence, LOW confidence, conceptual ambiguity — is
**`HYBRID_UNRESOLVED`**, counted as neither a match nor a confirmed error.

### Machine-only themes

Audited separately as `VALID_NOVEL_THEME`, `UNSUPPORTED_OR_SPURIOUS`,
`DUPLICATE_MACHINE_THEME` or `UNCERTAIN`.

**`HYBRID_CORROBORATED_NOVEL`** only when both repetitions say `VALID_NOVEL_THEME`,
confidence is not LOW, and evidence is valid. Anything else is
**`HYBRID_UNRESOLVED_MACHINE_ONLY`**.

**Claude alone can never make a case "human validated".**

### Fragmentation and fusion

One human theme → several machine themes = possible fragmentation. One machine theme →
several human themes = possible fusion. Classified as
`LEGITIMATE_GRANULARITY_DIFFERENCE`, `POSSIBLE_OVER_MERGING`,
`POSSIBLE_OVER_FRAGMENTATION`, `SUBSTANTIVE_MISMATCH` or `UNCERTAIN`; reported as
corroborated only when both repetitions agree and evidence passes. **Never alters a
numerator automatically.**

## 6. Metrics

Per unit and per question:

- **`confirmed_recall_lower_bound`** = human themes with ≥1 `HYBRID_CONFIRMED_MATCH` ÷ human themes
- **`possible_recall_upper_bound`** = human themes confirmed **or** carrying a plausible unresolved relation ÷ human themes

Both are always reported. **Uncertainty is never converted into absence.**

- **`strict_confirmed_precision`** = machine themes with ≥1 confirmed match ÷ machine themes
- Reported separately: confirmed-match themes · corroborated novel · corroborated unsupported/spurious · corroborated duplicates · unresolved
- Any precision crediting novelty is named
  **`exploratory_adjusted_precision_including_corroborated_novelty`**, with strict
  precision always visible beside it
- **`literal_evidence_attachment_rate`** — never called groundedness — plus verified and
  quarantined quotation counts

## 7. Frozen final classification rule

Evaluated **in order**; fixed before any result exists:

1. **`UNRESOLVED_DUE_TO_HYBRID_UNCERTAINTY`** — unresolved human themes > 40% of 18, **or**
   mean per-question lower–upper band width > 0.35.
2. **`DESCRIPTIVELY_LOWER_THAN_Q3`** — in ≥3 of the 4 questions the **upper** bound is
   still below 0.6818.
3. **`DESCRIPTIVELY_COMPATIBLE_WITH_Q3`** — in **every** question the band
   [lower, upper] reaches or exceeds 0.6818, **and** no unsupported/spurious theme is
   corroborated in ≥2 units.
4. **`MIXED_OUTSIDE_Q3_PERFORMANCE`** — otherwise.

The choice **never** depends on whether a single pooled average exceeds 0.6818.
Per-question results, band width, unresolved share and recurrent unsupported themes all
enter. **No PASS/FAIL under any branch.** No statistical test between questions. No claim
of equivalence, non-inferiority or validation.

**n caveat:** with 6/4/4/4 themes per question, a single theme moves a question by
0.17–0.25. Nothing inferential can rest on this.

## 8. Stopping points

1. Input validation fails → stop.
2. Any Gemini extraction not COMPLETE → stop, no partial corpus.
3. Candidate generation not covering 100% of both sides → improve generation, never
   invent matches.
4. Claude output failing the technical gates → stop.

## 9. Protections

No modification of `Transportability_Emergent_SingleCoder.xlsx`,
`supplementary_human_reference.json`, U01–U07/Q3 artefacts, clustering or matching
workbooks, deductive results, transcripts, comparable windows, the frozen specification
or the registry. No human task is created. No model, prompt or configuration is
substituted. Job ids are saved immediately. Actual costs are recorded separately from
estimates.
