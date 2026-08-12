"""Test configuration for the published repository.

Two human focus-group corpora were standardised during this project: the Macho
Meals corpus, which is the benchmark reported in the dissertation, and the earlier
QESB / PHIND corpora, which were used only to build and calibrate the Stage-7
assessment scaffolding. The QESB / PHIND transcripts are third-party data and are
**not redistributed here**, so `data/human_baseline/standardized_claude_v1/` is
absent from this repository.

A small number of tests assert directly against that directory. They are skipped
when it is missing rather than deleted, so the assertions stay visible and re-run
unchanged for anyone who obtains the corpora from their original sources. Nothing
that exercises the reported Macho Meals benchmark is skipped by this file.
"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_HUMAN_BASELINE = _ROOT / "data" / "human_baseline" / "standardized_claude_v1"

_REASON = (
    "requires data/human_baseline/standardized_claude_v1/ (QESB / PHIND corpora, "
    "third-party data not redistributed with this repository)"
)

# Whole modules whose every live assertion targets the QESB / PHIND corpus.
_MODULES_REQUIRING_HUMAN_BASELINE = {
    "test_human_baseline_artifact_manifest.py",
    "test_human_baseline_source_and_assessment_closure.py",
}

# Individual tests inside modules that otherwise run fine without the corpus.
_TESTS_REQUIRING_HUMAN_BASELINE = {
    "test_stage7c5_human_baseline_calibration_gate.py": {
        "test_missing_transcript_baseline_blocks",
        "test_missing_assessment_baseline_blocks",
        "test_different_ids_same_count_blocks",
        "test_turn_count_mismatch_blocks",
        "test_sys_exit_on_blocked",
    },
}


def pytest_collection_modifyitems(config, items):
    if _HUMAN_BASELINE.is_dir():
        return
    skip = pytest.mark.skip(reason=_REASON)
    for item in items:
        module = Path(str(item.fspath)).name
        if module in _MODULES_REQUIRING_HUMAN_BASELINE:
            item.add_marker(skip)
        elif item.name in _TESTS_REQUIRING_HUMAN_BASELINE.get(module, ()):
            item.add_marker(skip)
