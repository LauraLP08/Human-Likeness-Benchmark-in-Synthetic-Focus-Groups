"""
Structural aggregation (Phase 2C, hardened in 2C.1).

TWO ROUTES, not one chain. "run -> focus group -> study replicate" reads as a single
ladder and is misleading: the two summaries answer different questions.

  Route A - FOCUS GROUP x CONDITION   three runs in one cell, against the paired human
  Route B - STUDY REPLICATE           run k of FG1..FG5; three replicates per condition

COVERAGE IS CHECKED PER METRIC. A metric is not complete because a *different* metric
has rows for that replicate - each metric_id is verified independently at
condition x focus_group x replicate_index x metric_id.

COVERAGE POLICY IS AN ARGUMENT, NOT A CONVENTION. Every public aggregator takes a
`policy` and applies it itself, so a caller cannot forget to run the integrity check
first. STRICT blocks on any duplicate, collision or gap; EXPLORATORY continues without
imputing and stamps `coverage_status`, `n_valid`, `n_expected` and `missing_units` on
every result. Reproducing the frozen results uses STRICT.

The replicate index is READ from the frozen results (`canonical_replication_index`),
never inferred from a run name: `macho_meals_fg4_run04` is replicate 2.

Rules that never bend:
  * the 15 sessions of a condition are never pooled as independent observations;
  * an undefined value stays null and reduces n; it never becomes zero;
  * every statistic reports the n it was computed over;
  * no inferential test is performed.
"""
from __future__ import annotations

import csv
import statistics
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from .config import REPO_ROOT

RESULTS = REPO_ROOT / "analysis" / "production_evaluation" / "results"
FROZEN_METRICS_CSV = RESULTS / "structural_interaction_metrics_long.csv"
FROZEN_DISTRIBUTIONS_CSV = RESULTS / "structural_distributions_long.csv"

FGS = ("fg1", "fg2", "fg3", "fg4", "fg5")
CONDITIONS = ("enriched", "demographics-only")
REPLICATES = (1, 2, 3)

# How each metric may be aggregated. Declared per metric; never inferred.
#   mean_of_values   a count or location statistic - the mean of the cell's values
#   ratio_no_pooling a proportion whose denominator differs between runs. The mean of
#                    the run-level proportions is reported AS A MEAN OF PROPORTIONS;
#                    numerators and denominators are never summed across runs.
AGGREGATION_RULE = {
    "participant_turns": "mean_of_values",
    "moderator_turns": "mean_of_values",
    "participant_words": "mean_of_values",
    "total_words": "mean_of_values",
    "words_per_turn_median": "mean_of_values",
    "words_per_turn_iqr": "mean_of_values",
    "chain_depth": "mean_of_values",
    "chain_depth_max": "mean_of_values",
    "chain_depth_n_chains": "mean_of_values",
    "turn_balance_gini": "mean_of_values",
    "word_balance_gini": "mean_of_values",
    "short_turn_proportion_25w": "ratio_no_pooling",
    "short_turn_proportion_10w": "ratio_no_pooling",
    "short_turn_proportion_50w": "ratio_no_pooling",
    "moderator_turn_share": "ratio_no_pooling",
    "moderator_word_share": "ratio_no_pooling",
    "participant_participant_adjacency": "ratio_no_pooling",
    "reference_density": "ratio_no_pooling",
}

DISTRIBUTION_IDS = ("words_per_turn", "participant_turn_counts",
                    "participant_word_counts", "chain_depth")

# FIXED bins for words_per_turn, never chosen from the corpus at hand. The first three
# edges are the registry's own short-turn thresholds (10, 25, 50), so the binned view
# and `short_turn_proportion_*` cannot disagree about where a boundary is; the upper
# three give the synthetic side, which piles up past 200 words, some resolution there.
# A corpus-dependent binning would make two runs incomparable, so this is a constant.
WORDS_PER_TURN_BINS = ((0, 10), (10, 25), (25, 50), (50, 100), (100, 200),
                       (200, 250), (250, 300), (300, None))


class CoveragePolicy(str, Enum):
    STRICT = "STRICT"
    EXPLORATORY = "EXPLORATORY"


class CalculationStatus(str, Enum):
    """
    Where a number stands epistemically. Stable identifiers; never inferred.

      FROZEN_REPRODUCED    an existing scalar, recomputed here and checked against a
                           golden source. The check is what earns the label.
      DERIVED_FROM_FROZEN  a NEW summary computed over frozen rows. The inputs are
                           frozen; the summary itself has no frozen counterpart and
                           is therefore verified against no external number.
      EXPLORATORY          the instrument or the interpretation is not validated.
    """

    FROZEN_REPRODUCED = "FROZEN_REPRODUCED"
    DERIVED_FROM_FROZEN = "DERIVED_FROM_FROZEN"
    EXPLORATORY = "EXPLORATORY"


# Bumped when an aggregation rule changes, so two artefacts can be told apart.
AGGREGATION_VERSION = "2C.1"

SOURCE_ARTIFACTS = {
    "structural_metrics": "analysis/production_evaluation/results/"
                          "structural_interaction_metrics_long.csv",
    "structural_distributions": "analysis/production_evaluation/results/"
                                "structural_distributions_long.csv",
    "final_workbook": "analysis/production_evaluation/final/"
                      "FINAL_RESULTS_TABLES.xlsx#3_Structural_Interaction",
}


