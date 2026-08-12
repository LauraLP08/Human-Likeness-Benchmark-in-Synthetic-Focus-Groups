"""
Structural aggregation driven by a StudyDesign.

`aggregate.py` stays exactly as it is. It reproduces the frozen workbook, its tests
pin those numbers, and rewriting it to be general would put every frozen figure at
risk to gain a feature the thesis does not need. This module is the general engine;
the frozen path keeps its own.

The two are kept honest by a test: a StudyDesign of 5 focus groups x 2 synthetic
conditions x 3 replicates, fed the frozen per-run values, produces cell means
identical to `aggregate.aggregate_focus_group_condition`. Same arithmetic, reached
from a design instead of from three module constants.

The rules do not change because the corpus did:

  * a ratio is aggregated as the MEAN OF RUN RATIOS. Numerators and denominators are
    never summed across sessions - two runs of different length would otherwise let
    the longer one set the answer.
  * None reduces n. It never becomes 0.
  * every statistic carries the n it was computed over, and the n it expected.
  * no inferential test is performed, here or anywhere in this application.
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field

from .aggregate import AGGREGATION_RULE
from .design import (CoverageReport, Role, StudyDesign, TranscriptAssignment)

# The seven metrics the interface shows. The rest stay in the per-run results.
DISPLAY_METRIC_IDS = ("total_words", "participant_turns", "words_per_turn_iqr",
                      "short_turn_proportion_25w", "turn_balance_gini",
                      "chain_depth", "moderator_word_share")

MEAN_OF_RATIOS = ("mean of the run-level ratios; numerators and denominators are "
                  "never summed across sessions")
MEAN_OF_VALUES = "mean of the run-level values"


class EngineError(RuntimeError):
    pass


def aggregation_rule(metric_id: str) -> str:
    return AGGREGATION_RULE.get(metric_id, "mean_of_values")


def rule_description(metric_id: str) -> str:
    return (MEAN_OF_RATIOS if aggregation_rule(metric_id) == "ratio_no_pooling"
            else MEAN_OF_VALUES)


@dataclass
class Stat:
    """A descriptive statistic that always states what it was computed over."""

    values: list[float | None]
    n_valid: int
    n_expected: int
    mean: float | None = None
    median: float | None = None
    sd: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    undefined_reason: str | None = None

    @property
    def complete(self) -> bool:
        return self.n_valid == self.n_expected

    @property
    def range(self) -> float | None:
        if self.minimum is None or self.maximum is None:
            return None
        return self.maximum - self.minimum

    def to_dict(self) -> dict:
        d = asdict(self)
        d["range"] = self.range
        return d


def summarise(values, n_expected: int) -> Stat:
    valid = [v for v in values if v is not None]
    stat = Stat(values=list(values), n_valid=len(valid), n_expected=n_expected)
    if not valid:
        stat.undefined_reason = ("no valid value in this unit; undefined, not zero")
        return stat
    stat.mean = statistics.mean(valid)
    stat.median = statistics.median(valid)
    stat.sd = statistics.stdev(valid) if len(valid) > 1 else 0.0
    stat.minimum, stat.maximum = min(valid), max(valid)
    if len(valid) < n_expected:
        stat.undefined_reason = (
            f"{n_expected - len(valid)} value(s) undefined; computed over "
            f"n={len(valid)}, not imputed to n={n_expected}")
    return stat


# --------------------------------------------------------------- run results
@dataclass
class RunValue:
    """One metric, one transcript."""

    transcript_id: str
    metric_id: str
    value: float | None
    status: str = ""
    denominator: float | None = None
    denominator_definition: str = ""


def index_run_values(run_results: dict[str, list[dict]]) -> dict[str, dict[str, dict]]:
    """
    `{transcript_id: [row, ...]}` -> `{transcript_id: {metric_id: row}}`.

    Rows are whatever `structural_service` produced; only `metric_id`, `value`,
    `status` and the denominator fields are read.
    """
    out: dict[str, dict[str, dict]] = {}
    for transcript_id, rows in run_results.items():
        indexed: dict[str, dict] = {}
        for row in rows:
            metric_id = row.get("metric_id")
            if metric_id is None:
                continue
            if metric_id in indexed:
                raise EngineError(
                    f"{transcript_id}: metric {metric_id!r} appears twice in one run "
                    f"result; refusing to choose between them")
            indexed[metric_id] = row
        out[transcript_id] = indexed
    return out


def _value(indexed, transcript_id: str, metric_id: str):
    return (indexed.get(transcript_id) or {}).get(metric_id, {}).get("value")


# ------------------------------------------------------ route A: FG x condition
@dataclass
class CellResult:
    metric_id: str
    condition_id: str
    focus_group_id: str
    replicate_indices: list[int | None]
    transcript_ids: list[str]
    stat: Stat
    human_reference: float | None
    human_transcript_id: str | None
    n_expected: int
    coverage_status: str
    missing_replicates: list[int] = field(default_factory=list)
    aggregation_rule: str = ""
    aggregation_rule_description: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stat"] = self.stat.to_dict()
        return d


def aggregate_route_a(design: StudyDesign, assignments: list[TranscriptAssignment],
                      run_results: dict[str, list[dict]], *,
                      metric_ids=None,
                      coverage: CoverageReport | None = None) -> list[CellResult]:
    """
    ROUTE A - one cell per focus group x synthetic condition.

    The cell's n_expected comes from the DESIGN, not from how many transcripts turned
    up. A cell with two of three runs reports n=2 of 3, which is a different statement
    from a design that only ever wanted two.
    """
    metric_ids = tuple(metric_ids or DISPLAY_METRIC_IDS)
    indexed = index_run_values(run_results)

    humans: dict[str, TranscriptAssignment] = {}
    for a in assignments:
        if a.role == Role.HUMAN_REFERENCE.value:
            # A focus group with two human references has no defensible referent.
            humans[a.focus_group_id] = (None if a.focus_group_id in humans
                                        else a)

    out: list[CellResult] = []
    for condition in design.synthetic_conditions:
        indices = list(range(1, condition.expected_replicates + 1))
        for fg in design.focus_group_ids:
            mine = [a for a in assignments
                    if a.role == Role.SYNTHETIC_RUN.value
                    and a.condition_id == condition.condition_id
                    and a.focus_group_id == fg]
            by_index = {a.replicate_index: a for a in mine
                        if a.replicate_index is not None}
            missing = [k for k in indices if k not in by_index]
            human = humans.get(fg)

            for metric_id in metric_ids:
                values = [_value(indexed, by_index[k].transcript_id, metric_id)
                          if k in by_index else None for k in indices]
                stat = summarise(values, n_expected=len(indices))
                out.append(CellResult(
                    metric_id=metric_id, condition_id=condition.condition_id,
                    focus_group_id=fg,
                    replicate_indices=[k for k in indices if k in by_index],
                    transcript_ids=[by_index[k].transcript_id for k in indices
                                    if k in by_index],
                    stat=stat,
                    human_reference=(_value(indexed, human.transcript_id, metric_id)
                                     if human else None),
                    human_transcript_id=human.transcript_id if human else None,
                    n_expected=len(indices),
                    coverage_status=("COMPLETE" if stat.complete and not missing
                                     else "INCOMPLETE"),
                    missing_replicates=missing,
                    aggregation_rule=aggregation_rule(metric_id),
                    aggregation_rule_description=rule_description(metric_id)))
    return out


# --------------------------------------------------- route B: study replicates
@dataclass
class ReplicateResult:
    metric_id: str
    condition_id: str
    replicate_index: int
    focus_groups_included: list[str]
    transcript_ids: list[str]
    stat: Stat
    n_expected: int
    coverage_status: str
    missing_focus_groups: list[str] = field(default_factory=list)
    aggregation_rule: str = ""
    aggregation_rule_description: str = ""
    note: str = ("replicate k groups the run indexed k in each focus group. The index "
                 "labels a position in the design; it does NOT imply a shared seed "
                 "between focus groups, and the sessions of a condition are never "
                 "pooled as independent observations")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stat"] = self.stat.to_dict()
        return d


def aggregate_route_b(design: StudyDesign, assignments: list[TranscriptAssignment],
                      run_results: dict[str, list[dict]], *,
                      metric_ids=None,
                      coverage: CoverageReport | None = None
                      ) -> tuple[list[ReplicateResult], str]:
    """
    ROUTE B - replicate k across the focus groups.

    Refuses to run when the design's focus groups do not offer comparable indices,
    and says why. Returning an empty list with a reason is the point: a table built
    on an invented pairing would look exactly like a real one.
    """
    from .design import route_b_availability
    available, reason = route_b_availability(design, assignments)
    if not available:
        return [], reason

    metric_ids = tuple(metric_ids or DISPLAY_METRIC_IDS)
    indexed = index_run_values(run_results)

    out: list[ReplicateResult] = []
    for condition in design.synthetic_conditions:
        for k in range(1, condition.expected_replicates + 1):
            by_fg = {a.focus_group_id: a for a in assignments
                     if a.role == Role.SYNTHETIC_RUN.value
                     and a.condition_id == condition.condition_id
                     and a.replicate_index == k}
            missing = [fg for fg in design.focus_group_ids if fg not in by_fg]
            for metric_id in metric_ids:
                values = [_value(indexed, by_fg[fg].transcript_id, metric_id)
                          if fg in by_fg else None
                          for fg in design.focus_group_ids]
                stat = summarise(values, n_expected=len(design.focus_group_ids))
                out.append(ReplicateResult(
                    metric_id=metric_id, condition_id=condition.condition_id,
                    replicate_index=k,
                    focus_groups_included=[fg for fg in design.focus_group_ids
                                           if fg in by_fg],
                    transcript_ids=[by_fg[fg].transcript_id
                                    for fg in design.focus_group_ids if fg in by_fg],
                    stat=stat, n_expected=len(design.focus_group_ids),
                    coverage_status="COMPLETE" if stat.complete else "INCOMPLETE",
                    missing_focus_groups=missing,
                    aggregation_rule=aggregation_rule(metric_id),
                    aggregation_rule_description=rule_description(metric_id)))
    return out, reason


# ------------------------------------------------------------- condition level
@dataclass
class ConditionResult:
    metric_id: str
    condition_id: str
    route: str
    stat: Stat
    human_reference: Stat | None
    n_expected: int
    coverage_status: str
    aggregation_rule: str = ""
    aggregation_rule_description: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stat"] = self.stat.to_dict()
        d["human_reference"] = (self.human_reference.to_dict()
                                if self.human_reference else None)
        return d


def summarise_conditions(design: StudyDesign, cells: list[CellResult]
                         ) -> list[ConditionResult]:
    """Mean of the cell means across focus groups, with the human side beside it."""
    grouped: dict[tuple[str, str], list[CellResult]] = {}
    for c in cells:
        grouped.setdefault((c.metric_id, c.condition_id), []).append(c)

    out: list[ConditionResult] = []
    for (metric_id, condition_id), group in sorted(grouped.items()):
        group.sort(key=lambda c: c.focus_group_id)
        stat = summarise([c.stat.mean for c in group],
                         n_expected=len(design.focus_group_ids))
        human_values = [c.human_reference for c in group]
        human = (summarise(human_values, n_expected=len(design.focus_group_ids))
                 if any(v is not None for v in human_values) else None)
        out.append(ConditionResult(
            metric_id=metric_id, condition_id=condition_id, route="A",
            stat=stat, human_reference=human,
            n_expected=len(design.focus_group_ids),
            coverage_status="COMPLETE" if stat.complete else "INCOMPLETE",
            aggregation_rule=aggregation_rule(metric_id),
            aggregation_rule_description=rule_description(metric_id)))
    return out
