import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Fix path to import scripts
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_live_pilot import main
from core.orchestrator import _OUTPUT_ROOT


@pytest.fixture
def mock_anthropic(monkeypatch):
    """Ensure absolutely no Anthropic API calls can be made during testing."""
    def fail_if_called(*args, **kwargs):
        pytest.fail("Anthropic API was called during a dry-run test!")

    monkeypatch.setattr("anthropic.Anthropic.messages", fail_if_called, raising=False)
    monkeypatch.setattr("anthropic.resources.messages.Messages.create", fail_if_called, raising=False)
    
@pytest.fixture
def safe_run_id():
    return "test_harness_run_001"

@pytest.fixture
def cleanup_output(safe_run_id):
    output_dir = _OUTPUT_ROOT / safe_run_id
    yield output_dir
    # Cleanup after test
    import shutil
    if output_dir.exists():
        shutil.rmtree(output_dir)


def test_dry_run_generates_metadata(mock_anthropic, cleanup_output, safe_run_id):
    """Test that dry run loads config, initializes state, writes metadata, and makes NO API calls."""
    test_args = ["run_live_pilot.py", "--config", "configs/smoke_test_grocery.json", "--run-id", safe_run_id, "--dry-run"]
    
    with patch.object(sys, 'argv', test_args):
        try:
            main()
        except SystemExit as e:
            if e.code != 0:
                pytest.fail(f"Script exited with error code {e.code}")

    # Check that metadata was produced
    assert cleanup_output.exists()
    
    metadata_path = cleanup_output / "run_metadata.json"
    assert metadata_path.exists()
    
    metadata = json.loads(metadata_path.read_text())
    assert metadata["dry_run"] is True
    assert metadata["stage"] == "Stage 2 live pilot harness"
    assert metadata["run_id"] == safe_run_id
    assert "original_session_id" in metadata
    
    # Check artifact_status
    assert "artifact_status" in metadata
    status = metadata["artifact_status"]
    assert status["config_used"]["exists"] is True
    assert status["session_state_final"]["exists"] is True
    assert status["transcript_json"]["exists"] is False
    assert status["transcript_txt"]["exists"] is False
    assert status["moderator_log"]["exists"] is False
    assert status["api_calls"]["exists"] is False
    
    config_used_path = cleanup_output / "config_used.json"
    assert config_used_path.exists()


def test_invalid_config_path_fails(mock_anthropic):
    test_args = ["run_live_pilot.py", "--config", "configs/does_not_exist.json", "--dry-run"]
    with patch.object(sys, 'argv', test_args):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1


def test_invalid_max_steps_fails(mock_anthropic):
    test_args = ["run_live_pilot.py", "--config", "configs/smoke_test_grocery.json", "--max-steps", "0", "--dry-run"]
    with patch.object(sys, 'argv', test_args):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1


def test_unsafe_run_id_fails(mock_anthropic):
    test_args = ["run_live_pilot.py", "--config", "configs/smoke_test_grocery.json", "--run-id", "../unsafe_id", "--dry-run"]
    with patch.object(sys, 'argv', test_args):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1


def test_existing_output_directory_rejected(mock_anthropic, cleanup_output, safe_run_id):
    """Test that a run ID matching an existing directory is rejected to prevent overwrites."""
    cleanup_output.mkdir(parents=True, exist_ok=True)
    
    test_args = ["run_live_pilot.py", "--config", "configs/smoke_test_grocery.json", "--run-id", safe_run_id, "--dry-run"]
    with patch.object(sys, 'argv', test_args):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1


def test_live_mode_without_confirm_fails(mock_anthropic):
    """Test that running without --confirm-live or --dry-run fails immediately to protect API cost."""
    test_args = ["run_live_pilot.py", "--config", "configs/smoke_test_grocery.json"]
    with patch.object(sys, 'argv', test_args):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1


def test_metadata_handles_action_none_and_counts_modes(mock_anthropic, cleanup_output, safe_run_id):
    """Test that metadata generation doesn't crash on action=None and correctly counts intervention modes."""
    
    # We will mock FocusGroupOrchestrator to return a mocked state
    test_args = ["run_live_pilot.py", "--config", "configs/smoke_test_grocery.json", "--run-id", safe_run_id, "--dry-run"]
    
    class DummyAction:
        def __init__(self, val):
            self.value = val
            
    class DummyEntry:
        def __init__(self, mode, action_val, fallback):
            self.intervention_mode = mode
            self.action = DummyAction(action_val) if action_val else None
            self.validation_fallback = fallback

    mock_state = MagicMock()
    mock_state.moderator_log = [
        DummyEntry("observe", None, True),
        DummyEntry("speak", "redirect", False),
        DummyEntry("yield", None, False)
    ]
    mock_state.transcript = []
    mock_state.model_dump_json.return_value = "{}"
    
    with patch('scripts.run_live_pilot.FocusGroupOrchestrator') as MockOrch, patch.object(sys, 'argv', test_args):
        def mock_init(*args, **kwargs):
            cleanup_output.mkdir(parents=True, exist_ok=True)
            instance = MagicMock()
            instance.state = mock_state
            instance.log_dir = cleanup_output
            return instance
            
        MockOrch.side_effect = mock_init
    
        try:
            main()
        except SystemExit as e:
            if e.code != 0:
                pytest.fail(f"Script exited with error code {e.code}")
                
        metadata_path = cleanup_output / "run_metadata.json"
        metadata = json.loads(metadata_path.read_text())
        
        # Verify counts
        assert metadata["intervention_mode_counts"] == {"observe": 1, "speak": 1, "yield": 1}
        assert metadata["moderator_action_counts"] == {"none": 2, "redirect": 1}
        assert metadata["validation_fallback_count"] == 1