def provenance(calculation_status: CalculationStatus, source_artifact: str,
               aggregation_rule: str) -> dict:
    """
    The four provenance fields carried by every result.

    `generated_utc` is deliberately absent: a timestamp inside a result makes the
    result non-deterministic and unusable in a test. It belongs to the OUTPUT
    ARTEFACT and is added once, by `stamp_output_artifact`, at write time.
    """
    return {"calculation_status": CalculationStatus(calculation_status).value,
            "source_artifact": source_artifact,
            "aggregation_version": AGGREGATION_VERSION,
            "aggregation_rule": aggregation_rule}


def stamp_output_artifact(payload: dict, generated_utc: str) -> dict:
    """Wrap results for writing. The clock touches the envelope, not the results."""
    return {"generated_utc": generated_utc,
            "aggregation_version": AGGREGATION_VERSION,
            "results": payload}


class CoverageStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    DUPLICATED = "DUPLICATED"


class AggregationError(RuntimeError):
    pass


class CoverageError(AggregationError):
    pass


# ------------------------------------------------------------------- helpers
@dataclass
class Summary:
    """A descriptive statistic that always carries the n it was computed over."""

    values: list[float | None]
    n_valid: int
    n_expected: int
    mean: float | None = None
    median: float | None = None
    sd: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    aggregation_rule: str = "mean_of_values"
    undefined_reason: str | None = None
    coverage_status: str = CoverageStatus.COMPLETE.value
    missing_units: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.n_valid == self.n_expected


def summarise(values: list[float | None], n_expected: int,
              rule: str = "mean_of_values",
              missing_units: list[str] | None = None) -> Summary:
    """Undefined stays undefined. A None reduces n; it is never read as 0."""
    valid = [v for v in values if v is not None]
    s = Summary(values=list(values), n_valid=len(valid), n_expected=n_expected,
                aggregation_rule=rule, missing_units=list(missing_units or []))
    if len(valid) < n_expected or s.missing_units:
        s.coverage_status = CoverageStatus.INCOMPLETE.value
    if not valid:
        s.undefined_reason = ("no valid value in this cell; the statistic is "
                              "undefined, not zero")
        return s
    s.mean = statistics.mean(valid)
    s.median = statistics.median(valid)
    s.sd = statistics.stdev(valid) if len(valid) > 1 else 0.0
    s.minimum, s.maximum = min(valid), max(valid)
    if len(valid) < n_expected:
        s.undefined_reason = (f"{n_expected - len(valid)} value(s) undefined; the "
                              f"statistic is computed over n={len(valid)}, not "
                              f"imputed to n={n_expected}")
    return s


# ------------------------------------------------------------ frozen loading
@dataclass
class RunRow:
    physical_run: str
    side: str
    condition: str
    fg: str
    replicate_index: int | None
    metric_id: str
    value: float | None


def load_frozen_metric_rows(path: Path | None = None) -> list[RunRow]:
    p = Path(path) if path else FROZEN_METRICS_CSV
    out: list[RunRow] = []
    for r in csv.DictReader(p.open(encoding="utf-8-sig")):
        raw = r["value"]
        k = r["canonical_replication_index"]
        out.append(RunRow(
            physical_run=r["physical_run"], side=r["side"],
            condition=r["condition"], fg=r["fg"],
            replicate_index=int(k) if k not in ("", "None") else None,
            metric_id=r["metric_id"],
            value=None if raw in ("", "None", "null") else float(raw)))
    return out


def replicate_index_map(rows: list[RunRow] | None = None) -> dict[str, int]:
    """physical_run -> study replicate index, READ from the frozen results."""
    rows = rows or load_frozen_metric_rows()
    out: dict[str, int] = {}
    for r in rows:
        if r.side == "synthetic" and r.replicate_index is not None:
            existing = out.get(r.physical_run)
            if existing is not None and existing != r.replicate_index:
                raise AggregationError(
                    f"{r.physical_run} carries two replicate indices "
                    f"({existing} and {r.replicate_index})")
            out[r.physical_run] = r.replicate_index
    return out


# --------------------------------------------------------------- integrity
@dataclass
class MetricCoverage:
    """
    Coverage on BOTH sides. A comparative metric with 30 flawless synthetic units and
    a missing human focus group is not covered - the comparison it exists to support
    cannot be made for that focus group.

    `cells_expected` / `cells_present` count the SYNTHETIC units only; the human side
    has its own four fields because "5 of 5 focus groups" and "30 of 30 runs" are
    different denominators and adding them together would hide which one failed.
    """

    metric_id: str
    cells_expected: int
    cells_present: int
    missing_units: list[str] = field(default_factory=list)
    duplicate_same_run: list[dict] = field(default_factory=list)
    collision_different_runs: list[dict] = field(default_factory=list)
    human_reference_required: bool = True
    human_fgs_expected: list[str] = field(default_factory=list)
    human_fgs_present: list[str] = field(default_factory=list)
    missing_human_fgs: list[str] = field(default_factory=list)
    undefined_human_fgs: list[str] = field(default_factory=list)
    human_duplicates: list[dict] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not (self.missing_units or self.duplicate_same_run
                    or self.collision_different_runs or self.human_duplicates
                    or self.missing_human_fgs or self.undefined_human_fgs)

    @property
    def status(self) -> str:
        if self.duplicate_same_run or self.collision_different_runs \
                or self.human_duplicates:
            return CoverageStatus.DUPLICATED.value
        if self.missing_units or self.missing_human_fgs or self.undefined_human_fgs:
            return CoverageStatus.INCOMPLETE.value
        return CoverageStatus.COMPLETE.value

    @property
    def human_n_expected(self) -> int:
        return len(self.human_fgs_expected)

    @property
    def human_n_valid(self) -> int:
        """Absent and undefined both reduce n. Neither becomes zero."""
        return len([f for f in self.human_fgs_present
                    if f not in self.undefined_human_fgs])


