"""
Reconciliation of the simplified main figure against the curve artefacts.

The figure is a reader-facing simplification, which is exactly why it needs guarding:
a simplification is where a number quietly stops matching its source. Every plotted
value here is recomputed from `inductive_curves_v2_full.json` and, for Panel B, from
`inductive_endpoints_by_replicate.csv`, then compared.

The rules that shape each panel are asserted with planted violations:
  Panel A - per-realisation percentages, and Q4 holding its position-4 endpoint at
            position 5.
  Panel B - endpoints read from the authoritative table, and synthetic ranges never
            joined across questions, which would read as a confidence band.

Nothing here writes into the repository; renders go to tmp_path.

Offline; no API call.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "analysis/figures"))

import render_inductive_theme_accumulation_main as fig      # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/inductive_curves"
_FIGS = _ROOT / "analysis/figures"

# The seven realisations, exactly as the saturation section reports them.
VERIFIED_PCT = {
    ("human", 0): (79.4, 91.6),
    ("enriched", 0): (77.7, 91.6),
    ("enriched", 1): (72.2, 89.0),
    ("enriched", 2): (74.9, 90.0),
    ("demographics-only", 0): (71.0, 87.6),
    ("demographics-only", 1): (68.8, 85.6),
    ("demographics-only", 2): (72.9, 89.7),
}

# Panel B. Endpoints per guide question, as the authoritative table records them.
VERIFIED_ENDPOINTS = {
    "1": {"human": [9], "enriched": [5, 9, 9], "demographics-only": [8, 10, 8]},
    "2": {"human": [6], "enriched": [4, 10, 5], "demographics-only": [10, 6, 6]},
    "3": {"human": [4], "enriched": [9, 7, 9], "demographics-only": [7, 8, 5]},
    "4": {"human": [5], "enriched": [7, 7, 8], "demographics-only": [7, 4, 8]},
    "5": {"human": [7], "enriched": [6, 7, 7], "demographics-only": [10, 8, 8]},
}
VERIFIED_ENDPOINT_MEDIANS = {
    "1": {"human": 9, "enriched": 9, "demographics-only": 8},
    "2": {"human": 6, "enriched": 5, "demographics-only": 6},
    "3": {"human": 4, "enriched": 9, "demographics-only": 7},
    "4": {"human": 5, "enriched": 7, "demographics-only": 7},
    "5": {"human": 7, "enriched": 7, "demographics-only": 8},
}

# Moved off Panel B; retained in the caption table.
VERIFIED_MEDIAN_INCREMENTS = {
    "1": {"human": 1.4, "enriched": 1.2, "demographics-only": 1.4},
    "2": {"human": 0.6, "enriched": 0.6, "demographics-only": 1.2},
    "3": {"human": 0.4, "enriched": 1.0, "demographics-only": 0.8},
    "4": {"human": 0.5, "enriched": 1.25, "demographics-only": 1.0},
    "5": {"human": 0.2, "enriched": 0.8, "demographics-only": 1.2},
}

# Identifiers that belong in the caption and the traceability record, never on the face
# of a reader-facing figure.
TECHNICAL_IDS = ("LLM_ASSISTED_RETROSPECTIVE_OPEN_THEMATIC_ACCUMULATION",
                 "CANONICAL_RESOLVED_LOWER", "CANONICAL_MATHEMATICAL_MAXIMUM",
                 "STRICT_AGAINST_E1", "EXTENDED_E3", "mean_cumulative_by_position",
                 "mean_new_at_position")

PANEL_B_LEFT = 1010     # x where Panel B's plot area begins


@pytest.fixture(scope="module")
def full():
    return json.loads((_OUT / "inductive_curves_v2_full.json").read_text(
        encoding="utf-8"))


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    t = tmp_path_factory.mktemp("mainfig")
    png, csvp, pct, ends, inc = fig.render(t / "f.png", t / "f.csv")
    rows = list(csv.DictReader(csvp.open(encoding="utf-8")))
    return {"png": png, "csv": csvp, "rows": rows, "pct": pct, "ends": ends,
            "inc": inc}


# ------------------------------------------------------------------ Panel A
def test_panel_a_reproduces_the_seven_verified_realisations(rendered):
    for (cond, i), (e3, e4) in VERIFIED_PCT.items():
        rep = rendered["pct"][cond][i]
        assert abs(rep[2] - e3) < 0.05, f"{cond} R{i + 1} after 3 FGs"
        assert abs(rep[3] - e4) < 0.05, f"{cond} R{i + 1} after 4 FGs"


def test_panel_a_is_computed_from_the_curve_artefact_not_hard_coded(full, rendered):
    """Recompute from the JSON independently of the module and compare."""
    L = full[fig.SCENARIO]
    for cond in fig.CONDITIONS:
        for i in range(fig.N_REP[cond]):
            ep = sum(L[q][cond]["realisations"][i]["endpoint"] for q in "12345")
            for pos in range(5):
                tot = 0.0
                for q in "12345":
                    v = L[q][cond]["realisations"][i]["mean_cumulative_by_position"]
                    tot += v[min(pos, len(v) - 1)]
                assert abs(rendered["pct"][cond][i][pos] - 100 * tot / ep) < 1e-9


def test_every_realisation_ends_at_exactly_one_hundred_percent(rendered):
    """The endpoint is the definition of 100%, which is why it is not a saturation
    threshold. If any curve ended elsewhere the denominator would be wrong."""
    for cond in fig.CONDITIONS:
        for rep in rendered["pct"][cond]:
            assert abs(rep[-1] - 100.0) < 1e-6


def test_q4_holds_its_endpoint_at_position_five(full, rendered):
    """PLANTED: dropping Q4 from position 5 instead of holding it must change Panel A."""
    L = full[fig.SCENARIO]
    for cond in fig.CONDITIONS:
        for i in range(fig.N_REP[cond]):
            ep = sum(L[q][cond]["realisations"][i]["endpoint"] for q in "12345")
            dropped = sum(
                L[q][cond]["realisations"][i]["mean_cumulative_by_position"][4]
                for q in "1235")
            assert abs(100 * dropped / ep - rendered["pct"][cond][i][4]) > 1.0, (
                f"{cond} R{i + 1}: dropping Q4 must not reproduce the plotted value")


def test_q4_contributes_four_positions_and_the_others_five(full):
    L = full[fig.SCENARIO]
    for cond in fig.CONDITIONS:
        for r in L["4"][cond]["realisations"]:
            assert len(r["mean_cumulative_by_position"]) == 4
        for q in ("1", "2", "3", "5"):
            for r in L[q][cond]["realisations"]:
                assert len(r["mean_cumulative_by_position"]) == 5


def test_percentages_are_taken_within_a_realisation_not_across(full, rendered):
    """
    PLANTED: pooling first - summing all three replicates' cumulative counts over the
    pooled endpoint - must not reproduce the plotted synthetic curves.
    """
    L = full[fig.SCENARIO]
    for cond in ("enriched", "demographics-only"):
        pooled = []
        for pos in range(5):
            num = den = 0.0
            for i in range(3):
                for q in "12345":
                    v = L[q][cond]["realisations"][i]["mean_cumulative_by_position"]
                    num += v[min(pos, len(v) - 1)]
                    den += L[q][cond]["realisations"][i]["endpoint"]
            pooled.append(100 * num / den)
        median = [statistics.median(r[p] for r in rendered["pct"][cond])
                  for p in range(5)]
        assert any(abs(pooled[p] - median[p]) > 0.05 for p in (1, 2, 3)), (
            f"{cond}: the pooled construction must be distinguishable")


def test_the_three_synthetic_realisations_are_kept_separate(rendered):
    assert len(rendered["pct"]["human"]) == 1
    assert len(rendered["pct"]["enriched"]) == 3
    assert len(rendered["pct"]["demographics-only"]) == 3


# ------------------------------------------------------------------ Panel B
def test_panel_b_endpoints_come_from_the_authoritative_table(rendered):
    """Panel B must reconcile directly with `inductive_endpoints_by_replicate.csv`."""
    rows = [r for r in csv.DictReader(
        (_OUT / "inductive_endpoints_by_replicate.csv").open(encoding="utf-8"))
        if r["scenario"] == fig.SCENARIO]
    for q in "12345":
        for cond in fig.CONDITIONS:
            order = ["human"] if cond == "human" else ["R1", "R2", "R3"]
            m = {r["replicate"]: int(r["endpoint"]) for r in rows
                 if r["question"] == q and r["condition"] == cond}
            assert rendered["ends"][q][cond]["values"] == [m[k] for k in order], \
                f"Q{q} {cond}"


def test_panel_b_endpoints_match_the_verified_values(rendered):
    for q, exp in VERIFIED_ENDPOINTS.items():
        for cond, vals in exp.items():
            assert rendered["ends"][q][cond]["values"] == vals, f"Q{q} {cond}"


def test_panel_b_medians_match_the_verified_values(rendered):
    for q, exp in VERIFIED_ENDPOINT_MEDIANS.items():
        for cond, v in exp.items():
            assert rendered["ends"][q][cond]["median"] == v, f"Q{q} {cond}"


def test_the_endpoint_table_and_the_curve_json_agree(full, rendered):
    """Two artefacts carry these endpoints. A drift between them must fail here."""
    L = full[fig.SCENARIO]
    for q in "12345":
        for cond in fig.CONDITIONS:
            src = [r["endpoint"] for r in L[q][cond]["realisations"]]
            assert rendered["ends"][q][cond]["values"] == src, f"Q{q} {cond}"


def test_a_drift_between_the_two_endpoint_sources_is_detected(monkeypatch):
    """PLANTED: if the curve JSON disagreed with the table, the figure must not draw."""
    real = fig.load

    def bent():
        L = json.loads(json.dumps(real()))
        L["3"]["human"]["realisations"][0]["endpoint"] = 99
        return L

    monkeypatch.setattr(fig, "load", bent)
    with pytest.raises(ValueError, match="does not match the curve JSON"):
        fig.endpoints_by_question()


def test_the_annotated_spreads_are_the_ones_in_the_data(rendered):
    """
    The annotation states human 4-9 and demographics-only medians 6-8. If either range
    moved, the sentence on the figure would be false, so it is recomputed here.
    """
    human = [rendered["ends"][q]["human"]["median"] for q in "12345"]
    assert (min(human), max(human)) == (4, 9)
    demo = [rendered["ends"][q]["demographics-only"]["median"] for q in "12345"]
    assert (min(demo), max(demo)) == (6, 8)
    # The stated contrast: the human profile spans a wider range than the
    # demographics-only medians. This is descriptive of these values only.
    assert max(human) - min(human) > max(demo) - min(demo)


def test_the_exploratory_caveat_is_earned_by_replicate_level_variation(rendered):
    """
    The caveat says the pattern does not hold across every realisation. That must be
    true of the data: at least one synthetic replicate profile must span at least as
    wide a range as the human profile.
    """
    human = [rendered["ends"][q]["human"]["median"] for q in "12345"]
    hspan = max(human) - min(human)
    wide = 0
    for cond in ("enriched", "demographics-only"):
        for i in range(3):
            prof = [rendered["ends"][q][cond]["values"][i] for q in "12345"]
            if max(prof) - min(prof) >= hspan:
                wide += 1
    assert wide > 0, "no replicate profile is as uneven as the human one"


def test_the_panel_b_axis_contains_every_endpoint(rendered):
    """A clipped endpoint would understate a question's repertoire."""
    hi = max(rendered["ends"][q][c]["max"] for q in "12345" for c in fig.CONDITIONS)
    assert hi <= fig.B_YMAX, f"the 0-{fig.B_YMAX} axis would clip an endpoint at {hi}"


