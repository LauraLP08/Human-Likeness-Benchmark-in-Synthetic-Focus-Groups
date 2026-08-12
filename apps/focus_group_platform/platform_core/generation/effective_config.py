"""
The resolved effective configuration, and the architecture hash that pins it.

WHAT CHANGED AND WHY. Phase 3D deliberately omitted public keys the CLI defaults, so a
later architecture change would reach older plans. That is good inheritance and bad
reproducibility: the same plan hash could run a different instrument next month. The
audit called it right.

The fix is not to hard-code the architecture's choices. It is to RECORD them: every
behaviourally relevant parameter is resolved to a value, with where the value came
from, and the whole thing is pinned to `architecture_code_manifest_hash`. If the
architecture changes, the hash changes, and the plan blocks until a human reconfirms
it. Inheritance still happens - it just cannot happen silently.

Four provenances:

    USER_SELECTED                 the researcher chose it
    PROFILE_SELECTED              it comes from the agent payload (participant model)
    ARCHITECTURE_DEFAULT_RESOLVED the architecture's default, RECORDED WITH ITS VALUE
    PLAN_FIXED                    the plan set it (session id, guide, max turns)

WHAT THIS IS NOT. Recording that the architecture defaults a token cap is not the same
as imposing one. Nothing here sets a response length in words, dictates content or
prescribes a style. Those remain the model's, which is a methodological commitment of
the thesis and not a UI preference.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import REPO_ROOT
from ..provenance import APPLICATION_VERSION

USER_SELECTED = "USER_SELECTED"
PROFILE_SELECTED = "PROFILE_SELECTED"
ARCHITECTURE_DEFAULT_RESOLVED = "ARCHITECTURE_DEFAULT_RESOLVED"
PLAN_FIXED = "PLAN_FIXED"

# The architecture files whose content decides how a session behaves. The hash over
# these is what a plan is pinned to.
ARCHITECTURE_FILES = (
    "core/__init__.py",
    "core/config.py",
    "core/moderator_brain.py",
    "core/orchestrator.py",
    "core/participant_agent.py",
    "core/prompt_renderer.py",
    "core/session_state.py",
    "scripts/run_full_session.py",
)

# Defaults the architecture applies when a key is absent. Declared here WITH THEIR
# VALUES so the effective configuration is complete, and pinned by the architecture
# hash so a change in the architecture invalidates the pin rather than passing
# unnoticed. These are read from the public code at pin time; they are not the
# platform's opinion about how a session should run.
ARCHITECTURE_DEFAULTS = {
    "moderator_model": "claude-sonnet-4-6",
    "participant_model": "claude-haiku-4-5-20251001",
    "temperature": 1.0,
    "participation_mode": "orchestrated",
    "moderator_context_mode": "full",
    "moderator_reflection_enabled": False,
    "time_budget_tracking_enabled": False,
    "max_turns": 90,
}

# Public keys the platform may write. Anything else stays with the architecture.
BEHAVIOURAL_KEYS = (
    "moderator_model", "participant_model", "temperature", "participation_mode",
    "moderator_context_mode", "moderator_reflection_enabled",
    "time_budget_tracking_enabled", "max_turns", "guide", "profiles",
)


def architecture_code_manifest_hash(repo_root: Path | None = None) -> str:
    """
    One hash over the architecture that actually runs a session.

    Missing files are recorded as such rather than skipped: a file that disappears is
    a change, and a hash that ignored it would say nothing happened.
    """
    root = repo_root or REPO_ROOT
    digest = hashlib.sha256()
    for relative in ARCHITECTURE_FILES:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes() if path.is_file() else b"__MISSING__")
    return digest.hexdigest()


def architecture_manifest_detail(repo_root: Path | None = None) -> list[dict]:
    root = repo_root or REPO_ROOT
    out = []
    for relative in ARCHITECTURE_FILES:
        path = root / relative
        out.append({
            "relative_path": relative, "present": path.is_file(),
            "sha256": (hashlib.sha256(path.read_bytes()).hexdigest()
                       if path.is_file() else None)})
    return out


@dataclass
class ResolvedValue:
    name: str
    value: object
    provenance: str
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EffectiveConfiguration:
    session_id: str
    plan_id: str
    values: list[ResolvedValue] = field(default_factory=list)
    per_agent_models: dict = field(default_factory=dict)
    architecture_code_manifest_hash: str = ""
    architecture_files: list[dict] = field(default_factory=list)
    application_version: str = APPLICATION_VERSION
    config_sha256: str = ""
    command: list[str] = field(default_factory=list)
    note: str = (
        "every behaviourally relevant parameter is resolved to a VALUE here, with "
        "where that value came from. Recording a resolved default is not the same as "
        "imposing one: no response length, content or style is fixed by this "
        "platform.")

    def value(self, name: str):
        for item in self.values:
            if item.name == name:
                return item
        return None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(self.reproducibility_body(), sort_keys=True,
                       ensure_ascii=False).encode("utf-8")).hexdigest()

    def reproducibility_body(self) -> dict:
        """
        Everything that decides behaviour - and nothing that does not.

        The command line and the application version are excluded: a different
        interpreter path is not a different instrument, and including it would make
        the same plan look changed on another machine.
        """
        return {
            "session_id": self.session_id,
            "values": {v.name: v.value for v in self.values},
            "per_agent_models": self.per_agent_models,
            "architecture_code_manifest_hash":
                self.architecture_code_manifest_hash,
            "config_sha256": self.config_sha256,
        }

    def to_dict(self) -> dict:
        d = asdict(self)
        d["values"] = [v.to_dict() for v in self.values]
        d["effective_config_sha256"] = self.sha256
        return d


def resolve(study, *, session_id: str, plan_id: str, config: dict,
            profiles: list[dict], config_sha256: str,
            command: list[str] | None = None,
            repo_root: Path | None = None) -> EffectiveConfiguration:
    """
    Resolve every behavioural parameter for one session.

    `profiles` are the parsed agent payloads, so the participant model can be read
    from `simulation_config.model` where the architecture reads it - and marked
    PROFILE_SELECTED rather than pretended to be a platform choice.
    """
    values: list[ResolvedValue] = []

    def record(name, value, provenance, note=""):
        values.append(ResolvedValue(name=name, value=value, provenance=provenance,
                                    note=note))

    record("session_id", session_id, PLAN_FIXED)
    record("max_turns", study.max_turns, PLAN_FIXED,
           "passed on the command line as --max-turns")
    record("participation_mode", config.get(
        "participation_mode", ARCHITECTURE_DEFAULTS["participation_mode"]),
        USER_SELECTED if "participation_mode" in config
        else ARCHITECTURE_DEFAULT_RESOLVED)
    record("moderator_model", config.get(
        "moderator_model", ARCHITECTURE_DEFAULTS["moderator_model"]),
        USER_SELECTED if "moderator_model" in config
        else ARCHITECTURE_DEFAULT_RESOLVED)
    record("temperature", config.get("temperature",
                                     ARCHITECTURE_DEFAULTS["temperature"]),
           USER_SELECTED if "temperature" in config
           else ARCHITECTURE_DEFAULT_RESOLVED)

    for name in ("moderator_context_mode", "moderator_reflection_enabled",
                 "time_budget_tracking_enabled"):
        record(name, config.get(name, ARCHITECTURE_DEFAULTS[name]),
               USER_SELECTED if name in config else ARCHITECTURE_DEFAULT_RESOLVED)

    per_agent: dict[str, dict] = {}
    for payload in profiles:
        agent_id = str(payload.get("agent_id", ""))
        simulation = payload.get("simulation_config") or {}
        model = simulation.get("model")
        per_agent[agent_id] = {
            "model": model or ARCHITECTURE_DEFAULTS["participant_model"],
            "provenance": (PROFILE_SELECTED if model
                           else ARCHITECTURE_DEFAULT_RESOLVED),
            "max_tokens": simulation.get("max_tokens"),
            "max_tokens_provenance": (PROFILE_SELECTED
                                      if simulation.get("max_tokens") is not None
                                      else ARCHITECTURE_DEFAULT_RESOLVED),
            "max_tokens_note": ("a ceiling the payload may set; it is not a target "
                                "length and no word count is imposed"),
        }
    record("participant_models", per_agent,
           PROFILE_SELECTED if per_agent else ARCHITECTURE_DEFAULT_RESOLVED,
           "read from each agent payload's simulation_config, where the "
           "architecture reads it")

    record("guide_sections", len(config.get("discussion_guide") or []), PLAN_FIXED)
    record("n_participants", len(config.get("participants") or []), PLAN_FIXED)

    return EffectiveConfiguration(
        session_id=session_id, plan_id=plan_id, values=values,
        per_agent_models=per_agent,
        architecture_code_manifest_hash=architecture_code_manifest_hash(repo_root),
        architecture_files=architecture_manifest_detail(repo_root),
        config_sha256=config_sha256, command=list(command or []))