@dataclass
class CoverageReport:
    per_metric: dict[str, MetricCoverage] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return all(c.complete for c in self.per_metric.values())

    def incomplete_metrics(self) -> list[str]:
        return sorted(m for m, c in self.per_metric.items() if not c.complete)

    def for_metric(self, metric_id: str) -> MetricCoverage:
        try:
            return self.per_metric[metric_id]
        except KeyError:
            raise AggregationError(
                f"no coverage recorded for metric {metric_id!r}") from None

    def problems(self) -> list[str]:
        out: list[str] = []
        for metric_id in sorted(self.per_metric):
            c = self.per_metric[metric_id]
            if c.duplicate_same_run:
                out.append(f"{metric_id}: duplicate_same_run {c.duplicate_same_run}")
            if c.collision_different_runs:
                out.append(f"{metric_id}: collision_different_runs "
                           f"{c.collision_different_runs}")
            if c.human_duplicates:
                out.append(f"{metric_id}: human_duplicates {c.human_duplicates}")
            if c.missing_human_fgs:
                out.append(f"{metric_id}: missing_human_fgs {c.missing_human_fgs}")
            if c.undefined_human_fgs:
                out.append(f"{metric_id}: undefined_human_fgs "
                           f"{c.undefined_human_fgs}")
            if c.missing_units:
                out.append(f"{metric_id}: missing {c.missing_units}")
        return out


def _unit(condition: str, fg: str, k: int) -> str:
    return f"{condition}|{fg}|r{k}"


def _human_unit(fg: str) -> str:
    return f"human|{fg}"


def _requires_human(metric_id: str, spec) -> bool:
    """
    `spec` is None/True (every metric is comparative - the safe default), False (none
    are), or an explicit collection of the metric ids that are.
    """
    if spec is None or spec is True:
        return True
    if spec is False:
        return False
    return metric_id in set(spec)


def check_integrity(rows: list[RunRow], metric_ids=None, *,
                    human_reference_required=None) -> CoverageReport:
    """
    Coverage at condition x focus_group x replicate_index x metric_id, ON BOTH SIDES.

    A metric's completeness is decided from ITS OWN rows. Two distinct defects are
    reported separately because they mean different things:

      duplicate_same_run        the same physical run appears more than once in one
                                logical position - a loading or concatenation fault
      collision_different_runs  two different runs occupy one logical position - a
                                mapping fault, and the more dangerous of the two

    For a comparative metric STRICT requires all four of: 30 synthetic units, exactly
    one row per human focus group, no human duplicate, and a DEFINED human value in
    each of the five. Human rows are counted per (metric_id, fg); a repeat is recorded
    rather than silently overwriting a dictionary entry, and a repeated or null value
    lands in `undefined_human_fgs` - it never becomes zero.
    """
    metric_ids = tuple(metric_ids) if metric_ids else tuple(
        sorted({r.metric_id for r in rows}))

    synth: dict[str, dict[tuple[str, str, int], list[str]]] = {
        m: {} for m in metric_ids}
    human: dict[str, dict[str, list[float | None]]] = {m: {} for m in metric_ids}

    for r in rows:
        if r.metric_id not in synth:
            continue
        if r.side == "human":
            human[r.metric_id].setdefault(r.fg, []).append(r.value)
            continue
        if r.condition not in CONDITIONS:
            raise AggregationError(f"unknown condition {r.condition!r}")
        if r.fg not in FGS:
            raise AggregationError(f"unknown focus group {r.fg!r}")
        if r.replicate_index not in REPLICATES:
            raise AggregationError(
                f"{r.physical_run}: replicate index {r.replicate_index!r} outside "
                f"{list(REPLICATES)}")
        synth[r.metric_id].setdefault(
            (r.condition, r.fg, r.replicate_index), []).append(r.physical_run)

    report = CoverageReport()
    expected_units = [_unit(c, f, k) for c in CONDITIONS for f in FGS
                      for k in REPLICATES]

    for metric_id in metric_ids:
        cells = synth[metric_id]
        same_run, collisions = [], []
        for (condition, fg, k), runs in sorted(cells.items()):
            unique = sorted(set(runs))
            if len(runs) > len(unique):
                same_run.append({"unit": _unit(condition, fg, k),
                                 "run": unique[0], "n_rows": len(runs)})
            if len(unique) > 1:
                collisions.append({"unit": _unit(condition, fg, k), "runs": unique})

        present = {_unit(c, f, k) for (c, f, k) in cells}
        missing = [u for u in expected_units if u not in present]

        human_dupes = [{"fg": fg, "n_rows": len(vals)}
                       for fg, vals in sorted(human[metric_id].items())
                       if len(vals) > 1]

        needs_human = _requires_human(metric_id, human_reference_required)
        human_present = sorted(human[metric_id])
        missing_human, undefined_human = [], []
        if needs_human:
            missing_human = [f for f in FGS if f not in human[metric_id]]
            # A focus group whose only row is null, and one with two rows that cannot
            # be told apart, are both "no usable human reference here".
            undefined_human = [f for f in FGS
                               if f in human[metric_id]
                               and (len(human[metric_id][f]) > 1
                                    or human[metric_id][f][0] is None)]
            # Human gaps join the same missing_units list, so a caller that reads only
            # that list still sees them and still loses denominator.
            missing += [_human_unit(f) for f in missing_human + undefined_human]

        report.per_metric[metric_id] = MetricCoverage(
            metric_id=metric_id,
            cells_expected=len(expected_units),
            cells_present=len(present),
            missing_units=missing,
            duplicate_same_run=same_run,
            collision_different_runs=collisions,
            human_reference_required=needs_human,
            human_fgs_expected=list(FGS) if needs_human else [],
            human_fgs_present=human_present,
            missing_human_fgs=missing_human,
            undefined_human_fgs=sorted(undefined_human),
            human_duplicates=human_dupes,
        )
    return report


