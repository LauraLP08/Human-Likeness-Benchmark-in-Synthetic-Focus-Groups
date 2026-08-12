"""Profiles (ADR-007), the guide compiler (ADR-003), provenance and pricing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from conftest import make_guide, make_profile
from platform_core import guides, pricing, profiles, provenance
from platform_core.frozen import FrozenCorpusError


def _write(path: Path, payload: dict, fmt: str) -> Path:
    if fmt == "json":
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    else:
        path.write_text(yaml.safe_dump(payload, sort_keys=False,
                                       allow_unicode=True), encoding="utf-8")
    return path


# ================================================================== profiles
def test_json_and_yaml_produce_the_same_canonical_form(tmp_path):
    payload = make_profile()
    j = _write(tmp_path / "p.json", payload, "json")
    y = _write(tmp_path / "p.yaml", payload, "yaml")

    rj = profiles.load_profile_file(j)
    ry = profiles.load_profile_file(y)

    assert rj.source_format == "json" and ry.source_format == "yaml"
    assert rj.canonical_sha256 == ry.canonical_sha256
    assert rj.original_sha256 != ry.original_sha256   # different bytes, same meaning
    assert rj.field_provenance == ry.field_provenance


def test_originals_are_never_written(tmp_path):
    p = _write(tmp_path / "p.json", make_profile(), "json")
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    record = profiles.load_profile_file(p)
    profiles.derive_profile(record, tmp_path / "derived",
                            participant_model="claude-opus-5")
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before


def test_missing_fields_stay_undefined(tmp_path):
    payload = make_profile()
    del payload["simulation_config"]
    p = _write(tmp_path / "p.json", payload, "json")
    r = profiles.load_profile_file(p)

    assert "simulation_config.model" in r.missing_recommended
    assert r.field_provenance["simulation_config.model"] == "undefined"
    assert "simulation_config.model" in r.undefined_fields
    assert r.declared_model is None
    # the loader did not invent one
    assert "simulation_config" not in r.payload


def test_declared_provenance_is_mapped_not_discarded(tmp_path):
    p = _write(tmp_path / "p.json", make_profile(), "json")
    r = profiles.load_profile_file(p)
    assert r.field_provenance["persona.demographics.name"] == "from_file"
    assert r.field_provenance["persona.demographics.location.country"] == "transformed"


def test_duplicate_ids_block(tmp_path):
    a = _write(tmp_path / "a.json", make_profile("same"), "json")
    b = _write(tmp_path / "b.yaml", make_profile("same"), "yaml")
    s = profiles.load_profile_set([a, b])
    assert s.validation.duplicate_ids == ["same"]
    assert s.validation.blocking is True


def test_missing_required_blocks(tmp_path):
    payload = make_profile()
    del payload["persona"]["demographics"]["name"]
    p = _write(tmp_path / "p.json", payload, "json")
    s = profiles.load_profile_set([p])
    assert s.validation.blocking is True
    assert any(m["field"] == "persona.demographics.name"
               for m in s.validation.missing_required)


def test_missing_agent_id_is_rejected(tmp_path):
    payload = make_profile()
    del payload["agent_id"]
    p = _write(tmp_path / "p.json", payload, "json")
    with pytest.raises(profiles.ProfileError, match="agent_id"):
        profiles.load_profile_file(p)


def test_csv_is_refused_with_a_reason(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("agent_id,name\np1,Alex\n", encoding="utf-8")
    with pytest.raises(profiles.ProfileError, match="per-field provenance"):
        profiles.load_profile_file(p)


def test_sensitive_scan_finds_and_masks(tmp_path):
    payload = make_profile()
    payload["persona"]["demographics"]["email"] = "alex.smith@example.com"
    payload["persona"]["demographics"]["note"] = "reach me on +44 7700 900123"
    p = _write(tmp_path / "p.json", payload, "json")
    findings = profiles.scan_sensitive(profiles.load_profile_file(p))
    kinds = {f.pattern for f in findings}
    assert "sensitive_field_name" in kinds or "email" in kinds
    assert all("@example.com" not in f.excerpt_masked
               for f in findings if f.pattern == "email")


# ------------------------------------------------------------- derived copies
def test_model_change_creates_a_derived_profile(tmp_path):
    p = _write(tmp_path / "p.json", make_profile(), "json")
    record = profiles.load_profile_file(p)
    derived = profiles.derive_profile(record, tmp_path / "derived",
                                      participant_model="claude-opus-5")

    assert Path(derived.derived_path).is_file()
    assert derived.source_sha256 == record.original_sha256
    out = json.loads(Path(derived.derived_path).read_text(encoding="utf-8"))
    assert out["simulation_config"]["model"] == "claude-opus-5"
    assert json.loads(p.read_text(encoding="utf-8"))["simulation_config"]["model"] \
        == "claude-haiku-4-5"


def test_transformation_is_recorded_twice(tmp_path):
    p = _write(tmp_path / "p.json", make_profile(), "json")
    record = profiles.load_profile_file(p)
    derived = profiles.derive_profile(record, tmp_path / "derived",
                                      participant_model="claude-opus-5")
    t = derived.run_transformations[0]
    assert t.field_path == "simulation_config.model"
    assert t.from_value == "claude-haiku-4-5" and t.to_value == "claude-opus-5"
    assert t.applied_at
    assert derived.field_provenance["simulation_config.model"] == "transformed"


def test_derived_payload_differs_only_in_declared_fields(tmp_path):
    p = _write(tmp_path / "p.json", make_profile(), "json")
    record = profiles.load_profile_file(p)
    derived = profiles.derive_profile(record, tmp_path / "derived",
                                      participant_model="claude-opus-5")
    out = json.loads(Path(derived.derived_path).read_text(encoding="utf-8"))
    out.pop("_derived_from")
    changed = profiles.diff_payloads(record.payload, out)
    assert changed == ["simulation_config.model"]


def test_no_transformation_when_the_model_is_unchanged(tmp_path):
    p = _write(tmp_path / "p.json", make_profile(), "json")
    record = profiles.load_profile_file(p)
    derived = profiles.derive_profile(record, tmp_path / "derived",
                                      participant_model="claude-haiku-4-5")
    assert derived.run_transformations == []


def test_max_tokens_override_is_labelled_a_ceiling(tmp_path):
    p = _write(tmp_path / "p.json", make_profile(), "json")
    record = profiles.load_profile_file(p)
    derived = profiles.derive_profile(record, tmp_path / "derived", max_tokens=800)
    assert "ceiling, not a target" in derived.run_transformations[0].rule


def test_derive_refuses_to_write_into_the_frozen_corpus(tmp_path, repo_root):
    p = _write(tmp_path / "p.json", make_profile(), "json")
    record = profiles.load_profile_file(p)
    with pytest.raises(FrozenCorpusError):
        profiles.derive_profile(record, repo_root / "agents" / "macho_meals")


# ==================================================================== guides
REPO_GUIDES = sorted((Path(__file__).resolve().parents[3] / "configs" / "guides")
                     .glob("*.yaml"))


@pytest.mark.parametrize("path", REPO_GUIDES, ids=lambda p: p.stem)
def test_every_repository_guide_compiles(path):
    """All eight existing guides must validate, or fail with a localised error."""
    compiled = guides.compile_guide_file(path)
    assert compiled.section_count > 0
    assert compiled.validation.ok
    assert all(s["section_phase"] in guides.VALID_PHASES
               for s in compiled.sections)
    assert [s["section_index"] for s in compiled.sections] == \
        list(range(compiled.section_count))


def test_compilation_is_deterministic(tmp_path):
    p = tmp_path / "g.yaml"
    p.write_text(yaml.safe_dump(make_guide(), sort_keys=False), encoding="utf-8")
    a = guides.compile_guide_file(p)
    b = guides.compile_guide_file(p)
    assert a.compiled_json_sha256 == b.compiled_json_sha256
    assert a.source_yaml_sha256 == b.source_yaml_sha256


def test_compiler_matches_the_repository_conversion(tmp_path):
    """Mirrors scripts/run_batch.py::_load_guide_sections."""
    p = tmp_path / "g.yaml"
    p.write_text(yaml.safe_dump(make_guide(), sort_keys=False), encoding="utf-8")
    section = guides.compile_guide_file(p).sections[1]
    assert section == {
        "section_index": 1,
        "section_label": "Main",
        "section_phase": "context",
        "section_purpose": "Section 1: Main",
        "scripted_question": "What do you think?",     # stripped
        "suggested_probes": ["Why?", "Can you say more?"],
    }


def test_unknown_phase_blocks_with_a_localised_error(tmp_path):
    p = tmp_path / "g.yaml"
    p.write_text(yaml.safe_dump(make_guide(phase="introductory"), sort_keys=False),
                 encoding="utf-8")
    with pytest.raises(guides.GuideError, match="section 1"):
        guides.compile_guide_file(p)

    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    v = guides.validate_guide(raw)
    assert not v.ok
    err = v.errors[0]
    assert err.section_index == 1 and err.field_path == "phase"
    assert "introductory -> context" in err.message      # Krueger hint
    assert v.unmapped_phases == ["introductory"]


def test_missing_required_section_field_blocks(tmp_path):
    guide = make_guide()
    del guide["sections"][0]["scripted_question"]
    p = tmp_path / "g.yaml"
    p.write_text(yaml.safe_dump(guide, sort_keys=False), encoding="utf-8")
    with pytest.raises(guides.GuideError):
        guides.compile_guide_file(p)


def test_correspondence_holds_then_breaks(tmp_path):
    src = tmp_path / "g.yaml"
    src.write_text(yaml.safe_dump(make_guide(), sort_keys=False), encoding="utf-8")
    compiled = guides.compile_guide_file(src)
    out = guides.write_compiled(compiled, tmp_path / "derived")

    ok, reason = guides.check_correspondence(src, out,
                                             compiled.compiled_json_sha256)
    assert ok and reason is None

    tampered = json.loads(out.read_text(encoding="utf-8"))
    tampered[1]["scripted_question"] = "Something the researcher never wrote"
    out.write_text(json.dumps(tampered, ensure_ascii=False,
                              separators=(",", ":")), encoding="utf-8")
    ok, reason = guides.check_correspondence(src, out,
                                             compiled.compiled_json_sha256)
    assert not ok
    assert "edited outside the compiler" in reason


def test_correspondence_breaks_when_the_yaml_moves(tmp_path):
    src = tmp_path / "g.yaml"
    src.write_text(yaml.safe_dump(make_guide(), sort_keys=False), encoding="utf-8")
    compiled = guides.compile_guide_file(src)
    out = guides.write_compiled(compiled, tmp_path / "derived")

    moved = make_guide()
    moved["sections"][1]["scripted_question"] = "A different question"
    src.write_text(yaml.safe_dump(moved, sort_keys=False), encoding="utf-8")

    ok, reason = guides.check_correspondence(src, out,
                                             compiled.compiled_json_sha256)
    assert not ok
    assert "does not reproduce" in reason or "edited outside" in reason


def test_frozen_configs_are_exempt_from_recompilation(repo_root):
    cfg = repo_root / "configs/experiment/macho_meals_fg1_run02.json"
    assert guides.frozen_config_exempt(cfg)
    sections = guides.discussion_guide_from_config(cfg)
    assert isinstance(sections, list) and sections
    assert sections[0]["section_index"] == 0


def test_write_compiled_refuses_the_frozen_corpus(tmp_path, repo_root):
    src = tmp_path / "g.yaml"
    src.write_text(yaml.safe_dump(make_guide(), sort_keys=False), encoding="utf-8")
    compiled = guides.compile_guide_file(src)
    with pytest.raises(FrozenCorpusError):
        guides.write_compiled(compiled, repo_root / "configs" / "guides")


# =============================================================== provenance
def test_hash_is_stable():
    assert provenance.code_content_hash() == provenance.code_content_hash()


def test_hash_starts_with_its_prefix():
    assert provenance.code_content_hash().startswith("cch:")


def test_hash_changes_when_a_listed_file_changes(tmp_path):
    manifest = tmp_path / "m.txt"
    manifest.write_text("a.py\nb.py\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("one", encoding="utf-8")
    (tmp_path / "b.py").write_text("two", encoding="utf-8")

    first = provenance.code_content_hash(manifest, tmp_path)
    (tmp_path / "b.py").write_text("two!", encoding="utf-8")
    assert provenance.code_content_hash(manifest, tmp_path) != first


def test_hash_depends_on_manifest_order(tmp_path):
    (tmp_path / "a.py").write_text("one", encoding="utf-8")
    (tmp_path / "b.py").write_text("two", encoding="utf-8")
    m1 = tmp_path / "m1.txt"
    m2 = tmp_path / "m2.txt"
    m1.write_text("a.py\nb.py\n", encoding="utf-8")
    m2.write_text("b.py\na.py\n", encoding="utf-8")
    assert provenance.code_content_hash(m1, tmp_path) != \
        provenance.code_content_hash(m2, tmp_path)


def test_missing_listed_file_is_an_error(tmp_path):
    manifest = tmp_path / "m.txt"
    manifest.write_text("gone.py\n", encoding="utf-8")
    with pytest.raises(provenance.ProvenanceError, match="does not exist"):
        provenance.code_content_hash(manifest, tmp_path)


def test_empty_manifest_is_an_error(tmp_path):
    manifest = tmp_path / "m.txt"
    manifest.write_text("# only a comment\n", encoding="utf-8")
    with pytest.raises(provenance.ProvenanceError, match="empty"):
        provenance.code_content_hash(manifest, tmp_path)


def test_hash_is_never_labelled_a_commit():
    described = provenance.describe_code_hash(provenance.code_content_hash())
    assert "no git repository present" in described
    assert "commit" not in described.lower()
    assert "commit" not in provenance.HASH_LABEL.lower()


def test_real_manifest_covers_core_and_the_registry():
    listed = provenance.read_code_manifest()
    assert "core/orchestrator.py" in listed
    assert "core/participant_agent.py" in listed
    assert "analysis/production_evaluation/metric_registry.csv" in listed
    assert any(p.startswith("apps/focus_group_platform/platform_core/")
               for p in listed)


def test_figure_carries_only_the_compact_fields():
    block = provenance.ProvenanceBlock(metric_id="words_per_turn_median",
                                       status="AVAILABLE_VALIDATED").stamp()
    caption = provenance.figure_caption_fields(block)
    assert set(caption) == {"metric_id", "status", "denominator"}
    assert "inputs" not in caption and "parameters" not in caption
    assert provenance.sidecar_path(Path("fig.png")).name == "fig.provenance.json"


# ================================================================== pricing
def test_pricing_is_schema_only():
    table = pricing.PricingTable(version="2026-08-04.1",
                                 effective_date=__import__("datetime").date(2026, 8, 4),
                                 source_note="not populated in Phase 2A")
    assert table.rates == []
    assert table.rate_for("claude-opus-5") is None
    assert table.known_models() == []


def test_empty_estimate_is_undefined_not_zero():
    est = pricing.empty_estimate("2026-08-04.1")
    assert est.total_usd is None
    assert est.is_estimate is True
    assert "undefined" in est.label


def test_lower_bound_label():
    est = pricing.CostEstimate(total_usd=1.25, pricing_table_version="v1",
                               unpriced_models=["some-model"], is_lower_bound=True)
    assert "lower bound" in est.label
