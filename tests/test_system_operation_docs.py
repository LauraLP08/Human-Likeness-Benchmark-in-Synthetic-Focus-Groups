import os
import pytest
from pathlib import Path

DOCS_DIR = Path("docs/system_operation")
TEST_TERMS = [
    "run_conversation_step",
    "assess_engagement",
    "call_moderator",
    "call_participant",
    "render_turn_message",
    "SessionState",
    "TriggerEvent",
    "ModeratorAPIResponse",
    "ParticipantEngagementAssessment",
    "transcript.json",
    "transcript.txt",
    "moderator_log.json",
    "api_calls.jsonl",
    "state_turn_*.json",
    "output/session_logs",
    "rendered_prompt_index.csv",
    "model_usage_audit.csv",
    "claude-sonnet-4-6",
    "deterministic",
    "model-decided",
    "mixed",
    "verbosity",
    "source of truth",
]

NEGATIVE_TERMS = [
    "human-likeness validation",
    "thematic equivalence",
    "outcome validity",
]

def test_docs_exist():
    expected_files = [
        "OPERATIONAL_FLOWCHART.md",
        "SESSION_RUN_SEQUENCE.md",
        "PROMPT_RENDERING_AND_VISIBILITY.md",
        "EMERGENT_MODE_MECHANICS.md",
        "OUTPUT_AND_AUDIT_GUIDE.md",
        "VERBOSITY_CONTROL_MAP.md",
        "OPERATIONAL_TRUTH_TABLE.md",
        "CODE_ARCHITECTURE_CONSISTENCY_AUDIT.md"
    ]
    for filename in expected_files:
        assert (DOCS_DIR / filename).exists(), f"Missing required document: {filename}"

def test_diagrams_exist():
    diagrams_dir = DOCS_DIR / "diagrams"
    assert diagrams_dir.exists()
    assert len(list(diagrams_dir.glob("*.mmd"))) >= 7

def test_docs_content_requirements():
    # Read all docs into one big string
    all_content = ""
    for md_file in DOCS_DIR.glob("*.md"):
        all_content += md_file.read_text(encoding="utf-8").lower()

    # Check for required terms
    for term in TEST_TERMS:
        search_term = term.lower()
        assert search_term in all_content, f"Required term '{term}' not found in operational documentation."

    # Check for forbidden claims
    for n_term in NEGATIVE_TERMS:
        assert n_term.lower() not in all_content, f"Forbidden claim '{n_term}' found in operational documentation."
