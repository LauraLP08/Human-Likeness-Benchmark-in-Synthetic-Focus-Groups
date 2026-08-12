# Human Process Calibration Summary

**Human Baselines from transcript.json**: 7
**Human Baselines from assessments**: 7
**Total Dialogue Turns from transcript.json**: 649
**Total Dialogue Turns from assessments**: 649
**Count Match**: True
**Turn Match**: True

> **CAUTION**: Stage 7C.5 establishes which human baseline metrics may be used for process calibration. Synthetic-vs-human comparison should be run only after this calibration gate is reviewed. This does not validate outcome/theme content, and all thresholds derived from this n=7 sample remain provisional soft reference ranges.

## Metrics Evaluation
### dialogue_turn_count
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 53.0 - 145.0
- Mean: 92.71428571428571, Median: 86.0
- Limitation/Reason: Fundamental conversational volume

### moderator_turn_count
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 29.0 - 75.0
- Mean: 48.285714285714285, Median: 43.0
- Limitation/Reason: Moderator intervention frequency

### participant_turn_count
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 24.0 - 70.0
- Mean: 43.714285714285715, Median: 43.0
- Limitation/Reason: Participant intervention frequency

### participant_count
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 3.0 - 8.0
- Mean: 5.428571428571429, Median: 5.0
- Limitation/Reason: Number of participants in focus group

### moderator_word_share
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 0.16191454747838 - 0.3559818421437985
- Mean: 0.27031816205685044, Median: 0.33072281422518934
- Limitation/Reason: Core metric of facilitator dominance

### gini_turns
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 0.05555555520679012 - 0.30978260838374294
- Mean: 0.13877057130138384, Median: 0.11428571409081645
- Limitation/Reason: Participant equity metric

### gini_words
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 0.05282496865769315 - 0.4040797765182782
- Mean: 0.19325708238723127, Median: 0.15035570082416805
- Limitation/Reason: Participant equity metric

### max_consecutive_participant_turns
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 1.0 - 3.0
- Mean: 1.4285714285714286, Median: 1.0
- Limitation/Reason: Indicator of participant-to-participant flow

### avg_participant_turn_words
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 135.28070175438597 - 244.7906976744186
- Mean: 166.3982014958432, Median: 147.06521739130434
- Limitation/Reason: Turn length distribution

### median_participant_turn_words
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 126.0 - 173.0
- Mean: 141.14285714285714, Median: 132.0
- Limitation/Reason: Turn length distribution

### participant_to_participant_edge_density
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 0.013888888888888888 - 1.0
- Mean: 0.38531746031746034, Median: 0.14285714285714285
- Limitation/Reason: Shows cross-talk levels

### total_edges
- Proposed Status: ILLUSTRATIVE_ONLY
- Final Status: **ILLUSTRATIVE_ONLY**
- Observed range (soft reference): 63.0 - 164.0
- Mean: 99.71428571428571, Median: 88.0
- Limitation/Reason: Depends on length of group

### total_repairs
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 2.0 - 16.0
- Mean: 7.0, Median: 7.0
- Limitation/Reason: Measures human-like self-correction

### total_hedges
- Proposed Status: CALIBRATION_REFERENCE
- Final Status: **CALIBRATION_REFERENCE**
- Observed range (soft reference): 17.0 - 42.0
- Mean: 27.714285714285715, Median: 25.0
- Limitation/Reason: Measures uncertainty language

### participant_lexical_diversity_range
- Proposed Status: ILLUSTRATIVE_ONLY
- Final Status: **ILLUSTRATIVE_ONLY**
- Observed range (soft reference): 0.05660251331313587 - 0.38033276450511944
- Mean: 0.1620597517983854, Median: 0.09189402521227652
- Limitation/Reason: Depends on topic and text length

### sections_completed
- Proposed Status: NOT_COMPARABLE
- Final Status: **NOT_COMPARABLE**
- Observed range (soft reference): 0.0 - 0.0
- Mean: 0.0, Median: 0.0
- Limitation/Reason: Guide structure differs heavily between topics

### section_coverage_rate
- Proposed Status: NOT_COMPARABLE
- Final Status: **NOT_COMPARABLE**
- Observed range (soft reference): 0.0 - 0.0
- Mean: 0.0, Median: 0.0
- Limitation/Reason: Guide structure differs heavily between topics

### section_transition_count
- Proposed Status: NOT_COMPARABLE
- Final Status: **NOT_COMPARABLE**
- Observed range (soft reference): 0.0 - 0.0
- Mean: 0.0, Median: 0.0
- Limitation/Reason: Section markers vary by dataset (QESB has headings, PHIND does not)

### stage_direction_count
- Proposed Status: NOT_COMPARABLE
- Final Status: **NOT_COMPARABLE**
- Observed range (soft reference): 1.0 - 12.0
- Mean: 5.0, Median: 4.0
- Limitation/Reason: Humans use [inaudible], synthetic uses *laughs*. Not directly equivalent.

### nonverbal_marker_count
- Proposed Status: HUMAN_ONLY_CONTEXTUAL
- Final Status: **HUMAN_ONLY_CONTEXTUAL**
- Observed range (soft reference): 0.0 - 47.0
- Mean: 13.571428571428571, Median: 0.0
- Limitation/Reason: Captures human-only transcription notes

### internal_overvalidation_entries_total
- Proposed Status: SYNTHETIC_ONLY_NOT_APPLICABLE
- Final Status: **SYNTHETIC_ONLY_NOT_APPLICABLE**
- Observed range (soft reference): 0.0 - 0.0
- Mean: 0.0, Median: 0.0
- Limitation/Reason: Humans do not have internal reasoning logs

### strict_target_count
- Proposed Status: SYNTHETIC_ONLY_NOT_APPLICABLE
- Final Status: **SYNTHETIC_ONLY_NOT_APPLICABLE**
- Observed range (soft reference): 0.0 - 0.0
- Mean: 0.0, Median: 0.0
- Limitation/Reason: Humans do not have internal reasoning logs

### visible_overvalidation_hits
- Proposed Status: ILLUSTRATIVE_ONLY
- Final Status: **ILLUSTRATIVE_ONLY**
- Observed range (soft reference): 0.0 - 2.0
- Mean: 0.2857142857142857, Median: 0.0
- Limitation/Reason: Valid for human dialogue, but underpowered n=7

