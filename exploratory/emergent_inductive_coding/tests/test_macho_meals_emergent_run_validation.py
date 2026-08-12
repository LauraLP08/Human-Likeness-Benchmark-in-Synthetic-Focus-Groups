import json
import csv
from pathlib import Path
import pytest
import re

def test_macho_meals_emergent_run_validation_all_strict_points():
    out_dir = Path("docs/testing/macho_meals_emergent_run_validation")
    session_id = "macho_meals_emergent_full_run_02"
    canon_dir = Path(f"output/session_logs/{session_id}")
    live_out = out_dir / "live_run_outputs" / session_id
    
    assert out_dir.exists()
    assert canon_dir.exists(), "The canonical session log directory must exist."
    
    # 1. Verify Canonical Paths
    t_json = canon_dir / "transcript.json"
    t_txt = canon_dir / "transcript.txt"
    assert t_json.exists(), "Canonical transcript.json missing"
    assert t_txt.exists(), "Canonical transcript.txt missing"
    assert len(t_txt.read_text(encoding="utf-8").strip()) > 0, "Canonical transcript.txt is empty"
    try:
        j_data = json.loads(t_json.read_text(encoding="utf-8"))
        assert len(j_data) > 0, "Canonical transcript.json is empty"
    except Exception as e:
        pytest.fail(f"Could not load transcript.json: {e}")
        
    assert (canon_dir / "moderator_log.json").exists()
    assert (canon_dir / "api_calls.jsonl").exists()
    state_files = list(canon_dir.glob("state_turn_*.json"))
    assert len(state_files) > 0, "At least one state_turn_*.json must exist in canonical dir"

    # 2. Verify Testing Mirror Copies
    assert (live_out / "transcript.json").exists()
    copy_t_txt = live_out / "transcript.txt"
    assert copy_t_txt.exists(), "Copied transcript.txt is missing in live_run_outputs mirror"
    assert len(copy_t_txt.read_text(encoding="utf-8").strip()) > 0, "Copied transcript.txt is empty"
    
    # 3. Model & Agents Verification
    asset_manifest = (out_dir / "asset_manifest.csv").read_text(encoding="utf-8")
    assert "macho_meals_plant_based_masculinity_uk" in asset_manifest
    agent_manifest = (out_dir / "agent_selection_manifest.csv").read_text(encoding="utf-8")
    for agent in ["mm_fg1_amir", "mm_fg1_david", "mm_fg1_ibrahim", "mm_fg1_isaiah", "mm_fg1_will"]:
        assert agent in agent_manifest
        
    audit_csv = out_dir / "model_usage_audit.csv"
    assert audit_csv.exists()
    with open(audit_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            assert row["model"] == "claude-sonnet-4-6", "All actual calls must use claude-sonnet-4-6"

    # 4. Prompt Audits
    idx_csv = out_dir / "rendered_prompt_index.csv"
    assert idx_csv.exists()
    mod_dir = out_dir / "rendered_prompts" / "moderator"
    part_dir = out_dir / "rendered_prompts" / "participants"
    eng_dir = out_dir / "rendered_prompts" / "engagement_assessments"
    assert mod_dir.exists() and len(list(mod_dir.glob("*"))) > 0
    assert part_dir.exists() and len(list(part_dir.glob("*"))) > 0
    assert eng_dir.exists() and len(list(eng_dir.glob("*"))) > 0

    with open(idx_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            assert row["call_type"] != "UNKNOWN"
            assert row["call_type"] in ["moderator_opening", "moderator_turn", "participant_response", "engagement_assessment"]

    # 5. Strict Disk-Based Report Validation
    report_file = out_dir / "MACHO_MEALS_EMERGENT_RUN_REPORT.md"
    assert report_file.exists()
    report = report_file.read_text(encoding="utf-8")
    
    verdicts = [
        "LIVE_RUN_COMPLETED_CLEAN",
        "LIVE_RUN_COMPLETED_WITH_CAVEATS",
        "LIVE_RUN_INCOMPLETE_GUIDE_NOT_CLOSED",
        "LIVE_RUN_FAILED_TRANSCRIPT_MISMATCH",
        "MODEL_MISMATCH",
        "LIVE_RUN_FAILED",
        "BLOCKED"
    ]
    assert any(v in report for v in verdicts)
    
    # Calculate disk truth
    max_json_turn = max((e.get("turn", 0) for e in j_data), default=-1)

    txt_lines = t_txt.read_text(encoding="utf-8").splitlines()
    max_txt_turn = -1
    for line in txt_lines:
        m = re.search(r'^Turn\s+(\d+)\s*\|', line)
        if m: max_txt_turn = max(max_txt_turn, int(m.group(1)))

    if "LIVE_RUN_COMPLETED_CLEAN" in report:
        assert max_json_turn > 12, "Final report claims CLEAN COMPLETED but max_json_turn is <= 12"
        assert max_txt_turn > 12, "Final report claims CLEAN COMPLETED but max_txt_turn is <= 12"
        assert max_json_turn == max_txt_turn, "Final report claims CLEAN COMPLETED but transcript.json and transcript.txt disagree on max turn"
        
        # Verify state claims
        assert "whether the closing section was completed: yes" in report.lower(), "Report claims CLEAN but closing section not completed in state"

    if max_json_turn <= 12:
        assert "LIVE_RUN_COMPLETED_CLEAN" not in report, "Final report cannot say CLEAN if transcript ends at turn 12"
        
    if max_json_turn != max_txt_turn:
        assert "LIVE_RUN_FAILED_TRANSCRIPT_MISMATCH" in report, "Report MUST be LIVE_RUN_FAILED_TRANSCRIPT_MISMATCH if turn counts disagree"
        
    m = re.search(r'max turn number in transcript\.json:\s*(\d+)', report)
    if m:
        reported_turn = int(m.group(1))
        assert reported_turn == max_json_turn, f"Reported turn {reported_turn} does not match disk transcript.json {max_json_turn}"