def _enforce(policy: CoveragePolicy, coverage: MetricCoverage) -> None:
    if policy is CoveragePolicy.STRICT and not coverage.complete:
        raise CoverageError(
            f"{coverage.metric_id}: STRICT policy blocks aggregation - status "
            f"{coverage.status}; duplicate_same_run={coverage.duplicate_same_run}; "
            f"collision_different_runs={coverage.collision_different_runs}; "
            f"human_duplicates={coverage.human_duplicates}; "
            f"missing_human_fgs={coverage.missing_human_fgs}; "
            f"undefined_human_fgs={coverage.undefined_human_fgs}; "
            f"missing={coverage.missing_units}")


def _human_values(rows: list[RunRow], metric_id: str) -> dict[str, float | None]:
    """One value per FG. A repeat is a coverage defect, not a silent overwrite."""
    seen: dict[str, list[float | None]] = {}
    for r in rows:
        if r.side == "human" and r.metric_id == metric_id:
            seen.setdefault(r.fg, []).append(r.value)
    out: dict[str, float | None] = {}
    for fg, vals in seen.items():
        out[fg] = vals[0] if len(vals) == 1 else None
    return out


# ------------------------------------------------------ route A: FG x condition
@dataclass
class CellSummary:
    metric_id: str
    condition: str
    focus_group: str
    runs: list[str]
    summary: Summary
    human_value: float | None
    aggregation_rule: str
    coverage_status: str
    missing_units: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["summary"] = asdict(self.summary)
        return d


def aggregate_focus_group_condition(rows: list[RunRow], metric_ids=None, *,
                                    policy: CoveragePolicy = CoveragePolicy.STRICT,
                                    coverage: CoverageReport | None = None,
                                    human_reference_required=None
                                    ) -> list[CellSummary]:
    metric_ids = tuple(metric_ids or sorted(AGGREGATION_RULE))
    coverage = coverage or check_integrity(
        rows, metric_ids, human_reference_required=human_reference_required)

    by_cell: dict[tuple[str, str, str], list[RunRow]] = {}
    for r in rows:
        if r.side == "synthetic" and r.metric_id in metric_ids:
            by_cell.setdefault((r.metric_id, r.condition, r.fg), []).append(r)

    out: list[CellSummary] = []
    for metric_id in metric_ids:
        cov = coverage.for_metric(metric_id)
        _enforce(policy, cov)
        human = _human_values(rows, metric_id)
        rule = AGGREGATION_RULE.get(metric_id, "mean_of_values")
        for condition in CONDITIONS:
            for fg in FGS:
                cell = sorted(by_cell.get((metric_id, condition, fg), []),
                              key=lambda r: (r.replicate_index or 0, r.physical_run))
                present = {r.replicate_index for r in cell}
                missing = [_unit(condition, fg, k) for k in REPLICATES
                           if k not in present]
                values = [next((r.value for r in cell if r.replicate_index == k),
                               None) for k in REPLICATES]
                s = summarise(values, n_expected=len(REPLICATES), rule=rule,
                              missing_units=missing)
                out.append(CellSummary(
                    metric_id=metric_id, condition=condition, focus_group=fg,
                    runs=[r.physical_run for r in cell], summary=s,
                    human_value=human.get(fg), aggregation_rule=rule,
                    coverage_status=s.coverage_status, missing_units=missing,
                    provenance=provenance(
                        CalculationStatus.FROZEN_REPRODUCED,
                        SOURCE_ARTIFACTS["structural_metrics"],
                        f"route_A_focus_group_x_condition/{rule}")))
    return out


# --------------------------------------------------- route B: study replicates
@dataclass
class StudyReplicate:
    metric_id: str
    condition: str
    replicate_index: int
    fgs_included: list[str]
    runs: list[str]
    summary: Summary
    coverage_status: str
    missing_units: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["summary"] = asdict(self.summary)
        return d


