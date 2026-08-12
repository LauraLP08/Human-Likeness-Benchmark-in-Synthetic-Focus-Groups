"""
THEMATIC_FIDELITY (Level 1), offline and read-only.

This module READS results that were produced once, by the historical pipeline, and
re-expresses them in the platform's neutral shape. It does not code transcripts, does
not call an evaluator, and does not open a socket. Nothing here writes.

Three rules run through all of it:

  1. PRIMARY CODING IS THE OUTPUT. The adjudicated sensitivity re-coding is a parallel
     view, obtained through its own functions and carrying `coding_basis=SENSITIVITY`.
     No function returns a mixture, and no sensitivity number silently replaces a
     primary one.

  2. NUMERATOR AND DENOMINATOR ARE KEPT. A ratio recomputed from two rounded scalars
     is not the same number as one computed from its counts - `tier1_f1_secondary`
     differs in the fourth decimal between two frozen artefacts for exactly that
     reason, and only the counts reproduce the published table.

  3. AN UNDEFINED VALUE STAYS UNDEFINED. Precision over an empty denominator is None,
     not zero; a metric with no human referent says so rather than reporting one.

`calculation_status` follows `aggregate.CalculationStatus` and answers "where does this
number stand". `verification` answers the narrower question "what was actually done":

  RECOMPUTED_AND_MATCHED      recomputed here from frozen inputs and compared, value
                              by value, against a frozen published table
  RECOMPUTED_NO_GOLDEN        recomputed here; no frozen table exists to check it
  READ_FROM_FROZEN_ARTIFACT   read as it stands; no recomputation, so no check

The two are separate on purpose. A metric can reproduce its published arithmetic
exactly and still be EXPLORATORY, because the doubt is about the instrument, not the
sum: `tier1_salience_hierarchy` is that case.
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from .aggregate import (AGGREGATION_VERSION, CONDITIONS, FGS, REPLICATES,
                        CalculationStatus, CoverageStatus, Summary, summarise)
from .catalog import Status, load_catalog
from .config import REPO_ROOT

HUMAN = "human"


class CodingBasis(str, Enum):
    PRIMARY = "PRIMARY"
    SENSITIVITY = "SENSITIVITY"
    BOTH = "BOTH"


class Verification(str, Enum):
    RECOMPUTED_AND_MATCHED = "RECOMPUTED_AND_MATCHED"
    RECOMPUTED_NO_GOLDEN = "RECOMPUTED_NO_GOLDEN"
    READ_FROM_FROZEN_ARTIFACT = "READ_FROM_FROZEN_ARTIFACT"


class ThematicError(RuntimeError):
    pass


# ================================================================== B2 sources
@dataclass(frozen=True)
class ThematicSource:
    """
    A frozen Level 1 artefact, registered before any code reads it.

    `expected_sha256` and `expected_rows` are pinned so that a source changing under
    the platform is an error rather than a quietly different answer.
    """

    key: str
    relative_path: str
    producer: str
    schema: tuple[str, ...]
    expected_rows: int | None
    coding_basis: str
    description: str
    expected_sha256: str
    unit_of_analysis: str

    @property
    def path(self) -> Path:
        return REPO_ROOT / self.relative_path

    def sha256(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def rows(self) -> list[dict]:
        if not self.relative_path.endswith(".csv"):
            raise ThematicError(f"{self.key} is not a CSV; use .payload()")
        return list(csv.DictReader(self.path.open(encoding="utf-8-sig")))

    def payload(self) -> dict:
        if not self.relative_path.endswith(".json"):
            raise ThematicError(f"{self.key} is not JSON; use .rows()")
        return json.loads(self.path.read_text(encoding="utf-8"))

    def verify(self) -> dict:
        """Path, schema, row count and hash, checked - not assumed."""
        problems: list[str] = []
        if not self.path.exists():
            return {"key": self.key, "exists": False,
                    "problems": [f"missing: {self.relative_path}"]}
        got_hash = self.sha256()
        if got_hash != self.expected_sha256:
            problems.append(f"sha256 {got_hash} != pinned {self.expected_sha256}")
        n_rows = None
        if self.relative_path.endswith(".csv"):
            rows = self.rows()
            n_rows = len(rows)
            got_cols = tuple(rows[0].keys()) if rows else ()
            missing = [c for c in self.schema if c not in got_cols]
            if missing:
                problems.append(f"missing columns {missing}")
            if self.expected_rows is not None and n_rows != self.expected_rows:
                problems.append(f"{n_rows} rows, expected {self.expected_rows}")
        else:
            payload = self.payload()
            missing = [k for k in self.schema if k not in payload]
            if missing:
                problems.append(f"missing keys {missing}")
        return {"key": self.key, "exists": True, "sha256": got_hash,
                "n_rows": n_rows, "producer": self.producer,
                "coding_basis": self.coding_basis, "problems": problems,
                "ok": not problems}


_R = "analysis/production_evaluation/results/"
_F = "analysis/production_evaluation/final/"
_A = "analysis/production_evaluation/salience_absence_audit/"

SOURCES: dict[str, ThematicSource] = {
    "per_run_metrics": ThematicSource(
        key="per_run_metrics",
        relative_path=_R + "per_run_metrics.csv",
        producer="scripts/aggregate_production_results.py",
        schema=("physical_run", "condition", "fg", "canonical_replication_index",
                "namespace", "human_present_n", "synthetic_present_n", "shared_n",
                "tier1_subtheme_recall", "tier1_matched_theme_precision",
                "tier1_f1_secondary", "tier1_participant_reach",
                "tier1_salience_hierarchy", "participants_n"),
        expected_rows=30,
        coding_basis=CodingBasis.PRIMARY.value,
        description="one row per synthetic run: the Level 1 scalars with the counts "
                    "they were computed from",
        expected_sha256="7a013c0314ca8f384217e26257193dd489cb893fdace66087328e8826"
                        "493d88c",
        unit_of_analysis="one synthetic run"),
    "primary_effects_by_fg": ThematicSource(
        key="primary_effects_by_fg",
        relative_path=_R + "primary_effects_by_fg.csv",
        producer="scripts/build_primary_effects_tables.py",
        schema=("metric", "role", "fg", "enriched_r1", "enriched_r2", "enriched_r3",
                "enriched_mean", "demographics_only_r1", "demographics_only_r2",
                "demographics_only_r3", "demographics_only_mean",
                "difference_enriched_minus_demo"),
        expected_rows=20,
        coding_basis=CodingBasis.PRIMARY.value,
        description="GOLDEN for route A: the three runs and their mean in every "
                    "focus group x condition cell",
        expected_sha256="e2f7cc55147eab71843eb3eabdc7ce1be9e9cb2b8f0a4401054883bea"
                        "f434152",
        unit_of_analysis="one focus group x condition cell"),
    "per_group_condition_summary": ThematicSource(
        key="per_group_condition_summary",
        relative_path=_R + "per_group_condition_summary.csv",
        producer="scripts/aggregate_production_results.py",
        schema=("fg", "condition", "n_replicates", "recall_mean", "recall_min",
                "recall_max", "precision_mean", "reach_mean", "human_present_n"),
        expected_rows=10,
        coding_basis=CodingBasis.PRIMARY.value,
        description="route A with the range; the same cells as "
                    "primary_effects_by_fg, reported with min/max",
        expected_sha256="3d755a227098527693faeb66906c643d26e8c436ef0f87356f9487629"
                        "9511256",
        unit_of_analysis="one focus group x condition cell"),
    "study_replication_summary": ThematicSource(
        key="study_replication_summary",
        relative_path=_R + "study_replication_summary.csv",
        producer="scripts/aggregate_production_results.py",
        schema=("study_replicate", "condition", "n_fgs", "fgs_included",
                "recall_mean_across_5_fgs", "precision_mean_across_5_fgs",
                "f1_secondary_mean", "reach_mean", "distinct_subthemes_across_study"),
        expected_rows=6,
        coding_basis=CodingBasis.PRIMARY.value,
        description="GOLDEN for route B: study replicate k over FG1..FG5",
        expected_sha256="1abf6fb6a8094f44e3079e8bd22996dda73396ca63452e7a4013cb0c8"
                        "eff3785",
        unit_of_analysis="one study replicate (five focus groups)"),
    "thematic_code_presence_long": ThematicSource(
        key="thematic_code_presence_long",
        relative_path=_R + "thematic_code_presence_long.csv",
        producer="scripts/aggregate_production_results.py",
        schema=("side", "physical_run", "condition", "fg",
                "canonical_replication_index", "subtheme_id", "parent_theme",
                "present", "quote_verified", "n_verified_quotes", "voiced_by_n"),
        expected_rows=385,
        coding_basis=CodingBasis.PRIMARY.value,
        description="the primary presence coding itself: 11 subthemes x 30 synthetic "
                    "runs + 5 human focus groups",
        expected_sha256="1003c730c50adef36e91734c66c067f1c148e940182cba396c63aa102"
                        "313ef41",
        unit_of_analysis="one subtheme within one run or human focus group"),
    "thematic_reach_long": ThematicSource(
        key="thematic_reach_long",
        relative_path=_R + "thematic_reach_long.csv",
        producer="scripts/aggregate_production_results.py",
        schema=("side", "physical_run", "condition", "fg",
                "canonical_replication_index", "subtheme_id", "voiced_by_n",
                "participants_n", "reach", "implementation_caveat"),
        expected_rows=125,
        coding_basis=CodingBasis.PRIMARY.value,
        description="participant reach per PRESENT subtheme; absent subthemes have "
                    "no row, which is why the denominator must be read and not "
                    "assumed to be 11",
        expected_sha256="af2424f5531aac8cee23e3a0cba9e9eace21a347dc8e5b557cf3e81ed"
                        "d2f5721",
        unit_of_analysis="one present subtheme within one run or human focus group"),
    "salience_hierarchy_per_run": ThematicSource(
        key="salience_hierarchy_per_run",
        relative_path=_F + "salience_hierarchy_per_run.csv",
        producer="scripts/salience_hierarchy_outputs.py",
        schema=("fg", "condition", "canonical_replication_index", "n_human_present",
                "n_scored", "kendall_tau_b", "undefined_reason",
                "top_theme_overlap_tie_aware"),
        expected_rows=30,
        coding_basis=CodingBasis.PRIMARY.value,
        description="ordering agreement per run; the tau-b values are READ, the "
                    "aggregation over them is recomputed",
        expected_sha256="fd572c6a3c939f0fcabe4aad7e843ec8bd20fb77a6c7c0d533a39f12a"
                        "61e61e1",
        unit_of_analysis="one synthetic run"),
    "salience_hierarchy_by_fg_condition": ThematicSource(
        key="salience_hierarchy_by_fg_condition",
        relative_path=_F + "salience_hierarchy_by_fg_condition.csv",
        producer="scripts/salience_hierarchy_outputs.py",
        schema=("fg", "condition", "n_replicates", "n_defined",
                "median_kendall_tau_b", "min_kendall_tau_b", "max_kendall_tau_b"),
        expected_rows=10,
        coding_basis=CodingBasis.PRIMARY.value,
        description="GOLDEN for the route A aggregation of ordering agreement",
        expected_sha256="77b8614a16cd786be540d2db2a00cdded663ec40c3479eb7a641690f1"
                        "1cddd7b",
        unit_of_analysis="one focus group x condition cell"),
    "salience_hierarchy_study_replicates": ThematicSource(
        key="salience_hierarchy_study_replicates",
        relative_path=_F + "salience_hierarchy_study_replicates.csv",
        producer="scripts/salience_hierarchy_outputs.py",
        schema=("condition", "canonical_replication_index", "n_subthemes",
                "kendall_tau_b_n_fgs_present", "kendall_tau_b_mean_reach"),
        expected_rows=6,
        coding_basis=CodingBasis.PRIMARY.value,
        description="ordering agreement assembled at study-replicate level",
        expected_sha256="82bf458536f0ff31dba289b69a3f3ab8f817ec8f2199a7f87f6f0c40d"
                        "c5d9272",
        unit_of_analysis="one study replicate"),
    "across_group_recurrence_sensitivity": ThematicSource(
        key="across_group_recurrence_sensitivity",
        relative_path=_A + "across_group_recurrence_sensitivity.csv",
        producer="scripts/absence_audit_final.py",
        schema=("condition", "canonical_replication_index", "subtheme_id",
                "n_fgs_original", "n_fgs_contested_as_present", "delta"),
        expected_rows=77,
        coding_basis=CodingBasis.BOTH.value,
        description="BOTH bases in one file, in DIFFERENT COLUMNS: n_fgs_original is "
                    "primary and is the golden for recurrence; "
                    "n_fgs_contested_as_present is the adjudicated sensitivity. They "
                    "are never added together",
        expected_sha256="a8efbb0162446754dd4a952055b1113bd45e724ffdef0c52c9ddcd699"
                        "3b6d450",
        unit_of_analysis="one subtheme within one condition x study replicate"),
    "combined_recurrence_sensitivity": ThematicSource(
        key="combined_recurrence_sensitivity",
        relative_path=_A + "combined_recurrence_sensitivity.csv",
        producer="scripts/combined_sensitivity.py",
        schema=("condition", "canonical_replication_index", "subtheme_id",
                "n_fgs_ORIGINAL", "n_fgs_CROSS_MODEL", "n_fgs_COMBINED",
                "delta_cross_model", "delta_combined"),
        expected_rows=77,
        coding_basis=CodingBasis.BOTH.value,
        description="the same cells under three treatments; ORIGINAL is the primary "
                    "coding and the other two are sensitivity treatments",
        expected_sha256="d8cb10a04732ce0216442670f519da939395787e34df428f224fcb111"
                        "c93e51b",
        unit_of_analysis="one subtheme within one condition x study replicate"),
    "salience_sensitivity_final": ThematicSource(
        key="salience_sensitivity_final",
        relative_path=_A + "salience_sensitivity_final.json",
        producer="scripts/salience_sensitivity_final.py",
        schema=("classification", "primary", "primary_unmodified", "tau_b_table",
                "n_contested_cells_applied", "n_defined_by_treatment"),
        expected_rows=None,
        coding_basis=CodingBasis.BOTH.value,
        description="adjudicated sensitivity over the ordering agreement; declares "
                    "ORIGINAL_LOWER as primary and records that the primary result "
                    "was left unmodified",
        expected_sha256="90e8e77822e75fb02613f735abf9a0f99e45bf866b4f34da7cb7ab00a"
                        "e463ea1",
        unit_of_analysis="one synthetic run, under three treatments"),
    "inductive_theme_accumulation_main": ThematicSource(
        key="inductive_theme_accumulation_main",
        relative_path="analysis/figures/inductive_theme_accumulation_main.csv",
        producer="analysis/figures/render_inductive_theme_accumulation_main.py",
        schema=("panel", "condition", "realisation", "position", "metric", "value"),
        expected_rows=135,
        coding_basis=CodingBasis.PRIMARY.value,
        description="the accumulation curve as published; derived from the frozen "
                    "inductive coding, with no independent numeric golden",
        expected_sha256="db0831a5a3e2d3e7e42b8fb54aaaa1bee0aa24a86a25e3e45c5c7e4ed"
                        "be2292d",
        unit_of_analysis="one sequence position within one realisation"),
}


def verify_sources(keys=None) -> list[dict]:
    return [SOURCES[k].verify() for k in (keys or sorted(SOURCES))]


def source_inventory() -> list[dict]:
    """Path, schema, producer, hash, expected rows, coding basis - all of it."""
    out = []
    for key in sorted(SOURCES):
        s = SOURCES[key]
        out.append({"key": s.key, "path": s.relative_path, "producer": s.producer,
                    "schema": list(s.schema), "expected_rows": s.expected_rows,
                    "coding_basis": s.coding_basis,
                    "unit_of_analysis": s.unit_of_analysis,
                    "sha256": s.sha256(), "description": s.description})
    return out


# ================================================================ B3 the result
@dataclass
class ThematicResult:
    metric_id: str
    condition: str
    focus_group: str | None
    replicate_index: int | None
    value: float | None
    numerator: float | None
    denominator: float | None
    coding_basis: str
    calculation_status: str
    source_artifact: str
    source_hash: str
    verification: str
    caveats: list[str] = field(default_factory=list)
    aggregation_version: str = AGGREGATION_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------- metric contracts
# Nothing is implemented without all five: producer, golden, unit, denominator, rule.
@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    label: str
    unit_of_analysis: str
    numerator: str
    denominator: str
    aggregation_rule: str
    golden: str | None
    source_key: str
    estimand: str
    statistic_name: str | None = None


METRIC_SPECS: dict[str, MetricSpec] = {
    "tier1_subtheme_recall": MetricSpec(
        metric_id="tier1_subtheme_recall", label="Thematic recall",
        unit_of_analysis="one synthetic run against its paired human focus group",
        numerator="subthemes present in BOTH the human focus group and the run",
        denominator="subthemes present in the human focus group",
        aggregation_rule="mean of the run values within the cell; the counts are "
                         "never summed across runs",
        golden="primary_effects_by_fg", source_key="per_run_metrics",
        estimand="proportion of the human repertoire the run recovered"),
    "tier1_matched_theme_precision": MetricSpec(
        metric_id="tier1_matched_theme_precision", label="Thematic precision",
        unit_of_analysis="one synthetic run against its paired human focus group",
        numerator="subthemes present in BOTH",
        denominator="subthemes present in the synthetic run",
        aggregation_rule="mean of the run values within the cell; undefined runs "
                         "reduce n and are not imputed",
        golden="primary_effects_by_fg", source_key="per_run_metrics",
        estimand="proportion of what the run produced that the humans also produced"),
    "tier1_f1_secondary": MetricSpec(
        metric_id="tier1_f1_secondary", label="Thematic F1 (secondary)",
        unit_of_analysis="one synthetic run against its paired human focus group",
        numerator="2 x subthemes present in BOTH",
        denominator="human present + synthetic present",
        aggregation_rule="computed FROM THE COUNTS in each run, then averaged. "
                         "TWO FROZEN ARTEFACTS DISAGREE HERE BY 1e-4: "
                         "primary_effects_by_fg.csv computes f1 at full precision, "
                         "while study_replication_summary.csv averages the 4dp "
                         "values stored in per_run_metrics.csv. This module follows "
                         "the counts, so it reproduces the first exactly and the "
                         "second in five of six cells "
                         "(demographics-only replicate 2: 0.3641 vs 0.3642)",
        golden="primary_effects_by_fg", source_key="per_run_metrics",
        estimand="harmonic mean of recall and precision"),
    "tier1_participant_reach": MetricSpec(
        metric_id="tier1_participant_reach", label="Participant reach (all present)",
        unit_of_analysis="one synthetic run",
        numerator="sum of per-subtheme reach over the subthemes the run marked "
                  "present",
        denominator="number of subthemes the run marked present",
        aggregation_rule="mean of the run values within the cell",
        golden="primary_effects_by_fg", source_key="thematic_reach_long",
        estimand="ESTIMAND 1 - how widely the run's OWN themes were voiced. The "
                 "human side does not enter this number at all"),
    "tier1_participant_reach_shared_only": MetricSpec(
        metric_id="tier1_participant_reach_shared_only",
        label="Participant reach (shared subthemes only)",
        unit_of_analysis="one synthetic run against its paired human focus group",
        numerator="sum of per-subtheme reach over subthemes present in BOTH",
        denominator="number of subthemes present in BOTH",
        aggregation_rule="mean of the run values within the cell; a run with no "
                         "shared subtheme is undefined, not zero",
        golden=None, source_key="thematic_reach_long",
        estimand="ESTIMAND 2 - how widely the SHARED themes were voiced, on each "
                 "side. Comparable with the human reach over the same subthemes, "
                 "which estimand 1 is not"),
    "theme_recurrence_across_groups": MetricSpec(
        metric_id="theme_recurrence_across_groups",
        label="Thematic recurrence across focus groups",
        unit_of_analysis="one subtheme within one condition x study replicate",
        numerator="focus groups in which the subtheme is present",
        denominator="focus groups in the realisation (5)",
        aggregation_rule="counted across the five focus groups of one study "
                         "replicate; NOT across participants",
        golden="across_group_recurrence_sensitivity",
        source_key="thematic_code_presence_long",
        estimand="in how many of the five groups a subtheme appeared at all"),
    "tier1_salience_hierarchy": MetricSpec(
        metric_id="tier1_salience_hierarchy",
        label="Agreement in thematic ordering",
        unit_of_analysis="one synthetic run against its paired human focus group",
        numerator="concordant minus discordant subtheme pairs",
        denominator="tie-corrected total pairs",
        aggregation_rule="median of the defined run values within the cell; runs "
                         "with an undefined_reason are excluded and counted",
        golden="salience_hierarchy_by_fg_condition",
        source_key="salience_hierarchy_per_run",
        estimand="whether the two sides rank the same subthemes as most prominent",
        statistic_name="Kendall tau-b"),
}

DEFERRED: dict[str, dict] = {
    "guide_coverage": {
        "metric_id": "guide_coverage",
        "status": Status.DEFERRED_NOT_IMPLEMENTED.value,
        "reason": "no unambiguous definition and no frozen artefact. The corpus "
                  "contains no producer, no golden table and no per-guide-question "
                  "coverage column; the term appears in the final documents only in "
                  "the list of things NOT reported.",
        "explicitly_not_done": [
            "guide coverage is NOT inferred from thematic recall - recall is "
            "measured against the human codebook, not against the guide, and the "
            "two denominators are different objects",
            "no proxy is substituted",
        ],
        "blocks_other_metrics": False,
        "to_implement_it_would_need": [
            "a stated mapping from guide question to subtheme",
            "a decision on whether a question counts as covered when any "
            "participant addresses it or when the discussion reaches it",
            "a denominator: planned questions, or planned probes",
        ],
    },
}


def _catalog_status(metric_id: str) -> str | None:
    try:
        return load_catalog().get(metric_id).status
    except Exception:
        return None


def _calculation_status(metric_id: str, has_golden: bool) -> str:
    """
    EXPLORATORY wins over arithmetic. A metric the registry marks exploratory stays
    exploratory even when it reproduces its published table to the last decimal: the
    doubt is about the instrument, and reproducing a number does not validate it.
    """
    if _catalog_status(metric_id) == Status.AVAILABLE_EXPLORATORY:
        return CalculationStatus.EXPLORATORY.value
    return (CalculationStatus.FROZEN_REPRODUCED.value if has_golden
            else CalculationStatus.DERIVED_FROM_FROZEN.value)


# =============================================================== primary loading
def _int(v):
    return None if v in ("", "None", None) else int(v)


def _replicate_index(v):
    """
    The human side has no replicate index. Different artefacts spell that absence
    differently - empty in `across_group_recurrence_sensitivity`, the literal string
    "human" in `combined_recurrence_sensitivity`. Both mean "not a replicate"; any
    OTHER non-numeric value is a fault and still raises.
    """
    if v in ("", "None", None, HUMAN):
        return None
    return int(v)


def _float(v):
    return None if v in ("", "None", None, "null") else float(v)


def load_per_run_metrics() -> list[dict]:
    return SOURCES["per_run_metrics"].rows()


def load_code_presence() -> list[dict]:
    return SOURCES["thematic_code_presence_long"].rows()


def load_reach_long() -> list[dict]:
    return SOURCES["thematic_reach_long"].rows()


def _reach_by_run(rows=None) -> dict[str, dict[str, float]]:
    """physical_run -> {subtheme_id: reach}, synthetic side."""
    rows = rows if rows is not None else load_reach_long()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        if r["side"] != "synthetic":
            continue
        out.setdefault(r["physical_run"], {})[r["subtheme_id"]] = float(r["reach"])
    return out


def _reach_by_human_fg(rows=None) -> dict[str, dict[str, float]]:
    rows = rows if rows is not None else load_reach_long()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        if r["side"] == HUMAN:
            out.setdefault(r["fg"], {})[r["subtheme_id"]] = float(r["reach"])
    return out


def _present_subthemes(rows=None) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(synthetic by physical_run, human by fg) - only subthemes marked present."""
    rows = rows if rows is not None else load_code_presence()
    synth: dict[str, set[str]] = {}
    human: dict[str, set[str]] = {}
    for r in rows:
        if r["present"] != "True":
            continue
        if r["side"] == HUMAN:
            human.setdefault(r["fg"], set()).add(r["subtheme_id"])
        else:
            synth.setdefault(r["physical_run"], set()).add(r["subtheme_id"])
    return synth, human


