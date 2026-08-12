"""
Profile loading, validation, canonicalisation and derived payloads.

JSON and YAML are both accepted (Amendment A). They express the same nested schema,
so a JSON file and a YAML file carrying the same information MUST produce the same
canonical hash - that equality is the contract, and it is tested.

CSV stays out: a flat table cannot carry per-field provenance without a column-mapping
layer, which is a separate contract.

Two rules that never bend:
  * the original file is never written;
  * an absent attribute stays undefined. The application does not invent values.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .atomic import OnExists, atomic_write_text
from .frozen import assert_writable
from .paths import PathValidationError, safe_component, safe_path
from .provenance import PROFILE_SCHEMA_VERSION

# Required by core.participant_agent.load_agent_from_json
REQUIRED_FIELDS = ("agent_id", "persona.demographics.name")
RECOMMENDED_FIELDS = ("persona.demographics.age", "persona.demographics.gender",
                      "simulation_config.model", "simulation_config.max_tokens")

# The existing payloads' provenance vocabulary, mapped onto the application's.
SOURCE_PROVENANCE_MAP = {
    "observed": "from_file",
    "observed_transcript_intro": "from_file",
    "derived": "transformed",
}

_SENSITIVE_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"),
    "phone": re.compile(r"(?<!\d)(?:\+?\d[\d ().-]{8,}\d)(?!\d)"),
    "uk_postcode": re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I),
    "national_id": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}
SENSITIVE_FIELD_TERMS = ("email", "phone", "address", "postcode", "nhs", "passport",
                         "national_insurance", "ssn", "dob", "date_of_birth")


class ProfileError(ValueError):
    pass


# --------------------------------------------------------------------- helpers
def canonical_json(payload: dict) -> str:
    """The one canonical serialisation. JSON and YAML must both reduce to this."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def canonical_sha256(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _get(payload: dict, dotted: str) -> Any:
    node: Any = payload
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set(payload: dict, dotted: str, value: Any) -> Any:
    parts = dotted.split(".")
    node = payload
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    previous = node.get(parts[-1])
    node[parts[-1]] = value
    return previous


