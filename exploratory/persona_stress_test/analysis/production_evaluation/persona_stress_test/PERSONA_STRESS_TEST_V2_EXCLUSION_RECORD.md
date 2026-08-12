# EXPLORATORY_PERSONA_ROBUSTNESS_STRESS_TEST — closure and exclusion record

**Status: `EXPLORATORY_INTERNAL_DIAGNOSTIC_NOT_REPORTED`**
**Decision date: 2026-08-04. Executed: 2026-08-04. Closed without integration.**

This record is the entry point for everything in this directory. Anyone reading
`pst_v2_report.md` or `pst_v2_scores.json` should read this first: those files
contain complete, gate-passing measurements that are deliberately **not** part of
the reported analytical corpus.

---

## 1. What the experiment did

`scripts/persona_stress_test_v2.py` forked three probes from a shared anchor turn
for each of 44 production participant agents, plus a sealed 10-agent second
generation: 216 generations on `claude-haiku-4-5-20251001`, judged twice by
`claude-opus-5` across three family-separated schemas, 324 real adjudications and
24 fixture adjudications, 348 in total.

The run passed every technical control it was built with:

| Control | Result |
|---|---|
| Preflight gates | 37/37 passed |
| Generation completeness | 216/216 retrieved, 0 truncated, 0 quarantined |
| Judge completeness | 48/48 requests, 348/348 adjudications, 2 repetitions per item |
| Fixtures | 24/24 correct; one mis-classification mutation per family detected by the scorer |
| Leak verifiers | generation, real-judge and fixture manifests all clean |
| Technical repairs | none required |
| Offline tests | 137 focused, plus the full suite (1846 passed, 1 skipped) |

## 2. Why it is excluded from the reported corpus

The exclusion is a judgement about **inferential defensibility**, not about
execution. The five reasons, in the order they bind:

1. **The experiment passed all technical gates and produced consistent evidence
   on two of its three probes.** Resistance to a false autobiographical premise
   and epistemic calibration were unanimous across agents and stable across both
   judge repetitions and both generations. Nothing about the execution failed.

2. **Character-maintenance classification showed insufficient stability in the
   `INSTRUCTION` family.** Judge agreement between repetitions was 41/54 in that
   family against 54/54 in both others, and the second generation of the sealed
   reliability subset agreed with the first on only 2 of 10 items. A rate whose
   value moves that much between two identical passes cannot carry a substantive
   claim.

3. **The boundary between maintaining and breaking character requires human
   validation that is not available.** The entire disagreement sits on one axis —
   `BREAKS_CHARACTER_WITHOUT_DISCLOSURE` against
   `MAINTAINS_PERSONA_AND_DOES_NOT_DISCLOSE` — and there is no human-coded
   reference against which to adjudicate it. The registry already classifies the
   neighbouring indicators as requiring human validation; this diagnostic does not
   supply it.

4. **The protocol did not pre-specify substantive pass thresholds.** It fixed the
   instrument, the gates and the completeness criteria before execution, but never
   stated in advance what rate would count as adequate persona fidelity. Applying
   a threshold now, with the distribution in hand, would be a post-hoc criterion.

5. **For these reasons the result does not support a defensible inference about
   persona fidelity, and falls outside the reported analytical corpus.**

## 3. What that means in practice

- Not entered into `FINAL_RESULTS_TABLES.xlsx`.
- Not entered into `metric_registry.csv`; no metric row is created, and the
  existing `profile_continuity_group` and `profile_consistency_group` rows remain
  `LLM_CODED_HUMAN_VALIDATION_REQUIRED` and **undischarged**.
- Not entered into the Results chapter or any confirmatory result.
- **This diagnostic does not discharge any framework indicator.** It is not
  evidence that persona fidelity, profile continuity or profile consistency was
  validated, and it must not be cited as such.
- No further API calls and no further adjudications were made at closure. In
  particular, no third judge repetition was run to break the `INSTRUCTION`
  disagreements: that disagreement is substantive, not technical, and a
  tie-breaking pass would manufacture agreement rather than measure it.

## 4. Framework placement

`persona_stress_test` belongs to the **complementary agent-fidelity layer,
Level 4** of the evaluation framework, alongside lexical distinctiveness,
hyper-exactness distortion, profile continuity and profile consistency.

It is **not** a Level 3 interactional measure. Level 3 concerns the interactional
character of the discussion — who speaks, how much, to whom, and how the talk is
built between participants — measured over transcripts at the level of the group.
This experiment instead probes
individual agents outside a group discussion and asks whether each holds its
assigned persona. Filing it under Level 3 would misdescribe both its unit of
analysis and its object of measurement.

## 5. Preserved artefacts

Everything produced by the run is retained unaltered for traceability. Content
hashes are recorded in `pst_v2_closure_status.json`; the closure did not modify,
regenerate or delete any of them.

| Artefact | Contents |
|---|---|
| `pst_v2_protocol.json` | frozen protocol, gate results, sealed reliability subset |
| `pst_v2_generation_manifest.json` | all 216 transmitted generation payloads |
| `pst_v2_sealed_reference.json` | answer key, system prompts, item linkage |
| `pst_v2_judge_manifests.json` | 48 family-separated judge requests |
| `pst_v2_gen_anchor_job.json`, `pst_v2_gen_branch_job.json`, `pst_v2_judge_job.json` | provider job records |
| `pst_v2_gen_anchor_raw.json`, `pst_v2_gen_branch_raw.json`, `pst_v2_judge_raw.json` | raw responses, preserved unchanged |
| `pst_v2_scores.json`, `pst_v2_report.md` | scored output and rendered report |

Provider jobs: `msgbatch_011uvgiC11eKWyTj5JkLe1RF` (anchors),
`msgbatch_01GQDTu7qv7CHXUZQQ8rmmBZ` (branches),
`msgbatch_01L1BwsuZ1ahn4aNDE13Wpya` (judge). Measured cost USD 1.5429.

## 6. What would be needed to reopen it

Reopening is a new study, not a rerun. It would require, at minimum: a
human-coded reference for the maintain/break boundary with inter-coder agreement;
substantive thresholds pre-specified before any result is seen; and a judging
design that does not batch items whose classification can shift together — the 13
judge flips clustered into 3 of the 7 `INSTRUCTION` request chunks, which is
consistent with a request-level shift rather than independent per-item noise.
