"""
Light checks on the Streamlit layer.

Deliberately small. The point of the services layer is that the methodology is tested
without a browser; these tests only confirm that the app starts, that the three views
exist, and that the thin-layer rule has not quietly been broken.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR.parent) not in sys.path:
    sys.path.insert(0, str(APP_DIR.parent))

streamlit = pytest.importorskip("streamlit")


def test_the_application_imports_and_exposes_its_views():
    from app import streamlit_app
    assert list(streamlit_app.VIEWS) == ["Home / Projects", "Frozen benchmark",
                                         "New evaluation",
                                         "Generate focus groups"]
    for module in streamlit_app.VIEWS.values():
        assert callable(module.render)


def test_the_app_renders_with_streamlits_own_test_harness():
    """`AppTest` runs the script without a browser and surfaces any exception."""
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=90)
    app.run()
    assert not app.exception, [str(e) for e in app.exception]
    assert app.title[0].value == "Synthetic focus group platform"


def test_the_frozen_benchmark_view_renders():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=180)
    app.run()
    app.sidebar.radio[0].set_value("Frozen benchmark").run()
    assert not app.exception, [str(e) for e in app.exception]
    assert app.title[0].value.startswith("Frozen benchmark")
    assert not app.error, [e.value for e in app.error]


def test_a_navigation_button_actually_changes_the_view():
    """
    Regression. The sidebar radio used to keep its own copy of the current view, so
    once it had been touched the "Open frozen benchmark" button silently did nothing.
    One session key now holds the view; both controls write it.
    """
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=180)
    app.run()
    app.sidebar.radio[0].set_value("Home / Projects").run()      # touch the radio
    assert app.title[0].value == "Synthetic focus group platform"

    next(b for b in app.button if "frozen benchmark" in b.label.lower()).click().run()
    assert not app.exception, [str(e) for e in app.exception]
    assert app.title[0].value.startswith("Frozen benchmark")
    assert app.session_state["nav"] == "Frozen benchmark"


def test_the_new_evaluation_view_renders_without_a_project():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=90)
    app.run()
    app.sidebar.radio[0].set_value("New evaluation").run()
    assert not app.exception, [str(e) for e in app.exception]
    assert app.title[0].value == "New evaluation"


def test_the_words_per_turn_axis_keeps_the_service_order():
    """
    Regression. Streamlit's built-in bar chart sorts a categorical axis
    alphabetically, which put `100-199w` between `10-24w` and `200-249w` - an axis
    that reads as a bimodal corpus when it is not. The chart must pin the order the
    service returned.
    """
    from app import ui
    from platform_core.services import benchmark_service as B

    distribution = B.level2_words_per_turn()
    data, ordered = ui._long_frame(distribution["bins"], distribution["series"])
    assert list(dict.fromkeys(data["bin"])) == distribution["bins"]
    assert sorted(distribution["bins"]) != distribution["bins"]   # they differ
    assert [c for c in ordered] == ["human", "enriched", "demographics-only"]


# ------------------------------------------------- the thin-layer rule holds
FORBIDDEN_IN_VIEWS = {
    # normalisation, metric computation, aggregation, frozen artefact reads
    "normalise_transcript", "run_level2", "compute_structural_metrics",
    "load_frozen_metric_rows", "load_frozen_distributions",
    "aggregate_words_per_turn", "aggregate_focus_group_condition",
    "aggregate_study_replicates", "check_integrity", "frozen_workbook_route",
    "primary_results", "recurrence_across_focus_groups", "verify_sources",
    "classify_comparability",
}


def _view_files():
    return sorted(APP_DIR.rglob("*.py"))


def test_no_interface_file_computes_a_metric_or_reads_a_frozen_artefact():
    for path in _view_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called = {node.func.attr if isinstance(node.func, ast.Attribute)
                  else getattr(node.func, "id", None)
                  for node in ast.walk(tree) if isinstance(node, ast.Call)}
        leaked = called & FORBIDDEN_IN_VIEWS
        assert not leaked, f"{path.name} calls {sorted(leaked)} directly"


def test_no_interface_file_opens_a_repository_path():
    for path in _view_files():
        text = path.read_text(encoding="utf-8")
        assert "analysis/production_evaluation" not in text, path.name
        assert "REPO_ROOT" not in text, path.name


def test_no_interface_file_defines_its_own_condition_colour():
    """Colours come from platform_core.theme, never from a local literal."""
    import re
    for path in _view_files():
        text = path.read_text(encoding="utf-8")
        if path.name == "ui.py":
            # ui.py renders a legend; its only literal is the neutral caption grey.
            hexes = set(re.findall(r"#[0-9a-fA-F]{6}", text)) - {"#64748b"}
        else:
            hexes = set(re.findall(r"#[0-9a-fA-F]{6}", text))
        assert not hexes, f"{path.name} hard-codes {sorted(hexes)}"


def test_no_network_client_is_reachable_from_the_interface():
    for path in _view_files():
        text = path.read_text(encoding="utf-8")
        for forbidden in ("requests", "httpx", "urllib", "anthropic", "openai",
                          "google.genai", "subprocess", "socket"):
            assert forbidden not in text, (path.name, forbidden)
