import os
import json
import pytest

def test_human_calibration_gate_pass():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/human_calibration_gate_check.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["gate_status"] == "PASS"
    assert data["blocking_issue_count"] == 0

def test_human_calibration_summary_has_7_baselines():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/human_calibration_gate_check.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["human_baseline_count"] == 7

def test_human_calibration_summary_has_649_turns():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/human_calibration_gate_check.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["total_human_turns"] == 649

def test_only_calibration_reference_used():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["human_final_status"] != "CALIBRATION_REFERENCE":
                assert "INSIDE" not in row["comparison_classification"]
                assert "NEAR" not in row["comparison_classification"]
                assert "OUTSIDE" not in row["comparison_classification"]

def test_illustrative_only_metrics_not_used():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["human_final_status"] == "ILLUSTRATIVE_ONLY":
                assert row["comparison_classification"] == "HUMAN_REFERENCE_ILLUSTRATIVE_ONLY"

def test_not_comparable_metrics_excluded():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["human_final_status"] == "NOT_COMPARABLE":
                assert row["comparison_classification"] == "NOT_COMPARABLE"

def test_synthetic_only_audit_metrics():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["human_final_status"] == "SYNTHETIC_ONLY_NOT_APPLICABLE":
                assert row["comparison_classification"] == "SYNTHETIC_ONLY_AUDIT_METRIC"

def test_no_composite_score():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            assert "composite" not in row["human_metric"].lower()
            assert "overall_score" not in row["human_metric"].lower()

def test_no_outcome_validity_claim():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().lower().replace("**", "")
    assert "this is not outcome validity" in content
    assert "this is not theme equivalence" in content

def test_no_validated_synthetic_data_claim():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().lower().replace("**", "")
    assert "does not validate synthetic data" in content

