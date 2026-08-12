"""
Study design: the shape of a study, declared rather than inferred.

The thesis ran 5 focus groups x 2 synthetic conditions x 3 replicates. That is ONE
design, not THE design. This module lets a researcher state their own - 3 groups and 2
runs, or 8 groups and 1 run - and everything downstream reads the design instead of
assuming the thesis numbers.

NOTHING IS INFERRED FROM A FILE NAME. A file called `fg2_enriched_run03.json` gets no
condition, no focus group and no replicate index from its name. The user assigns them,
or imports a manifest that states them. Filename inference is how a corpus quietly
ends up mis-labelled, and a mis-labelled cell is worse than an empty one.

This module is pure: dataclasses, validation and status. It reads no file and writes
none - `services/design_service.py` does the persistence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

SCHEMA_VERSION = "1.0.0"


class Side(str, Enum):
    HUMAN = "HUMAN"
    SYNTHETIC = "SYNTHETIC"


class Role(str, Enum):
    HUMAN_REFERENCE = "HUMAN_REFERENCE"
    SYNTHETIC_RUN = "SYNTHETIC_RUN"


class HumanReferencePolicy(str, Enum):
    REQUIRED = "REQUIRED"        # one human transcript per focus group
    OPTIONAL = "OPTIONAL"        # accepted if present, not demanded
    NONE = "NONE"                # synthetic-only study


class MatchingPolicy(str, Enum):
    PAIRED_BY_FOCUS_GROUP = "PAIRED_BY_FOCUS_GROUP"
    NONE = "NONE"


class DesignStatus(str, Enum):
    EMPTY = "EMPTY"
    PARTIAL = "PARTIAL"
    READY_FOR_DESCRIPTIVE = "READY_FOR_DESCRIPTIVE"
    READY_FOR_MATCHED_COMPARISON = "READY_FOR_MATCHED_COMPARISON"
    INCOMPLETE = "INCOMPLETE"
    STALE = "STALE"
    INVALID = "INVALID"


class WindowStatus(str, Enum):
    COMPARABLE_WINDOW = "COMPARABLE_WINDOW"
    FULL_TRANSCRIPT = "FULL_TRANSCRIPT"
    NOT_APPLICABLE = "NOT_APPLICABLE"     # human side
    UNDECLARED = "UNDECLARED"


class DesignError(RuntimeError):
    pass


@dataclass
class Condition:
    condition_id: str
    label: str
    side: str
    expected_replicates: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FocusGroup:
    focus_group_id: str
    label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TranscriptAssignment:
    """
    One transcript in one logical position.

    The two hashes travel with the assignment so that a later reader can tell whether
    the transcript is still the one that was assigned. They are not decoration: the
    STALE state depends on them.
    """

    transcript_id: str
    condition_id: str
    focus_group_id: str
    role: str
    source_sha256: str
    canonical_sha256: str
    replicate_index: int | None = None
    window_status: str = WindowStatus.UNDECLARED.value
    assigned_utc: str = ""
    analysis_input_id: str | None = None
    window_id: str | None = None
    window_artifact_sha256: str | None = None

    @property
    def position(self) -> tuple[str, str, int | None]:
        return (self.condition_id, self.focus_group_id, self.replicate_index)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StudyDesign:
    design_id: str
    project_id: str
    study_name: str
    conditions: list[Condition] = field(default_factory=list)
    focus_groups: list[FocusGroup] = field(default_factory=list)
    human_reference_policy: str = HumanReferencePolicy.OPTIONAL.value
    matching_policy: str = MatchingPolicy.PAIRED_BY_FOCUS_GROUP.value
    created_utc: str = ""
    schema_version: str = SCHEMA_VERSION

    # ------------------------------------------------------------- accessors
    @property
    def expected_replicates_by_condition(self) -> dict[str, int]:
        return {c.condition_id: c.expected_replicates for c in self.conditions}

    @property
    def condition_ids(self) -> list[str]:
        return [c.condition_id for c in self.conditions]

    @property
    def focus_group_ids(self) -> list[str]:
        return [f.focus_group_id for f in self.focus_groups]

    @property
    def synthetic_conditions(self) -> list[Condition]:
        return [c for c in self.conditions if c.side == Side.SYNTHETIC.value]

    @property
    def human_conditions(self) -> list[Condition]:
        return [c for c in self.conditions if c.side == Side.HUMAN.value]

    def condition(self, condition_id: str) -> Condition:
        for c in self.conditions:
            if c.condition_id == condition_id:
                return c
        raise DesignError(f"condition {condition_id!r} is not declared in this design")

    def replicate_indices(self, condition_id: str) -> list[int]:
        return list(range(1, self.condition(condition_id).expected_replicates + 1))

    def expected_synthetic_positions(self) -> list[tuple[str, str, int]]:
        return [(c.condition_id, fg, k)
                for c in self.synthetic_conditions
                for fg in self.focus_group_ids
                for k in range(1, c.expected_replicates + 1)]

    def expected_human_positions(self) -> list[tuple[str, str]]:
        if self.human_reference_policy == HumanReferencePolicy.NONE.value:
            return []
        return [(c.condition_id, fg) for c in self.human_conditions
                for fg in self.focus_group_ids]

    def to_dict(self) -> dict:
        return {
            "design_id": self.design_id,
            "project_id": self.project_id,
            "study_name": self.study_name,
            "conditions": [c.to_dict() for c in self.conditions],
            "focus_groups": [f.to_dict() for f in self.focus_groups],
            "expected_replicates_by_condition": self.expected_replicates_by_condition,
            "human_reference_policy": self.human_reference_policy,
            "matching_policy": self.matching_policy,
            "created_utc": self.created_utc,
            "schema_version": self.schema_version,
        }


def design_from_dict(payload: dict) -> StudyDesign:
    return StudyDesign(
        design_id=payload["design_id"], project_id=payload["project_id"],
        study_name=payload["study_name"],
        conditions=[Condition(**c) for c in payload.get("conditions", [])],
        focus_groups=[FocusGroup(**f) for f in payload.get("focus_groups", [])],
        human_reference_policy=payload.get(
            "human_reference_policy", HumanReferencePolicy.OPTIONAL.value),
        matching_policy=payload.get("matching_policy",
                                    MatchingPolicy.PAIRED_BY_FOCUS_GROUP.value),
        created_utc=payload.get("created_utc", ""),
        schema_version=payload.get("schema_version", SCHEMA_VERSION))


def assignment_from_dict(payload: dict) -> TranscriptAssignment:
    return TranscriptAssignment(**payload)


# ------------------------------------------------------------------ validation
def validate_design(design: StudyDesign) -> list[str]:
    """Problems with the design itself, before any transcript is assigned."""
    problems: list[str] = []
    if not design.conditions:
        problems.append("no condition is declared")
    if not design.focus_groups:
        problems.append("no focus group is declared")

    seen: set[str] = set()
    for c in design.conditions:
        if c.condition_id in seen:
            problems.append(f"condition id {c.condition_id!r} is declared twice")
        seen.add(c.condition_id)
        if c.side not in (Side.HUMAN.value, Side.SYNTHETIC.value):
            problems.append(f"condition {c.condition_id!r}: unknown side {c.side!r}")
        if c.side == Side.SYNTHETIC.value and c.expected_replicates < 1:
            problems.append(
                f"condition {c.condition_id!r}: expected_replicates must be at least "
                f"1, got {c.expected_replicates}")

    seen = set()
    for f in design.focus_groups:
        if f.focus_group_id in seen:
            problems.append(f"focus group id {f.focus_group_id!r} is declared twice")
        seen.add(f.focus_group_id)

    if design.human_reference_policy == HumanReferencePolicy.REQUIRED.value \
            and not design.human_conditions:
        problems.append(
            "human_reference_policy is REQUIRED but no HUMAN condition is declared")
    return problems


@dataclass
class PositionState:
    """
    The five conditions a position must meet to enter a comparison, one field each.

    Reported separately because they fail for different reasons and need different
    fixes: a missing file is not a missing window, and a locked window with no
    computation is not an ineligible one.
    """

    transcript_id: str
    replicate_index: int | None
    assigned: bool = True
    source_present: bool = False
    window_present: bool = False
    window_locked: bool = False
    level2_fresh: bool = False
    comparison_eligible: bool = False
    window_status: str = ""
    namespace: str = ""
    note: str = ""

    @property
    def complete_for_comparison(self) -> bool:
        return all((self.assigned, self.source_present, self.window_present,
                    self.window_locked, self.level2_fresh,
                    self.comparison_eligible))

    @property
    def display(self) -> str:
        if not self.source_present:
            return "missing transcript"
        if not self.window_present:
            return "missing window"
        if not self.window_locked:
            return "under review"
        if not self.level2_fresh:
            return "locked, not computed"
        if not self.comparison_eligible:
            return "descriptive only"
        return "eligible"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["complete_for_comparison"] = self.complete_for_comparison
        d["display"] = self.display
        return d


@dataclass
class CellCoverage:
    condition_id: str
    focus_group_id: str
    expected: int
    present: int
    replicate_indices_present: list[int] = field(default_factory=list)
    missing_replicates: list[int] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)
    stale_transcript_ids: list[str] = field(default_factory=list)
    missing_transcript_ids: list[str] = field(default_factory=list)
    transcript_ids: list[str] = field(default_factory=list)
    positions: list[PositionState] = field(default_factory=list)

    @property
    def eligible(self) -> int:
        return len([p for p in self.positions if p.complete_for_comparison])

    @property
    def ineligible(self) -> list[dict]:
        return [{"transcript_id": p.transcript_id, "reason": p.display}
                for p in self.positions if not p.complete_for_comparison]

    @property
    def complete(self) -> bool:
        """Structurally complete: the right number of runs, no defects."""
        return (self.present == self.expected and not self.missing_replicates
                and not self.duplicates and not self.stale_transcript_ids
                and not self.missing_transcript_ids)

    @property
    def complete_for_comparison(self) -> bool:
        """AND every one of them is an eligible comparable unit."""
        return self.complete and self.eligible == self.expected

    def to_dict(self) -> dict:
        d = asdict(self)
        d["complete"] = self.complete
        d["complete_for_comparison"] = self.complete_for_comparison
        d["eligible"] = self.eligible
        d["ineligible"] = self.ineligible
        d["positions"] = [p.to_dict() for p in self.positions]
        return d


@dataclass
class CoverageReport:
    design_id: str
    status: str
    problems: list[str] = field(default_factory=list)
    cells: list[CellCoverage] = field(default_factory=list)
    human_by_focus_group: dict[str, list[str]] = field(default_factory=dict)
    missing_human_focus_groups: list[str] = field(default_factory=list)
    duplicate_human_focus_groups: list[str] = field(default_factory=list)
    stale_transcript_ids: list[str] = field(default_factory=list)
    missing_assigned_transcript_ids: list[str] = field(default_factory=list)
    fresh_transcript_ids: list[str] = field(default_factory=list)
    unassigned_transcript_ids: list[str] = field(default_factory=list)
    human_positions: list[PositionState] = field(default_factory=list)
    route_b_available: bool = False
    route_b_reason: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def ready_for_comparison(self) -> bool:
        """
        BOTH SIDES. An earlier version checked only the synthetic cells, so a human
        reference whose window had been superseded left Route A reporting "ready"
        while the referent it compares against was stale. The human side is the point
        of a matched comparison; it gates the same way.
        """
        return (bool(self.cells) and not self.problems
                and all(c.complete_for_comparison for c in self.cells)
                and all(p.complete_for_comparison for p in self.human_positions))

    @property
    def ready_for_descriptive(self) -> bool:
        return self.status in (DesignStatus.READY_FOR_DESCRIPTIVE.value,
                               DesignStatus.READY_FOR_MATCHED_COMPARISON.value)

    @property
    def ready_for_matched_comparison(self) -> bool:
        return self.status == DesignStatus.READY_FOR_MATCHED_COMPARISON.value

    def cell(self, condition_id: str, focus_group_id: str) -> CellCoverage:
        for c in self.cells:
            if (c.condition_id, c.focus_group_id) == (condition_id, focus_group_id):
                return c
        raise DesignError(f"no cell {condition_id}/{focus_group_id}")

    def to_dict(self) -> dict:
        return {
            "design_id": self.design_id, "status": self.status,
            "problems": self.problems,
            "cells": [c.to_dict() for c in self.cells],
            "human_by_focus_group": self.human_by_focus_group,
            "missing_human_focus_groups": self.missing_human_focus_groups,
            "duplicate_human_focus_groups": self.duplicate_human_focus_groups,
            "stale_transcript_ids": self.stale_transcript_ids,
            "missing_assigned_transcript_ids": self.missing_assigned_transcript_ids,
            "fresh_transcript_ids": self.fresh_transcript_ids,
            "unassigned_transcript_ids": self.unassigned_transcript_ids,
            "human_positions": [p.to_dict() for p in self.human_positions],
            "ready_for_comparison": self.ready_for_comparison,
            "route_b_available": self.route_b_available,
            "route_b_reason": self.route_b_reason,
            "notes": self.notes,
            "imputation": "none; a missing transcript reduces n and is listed",
        }


def route_b_availability(design: StudyDesign,
                         assignments: list[TranscriptAssignment]
                         ) -> tuple[bool, str]:
    """
    Route B groups replicate k across focus groups. That only means something when
    every focus group in a condition offers the SAME replicate indices.

    Where they differ - four runs here, two there - there is no honest way to say
    which run of one group belongs with which run of another, and inventing a pairing
    is exactly the mistake this check exists to prevent.
    """
    synthetic = [a for a in assignments if a.role == Role.SYNTHETIC_RUN.value]
    if not synthetic:
        return False, "no synthetic run is assigned"

    for condition in design.synthetic_conditions:
        by_fg: dict[str, set[int]] = {}
        for a in synthetic:
            if a.condition_id != condition.condition_id:
                continue
            if a.replicate_index is None:
                return False, (f"{a.transcript_id} has no replicate index; route B "
                               f"needs one for every synthetic run")
            by_fg.setdefault(a.focus_group_id, set()).add(a.replicate_index)

        present = [fg for fg in design.focus_group_ids if fg in by_fg]
        if len(present) < 2:
            return False, (f"condition {condition.condition_id}: fewer than two "
                           f"focus groups have runs, so there is nothing to group "
                           f"across")
        index_sets = {fg: by_fg[fg] for fg in present}
        first = index_sets[present[0]]
        for fg in present[1:]:
            if index_sets[fg] != first:
                return False, (
                    f"condition {condition.condition_id}: focus groups offer "
                    f"different replicate indices "
                    f"({present[0]}={sorted(first)}, {fg}={sorted(index_sets[fg])}). "
                    f"Replicate k cannot be grouped across focus groups without "
                    f"inventing a pairing.")
    return True, ("every focus group in each condition offers the same replicate "
                  "indices; index k labels a position, NOT a shared seed")


def build_coverage(design: StudyDesign, assignments: list[TranscriptAssignment], *,
                   current_hashes: dict[str, str] | None = None,
                   known_transcript_ids=None,
                   eligibility: dict[str, dict] | None = None) -> CoverageReport:
    """
    Coverage of the declared design by the actual assignments.

    `current_hashes` maps transcript_id -> the canonical sha256 ON DISK NOW. Three
    outcomes are distinguished, because they are three different faults:

      MISSING   the assignment names a transcript that is no longer stored. The
                position is empty, not merely questionable.
      STALE     the transcript exists but its bytes changed after it was assigned.
      FRESH     the assignment still points at what it pointed at.

    `eligibility` maps transcript_id -> the window/result state from the services, so
    the report can say whether a position may enter a comparison and not only whether
    a file is present.
    """
    problems = validate_design(design)
    current_hashes = current_hashes or {}
    eligibility = eligibility or {}

    known_conditions = set(design.condition_ids)
    known_fgs = set(design.focus_group_ids)
    seen_transcripts: dict[str, int] = {}
    stale: list[str] = []
    missing: list[str] = []

    for a in assignments:
        seen_transcripts[a.transcript_id] = seen_transcripts.get(
            a.transcript_id, 0) + 1
        if a.condition_id not in known_conditions:
            problems.append(f"{a.transcript_id}: condition {a.condition_id!r} is not "
                            f"declared in the design")
            continue
        if a.focus_group_id not in known_fgs:
            problems.append(f"{a.transcript_id}: focus group {a.focus_group_id!r} is "
                            f"not declared in the design")
            continue
        condition = design.condition(a.condition_id)
        if a.role == Role.SYNTHETIC_RUN.value:
            if condition.side != Side.SYNTHETIC.value:
                problems.append(
                    f"{a.transcript_id}: assigned as a synthetic run to "
                    f"{a.condition_id!r}, which is declared {condition.side}")
            elif a.replicate_index is not None and not (
                    1 <= a.replicate_index <= condition.expected_replicates):
                problems.append(
                    f"{a.transcript_id}: replicate index {a.replicate_index} is "
                    f"outside 1..{condition.expected_replicates} for condition "
                    f"{a.condition_id!r}")
        elif a.role == Role.HUMAN_REFERENCE.value:
            if condition.side != Side.HUMAN.value:
                problems.append(
                    f"{a.transcript_id}: assigned as a human reference to "
                    f"{a.condition_id!r}, which is declared {condition.side}")
        else:
            problems.append(f"{a.transcript_id}: unknown role {a.role!r}")

        recorded = current_hashes.get(a.transcript_id)
        if recorded is None:
            missing.append(a.transcript_id)
            problems.append(
                f"{a.transcript_id} is assigned to "
                f"{a.condition_id}/{a.focus_group_id} but no canonical transcript "
                f"with that id is stored; the position is empty")
        elif recorded != a.canonical_sha256:
            stale.append(a.transcript_id)

    for transcript_id, count in sorted(seen_transcripts.items()):
        if count > 1:
            problems.append(
                f"{transcript_id} is assigned {count} times; one transcript occupies "
                f"one logical position")

    # ---- synthetic cells
    cells: list[CellCoverage] = []
    for condition in design.synthetic_conditions:
        for fg in design.focus_group_ids:
            mine = [a for a in assignments
                    if a.role == Role.SYNTHETIC_RUN.value
                    and a.condition_id == condition.condition_id
                    and a.focus_group_id == fg]
            by_index: dict[int | None, list[str]] = {}
            for a in mine:
                by_index.setdefault(a.replicate_index, []).append(a.transcript_id)
            duplicates = [{"replicate_index": k, "transcript_ids": sorted(v)}
                          for k, v in sorted(by_index.items(),
                                             key=lambda kv: (kv[0] is None, kv[0]))
                          if len(v) > 1]
            expected_indices = list(range(1, condition.expected_replicates + 1))
            # A position whose file has vanished is NOT present. Counting it would
            # report a full cell built on an absent transcript.
            present_indices = sorted(k for k, ids in by_index.items()
                                     if k is not None
                                     and any(i not in missing for i in ids))
            positions = [_position_state(a, current_hashes, eligibility)
                         for a in sorted(mine,
                                         key=lambda a: (a.replicate_index or 0,
                                                        a.transcript_id))]
            cells.append(CellCoverage(
                condition_id=condition.condition_id, focus_group_id=fg,
                expected=condition.expected_replicates,
                present=len(present_indices),
                replicate_indices_present=present_indices,
                missing_replicates=[k for k in expected_indices
                                    if k not in present_indices],
                duplicates=duplicates,
                stale_transcript_ids=[a.transcript_id for a in mine
                                      if a.transcript_id in stale],
                missing_transcript_ids=[a.transcript_id for a in mine
                                        if a.transcript_id in missing],
                transcript_ids=sorted(a.transcript_id for a in mine),
                positions=positions))

    # ---- human references
    human_by_fg: dict[str, list[str]] = {}
    for a in assignments:
        if a.role == Role.HUMAN_REFERENCE.value:
            human_by_fg.setdefault(a.focus_group_id, []).append(a.transcript_id)
    human_wanted = (design.human_reference_policy
                    in (HumanReferencePolicy.REQUIRED.value,
                        HumanReferencePolicy.OPTIONAL.value))
    missing_human = ([fg for fg in design.focus_group_ids if fg not in human_by_fg]
                     if human_wanted else [])
    duplicate_human = sorted(fg for fg, ids in human_by_fg.items() if len(ids) > 1)

    route_b, route_b_reason = route_b_availability(design, assignments)

    assigned = set(seen_transcripts)
    unassigned = sorted(set(known_transcript_ids or []) - assigned)

    status = _status(design, problems, assignments, cells, stale, missing_human,
                     duplicate_human)
    notes = []
    if status == DesignStatus.READY_FOR_DESCRIPTIVE.value and missing_human:
        notes.append("descriptive only: not every focus group has a human reference")
    if design.human_reference_policy == HumanReferencePolicy.NONE.value:
        notes.append("this design declares no human reference; results are "
                     "descriptive by construction")
    notes.append("no missing transcript is imputed; a gap reduces n and is listed")

    human_positions = [_position_state(a, current_hashes, eligibility)
                       for a in assignments
                       if a.role == Role.HUMAN_REFERENCE.value]
    fresh = sorted(set(seen_transcripts) - set(stale) - set(missing))

    return CoverageReport(
        design_id=design.design_id, status=status, problems=problems, cells=cells,
        human_by_focus_group={k: sorted(v) for k, v in sorted(human_by_fg.items())},
        missing_human_focus_groups=missing_human,
        duplicate_human_focus_groups=duplicate_human,
        stale_transcript_ids=sorted(set(stale)),
        missing_assigned_transcript_ids=sorted(set(missing)),
        fresh_transcript_ids=fresh,
        unassigned_transcript_ids=unassigned,
        human_positions=human_positions,
        route_b_available=route_b, route_b_reason=route_b_reason, notes=notes)


def _position_state(assignment: TranscriptAssignment,
                    current_hashes: dict[str, str],
                    eligibility: dict[str, dict]) -> PositionState:
    present = assignment.transcript_id in current_hashes
    info = eligibility.get(assignment.transcript_id, {})
    return PositionState(
        transcript_id=assignment.transcript_id,
        replicate_index=assignment.replicate_index,
        assigned=True,
        source_present=present,
        window_present=bool(info.get("window_present")),
        window_locked=bool(info.get("window_locked")),
        level2_fresh=bool(info.get("level2_fresh")),
        comparison_eligible=bool(info.get("comparison_eligible")),
        window_status=info.get("window_status", ""),
        namespace=info.get("namespace", ""),
        note=info.get("reason", "" if present else
                      "the canonical transcript is no longer stored"))


def _status(design, problems, assignments, cells, stale, missing_human,
            duplicate_human) -> str:
    if problems:
        return DesignStatus.INVALID.value
    if not assignments:
        return DesignStatus.EMPTY.value
    if stale:
        return DesignStatus.STALE.value

    synthetic_complete = bool(cells) and all(c.complete for c in cells)
    any_complete_cell = any(c.complete for c in cells)

    if synthetic_complete:
        wants_human = design.human_reference_policy == \
            HumanReferencePolicy.REQUIRED.value
        paired = design.matching_policy == MatchingPolicy.PAIRED_BY_FOCUS_GROUP.value
        human_ok = not missing_human and not duplicate_human
        if human_ok and paired and design.human_conditions:
            return DesignStatus.READY_FOR_MATCHED_COMPARISON.value
        if wants_human:
            return DesignStatus.INCOMPLETE.value
        return DesignStatus.READY_FOR_DESCRIPTIVE.value

    if any_complete_cell:
        return DesignStatus.INCOMPLETE.value
    return DesignStatus.PARTIAL.value


# ---------------------------------------------------------------- convenience
def simple_design(*, design_id: str, project_id: str, study_name: str,
                  n_focus_groups: int, synthetic_conditions: list[str],
                  replicates: int, with_human: bool = True,
                  created_utc: str = "") -> StudyDesign:
    """A rectangular design. The general case is built condition by condition."""
    conditions = [Condition(condition_id=c, label=c.replace("-", " ").title(),
                            side=Side.SYNTHETIC.value, expected_replicates=replicates)
                  for c in synthetic_conditions]
    if with_human:
        conditions.insert(0, Condition(condition_id="human", label="Human",
                                       side=Side.HUMAN.value, expected_replicates=1))
    return StudyDesign(
        design_id=design_id, project_id=project_id, study_name=study_name,
        conditions=conditions,
        focus_groups=[FocusGroup(focus_group_id=f"fg{i}", label=f"Focus group {i}")
                      for i in range(1, n_focus_groups + 1)],
        human_reference_policy=(HumanReferencePolicy.REQUIRED.value if with_human
                                else HumanReferencePolicy.NONE.value),
        matching_policy=(MatchingPolicy.PAIRED_BY_FOCUS_GROUP.value if with_human
                         else MatchingPolicy.NONE.value),
        created_utc=created_utc)
