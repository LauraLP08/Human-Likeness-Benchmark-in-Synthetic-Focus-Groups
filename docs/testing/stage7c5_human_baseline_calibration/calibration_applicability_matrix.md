# Calibration Applicability Matrix

| Metric | Track | Comparable | Proposed Status | Final Status | Recommended Use | Topic Sensitive |
|---|---|---|---|---|---|---|
| dialogue_turn_count | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| moderator_turn_count | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| participant_turn_count | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| participant_count | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| moderator_word_share | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| gini_turns | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| gini_words | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| max_consecutive_participant_turns | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| avg_participant_turn_words | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| median_participant_turn_words | process_metrics | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| participant_to_participant_edge_density | interaction_graph | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| total_edges | interaction_graph | conditional | ILLUSTRATIVE_ONLY | ILLUSTRATIVE_ONLY | use_as_descriptive_context_only | No |
| total_repairs | distinctiveness | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| total_hedges | distinctiveness | yes | CALIBRATION_REFERENCE | CALIBRATION_REFERENCE | use_as_soft_reference_range | No |
| participant_lexical_diversity_range | distinctiveness | yes | ILLUSTRATIVE_ONLY | ILLUSTRATIVE_ONLY | use_as_descriptive_context_only | Yes |
| sections_completed | research_design_coverage | no | NOT_COMPARABLE | NOT_COMPARABLE | do_not_compare | Yes |
| section_coverage_rate | research_design_coverage | no | NOT_COMPARABLE | NOT_COMPARABLE | do_not_compare | Yes |
| section_transition_count | research_design_coverage | no | NOT_COMPARABLE | NOT_COMPARABLE | do_not_compare | Yes |
| stage_direction_count | mechanical_integrity | no | NOT_COMPARABLE | NOT_COMPARABLE | do_not_compare | No |
| nonverbal_marker_count | mechanical_integrity | no | HUMAN_ONLY_CONTEXTUAL | HUMAN_ONLY_CONTEXTUAL | use_as_descriptive_context_only | No |
| internal_overvalidation_entries_total | moderator_quality | no | SYNTHETIC_ONLY_NOT_APPLICABLE | SYNTHETIC_ONLY_NOT_APPLICABLE | synthetic_only_audit_metric | No |
| strict_target_count | moderator_quality | no | SYNTHETIC_ONLY_NOT_APPLICABLE | SYNTHETIC_ONLY_NOT_APPLICABLE | synthetic_only_audit_metric | No |
| visible_overvalidation_hits | moderator_quality | yes | ILLUSTRATIVE_ONLY | ILLUSTRATIVE_ONLY | use_as_descriptive_context_only | No |