def _flatten(payload: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(payload, dict):
        for k, v in payload.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    else:
        out[prefix] = payload
    return out


# ----------------------------------------------------------------- data model
@dataclass
class RunTransformation:
    field_path: str
    rule: str
    from_value: Any
    to_value: Any
    applied_at: str = ""

    def __post_init__(self):
        if not self.applied_at:
            self.applied_at = datetime.now(UTC).isoformat()


@dataclass
class SensitiveFinding:
    agent_id: str
    field_path: str
    pattern: str
    excerpt_masked: str


@dataclass
class ProfileRecord:
    agent_id: str
    storage_name: str                  # safe path component; never invented silently
    source_path: str
    source_format: str                 # json | yaml
    original_sha256: str
    canonical_sha256: str
    payload: dict
    field_provenance: dict[str, str] = field(default_factory=dict)
    undefined_fields: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    run_transformations: list[RunTransformation] = field(default_factory=list)
    # What the architecture will refuse at run time, not what the schema allows.
    architecture_problems: list[str] = field(default_factory=list)

    @property
    def declared_model(self) -> str | None:
        return _get(self.payload, "simulation_config.model")


@dataclass
class ProfileSetValidation:
    schema_ok: bool
    duplicate_ids: list[str]
    missing_required: list[dict]
    missing_recommended: list[dict]
    blocking: bool
    problems: list[str] = field(default_factory=list)


@dataclass
class ProfileSet:
    profiles: list[ProfileRecord]
    validation: ProfileSetValidation
    sensitive_findings: list[SensitiveFinding] = field(default_factory=list)
    schema_version: str = PROFILE_SCHEMA_VERSION

    @property
    def by_id(self) -> dict[str, ProfileRecord]:
        return {p.agent_id: p for p in self.profiles}



# ------------------------------------------------- architecture shape contract
# THE ONE PUBLIC VALIDATOR. Shapes the generation architecture requires of a payload,
# checked WITHOUT importing it. Found by the first real run: a `persona.background`
# written as a string passed schema validation and then crashed the session after six
# paid calls. Validating a schema is not the same as validating what the consumer will
# do with the payload, and having the check live in only one of the two entry points
# meant a profile could reach a paid run unchecked. Every profile that enters through
# `platform_core` now passes through here.
#
# NOT REPO-WIDE. `ui/backend/api.py`'s POST /start-session takes agent payloads
# straight from the HTTP body and constructs an orchestrator without consulting this
# function at all. That is a separate application with its own entry point; a payload
# posted there can still crash a session after billed calls.
def architecture_shape_problems(payload: dict) -> list[str]:
    """
    Only SHAPES THAT CRASH. Absent optional attributes are not problems.

    An earlier version of this function also demanded `age` and `gender`, because
    `core.participant_agent.load_agent_from_json`'s docstring lists them as required.
    The docstring is wrong about its own code: the loader does `if age is not None`
    and builds the identity line without them. That mistake refused 44 of the 123 agent
    payloads in this repository, including a whole study arm — profiles the
    architecture runs perfectly well. Validate against what the consumer DOES.
    """
    problems: list[str] = []
    persona = payload.get("persona")
    if not isinstance(persona, dict):
        return ["persona must be an object"]

    demographics = persona.get("demographics")
    if not isinstance(demographics, dict):
        problems.append("persona.demographics must be an object")
    else:
        # `name` only. It is the one demographic the architecture indexes rather than
        # tests for absence, and it is already in REQUIRED_FIELDS.
        if demographics.get("name") in (None, ""):
            problems.append("persona.demographics.name is missing; the participant "
                            "is identified by it")
        # `.get()` is called on this without a type check in three places in
        # `core.participant_agent`, including inside the loader that runs BEFORE the
        # first billed call.
        location = demographics.get("location")
        if location is not None and not isinstance(location, dict):
            problems.append(
                f"persona.demographics.location must be an object with "
                f"urban_rural/region/country, not {type(location).__name__}")

    for key in ("background", "food_consumption"):
        value = persona.get(key)
        if value is not None and not isinstance(value, dict):
            problems.append(
                f"persona.{key} must be an object of labelled entries, not "
                f"{type(value).__name__}; the participant prompt iterates its items")

    # A top-level sibling of `persona`. The prompt builder calls `.items()` on it, then
    # `.get("value")` on each entry, then `float()` on that - three crash sites.
    psychometric = payload.get("psychometric_scores")
    if psychometric is not None:
        if not isinstance(psychometric, dict):
            problems.append(
                f"psychometric_scores must be an object keyed by dimension, not "
                f"{type(psychometric).__name__}; the prompt builder iterates its items")
        else:
            for dimension, entry in psychometric.items():
                if not isinstance(entry, dict):
                    problems.append(
                        f"psychometric_scores.{dimension} must be an object with "
                        f"`value` and `direction`, not {type(entry).__name__}")
                    continue
                value = entry.get("value")
                if value is not None and not isinstance(value, (int, float)):
                    problems.append(
                        f"psychometric_scores.{dimension}.value must be a number, "
                        f"not {type(value).__name__}; it is passed to float()")

    intro = payload.get("opening_intro")
    if intro is not None and not isinstance(intro, dict):
        problems.append(
            f"opening_intro must be an object, not {type(intro).__name__}; it is read "
            f"with .get() when participant intros are injected")

    simulation = payload.get("simulation_config")
    if simulation is not None and not isinstance(simulation, dict):
        problems.append("simulation_config must be an object")
    return problems


# ------------------------------------------------------------------- loading
def load_profile_file(path: Path | str) -> ProfileRecord:
    """
    Load one profile from JSON or YAML. The file is only ever read.

    `original_sha256` hashes the bytes as supplied; `canonical_sha256` hashes the
    canonical JSON. Two files carrying the same information share the second and
    differ in the first - which is exactly what makes the equality testable.
    """
    p = Path(path)
    raw = p.read_bytes()
    suffix = p.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        fmt = "yaml"
        try:
            payload = yaml.safe_load(raw.decode("utf-8"))
        except yaml.YAMLError as exc:
            raise ProfileError(f"{p.name}: invalid YAML: {exc}") from exc
    elif suffix == ".json":
        fmt = "json"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ProfileError(f"{p.name}: invalid JSON: {exc}") from exc
    elif suffix == ".csv":
        raise ProfileError(
            f"{p.name}: CSV profiles are not supported. A flat table cannot carry "
            f"per-field provenance without a column-mapping layer, which is a "
            f"separate contract.")
    else:
        raise ProfileError(f"{p.name}: unsupported profile format {suffix!r}; "
                           f"expected .json, .yaml or .yml")

    if not isinstance(payload, dict):
        raise ProfileError(f"{p.name}: a profile must be a mapping, got "
                           f"{type(payload).__name__}")

    agent_id = payload.get("agent_id")
    if not agent_id or not isinstance(agent_id, str):
        raise ProfileError(f"{p.name}: missing or non-string agent_id")

    # agent_id is untrusted input that reaches file names, session ids and provenance
    # keys. It must satisfy the path-component contract; it is NEVER rewritten to
    # make it fit, because the substantive research identity would then differ from
    # what the researcher supplied (ADR-008).
    try:
        storage_name = safe_component(agent_id, field="agent_id")
    except PathValidationError as exc:
        raise ProfileError(f"{p.name}: {exc}") from exc

    record = ProfileRecord(
        agent_id=agent_id,
        storage_name=storage_name,
        source_path=str(p),
        source_format=fmt,
        original_sha256=hashlib.sha256(raw).hexdigest(),
        canonical_sha256=canonical_sha256(payload),
        payload=payload,
    )
    _apply_provenance(record)
    record.architecture_problems = architecture_shape_problems(payload)
    return record


def _apply_provenance(record: ProfileRecord) -> None:
    """
    Three-way provenance per field: from_file, transformed, undefined.

    The payload's own `field_provenance` map is honoured where present; every other
    concrete leaf is from_file; required and recommended fields that are absent are
    undefined and are NEVER filled in.
    """
    declared = record.payload.get("field_provenance") or {}
    provenance: dict[str, str] = {}

    for dotted, value in _flatten(record.payload).items():
        if dotted.startswith("field_provenance"):
            continue
        if value is None:
            provenance[dotted] = "undefined"
            record.undefined_fields.append(dotted)
        else:
            provenance[dotted] = "from_file"

    for dotted, source_value in declared.items():
        mapped = SOURCE_PROVENANCE_MAP.get(str(source_value))
        if mapped is None:
            continue
        for key in list(provenance):
            if key == dotted or key.startswith(dotted + "."):
                provenance[key] = mapped
        provenance.setdefault(dotted, mapped)

    for dotted in REQUIRED_FIELDS:
        if _get(record.payload, dotted) is None:
            record.missing_required.append(dotted)
            provenance[dotted] = "undefined"
            if dotted not in record.undefined_fields:
                record.undefined_fields.append(dotted)
    for dotted in RECOMMENDED_FIELDS:
        if _get(record.payload, dotted) is None:
            record.missing_recommended.append(dotted)
            provenance[dotted] = "undefined"
            if dotted not in record.undefined_fields:
                record.undefined_fields.append(dotted)

    record.field_provenance = dict(sorted(provenance.items()))
    record.undefined_fields = sorted(set(record.undefined_fields))


def scan_sensitive(record: ProfileRecord) -> list[SensitiveFinding]:
    findings: list[SensitiveFinding] = []
    for dotted, value in _flatten(record.payload).items():
        leaf = dotted.split(".")[-1].lower()
        if any(term in leaf for term in SENSITIVE_FIELD_TERMS):
            findings.append(SensitiveFinding(record.agent_id, dotted,
                                             "sensitive_field_name",
                                             _mask(str(value))))
            continue
        if not isinstance(value, str):
            continue
        for name, pattern in _SENSITIVE_PATTERNS.items():
            m = pattern.search(value)
            if m:
                findings.append(SensitiveFinding(record.agent_id, dotted, name,
                                                 _mask(m.group(0))))
    return findings


def _mask(text: str) -> str:
    text = text.strip()
    if len(text) <= 4:
        return "*" * len(text)
    return text[:2] + "*" * (len(text) - 4) + text[-2:]


def load_profile_set(paths: list[Path | str]) -> ProfileSet:
    records: list[ProfileRecord] = []
    problems: list[str] = []
    for path in paths:
        records.append(load_profile_file(path))

    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for r in records:
        if r.agent_id in seen:
            duplicates.append(r.agent_id)
            problems.append(
                f"duplicate agent_id {r.agent_id!r}: {seen[r.agent_id]} and "
                f"{r.source_path}")
        else:
            seen[r.agent_id] = r.source_path

    architecture_problems = [f"{r.agent_id}: {problem}"
                             for r in records for problem in r.architecture_problems]
    problems += architecture_problems

    missing_required = [{"agent_id": r.agent_id, "field": f}
                        for r in records for f in r.missing_required]
    missing_recommended = [{"agent_id": r.agent_id, "field": f}
                           for r in records for f in r.missing_recommended]
    if missing_required:
        problems.append(f"{len(missing_required)} required field(s) missing")

    validation = ProfileSetValidation(
        schema_ok=not missing_required,
        duplicate_ids=sorted(set(duplicates)),
        missing_required=missing_required,
        missing_recommended=missing_recommended,
        # An architecture-shape problem blocks. It is not a warning: the run would
        # reach the paid call and then fail.
        blocking=bool(duplicates or missing_required or architecture_problems),
        problems=problems,
    )
    findings = [f for r in records for f in scan_sensitive(r)]
    return ProfileSet(profiles=records, validation=validation,
                      sensitive_findings=findings)


# ------------------------------------------------------- derived payloads
@dataclass
class DerivedProfile:
    agent_id: str
    source_profile_path: str
    source_sha256: str
    derived_path: str
    derived_sha256: str
    run_transformations: list[RunTransformation]
    field_provenance: dict[str, str]


def derive_profile(record: ProfileRecord, out_dir: Path, *,
                   participant_model: str | None = None,
                   max_tokens: int | None = None,
                   on_exists: OnExists = OnExists.FAIL) -> DerivedProfile:
    """
    Write a derived copy with run-time overrides applied (ADR-007).

    The participant model lives at `agent_payload.simulation_config.model`
    (core/participant_agent.py lines 951, 964) - it is a property of the profile, not
    of the session. Changing it therefore requires a copy, never a mutation of the
    original.

    A derived payload differs from its source ONLY in the fields listed in
    `run_transformations`.
    """
    out_dir = Path(out_dir)
    assert_writable(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(json.dumps(record.payload))   # deep copy, no aliasing
    transformations: list[RunTransformation] = []
    provenance = dict(record.field_provenance)

    if participant_model is not None:
        previous = _set(payload, "simulation_config.model", participant_model)
        if previous != participant_model:
            transformations.append(RunTransformation(
                field_path="simulation_config.model",
                rule="study.participant_model applied to the derived payload",
                from_value=previous, to_value=participant_model))
            provenance["simulation_config.model"] = "transformed"

    if max_tokens is not None:
        previous = _set(payload, "simulation_config.max_tokens", max_tokens)
        if previous != max_tokens:
            transformations.append(RunTransformation(
                field_path="simulation_config.max_tokens",
                rule=("study.participant_response_max_tokens applied as a technical "
                      "ceiling, not a target length"),
                from_value=previous, to_value=max_tokens))
            provenance["simulation_config.max_tokens"] = "transformed"

    payload["_derived_from"] = {
        "source_path": record.source_path,
        "source_sha256": record.original_sha256,
        "source_canonical_sha256": record.canonical_sha256,
        "transformations": [t.__dict__ for t in transformations],
        "note": ("derived copy written by the focus group platform; the source file "
                 "was not modified"),
    }

    # The identifier never reaches the filesystem directly: the storage name is a
    # validated component and the join goes through safe_path (ADR-008).
    target = safe_path(out_dir, f"{record.storage_name}.json")
    assert_writable(target)
    text = json.dumps(payload, indent=1, ensure_ascii=False)
    atomic_write_text(target, text, on_exists=on_exists,
                      verify=lambda written: json.loads(written))

    return DerivedProfile(
        agent_id=record.agent_id,
        source_profile_path=record.source_path,
        source_sha256=record.original_sha256,
        derived_path=str(target),
        derived_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        run_transformations=transformations,
        field_provenance=provenance,
    )


def diff_payloads(a: dict, b: dict) -> list[str]:
    """Dotted paths whose values differ. Used to prove a derived copy is minimal."""
    fa, fb = _flatten(a), _flatten(b)
    keys = set(fa) | set(fb)
    return sorted(k for k in keys if fa.get(k) != fb.get(k))