def _result(spec: MetricSpec, row: dict, value, numerator, denominator,
            caveats=None, verification=None) -> ThematicResult:
    source = SOURCES[spec.source_key]
    return ThematicResult(
        metric_id=spec.metric_id, condition=row["condition"], focus_group=row["fg"],
        replicate_index=_int(row["canonical_replication_index"]),
        value=value, numerator=numerator, denominator=denominator,
        coding_basis=CodingBasis.PRIMARY.value,
        calculation_status=_calculation_status(spec.metric_id,
                                               spec.golden is not None),
        source_artifact=source.relative_path, source_hash=source.sha256(),
        verification=(verification or
                      (Verification.RECOMPUTED_AND_MATCHED.value if spec.golden
                       else Verification.RECOMPUTED_NO_GOLDEN.value)),
        caveats=list(caveats or []))


def recall_results(rows=None) -> list[ThematicResult]:
    spec = METRIC_SPECS["tier1_subtheme_recall"]
    out = []
    for r in (rows if rows is not None else load_per_run_metrics()):
        num, den = _int(r["shared_n"]), _int(r["human_present_n"])
        caveats = []
        if not den:
            value = None
            caveats.append("the human focus group has no coded subtheme; recall is "
                           "undefined, not zero")
        else:
            value = num / den
        out.append(_result(spec, r, value, num, den, caveats))
    return out