def aggregate_study_replicates(rows: list[RunRow], metric_ids=None, *,
                               policy: CoveragePolicy = CoveragePolicy.STRICT,
                               coverage: CoverageReport | None = None,
                               human_reference_required=None
                               ) -> list[StudyReplicate]:
    """
    Study replicate k = run k of FG1..FG5, one value per focus group.

    DERIVED_FROM_FROZEN, not FROZEN_REPRODUCED: the frozen workbook does not publish a
    structural study-replicate table, so there is no golden number to check this
    against. `study_replication_summary.csv` is thematic and is not a counterpart.
    """
    metric_ids = tuple(metric_ids or sorted(AGGREGATION_RULE))
    coverage = coverage or check_integrity(
        rows, metric_ids, human_reference_required=human_reference_required)

    grouped: dict[tuple[str, str, int], list[RunRow]] = {}
    for r in rows:
        if r.side == "synthetic" and r.metric_id in metric_ids:
            grouped.setdefault((r.metric_id, r.condition, r.replicate_index),
                               []).append(r)

    out: list[StudyReplicate] = []
    for metric_id in metric_ids:
        cov = coverage.for_metric(metric_id)
        _enforce(policy, cov)
        rule = AGGREGATION_RULE.get(metric_id, "mean_of_values")
        for condition in CONDITIONS:
            for k in REPLICATES:
                group = sorted(grouped.get((metric_id, condition, k), []),
                               key=lambda r: r.fg)
                by_fg = {r.fg: r for r in group}
                missing = [_unit(condition, f, k) for f in FGS if f not in by_fg]
                values = [by_fg[f].value if f in by_fg else None for f in FGS]
                s = summarise(values, n_expected=len(FGS), rule=rule,
                              missing_units=missing)
                out.append(StudyReplicate(
                    metric_id=metric_id, condition=condition, replicate_index=k,
                    fgs_included=[f for f in FGS if f in by_fg],
                    runs=[by_fg[f].physical_run for f in FGS if f in by_fg],
                    summary=s, coverage_status=s.coverage_status,
                    missing_units=missing,
                    provenance=provenance(
                        CalculationStatus.DERIVED_FROM_FROZEN,
                        SOURCE_ARTIFACTS["structural_metrics"],
                        f"route_B_study_replicate/{rule}")))
    return out


@dataclass
class StudyLevelSummary:
    metric_id: str
    condition: str
    replicate_means: list[float | None]
    across_replicates: Summary
    human_reference: Summary
    coverage_status: str
    missing_units: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    note: str = ("the three study replicates are summarised descriptively; they are "
                 "independent realisations, not paired seeds, and are never pooled "
                 "as 15 independent sessions")

    def to_dict(self) -> dict:
        return {"metric_id": self.metric_id, "condition": self.condition,
                "replicate_means": self.replicate_means,
                "across_replicates": asdict(self.across_replicates),
                "human_reference": asdict(self.human_reference),
                "coverage_status": self.coverage_status,
                "missing_units": self.missing_units,
                "provenance": self.provenance, "note": self.note}


def summarise_study_level(rows: list[RunRow], metric_ids=None, *,
                          policy: CoveragePolicy = CoveragePolicy.STRICT,
                          coverage: CoverageReport | None = None,
                          human_reference_required=None
                          ) -> list[StudyLevelSummary]:
    metric_ids = tuple(metric_ids or sorted(AGGREGATION_RULE))
    coverage = coverage or check_integrity(
        rows, metric_ids, human_reference_required=human_reference_required)
    replicates = aggregate_study_replicates(rows, metric_ids, policy=policy,
                                            coverage=coverage)

    out: list[StudyLevelSummary] = []
    for metric_id in metric_ids:
        cov = coverage.for_metric(metric_id)
        human = _human_values(rows, metric_id)
        # An absent or ambiguous human focus group reduces the human n; it is listed,
        # not filled in.
        human_missing = [_human_unit(f) for f in cov.missing_human_fgs
                         + cov.undefined_human_fgs]
        for condition in CONDITIONS:
            mine = sorted((sr for sr in replicates
                           if sr.metric_id == metric_id
                           and sr.condition == condition),
                          key=lambda s: s.replicate_index)
            means = [sr.summary.mean for sr in mine]
            missing = sorted({u for sr in mine for u in sr.missing_units}
                             | set(human_missing))
            across = summarise(means, n_expected=len(REPLICATES),
                               missing_units=[u for u in missing
                                              if not u.startswith("human|")])
            out.append(StudyLevelSummary(
                metric_id=metric_id, condition=condition, replicate_means=means,
                across_replicates=across,
                human_reference=summarise(
                    [human.get(f) for f in FGS], n_expected=len(FGS),
                    missing_units=sorted(human_missing)),
                coverage_status=cov.status, missing_units=missing,
                provenance=provenance(
                    CalculationStatus.DERIVED_FROM_FROZEN,
                    SOURCE_ARTIFACTS["structural_metrics"],
                    "route_B_study_replicate/mean_across_replicates")))
    return out


# ------------------------------------------- the frozen workbook's own route
def frozen_workbook_route(rows: list[RunRow], metric_ids, *,
                          policy: CoveragePolicy = CoveragePolicy.STRICT,
                          coverage: CoverageReport | None = None,
                          human_reference_required=None) -> list[dict]:
    """
    Reproduce `FINAL_RESULTS_TABLES.xlsx` sheet `3_Structural_Interaction`.

    That sheet takes the mean of the three runs in each FG x condition cell, then the
    mean of the five cell means (`scripts/build_final_products.py::structural`). Route
    B is a different, also specified, summary - reported separately, not reconciled.
    """
    metric_ids = tuple(metric_ids)
    coverage = coverage or check_integrity(
        rows, metric_ids, human_reference_required=human_reference_required)
    cells = aggregate_focus_group_condition(rows, metric_ids, policy=policy,
                                            coverage=coverage)

    out = []
    for metric_id in metric_ids:
        cov = coverage.for_metric(metric_id)
        _enforce(policy, cov)
        human = _human_values(rows, metric_id)
        h = [human[f] for f in FGS if human.get(f) is not None]
        e = [c.summary.mean for c in cells
             if c.metric_id == metric_id and c.condition == "enriched"
             and c.summary.mean is not None]
        d = [c.summary.mean for c in cells
             if c.metric_id == metric_id and c.condition == "demographics-only"
             and c.summary.mean is not None]
        if not (h and e and d):
            continue
        closer = sum(1 for i in range(min(len(h), len(e), len(d)))
                     if abs(e[i] - h[i]) < abs(d[i] - h[i]))
        out.append({
            "metric": metric_id,
            "human_mean": statistics.mean(h),
            "enriched_mean": statistics.mean(e),
            "demographics_only_mean": statistics.mean(d),
            "enriched_minus_demo": statistics.mean(e) - statistics.mean(d),
            "n_fg_enriched_closer_to_human": f"{closer}/5",
            "n_fgs": len(h),
            "coverage_status": cov.status,
            "missing_units": cov.missing_units,
            # The only route in this module with an external number to be wrong
            # against: sheet `3_Structural_Interaction` of the frozen workbook.
            **provenance(CalculationStatus.FROZEN_REPRODUCED,
                         SOURCE_ARTIFACTS["final_workbook"],
                         "mean_of_three_runs_then_mean_of_five_cell_means"),
        })
    return out


