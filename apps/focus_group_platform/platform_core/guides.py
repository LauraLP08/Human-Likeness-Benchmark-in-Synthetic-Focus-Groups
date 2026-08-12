"""
Guide compiler: YAML (editable source) -> `discussion_guide` JSON (what executes).

ADR-003. The YAML is NOT what runs. `core/orchestrator.py::_build_state_from_config`
reads `session_config["discussion_guide"]`, an inline array. The project has already
suffered one drift between the two representations, so this compiler exists to make
drift detectable rather than possible.

Section mapping mirrors `scripts/run_batch.py::_load_guide_sections`, which is the
behaviour the repository already executes. Derived from it deliberately; not imported,
because that function hard-codes one guide path.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .atomic import OnExists, atomic_write_text
from .frozen import assert_writable, is_frozen
from .paths import PathValidationError, safe_component, safe_path
from .provenance import GUIDE_COMPILER_VERSION

# core.session_state.SectionPhase
VALID_PHASES = ("intro", "context", "main_topic", "stimulus", "closing")

# Krueger-format interview schedules, as documented in the project's own guide header.
KRUEGER_PHASE_HINTS = {
    "opening": "intro",
    "introductory": "context",
    "transition": "context",
    "key": "main_topic",
    "stimulus task": "stimulus",
    "ending": "closing",
    "closing": "closing",
}

REQUIRED_TOP_LEVEL = ("guide_id", "title", "sections")
REQUIRED_SECTION = ("label", "phase", "scripted_question")


class GuideError(ValueError):
    pass


@dataclass
class GuideProblem:
    section_index: int | None
    field_path: str
    message: str
    blocking: bool = True


@dataclass
class GuideValidation:
    errors: list[GuideProblem] = field(default_factory=list)
    warnings: list[GuideProblem] = field(default_factory=list)
    phases_used: list[str] = field(default_factory=list)
    unmapped_phases: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class CompiledGuide:
    guide_id: str
    storage_name: str
    sections: list[dict]
    source_yaml_sha256: str
    compiled_json_sha256: str
    compiler_version: str
    compiled_at: str
    validation: GuideValidation
    source_yaml_path: str | None = None
    compiled_json_path: str | None = None

    @property
    def section_count(self) -> int:
        return len(self.sections)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compiled_json_text(sections: list[dict]) -> str:
    """
    The canonical serialisation of the compiled guide.

    Deterministic by construction: fixed key order per section (insertion order is
    fixed by the compiler), no timestamps inside the payload, no locale-dependent
    formatting. Two compilations of the same bytes in different processes produce the
    same string, and therefore the same hash.
    """
    return json.dumps(sections, ensure_ascii=False, separators=(",", ":"))


def validate_guide(raw: dict) -> GuideValidation:
    v = GuideValidation()

    for key in REQUIRED_TOP_LEVEL:
        if key not in raw:
            v.errors.append(GuideProblem(None, key, f"missing top-level key {key!r}"))

    # guide_id becomes a file name, so it is validated BEFORE anything is compiled or
    # written, and an invalid one is a localised error rather than a silent rewrite
    # (ADR-008).
    if "guide_id" in raw:
        try:
            safe_component(str(raw["guide_id"]), field="guide_id")
        except PathValidationError as exc:
            v.errors.append(GuideProblem(None, "guide_id", str(exc)))

    sections = raw.get("sections")
    if sections is None:
        return v
    if not isinstance(sections, list) or not sections:
        v.errors.append(GuideProblem(None, "sections",
                                     "sections must be a non-empty list"))
        return v

    for idx, sec in enumerate(sections):
        if not isinstance(sec, dict):
            v.errors.append(GuideProblem(idx, "section",
                                         "section must be a mapping"))
            continue
        for key in REQUIRED_SECTION:
            if not sec.get(key):
                v.errors.append(GuideProblem(idx, key,
                                             f"missing or empty {key!r}"))
        phase = sec.get("phase")
        if phase is not None:
            v.phases_used.append(str(phase))
            if phase not in VALID_PHASES:
                hint = KRUEGER_PHASE_HINTS.get(str(phase).lower())
                suffix = (f" Krueger-format mapping: {phase} -> {hint}."
                          if hint else "")
                v.unmapped_phases.append(str(phase))
                v.errors.append(GuideProblem(
                    idx, "phase",
                    f"phase {phase!r} is not a SectionPhase value "
                    f"{list(VALID_PHASES)}.{suffix}"))
        if not sec.get("suggested_probes"):
            v.warnings.append(GuideProblem(idx, "suggested_probes",
                                           "section has no suggested probes",
                                           blocking=False))
    return v


def compile_guide(raw: dict, source_yaml_text: str) -> CompiledGuide:
    """Validate then compile. A blocking error raises: nothing half-valid compiles."""
    validation = validate_guide(raw)
    if not validation.ok:
        first = validation.errors[0]
        raise GuideError(
            f"guide does not validate ({len(validation.errors)} error(s)); first: "
            f"section {first.section_index} field {first.field_path}: {first.message}")

    sections: list[dict] = []
    for idx, sec in enumerate(raw["sections"]):
        entry: dict = {
            "section_index": idx,
            "section_label": sec["label"],
            "section_phase": sec["phase"],
            "section_purpose": f"Section {idx}: {sec['label']}",
            "scripted_question": str(sec["scripted_question"]).strip(),
        }
        if probes := sec.get("suggested_probes"):
            entry["suggested_probes"] = list(probes)
        sections.append(entry)

    return CompiledGuide(
        guide_id=str(raw["guide_id"]),
        storage_name=safe_component(str(raw["guide_id"]), field="guide_id"),
        sections=sections,
        source_yaml_sha256=_sha(source_yaml_text),
        compiled_json_sha256=_sha(compiled_json_text(sections)),
        compiler_version=GUIDE_COMPILER_VERSION,
        compiled_at=datetime.now(UTC).isoformat(),
        validation=validation,
    )


def compile_guide_file(path: Path | str) -> CompiledGuide:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise GuideError(f"{p.name}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise GuideError(f"{p.name}: a guide must be a mapping")
    guide = compile_guide(raw, text)
    guide.source_yaml_path = str(p)
    return guide


def write_compiled(guide: CompiledGuide, out_dir: Path, *,
                   on_exists: OnExists = OnExists.FAIL) -> Path:
    out_dir = Path(out_dir)
    assert_writable(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = safe_path(out_dir, f"{guide.storage_name}.discussion_guide.json")
    assert_writable(target)
    atomic_write_text(target, compiled_json_text(guide.sections),
                      on_exists=on_exists,
                      verify=lambda written: json.loads(written))
    guide.compiled_json_path = str(target)
    return target


def check_correspondence(source_yaml_path: Path | str,
                         compiled_json_path: Path | str,
                         expected_compiled_sha256: str) -> tuple[bool, str | None]:
    """
    Recompile the stored YAML and compare against the stored compiled artefact.

    Three ways to fail, all of them blocking: the compiled file on disk was edited,
    the YAML was edited without recompiling, or the compiler version moved. A warning
    is not enough here - a warning is what the project already had when the two
    representations drifted.
    """
    src = Path(source_yaml_path)
    dst = Path(compiled_json_path)
    if not src.is_file():
        return False, f"source YAML missing: {src}"
    if not dst.is_file():
        return False, f"compiled JSON missing: {dst}"

    on_disk = dst.read_text(encoding="utf-8")
    on_disk_sha = _sha(on_disk)
    if on_disk_sha != expected_compiled_sha256:
        return False, ("the compiled JSON on disk does not match its recorded hash; "
                       "it was edited outside the compiler")

    recompiled = compile_guide_file(src)
    if recompiled.compiled_json_sha256 != expected_compiled_sha256:
        return False, ("recompiling the source YAML does not reproduce the compiled "
                       "artefact; the YAML changed after compilation")
    return True, None


def frozen_config_exempt(config_path: Path | str) -> bool:
    """
    Frozen experiment configs are executed as-is (ADR-003).

    Their `discussion_guide` array is the artefact of record. The application does not
    recompile them and does not compare them against `configs/guides/*.yaml`.
    """
    return is_frozen(Path(config_path))


def discussion_guide_from_config(config_path: Path | str) -> list[dict]:
    """Read an existing session config's `discussion_guide` array verbatim."""
    raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if "discussion_guide" not in raw:
        raise GuideError(f"{config_path}: no discussion_guide array")
    return raw["discussion_guide"]
