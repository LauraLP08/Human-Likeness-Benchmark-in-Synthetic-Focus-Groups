"""
The generation adapter.

THE BOUNDARY. This package speaks to the generation architecture through exactly one
public surface: `scripts/run_full_session.py`, invoked as a separate process with an
argument list. It does not import `core.orchestrator`, `core.participant_agent` or
`core.moderator_brain`; it touches no private attribute of `core`; it reuses no part
of the old `ui/backend`; and it never calls a model provider itself.

A source scan in the test suite enforces every one of those, because a boundary that
is only a convention stops being a boundary the first time someone is in a hurry.
"""
from __future__ import annotations

from . import (bundle, config_builder, contracts, credentials,
               effective_config, importer, launcher, monitor, planner,
               preflight, pricing_ledger, profiles_source, queue,
               terminal)

__all__ = ["contracts", "config_builder", "profiles_source", "planner",
           "launcher", "monitor", "importer", "terminal", "bundle",
           "effective_config", "credentials", "preflight", "queue",
           "pricing_ledger"]