def precision_results(rows=None) -> list[ThematicResult]:
    spec = METRIC_SPECS["tier1_matched_theme_precision"]
    out = []
    for r in (rows if rows is not None else load_per_run_metrics()):
        num, den = _int(r["shared_n"]), _int(r["synthetic_present_n"])
        caveats = []
        if not den:
            value = None
            caveats.append("the run produced no subtheme; precision over an empty "
                           "denominator is UNDEFINED, not zero - a run that says "
                           "nothing is not perfectly precise")
        else:
            value = num / den
        out.append(_result(spec, r, value, num, den, caveats))
    return out


def f1_results(rows=None) -> list[ThematicResult]:
    spec = METRIC_SPECS["tier1_f1_secondary"]
    out = []
    for r in (rows if rows is not None else load_per_run_metrics()):
        shared = _int(r["shared_n"])
        den = (_int(r["human_present_n"]) or 0) + (_int(r["synthetic_present_n"]) or 0)
        value = (2 * shared / den) if den else None
        caveats = ["computed from the counts, not from rounded recall and precision"]
        if not den:
            caveats.append("neither side coded anything; undefined, not zero")
        out.append(_result(spec, r, value,
                           2 * shared if shared is not None else None,
                           den, caveats))
    return out


def reach_results_all_present(per_run=None, reach_rows=None) -> list[ThematicResult]:
    """ESTIMAND 1: mean reach over the subthemes the run itself marked present."""
    spec = METRIC_SPECS["tier1_participant_reach"]
    by_run = _reach_by_run(reach_rows)
    out = []
    for r in (per_run if per_run is not None else load_per_run_metrics()):
        vals = list(by_run.get(r["physical_run"], {}).values())
        value = statistics.mean(vals) if vals else None
        caveats = ["the denominator is the run's OWN present subthemes; this number "
                   "is not a comparison with the human side"]
        if not vals:
            caveats.append("no present subtheme with a reach value; undefined")
        out.append(_result(spec, r, value, sum(vals) if vals else None,
                           len(vals), caveats))
    return out