# =============================================================== distributions
def load_frozen_distributions(path: Path | None = None) -> list[dict]:
    p = Path(path) if path else FROZEN_DISTRIBUTIONS_CSV
    return list(csv.DictReader(p.open(encoding="utf-8-sig")))


def _by_run(rows: list[dict], distribution_id: str, side: str
            ) -> tuple[dict[str, list[float]], dict[str, tuple[str, str]]]:
    buckets: dict[str, list[float]] = {}
    meta: dict[str, tuple[str, str]] = {}
    for r in rows:
        if r["distribution_id"] != distribution_id or r["side"] != side:
            continue
        key = r["physical_run"] if side == "synthetic" else r["fg"]
        buckets.setdefault(key, []).append(float(r["value"]))
        meta[key] = (r["condition"] or "human", r["fg"])
    return buckets, meta


def _across_cells(per_run: dict[str, float], meta: dict[str, tuple[str, str]]
                  ) -> tuple[dict[str, dict], dict[str, dict]]:
    per_cell: dict[tuple[str, str], list[float]] = {}
    for run, value in per_run.items():
        per_cell.setdefault(meta[run], []).append(value)
    cell_out = {f"{c}|{f}": {"mean": round(statistics.mean(v), 6), "n_runs": len(v)}
                for (c, f), v in sorted(per_cell.items())}

    per_condition: dict[str, list[float]] = {}
    for (condition, _fg), v in per_cell.items():
        per_condition.setdefault(condition, []).append(statistics.mean(v))
    cond_out = {}
    for c, v in sorted(per_condition.items()):
        cond_out[c] = {"mean_of_cell_means": round(statistics.mean(v), 6),
                       "sd_across_focus_groups": (round(statistics.stdev(v), 6)
                                                  if len(v) > 1 else 0.0),
                       "n_focus_groups": len(v)}
    return cell_out, cond_out


def summarise_distribution_location(rows: list[dict], distribution_id: str,
                                    statistic=statistics.median) -> dict:
    """
    A LOCATION summary only - one statistic per run, then per cell, then per FG.

    It is deliberately NOT a reproduction of the distribution: reducing a vector to a
    median discards its shape. Use `aggregate_words_per_turn` for a binned view,
    `aggregate_participant_counts` for the per-participant vectors and
    `aggregate_chain_depth` for depth. Named `_location` so no caller can mistake it
    for the distribution itself.
    """
    buckets, meta = _by_run(rows, distribution_id, "synthetic")
    per_run = {run: statistic(v) for run, v in buckets.items()}
    cells, conditions = _across_cells(per_run, meta)
    return {
        "distribution_id": distribution_id,
        **provenance(CalculationStatus.DERIVED_FROM_FROZEN,
                     SOURCE_ARTIFACTS["structural_distributions"],
                     "location_statistic_within_run_then_unweighted_mean_by_focus_"
                     "group_then_condition"),
        "what_this_is": ("a location statistic per run, aggregated; NOT the "
                         "distribution's shape"),
        "statistic": getattr(statistic, "__name__", str(statistic)),
        "step_1_within_run": {k: round(v, 6) for k, v in sorted(per_run.items())},
        "step_2_within_cell": cells,
        "step_3_across_focus_groups": conditions,
        "rule": ("computed inside each run, then across the runs of a cell, then "
                 "across the five focus groups; never pooled across the 15 sessions "
                 "of a condition"),
    }


QUARTILE_METHOD = "inclusive"
QUARTILE_METHOD_NOTE = (
    "linear interpolation between the closest ranks of the sample itself "
    "(statistics.quantiles method='inclusive', the R type-7 / numpy default). Chosen "
    "because it never extrapolates: every quartile lies inside the observed min-max, "
    "which the 'exclusive' method does not guarantee on the short vectors a single "
    "run can produce. n=1 has no spread to estimate, so the IQR is UNDEFINED (None) "
    "rather than 0 - a zero would read as 'no dispersion observed', which is a "
    "claim the single value does not support.")


def quartiles(values: list[float]) -> tuple[float | None, float | None,
                                            float | None]:
    """(q1, q3, iqr) by the inclusive method. n<2 -> undefined, never zero."""
    if len(values) < 2:
        return None, None, None
    q = statistics.quantiles(values, n=4, method=QUARTILE_METHOD)
    return q[0], q[2], q[2] - q[0]


def _bin_label(lo: int, hi: int | None) -> str:
    return f"{lo}-{hi - 1}w" if hi is not None else f"{lo}w+"


def _bin_percentages(values: list[float]) -> dict[str, float]:
    n = len(values)
    out: dict[str, float] = {}
    for lo, hi in WORDS_PER_TURN_BINS:
        hits = sum(1 for v in values
                   if v >= lo and (hi is None or v < hi))
        out[_bin_label(lo, hi)] = (hits / n) if n else 0.0
    return out