def test_an_endpoint_above_the_axis_is_rejected(tmp_path, monkeypatch):
    """PLANTED: silently drawing off-axis would misreport a repertoire."""
    real = fig.endpoints_by_question

    def bent():
        e = real()
        e["2"]["enriched"]["max"] = fig.B_YMAX + 1
        return e

    monkeypatch.setattr(fig, "endpoints_by_question", bent)
    with pytest.raises(ValueError, match="exceeds the axis"):
        fig.render(tmp_path / "x.png", tmp_path / "x.csv")


def test_only_the_human_series_is_connected_in_panel_b(tmp_path, monkeypatch):
    """
    Joining the synthetic points across questions would read as a band over a continuous
    variable. Guide questions are not ordered, and the ranges are not intervals, so only
    the human series is connected.
    """
    polylines = []
    orig = ImageDraw.ImageDraw.line

    def spy(self, xy, *a, **k):
        pts = list(xy)
        if pts and isinstance(pts[0], (tuple, list)) and len(pts) > 2:
            polylines.append((min(p[0] for p in pts), k.get("fill")))
        return orig(self, xy, *a, **k)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", spy)
    fig.render(tmp_path / "c.png", tmp_path / "c.csv")

    in_b = [c for x, c in polylines if x >= PANEL_B_LEFT]
    assert in_b, "Panel B must draw the connected human series"
    assert set(in_b) == {fig.COL["human"]}, (
        f"only the human series may be connected in Panel B; found {set(in_b)}")


