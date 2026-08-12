"""
Phase 3C: comparable windows for a user's corpus, and analytical-input identity.

No Streamlit, no network.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from platform_core import analysis_window as AW
from platform_core import design as D
from platform_core import thematic as TH
from platform_core.config import resolve_data_dir
from platform_core.services import (audit, design_service as DS,
                                    import_service as I, structural_service as S,
                                    window_service as W)

LONG = ("When I get home after work the last thing I want is a project, so I keep a "
        "rotation of about five meals I can do with my eyes closed.")
PREAMBLE = "Before we begin, please confirm you are happy to be recorded."
CLOSING = "That is all from me, thank you for your time this evening."


def _synthetic(rounds=3, seed=0):
    entries = [{"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator",
                "content": PREAMBLE, "timestamp": "2026-01-01T00:00:00Z",
                "selection_mode": "scripted"},
               {"turn": 2, "speaker_id": "MODERATOR", "speaker_name": "Moderator",
                "content": "Right, tell me about weeknight cooking.",
                "timestamp": "2026-01-01T00:01:00Z", "selection_mode": "scripted"}]
    turn = 3
    for r in range(rounds):
        for p in range(4):
            entries.append({
                "turn": turn, "speaker_id": f"P{p + 1}",
                "speaker_name": f"Person{p + 1}",
                "content": f"{LONG} ({r},{p},{seed})",
                "timestamp": f"2026-01-01T00:{turn:02d}:00Z",
                "selection_mode": "model"})
            turn += 1
    entries.append({"turn": turn, "speaker_id": "MODERATOR",
                    "speaker_name": "Moderator", "content": CLOSING,
                    "timestamp": f"2026-01-01T00:{turn:02d}:00Z",
                    "selection_mode": "scripted"})
    return entries


def _human(rounds=3, seed=0):
    entries = [{"turn": 1, "speaker_id": "MOD", "canonical_speaker_id": "MOD",
                "speaker_name": "Moderator", "speaker_role": "moderator",
                "content": PREAMBLE},
               {"turn": 2, "speaker_id": "MOD", "canonical_speaker_id": "MOD",
                "speaker_name": "Moderator", "speaker_role": "moderator",
                "content": "Right, tell me about weeknight cooking."}]
    turn = 3
    for r in range(rounds):
        for p in range(4):
            entries.append({
                "turn": turn, "speaker_id": f"P{p + 1}",
                "canonical_speaker_id": f"P{p + 1}",
                "speaker_name": f"Person{p + 1}", "speaker_role": "participant",
                "content": f"I agree with that, mostly. ({r},{p},{seed})"})
            turn += 1
    entries.append({"turn": turn, "speaker_id": "MOD",
                    "canonical_speaker_id": "MOD", "speaker_name": "Moderator",
                    "speaker_role": "moderator", "content": CLOSING})
    return entries


ROSTER = ["Person1", "Person2", "Person3", "Person4"]


@pytest.fixture()
def data_dir(tmp_path):
    return resolve_data_dir(injected=tmp_path / "platform-data", ensure=True)


@pytest.fixture()
def project(data_dir):
    return I.new_project("Trial", data_dir)


def _import(project, name, entries, transcript_type, **kwargs):
    if transcript_type == "human":
        kwargs.setdefault("roster_names", ROSTER)
    else:
        kwargs.setdefault("window_declaration", "comparable_window")
    return I.import_transcript(
        project, filename=f"{name}.json",
        content=json.dumps(entries).encode("utf-8"),
        transcript_type=transcript_type, **kwargs)


def _lock_whole(project, transcript_id, label="R. Lara"):
    window = W.confirm_whole_transcript(project, transcript_id,
                                        researcher_label=label,
                                        researcher_note="already trimmed at source")
    return W.lock_window(project, window.window_id)


def _design(project, *, n_fg=2, replicates=2, condition="cond-a"):
    design = D.simple_design(
        design_id="default", project_id=project.project_id, study_name="Trial",
        n_focus_groups=n_fg, synthetic_conditions=[condition],
        replicates=replicates, with_human=True, created_utc="2026-08-04")
    DS.save_design(project, design)
    return design


# ================================================== A1 transcript type vs role
def test_a_human_transcript_cannot_hold_a_synthetic_role(project):
    """(1)"""
    _design(project)
    _import(project, "hum_a", _human(), "human")
    with pytest.raises(DS.DesignServiceError, match="imported as a HUMAN"):
        DS.assign(project, transcript_id="hum_a", condition_id="cond-a",
                  focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
                  replicate_index=1)


def test_a_synthetic_transcript_cannot_hold_a_human_role(project):
    """(2)"""
    _design(project)
    _import(project, "syn_a", _synthetic(), "synthetic")
    with pytest.raises(DS.DesignServiceError, match="imported as a SYNTHETIC"):
        DS.assign(project, transcript_id="syn_a", condition_id="human",
                  focus_group_id="fg1", role=D.Role.HUMAN_REFERENCE.value)


def test_a_human_reference_may_not_carry_a_replicate_index(project):
    _design(project)
    _import(project, "hum_a", _human(), "human")
    with pytest.raises(DS.DesignServiceError, match="no replicate index"):
        DS.assign(project, transcript_id="hum_a", condition_id="human",
                  focus_group_id="fg1", role=D.Role.HUMAN_REFERENCE.value,
                  replicate_index=1)


def test_a_synthetic_run_must_carry_a_replicate_index(project):
    _design(project)
    _import(project, "syn_a", _synthetic(), "synthetic")
    with pytest.raises(DS.DesignServiceError, match="needs a replicate index"):
        DS.assign(project, transcript_id="syn_a", condition_id="cond-a",
                  focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value)


def test_the_manifest_applies_the_same_rules(project):
    _design(project)
    _import(project, "hum_a", _human(), "human")
    _import(project, "syn_a", _synthetic(), "synthetic")
    manifest = ("transcript_id,condition_id,focus_group_id,replicate_index,role\n"
                "hum_a,cond-a,fg1,1,SYNTHETIC_RUN\n"
                "syn_a,human,fg1,,HUMAN_REFERENCE\n")
    assigned, problems = DS.import_manifest(project, manifest)
    assert assigned == []
    assert len(problems) == 2
    assert "imported as a HUMAN" in problems[0]
    assert "imported as a SYNTHETIC" in problems[1]


def test_a_role_in_the_wrong_side_of_the_design_is_refused(project):
    design = D.StudyDesign(
        design_id="default", project_id=project.project_id, study_name="T",
        conditions=[D.Condition("odd", "Odd", D.Side.HUMAN.value, 1)],
        focus_groups=[D.FocusGroup("fg1")])
    DS.save_design(project, design)
    _import(project, "hum_a", _human(), "human")
    DS.assign(project, transcript_id="hum_a", condition_id="odd",
              focus_group_id="fg1", role=D.Role.HUMAN_REFERENCE.value)
    assert len(DS.load_assignments(project)) == 1


# ============================================ A2 assignments whose file vanished
def test_an_assignment_whose_canonical_vanished_is_not_coverage(project):
    """(3)"""
    _design(project, n_fg=1, replicates=1)
    _import(project, "syn_a", _synthetic(), "synthetic")
    _lock_whole(project, "syn_a")
    DS.assign(project, transcript_id="syn_a", condition_id="cond-a",
              focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
              replicate_index=1)
    DS.compute_for_assignment(project, "syn_a")
    assert DS.coverage(project).cell("cond-a", "fg1").present == 1

    (project.path / "derived" / "canonical" / "syn_a.json").unlink()

    report = DS.coverage(project)
    assert report.missing_assigned_transcript_ids == ["syn_a"]
    assert report.stale_transcript_ids == []
    assert report.fresh_transcript_ids == []
    cell = report.cell("cond-a", "fg1")
    assert cell.present == 0 and cell.missing_replicates == [1]
    assert cell.missing_transcript_ids == ["syn_a"]
    assert not cell.complete
    assert report.status == D.DesignStatus.INVALID.value

    readiness = DS.readiness(project)
    assert not readiness["route_a"] and not readiness["route_b"]
    assert "no longer stored" in " ".join(readiness["reasons"])


def test_missing_stale_and_fresh_are_three_different_things(project):
    _design(project, n_fg=3, replicates=1)
    for fg, name in enumerate(("syn_a", "syn_b", "syn_c"), start=1):
        _import(project, name, _synthetic(seed=fg), "synthetic")
        _lock_whole(project, name)
        DS.assign(project, transcript_id=name, condition_id="cond-a",
                  focus_group_id=f"fg{fg}", role=D.Role.SYNTHETIC_RUN.value,
                  replicate_index=1)
    (project.path / "derived" / "canonical" / "syn_a.json").unlink()
    _import(project, "syn_b", _synthetic(rounds=9), "synthetic",
            on_collision=I.CollisionPolicy.REPLACE_INVALIDATE_DERIVED)

    report = DS.coverage(project)
    assert report.missing_assigned_transcript_ids == ["syn_a"]
    assert report.stale_transcript_ids == ["syn_b"]
    assert report.fresh_transcript_ids == ["syn_c"]


# ======================================= A3 / B window contract, both sides
def test_a_new_human_transcript_also_needs_a_reviewed_window(project):
    """(5)"""
    _import(project, "hum_a", _human(), "human")
    state = W.window_state(project, "hum_a")
    assert state.window is None
    assert state.window_status == AW.WindowStatus.RAW_FULL_TRANSCRIPT.value
    assert not state.comparison_eligible
    assert state.namespace == AW.FULL_RUN_NAMESPACE

    locked = _lock_whole(project, "hum_a")
    assert locked.side == "human"
    after = W.window_state(project, "hum_a")
    assert after.comparison_eligible and after.namespace == AW.COMPARABLE_NAMESPACE


def test_confirming_the_whole_transcript_makes_a_reproducible_locked_window(project):
    """(6)"""
    _import(project, "syn_a", _synthetic(), "synthetic")
    window = _lock_whole(project, "syn_a")
    turns = I.load_canonical(project, "syn_a")["turns"]

    assert window.status == AW.WindowStatus.LOCKED.value
    assert window.derivation_method == \
        AW.DerivationMethod.CONFIRMED_ENTIRE_TRANSCRIPT.value
    assert window.n_retained_turns == window.n_source_turns == len(turns)
    assert window.start_boundary["turn_id"] == turns[0]["turn_id"]
    assert window.end_boundary["turn_id"] == turns[-1]["turn_id"]
    assert window.researcher_label and window.locked_utc
    assert len(window.window_artifact_sha256) == 64

    # rebuilding the same confirmation gives the same artefact hash
    again = AW.confirm_entire_transcript(
        window_id="x", source_transcript_id="syn_a",
        source_canonical_sha256=window.source_canonical_sha256, side="synthetic",
        turns=turns, researcher_label="R. Lara",
        researcher_note="already trimmed at source")
    assert again.window_artifact_sha256 == window.window_artifact_sha256


def test_a_declaration_at_import_is_not_a_window(project):
    """`window_declaration='comparable_window'` grants nothing on its own."""
    _import(project, "syn_a", _synthetic(), "synthetic",
            window_declaration="comparable_window")
    state = W.window_state(project, "syn_a")
    assert state.window is None and not state.comparison_eligible


# ================================================ C1 manual boundary selection
def test_manual_boundaries_preserve_order_speaker_and_provenance(project):
    """(7)"""
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    turns = I.load_canonical(project, "syn_a")["turns"]
    window = W.propose_manual_window(
        project, "syn_a", start_turn_id=turns[2]["turn_id"],
        end_turn_id=turns[-2]["turn_id"], researcher_label="R. Lara",
        researcher_note="drop the consent preamble and the closing")

    assert window.n_source_turns == len(turns)
    assert window.n_retained_turns == len(turns) - 3
    assert window.included_turn_ids == [t["turn_id"] for t in turns[2:-1]]

    retained = W.windowed_turns(project, window)
    source_by_id = {t["turn_id"]: t for t in turns}
    assert [t["turn_id"] for t in retained] == window.included_turn_ids
    for turn in retained:
        original = source_by_id[turn["turn_id"]]
        assert turn["canonical_speaker_id"] == original["canonical_speaker_id"]
        assert turn["speaker_role"] == original["speaker_role"]
        assert turn["original_index"] == original["original_index"]
        assert turn["provenance"] == original["provenance"]
    indices = [t["original_index"] for t in retained]
    assert indices == sorted(indices)


def test_a_start_after_the_end_is_refused(project):
    _import(project, "syn_a", _synthetic(), "synthetic")
    turns = I.load_canonical(project, "syn_a")["turns"]
    with pytest.raises(AW.WindowError, match="cannot run backwards"):
        W.propose_manual_window(project, "syn_a",
                                start_turn_id=turns[-1]["turn_id"],
                                end_turn_id=turns[0]["turn_id"])


def test_an_offset_outside_the_turn_blocks(project):
    """(8)"""
    _import(project, "syn_a", _synthetic(), "synthetic")
    turns = I.load_canonical(project, "syn_a")["turns"]
    with pytest.raises(AW.WindowError, match="outside turn"):
        W.propose_manual_window(project, "syn_a",
                                start_turn_id=turns[0]["turn_id"],
                                end_turn_id=turns[-1]["turn_id"],
                                start_char_offset=10_000)
    assert W.windows_for(project, "syn_a") == []      # no window was created


def test_an_unknown_turn_id_blocks(project):
    _import(project, "syn_a", _synthetic(), "synthetic")
    with pytest.raises(AW.WindowError, match="not in the source transcript"):
        W.propose_manual_window(project, "syn_a", start_turn_id="t9999")


# ============================================== C2 ambiguity and positional
def test_a_phrase_matching_several_turns_leaves_the_window_under_review(project):
    """(9)"""
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    window = W.propose_manual_window(
        project, "syn_a", start_text="When I get home after work",
        researcher_label="R. Lara")
    assert window.status == AW.WindowStatus.UNDER_REVIEW.value
    assert not window.unambiguous
    assert any("does not identify a single boundary" in p
               for p in window.review_problems)
    with pytest.raises(W.WindowServiceError, match="under review"):
        W.lock_window(project, window.window_id)


def test_a_phrase_matching_once_resolves_the_boundary(project):
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    window = W.propose_manual_window(
        project, "syn_a", start_text="Right, tell me about weeknight cooking.",
        end_text=CLOSING, researcher_label="R. Lara")
    assert window.unambiguous
    assert window.status == AW.WindowStatus.PROPOSED.value
    locked = W.lock_window(project, window.window_id)
    assert locked.locked


def test_a_phrase_that_appears_nowhere_is_under_review(project):
    _import(project, "syn_a", _synthetic(), "synthetic")
    window = W.propose_manual_window(project, "syn_a",
                                     start_text="this phrase is not present")
    assert window.status == AW.WindowStatus.UNDER_REVIEW.value
    assert any("no turn contains" in p for p in window.review_problems)


def test_a_positional_boundary_needs_a_researcher_and_a_note(project):
    """(10)"""
    _import(project, "syn_a", _synthetic(), "synthetic")
    turns = I.load_canonical(project, "syn_a")["turns"]
    with pytest.raises(W.WindowServiceError, match="researcher decision"):
        W.propose_manual_window(project, "syn_a",
                                start_turn_id=turns[2]["turn_id"],
                                positional_fallback_used=True)
    with pytest.raises(W.WindowServiceError, match="researcher decision"):
        W.propose_manual_window(project, "syn_a",
                                start_turn_id=turns[2]["turn_id"],
                                positional_fallback_used=True,
                                researcher_label="R. Lara")

    window = W.propose_manual_window(
        project, "syn_a", start_turn_id=turns[2]["turn_id"],
        positional_fallback_used=True, researcher_label="R. Lara",
        researcher_note="the recording starts mid-sentence; boundary set by hand")
    assert window.positional_fallback_used
    assert window.start_boundary["confidence"] == "positional"
    events = [e for e in audit.read_log(project.path)
              if e["event"] == audit.WINDOW]
    assert any(e["detail"].get("positional_fallback_used") for e in events)


# ============================================ C3 immutability and versioning
def test_a_locked_window_cannot_be_edited(project):
    """(11)"""
    _import(project, "syn_a", _synthetic(), "synthetic")
    window = _lock_whole(project, "syn_a")
    with pytest.raises(W.WindowServiceError, match="immutable"):
        W.edit_locked_window(project, window.window_id)
    with pytest.raises(W.WindowServiceError, match="already locked"):
        W.lock_window(project, window.window_id)
    with pytest.raises(W.WindowServiceError, match="supersede"):
        W.reject_window(project, window.window_id)


def test_a_new_version_supersedes_the_previous_one(project):
    """(12)"""
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    first = _lock_whole(project, "syn_a")
    turns = I.load_canonical(project, "syn_a")["turns"]

    second = W.supersede_window(
        project, first.window_id, start_turn_id=turns[2]["turn_id"],
        end_turn_id=turns[-2]["turn_id"], researcher_label="R. Lara",
        researcher_note="trim the preamble after review")
    assert second.window_id == "syn_a__window_v002"
    assert second.supersedes_window_id == first.window_id
    assert W.load_window(project, first.window_id).locked      # not yet superseded

    W.lock_window(project, second.window_id)
    previous = W.load_window(project, first.window_id)
    assert previous.status == AW.WindowStatus.SUPERSEDED.value
    assert previous.superseded_by_window_id == second.window_id
    assert W.load_window(project, first.window_id) is not None  # never deleted
    assert W.active_window(project, "syn_a").window_id == second.window_id


# ================================================ D analysis input identity
def test_two_windows_of_one_transcript_keep_separate_results(project):
    """(14)"""
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    first = _lock_whole(project, "syn_a")
    result_one = DS.compute_for_assignment(project, "syn_a")
    assert result_one.analysis_input_id == first.window_id

    turns = I.load_canonical(project, "syn_a")["turns"]
    second = W.supersede_window(project, first.window_id,
                                start_turn_id=turns[2]["turn_id"],
                                end_turn_id=turns[-2]["turn_id"],
                                researcher_label="R. Lara",
                                researcher_note="trim")
    W.lock_window(project, second.window_id)
    result_two = DS.compute_for_assignment(project, "syn_a")

    assert result_two.analysis_input_id == second.window_id
    assert sorted(S.stored_runs(project)) == [first.window_id, second.window_id]
    one = S.load_structural(project, first.window_id)
    two = S.load_structural(project, second.window_id)
    assert one["window_id"] != two["window_id"]
    values_one = {r["metric_id"]: r["value"] for r in result_one.rows}
    values_two = {r["metric_id"]: r["value"] for r in result_two.rows}
    # The trimmed window drops three MODERATOR turns, so the participant count is
    # rightly unchanged; what must differ is what the window actually removed.
    assert values_one["participant_turns"] == values_two["participant_turns"] == 12
    assert values_one["moderator_turns"] == 3
    assert values_two["moderator_turns"] == 0
    assert values_one["total_words"] > values_two["total_words"]


def test_changing_the_window_makes_the_previous_result_stale(project):
    """(13)"""
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    first = _lock_whole(project, "syn_a")
    DS.compute_for_assignment(project, "syn_a")
    assert S.restore_results(project)[first.window_id].freshness == S.FRESH

    turns = I.load_canonical(project, "syn_a")["turns"]
    second = W.supersede_window(project, first.window_id,
                                start_turn_id=turns[2]["turn_id"],
                                end_turn_id=turns[-2]["turn_id"],
                                researcher_label="R. Lara",
                                researcher_note="trim")
    W.lock_window(project, second.window_id)

    stored = S.restore_results(project)[first.window_id]
    assert stored.freshness == S.STALE
    assert "SUPERSEDED" in (stored.stale_reason or "")
    assert first.window_id not in S.comparable_run_results(project)


def test_a_full_session_result_is_descriptive_and_never_comparable(project):
    """(4)"""
    _import(project, "syn_a", _synthetic(), "synthetic")
    result = DS.compute_for_assignment(project, "syn_a")
    assert result.analysis_input_id == "syn_a__fullrun"
    assert result.namespace == AW.FULL_RUN_NAMESPACE
    assert not result.comparison_eligible

    stored = S.restore_results(project)["syn_a__fullrun"]
    assert stored.freshness == S.FRESH            # current, but not comparable
    assert not stored.aggregation_eligible
    assert stored.calculation_status == AW.CalculationStatus.DESCRIPTIVE_ONLY.value
    assert S.comparable_run_results(project) == {}


def test_the_artifact_hash_covers_speaker_and_order_not_only_content():
    """(19)"""
    turns = [{"turn_id": "t0", "original_turn_id": 1, "original_index": 0,
              "canonical_speaker_id": "P1", "original_speaker_id": "P1",
              "speaker_role": "participant", "text": "alpha"},
             {"turn_id": "t1", "original_turn_id": 2, "original_index": 1,
              "canonical_speaker_id": "P2", "original_speaker_id": "P2",
              "speaker_role": "participant", "text": "beta"}]

    def digest(rows):
        return AW.artifact_digest(
            source_canonical_sha256="c", side="synthetic",
            derivation_method="MANUAL",
            retained=[(t, t["text"]) for t in rows],
            start_boundary=None, end_boundary=None)

    base = digest(turns)
    reordered = digest(list(reversed(turns)))
    reattributed = digest([dict(turns[0], canonical_speaker_id="P9"), turns[1]])
    rerole = digest([dict(turns[0], speaker_role="moderator"), turns[1]])

    assert base != reordered, "order must change the identity"
    assert base != reattributed, "speaker must change the identity"
    assert base != rerole, "role must change the identity"
    # a content-only digest would call all four identical
    content = AW.retained_digest([(t, t["text"]) for t in turns])
    assert content == AW.retained_digest(
        [(dict(turns[0], canonical_speaker_id="P9"), "alpha"), (turns[1], "beta")])


# ================================================ E coverage and aggregation
def _ready(project, *, n_fg=2, replicates=2, lock=True):
    design = _design(project, n_fg=n_fg, replicates=replicates)
    for fg in range(1, n_fg + 1):
        name = f"hum_fg{fg}"
        _import(project, name, _human(seed=fg), "human")
        if lock:
            _lock_whole(project, name)
        DS.assign(project, transcript_id=name, condition_id="human",
                  focus_group_id=f"fg{fg}", role=D.Role.HUMAN_REFERENCE.value)
        DS.compute_for_assignment(project, name)
        for k in range(1, replicates + 1):
            run = f"syn_fg{fg}_r{k}"
            _import(project, run, _synthetic(rounds=2 + fg, seed=k), "synthetic")
            if lock:
                _lock_whole(project, run)
            DS.assign(project, transcript_id=run, condition_id="cond-a",
                      focus_group_id=f"fg{fg}", role=D.Role.SYNTHETIC_RUN.value,
                      replicate_index=k)
            DS.compute_for_assignment(project, run)
    return design


def test_route_a_uses_only_locked_fresh_windows(project):
    """(15)"""
    _ready(project)
    readiness = DS.readiness(project)
    assert readiness["route_a"], readiness["reasons"]
    payload = DS.aggregate(project)
    assert payload["namespace"] == AW.COMPARABLE_NAMESPACE
    assert payload["excluded"] == []
    for used in payload["analysis_inputs_used"].values():
        assert used.endswith("__window_v001")
    for cell in payload["route_a"]:
        assert cell["coverage_status"] == "COMPLETE"
        assert cell["stat"]["n_valid"] == 2


def test_route_b_uses_only_locked_fresh_windows(project):
    """(16)"""
    _ready(project)
    payload = DS.aggregate(project)
    assert payload["route_b_available"]
    assert payload["route_b"]
    for rep in payload["route_b"]:
        assert rep["stat"]["n_valid"] == rep["stat"]["n_expected"] == 2


def test_a_cell_with_a_full_session_reports_two_of_three(project):
    """(4) and the coverage display."""
    design = _design(project, n_fg=1, replicates=3)
    _import(project, "hum_fg1", _human(), "human")
    _lock_whole(project, "hum_fg1")
    DS.assign(project, transcript_id="hum_fg1", condition_id="human",
              focus_group_id="fg1", role=D.Role.HUMAN_REFERENCE.value)
    DS.compute_for_assignment(project, "hum_fg1")

    for k in (1, 2, 3):
        name = f"syn_r{k}"
        _import(project, name, _synthetic(seed=k), "synthetic")
        if k != 3:
            _lock_whole(project, name)
        DS.assign(project, transcript_id=name, condition_id="cond-a",
                  focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
                  replicate_index=k)
        DS.compute_for_assignment(project, name)

    report = DS.coverage(project)
    cell = report.cell("cond-a", "fg1")
    assert cell.present == 3                      # three files are there...
    assert cell.eligible == 2                     # ...two are comparable units
    assert not cell.complete_for_comparison
    assert [i["transcript_id"] for i in cell.ineligible] == ["syn_r3"]
    assert cell.ineligible[0]["reason"] == "missing window"

    matrix = DS.coverage_matrix(report, design)
    assert matrix[0]["cond-a"].startswith("2/3")
    assert not DS.readiness(project)["route_a"]

    payload = DS.aggregate(project)
    excluded = {e["transcript_id"] for e in payload["excluded"]}
    assert excluded == {"syn_r3"}
    for cell_payload in payload["route_a"]:
        assert cell_payload["stat"]["n_valid"] == 2
        assert cell_payload["stat"]["n_expected"] == 3
        assert cell_payload["coverage_status"] == "INCOMPLETE"


def test_an_under_review_window_does_not_feed_a_comparison(project):
    _design(project, n_fg=1, replicates=1)
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    window = W.propose_manual_window(project, "syn_a",
                                     start_text="When I get home after work")
    assert window.status == AW.WindowStatus.UNDER_REVIEW.value
    DS.assign(project, transcript_id="syn_a", condition_id="cond-a",
              focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
              replicate_index=1)
    DS.compute_for_assignment(project, "syn_a")

    cell = DS.coverage(project).cell("cond-a", "fg1")
    assert cell.eligible == 0
    assert cell.positions[0].display == "under review"
    assert not DS.readiness(project)["route_a"]


# ================================================================ D3 migration
def test_migration_does_not_promote_an_old_declaration(project):
    """(17)"""
    _import(project, "syn_a", _synthetic(), "synthetic",
            window_declaration="comparable_window")
    payload = I.load_canonical(project, "syn_a")
    # a Phase 3B result: keyed by transcript, no analysis input
    S.run_structural(project, I.rehydrate(payload),
                     window_declaration="comparable_window",
                     canonical_sha256=payload["canonical_sha256"])
    legacy_path = project.path / "runs" / "level2" / "syn_a__fullrun.json"
    stored = json.loads(legacy_path.read_text(encoding="utf-8"))
    for key in ("analysis_input_id", "namespace", "comparison_eligible",
                "calculation_status", "window_id"):
        stored.pop(key, None)
    (project.path / "runs" / "level2" / "syn_a.json").write_text(
        json.dumps(stored), encoding="utf-8")
    legacy_path.unlink()

    report = I.migration_report(project)
    assert report["legacy_unverified_window"] == ["syn_a"]
    assert report["transcripts_without_window"] == ["syn_a"]
    assert "NOT promoted" in report["promotion_policy"]

    result = S.restore_results(project)["syn_a"]
    assert result.calculation_status == \
        AW.CalculationStatus.LEGACY_UNVERIFIED_WINDOW.value
    assert not result.aggregation_eligible
    assert W.active_window(project, "syn_a") is None       # nothing was created
    assert S.comparable_run_results(project) == {}


def test_a_legacy_full_transcript_result_is_descriptive_only(project):
    _import(project, "syn_a", _synthetic(), "synthetic",
            window_declaration="full_transcript")
    payload = I.load_canonical(project, "syn_a")
    S.run_structural(project, I.rehydrate(payload),
                     window_declaration="full_transcript",
                     canonical_sha256=payload["canonical_sha256"])
    stored = json.loads((project.path / "runs" / "level2"
                         / "syn_a__fullrun.json").read_text(encoding="utf-8"))
    for key in ("analysis_input_id", "namespace", "comparison_eligible",
                "calculation_status"):
        stored.pop(key, None)
    (project.path / "runs" / "level2" / "syn_a.json").write_text(
        json.dumps(stored), encoding="utf-8")
    assert S.restore_results(project)["syn_a"].calculation_status == \
        AW.CalculationStatus.DESCRIPTIVE_ONLY.value


# =========================================================== G replace safely
def test_replacing_a_canonical_invalidates_its_windows_and_results(project):
    """(18)"""
    _design(project, n_fg=1, replicates=1)
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    window = _lock_whole(project, "syn_a")
    DS.assign(project, transcript_id="syn_a", condition_id="cond-a",
              focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
              replicate_index=1)
    DS.compute_for_assignment(project, "syn_a")

    preview = I.replacement_preview(project, "syn_a")
    assert preview["windows_invalidated"] == [window.window_id]
    assert preview["level2_results_archived"] == [window.window_id]
    assert preview["assignments_becoming_stale"]
    assert preview["reversible"] is True
    assert "syn_a" in preview["confirmation_required"]

    _import(project, "syn_a", _synthetic(rounds=9), "synthetic",
            on_collision=I.CollisionPolicy.REPLACE_INVALIDATE_DERIVED)

    assert S.stored_runs(project) == []            # the window's result was archived
    assert W.load_window(project, window.window_id) is not None   # kept, not deleted
    state = W.window_state(project, "syn_a")
    assert not state.comparison_eligible
    assert "different version" in state.reason
    report = DS.coverage(project)
    assert report.stale_transcript_ids == ["syn_a"]
    assert not DS.readiness(project)["route_a"]


def test_a_window_derived_from_replaced_bytes_cannot_be_locked(project):
    """The guard that stops a stale proposal being promoted after a replacement."""
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    turns = I.load_canonical(project, "syn_a")["turns"]
    proposed = W.propose_manual_window(
        project, "syn_a", start_turn_id=turns[2]["turn_id"],
        end_turn_id=turns[-2]["turn_id"], researcher_label="R. Lara")
    assert proposed.status == AW.WindowStatus.PROPOSED.value

    _import(project, "syn_a", _synthetic(rounds=9), "synthetic",
            on_collision=I.CollisionPolicy.REPLACE_INVALIDATE_DERIVED)

    with pytest.raises(W.WindowServiceError, match="re-propose"):
        W.lock_window(project, proposed.window_id)
    assert W.load_window(project, proposed.window_id).status == \
        AW.WindowStatus.PROPOSED.value            # unchanged, not silently rejected


# ============================================================== immutability
def test_the_frozen_benchmark_is_byte_identical_after_everything(project):
    """(20)"""
    def digests():
        return {k: hashlib.sha256(s.path.read_bytes()).hexdigest()
                for k, s in TH.SOURCES.items()}

    before = digests()
    _ready(project)
    DS.aggregate(project)
    DS.coverage(project)
    DS.readiness(project)
    I.migration_report(project)
    assert digests() == before

    from platform_core.services import benchmark_service as B
    assert B.check_sources()["ok"]
    assert len(B.level2_condition_summary()) == 7


def test_the_frozen_windows_module_is_untouched_by_this_phase():
    """`windows.py` reads the artefacts of record; nothing here re-derives them."""
    import inspect

    from platform_core import windows as frozen_windows
    source = inspect.getsource(W)
    assert "propose_window_for_new_corpus" not in source
    assert "FROZEN_WINDOW_ROOT" not in source
    assert frozen_windows.available_frozen_windows()      # still readable


def test_a_stale_human_reference_blocks_route_a(project):
    """
    Regression. Readiness once checked only the synthetic cells, so superseding a
    HUMAN window left Route A reporting ready while the referent was stale. The
    human side is the point of a matched comparison; it gates the same way.
    """
    _ready(project, n_fg=1, replicates=2)
    assert DS.readiness(project)["route_a"]

    old = W.active_window(project, "hum_fg1").window_id
    turns = I.load_canonical(project, "hum_fg1")["turns"]
    new = W.supersede_window(project, old, start_turn_id=turns[2]["turn_id"],
                             end_turn_id=turns[-2]["turn_id"],
                             researcher_label="R. Lara",
                             researcher_note="second review")
    W.lock_window(project, new.window_id)

    readiness = DS.readiness(project)
    assert not readiness["route_a"] and not readiness["route_b"]
    assert "hum_fg1" in " ".join(readiness["reasons"])
    report = DS.coverage(project)
    assert not report.ready_for_comparison
    assert [p.display for p in report.human_positions] == ["locked, not computed"]

    DS.compute_for_assignment(project, "hum_fg1")
    assert DS.readiness(project)["route_a"]
    payload = DS.aggregate(project)
    assert payload["analysis_inputs_used"]["hum_fg1"] == new.window_id
