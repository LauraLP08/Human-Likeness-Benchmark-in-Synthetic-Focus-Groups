# Smoke Test Thresholds

| Diagnostic | Green Rule | Amber Rule | Red Rule | Rationale | Limitation | Validated |
|---|---|---|---|---|---|---|
| Artifact completeness | All present | N/A | Any missing | Need basic files | Checks presence not validity | False |
| Observable conversation structure | Turn count > 20, >1 participants | Low turn count | No turns or no participants | Basic structure check | Quantity not quality | False |
| Moderator footprint | Word share 0.1-0.4 | >0.4 or <0.05 | >0.6 or 0 | Moderator shouldn't dominate | Word count is a crude proxy | False |
| Participant-to-participant uptake | Edge density > 0.1 | 0 < x <= 0.1 | 0 or missing | Focus groups must have cross-talk | Quantity not depth | False |
| Participation balance | Gini < 0.4 | Gini >= 0.4 or Gini < 0.05 | Gini > 0.6 | Avoid total dominance by one agent | Proxy only | False |
| Over-consensus | Disagreement markers > 0 | 0 markers | N/A | Check for echo chambers | Keyword proxy only | False |
| Repetition | Low duplicates | Moderate duplicates | High duplicates | Check for loop collapse | Exact match proxy only | False |
| Specificity | Richness proxies > 0 | 0 proxies | N/A | Avoid generic responses | Proxy only | False |
| Speaker distinguishability | Std dev of lengths > 0 | Near 0 variance | N/A | Agents should vary | Length variance proxy | False |
| Process metric availability | All core metrics present | N/A | Missing core metrics | Required for later stages | Presence only | False |
| Claim boundary compliance | Report meets constraints | N/A | N/A | Policy | N/A | False |