# ------------------------------------------------------ caption-table increments
def test_the_final_increments_are_kept_in_the_caption_table(rendered):
    for q, exp in VERIFIED_MEDIAN_INCREMENTS.items():
        for cond, v in exp.items():
            assert round(rendered["inc"][q][cond]["median"], 2) == v, f"Q{q} {cond}"


def test_the_increments_come_from_the_curve_artefact(full, rendered):
    L = full[fig.SCENARIO]
    for q in "12345":
        for cond in fig.CONDITIONS:
            src = [r["mean_new_at_position"][-1] for r in L[q][cond]["realisations"]]
            assert rendered["inc"][q][cond]["values"] == src


def test_no_increment_is_zero(rendered):
    """The basis for saying themes were still being incorporated at the last position."""
    for q in "12345":
        for cond in fig.CONDITIONS:
            assert rendered["inc"][q][cond]["min"] > 0, f"Q{q} {cond}"


def test_the_increments_are_not_drawn_on_the_simplified_figure(tmp_path, monkeypatch):
    blob = " ".join(_drawn_strings(tmp_path, monkeypatch))
    assert "Mean new clusters at the final focus-group position" not in blob


# ------------------------------------------------------ question titles
def test_question_titles_are_derived_from_the_guide_and_not_invented():
    """
    Every content word in a title must appear in that question's literal moderator
    header. This is the check that stops a plausible-sounding label being written from
    memory rather than from the guide.
    """
    guide = {
        "1": "What's your favourite place in your city to spend time with your male "
             "friends? Why - feel free to be specific?",
        "2": "How do you decide what to eat?",
        "3": "Do you think your gender influences what you eat? Tell us more about why "
             "or why not?",
        "4": "Imagine you decided to go plant-based - what would need to change in your "
             "life for you to do that?",
        "5": "What might make plant-based foods more appealing to you or other men you "
             "know?",
    }
    # "whether" is the only word allowed that the guide does not contain: it turns an
    # interrogative into a noun phrase. Every content word must be literal.
    stop = {"whether"}
    for q, title in fig.GUIDE_TITLES.items():
        src = guide[q].lower().replace("-", " ").replace("?", " ")
        src = set(src.replace("'s", " ").split())
        for w in title.lower().replace("\n", " ").replace("-", " ").split():
            if w in stop:
                continue
            assert w in src or w + "s" in src or w.rstrip("s") in src, (
                f"Q{q}: {w!r} is not in the guide question")


