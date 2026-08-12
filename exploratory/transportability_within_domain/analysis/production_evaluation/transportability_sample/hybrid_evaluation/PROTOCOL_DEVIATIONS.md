# Protocol deviations — exploratory out-of-Q3 transportability check

`EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK`

This file records every point at which execution departed from the protocol frozen in
`hybrid_manifest.json`, and every rule added afterwards to cover a contingency the
protocol had not specified. It exists so that the phrase "all stopping points passed"
is never used where it is not true.

---

## `PROTOCOL_DEVIATION_01` — a failed request was retained rather than stopping

**What the protocol said.** Stopping point 4: *"Detente si el resultado de Claude no pasa
los gates técnicos."*

**What happened.** In the round-1 batch (`msgbatch_01RgXvJrPHyUZfaTimUzw1Bf`), 121 of 122
requests succeeded and one errored, returning no message at all. The affected request was
repetition 2 of case `P::S06::S06_slot_01::S06::M6`. Execution did not stop. The case was
carried forward as `HYBRID_UNRESOLVED` on the frozen ground that a missing repetition is a
failed reliability gate, and the analysis continued.

**Why this is a deviation and not a judgement call.** The stopping rule as written does not
distinguish a transport failure from a substantive gate failure. Continuing was defensible
on the merits — the case was recorded as unresolved and never counted as a match — but it
was a decision taken *after* seeing the failure, against a rule that said stop. Presenting
it afterwards as compliance would be a misdescription.

**Correction to the record.** Any statement that all stopping points passed in the original
run is withdrawn. The protocol defined **four** stopping points, not five — the fifth
numbered item instructed execution to proceed and deliver the products, which is not a
stopping condition. The correct statement is: **stopping points 1–3 passed; stopping point
4 was not applied as written** when one request errored, and the case was retained as
unresolved instead.

**Effect on results.** The affected pair belonged to `ORIGINAL_SCREENED_61` and was not
re-examined in the complementary audit, which was restricted to the 32 previously omitted
pairs. It remains `HYBRID_UNRESOLVED` with one completed repetition and contributes to the
precision uncertainty associated with `S06::M6`.

---

## `PROTOCOL_DEVIATION_02` — the correspondence space was incomplete when metrics were computed

**What happened.** Phase 3 verified that every human theme and every machine theme appeared
in at least one candidate pair, and reported `coverage: complete`. Phase 5 then computed
recall and precision as though the 61 audited pairs were the whole correspondence space.
They were not. Within the six units there are 93 possible human × machine pairs; a
deterministic similarity screener excluded 32 of them, and those 32 were never put to the
adjudicator.

**Why it matters.** The screener's documented role is to *propose* pairs, never to accept or
reject a correspondence. Treating its exclusions as settled non-correspondences silently
promoted a heuristic into an adjudicator. Concretely, it made these claims unsupported at
the time they were published:

- `possible_recall_upper_bound = 0.8889` and a recall band of zero width;
- "zero human themes unresolved";
- that the two unrecovered human themes had *only* confirmed non-correspondences;
- that the final classification was closed.

**Correction.** All 32 omitted pairs were audited under the same model, mode, effort,
schema, blinding, categories and gates as the original 61 (`hybrid_complement_manifest.json`,
`claude_complement_results.json`). Metrics were recomputed from the complete 93-pair
universe. The pre-complement classification is retained as
`PROVISIONAL_SUPERSEDED — based on 61/93 screened pairs`.

**Not corrected by re-running anything.** No historical decision was re-run, re-judged or
overwritten. The 61 original pairs are carried forward byte-identical and are marked
`source_round = ORIGINAL_SCREENED_61`.

---

## `COMPLEMENT_RETRY_POLICY_V1` — added rule, frozen before the complementary submission

The original protocol did not say what to do when a request fails for transport reasons
rather than substantive ones. `PROTOCOL_DEVIATION_01` is the consequence of that gap. The
following rule was frozen in `hybrid_complement_manifest.json` **before** the 64
complementary requests were sent, and applies only to them.

- A request that produced **no usable substantive response** — an API error, an absent
  result, invalid JSON, or output truncated at `max_tokens` — may be retried **once**.
- A retry is **never** permitted for: a disagreement between repetitions, LOW confidence,
  an invalid or non-literal quotation, or a result the analyst finds unfavourable.
- If the single retry also fails, the pair remains `HYBRID_UNRESOLVED`.
- There is no retrying until the repetitions agree. Resampling a judgement until it
  converges manufactures agreement; the retry exists only to recover from transport
  failure.
- Every attempt and its reason is recorded in `claude_complement_results.json`.

**This is an operational correction, not part of the original protocol.** It must not be
described as though it had been in force during the original run — it was written
precisely because it was not.

---

## Standing constraints, not deviated from

No human workbook, the frozen supplementary reference, the U01–U07/Q3 calibration, the
clustering and matching workbooks, the deductive results, the transcripts, the comparable
windows, the frozen specification, the registry, or `output/session_logs/` was modified at
any point. No new researcher task was created. No model, prompt or configuration was
substituted. Gemini was not re-run for the complementary audit; the extraction is the
original sealed one.