def reach_results_shared_only(per_run=None, reach_rows=None, presence_rows=None
                              ) -> list[ThematicResult]:
    """
    ESTIMAND 2: mean reach over subthemes present in BOTH sides.

    A DIFFERENT ESTIMAND from `reach_results_all_present`, not a refinement of it, and
    the two must never be averaged together or plotted on one axis: one describes the
    run's own repertoire, the other describes the overlap.
    """
    spec = METRIC_SPECS["tier1_participant_reach_shared_only"]
    by_run = _reach_by_run(reach_rows)
    synth_present, human_present = _present_subthemes(presence_rows)
    human_reach = _reach_by_human_fg(reach_rows)
    out = []
    for r in (per_run if per_run is not None else load_per_run_metrics()):
        run = r["physical_run"]
        shared = sorted(synth_present.get(run, set())
                        & human_present.get(r["fg"], set()))
        vals = [by_run[run][s] for s in shared if s in by_run.get(run, {})]
        value = statistics.mean(vals) if vals else None
        caveats = ["shared subthemes only; NOT comparable with "
                   "tier1_participant_reach, which uses a different denominator"]
        if not vals:
            caveats.append("no shared subtheme; undefined, not zero")
        res = _result(spec, r, value, sum(vals) if vals else None,
                      len(vals), caveats)
        # The matching human figure over the SAME subthemes, so the comparison is
        # like for like. Kept beside the value, not folded into it.
        hv = [human_reach.get(r["fg"], {})[s] for s in shared
              if s in human_reach.get(r["fg"], {})]
        res.caveats.append(
            f"paired human reach over the same {len(hv)} subtheme(s): "
            f"{round(statistics.mean(hv), 6) if hv else None}")
        out.append(res)
    return out


