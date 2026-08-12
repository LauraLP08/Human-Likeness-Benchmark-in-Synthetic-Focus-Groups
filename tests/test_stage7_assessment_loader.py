import pytest
import os
import json
import tempfile

from assessment.loader import load_session_artifacts
from assessment.metrics import compute_mechanical_integrity
from assessment.schema import SessionArtifacts

def test_loader_missing_required_files():
    # Transcript is missing, so it should be in missing_required_files
    artifacts = load_session_artifacts("nonexistent_dir")
    assert "transcript.json" in artifacts.missing_required_files
    assert "moderator_log.json" in artifacts.missing_required_files
    assert "run_metadata.json" in artifacts.missing_required_files
    assert "session_state_final.json" in artifacts.missing_required_files
    assert "api_calls.jsonl" in artifacts.missing_optional_files
    assert "config_used.json" in artifacts.missing_optional_files

def test_loader_missing_optional_files_no_critical_flag():
    artifacts = SessionArtifacts(
        session_dir="test",
        run_id="test",
        transcript=[{"turn": 1, "speaker_id": "P1", "content": "hi"}],
        missing_optional_files=["config_used.json", "api_calls.jsonl"]
    )
    track = compute_mechanical_integrity(artifacts)
    assert not any(f.severity == "critical" for f in track.flags)
    assert any(f.flag_id == "MISSING_OPTIONAL_FILES" and f.severity == "info" for f in track.flags)

def test_loader_malformed_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "transcript.json"), "w") as f:
            f.write("{malformed")
            
        artifacts = load_session_artifacts(tmpdir)
        assert any("Malformed" in e for e in artifacts.load_errors)
        assert not artifacts.transcript

def test_loader_valid():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "transcript.json"), "w") as f:
            json.dump([{"turn": 1, "speaker_id": "P1", "content": "hello"}], f)
            
        artifacts = load_session_artifacts(tmpdir)
        assert not artifacts.load_errors
        assert "transcript.json" not in artifacts.missing_files
        assert len(artifacts.transcript) == 1
