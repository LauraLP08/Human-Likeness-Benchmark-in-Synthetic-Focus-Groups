# Exploratory out-of-Q3 transportability check — traceability

**`EXPLORATORY_OUT_OF_Q3_TRANSPORTABILITY_CHECK`** · built 2026-08-02T21:34:15.267222+00:00

Every figure in the results document can be reached from this index. Artefacts are listed with the SHA-256 of the file as it stands now, so any later edit is detectable.

## Provenance chain

| # | Stage | Produced by | Artefact | Gate |
|---|---|---|---|---|
| 0 | Freeze protocol and rules | `scripts/hybrid_transportability.py` | `hybrid_manifest.json` | rules frozen before any model ran |
| 1 | Validate inputs | `scripts/hybrid_transportability.py --validate` | `manifest.input_validation` | 18/18 themes, 6/6 unit hashes, boundaries clean, quotes literal |
| 2 | Emergent extraction | `scripts/hybrid_gemini_extract.py` | `gemini_extraction_results.json` | 6/6 COMPLETE or stop |
| 3 | Candidate proposal | `scripts/hybrid_candidates.py` | `hybrid_candidates.json` | both sides covered — NOT the whole pair space, see DEVIATION_02 |
| 4a | Blinded adjudication, round 1 | `scripts/hybrid_claude_audit.py` | `claude_round1_results.json` | blinding + schema + repetition gates |
| 4b | Blinded adjudication, round 2 | `scripts/hybrid_claude_audit.py` | `claude_round2_results.json` | same gates; candidate-only and granularity |
| 4c | Complement: the 32 omitted pairs | `scripts/hybrid_complement.py` | `hybrid_complement_manifest.json, claude_complement_results.json` | set equality 61+32=93 proved before submission; same gates |
| 5 | Universe integration | `scripts/hybrid_universe.py` | `hybrid_universe.json` | 93/93 present, no duplicates, no cross-unit pair, history unchanged |
| 6 | Metrics | `scripts/hybrid_metrics.py` | `hybrid_metrics.json, hybrid_matching_derivation.json` | recomputed from the complete universe |
| 7 | Products | `scripts/hybrid_products.py` | `results, tables, traceability, cost` | frozen rule + balanced interpretation, both reported |

## The correspondence space

| Quantity | n |
|---|---:|
| human themes | 18 |
| candidate themes | 30 |
| within-unit pairs possible | 93 |
| adjudicated in the original run | 61 |
| adjudicated in the complement | 32 |
| duplicates | 0 |

Per unit: S01 4×4=16, S02 3×7=21, S03 2×4=8, S04 1×4=4, S05 4×5=20, S06 4×6=24.

61 + 32 reconstitutes the cartesian exactly: `True`. The screener's own rejection list was checked independently and is exactly the complement. The 61 historical pairs were carried forward read-only; their SHA-256 record is in `hybrid_complement_manifest.json → historical_pairs_read_only`.

## Artefact hashes