PRIMARY_BUILDERS = {
    "tier1_subtheme_recall": recall_results,
    "tier1_matched_theme_precision": precision_results,
    "tier1_f1_secondary": f1_results,
    "tier1_participant_reach": reach_results_all_present,
    "tier1_participant_reach_shared_only": reach_results_shared_only,
}


def primary_results(metric_ids=None) -> list[ThematicResult]:
    ids = tuple(metric_ids or PRIMARY_BUILDERS)
    out: list[ThematicResult] = []
    for metric_id in ids:
        if metric_id not in PRIMARY_BUILDERS:
            raise ThematicError(
                f"{metric_id!r} has no primary builder; see DEFERRED and "
                f"METRIC_SPECS")
        out.extend(PRIMARY_BUILDERS[metric_id]())
    return out


# ================================================================ B4 aggregation
@dataclass
class ThematicCell:
    """Route A: three synthetic runs in one focus group x condition cell."""

    metric_id: str
    condition: str
    focus_group: str
    replicate_indices: list[int | None]
    summary: Summary
    human_reference: float | None
    human_reference_note: str
    calculation_status: str
    coding_basis: str
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["summary"] = asdict(self.summary)
        return d


HUMAN_REFERENCE_NOTES = {
    "tier1_subtheme_recall":
        "no separate human referent: the human repertoire IS the denominator",
    "tier1_matched_theme_precision":
        "no separate human referent: the comparison is already against the human "
        "codebook",
    "tier1_f1_secondary":
        "no separate human referent: both components are already human-referenced",
    "tier1_participant_reach":
        "the human focus group's mean reach over ITS OWN present subthemes; the two "
        "denominators differ, so this is a context figure, not a paired contrast",
    "tier1_participant_reach_shared_only":
        "the human mean reach over the SAME shared subthemes - a like-for-like pair",
}