def test_a_title_too_wide_for_its_slot_is_rejected(tmp_path, monkeypatch):
    """PLANTED: an over-wide title would run into the neighbouring question."""
    monkeypatch.setitem(fig.GUIDE_TITLES, "3",
                        "Whether gender influences what people choose to eat every day")
    with pytest.raises(ValueError, match="slot is"):
        fig.render(tmp_path / "x.png", tmp_path / "x.csv")


# ------------------------------------------------------------- figure face
def _drawn_strings(tmp_path, monkeypatch):
    seen = []
    orig = ImageDraw.ImageDraw.text

    def spy(self, xy, text, *a, **k):
        seen.append(text)
        return orig(self, xy, text, *a, **k)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", spy)
    fig.render(tmp_path / "s.png", tmp_path / "s.csv")
    return seen


def test_no_technical_identifier_appears_on_the_face_of_the_figure(
        tmp_path, monkeypatch):
    blob = " ".join(_drawn_strings(tmp_path, monkeypatch))
    for ident in TECHNICAL_IDS:
        assert ident not in blob, f"{ident} is drawn on the figure"


def test_the_required_annotations_are_drawn(tmp_path, monkeypatch):
    blob = " ".join(" ".join(_drawn_strings(tmp_path, monkeypatch)).split())
    for required in (
            "Theme accumulation across focus groups",
            "Cumulative share of final repertoire",
            "Number of focus groups",
            "Final repertoire by guide question",
            "Classified clusters",
            "Human",
            "Enriched (median)",
            "Demographics-only (median)",
            "Range = R1–R3"):
        assert required in blob, required


