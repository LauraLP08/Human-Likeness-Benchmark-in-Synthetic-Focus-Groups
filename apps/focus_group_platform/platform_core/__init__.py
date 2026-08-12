"""
Focus group platform - service layer.

Importing this package creates NOTHING. No directory, no file, no user data. The data
directory is resolved lazily and only created on an explicit `ensure=True`
(ADR-005).

This package must never import `streamlit` (ADR-001); a test asserts it.

Phase 2A implements: configuration, paths, frozen-corpus protection, projects, the
metric catalogue and its eight-status model, profile loading and derived payloads, the
guide compiler, provenance hashing, and pricing schemas. Generation, transcripts,
matching, evaluation and reporting are not implemented yet.
"""
from __future__ import annotations

__all__ = [
    "catalog",
    "config",
    "frozen",
    "guides",
    "paths",
    "pricing",
    "profiles",
    "projects",
    "provenance",
]

__version__ = "0.1.0"