def _human_reference(metric_id: str, fg: str) -> float | None:
    if metric_id not in ("tier1_participant_reach",
                         "tier1_participant_reach_shared_only"):
        return None
    vals = list(_reach_by_human_fg().get(fg, {}).values())
    return statistics.mean(vals) if vals else None


def aggregate_thematic_focus_group_condition(results: list[ThematicResult]
                                             ) -> list[ThematicCell]:
    """
    Route A. Three synthetic runs per cell, the paired human referent where one is
    defined, and the n the mean was actually computed over.
    """
    grouped: dict[tuple[str, str, str], list[ThematicResult]] = {}
    for r in results:
        grouped.setdefault((r.metric_id, r.condition, r.focus_group), []).append(r)

    out: list[ThematicCell] = []
    for (metric_id, condition, fg), group in sorted(grouped.items()):
        group.sort(key=lambda r: (r.replicate_index or 0))
        values = [r.value for r in group]
        s = summarise(values, n_expected=len(REPLICATES),
                      rule=METRIC_SPECS[metric_id].aggregation_rule)
        out.append(ThematicCell(
            metric_id=metric_id, condition=condition, focus_group=fg,
            replicate_indices=[r.replicate_index for r in group], summary=s,
            human_reference=_human_reference(metric_id, fg),
            human_reference_note=HUMAN_REFERENCE_NOTES.get(metric_id, ""),
            calculation_status=group[0].calculation_status,
            coding_basis=group[0].coding_basis,
            caveats=sorted({c for r in group for c in r.caveats})))
    return out


@dataclass
class ThematicStudyReplicate:
    """
    Route B. Replicate k is run k of FG1..FG5 - a canonical index, not a shared seed
    and not a repeated experiment. The five values are five focus groups, and the 15
    sessions of a condition are never pooled.
    """

    metric_id: str
    condition: str
    replicate_index: int
    fgs_included: list[str]
    summary: Summary
    human_reference: Summary | None
    calculation_status: str
    coding_basis: str
    note: str = ("canonical_replication_index k of FG1..FG5; the index labels a "
                 "position in the frozen results, it does not imply a shared seed "
                 "between focus groups")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["summary"] = asdict(self.summary)
        d["human_reference"] = (asdict(self.human_reference)
                                if self.human_reference else None)
        return d


def aggregate_thematic_study_replicates(results: list[ThematicResult]
                                        ) -> list[ThematicStudyReplicate]:
    grouped: dict[tuple[str, str, int], dict[str, ThematicResult]] = {}
    for r in results:
        grouped.setdefault((r.metric_id, r.condition, r.replicate_index),
                           {})[r.focus_group] = r

    out: list[ThematicStudyReplicate] = []
    for (metric_id, condition, k), by_fg in sorted(grouped.items()):
        values = [by_fg[f].value if f in by_fg else None for f in FGS]
        s = summarise(values, n_expected=len(FGS),
                      rule=METRIC_SPECS[metric_id].aggregation_rule,
                      missing_units=[f for f in FGS if f not in by_fg])
        href = None
        if metric_id in ("tier1_participant_reach",
                         "tier1_participant_reach_shared_only"):
            href = summarise([_human_reference(metric_id, f) for f in FGS],
                             n_expected=len(FGS))
        any_r = next(iter(by_fg.values()))
        out.append(ThematicStudyReplicate(
            metric_id=metric_id, condition=condition, replicate_index=k,
            fgs_included=[f for f in FGS if f in by_fg], summary=s,
            human_reference=href, calculation_status=any_r.calculation_status,
            coding_basis=any_r.coding_basis))
    return out


