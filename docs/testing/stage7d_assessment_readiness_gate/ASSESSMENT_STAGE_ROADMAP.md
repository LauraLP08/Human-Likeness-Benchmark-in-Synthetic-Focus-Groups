# ASSESSMENT STAGE ROADMAP

## Stage 7D — Assessment Readiness Gate
* **Purpose**: Establish data contracts, artifact manifests, metric registry, corpus comparison manifest, and stage roadmap.
* **Inputs**: Existing Stage 7C.5 and 7C.6 outputs.
* **Outputs**: Artifact manifests, metric registry, corpus comparison manifest, STAGE7D_ASSESSMENT_READINESS_GATE_REPORT.md.
* **Tests**: Python test validating output constraints.
* **Allowed claims**: Structural readiness to proceed to Stage 8A.
* **Disallowed claims**: No new validity claims.
* **Blocking conditions**: Missing artifacts or tests failing.

## Stage 8A — Smoke Test Scorecard
* **Purpose**: Fast diagnostic of catastrophic failures.
* **Inputs**: Synthetic transcripts, moderator logs, metric outputs.
* **Outputs**: Traffic-light style scorecard (GREEN / AMBER / RED).
* **Suggested areas**: Topic/guide coverage, moderator footprint, participant-to-participant uptake, participation balance, over-consensus, repetition, specificity, speaker distinguishability.
* **Allowed claims**: High-level diagnostic clearance.
* **Disallowed claims**: Validity or human-equivalence.
* **Blocking conditions**: RED status on critical parameters.

## Stage 8B — Traceability Foundations
* **Purpose**: Stable quote IDs, turn IDs, claim-to-evidence linking, source artifact checks.
* **Inputs**: Transcripts and logs.
* **Outputs**: Traceability indices.
* **Allowed claims**: System can trace findings to source.
* **Disallowed claims**: Validity or human-equivalence.
* **Blocking conditions**: Untraceable findings.

## Stage 8C — Process Validity Expansion
* **Purpose**: Expanded group dynamics, moderator action mix, interaction depth, network measures, agreement/disagreement markers.
* **Inputs**: Interaction graph, expanded transcripts.
* **Outputs**: Advanced network and process metrics.
* **Allowed claims**: Process alignment with observed phenomena.
* **Disallowed claims**: Thematic equivalence.
* **Blocking conditions**: Metrics fundamentally disagree with human baseline.

## Stage 8D — Human-Likeness Diagnostics
* **Purpose**: Linguistic and discourse-level diagnostics: specificity, hedging, disfluency, lexical diversity, stance entropy, speaker distinctiveness, persona consistency.
* **Inputs**: Transcript text, NLP models.
* **Outputs**: Diagnostic report on linguistic features.
* **Allowed claims**: Identified linguistic differences/similarities.
* **Disallowed claims**: Proof of human equivalence.
* **Blocking conditions**: Extreme linguistic divergence.

## Stage 8E — Outcome / Thematic Equivalence
* **Purpose**: Establish thematic validity using human-coded baselines.
* **Inputs**: Human baselines with known themes, synthetic runs on matched topics.
* **Outputs**: Thematic alignment scores, claim-to-quote traceability.
* **Allowed claims**: Thematic equivalence on specific matching topics.
* **Disallowed claims**: Comparing themes across unrelated topics.
* **Blocking conditions**: Lack of human-coded baseline or codebook.

## Stage 8F — Statistical Robustness Packaging
* **Purpose**: Bootstrap confidence intervals, permutation tests, within-corpus baselines, robustness checks.
* **Inputs**: All previously computed comparable metrics.
* **Outputs**: Statistical confidence report.
* **Allowed claims**: Statistical robustness of measured effects.
* **Disallowed claims**: Validity of unverified metrics.
* **Blocking conditions**: Insufficient sample size.

## Stage 8G — Report Assembly
* **Purpose**: Final HTML/Markdown audit report.
* **Inputs**: All Stage 8 outputs.
* **Outputs**: Final integrated report.
* **Allowed claims**: Comprehensive system audit summary.
* **Disallowed claims**: Generalization beyond tested topics.
* **Blocking conditions**: Any previous stage missing or blocked.