| Artefact | SHA-256 | bytes |
|---|---|---:|
| `claude_complement_job.json` | `ec99f653d83b808bf2cc43325bb5afcdad1a991f3701a0859ba442f521e74a2b` | 81,082 |
| `claude_complement_results.json` | `12f3661596fe79972a61d864bfed7e8b1d367c71cd088ef8494f9208f407ff64` | 174,652 |
| `claude_cross_model_results.json` | `85f64083e835833caf1bc16cece4bd3304690628f4bfe7f748910d615bef84c4` | 353,486 |
| `claude_job_round1.json` | `c512ecae0dd05b8e1df4958435f9d975c67d0a36f3805872924a9084f4c5ebc7` | 154,524 |
| `claude_job_round2.json` | `a1753b756d2139ec661aa7edc6323e53f57bd5c044ed503eab58da92e056071f` | 89,909 |
| `claude_round1_results.json` | `26c14a7f2b5032d37a2939374b7425f4424518d2b7807744d34b9dacc1b737f5` | 322,664 |
| `claude_round2_results.json` | `14019c6ba416e80b68accdc7a9fc89352bf913cc1ea8501915e6e30fb45440ee` | 93,567 |
| `gemini_extraction_results.json` | `0bc41daeeba8c01f8aaf7106759b699e3933bf127580eac994f66b5b42ef546d` | 30,348 |
| `gemini_job.json` | `f52aa8974bf80d191134793bd71d796650364177a75966355f93764e0304b422` | 1,628 |
| `gemini_raw.json` | `e4b73143f7b2c9e78ce774f6c202bce175f69b714f3f8e9272e0515f7cb5295b` | 28,088 |
| `hybrid_candidates.json` | `2b65088946bfd60d01ab969d7dc8c9826e89ca5d1122c590c7d0b043d30b2847` | 61,853 |
| `hybrid_complement_manifest.json` | `d357a353851c89a6893a7b235707171310b1cb90d1f1d6b6748890dd7c2a00a2` | 17,998 |
| `hybrid_cost_actual.json` | `af690b60c63e1f5014e9027a9b2d3ba22319051dc4d2e2c92023a73b24fac7bb` | 2,039 |
| `hybrid_manifest.json` | `54efcccc9585f33b44b0ddeb1c7f1a1226fa35d577772b94c01156cce20e398d` | 6,653 |
| `hybrid_matching_derivation.json` | `238da5e108784a738177a6bbc33447ca901c9f5be3806993714f601ecb3d1c28` | 102,148 |
| `hybrid_metrics.json` | `3f725f7b454e19d95ea649ad58c732f399484aa1df2bd442ad9ea1efb155f7fa` | 30,477 |
| `hybrid_round1_derivation.json` | `b4ecfb204986cd9f35aee34f3fed5de8c444eb2509b3fa8b231bee9f77c0e42c` | 19,436 |
| `HYBRID_TRANSPORTABILITY_RESULTS.md` | `a9ae09bff0eece88142f02f324c3eb24c4c458c792c023d204ab0a49a14fd1b9` | 14,243 |
| `HYBRID_TRANSPORTABILITY_TABLES.xlsx` | `962d0eea59e3e86b48d3039326e87941a93fe6a3d0ad801f2abc119f27830a25` | 23,256 |
| `hybrid_universe.json` | `9a6ad7730c90f337dd1b2d92a0e549aa6817a807c2733f19f939063f5ab4ea61` | 93,476 |
| `PROTOCOL_DEVIATIONS.md` | `5fd7d1ccf9891c7a3df96937bf644e46f6de60fe0bd64114a46dd6d3d2935d39` | 5,754 |

`HYBRID_TRANSPORTABILITY_TRACEABILITY.md` is not listed: a file cannot carry its own hash. Verify it by regenerating it — `py scripts/hybrid_products.py` is deterministic apart from the build timestamp in its header.

## Model calls

| Stage | Model | Mode | Job id | Requests | Complete |
|---|---|---|---|---:|---:|
| extraction | `gemini-3.5-flash` | batch | `batches/fr2ux2vj1g55gy1oe62c48gmkgplchers1rg` | 6 | 6 |
| audit round 1 | `claude-opus-5` | batch | `msgbatch_01RgXvJrPHyUZfaTimUzw1Bf` | 122 | 121 |
| audit round 2 | `claude-opus-5` | batch | `msgbatch_01LSVnMiM5BgYx5kiHX5pBdp` | 30 | 30 |
| complementary audit (32 omitted pairs) | `claude-opus-5` | batch | `msgbatch_01CkAwX2ruMRSV5yGRnxKfv6` | 64 | 64 |

Extraction prompt SHA-256 `4424eec734ce7c057c805fdc9885ad10f62c335302c4f7392e4ed8914b9b5608` — byte-identical to the prompt frozen for U01–U07/Q3. Response schema SHA-256 `eed4e1b03b546b03fac59d7f2a9e2474a1c0b02de16a64658bdba4004d50ed95`. **Gemini was not re-run for the complement**; the extraction is the original sealed one.

The complementary audit used the same adjudication configuration as the original: `claude-opus-5`, batch, effort `high`, structured output, 2 repetitions per pair, prompt SHA-256 `287b242f82bfcfc8…`, schema SHA-256 `94a2b1a78ae97e15…`, identical categories and identical gates. Cache keys incorporate the pair case id, the rendered content hash and the repetition index; all 64 were unique and none collided with the 152 historical keys.

Every response was matched to its case by `custom_id`, never by position. custom_ids are allocated per batch, so they are unique within a job and repeat across jobs; matching is always through that job's own id map.

## Where each headline number comes from

