# Assessment Artifact Manifest

| artifact_name | artifact_type | required_for | expected_path_pattern | current_presence_status | produced_by_stage_or_script | consumed_by_stage_or_script | blocking_if_missing | notes |
|---|---|---|---|---|---|---|---|---|
| transcript.json | JSON | Synthetic run | docs/testing/*/transcript.json | PRESENT | simulation_runner.py | assessment/metrics.py | TRUE |  |
| transcript.txt | TXT | Synthetic run | docs/testing/*/transcript.txt | PRESENT | simulation_runner.py | none | FALSE |  |
| moderator_log.json | JSON | Synthetic run | docs/testing/*/moderator_log.json | PRESENT | moderator_brain | UI/Results Viewer | FALSE |  |
| assessment_metrics.json | JSON | Synthetic run | docs/testing/*/assessment_metrics.json | PRESENT | assessment/loader.py | synthetic_backtest_human_calibration.py | TRUE |  |
| interaction_edges.csv | CSV | Synthetic run | docs/testing/*/interaction_edges.csv | PRESENT | interaction_graph.py | synthetic_backtest_human_calibration.py | TRUE |  |
| state snapshots if applicable | JSON | Synthetic run | docs/testing/*/*.json | PRESENT | simulation_runner.py | none | FALSE |  |
| guide/config file if available | JSON | Synthetic run | configs/* | PRESENT | human_author | simulation_runner.py | FALSE |  |
| participant/agent definitions if available | JSON | Synthetic run | configs/agents/* | PRESENT | human_author | simulation_runner.py | FALSE |  |
| transcript.json | JSON | Human baseline | data/transcripts/human_baseline_standardization_claude_v1/*/transcript.json | PRESENT | human_transcript_standardization | human_baseline_calibration.py | TRUE |  |
| assessment_metrics.json | JSON | Human baseline | docs/testing/assessments_hardened/*/assessment_metrics.json | PRESENT | assessment/loader.py | human_baseline_calibration.py | TRUE |  |
| per-baseline reconciliation row | CSV | Human baseline | docs/testing/stage7c5_human_baseline_calibration/per_baseline_reconciliation_table.csv | PRESENT | human_baseline_calibration.py | stage 7c.5 gate | TRUE |  |
| human_process_calibration_summary.json | JSON | Human baseline | docs/testing/stage7c5_human_baseline_calibration/human_process_calibration_summary.json | PRESENT | human_baseline_calibration.py | synthetic_backtest_human_calibration.py | TRUE |  |
| calibration_applicability_matrix.csv | CSV | Human baseline | docs/testing/stage7c5_human_baseline_calibration/calibration_applicability_matrix.csv | PRESENT | human_baseline_calibration.py | manual review | FALSE |  |
| human_calibration_gate_check.json | JSON | Cross-stage | docs/testing/stage7c5_human_baseline_calibration/human_process_calibration_summary.json | PRESENT | human_baseline_calibration.py | synthetic_backtest_human_calibration.py | TRUE |  |
| synthetic_vs_human_process_reference_matrix.csv | CSV | Cross-stage | docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv | PRESENT | synthetic_backtest_human_calibration.py | manual review | FALSE |  |
| stage6c_to_6f_progression_table.csv | CSV | Cross-stage | docs/testing/stage7c6_synthetic_backtest_human_calibration/stage6c_to_6f_progression_table.csv | PRESENT | synthetic_backtest_human_calibration.py | manual review | FALSE |  |
| known_issue_visibility_matrix.md | MD | Cross-stage | docs/testing/stage7c6_synthetic_backtest_human_calibration/known_issue_visibility_matrix.md | PRESENT | synthetic_backtest_human_calibration.py | manual review | FALSE |  |
| synthetic_metric_inventory_by_run.json | JSON | Cross-stage | docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_metric_inventory_by_run.json | PRESENT | synthetic_backtest_human_calibration.py | manual review | FALSE |  |
| Stage 7C.5 and Stage 7C.6 reports | MD | Cross-stage | docs/testing/stage7c*/*.md | PRESENT | assessment scripts | manual review | TRUE |  |