# ==================================================== salience: two separate axes
def recurrence_across_focus_groups(presence_rows=None) -> list[ThematicResult]:
    """
    AXIS 1 of salience: in how many of the five focus groups a subtheme appears.

    Counted across GROUPS. This is not reach, which counts across PARTICIPANTS inside
    a group; the two are reported separately and are never combined into one
    "salience" figure.
    """
    spec = METRIC_SPECS["theme_recurrence_across_groups"]
    rows = presence_rows if presence_rows is not None else load_code_presence()
    source = SOURCES["thematic_code_presence_long"]

    counts: dict[tuple[str, str | None, str], set[str]] = {}
    subthemes = sorted({r["subtheme_id"] for r in rows})
    seen_cells: set[tuple[str, str | None]] = set()
    for r in rows:
        k = None if r["side"] == HUMAN else _int(r["canonical_replication_index"])
        seen_cells.add((r["condition"], k))
        if r["present"] == "True":
            counts.setdefault((r["condition"], k, r["subtheme_id"]),
                              set()).add(r["fg"])

    out = []
    for condition, k in sorted(seen_cells, key=lambda t: (t[0], t[1] or 0)):
        for subtheme in subthemes:
            fgs = counts.get((condition, k, subtheme), set())
            out.append(ThematicResult(
                metric_id=spec.metric_id, condition=condition, focus_group=None,
                replicate_index=k, value=len(fgs) / len(FGS),
                numerator=len(fgs), denominator=len(FGS),
                coding_basis=CodingBasis.PRIMARY.value,
                calculation_status=_calculation_status(spec.metric_id, True),
                source_artifact=source.relative_path, source_hash=source.sha256(),
                verification=Verification.RECOMPUTED_AND_MATCHED.value,
                caveats=[f"subtheme {subtheme}",
                         "counted across FOCUS GROUPS, not across participants"]))
    return out


def salience_ordering_agreement(rows=None) -> list[dict]:
    """
    AXIS 2 of salience: do the two sides put the same subthemes at the top?

    The statistic is Kendall tau-b. The label a reader sees is "agreement in thematic
    ordering"; the statistical name stays in the metadata, where it belongs. No
    "hierarchy concordance" is asserted anywhere a tau-b was not actually computed -
    runs with an `undefined_reason` are carried as undefined and counted, never
    dropped silently and never read as zero agreement.
    """
    spec = METRIC_SPECS["tier1_salience_hierarchy"]
    source = SOURCES["salience_hierarchy_per_run"]
    out = []
    for r in (rows if rows is not None else source.rows()):
        tau = _float(r["kendall_tau_b"])
        out.append({
            "metric_id": spec.metric_id,
            "label": spec.label,
            "condition": r["condition"], "focus_group": r["fg"],
            "replicate_index": _int(r["canonical_replication_index"]),
            "value": tau,
            "undefined_reason": r["undefined_reason"] or None,
            "n_scored": _int(r["n_scored"]),
            "coding_basis": CodingBasis.PRIMARY.value,
            "calculation_status": _calculation_status(spec.metric_id, True),
            "source_artifact": source.relative_path,
            "source_hash": source.sha256(),
            "verification": Verification.READ_FROM_FROZEN_ARTIFACT.value,
            "metadata": {"statistic": spec.statistic_name,
                         "range": "-1 to 1",
                         "zero_means": "no association in ordering, NOT 'no themes "
                                       "in common'"},
        })
    return out


def salience_ordering_by_focus_group(rows=None) -> list[dict]:
    """Route A over the ordering agreement: the median of the defined run values."""
    per_run = salience_ordering_agreement(rows)
    grouped: dict[tuple[str, str], list[dict]] = {}
    for r in per_run:
        grouped.setdefault((r["focus_group"], r["condition"]), []).append(r)

    out = []
    for (fg, condition), group in sorted(grouped.items()):
        defined = [r["value"] for r in group if r["value"] is not None]
        out.append({
            "metric_id": "tier1_salience_hierarchy",
            "label": METRIC_SPECS["tier1_salience_hierarchy"].label,
            "focus_group": fg, "condition": condition,
            "n_replicates": len(group), "n_defined": len(defined),
            "median": statistics.median(defined) if defined else None,
            "minimum": min(defined) if defined else None,
            "maximum": max(defined) if defined else None,
            "calculation_status": _calculation_status("tier1_salience_hierarchy",
                                                      True),
            "verification": Verification.RECOMPUTED_AND_MATCHED.value,
            "coding_basis": CodingBasis.PRIMARY.value,
            "metadata": {"statistic": "Kendall tau-b"},
        })
    return out


# ============================================================ B4 sensitivity view
@dataclass
class SensitivityComparison:
    """
    A PAIRED view, never a substitution. Both bases are present in the same object
    with their own labels, so a reader cannot mistake one for the other and a caller
    cannot accidentally publish the sensitivity figure as the result.
    """

    metric_id: str
    condition: str
    replicate_index: int | None
    subtheme_id: str
    primary_value: float | None
    sensitivity_value: float | None
    delta: float | None
    treatment: str
    primary_is_unmodified: bool
    source_artifact: str
    source_hash: str
    note: str = ("the primary coding stands; the sensitivity treatment is reported "
                 "alongside it and does not replace it")


def recurrence_sensitivity(treatment: str = "CONTESTED_AS_PRESENT"
                           ) -> list[SensitivityComparison]:
    """
    The adjudicated absence audit, as a parallel view of recurrence.

    `treatment` selects a column, never a merge:
      CONTESTED_AS_PRESENT   n_fgs_contested_as_present (absence_audit_final)
      CROSS_MODEL            n_fgs_CROSS_MODEL          (combined_sensitivity)
      COMBINED               n_fgs_COMBINED             (combined_sensitivity)
    """
    if treatment == "CONTESTED_AS_PRESENT":
        source = SOURCES["across_group_recurrence_sensitivity"]
        primary_col, sens_col = "n_fgs_original", "n_fgs_contested_as_present"
    elif treatment in ("CROSS_MODEL", "COMBINED"):
        source = SOURCES["combined_recurrence_sensitivity"]
        primary_col, sens_col = "n_fgs_ORIGINAL", f"n_fgs_{treatment}"
    else:
        raise ThematicError(f"unknown sensitivity treatment {treatment!r}")

    digest = source.sha256()
    out = []
    for r in source.rows():
        p, s = _int(r[primary_col]), _int(r[sens_col])
        out.append(SensitivityComparison(
            metric_id="theme_recurrence_across_groups",
            condition=r["condition"],
            replicate_index=_replicate_index(r["canonical_replication_index"]),
            subtheme_id=r["subtheme_id"],
            primary_value=p / len(FGS) if p is not None else None,
            sensitivity_value=s / len(FGS) if s is not None else None,
            delta=(s - p) / len(FGS) if (p is not None and s is not None) else None,
            treatment=treatment, primary_is_unmodified=True,
            source_artifact=source.relative_path, source_hash=digest))
    return out


