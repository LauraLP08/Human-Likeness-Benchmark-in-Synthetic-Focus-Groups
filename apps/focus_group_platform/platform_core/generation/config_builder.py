"""
Build the session config the existing CLI already accepts.

THE PLATFORM INVENTS NOTHING. Every key written here is one `core.orchestrator`
already reads; where the architecture has a default, the platform leaves the key out
rather than restating it, so a later change to the CLI's default reaches these runs
instead of being frozen at whatever this file happened to say.

`effective_config.json` records the provenance of every value:

    USER_PROVIDED   the researcher typed or uploaded it
    PLAN_FIXED      the plan set it (session_id, run_label, the guide)
    CLI_DEFAULT     deliberately absent from the config; the CLI supplies it

That third category is the point. A reader can see which numbers this platform chose
and which it declined to choose.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .contracts import (GenerationError, GenerationStudy, PUBLIC_CONFIG_KEYS,
                        REQUIRED_CONFIG_KEYS, sha256_json)

USER_PROVIDED = "USER_PROVIDED"
PLAN_FIXED = "PLAN_FIXED"
CLI_DEFAULT = "CLI_DEFAULT"

# Keys the architecture defaults for us. Listing them is documentation, not
# behaviour: they are omitted from the config on purpose.
CLI_DEFAULTS = {
    "temperature": "core.orchestrator default",
    "moderator_model": "core.orchestrator default (claude-sonnet-4-6)",
    "participant model": ("agent_payload.simulation_config.model, or the "
                          "participant_agent default"),
    "max_turns": "run_full_session.py --max-turns default (90)",
}


@dataclass
class BuiltConfig:
    session_id: str
    config: dict
    provenance: dict[str, str] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    agent_ids: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def sha256(self) -> str:
        return sha256_json(self.config)

    def effective_config(self, *, plan_id: str, cli_command: list[str]) -> dict:
        return {
            "session_id": self.session_id,
            "plan_id": plan_id,
            "config_sha256": self.sha256,
            "config": self.config,
            "value_provenance": self.provenance,
            "cli_defaults_not_overridden": CLI_DEFAULTS,
            "command": cli_command,
            "note": ("keys absent from `config` are supplied by the CLI; the "
                     "platform declines to restate a default it does not own"),
        }


def build_session_config(study: GenerationStudy, *, session_id: str,
                         run_label: str, participants: list[dict],
                         discussion_guide: list[dict],
                         override_temperature: bool = False) -> BuiltConfig:
    """
    One session's config. `participants` is already in the public shape.

    Each participant carries EXACTLY ONE of `agent_payload_path`, `agent_payload`, or
    the legacy `{id, name, profile_summary}` trio - mixing them inside one participant
    is refused, because the architecture would then have two sources for the same
    person and the precedence is not something the platform should be deciding.
    """
    provenance: dict[str, str] = {}
    problems: list[str] = []

    config: dict = {
        "session_id": session_id,
        "run_label": run_label,
        "research_objective": study.research_objective,
        "topic_domain": study.topic_domain,
        "participant_collective_identity": study.participant_collective_identity,
        "moderator_knowledge_brief": study.moderator_knowledge_brief,
        "participation_mode": study.participation_mode,
        "participants": participants,
        "discussion_guide": discussion_guide,
    }
    provenance.update({
        "session_id": PLAN_FIXED, "run_label": PLAN_FIXED,
        "research_objective": USER_PROVIDED, "topic_domain": USER_PROVIDED,
        "participant_collective_identity": USER_PROVIDED,
        "moderator_knowledge_brief": USER_PROVIDED,
        "participation_mode": USER_PROVIDED,
        "participants": USER_PROVIDED, "discussion_guide": PLAN_FIXED,
    })

    if study.researcher_notes:
        config["researcher_notes"] = study.researcher_notes
        provenance["researcher_notes"] = USER_PROVIDED
    if study.moderator_model:
        config["moderator_model"] = study.moderator_model
        provenance["moderator_model"] = USER_PROVIDED
    else:
        provenance["moderator_model"] = CLI_DEFAULT
    if override_temperature and study.temperature is not None:
        config["temperature"] = study.temperature
        provenance["temperature"] = USER_PROVIDED
    else:
        provenance["temperature"] = CLI_DEFAULT
    provenance["max_turns"] = PLAN_FIXED       # passed on the command line
    provenance["participant model"] = CLI_DEFAULT

    problems += _check_keys(config)
    agent_ids, participant_problems = _check_participants(participants)
    problems += participant_problems
    if not discussion_guide:
        problems.append("the discussion guide is empty")

    return BuiltConfig(session_id=session_id, config=config,
                       provenance=provenance, problems=problems,
                       agent_ids=agent_ids)


def _check_keys(config: dict) -> list[str]:
    problems = []
    for key in REQUIRED_CONFIG_KEYS:
        if key not in config or config[key] in (None, "", [], {}):
            problems.append(f"the config contract requires {key!r}")
    unknown = [k for k in config if k not in PUBLIC_CONFIG_KEYS]
    if unknown:
        problems.append(
            f"refusing to write key(s) {unknown} that are not part of the public "
            f"config contract; the platform does not extend the architecture's "
            f"interface")
    return problems


PARTICIPANT_FORMS = {
    "agent_payload_path": ("agent_payload_path",),
    "inline_agent_payload": ("agent_payload",),
    "legacy": ("id", "name", "profile_summary"),
}


def _check_participants(participants: list[dict]) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    agent_ids: list[str] = []
    if not participants:
        return [], ["a session needs at least one participant"]

    for index, participant in enumerate(participants):
        present = [name for name, keys in PARTICIPANT_FORMS.items()
                   if any(k in participant for k in keys)]
        if not present:
            problems.append(
                f"participant {index}: none of the accepted forms "
                f"({', '.join(PARTICIPANT_FORMS)}) is present")
            continue
        if len(present) > 1:
            problems.append(
                f"participant {index}: {present} are combined in one participant. "
                f"Exactly one form per participant - the architecture would "
                f"otherwise have two sources for the same person")
            continue
        form = present[0]
        if form == "legacy":
            missing = [k for k in PARTICIPANT_FORMS["legacy"]
                       if k not in participant]
            if missing:
                problems.append(f"participant {index}: legacy form is missing "
                                f"{missing}")
            agent_ids.append(str(participant.get("id", f"participant_{index}")))
        elif form == "agent_payload_path":
            path = str(participant["agent_payload_path"])
            agent_ids.append(path.rsplit("/", 1)[-1].removesuffix(".json"))
        else:
            payload = participant["agent_payload"]
            if not isinstance(payload, dict):
                problems.append(f"participant {index}: agent_payload is not an "
                                f"object")
                continue
            agent_ids.append(str(payload.get("agent_id", f"participant_{index}")))
    return agent_ids, problems


def serialise(config: dict) -> str:
    return json.dumps(config, indent=1, ensure_ascii=False)


def cli_command(*, python_executable: str, cli_path: str, config_path: str,
                max_turns: int, mode: str | None) -> list[str]:
    """
    The exact argument LIST. Never a string, never a shell.

    A command built by string concatenation and handed to a shell is how a path with
    a space, or a quote in a study name, becomes an arbitrary command. There is no
    code path in this application that passes `shell=True`.
    """
    command = [python_executable, cli_path, "--config", config_path,
               "--max-turns", str(int(max_turns))]
    if mode:
        command += ["--mode", mode]
    return command