def aggregate_words_per_turn(rows: list[dict] | None = None) -> dict:
    """
    Binned words-per-turn, run -> focus group -> condition.

    Percentages are computed INSIDE each run, so a run with three times the turns
    carries the same weight as any other. Pooling the turns of 15 sessions would let
    the longest session dominate; a test plants exactly that and asserts it does not.
    """
    rows = rows if rows is not None else load_frozen_distributions()
    labels = [_bin_label(lo, hi) for lo, hi in WORDS_PER_TURN_BINS]

    def side_view(side: str) -> dict:
        buckets, meta = _by_run(rows, "words_per_turn", side)
        per_run = {run: _bin_percentages(v) for run, v in buckets.items()}
        turns_per_run = {run: len(v) for run, v in buckets.items()}

        per_cell: dict[tuple[str, str], list[dict[str, float]]] = {}
        for run, pct in per_run.items():
            per_cell.setdefault(meta[run], []).append(pct)

        # NOT rounded. These percentages must sum to 1 exactly at every level, and a
        # rounded intermediate breaks that invariant - rounding is a presentation
        # concern and belongs to the caller.
        cell_view = {
            f"{c}|{f}": {
                "bins": {lab: statistics.mean([p[lab] for p in ps])
                         for lab in labels},
                "n_runs": len(ps)}
            for (c, f), ps in sorted(per_cell.items())}

        per_condition: dict[str, list[dict[str, float]]] = {}
        for (c, _f), ps in per_cell.items():
            per_condition.setdefault(c, []).append(
                {lab: statistics.mean([p[lab] for p in ps]) for lab in labels})

        cond_view = {}
        for c, cells in sorted(per_condition.items()):
            cond_view[c] = {
                "bins": {lab: {
                    "mean_percent": statistics.mean(
                        [cell[lab] for cell in cells]),
                    "sd_across_focus_groups": (statistics.stdev(
                        [cell[lab] for cell in cells]) if len(cells) > 1
                        else 0.0),
                    "n_focus_groups": len(cells)} for lab in labels},
                "n_focus_groups": len(cells)}
        return {"per_run": {k: {lab: v[lab] for lab in labels}
                            for k, v in sorted(per_run.items())},
                "turns_per_run": dict(sorted(turns_per_run.items())),
                "per_cell": cell_view, "per_condition": cond_view}

    return {
        "distribution_id": "words_per_turn",
        **provenance(CalculationStatus.DERIVED_FROM_FROZEN,
                     SOURCE_ARTIFACTS["structural_distributions"],
                     "binned_within_run_then_unweighted_mean_by_focus_group_then_"
                     "condition"),
        "bins": labels,
        "bins_are_fixed": ("the bin edges are a module constant and are never chosen "
                           "from the corpus being summarised"),
        "original_unit": "one participant turn",
        "within_run_transformation": ("percentage of that run's participant turns "
                                      "falling in each bin; the percentages sum to 1"),
        "within_focus_group_aggregation": ("unweighted mean of the run percentages "
                                           "across the runs of the cell"),
        "across_focus_group_aggregation": ("unweighted mean of the cell percentages "
                                           "across the five focus groups, with the "
                                           "standard deviation across focus groups"),
        "denominators": {"within_run": "participant turns in that run",
                         "within_focus_group": "runs in the cell (3)",
                         "across_focus_groups": "focus groups (5)"},
        "statistics": ["mean_percent", "sd_across_focus_groups", "n_focus_groups"],
        "synthetic": side_view("synthetic"),
        "human_reference": side_view("human"),
        "human_reference_rule": ("computed inside each human focus group first, then "
                                 "across the five focus groups - the same ladder as "
                                 "the synthetic side"),
    }


def _gini(values: list[float]) -> float | None:
    if not values or len(values) < 2:
        return None
    s = sorted(values)
    n, total = len(s), sum(s)
    if total == 0:
        return None
    cum = sum((i + 1) * v for i, v in enumerate(s))
    return (2 * cum) / (n * total) - (n + 1) / n