def test_forbidden_saturation_language_is_absent_from_the_figure(
        tmp_path, monkeypatch):
    blob = " ".join(_drawn_strings(tmp_path, monkeypatch)).lower()
    for banned in ("saturation achieved", "saturation reached", "plateau demonstrated",
                   "sufficient sample size proven", "conditions are equivalent",
                   "enrichment had no effect"):
        assert banned not in blob, banned


def test_explanatory_text_is_kept_off_the_figure(tmp_path, monkeypatch):
    blob = " ".join(" ".join(_drawn_strings(tmp_path, monkeypatch)).split()).lower()
    for removed in (
            "100% is the endpoint",
            "not evidence of saturation",
            "human endpoints vary more by question",
            "replicate-level variation means",
            "limitations",
            "retrospective llm-assisted analysis",
            "meaning saturation was not assessed"):
        assert removed not in blob, removed


# ------------------------------------------------------------------ outputs
def test_the_committed_figure_and_csv_exist():
    assert (_FIGS / "inductive_theme_accumulation_main.png").exists()
    assert (_FIGS / "inductive_theme_accumulation_main.csv").exists()
    assert (_FIGS / "render_inductive_theme_accumulation_main.py").exists()
    assert (_FIGS / "inductive_theme_accumulation_main_TRACEABILITY.md").exists()


def test_the_five_panel_figure_is_retained_as_the_technical_supplement():
    """The simplified figure replaces nothing: the per-question panels stay available."""
    assert (_OUT / "inductive_theme_accumulation.png").exists()
    assert (_OUT / "SATURATION_SECTION.md").exists()


def test_the_committed_csv_matches_a_fresh_render(rendered):
    committed = list(csv.DictReader(
        (_FIGS / "inductive_theme_accumulation_main.csv").open(encoding="utf-8")))
    assert committed == rendered["rows"], "the committed CSV is stale"


def test_the_csv_carries_every_plotted_value(rendered):
    rows = rendered["rows"]
    a = [r for r in rows if r["panel"] == "A"]
    b = [r for r in rows if r["panel"] == "B"]
    t = [r for r in rows if r["panel"] == "caption_table"]
    assert len(a) == 7 * 5                     # 7 realisations x 5 positions
    assert len(b) == 5 * (7 + 3)               # 5 questions x (7 values + 3 medians)
    assert len(t) == 5 * (7 + 3)
    assert {r["metric"] for r in a} == {"pct_of_final_repertoire"}
    assert {r["metric"] for r in b} == {"final_classified_clusters"}
    assert {r["metric"] for r in t} == {"new_clusters_final_pos"}


def test_the_csv_panel_b_rows_reconcile_with_the_endpoint_table(rendered):
    rows = [r for r in csv.DictReader(
        (_OUT / "inductive_endpoints_by_replicate.csv").open(encoding="utf-8"))
        if r["scenario"] == fig.SCENARIO]
    src = {(r["question"], r["condition"], r["replicate"]): int(r["endpoint"])
           for r in rows}
    n = 0
    for r in rendered["rows"]:
        if r["panel"] != "B" or r["realisation"] == "median":
            continue
        q = r["position"][1]
        rep = "human" if r["condition"] == "human" else r["realisation"]
        assert int(float(r["value"])) == src[(q, r["condition"], rep)]
        n += 1
    assert n == 35, f"expected 35 endpoint rows, found {n}"


def test_the_figure_renders_at_the_expected_size(rendered):
    with Image.open(rendered["png"]) as im:
        assert im.size == (fig.W, fig.H)


def test_the_render_is_deterministic(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    fig.render(a, tmp_path / "a.csv")
    fig.render(b, tmp_path / "b.csv")
    assert a.read_bytes() == b.read_bytes()
