# STAGE8A SMOKE TEST SCORECARD REPORT

## 1. Executive Verdict
**PARTIAL_READY**

## 2. Scope Statement
* This is a diagnostic smoke test only.
* This is not outcome validity.
* This is not thematic equivalence.
* This is not synthetic-human equivalence.
* GREEN does not mean validated.
* Stage 8B is traceability foundations, not validity.

## 3. Summary Table by Run
* stage6c_grocery_topic_development_01: GREEN (Red: 0, Amber: 0)
* stage6d_prompt_cleanup_verification_01: GREEN (Red: 0, Amber: 0)
* stage6e_naturalness_topic_tethering_verification_01: GREEN (Red: 0, Amber: 0)
* stage6f_internal_reasoning_calibration_verification_01: AMBER (Red: 0, Amber: 1)

## 4. Key Red Flags
* None observed.

## 5. Amber Review Items
The only AMBER item is Stage 6F low turn count.

* run_id: stage6f_internal_reasoning_calibration_verification_01
* diagnostic_name: Observable conversation structure
* value: Turns: 13, Parts: 4
* status: AMBER
* interpretation: Too short
* recommended_action: Review run if amber/red

## 6. Non-assessable Diagnostics
* None in these runs.

## 7. Artifact Limitations
* Proxies are crude and rely on exact match or basic variance.

## 8. Recommended Next Action
Review amber items before proceeding to Stage 8B Traceability Foundations.
