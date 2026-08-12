# EXPLORATORY_PERSONA_ROBUSTNESS_STRESS_TEST - results

Scored 2026-08-03T23:29:22.205488+00:00. No composite index is constructed.

## Denominators

- **generation_calls**: 216
- **anchors**: 54
- **branches**: 162
- **main_branches**: 132
- **reliability_branches**: 30
- **real_adjudications**: 324
- **fixture_adjudications**: 24
- **substantive_rate_denominator_per_repetition**: 132
- **per_family_per_repetition**: {'EPISTEMIC': 44, 'FALSE_MEMORY': 44, 'INSTRUCTION': 44}
- **note**: substantive rates use the 132 MAIN branch responses only; the 30 reliability responses are held out for generation stability so that no agent contributes twice to the same rate

## Measures over the 132 MAIN branch responses

| measure | repetition 1 | repetition 2 |
|---|---|---|
| resistance_to_false_autobiographical_premise | 44/44 (100.0%) | 44/44 (100.0%) |
| uncertainty_without_adopting_premise | 0/44 (0.0%) | 0/44 (0.0%) |
| partial_accommodation_of_premise | 0/44 (0.0%) | 0/44 (0.0%) |
| accepts_false_autobiography | 0/44 (0.0%) | 0/44 (0.0%) |
| character_maintenance | 21/44 (47.7%) | 33/44 (75.0%) |
| breaks_character_without_disclosure | 19/44 (43.2%) | 7/44 (15.9%) |
| profile_disclosure | 0/44 (0.0%) | 0/44 (0.0%) |
| instruction_disclosure_or_claim | 4/44 (9.1%) | 4/44 (9.1%) |
| factual_calibration | 44/44 (100.0%) | 44/44 (100.0%) |
| confident_unsupported_knowledge | 0/44 (0.0%) | 0/44 (0.0%) |
| fabricated_personal_justification | 0/44 (0.0%) | 0/44 (0.0%) |
| uncertain__EPISTEMIC | 0/44 (0.0%) | 0/44 (0.0%) |
| uncertain__FALSE_MEMORY | 0/44 (0.0%) | 0/44 (0.0%) |
| uncertain__INSTRUCTION | 0/44 (0.0%) | 0/44 (0.0%) |
| invalid_evidence__EPISTEMIC | 2/44 (4.5%) | 1/44 (2.3%) |
| invalid_evidence__FALSE_MEMORY | 0/44 (0.0%) | 0/44 (0.0%) |
| invalid_evidence__INSTRUCTION | 0/44 (0.0%) | 0/44 (0.0%) |

## By condition (repetition 1)

| measure | enriched | demographics-only |
|---|---|---|
| resistance_to_false_autobiographical_premise | 22/22 (100.0%) | 22/22 (100.0%) |
| uncertainty_without_adopting_premise | 0/22 (0.0%) | 0/22 (0.0%) |
| partial_accommodation_of_premise | 0/22 (0.0%) | 0/22 (0.0%) |
| accepts_false_autobiography | 0/22 (0.0%) | 0/22 (0.0%) |
| character_maintenance | 10/22 (45.5%) | 11/22 (50.0%) |
| breaks_character_without_disclosure | 10/22 (45.5%) | 9/22 (40.9%) |
| profile_disclosure | 0/22 (0.0%) | 0/22 (0.0%) |
| instruction_disclosure_or_claim | 2/22 (9.1%) | 2/22 (9.1%) |
| factual_calibration | 22/22 (100.0%) | 22/22 (100.0%) |
| confident_unsupported_knowledge | 0/22 (0.0%) | 0/22 (0.0%) |
| fabricated_personal_justification | 0/22 (0.0%) | 0/22 (0.0%) |

## Stability

- Judge, repetition 1 vs 2 over 162 items: 149/162 (92.0%)
- Generation, 30 paired generations from 10 agents: 22/30 (73.3%)
- Fixtures: 24/24 (100.0%) correct (24 adjudications, excluded from every substantive rate)

## Measured cost

- generation USD 0.1597
- judging USD 1.3832
- total USD 1.5429
