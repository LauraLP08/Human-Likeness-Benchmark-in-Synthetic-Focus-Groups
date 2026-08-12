"""
Study context and comparability.

The question this module answers is "what may be compared with what", and it answers
it once, in code, rather than leaving it to whoever builds the next screen.

THE RULE THAT MATTERS: a corpus the user uploaded never acquires the frozen human
referent. Not by having a focus group called `fg1`, not by declaring a condition named
`enriched`, not by using the Macho Meals discussion guide, not by being uploaded into
a project whose name mentions the study. `FROZEN_BENCHMARK_COMPATIBLE` is reachable
only from `SourceType.FROZEN_BENCHMARK`, and there is a test that tries every one of
those routes and fails to get there.

A structural comparison between an uploaded human set and an uploaded synthetic set is
available, but only after the user DECLARES the two sets are homologues and says on
what grounds. The declaration is stored with the context, so a later reader can see
what the comparison rested on. Without it the context is REQUIRES_REVIEW - not a
comparison made quietly on the user's behalf.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..paths import safe_component, safe_path

CONTEXTS_DIRNAME = "contexts"


class SourceType(str, Enum):
    FROZEN_BENCHMARK = "FROZEN_BENCHMARK"
    USER_PROVIDED = "USER_PROVIDED"


class ComparabilityStatus(str, Enum):
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    MATCHED_STRUCTURAL_COMPARISON = "MATCHED_STRUCTURAL_COMPARISON"
    FROZEN_BENCHMARK_COMPATIBLE = "FROZEN_BENCHMARK_COMPATIBLE"
    THEMATIC_COMPARISON_NOT_AVAILABLE = "THEMATIC_COMPARISON_NOT_AVAILABLE"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class ContextError(RuntimeError):
    pass


@dataclass
class StudyContext:
    """
    What a set of transcripts is, and what may be done with it.

    Two axes, because they fail independently: `comparability_status` is about
    STRUCTURE, `thematic_status` is about THEMES. A pair of uploaded corpora can
    support a structural comparison and still have no thematic comparison at all -
    that is the normal case, not an edge case.
    """

    context_id: str
    project_id: str | None
    study_name: str
    source_type: str
    synthetic_set_ids: list[str] = field(default_factory=list)
    human_set_id: str | None = None
    discussion_guide_id: str | None = None
    codebook_id: str | None = None
    comparability_status: str = ComparabilityStatus.REQUIRES_REVIEW.value
    thematic_status: str = ComparabilityStatus.THEMATIC_COMPARISON_NOT_AVAILABLE.value
    comparability_reasons: list[str] = field(default_factory=list)
    declaration_by_user: str | None = None
    created_utc: str = ""

    @property
    def structural_comparison_allowed(self) -> bool:
        return self.comparability_status in (
            ComparabilityStatus.MATCHED_STRUCTURAL_COMPARISON.value,
            ComparabilityStatus.FROZEN_BENCHMARK_COMPATIBLE.value)

    @property
    def may_use_frozen_human_referent(self) -> bool:
        """Only the frozen benchmark itself. There is no second route."""
        return (self.source_type == SourceType.FROZEN_BENCHMARK.value
                and self.comparability_status ==
                ComparabilityStatus.FROZEN_BENCHMARK_COMPATIBLE.value)

    @property
    def thematic_available(self) -> bool:
        return self.thematic_status == \
            ComparabilityStatus.FROZEN_BENCHMARK_COMPATIBLE.value

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def classify_comparability(*, source_type: str, human_set_id: str | None,
                           synthetic_set_ids, declaration_by_user: str | None,
                           codebook_id: str | None = None
                           ) -> tuple[str, str, list[str]]:
    """
    Decide (comparability_status, thematic_status, reasons).

    Every branch records WHY, because a status without a reason is an assertion the
    reader cannot check.
    """
    synthetic_set_ids = list(synthetic_set_ids or [])
    reasons: list[str] = []

    if source_type == SourceType.FROZEN_BENCHMARK.value:
        reasons.append(
            "frozen benchmark: the human referent, the codebook and the comparable "
            "windows are the artefacts of record; nothing is re-derived")
        return (ComparabilityStatus.FROZEN_BENCHMARK_COMPATIBLE.value,
                ComparabilityStatus.FROZEN_BENCHMARK_COMPATIBLE.value, reasons)

    if source_type != SourceType.USER_PROVIDED.value:
        raise ContextError(f"unknown source_type {source_type!r}")

    # Thematic first: for an uploaded corpus the answer is always the same, and it is
    # not a function of anything the user can declare in this phase.
    thematic = ComparabilityStatus.THEMATIC_COMPARISON_NOT_AVAILABLE.value
    reasons.append(
        "thematic comparison is not available for an uploaded corpus: it needs a "
        "codebook and a coding procedure for THIS study, and neither is inferred "
        "from the frozen Macho Meals codebook")
    if codebook_id:
        reasons.append(
            f"a codebook id ({codebook_id}) is recorded, but recording an identifier "
            "does not supply a validated coding procedure; Level 1 stays unavailable")

    if not synthetic_set_ids and not human_set_id:
        reasons.append("no transcript set has been imported yet")
        return ComparabilityStatus.REQUIRES_REVIEW.value, thematic, reasons

    if human_set_id and not synthetic_set_ids:
        reasons.append("a human set only: descriptive structural results, with no "
                       "synthetic counterpart to compare against")
        return ComparabilityStatus.DESCRIPTIVE_ONLY.value, thematic, reasons

    if synthetic_set_ids and not human_set_id:
        reasons.append("a synthetic set with no human set in this project: "
                       "descriptive structural results only")
        reasons.append("the frozen Macho Meals human referent is NOT substituted; a "
                       "comparison needs a human set the user provides and declares")
        return ComparabilityStatus.DESCRIPTIVE_ONLY.value, thematic, reasons

    if not (declaration_by_user or "").strip():
        reasons.append(
            "both a human and a synthetic set are present, but the user has not "
            "declared them homologues; the platform does not decide that on the "
            "user's behalf")
        return ComparabilityStatus.REQUIRES_REVIEW.value, thematic, reasons

    reasons.append("the user declared the human and synthetic sets homologues and "
                   "recorded the grounds; structural comparison is available")
    reasons.append("structural only: no thematic fidelity claim follows from a "
                   "declared structural correspondence")
    return (ComparabilityStatus.MATCHED_STRUCTURAL_COMPARISON.value, thematic,
            reasons)


def build_context(*, context_id: str, study_name: str,
                  source_type: str = SourceType.USER_PROVIDED.value,
                  project_id: str | None = None,
                  human_set_id: str | None = None,
                  synthetic_set_ids=None,
                  discussion_guide_id: str | None = None,
                  codebook_id: str | None = None,
                  declaration_by_user: str | None = None,
                  created_utc: str | None = None) -> StudyContext:
    safe_component(context_id, field="context_id")
    status, thematic, reasons = classify_comparability(
        source_type=source_type, human_set_id=human_set_id,
        synthetic_set_ids=synthetic_set_ids,
        declaration_by_user=declaration_by_user, codebook_id=codebook_id)
    return StudyContext(
        context_id=context_id, project_id=project_id, study_name=study_name,
        source_type=source_type, synthetic_set_ids=list(synthetic_set_ids or []),
        human_set_id=human_set_id, discussion_guide_id=discussion_guide_id,
        codebook_id=codebook_id, comparability_status=status,
        thematic_status=thematic, comparability_reasons=reasons,
        declaration_by_user=declaration_by_user,
        created_utc=created_utc or _now())


def frozen_benchmark_context() -> StudyContext:
    """The one context that may use the frozen human referent. Never persisted."""
    return build_context(
        context_id="frozen-benchmark", study_name="Macho Meals (thesis benchmark)",
        source_type=SourceType.FROZEN_BENCHMARK.value,
        human_set_id="frozen-human-fg1-fg5",
        synthetic_set_ids=["frozen-enriched", "frozen-demographics-only"],
        created_utc="frozen")


# ------------------------------------------------------------------ persistence
def contexts_dir(project_root: Path) -> Path:
    return safe_path(safe_path(project_root, "derived"), CONTEXTS_DIRNAME)


def save_context(context: StudyContext, project_root: Path) -> Path:
    if context.source_type == SourceType.FROZEN_BENCHMARK.value:
        raise ContextError(
            "the frozen benchmark context is not stored in a project: it describes "
            "read-only artefacts and must not become editable project state")
    directory = contexts_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    target = safe_path(directory, f"{context.context_id}.json")
    atomic_write_text(target,
                      json.dumps(context.to_dict(), indent=1, ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def load_context(context_id: str, project_root: Path) -> StudyContext:
    safe_component(context_id, field="context_id")
    target = safe_path(contexts_dir(project_root), f"{context_id}.json",
                       must_exist=True)
    raw = json.loads(target.read_text(encoding="utf-8"))
    context = StudyContext(**raw)
    if context.source_type == SourceType.FROZEN_BENCHMARK.value:
        raise ContextError(
            f"{target}: a stored context claims source_type FROZEN_BENCHMARK. Only "
            f"the built-in benchmark may carry that type; refusing to grant the "
            f"frozen human referent to project state")
    # Recompute rather than trust: an edited file must not be able to promote itself.
    status, thematic, reasons = classify_comparability(
        source_type=context.source_type, human_set_id=context.human_set_id,
        synthetic_set_ids=context.synthetic_set_ids,
        declaration_by_user=context.declaration_by_user,
        codebook_id=context.codebook_id)
    context.comparability_status = status
    context.thematic_status = thematic
    context.comparability_reasons = reasons
    return context


def list_contexts(project_root: Path) -> list[StudyContext]:
    directory = contexts_dir(project_root)
    if not directory.is_dir():
        return []
    out = []
    for child in sorted(directory.glob("*.json")):
        try:
            out.append(load_context(child.stem, project_root))
        except (ContextError, json.JSONDecodeError, TypeError):
            continue
    return out
