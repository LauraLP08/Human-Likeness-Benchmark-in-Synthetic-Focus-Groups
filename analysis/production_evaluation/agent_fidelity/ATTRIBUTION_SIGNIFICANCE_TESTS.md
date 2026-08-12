# Speaker attribution — significance testing

*Namespace: agent fidelity, Level 3. No API calls. Deterministic given the stated seed.*

## 1. What was tested

The attribution analysis asks whether participants within a session can be told apart by how they write. A linguistic profile is built for each participant from a subset of guide questions, one question is held out, and the algorithm attempts to attribute 50-word fragments from that held-out question to the correct speaker.

A **fold** is one session with one question held out. A **trial** is one attributed fragment. Chance differs across folds because the number of eligible speakers varies.

Three questions required testing: whether human groups exceeded chance, whether either synthetic condition exceeded chance, and whether humans exceeded the synthetic conditions. No significance tests had previously been run on this layer.

## 2. Why a standard test could not be used directly

Trials are not independent. Within a fold, every attribution rests on the same participants and the same fitted profiles, so a strong profile lifts all trials in that fold together. The 94 human trials come from only 24 folds.

Treating them as 94 independent observations overstates the evidence: a binomial test on pooled human trials returns p < .0001, but that assumes an independence the design does not have. It is recorded here only as a labelled contrast and is not a result.

Two approaches were used instead, and both are reported.

## 3. Test 1 — fold-respecting label permutation (primary)

Everything about the analysis is held fixed — folds, trials per fold, candidate speakers per fold, and the predictions produced. Only the ground truth is altered: within each fold the true speaker labels are randomly reassigned among that fold's items and accuracy is recomputed. Repeated 20,000 times, seed 20260808.

Permuting within folds preserves the clustered structure, so the null reflects what chance alone achieves in this exact design. The p-value is the proportion of permutations reaching the observed accuracy or better.

**Limitation.** This establishes whether the algorithm exceeded chance *in these sessions*. It is not an inference to sessions not observed.

| Condition | Sessions | Folds | Trials | Observed accuracy | Null mean | p (one-sided) |
|---|---|---|---|---|---|---|
| Human | 5 | 24 | 94 | .4681 (44/94) | .2557 | **< .0001** |
| Enriched | 15 | 73 | 234 | .3248 (76/234) | .3122 | .34 |
| Basic | 14 | 69 | 223 | .3767 (84/223) | .3092 | **.012** |

The permutation null mean (.2557 for humans) independently reproduces the analytic chance level (.2553), which is a check on the procedure.

## 4. Test 2 — session-level test (secondary)

Each session was reduced to a single value, its chance-corrected accuracy, and these values were tested against zero with an exact Wilcoxon signed-rank test. The session is the genuinely independent unit, so this test would generalise beyond the observed sessions.

**Limitation.** With five human sessions the smallest attainable two-sided p is .0625 regardless of effect size. The human result is reported as that floor, not as a null finding. The synthetic conditions are not so constrained (floors of .0005 and .0001).

| Condition | Sessions | Above chance | Median chance-corrected accuracy | Wilcoxon p | Smallest attainable p |
|---|---|---|---|---|---|
| Human | 5 | 5 of 5 | +.2223 | .0625 | .0625 |
| Enriched | 15 | 6 of 15 (6 below, 3 exactly at chance) | .0000 | .68 | .0005 |
| Basic | 14 | 9 of 14 | +.1771 | .14 | .0001 |

## 5. Test 3 — comparisons between conditions

Session-level chance-corrected accuracies compared with exact two-sided Mann-Whitney tests. Effect size is Cliff's delta. Holm correction applied across the four comparisons.

| Comparison | Medians | p (exact) | p (Holm) | Cliff's δ |
|---|---|---|---|---|
| Human vs enriched | +.2223 vs .0000 | **.011** | **.043** | +.76 |
| Human vs basic | +.2223 vs +.1771 | .16 | .31 | +.46 |
| Human vs synthetic pooled | +.2223 vs +.0834 | .029 | .087 | +.61 |
| Enriched vs basic | .0000 vs +.1771 | .35 | .35 | −.21 |

Human versus each condition separately is the primary comparison, because condition is the manipulated variable. The pooled comparison ignores that distinction and treats 29 sessions drawn from three replicates of five focus groups as one independent sample.

## 6. Eligibility and sample sizes

To build a profile, a participant must have a 50-word extract in the held-out question and in **at least two others**. Two other questions are required so that the profile spans more than one topic; a profile built from a single question would capture subject matter rather than style. Each fold additionally requires **at least two eligible participants**, since attribution is a discrimination task and one candidate makes it undefined.

The rule discards folds, not sessions, and it applied identically to all three conditions. Four documents each lost one question:

| Document | Condition | Question lost |
|---|---|---|
| `human::fg5` | Human | Q4 |
| `E::fg2::R1` | Enriched | Q3 |
| `E::fg3::R2` | Enriched | Q1 |
| `D::fg2::R2` | Basic | Q2 |

One session was lost in full: **`D::fg1::R2`** (basic, FG1, replicate 2). Four of its five participants spoke in only two guide questions, so only one participant ever met the profile requirement and no fold reached two candidates. The session yields zero attribution trials, giving **n = 14** for the basic condition. The exclusion follows the frozen eligibility rule and is recorded in the coverage block of the analysis output (`coverage 4/5`, `focus_groups_without_an_eligible_fold: ["fg1"]`).

Under a relaxed variant requiring only one other profile question, this session contributes a chance-corrected accuracy of exactly .0000 and the basic median moves from +.1771 to +.1667. That variant is a post-hoc amendment to a frozen rule and is not adopted.

**The two Level 3 measures do not share a denominator.** Attribution is n = 5 / 15 / 14 for the reason above. Between-speaker lexical similarity requires no cross-question profile — it compares participants within a single question — but in the frozen implementation it inherits the same eligibility gate and is therefore also n = 14 for the basic condition. Recovering that session for the similarity measure alone returns a basic median of .260 rather than .258, and .267 rather than .268 for enriched, since widening the gate admits additional cells elsewhere. This is reported as a sensitivity, not as the primary figure.

## 7. Findings

Human groups exceeded chance decisively on the permutation test, with all five sessions individually above chance. The enriched condition did not exceed chance by either test: its median session performed exactly at chance and as many sessions fell below it as above. The basic condition exceeded chance on the permutation test but was not corroborated at session level, where five of fourteen sessions fell below chance; it is reported as equivocal. Human sessions outperformed enriched sessions with a large effect surviving correction for multiple comparisons; the human–basic difference was not resolved at these sample sizes.

## 8. Provenance

The attribution pipeline was independently reproduced before testing and matched the committed analysis output on every field except its build timestamp.

| Item | Location |
|---|---|
| Attribution analysis output | `analysis/production_evaluation/agent_fidelity/agent_fidelity_stylometry.json` |
| Test results, per-session values, permutation nulls | `agent_fidelity_attribution_inference.json` (this folder) |
| Permutation seed | 20260808 |
| Permutations per condition | 20,000 |
