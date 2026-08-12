import pytest
import tempfile
import os
import json
from scripts.assess_session import assess_session

def test_assess_session_cli_wiring():
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "transcript.json"), "w") as f:
            json.dump([
                {"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator", "content": "Daniel, hi."},
                {"turn": 2, "speaker_id": "P1", "speaker_name": "Daniel", "content": "Hi"}
            ], f)
        with open(os.path.join(tmpdir, "moderator_log.json"), "w") as f:
            json.dump([], f)
        with open(os.path.join(tmpdir, "run_metadata.json"), "w") as f:
            json.dump({}, f)
        with open(os.path.join(tmpdir, "session_state_final.json"), "w") as f:
            json.dump({}, f)
            
        res = assess_session(tmpdir)
        assert len(res.interaction_edges) > 0
        assert res.manifest["session_dir"] == tmpdir
        assert "transcript.json" in res.manifest["file_hashes"]