| Figure | Value | Source |
|---|---|---|
| `confirmed_recall_lower_bound` | 0.8889 | hybrid_universe.json → human_state, count of state == RECOVERED |
| `possible_recall_upper_bound` | 0.8889 | adds state == UNRESOLVED_POSSIBLY_RECOVERED (there are none) |
| `n_confirmed_not_recovered` | 2 | state == CONFIRMED_NOT_RECOVERED; each verified local_universe_complete |
| `strict_confirmed_precision` | 0.6000 | machine_state, count of state == MATCHED |
| `possible_precision_upper_bound` | 0.7667 | adds 5 with state == UNRESOLVED_POSSIBLY_MATCHED: S01::M3, S02::M6, S03::M2, S04::M4, S06::M6 |
| `exploratory_adjusted_precision` | 0.9667 | adds candidate-only cases with status HYBRID_CORROBORATED_NOVEL |
| `literal_evidence_attachment_rate` | 1.0000 | gemini_extraction_results.json; verified at acceptance |
| `FROZEN_RULE_CLASSIFICATION` | DESCRIPTIVELY_COMPATIBLE_WITH_Q3 | hybrid_transportability.FINAL_RULE, frozen in hybrid_manifest.json before any result existed; unmodified |
| `BALANCED_INTERPRETATION` | see §6.2 | hybrid_metrics.json → BALANCED_INTERPRETATION.dimensions_weighed |
| `PRE_COMPLEMENT_CLASSIFICATION` | DESCRIPTIVELY_COMPATIBLE_WITH_Q3 | PROVISIONAL_SUPERSEDED — based on 61/93 screened pairs |

## Closure figures

| Quantity | Value |
|---|---|
| total pairs adjudicated | 93 |
|   historical (`ORIGINAL_SCREENED_61`) | 61 |
|   complementary (`COMPLEMENT_32`) | 32 |
| confirmed matches | 19 |
| confirmed non-correspondences | 60 |
| unresolved pairs | 14 |
| recall (confirmed) | 16/18 = 0.8889 |
| strict confirmed precision | 18/30 = 0.6000 |
| possible precision upper bound | 23/30 = 0.7667 |
| machine themes possibly matched (uncertain) | 5 |
| corroborated novel (automated, not human-validated) | 11 |
| adjusted precision (optimistic exploratory ceiling) | 29/30 = 0.9667 |
| cumulative Claude cost | USD 4.60 at the list Batch rate (calculated, not an invoice) |

19 + 60 + 14 = 93.

**Recorded deviation affecting these figures.** One round-1 request errored and was never resent (`PROTOCOL_DEVIATION_01`). That pair belonged to `ORIGINAL_SCREENED_61`, was not re-examined in the complementary audit, and remains `HYBRID_UNRESOLVED` with one completed repetition. It is one of the 5 sources of precision uncertainty, via `S06::M6`.

## Integrity checks

- 93/93 pairs present; 61 + 32 = 93; zero duplicate pair keys; every combination appears exactly once; no pair crosses a unit boundary.
- Every human and candidate theme was adjudicated against its complete local universe; a theme is called `CONFIRMED_NOT_RECOVERED` only on that basis.
- The 61 historical decisions are re-derived from the sealed round-1 results and compared cell for cell; any alteration fails the build.
- Mutation tests in `tests/test_hybrid_universe.py` plant a missing pair, a duplicated pair, a cross-unit pair, an altered historical decision, an unresolved counted as a match, and a theme declared unrecovered on an incomplete universe — each is proved to fail the corresponding guard.

## What this check did not touch

Read-only throughout, and re-verified after the run by `tests/test_hybrid_transportability.py`:

- Transportability_Emergent_SingleCoder.xlsx — the single-coder workbook
- supplementary_human_reference.json — the frozen supplementary reference
- the U01–U07/Q3 calibration and every artefact belonging to it
- the clustering and matching workbooks
- the deductive results
- the human transcripts and the comparable windows
- the frozen evaluation specification and the metric registry
- output/session_logs/
- the historical Claude round-1 and round-2 responses

Constraints held for the duration:

- no human workbook is modified
- supplementary_human_reference.json is read-only
- no human task is created
- no model, prompt or configuration is substituted

No new researcher task was created. Cases that could not be resolved automatically remain `HYBRID_UNRESOLVED`.

Deviations from the frozen protocol are recorded in `PROTOCOL_DEVIATIONS.md`. The protocol defined **four** stopping points: **1–3 passed; stopping point 4 was not applied as written** when one request errored. That pair belonged to `ORIGINAL_SCREENED_61`, was not re-examined in the complementary audit (which covered only the 32 omitted pairs), and remains `HYBRID_UNRESOLVED` with one completed repetition, contributing to the precision uncertainty around `S06::M6`.

## Reproduction

```bash
py scripts/hybrid_transportability.py --validate
py scripts/hybrid_complement.py --manifest
py scripts/hybrid_universe.py
py scripts/hybrid_metrics.py
py scripts/hybrid_products.py
```

Derivation and products are pure functions of the sealed batch results and reproduce exactly. The three batch submissions are not re-runnable without new API calls and are guarded: every submit path refuses to run when a job record already exists.
