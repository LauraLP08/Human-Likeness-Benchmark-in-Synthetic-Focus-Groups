"""
Application services.

The layer between the interface and the domain modules. Everything the interface
needs - reading the frozen benchmark, importing a transcript, running Level 2,
building an export - happens here, so the interface holds no normalisation, no metric
computation, no aggregation, no methodological rule and no direct read of a protected
artefact.

Nothing in this package imports Streamlit. That is the test: every service can be
called from a script, a CLI or a future API, and the whole layer is exercised by the
test suite without a browser.
"""
from __future__ import annotations

from . import (audit, benchmark_service, design_service, export_service,
               import_service, structural_service)
from .context import (ComparabilityStatus, SourceType, StudyContext,
                      classify_comparability)

__all__ = ["audit", "benchmark_service", "design_service", "export_service",
           "import_service", "structural_service", "StudyContext", "SourceType",
           "ComparabilityStatus", "classify_comparability"]
