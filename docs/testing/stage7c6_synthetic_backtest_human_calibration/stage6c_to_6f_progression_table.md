# Stage 6C to 6F Progression

| Dimension | Metric Used | 6C | 6D | 6E | 6F | Classification | Reason |
|---|---|---|---|---|---|---|---|
| internal over-validation reduction | internal_overvalidation_entries_total | 19 | 19 | 19 | 11 | IMPROVED_AS_EXPECTED | Metric decreased |
| visible over-validation | visible_overvalidation_hits | 1 | 5 | 0 | 0 | IMPROVED_AS_EXPECTED | Metric decreased |
| named-speaker targeting mismatch | strict_target_count | 1 | 4 | 3 | 0 | IMPROVED_AS_EXPECTED | Metric decreased |
| participant-to-participant interaction | participant_to_participant_edge_density | 0.9166666666666666 | 1.0 | 0.9166666666666666 | 0.5 | STILL_PROBLEMATIC | Metric regressed |
| moderator word share | moderator_word_share | 0.12026850643296662 | 0.1927986906710311 | 0.13171993349344172 | 0.10472972972972973 | IMPROVED_AS_EXPECTED | Metric decreased |
| participation balance | gini_words | 0.1048113607432073 | 0.0671127331684569 | 0.1608510638267855 | 0.15188679244695225 | STILL_PROBLEMATIC | Metric regressed or remained high |
| turn length / long monologue rate | max_consecutive_participant_turns | 5 | 2 | 5 | 5 | STABLE | No change |
| topic tethering | section_transition_count | 1 | 1 | 1 | 0 | STILL_PROBLEMATIC | Metric regressed |
| section coverage | sections_completed | 1 | 1 | 1 | 0 | STILL_PROBLEMATIC | Metric regressed |
| concreteness / abstraction | participant_lexical_diversity_range | 0.10348061554718974 | 0.044929381593929174 | 0.13375079264426126 | 0.18697786762582375 | NOT_COMPARABLE_TO_HUMAN | N/A |
| repair/self-correction markers | total_repairs | 6 | 3 | 6 | 4 | STILL_PROBLEMATIC | Metric regressed |
| synthetic-only metrics that remain important even without human comparison | internal_overvalidation_entries_total | 19 | 19 | 19 | 11 | IMPROVED_AS_EXPECTED | Metric decreased |
