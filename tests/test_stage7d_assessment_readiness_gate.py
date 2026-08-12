import os
import csv
import json

base_dir = "docs/testing/stage7d_assessment_readiness_gate"

def test_stage7d_directory_exists():
    assert os.path.exists(base_dir)
    assert os.path.isdir(base_dir)

def test_assessment_artifact_manifest_csv_exists_and_columns():
    path = os.path.join(base_dir, "assessment_artifact_manifest.csv")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "artifact_name" in reader.fieldnames
        assert "artifact_type" in reader.fieldnames
        assert "required_for" in reader.fieldnames
        assert "expected_path_pattern" in reader.fieldnames
        assert "current_presence_status" in reader.fieldnames
        assert "produced_by_stage_or_script" in reader.fieldnames
        assert "consumed_by_stage_or_script" in reader.fieldnames
        assert "blocking_if_missing" in reader.fieldnames
        assert "notes" in reader.fieldnames

def test_assessment_metric_registry_csv_exists_and_columns():
    path = os.path.join(base_dir, "assessment_metric_registry.csv")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "metric_name" in reader.fieldnames
        assert "source_track" in reader.fieldnames
        assert "current_implementation_status" in reader.fieldnames
        assert "human_availability" in reader.fieldnames
        assert "synthetic_availability" in reader.fieldnames
        assert "comparability_status" in reader.fieldnames
        assert "final_status_if_known" in reader.fieldnames
        assert "required_inputs" in reader.fieldnames
        assert "produced_by" in reader.fieldnames
        assert "used_by" in reader.fieldnames
        assert "current_stage_use" in reader.fieldnames
        assert "future_stage_use" in reader.fieldnames
        assert "claim_allowed" in reader.fieldnames
        assert "limitations" in reader.fieldnames

        metrics = [row["metric_name"] for row in reader]
        assert "participant_to_participant_edge_density" in metrics

def test_metric_registry_marks_edge_density_as_process():
    path = os.path.join(base_dir, "assessment_metric_registry.csv")
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["metric_name"] == "participant_to_participant_edge_density":
                assert row["source_track"] == "PROCESS"
                assert "Not thematic equivalence" in row["limitations"]

def test_corpus_comparison_manifest_csv_exists_and_columns():
    path = os.path.join(base_dir, "corpus_comparison_manifest.csv")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "corpus_or_run_id" in reader.fieldnames
        assert "corpus_type" in reader.fieldnames
        assert "topic_domain" in reader.fieldnames
        assert "source_stage" in reader.fieldnames
        assert "artifact_path" in reader.fieldnames
        assert "comparable_to" in reader.fieldnames
        assert "comparison_level_allowed" in reader.fieldnames
        assert "comparison_level_not_allowed" in reader.fieldnames
        assert "reason" in reader.fieldnames
        assert "caveats" in reader.fieldnames

        has_restriction = False
        for row in reader:
            if "Do not allow theme-equivalence claims across unrelated topics" in row["caveats"]:
                has_restriction = True
        assert has_restriction

def test_assessment_stage_roadmap_md_exists_and_contains_stages():
    path = os.path.join(base_dir, "ASSESSMENT_STAGE_ROADMAP.md")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        for stage in ["Stage 8A", "Stage 8B", "Stage 8C", "Stage 8D", "Stage 8E", "Stage 8F", "Stage 8G"]:
            assert stage in content

def test_stage7d_assessment_readiness_gate_report_md_exists():
    path = os.path.join(base_dir, "STAGE7D_ASSESSMENT_READINESS_GATE_REPORT.md")
    assert os.path.exists(path)

def test_readiness_report_constraints():
    path = os.path.join(base_dir, "STAGE7D_ASSESSMENT_READINESS_GATE_REPORT.md")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check for allowed final verdict
    verdicts = ["READY_FOR_STAGE_8A", "PARTIAL_READY", "BLOCKED"]
    assert any(v in content for v in verdicts)

    # Check for disallowed claims restrictions
    clean_content = content.lower().replace("**", "")
    assert "not yet allowed to claim synthetic focus groups are equivalent" in clean_content
    assert "not yet allowed to claim thematic equivalence" in clean_content
    assert "not yet allowed to claim outcome validity" in clean_content

    # Check that Stage 8A is explicitly diagnostic only
    if "ready_for_stage_8a" in clean_content:
        assert "only as a diagnostic smoke test" in clean_content

