"""
Tests for the corrected DS05 mindfulness thematic package.

Each test class corresponds to one required correction. These are guards against
regression to the earlier, wrong framing — several of them assert the ABSENCE of
a claim, which is the point.

    py -m pytest tests/test_mindfulness_thematic_corrections.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_CF = _ROOT / "analysis/transportability_mindfulness/coding_frame"
_REPORT = _ROOT / "analysis/transportability_mindfulness/TRANSPORTABILITY_MINDFULNESS_REPORT.md"


@pytest.fixture(scope="module")
def pkg() -> dict:
    path = _CF / "thematic_package_corrected.json"
    assert path.exists(), "run scripts/mindfulness_corrections.py first"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def frozen() -> dict:
    return json.loads((_CF / "frozen_frame.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report() -> str:
    return _REPORT.read_text(encoding="utf-8")


# --- 1. the 23 / 21 / 2 / 3 distinction -------------------------------------

class TestFrameStrata:
    def test_four_strata_have_the_required_sizes(self, pkg):
        s = pkg["frame_strata"]
        assert s["codes_total"] == 26
        assert s["stratum_1_any_valid_quote_in_some_repetition"]["n"] == 23
        assert s["stratum_2_stable_in_both_repetitions"]["n"] == 21
        assert s["stratum_3_unstable_between_repetitions"]["n"] == 2
        assert s["stratum_4_excluded_no_participant_speech"]["n"] == 3

    def test_strata_2_3_4_are_disjoint_and_exhaust_the_frame(self, pkg):
        s = pkg["frame_strata"]
        stable = set(s["stratum_2_stable_in_both_repetitions"]["codes"])
        unstable = set(s["stratum_3_unstable_between_repetitions"]["codes"])
        excluded = set(s["stratum_4_excluded_no_participant_speech"]["codes"])
        assert not (stable & unstable) and not (stable & excluded) and not (unstable & excluded)
        assert len(stable | unstable | excluded) == 26

    def test_stratum_1_is_the_union_of_stable_and_unstable(self, pkg):
        s = pkg["frame_strata"]
        assert set(s["stratum_1_any_valid_quote_in_some_repetition"]["codes"]) == (
            set(s["stratum_2_stable_in_both_repetitions"]["codes"])
            | set(s["stratum_3_unstable_between_repetitions"]["codes"])
        )

    def test_stratum_1_is_marked_as_not_a_denominator(self, pkg):
        note = pkg["frame_strata"]["stratum_1_any_valid_quote_in_some_repetition"]["note"]
        assert "NOT a denominator" in note

    def test_strata_agree_with_the_frozen_frame(self, pkg, frozen):
        stable = {c for c, r in frozen["verified_codes"].items() if r["agreement"] == "both"}
        unstable = {c for c, r in frozen["verified_codes"].items() if r["agreement"] == "one"}
        s = pkg["frame_strata"]
        assert set(s["stratum_2_stable_in_both_repetitions"]["codes"]) == stable
        assert set(s["stratum_3_unstable_between_repetitions"]["codes"]) == unstable
        assert set(s["stratum_4_excluded_no_participant_speech"]["codes"]) == set(
            frozen["unverified_summary_claims"]
        )


# --- 2. the denominator is 21, never 23 -------------------------------------

class TestDenominator:
    def test_coverage_denominator_is_21(self, pkg):
        assert pkg["coverage"]["denominator"] == 21
        assert pkg["AI_AUDITED_ASSIGNMENT_SENSITIVITY_ENVELOPE"]["denominator"] == 21

    def test_denominator_is_the_stable_stratum(self, pkg):
        assert "stratum 2" in pkg["coverage"]["denominator_stratum"]

    def test_bounds_are_computed_against_21(self, pkg):
        env = pkg["AI_AUDITED_ASSIGNMENT_SENSITIVITY_ENVELOPE"]
        assert env["lower_bound"]["value"] == pytest.approx(len(env["lower_bound"]["codes"]) / 21, abs=1e-4)
        assert env["upper_bound"]["value"] == pytest.approx(len(env["upper_bound"]["codes"]) / 21, abs=1e-4)

    def test_report_never_pairs_23_with_a_coverage_fraction(self, report):
        assert "1/21" in report or "1 code" in report
        assert "1/23" not in report
        assert "/23" not in report.replace("of 23", "")


# --- 3. the envelope is renamed and correctly framed ------------------------

class TestSensitivityEnvelope:
    def test_it_is_named_an_envelope(self, pkg):
        assert "AI_AUDITED_ASSIGNMENT_SENSITIVITY_ENVELOPE" in pkg

    def test_it_disclaims_the_forbidden_readings(self, pkg):
        is_not = " ".join(pkg["AI_AUDITED_ASSIGNMENT_SENSITIVITY_ENVELOPE"]["is_not"]).lower()
        for forbidden in ("confidence interval", "reliability band", "true recall"):
            assert forbidden in is_not

    def test_upper_bound_derivation_names_both_components(self, pkg):
        upper = pkg["AI_AUDITED_ASSIGNMENT_SENSITIVITY_ENVELOPE"]["upper_bound"]
        assert len(upper["components"]["cross_model_semantic_disagreements"]) == 7
        assert len(upper["components"]["unstable_synthetic_code"]) == 1
        assert "without any human" in upper["derivation"]

    def test_report_never_asserts_the_forbidden_readings(self, report):
        """
        The forbidden phrases may appear ONLY inside an explicit denial. Asserting
        their bare absence would be wrong: the report has to name what the
        envelope is not in order to rule it out.
        """
        lowered = report.lower()
        for phrase in ("confidence interval", "reliability band", "recall band"):
            idx = 0
            while True:
                idx = lowered.find(phrase, idx)
                if idx == -1:
                    break
                window = lowered[max(0, idx - 60): idx + len(phrase)]
                assert f"not a {phrase}" in window, (
                    f"{phrase!r} at offset {idx} is not inside a denial: ...{window}..."
                )
                idx += len(phrase)

    def test_the_denial_is_actually_present(self, report):
        lowered = report.lower()
        assert "not a confidence interval" in lowered
        assert "not a reliability band" in lowered


# --- 4. literal quotes are not semantic validation --------------------------

class TestCrossModelDisagreements:
    def test_seven_disagreements_are_recorded_as_semantic_disagreements(self, pkg):
        d = pkg["cross_model_semantic_disagreements"]
        assert len(d) == 7
        assert all(v["status"] == "CROSS_MODEL_SEMANTIC_DISAGREEMENT" for v in d.values())

    def test_none_is_counted_as_present(self, pkg):
        assert all(v["counted_as_present"] is False
                   for v in pkg["cross_model_semantic_disagreements"].values())

    def test_all_await_human_adjudication(self, pkg):
        assert all(v["resolution"] == "AWAITING_HUMAN_ADJUDICATION"
                   for v in pkg["cross_model_semantic_disagreements"].values())

    def test_gates_do_not_claim_to_verify_definition_correspondence(self, pkg):
        gate = pkg["gate_scope"]
        joined = " ".join(gate["what_the_gates_DO_NOT_verify"]).lower()
        assert "operational definition" in joined
        assert all("definition" not in g.lower() for g in gate["what_the_gates_verify"])

    def test_each_disagreement_records_the_gate_it_did_not_pass(self, pkg):
        for v in pkg["cross_model_semantic_disagreements"].values():
            assert "correspondence_with_the_operational_definition" in v["gates_NOT_passed"]

    def test_claude_is_auditor_not_primary(self, pkg):
        assert "gemini" in pkg["primary_evaluator"].lower()
        assert "auditor only" in pkg["cross_model_auditor"].lower()
        assert "not a correction" in pkg["cross_model_auditor"].lower()


# --- 5. reach computed from anonymous labels --------------------------------

class TestReachAndSalience:
    def test_reach_is_computable(self, pkg):
        r = pkg["participant_reach_and_salience"]
        assert r["status"] == "COMPUTABLE_FROM_STABLE_ANONYMOUS_LABELS"
        assert "NOT_RECOVERABLE" in r["supersedes"]

    def test_human_denominator_excludes_the_unattributed_speaker(self, pkg):
        human = pkg["participant_reach_and_salience"]["human"]
        assert human["participant_denominator"] == 5
        assert "Unknown Speaker" in human["denominator_note"]

    def test_every_stable_code_is_scored(self, pkg):
        human = pkg["participant_reach_and_salience"]["human"]
        assert human["codes_scored"] == 21
        assert len(human["per_code"]) == 21

    def test_reach_equals_distinct_speakers_over_denominator(self, pkg):
        for row in pkg["participant_reach_and_salience"]["human"]["per_code"].values():
            assert row["reach"] == pytest.approx(
                row["distinct_speakers"] / row["participant_denominator"], abs=1e-4
            )
            assert 1 <= row["distinct_speakers"] <= 5
            assert len(row["speaker_labels"]) == row["distinct_speakers"]

    def test_salience_rank_is_monotone_in_reach(self, pkg):
        rows = list(pkg["participant_reach_and_salience"]["human"]["per_code"].values())
        for a in rows:
            for b in rows:
                if a["reach"] > b["reach"]:
                    assert a["salience_rank"] < b["salience_rank"]
                if a["reach"] == b["reach"]:
                    assert a["salience_rank"] == b["salience_rank"]

    def test_no_real_identity_is_asserted(self, pkg):
        blob = json.dumps(pkg["participant_reach_and_salience"], ensure_ascii=False)
        for label in ("MF_P1", "MF_P2", "MF_P3", "MF_P4", "MF_P5"):
            assert label not in blob

    def test_synthetic_comparison_is_flagged_exploratory(self, pkg):
        r = pkg["participant_reach_and_salience"]
        assert r["comparison_status"] == "EXPLORATORY_ONLY"
        assert "no test is run" in r["comparison_caveat"].lower()


# --- 6. precision, F1 and novelty are not identifiable ----------------------

class TestClosedFrameLimits:
    def test_the_three_declarations_are_present(self, pkg):
        limits = pkg["closed_frame_limits"]
        for key in ("PRECISION_NOT_IDENTIFIABLE_UNDER_CLOSED_FRAME",
                    "F1_NOT_IDENTIFIABLE",
                    "SYNTHETIC_NOVELTY_NOT_ASSESSED"):
            assert key in limits and limits[key].strip()

    def test_no_precision_or_f1_value_is_published(self, pkg):
        blob = json.dumps(pkg, ensure_ascii=False)
        assert '"strict_precision": 1.0' not in blob
        assert '"f1":' not in blob

    def test_report_declares_all_three(self, report):
        for key in ("PRECISION_NOT_IDENTIFIABLE_UNDER_CLOSED_FRAME",
                    "F1_NOT_IDENTIFIABLE",
                    "SYNTHETIC_NOVELTY_NOT_ASSESSED"):
            assert key in report

    def test_report_no_longer_claims_zero_synthetic_only_themes(self, report):
        lowered = report.lower()
        assert "synthetic codes with no human counterpart | none" not in lowered
        assert "no human counterpart: []" not in lowered


# --- 7. the obsolete rewrite claim is gone ----------------------------------

class TestRewriteClaimRemoved:
    def test_report_does_not_assert_the_transcript_was_rewritten(self, report):
        lowered = report.lower()
        for claim in (
            "the human baseline is partially ai-rewritten",
            "part of this transcript was passed through a language model",
            "extent of the rewrite is not recoverable",
        ):
            assert claim not in lowered

    def test_report_does_not_claim_lexical_measurement_is_foreclosed(self, report):
        lowered = report.lower()
        for claim in (
            "lexical and stylometric comparison is foreclosed",
            "are not interpretable as properties of unedited human speech",
        ):
            assert claim not in lowered

    def test_any_mention_of_rewriting_is_inside_a_withdrawal(self, report):
        lowered = report.lower()
        idx = 0
        while True:
            idx = lowered.find("rewritten", idx)
            if idx == -1:
                break
            window = lowered[max(0, idx - 400): idx + 400]
            assert "withdrawn" in window, f"unretracted 'rewritten' near offset {idx}"
            idx += 1

    def test_baseline_metadata_records_the_researcher_confirmation(self):
        meta = json.loads(
            (_ROOT / "data/datasets_transcripts/standardized/mindfulness/fg1/baseline_metadata.json")
            .read_text(encoding="utf-8")
        )
        flags = meta["SOURCE_INTEGRITY_FLAGS"]
        assert "preserves the original speech" in flags["researcher_confirmation"]
        assert "ai_editing_artefact_detected" not in flags

    def test_lexical_results_exist_and_are_reported(self):
        lex = json.loads(
            (_ROOT / "analysis/transportability_mindfulness/lexical_transportability.json")
            .read_text(encoding="utf-8")
        )
        assert lex["preflight"]["verdict"] == "PROCEED"
        assert lex["results"] is not None


# --- integrity: raw outputs untouched ---------------------------------------

class TestRawOutputsUnmodified:
    def test_corrections_declare_no_api_calls_and_no_new_human_tasks(self, pkg):
        assert pkg["no_api_calls"] is True
        assert pkg["no_new_human_tasks"] is True
        assert pkg["raw_outputs_unmodified"] is True

    def test_raw_gemini_and_claude_artefacts_still_present(self):
        for name in ("frozen_frame.json", "thematic_results.json", "thematic_qc_audit.json"):
            assert (_CF / name).exists()

    def test_privacy_finding_identifies_two_files_without_modifying_them(self, pkg):
        p = pkg["privacy"]
        assert p["record_type"] == "PRIVACY_FINDING_IDENTIFIED_NOT_MODIFIED"
        assert p["n_files_affected"] == 2
        files = {f["file"] for f in p["findings"]}
        assert files == {"agents/mindfulness/mf_p2.json", "agents/mindfulness/mf_p3.json"}
        assert all(f["field"] == "opening_intro.text" for f in p["findings"])
        assert "NONE" in p["action_taken"]
