import os
import csv
import json

base_dir = "docs/testing/stage8a_smoke_test_scorecard"

def test_1_output_directory_exists():
    assert os.path.exists(base_dir)

def test_2_scorecard_csv_exists_and_columns():
    path = os.path.join(base_dir, "smoke_test_scorecard.csv")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "run_id" in reader.fieldnames
        assert "diagnostic_id" in reader.fieldnames
        assert "diagnostic_name" in reader.fieldnames
        assert "value" in reader.fieldnames
        assert "status" in reader.fieldnames
        assert "severity" in reader.fieldnames
        assert "evidence_source" in reader.fieldnames
        assert "interpretation" in reader.fieldnames
        assert "limitation" in reader.fieldnames
        assert "recommended_action" in reader.fieldnames

def test_3_run_level_summary_csv_exists_and_columns():
    path = os.path.join(base_dir, "run_level_smoke_summary.csv")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "run_id" in reader.fieldnames
        assert "overall_smoke_status" in reader.fieldnames
        assert "blocking_red_count" in reader.fieldnames
        assert "red_count" in reader.fieldnames
        assert "amber_count" in reader.fieldnames
        assert "green_count" in reader.fieldnames
        assert "not_assessable_count" in reader.fieldnames
        assert "artifact_missing_count" in reader.fieldnames
        assert "ready_for_deeper_diagnostics" in reader.fieldnames
        assert "summary_reason" in reader.fieldnames

def test_4_smoke_test_thresholds_json_exists():
    assert os.path.exists(os.path.join(base_dir, "smoke_test_thresholds.json"))

def test_5_smoke_test_thresholds_md_exists():
    assert os.path.exists(os.path.join(base_dir, "smoke_test_thresholds.md"))

def test_6_artifact_issue_log_csv_exists():
    path = os.path.join(base_dir, "smoke_test_artifact_issue_log.csv")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "run_id" in reader.fieldnames
        assert "artifact_name" in reader.fieldnames
        assert "expected_path" in reader.fieldnames
        assert "issue_type" in reader.fieldnames
        assert "blocking" in reader.fieldnames
        assert "diagnostic_affected" in reader.fieldnames
        assert "note" in reader.fieldnames

def test_7_final_report_md_exists():
    assert os.path.exists(os.path.join(base_dir, "STAGE8A_SMOKE_TEST_SCORECARD_REPORT.md"))

def test_8_to_12_and_21_report_contents():
    path = os.path.join(base_dir, "STAGE8A_SMOKE_TEST_SCORECARD_REPORT.md")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 8. Contains one of the verdicts
    assert any(v in content for v in ["READY_FOR_STAGE_8B", "PARTIAL_READY", "BLOCKED"])
    
    clean_content = content.lower()
    # 9.
    assert "not outcome validity" in clean_content
    # 10.
    assert "not thematic equivalence" in clean_content
    # 11.
    assert "not synthetic-human equivalence" in clean_content
    # 12.
    assert "green does not mean validated" in clean_content
    # 21.
    if "READY_FOR_STAGE_8B" in content:
        assert "stage 8b is traceability foundations, not validity" in clean_content

def test_13_to_16_scorecard_contents():
    path = os.path.join(base_dir, "smoke_test_scorecard.csv")
    runs = set()
    diagnostics = set()
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            runs.add(row["run_id"])
            diagnostics.add(row["diagnostic_name"])
            # 17. Scorecard status values are only from allowed status values.
            assert row["status"] in ["GREEN", "AMBER", "RED", "NOT_ASSESSABLE", "ARTIFACT_MISSING"]
            
    # 13.
    expected_runs = {"stage6c_grocery_topic_development_01", "stage6d_prompt_cleanup_verification_01", "stage6e_naturalness_topic_tethering_verification_01", "stage6f_internal_reasoning_calibration_verification_01"}
    assert expected_runs.issubset(runs)

    # 14.
    assert "Participant-to-participant uptake" in diagnostics # Maps to edge density
    # 15.
    assert "Moderator footprint" in diagnostics
    # 16.
    assert "Participant-to-participant uptake" in diagnostics

def test_18_summary_status_values():
    path = os.path.join(base_dir, "run_level_smoke_summary.csv")
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            assert row["overall_smoke_status"] in ["GREEN", "AMBER", "RED", "INCOMPLETE", "BLOCKED"] # Added BLOCKED

def test_19_thresholds_file_marks_empirically_validated_false():
    path = os.path.join(base_dir, "smoke_test_thresholds.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for t in data:
        assert str(t.get("empirically_validated", "")).lower() == "false"

def test_20_if_blocking_red_not_ready():
    summ_path = os.path.join(base_dir, "run_level_smoke_summary.csv")
    rep_path = os.path.join(base_dir, "STAGE8A_SMOKE_TEST_SCORECARD_REPORT.md")
    
    with open(summ_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        has_blocking = any(int(row["blocking_red_count"]) > 0 for row in reader)

    with open(rep_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    if has_blocking:
        assert "READY_FOR_STAGE_8B" not in content

def test_22_script_contains_makedirs():
    script_path = "assessment/stage8a_smoke_test_scorecard.py"
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "os.makedirs(OUT_DIR, exist_ok=True)" in content

def test_23_report_does_not_hardcode_amber():
    rep_path = os.path.join(base_dir, "STAGE8A_SMOKE_TEST_SCORECARD_REPORT.md")
    with open(rep_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Over-consensus and repetition proxies show minor warnings" not in content

def test_24_amber_items_represented_in_report():
    scorecard_path = os.path.join(base_dir, "smoke_test_scorecard.csv")
    amber_items = []
    with open(scorecard_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["status"] == "AMBER":
                amber_items.append(row)

    rep_path = os.path.join(base_dir, "STAGE8A_SMOKE_TEST_SCORECARD_REPORT.md")
    with open(rep_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not amber_items:
        assert "No AMBER diagnostics observed" in content
    elif len(amber_items) == 1 and amber_items[0]["run_id"] == "stage6f_internal_reasoning_calibration_verification_01" and amber_items[0]["diagnostic_name"] == "Observable conversation structure":
        assert "The only AMBER item is Stage 6F low turn count" in content
    else:
        for item in amber_items:
            assert item["run_id"] in content
            assert item["diagnostic_name"] in content
            assert item["value"] in content

def test_25_participant_turn_helper_logic():
    from assessment.stage8a_smoke_test_scorecard import get_speaker_label, is_moderator_turn, is_participant_turn
    
    # Test moderator exclusion
    turn1 = {"speaker_id": "MODERATOR"}
    assert is_moderator_turn(turn1)
    assert not is_participant_turn(turn1)
    
    turn2 = {"speaker": "mod"}
    assert is_moderator_turn(turn2)
    assert not is_participant_turn(turn2)
    
    turn3 = {"speaker_name": "Moderator"}
    assert is_moderator_turn(turn3)
    assert not is_participant_turn(turn3)
    
    turn4 = {"speaker_id": "MOD"}
    assert is_moderator_turn(turn4)
    assert not is_participant_turn(turn4)
    
    turn5 = {"speaker_name": "system"}
    assert is_moderator_turn(turn5)
    assert not is_participant_turn(turn5)
    
    # Test participant inclusion
    turn6 = {"speaker_id": "P1"}
    assert not is_moderator_turn(turn6)
    assert is_participant_turn(turn6)
    
    turn7 = {"speaker": "Participant 2"}
    assert not is_moderator_turn(turn7)
    assert is_participant_turn(turn7)