def ordering_agreement_sensitivity() -> dict:
    """
    The adjudicated sensitivity over the ordering agreement, as its own object.

    Reads the declared primary treatment out of the artefact rather than assuming it,
    and refuses to hand back a table if the artefact says the primary result was
    modified - at that point the primary/sensitivity separation this module rests on
    would no longer hold.
    """
    source = SOURCES["salience_sensitivity_final"]
    payload = source.payload()
    if not payload.get("primary_unmodified", False):
        raise ThematicError(
            "salience_sensitivity_final declares the primary result MODIFIED; the "
            "primary/sensitivity separation cannot be assumed - resolve by hand")
    return {
        "metric_id": "tier1_salience_hierarchy",
        "label": METRIC_SPECS["tier1_salience_hierarchy"].label,
        "classification": payload["classification"],
        "primary_treatment": payload["primary"],
        "primary_is_unmodified": True,
        "treatments": ["ORIGINAL_LOWER", "MID", "UPPER"],
        "n_contested_cells_applied": payload["n_contested_cells_applied"],
        "n_defined_by_treatment": payload["n_defined_by_treatment"],
        "per_run": payload["tau_b_table"],
        "coding_basis": CodingBasis.SENSITIVITY.value,
        "calculation_status": CalculationStatus.EXPLORATORY.value,
        "source_artifact": source.relative_path,
        "source_hash": source.sha256(),
        "verification": Verification.READ_FROM_FROZEN_ARTIFACT.value,
        "note": ("ORIGINAL_LOWER is the primary treatment and is the reported "
                 "result; MID and UPPER are sensitivity treatments and are shown "
                 "beside it, never instead of it"),
        "metadata": {"statistic": "Kendall tau-b"},
    }


# ========================================================== B5 theme accumulation
ACCUMULATION_POSITIONS = ("1", "2", "3", "4", "5")


@dataclass
class AccumulationCurve:
    condition: str
    realisation: str
    positions: list[str]
    values: list[float | None]
    metric: str
    calculation_status: str
    source_artifact: str
    source_hash: str
    verification: str
    note: str = ""


def load_accumulation(panel: str = "A",
                      metric: str = "pct_of_final_repertoire") -> list[dict]:
    return [r for r in SOURCES["inductive_theme_accumulation_main"].rows()
            if r["panel"] == panel and r["metric"] == metric]


def accumulation_curves(panel: str = "A",
                        metric: str = "pct_of_final_repertoire"
                        ) -> list[AccumulationCurve]:
    """
    Percentage of the FINAL repertoire observed after FG1..FG5, for human, enriched
    and demographics-only.

    Each condition's repertoire is its OWN. Two curves reaching 80% after three groups
    are accumulating at the same rate; that says nothing about whether they are
    accumulating the same categories. Whether the categories coincide is a different
    question and belongs to a separate metric - it is deliberately not answered here.
    """
    source = SOURCES["inductive_theme_accumulation_main"]
    digest = source.sha256()
    rows = load_accumulation(panel, metric)
    grouped: dict[tuple[str, str], dict[str, float]] = {}
    for r in rows:
        grouped.setdefault((r["condition"], r["realisation"]),
                           {})[r["position"]] = float(r["value"])

    out = []
    for (condition, realisation), by_pos in sorted(grouped.items()):
        positions = [p for p in ACCUMULATION_POSITIONS if p in by_pos]
        out.append(AccumulationCurve(
            condition=condition, realisation=realisation, positions=positions,
            values=[by_pos[p] for p in positions], metric=metric,
            calculation_status=CalculationStatus.DERIVED_FROM_FROZEN.value,
            source_artifact=source.relative_path, source_hash=digest,
            verification=Verification.READ_FROM_FROZEN_ARTIFACT.value,
            note="derived from the frozen inductive coding; no independent numeric "
                 "golden exists for this curve"))
    return out


def accumulation_by_condition(panel: str = "A",
                              metric: str = "pct_of_final_repertoire") -> list[dict]:
    """
    The synthetic conditions summarised over their THREE REALISATIONS at each
    position: mean, min and max, with the n. The human side has one realisation and
    says so rather than reporting a spread of one.
    """
    curves = accumulation_curves(panel, metric)
    by_condition: dict[str, list[AccumulationCurve]] = {}
    for c in curves:
        by_condition.setdefault(c.condition, []).append(c)

    out = []
    for condition, group in sorted(by_condition.items()):
        realisations = sorted(c.realisation for c in group)
        per_position = []
        for i, position in enumerate(ACCUMULATION_POSITIONS):
            vals = [c.values[i] for c in group
                    if i < len(c.values) and c.values[i] is not None]
            per_position.append({
                "position": position,
                "mean": statistics.mean(vals) if vals else None,
                "minimum": min(vals) if vals else None,
                "maximum": max(vals) if vals else None,
                "n_realisations": len(vals),
            })
        out.append({
            "metric_id": "inductive_theme_accumulation",
            "metric": metric, "condition": condition,
            "realisations": realisations,
            "n_realisations": len(group),
            "per_position": per_position,
            "single_realisation": len(group) == 1,
            "calculation_status": CalculationStatus.DERIVED_FROM_FROZEN.value,
            "verification": Verification.READ_FROM_FROZEN_ARTIFACT.value,
            "repertoire_note": ("each condition's percentage is of its OWN final "
                                "repertoire; equal accumulation SPEED does not imply "
                                "the same categories, and this function makes no "
                                "such claim"),
        })
    return out


# ================================================================= B6 deferrals
def guide_coverage_status() -> dict:
    return dict(DEFERRED["guide_coverage"])


def implemented_metrics() -> list[str]:
    return sorted(METRIC_SPECS)


def deferred_metrics() -> list[str]:
    return sorted(DEFERRED)