def aggregate_participant_counts(distribution_id: str,
                                 rows: list[dict] | None = None) -> dict:
    """
    Per-participant vectors (`participant_turn_counts`, `participant_word_counts`).

    DELIBERATELY NOT the words_per_turn rule. These vectors have one element per
    participant, and their question is concentration, not shape over a value axis:
    binning a five-element vector would be noise.

    The AGGREGATED result is the Gini coefficient, computed inside the run so that a
    group with more participants does not dilute one with fewer. The min/median/max of
    each participant's SHARE are PER-RUN DIAGNOSTICS ONLY - kept beside their run and
    deliberately not carried up to focus group or condition, because a mean of five
    "share of the most talkative participant" values is not itself a share of
    anything. They sit under `per_run_diagnostics` so the output cannot be read as if
    they had been aggregated.
    """
    if distribution_id not in ("participant_turn_counts",
                               "participant_word_counts"):
        raise AggregationError(
            f"{distribution_id} is not a per-participant vector; use "
            f"aggregate_words_per_turn or aggregate_chain_depth")
    rows = rows if rows is not None else load_frozen_distributions()

    def side_view(side: str) -> dict:
        buckets, meta = _by_run(rows, distribution_id, side)
        per_run = {}
        for run, values in buckets.items():
            total = sum(values)
            shares = sorted((v / total) for v in values) if total else []
            per_run[run] = {
                "n_participants": len(values),
                "gini": (round(g, 6) if (g := _gini(values)) is not None else None),
                "per_run_diagnostics": {
                    "share_min": round(shares[0], 6) if shares else None,
                    "share_median": (round(statistics.median(shares), 6) if shares
                                     else None),
                    "share_max": round(shares[-1], 6) if shares else None,
                },
            }
        gini_by_run = {r: v["gini"] for r, v in per_run.items()
                       if v["gini"] is not None}
        cells, conditions = _across_cells(gini_by_run, meta)
        return {"per_run": dict(sorted(per_run.items())),
                "gini_per_cell": cells, "gini_per_condition": conditions}

    return {
        "distribution_id": distribution_id,
        **provenance(CalculationStatus.DERIVED_FROM_FROZEN,
                     SOURCE_ARTIFACTS["structural_distributions"],
                     "gini_within_run_then_unweighted_mean_by_focus_group_then_"
                     "condition"),
        "original_unit": "one participant within one run",
        "within_run_transformation": ("Gini coefficient over the per-participant "
                                      "vector; the min/median/max of each "
                                      "participant's share are also computed but are "
                                      "retained as per-run diagnostics"),
        "within_focus_group_aggregation": "unweighted mean of the run Gini values",
        "across_focus_group_aggregation": ("unweighted mean of the cell means, with "
                                           "the standard deviation across focus "
                                           "groups"),
        "denominators": {"within_run": "participants in that run",
                         "within_focus_group": "runs in the cell (3)",
                         "across_focus_groups": "focus groups (5)"},
        "statistics": ["gini"],
        "aggregated_statistics": ["gini"],
        "per_run_diagnostics": ["share_min", "share_median", "share_max"],
        "per_run_diagnostics_note": ("these three are reported per run only. They are "
                                     "NOT aggregated to focus group or condition: the "
                                     "mean of five maxima is not a share, and "
                                     "labelling it as one would overstate what was "
                                     "computed"),
        "why_not_bins": ("a per-participant vector has one element per participant; "
                         "binning it would describe group size, not concentration"),
        "synthetic": side_view("synthetic"),
        "human_reference": side_view("human"),
    }


def aggregate_chain_depth(rows: list[dict] | None = None) -> dict:
    """
    Chain-depth distribution: median, IQR and maximum are kept per run BEFORE any
    aggregation, because the registry requires the distribution and the maximum, not
    the mean alone. A maximum averaged away is a maximum lost.
    """
    rows = rows if rows is not None else load_frozen_distributions()

    def side_view(side: str) -> dict:
        buckets, meta = _by_run(rows, "chain_depth", side)
        per_run = {}
        for run, values in buckets.items():
            q1, q3, iqr = quartiles(values)
            per_run[run] = {
                "n_chains": len(values),
                "median": round(statistics.median(values), 6),
                "q1": round(q1, 6) if q1 is not None else None,
                "q3": round(q3, 6) if q3 is not None else None,
                "iqr": round(iqr, 6) if iqr is not None else None,
                "iqr_undefined_reason": (None if iqr is not None else
                                         "n=1: a single chain has no spread to "
                                         "estimate; undefined, not zero"),
                "maximum": max(values),
                "mean": round(statistics.mean(values), 6),
            }
        out = {}
        for stat in ("median", "iqr", "maximum", "mean"):
            # A run whose IQR is undefined drops out of the mean and reduces n; it is
            # never read as a zero-spread run.
            per_run_stat = {r: v[stat] for r, v in per_run.items()
                            if v[stat] is not None}
            cells, conditions = _across_cells(per_run_stat, meta)
            out[stat] = {"per_cell": cells, "per_condition": conditions,
                         "n_runs_contributing": len(per_run_stat),
                         "n_runs_undefined": len(per_run) - len(per_run_stat)}
        return {"per_run": dict(sorted(per_run.items())), "aggregated": out}

    return {
        "distribution_id": "chain_depth",
        **provenance(CalculationStatus.DERIVED_FROM_FROZEN,
                     SOURCE_ARTIFACTS["structural_distributions"],
                     "median_iqr_max_mean_within_run_then_unweighted_mean_by_focus_"
                     "group_then_condition"),
        "original_unit": "one uninterrupted participant-to-participant chain",
        "within_run_transformation": ("median, IQR, maximum and mean of the chain "
                                      "lengths in that run; all four are retained "
                                      "before aggregation"),
        "quartile_method": QUARTILE_METHOD,
        "quartile_method_note": QUARTILE_METHOD_NOTE,
        "within_focus_group_aggregation": ("unweighted mean of each run statistic "
                                           "across the runs of the cell"),
        "across_focus_group_aggregation": ("unweighted mean of the cell means, with "
                                           "the standard deviation across focus "
                                           "groups"),
        "denominators": {"within_run": "chains in that run",
                         "within_focus_group": "runs in the cell (3)",
                         "across_focus_groups": "focus groups (5)"},
        "statistics": ["median", "iqr", "maximum", "mean"],
        "note": ("the maximum is aggregated as a mean OF MAXIMA and is labelled as "
                 "such; it is not the maximum of the pooled corpus"),
        "synthetic": side_view("synthetic"),
        "human_reference": side_view("human"),
    }


DISTRIBUTION_AGGREGATORS = {
    "words_per_turn": aggregate_words_per_turn,
    "participant_turn_counts": lambda rows=None: aggregate_participant_counts(
        "participant_turn_counts", rows),
    "participant_word_counts": lambda rows=None: aggregate_participant_counts(
        "participant_word_counts", rows),
    "chain_depth": aggregate_chain_depth,
}
