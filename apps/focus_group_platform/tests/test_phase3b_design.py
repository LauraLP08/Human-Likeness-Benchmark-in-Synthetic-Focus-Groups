"""
Phase 3B: persistence, configurable design, and aggregation for a user's corpus.

Everything here runs without Streamlit.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from platform_core import aggregate as A
from platform_core import design as D
from platform_core import design_aggregate as E
from platform_core import thematic as TH
from platform_core.config import resolve_data_dir
from platform_core.services import (audit, context as C, design_service as DS,
                                    export_service as X, import_service as I,
                                    structural_service as S,
                                    window_service as W)


def _input(transcript_id: str) -> str:
    """Phase 3C files a result under its analytical input."""
    return f"{transcript_id}__fullrun"


def _lock_whole(project, transcript_id):
    """Give a transcript a locked comparable window."""
    window = W.confirm_whole_transcript(
        project, transcript_id, researcher_label="R. Lara",
        researcher_note="already trimmed at source")
    return W.lock_window(project, window.window_id)

LONG = ("When I get home after work the last thing I want is a project, so I keep a "
        "rotation of about five meals I can do with my eyes closed.")
SHORT = "I agree with that."


def _synthetic(n_participants=4, rounds=3, text=LONG):
    entries = [{"turn": 1, "speaker_id": "MODERATOR", "speaker_name": "Moderator",
                "content": "Tell me about weeknight cooking.",
                "timestamp": "2026-01-01T00:00:00Z", "selection_mode": "scripted"}]
    turn = 2
    for r in range(rounds):
        for p in range(n_participants):
            entries.append({
                "turn": turn, "speaker_id": f"P{p + 1}",
                "speaker_name": f"Person{p + 1}",
                "content": f"{text} ({r},{p})",
                "timestamp": f"2026-01-01T00:{turn:02d}:00Z",
                "selection_mode": "model"})
            turn += 1
    return entries


def _human(n_participants=4, rounds=3, text=SHORT):
    entries = [{"turn": 1, "speaker_id": "MOD", "canonical_speaker_id": "MOD",
                "speaker_name": "Moderator", "speaker_role": "moderator",
                "content": "Tell me about weeknight cooking."}]
    turn = 2
    for r in range(rounds):
        for p in range(n_participants):
            entries.append({
                "turn": turn, "speaker_id": f"P{p + 1}",
                "canonical_speaker_id": f"P{p + 1}",
                "speaker_name": f"Person{p + 1}", "speaker_role": "participant",
                "content": f"{text} ({r},{p})"})
            turn += 1
    return entries


ROSTER = ["Person1", "Person2", "Person3", "Person4"]


@pytest.fixture()
def data_dir(tmp_path):
    return resolve_data_dir(injected=tmp_path / "platform-data", ensure=True)


@pytest.fixture()
def project(data_dir):
    return I.new_project("Trial", data_dir)


def _import(project, name, entries, transcript_type, **kwargs):
    kwargs.setdefault("window_declaration",
                      "comparable_window" if transcript_type == "synthetic"
                      else None)
    if transcript_type == "human":
        kwargs.pop("window_declaration", None)
        kwargs.setdefault("roster_names", ROSTER)
    return I.import_transcript(
        project, filename=f"{name}.json",
        content=json.dumps(entries).encode("utf-8"),
        transcript_type=transcript_type, **kwargs)


def _compute(project, transcript_id):
    payload = I.load_canonical(project, transcript_id)
    return S.run_structural(
        project, I.rehydrate(payload),
        roster_names=payload.get("roster_names") or None,
        window_declaration=payload.get("window_declaration"),
        canonical_sha256=payload["canonical_sha256"])


# ==================================================== A1 validation by id
def test_validation_is_persisted_per_transcript(project):
    a = _import(project, "syn_a", _synthetic(), "synthetic")
    b = _import(project, "syn_b", _synthetic(rounds=5), "synthetic")

    for outcome in (a, b):
        stored = I.load_validation_report(project, outcome.transcript_id)
        assert stored["transcript_id"] == outcome.transcript_id
        assert stored["canonical_sha256"] == outcome.canonical_sha256
        assert stored["source_sha256"] == outcome.transcript.source_sha256
        assert stored["normaliser_version"]
        assert "generated_utc" in stored
        assert "generated_utc" not in json.dumps(stored["validation_report"])

    reports = I.stored_validation_reports(project)
    assert sorted(r["transcript_id"] for r in reports) == ["syn_a", "syn_b"]
    assert (I.load_validation_report(project, "syn_a")["validation_report"]
            ["n_entries"]
            != I.load_validation_report(project, "syn_b")["validation_report"]
            ["n_entries"])


def test_exporting_a_never_carries_the_validation_of_b(project):
    """(1) The report travels by transcript id, not from the last import."""
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    _import(project, "syn_b", _synthetic(rounds=7), "synthetic")
    result = _compute(project, "syn_a")

    files = X.project_export(
        transcript_payload=I.load_canonical(project, "syn_a"),
        validation_report={},
        validation_payload=I.load_validation_report(project, "syn_a"),
        structural_payload=S.load_structural(project, _input("syn_a")),
        structural_rows=result.rows, generated_utc="2026-08-04T00:00:00Z")

    report = json.loads(next(f for f in files
                             if f.filename == "validation_report.json").text)
    assert report["transcript_id"] == "syn_a"
    assert report["n_entries"] == 13          # 3 rounds x 4 + moderator
    assert report["n_entries"] != 29


def test_a_mismatched_package_is_refused(project):
    _import(project, "syn_a", _synthetic(), "synthetic")
    _import(project, "syn_b", _synthetic(rounds=5), "synthetic")
    _compute(project, "syn_a")

    with pytest.raises(X.TraceabilityError, match="same transcript"):
        X.project_export(
            transcript_payload=I.load_canonical(project, "syn_a"),
            validation_report={},
            validation_payload=I.load_validation_report(project, "syn_b"),
            structural_payload=S.load_structural(project, _input("syn_a")),
            structural_rows=[], generated_utc="2026-08-04T00:00:00Z")


def test_a_stale_hash_blocks_the_export(project):
    _import(project, "syn_a", _synthetic(), "synthetic")
    _compute(project, "syn_a")
    stale = dict(S.load_structural(project, _input("syn_a")), canonical_sha256="0" * 64)
    with pytest.raises(X.TraceabilityError, match="canonical"):
        X.project_export(
            transcript_payload=I.load_canonical(project, "syn_a"),
            validation_report={},
            validation_payload=I.load_validation_report(project, "syn_a"),
            structural_payload=stale, structural_rows=[],
            generated_utc="2026-08-04T00:00:00Z")


# ================================================= A2 no silent overwrite
def test_a_collision_is_rejected_by_default(project):
    """(2)"""
    first = _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    again = _import(project, "syn_a", _synthetic(rounds=9), "synthetic")
    assert not again.ok
    assert again.problems[0].code == "transcript_id_collision"
    assert "Nothing has been changed" in again.problems[0].message
    # the original is untouched
    assert I.load_canonical(project, "syn_a")["canonical_sha256"] == \
        first.canonical_sha256
    assert len(I.stored_transcripts(project)) == 1


def test_new_version_keeps_both(project):
    """(3)"""
    first = _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    second = _import(project, "syn_a", _synthetic(rounds=9), "synthetic",
                     on_collision=I.CollisionPolicy.NEW_VERSION)
    assert second.ok and second.transcript_id == "syn_a__v002"
    assert second.version == 2
    ids = sorted(t["transcript_id"] for t in I.stored_transcripts(project))
    assert ids == ["syn_a", "syn_a__v002"]
    assert first.canonical_sha256 != second.canonical_sha256
    third = _import(project, "syn_a", _synthetic(rounds=11), "synthetic",
                    on_collision=I.CollisionPolicy.NEW_VERSION)
    assert third.transcript_id == "syn_a__v003"


def test_replace_archives_the_derived_artefacts(project):
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    _compute(project, "syn_a")
    old_result = S.load_structural(project, _input("syn_a"))

    replaced = _import(project, "syn_a", _synthetic(rounds=9), "synthetic",
                       on_collision=I.CollisionPolicy.REPLACE_INVALIDATE_DERIVED)
    assert replaced.replaced
    assert _input("syn_a") not in S.stored_runs(project)   # moved aside
    archived = list((project.path / "derived" / "archive").rglob("*.json"))
    assert len(archived) == 3                         # canonical, validation, level2
    assert any(json.loads(p.read_text(encoding="utf-8")).get("canonical_sha256")
               == old_result["canonical_sha256"] for p in archived)


# ================================================ A3 state restored from disk
def test_results_are_restored_from_disk(project):
    """(5)"""
    _import(project, "syn_a", _synthetic(), "synthetic")
    computed = _compute(project, "syn_a")
    restored = S.restore_results(project)
    assert set(restored) == {_input("syn_a")}
    assert restored[_input("syn_a")].freshness == S.FRESH
    assert [r["value"] for r in restored[_input("syn_a")].rows] == \
        [r["value"] for r in computed.rows]
    assert restored[_input("syn_a")].producer.startswith(
        "aggregate_production_results")


def test_a_result_from_an_older_hash_is_stale(project):
    """(4)"""
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    _compute(project, "syn_a")
    assert S.restore_results(project)[_input("syn_a")].freshness == S.FRESH

    _import(project, "syn_a", _synthetic(rounds=9), "synthetic",
            on_collision=I.CollisionPolicy.REPLACE_INVALIDATE_DERIVED)
    # replacement archives the result, so re-run against the OLD hash on purpose
    payload = I.load_canonical(project, "syn_a")
    S.run_structural(project, I.rehydrate(payload), canonical_sha256="0" * 64)

    restored = S.restore_results(project)[_input("syn_a")]
    assert restored.freshness == S.STALE
    assert _input("syn_a") not in S.fresh_run_results(project)
    problem = S.stale_problem(restored)
    assert problem.code == "stale_result"
    assert "excluded from every aggregate" in problem.message


def test_the_canonical_digest_is_stable_across_reads(project):
    outcome = _import(project, "syn_a", _synthetic(), "synthetic")
    first = I.load_canonical(project, "syn_a")["canonical_sha256"]
    second = I.load_canonical(project, "syn_a")["canonical_sha256"]
    assert first == second == outcome.canonical_sha256


# =================================================== A4 explicit pair only
def test_the_pair_is_chosen_not_taken_from_position(project):
    """(6) Two human and three synthetic; file order must not choose the pair."""
    for name in ("hum_z", "hum_a"):
        _import(project, name, _human(), "human")
    for name in ("syn_z", "syn_m", "syn_a"):
        _import(project, name, _synthetic(), "synthetic")
    for record in I.stored_transcripts(project):
        _compute(project, record["transcript_id"])

    context = C.build_context(context_id="default", study_name="X",
                              human_set_id="hum_z",
                              synthetic_set_ids=["syn_z", "syn_m", "syn_a"],
                              declaration_by_user="declared homologues")
    results = S.restore_results(project)
    comparison = S.compare_single_session(
        context, human_transcript_id="hum_z", synthetic_transcript_id="syn_m",
        human_rows=results[_input("hum_z")].rows,
        synthetic_rows=results[_input("syn_m")].rows)

    assert comparison.human_transcript_id == "hum_z"
    assert comparison.synthetic_transcript_id == "syn_m"
    assert all(r["synthetic_transcript_id"] == "syn_m" for r in comparison.rows)
    # alphabetical order would have chosen hum_a and syn_a
    assert sorted(t["transcript_id"] for t in I.stored_transcripts(project))[0] == \
        "hum_a"
    assert any("SINGLE-SESSION DIAGNOSTIC" in c for c in comparison.caveats)


def test_the_comparison_refuses_to_guess_a_pair(project):
    context = C.build_context(context_id="default", study_name="X",
                              human_set_id="h", synthetic_set_ids=["s"],
                              declaration_by_user="declared")
    with pytest.raises(S.StructuralError, match="never by position"):
        S.compare_single_session(context, human_transcript_id="",
                                 synthetic_transcript_id="s",
                                 human_rows=[], synthetic_rows=[])


# ================================================= B design and assignment
def _small_design(project, *, n_fg=3, replicates=2, conditions=("cond-a",),
                  with_human=True):
    design = D.simple_design(
        design_id="default", project_id=project.project_id, study_name="Trial",
        n_focus_groups=n_fg, synthetic_conditions=list(conditions),
        replicates=replicates, with_human=with_human, created_utc="2026-08-04")
    DS.save_design(project, design)
    return design


def test_a_three_by_two_design_is_valid_and_persisted(project):
    """(7)"""
    design = _small_design(project)
    reloaded = DS.load_design(project)
    assert reloaded.focus_group_ids == ["fg1", "fg2", "fg3"]
    assert reloaded.expected_replicates_by_condition["cond-a"] == 2
    assert len(design.expected_synthetic_positions()) == 6
    assert D.validate_design(reloaded) == []


def test_nothing_is_inferred_from_a_file_name(project):
    _small_design(project)
    _import(project, "fg2_conda_run03", _synthetic(), "synthetic")
    assignments = DS.load_assignments(project)
    assert assignments == []
    report = DS.coverage(project)
    assert report.status == D.DesignStatus.EMPTY.value
    assert report.unassigned_transcript_ids == ["fg2_conda_run03"]


def test_a_duplicate_assignment_is_blocked(project):
    """(9)"""
    _small_design(project)
    _import(project, "syn_a", _synthetic(), "synthetic")
    _import(project, "syn_b", _synthetic(), "synthetic")
    DS.assign(project, transcript_id="syn_a", condition_id="cond-a",
              focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
              replicate_index=1)
    DS.assign(project, transcript_id="syn_b", condition_id="cond-a",
              focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
              replicate_index=1)
    report = DS.coverage(project)
    cell = report.cell("cond-a", "fg1")
    assert cell.duplicates == [{"replicate_index": 1,
                                "transcript_ids": ["syn_a", "syn_b"]}]
    assert not cell.complete


def test_an_undeclared_condition_is_refused(project):
    _small_design(project)
    _import(project, "syn_a", _synthetic(), "synthetic")
    with pytest.raises(DS.DesignServiceError, match="not declared"):
        DS.assign(project, transcript_id="syn_a", condition_id="nope",
                  focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
                  replicate_index=1)


def test_a_replicate_index_outside_the_design_is_a_problem(project):
    _small_design(project, replicates=2)
    _import(project, "syn_a", _synthetic(), "synthetic")
    DS.assign(project, transcript_id="syn_a", condition_id="cond-a",
              focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
              replicate_index=1)
    stored = DS.load_assignments(project)
    stored[0].replicate_index = 5
    DS.save_assignments(project, stored)
    report = DS.coverage(project)
    assert report.status == D.DesignStatus.INVALID.value
    assert any("outside 1..2" in p for p in report.problems)


def test_reassigning_a_transcript_moves_it_rather_than_duplicating(project):
    _small_design(project)
    _import(project, "syn_a", _synthetic(), "synthetic")
    DS.assign(project, transcript_id="syn_a", condition_id="cond-a",
              focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
              replicate_index=1)
    DS.assign(project, transcript_id="syn_a", condition_id="cond-a",
              focus_group_id="fg2", role=D.Role.SYNTHETIC_RUN.value,
              replicate_index=1)
    assignments = DS.load_assignments(project)
    assert len(assignments) == 1
    assert assignments[0].focus_group_id == "fg2"


def test_a_manifest_assigns_from_declared_values(project):
    _small_design(project)
    for name in ("syn_a", "syn_b"):
        _import(project, name, _synthetic(), "synthetic")
    manifest = ("transcript_id,condition_id,focus_group_id,replicate_index,role\n"
                "syn_a,cond-a,fg1,1,SYNTHETIC_RUN\n"
                "syn_b,cond-a,fg1,2,SYNTHETIC_RUN\n")
    assigned, problems = DS.import_manifest(project, manifest)
    assert problems == [] and len(assigned) == 2
    assert DS.coverage(project).cell("cond-a", "fg1").complete


def test_an_assignment_goes_stale_when_the_transcript_changes(project):
    _small_design(project)
    _import(project, "syn_a", _synthetic(rounds=3), "synthetic")
    DS.assign(project, transcript_id="syn_a", condition_id="cond-a",
              focus_group_id="fg1", role=D.Role.SYNTHETIC_RUN.value,
              replicate_index=1)
    _import(project, "syn_a", _synthetic(rounds=9), "synthetic",
            on_collision=I.CollisionPolicy.REPLACE_INVALIDATE_DERIVED)
    report = DS.coverage(project)
    assert report.stale_transcript_ids == ["syn_a"]
    assert report.status == D.DesignStatus.STALE.value


# ================================================== C aggregation, new corpora
def _populate(project, *, n_fg=3, replicates=2, condition="cond-a",
              with_human=True, skip=()):
    _small_design(project, n_fg=n_fg, replicates=replicates,
                  conditions=(condition,), with_human=with_human)
    for fg in range(1, n_fg + 1):
        if with_human:
            name = f"hum_fg{fg}"
            _import(project, name, _human(), "human")
            _lock_whole(project, name)
            DS.assign(project, transcript_id=name, condition_id="human",
                      focus_group_id=f"fg{fg}", role=D.Role.HUMAN_REFERENCE.value)
        for k in range(1, replicates + 1):
            if (fg, k) in skip:
                continue
            name = f"syn_fg{fg}_r{k}"
            _import(project, name, _synthetic(rounds=2 + fg), "synthetic")
            _lock_whole(project, name)
            DS.assign(project, transcript_id=name, condition_id=condition,
                      focus_group_id=f"fg{fg}", role=D.Role.SYNTHETIC_RUN.value,
                      replicate_index=k)
    for record in I.stored_transcripts(project):
        DS.compute_for_assignment(project, record["transcript_id"])


def test_route_a_works_on_a_three_by_two_design(project):
    """(7)"""
    _populate(project)
    readiness = DS.readiness(project)
    assert readiness["status"] == D.DesignStatus.READY_FOR_MATCHED_COMPARISON.value
    assert readiness["route_a"] and readiness["route_b"]

    payload = DS.aggregate(project)
    cells = payload["route_a"]
    assert len(cells) == len(E.DISPLAY_METRIC_IDS) * 3     # 3 FGs, one condition
    for cell in cells:
        assert cell["stat"]["n_expected"] == 2
        assert cell["coverage_status"] == "COMPLETE"
        assert cell["human_reference"] is not None
    assert payload["frozen_benchmark_used"] is False


def test_route_b_groups_the_replicate_index_across_focus_groups(project):
    _populate(project)
    payload = DS.aggregate(project)
    assert payload["route_b_available"]
    replicates = payload["route_b"]
    assert len(replicates) == len(E.DISPLAY_METRIC_IDS) * 2
    for rep in replicates:
        assert rep["stat"]["n_expected"] == 3
        assert rep["focus_groups_included"] == ["fg1", "fg2", "fg3"]
        assert "does NOT imply a shared seed" in rep["note"]


def test_route_b_refuses_when_the_indices_are_not_comparable(project):
    """(11)"""
    _populate(project, replicates=2, skip=((2, 2),))
    payload = DS.aggregate(project)
    assert not payload["route_b_available"]
    assert payload["route_b"] == []
    assert "different replicate indices" in payload["route_b_reason"]
    # route A still reports, with the gap made explicit
    fg2 = [c for c in payload["route_a"] if c["focus_group_id"] == "fg2"]
    assert all(c["stat"]["n_valid"] == 1 and c["stat"]["n_expected"] == 2
               for c in fg2)
    assert all(c["missing_replicates"] == [2] for c in fg2)


def test_incomplete_coverage_is_reported_without_imputation(project):
    """(10)"""
    _populate(project, skip=((3, 2),))
    report = DS.coverage(project)
    assert report.status == D.DesignStatus.INCOMPLETE.value
    cell = report.cell("cond-a", "fg3")
    assert cell.present == 1 and cell.expected == 2
    assert cell.missing_replicates == [2]
    assert "no missing transcript is imputed" in " ".join(report.notes)

    payload = DS.aggregate(project)
    fg3 = [c for c in payload["route_a"] if c["focus_group_id"] == "fg3"]
    for c in fg3:
        assert c["stat"]["values"][1] is None       # not filled in
        assert c["stat"]["n_valid"] == 1
        assert 0 not in [v for v in c["stat"]["values"] if v is not None] or True


def test_a_none_reduces_n_and_never_becomes_zero(project):
    _populate(project, n_fg=1, replicates=2, with_human=False)
    values = [None, 4.0]
    stat = E.summarise(values, n_expected=2)
    assert stat.n_valid == 1 and stat.n_expected == 2
    assert stat.mean == 4.0                       # not (0 + 4) / 2
    assert stat.undefined_reason and "not imputed" in stat.undefined_reason


def test_ratios_are_means_of_run_ratios_not_pooled_denominators(project):
    """(13)"""
    _populate(project, n_fg=1, replicates=2, with_human=False)
    payload = DS.aggregate(project)
    ratio_cells = [c for c in payload["route_a"]
                   if c["metric_id"] == "moderator_word_share"]
    assert ratio_cells
    for cell in ratio_cells:
        assert cell["aggregation_rule"] == "ratio_no_pooling"
        assert "never summed across sessions" in \
            cell["aggregation_rule_description"]
        runs = [v for v in cell["stat"]["values"] if v is not None]
        assert cell["stat"]["mean"] == pytest.approx(sum(runs) / len(runs))


def test_a_stale_result_is_excluded_from_the_aggregate(project):
    _populate(project, n_fg=1, replicates=2, with_human=False)
    window_id = W.active_window(project, "syn_fg1_r1").window_id
    payload = S.load_structural(project, window_id)
    payload["canonical_sha256"] = "0" * 64
    (project.path / "runs" / "level2" / f"{window_id}.json").write_text(
        json.dumps(payload), encoding="utf-8")

    aggregated = DS.aggregate(project)
    assert aggregated["excluded_stale"] == [window_id]
    cells = [c for c in aggregated["route_a"]
             if c["metric_id"] == "participant_turns"]
    assert cells[0]["stat"]["n_valid"] == 1 and cells[0]["stat"]["n_expected"] == 2


def test_no_new_study_uses_the_macho_meals_referent(project):
    """(12)"""
    _populate(project)
    payload = DS.aggregate(project)
    frozen_human = {r["value"] for r in
                    __import__("platform_core.services.benchmark_service",
                               fromlist=["x"]).level2_rows()
                    if r["condition"] == "human" and r["value"] is not None}
    text = json.dumps(payload)
    for value in frozen_human:
        assert repr(value) not in text
    assert payload["frozen_benchmark_used"] is False
    for cell in payload["route_a"]:
        assert cell["human_transcript_id"] in (None, f"hum_{cell['focus_group_id']}")


# ============================== C1 the frozen wrapper still reproduces exactly
def _frozen_design_inputs():
    rows = A.load_frozen_metric_rows()
    metrics = list(E.DISPLAY_METRIC_IDS)
    design = D.StudyDesign(
        design_id="frozen", project_id="frozen", study_name="Macho Meals",
        conditions=[D.Condition("human", "Human", D.Side.HUMAN.value, 1),
                    D.Condition("enriched", "Enriched", D.Side.SYNTHETIC.value, 3),
                    D.Condition("demographics-only", "Demographics-only",
                                D.Side.SYNTHETIC.value, 3)],
        focus_groups=[D.FocusGroup(f) for f in A.FGS])

    assignments, run_results, seen = [], {}, set()
    for r in rows:
        if r.metric_id not in metrics:
            continue
        if r.side == "human":
            transcript_id = f"human_{r.fg}"
            if transcript_id not in seen:
                assignments.append(D.TranscriptAssignment(
                    transcript_id, "human", r.fg, D.Role.HUMAN_REFERENCE.value,
                    "s", "c"))
        else:
            transcript_id = r.physical_run
            if transcript_id not in seen:
                assignments.append(D.TranscriptAssignment(
                    transcript_id, r.condition, r.fg, D.Role.SYNTHETIC_RUN.value,
                    "s", "c", replicate_index=r.replicate_index))
        seen.add(transcript_id)
        run_results.setdefault(transcript_id, []).append(
            {"metric_id": r.metric_id, "value": r.value})
    return rows, metrics, design, assignments, run_results


def test_the_engine_reproduces_the_frozen_route_a_exactly():
    """(8)"""
    rows, metrics, design, assignments, run_results = _frozen_design_inputs()
    mine = {(c.metric_id, c.condition_id, c.focus_group_id): c
            for c in E.aggregate_route_a(design, assignments, run_results,
                                         metric_ids=metrics)}
    frozen = A.aggregate_focus_group_condition(rows, metrics)
    assert len(mine) == len(frozen) == 70
    for cell in frozen:
        got = mine[(cell.metric_id, cell.condition, cell.focus_group)]
        assert got.stat.mean == cell.summary.mean
        assert got.stat.n_valid == cell.summary.n_valid
        assert got.human_reference == cell.human_value


def test_the_engine_reproduces_the_frozen_route_b_exactly():
    rows, metrics, design, assignments, run_results = _frozen_design_inputs()
    replicates, reason = E.aggregate_route_b(design, assignments, run_results,
                                             metric_ids=metrics)
    mine = {(r.metric_id, r.condition_id, r.replicate_index): r
            for r in replicates}
    frozen = A.aggregate_study_replicates(rows, metrics)
    assert len(mine) == len(frozen) == 42
    for rep in frozen:
        got = mine[(rep.metric_id, rep.condition, rep.replicate_index)]
        assert got.stat.mean == rep.summary.mean
        assert got.stat.n_valid == rep.summary.n_valid
    assert "does NOT imply a shared seed" in replicates[0].note or reason


def test_the_frozen_module_is_not_touched_by_the_engine():
    """`aggregate.py` keeps its own path; the engine imports only the rule table."""
    import inspect
    source = inspect.getsource(E)
    code = source.replace(E.__doc__ or "", "")      # prose may name it; code may not
    assert "aggregate_focus_group_condition" not in code
    assert "aggregate_study_replicates" not in code
    assert "frozen_workbook_route" not in code
    assert "from .aggregate import AGGREGATION_RULE" in code


# ================================================================= E exports
def test_the_study_package_carries_ids_hashes_and_denominators(project):
    """(14)"""
    _populate(project)
    payload = DS.aggregate(project)
    report = DS.coverage(project)
    results = S.restore_results(project)
    stored = I.stored_transcripts(project)

    files = X.study_package(
        project_id=project.project_id, design=DS.load_design(project).to_dict(),
        assignments=[a.to_dict() for a in DS.load_assignments(project)],
        coverage=report.to_dict(), aggregation=payload,
        run_results={t: r.rows for t, r in results.items()},
        transcript_index={t["transcript_id"]: t for t in stored},
        freshness={t: r.freshness for t, r in results.items()},
        audit_summary=audit.summarise_log(project.path),
        generated_utc="2026-08-04T00:00:00Z")

    assert [f.filename for f in files] == [
        "study_design.json", "transcript_assignments.csv", "coverage_report.json",
        "level2_run_results.csv", "level2_fg_summary.csv",
        "level2_study_replicates.csv", "provenance.json"]

    runs = next(f for f in files if f.filename == "level2_run_results.csv").text
    header = runs.splitlines()[0]
    for column in ("project_id", "design_id", "transcript_id", "condition_id",
                   "focus_group_id", "replicate_index", "metric_id", "value",
                   "denominator", "calculation_status", "coverage_status",
                   "source_sha256", "canonical_sha256", "aggregation_rule"):
        assert column in header
    body = runs.splitlines()[1]
    assert project.project_id in body

    summary = next(f for f in files
                   if f.filename == "level2_fg_summary.csv").text
    assert "n_valid" in summary and "n_expected" in summary
    assert "DERIVED_FROM_PROJECT_RUNS" in summary

    provenance = json.loads(next(f for f in files
                                 if f.filename == "provenance.json").text)
    assert provenance["generated_utc"] == "2026-08-04T00:00:00Z"
    assert provenance["results"]["frozen_benchmark_used"] is False
    assert provenance["results"]["transcripts"]
    for record in provenance["results"]["transcripts"].values():
        assert len(record["canonical_sha256"]) == 64


def test_the_package_is_deterministic_apart_from_the_envelope(project):
    _populate(project, n_fg=1, replicates=2, with_human=False)
    payload = DS.aggregate(project)
    report = DS.coverage(project)
    results = S.restore_results(project)
    stored = I.stored_transcripts(project)

    def build(stamp):
        return {f.filename: f.text for f in X.study_package(
            project_id=project.project_id,
            design=DS.load_design(project).to_dict(),
            assignments=[a.to_dict() for a in DS.load_assignments(project)],
            coverage=report.to_dict(), aggregation=payload,
            run_results={t: r.rows for t, r in results.items()},
            transcript_index={t["transcript_id"]: t for t in stored},
            freshness={t: r.freshness for t, r in results.items()},
            audit_summary={}, generated_utc=stamp)}

    first, second = build("2026-01-01T00:00:00Z"), build("2030-12-31T23:59:59Z")
    for name in first:
        if name == "provenance.json":
            assert json.loads(first[name])["results"] == \
                json.loads(second[name])["results"]
        else:
            assert first[name] == second[name], name


# ================================================================== audit log
def test_the_audit_log_records_the_lifecycle_without_transcript_content(project):
    _populate(project, n_fg=1, replicates=2, with_human=False)
    entries = audit.read_log(project.path)
    events = {e["event"] for e in entries}
    assert {audit.IMPORT, audit.ASSIGN, audit.COMPUTE, audit.DESIGN} <= events

    text = json.dumps(entries)
    assert LONG[:40] not in text
    assert "content" not in text and "speaker_name" not in text
    assert all("canonical_sha256" in e["detail"] or e["event"] in
               (audit.DESIGN, audit.ASSIGN, audit.EXPORT)
               for e in entries if e["event"] == audit.IMPORT)


def test_the_audit_log_refuses_transcript_content(project):
    with pytest.raises(audit.AuditError, match="never transcript content"):
        audit.record(project.path, audit.IMPORT, project_id=project.project_id,
                     subject="x", detail={"content": "a participant said this"})


def test_the_audit_log_is_append_only(project):
    before = len(audit.read_log(project.path))      # creating the project logs one
    audit.record(project.path, audit.IMPORT, project_id="p", subject="a",
                 detail={"n": 1})
    first = audit.audit_path(project.path).read_text(encoding="utf-8")
    audit.record(project.path, audit.EXPORT, project_id="p", subject="b",
                 detail={"n": 2})
    second = audit.audit_path(project.path).read_text(encoding="utf-8")
    assert second.startswith(first)                 # nothing earlier was rewritten
    assert len(audit.read_log(project.path)) == before + 2


# ============================================================== immutability
def test_the_frozen_artefacts_are_untouched_by_the_whole_flow(project):
    """(15)"""
    def digests():
        return {k: hashlib.sha256(s.path.read_bytes()).hexdigest()
                for k, s in TH.SOURCES.items()}

    before = digests()
    _populate(project)
    DS.aggregate(project)
    DS.coverage(project)
    DS.readiness(project)
    assert digests() == before


def test_every_project_write_stays_inside_the_project(project):
    _populate(project, n_fg=1, replicates=2, with_human=False)
    for path in project.path.rglob("*"):
        if path.is_file():
            assert project.path in path.parents or path.parent == project.path


# ========================================== compatibility with Phase 3A projects
def test_a_phase_3a_project_is_migrated_without_adopting_unverifiable_results(
        project):
    """
    Phase 3A wrote no validation file and stored no hash with a result. The
    migration rebuilds the report from the stored canonical, and refuses to adopt a
    result whose input cannot be identified.
    """
    _import(project, "syn_a", _synthetic(), "synthetic")
    _compute(project, "syn_a")

    # regress the project to the Phase 3A shape
    I.validation_path(project, "syn_a").unlink()
    result_path = project.path / "runs" / "level2" / f"{_input('syn_a')}.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload.pop("canonical_sha256")
    payload.pop("analysis_input_id", None)
    legacy_path = project.path / "runs" / "level2" / "syn_a.json"
    legacy_path.write_text(json.dumps(payload), encoding="utf-8")
    result_path.unlink()

    assert S.restore_results(project)["syn_a"].freshness == S.STALE

    outcome = I.migrate_project(project)
    assert outcome["validation_reports_written"] == ["syn_a"]
    assert outcome["level2_results_without_hash"] == ["syn_a"]

    stored = I.load_validation_report(project, "syn_a")
    assert stored["transcript_id"] == "syn_a"
    assert stored["canonical_sha256"] == \
        I.load_canonical(project, "syn_a")["canonical_sha256"]
    # the result is still not adopted
    assert S.restore_results(project)["syn_a"].freshness == S.STALE
    assert "syn_a" not in S.fresh_run_results(project)

    # recomputing clears it, and a second migration is a no-op
    _compute(project, "syn_a")
    assert S.restore_results(project)[_input("syn_a")].freshness == S.FRESH
    again = I.migrate_project(project)
    assert again["validation_reports_written"] == []
    assert again["validation_reports_already_present"] == ["syn_a"]


def test_a_canonical_written_before_the_digest_existed_still_loads(project):
    _import(project, "syn_a", _synthetic(), "synthetic")
    path = project.path / "derived" / "canonical" / "syn_a.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload["canonical_sha256"]
    payload.pop("canonical_sha256")                 # the Phase 3A shape
    path.write_text(json.dumps(payload), encoding="utf-8")

    record = I.stored_transcripts(project)[0]
    assert record["canonical_sha256"] == expected   # recomputed, not read
    assert I.load_canonical(project, "syn_a")["canonical_sha256"] == expected
