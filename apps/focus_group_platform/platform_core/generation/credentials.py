"""
Credential preflight, per provider.

WHAT WAS WRONG. The dry-run accepted "a `.env` exists at the repository root" as
evidence that the run could authenticate. An empty `.env`, or one holding an unrelated
key, passed the check and the failure surfaced only after the first session had
started and the first call had been refused.

Now: the required providers are derived from the models actually resolved - the
moderator's and each agent's - and the check is whether THOSE providers' variables
hold a non-empty value, in the environment or in a safely parsed `.env`.

THE VALUE IS NEVER TOUCHED. Not shown, not stored, not hashed, not exported. Hashing
would be the subtle mistake: a hash of a short secret is a lookup away from the
secret, and a report that carried one would leak it into every export.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import REPO_ROOT

PRESENT = "PRESENT"
MISSING = "MISSING"

ENVIRONMENT = "environment"
DOTENV = "dotenv"
ABSENT = "absent"

# Model prefix -> provider. Unknown prefixes produce an UNKNOWN provider that the
# researcher must resolve, rather than a silent assumption of Anthropic.
PROVIDER_BY_PREFIX = (
    ("claude-", "anthropic"),
    ("gpt-", "openai"),
    ("o1-", "openai"),
    ("o3-", "openai"),
    ("gemini-", "google"),
)

REQUIRED_VARIABLES = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "google": ("GOOGLE_API_KEY",),
}


def provider_for_model(model: str) -> str:
    name = (model or "").strip().lower()
    for prefix, provider in PROVIDER_BY_PREFIX:
        if name.startswith(prefix):
            return provider
    return "unknown"


def parse_dotenv(path: Path) -> dict[str, str]:
    """
    A minimal, safe `.env` reader: `KEY=VALUE` lines only.

    Nothing is executed, no shell expansion happens, and `export` prefixes and
    surrounding quotes are handled. A malformed line is skipped, not guessed at.
    """
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip("'\"")
        if name:
            out[name] = value
    return out


@dataclass
class ProviderRequirement:
    provider: str
    required_variables: list[str]
    status: str
    source: str
    used_by: list[str] = field(default_factory=list)
    missing_variables: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == PRESENT

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CredentialReport:
    requirements: list[ProviderRequirement] = field(default_factory=list)
    dotenv_path: str = ""
    dotenv_present: bool = False
    note: str = ("presence only. No credential value is read into a report, stored, "
                 "hashed, displayed or exported.")

    @property
    def ok(self) -> bool:
        return bool(self.requirements) and all(r.ok for r in self.requirements)

    @property
    def missing(self) -> list[ProviderRequirement]:
        return [r for r in self.requirements if not r.ok]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        return d


def required_providers(*, moderator_model: str,
                       agent_models: dict[str, str]) -> dict[str, list[str]]:
    """provider -> what needs it, so a missing key names the thing that will fail."""
    out: dict[str, list[str]] = {}
    if moderator_model:
        out.setdefault(provider_for_model(moderator_model), []).append(
            f"moderator ({moderator_model})")
    for agent_id, model in sorted(agent_models.items()):
        out.setdefault(provider_for_model(model), []).append(
            f"{agent_id} ({model})")
    return out


def check(*, moderator_model: str, agent_models: dict[str, str],
          env: dict | None = None, dotenv_path: Path | None = None
          ) -> CredentialReport:
    environ = os.environ if env is None else env
    path = dotenv_path if dotenv_path is not None else (REPO_ROOT / ".env")
    dotenv = parse_dotenv(path)

    report = CredentialReport(dotenv_path=str(path), dotenv_present=path.is_file())
    for provider, used_by in sorted(required_providers(
            moderator_model=moderator_model, agent_models=agent_models).items()):
        variables = list(REQUIRED_VARIABLES.get(provider, ()))
        if not variables:
            report.requirements.append(ProviderRequirement(
                provider=provider, required_variables=[], status=MISSING,
                source=ABSENT, used_by=used_by,
                missing_variables=["unknown provider: the platform cannot tell "
                                   "which credential this model needs"]))
            continue

        missing, source = [], ABSENT
        for name in variables:
            if (environ.get(name) or "").strip():
                source = ENVIRONMENT
            elif (dotenv.get(name) or "").strip():
                source = DOTENV if source == ABSENT else source
            else:
                missing.append(name)
        report.requirements.append(ProviderRequirement(
            provider=provider, required_variables=variables,
            status=MISSING if missing else PRESENT,
            source=source if not missing else ABSENT,
            used_by=used_by, missing_variables=missing))
    return report