def test_run_inventory_includes_all_runs():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_metric_inventory_by_run.json"
    with open(path, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    runs = [item["run_id"] for item in inventory]
    assert "stage6c_grocery_topic_development_01" in runs
    assert "stage6d_prompt_cleanup_verification_01" in runs
    assert "stage6e_naturalness_topic_tethering_verification_01" in runs
    assert "stage6f_internal_reasoning_calibration_verification_01" in runs

def test_missing_synthetic_assessment_does_not_silently_pass():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    import json
    inv_path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_metric_inventory_by_run.json"
    with open(inv_path, "r", encoding="utf-8") as f:
        inv = json.load(f)
    if not all(len(item["metric_keys_found"]) > 0 for item in inv):
        assert "STAGE7C6_SYNTHETIC_BACKTEST_PARTIAL" in content or "STAGE7C6_BLOCKED" in content

def test_comparison_matrix_contains_classification_labels():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        classifications = [row["comparison_classification"] for row in reader]
    assert "NOT_COMPARABLE" in classifications
    valid_labels = ["INSIDE_HUMAN_OBSERVED_RANGE", "NEAR_HUMAN_OBSERVED_RANGE", "OUTSIDE_HUMAN_OBSERVED_RANGE", "HUMAN_REFERENCE_ILLUSTRATIVE_ONLY", "NOT_COMPARABLE", "SYNTHETIC_ONLY_AUDIT_METRIC", "INSUFFICIENT_HUMAN_REFERENCE", "SYNTHETIC_METRIC_MISSING"]
    for c in classifications:
        assert c in valid_labels

def test_progression_table_contains_required_dimensions():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/stage6c_to_6f_progression_table.csv"
    import csv
    dims = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dims.append(row["dimension"])
    assert "internal over-validation reduction" in dims
    assert "visible over-validation" in dims
    assert "named-speaker targeting mismatch" in dims
    assert "participant-to-participant interaction" in dims
    assert "moderator word share" in dims
    assert "participation balance" in dims
    assert "turn length / long monologue rate" in dims
    assert "topic tethering" in dims
    assert "section coverage" in dims
    assert "concreteness / abstraction" in dims
    assert "repair/self-correction markers" in dims

def test_known_issue_visibility_matrix_generated():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/known_issue_visibility_matrix.md"
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "internal over-validation" in content
    assert "topic drift" in content

def test_backlog_item_for_per_baseline_reconciliation_not_unresolved_if_complete():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().lower()
    if "stage7c6_synthetic_backtest_with_human_calibration_complete" in content:
        assert "per-baseline transcript-vs-assessment reconciliation hardening" not in content
        assert "stage 7c.5 per-baseline reconciliation: complete" in content

def test_output_json_csv_md_files_created():
    assert os.path.exists("docs/testing/stage7c6_synthetic_backtest_human_calibration/human_calibration_gate_check.json")
    assert os.path.exists("docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_metric_inventory_by_run.json")
    assert os.path.exists("docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv")
    assert os.path.exists("docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.md")
    assert os.path.exists("docs/testing/stage7c6_synthetic_backtest_human_calibration/stage6c_to_6f_progression_table.csv")
    assert os.path.exists("docs/testing/stage7c6_synthetic_backtest_human_calibration/stage6c_to_6f_progression_table.md")

def test_report_contains_soft_process_references_caution():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "soft process reference" in content

# NEW PATCH TESTS
def test_synthetic_metric_inventory_generated():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_metric_inventory_by_run.json"
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    assert len(inventory) == 4
    for item in inventory:
        assert "run_id" in item
        assert "metric_keys_found" in item

def test_at_least_one_numeric_calibration_reference():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    if "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE" in content:
        import csv
        matrix = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
        found_numeric = False
        with open(matrix, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["human_final_status"] == "CALIBRATION_REFERENCE" and row["synthetic_value"] != "N/A":
                    found_numeric = True
        assert found_numeric

def test_matrix_not_complete_if_all_missing():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE" in content:
        import csv
        matrix = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
        all_missing = True
        with open(matrix, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["human_final_status"] == "CALIBRATION_REFERENCE" and row["mapping_status"] != "UNMAPPED":
                    all_missing = False
        assert not all_missing

def test_matrix_contains_at_least_one_inside_near_outside():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE" in content:
        import csv
        matrix = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
        found = False
        with open(matrix, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["comparison_classification"] in ["INSIDE_HUMAN_OBSERVED_RANGE", "NEAR_HUMAN_OBSERVED_RANGE", "OUTSIDE_HUMAN_OBSERVED_RANGE"]:
                    found = True
        assert found

def test_progression_table_not_all_na():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    if "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE" in content:
        import csv
        progression = "docs/testing/stage7c6_synthetic_backtest_human_calibration/stage6c_to_6f_progression_table.csv"
        found_non_na = False
        with open(progression, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["stage6c_value"] != "N/A" or row["stage6f_value"] != "N/A":
                    found_non_na = True
        assert found_non_na

def test_known_issue_visibility_matrix_logic():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/known_issue_visibility_matrix.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # It shouldn't say VISIBLE_WITH_DIRECT_METRIC if available is No
    lines = content.split("\n")
    for line in lines:
        if "|" in line and "VISIBLE_WITH_DIRECT_METRIC" in line:
            assert "Yes" in line

def test_visible_issue_includes_metric():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/known_issue_visibility_matrix.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")
    for line in lines[4:]: # skip header
        if "|" in line and "VISIBLE_WITH_DIRECT_METRIC" in line:
            parts = [p.strip() for p in line.split("|")]
            assert len(parts[2]) > 0 # Metric name

def test_human_metric_to_synthetic_mapping_saved():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            assert "mapping_status" in row
            assert row["mapping_status"] in ["MAPPED_EXACT", "MAPPED_ALIAS", "DERIVED_FROM_SYNTHETIC_TRANSCRIPT", "DERIVED_FROM_INTERACTION_EDGES", "UNMAPPED"]

def test_derived_metrics_source_label():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["mapping_status"] == "DERIVED_FROM_SYNTHETIC_TRANSCRIPT":
                assert row["synthetic_value"] != "N/A"

def test_low_mapping_coverage_yields_partial():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if mappings are printed
    if "Mapped EXACT: 0" in content and "Mapped ALIAS: 0" in content and "Derived from transcript: 0" in content:
        assert "STAGE7C6_SYNTHETIC_BACKTEST_PARTIAL" in content

def test_residual_problems_report_claim():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if "known issue visibility has supporting metrics: false" in content.lower():
        assert "known residual problems remain visible" not in content.lower()

def test_numeric_comparisons_occurred_flag():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    if "numeric comparisons occurred: false" in content.lower():
        assert "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE" not in content


def test_participant_edge_density_mapped():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["human_metric"] == "participant_to_participant_edge_density":
                assert row["mapping_status"] in ["MAPPED_EXACT", "DERIVED_FROM_INTERACTION_EDGES", "DERIVED_FROM_SYNTHETIC_TRANSCRIPT"]
                assert row["mapping_status"] != "UNMAPPED"
                assert row["synthetic_value"] != "N/A"

def test_visibility_for_insufficient_uptake():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/known_issue_visibility_matrix.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "insufficient participant-to-participant uptake" in content
    assert "participant_to_participant_edge_density" in content
    assert "VISIBLE_WITH_DIRECT_METRIC" in content or "NOT_VISIBLE_METRIC_MISSING" in content

def test_visibility_proxy_distinction():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/known_issue_visibility_matrix.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")
    for line in lines:
        if "topic drift" in line:
            assert "VISIBLE_WITH_PROXY" in line or "NOT_VISIBLE_METRIC_MISSING" in line
        if "insufficient participant-to-participant uptake" in line:
            assert "VISIBLE_WITH_DIRECT_METRIC" in line or "NOT_VISIBLE_METRIC_MISSING" in line

def test_p2p_edge_density_has_exactly_four_rows():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = sum(1 for row in reader if row["human_metric"] == "participant_to_participant_edge_density")
    assert count == 4

def test_p2p_edge_density_rows_validity():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["human_metric"] == "participant_to_participant_edge_density":
                assert row["mapping_status"] != "UNMAPPED"
                assert row["synthetic_value"] != "N/A"
                assert row["comparison_classification"] in ["INSIDE_HUMAN_OBSERVED_RANGE", "NEAR_HUMAN_OBSERVED_RANGE", "OUTSIDE_HUMAN_OBSERVED_RANGE"]

def test_final_report_not_complete_if_p2p_unmapped():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE" in content:
        import csv
        matrix = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
        with open(matrix, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["human_metric"] == "participant_to_participant_edge_density":
                    assert row["mapping_status"] != "UNMAPPED"
                    assert row["synthetic_value"] != "N/A"

def test_final_report_not_complete_if_progression_not_enough_data():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE" in content:
        import csv
        progression = "docs/testing/stage7c6_synthetic_backtest_human_calibration/stage6c_to_6f_progression_table.csv"
        with open(progression, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["dimension"] == "participant-to-participant interaction":
                    assert row["classification"] != "NOT_ENOUGH_DATA"

def test_known_issue_visibility_matrix_complete_status():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE" in content:
        kim_path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/known_issue_visibility_matrix.md"
        with open(kim_path, "r", encoding="utf-8") as f:
            kim_content = f.read()
        lines = kim_content.split("\n")
        for line in lines:
            if "insufficient participant-to-participant uptake" in line:
                assert "VISIBLE_WITH_DIRECT_METRIC" in line

def test_package_consistency():
    path = "docs/testing/stage7c6_synthetic_backtest_human_calibration/STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_RESULTS.md"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    matrix = "docs/testing/stage7c6_synthetic_backtest_human_calibration/synthetic_vs_human_process_reference_matrix.csv"
    import csv
    has_unmapped_p2p = False
    with open(matrix, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["human_metric"] == "participant_to_participant_edge_density" and row["mapping_status"] == "UNMAPPED":
                has_unmapped_p2p = True
    
    if has_unmapped_p2p:
        assert "STAGE7C6_SYNTHETIC_BACKTEST_WITH_HUMAN_CALIBRATION_COMPLETE" not in content
