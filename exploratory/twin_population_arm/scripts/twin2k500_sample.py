#!/usr/bin/env python3
"""
twin2k500_sample.py — Sample agents from the Twin-2K-500 population to
satisfy a panel spec, then combine with a discussion guide to produce a
ready-to-run session config.

Usage:
    python scripts/twin2k500_sample.py \\
        --panel scripts/panel_specs/diverse_4.yaml \\
        --guide configs/guides/food_mood.yaml \\
        --out examples/sessions/food_mood_diverse_4.json

Optional:
    --mode {emergent,orchestrated}    Default: emergent
    --seed INT                         Override panel spec's seed
    --max-tries INT                    Default: 10000
    --manifest-dir PATH                Default: output/sample_manifests/
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents" / "twin2k500"
DEFAULT_MANIFEST_DIR = ROOT / "output" / "sample_manifests"


def load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def load_agent_index() -> list[dict]:
    """Load all agent JSONs as lightweight dicts for filtering and sampling."""
    index = []
    for fp in sorted(AGENTS_DIR.glob("twin_*.json")):
        try:
            data = json.loads(fp.read_text())
        except json.JSONDecodeError:
            continue
        demo = data.get("persona", {}).get("demographics", {})
        loc = demo.get("location") or {}
        index.append({
            "agent_id": data.get("agent_id"),
            "path": fp.relative_to(ROOT).as_posix(),
            "gender": demo.get("gender", "unspecified"),
            "age": demo.get("age", 0),
            "age_bucket": demo.get("age_bucket"),
            "region": loc.get("region"),
        })
    return index


def matches_filters(candidate: dict, filters: dict | None) -> bool:
    if not filters:
        return True
    for field, allowed in filters.items():
        value = candidate.get(field)
        if value is None:
            return False
        if isinstance(allowed, list):
            if value not in allowed:
                return False
        elif value != allowed:
            return False
    return True


def quotas_satisfied(sample: list[dict], quotas: dict | None) -> bool:
    if not quotas:
        return True
    for field, requirement in quotas.items():
        # _spread: true → all sampled agents must have distinct values for this field
        if field.endswith("_spread"):
            base = field[:-len("_spread")]
            if requirement:
                values = [c.get(base) for c in sample]
                if len(set(values)) < len(values):
                    return False
            continue
        # dict form: {category: required_count, ...}
        if isinstance(requirement, dict):
            counts = Counter(c.get(field) for c in sample)
            for cat, expected in requirement.items():
                if counts.get(cat, 0) != expected:
                    return False
    return True


def sample_panel(candidates: list[dict], panel_spec: dict, seed: int, max_tries: int) -> list[dict]:
    filters = panel_spec.get("filters")
    quotas = panel_spec.get("quotas")
    size = panel_spec["size"]

    filtered = [c for c in candidates if matches_filters(c, filters)]
    if len(filtered) < size:
        raise ValueError(
            f"Only {len(filtered)} agents match filters; need {size}. "
            f"Filters: {filters}"
        )

    rng = random.Random(seed)

    for _ in range(max_tries):
        attempt = rng.sample(filtered, size)
        if quotas_satisfied(attempt, quotas):
            return attempt

    raise ValueError(
        f"Could not satisfy quotas after {max_tries} attempts. "
        f"Filtered pool size: {len(filtered)}. Quotas: {quotas}. "
        f"Quotas may be too restrictive — relax a constraint or grow the filter pool."
    )


def build_session_config(panel_spec: dict, guide: dict, sampled: list[dict], mode: str, seed: int) -> dict:
    sections = []
    for i, sec in enumerate(guide["sections"]):
        out = {
            "section_index": i,
            "section_label": sec["label"],
            "section_phase": sec["phase"],
            "section_purpose": (sec.get("purpose") or "").strip(),
            "scripted_question": sec["scripted_question"].strip(),
            "stimulus": sec.get("stimulus"),
            "suggested_probes": sec.get("suggested_probes", []),
        }
        # Emit probing_depth_ceiling only if explicitly set on the section
        # or at the guide level. Otherwise omit entirely so the moderator
        # uses contextual judgment from section_phase and response content.
        explicit_ceiling = sec.get("probing_depth_ceiling") or guide.get("probing_depth_ceiling")
        if explicit_ceiling is not None:
            out["probing_depth_ceiling"] = explicit_ceiling
        sections.append(out)

    session_id = f"{guide['guide_id']}__{panel_spec['name']}__{mode}_seed{seed}"

    return {
        "session_id": session_id,
        "research_objective": (
            f"Multi-participant focus group combining panel '{panel_spec['name']}' "
            f"with guide '{guide['guide_id']}' in {mode} mode."
        ),
        "topic_domain": guide["topic_domain"],
        "participation_mode": mode,
        "temperature": 1.0,
        "participant_collective_identity": guide["participant_collective_identity"],
        "moderator_knowledge_brief": guide["moderator_knowledge_brief"].strip(),
        "researcher_notes": (guide.get("researcher_notes") or "").strip(),
        "participants": [{"agent_payload_path": c["path"]} for c in sampled],
        "discussion_guide": sections,
    }


def write_manifest(out_dir: Path, panel_spec: dict, guide: dict, sampled: list[dict],
                   seed: int, mode: str, session_id: str, config_path: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    breakdown = {
        "gender": dict(Counter(c["gender"] for c in sampled)),
        "age_bucket": dict(Counter(c.get("age_bucket") for c in sampled)),
        "region": dict(Counter(c.get("region") for c in sampled)),
    }

    manifest = {
        "session_id": session_id,
        "generated_at": timestamp,
        "mode": mode,
        "seed": seed,
        "panel_spec": panel_spec,
        "guide_id": guide["guide_id"],
        "guide_title": guide.get("title"),
        "config_path": config_path.resolve().relative_to(ROOT).as_posix(),
        "sampled_agents": [
            {
                "agent_id": c["agent_id"],
                "gender": c["gender"],
                "age": c["age"],
                "age_bucket": c.get("age_bucket"),
                "region": c.get("region"),
            }
            for c in sampled
        ],
        "demographic_breakdown": breakdown,
    }

    manifest_path = out_dir / f"{session_id}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", required=True, type=Path)
    parser.add_argument("--guide", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--mode", choices=["emergent", "orchestrated"], default="emergent")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--max-tries", type=int, default=10000)
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    args = parser.parse_args()

    panel_spec = load_yaml(args.panel)
    guide = load_yaml(args.guide)

    seed = args.seed if args.seed is not None else panel_spec.get("seed", 42)

    print(f"[sample] Panel: {panel_spec['name']} (size={panel_spec['size']}, seed={seed})")
    print(f"[sample] Guide: {guide['guide_id']}")
    print(f"[sample] Mode:  {args.mode}")

    candidates = load_agent_index()
    print(f"[sample] Loaded {len(candidates)} candidate agents.")

    sampled = sample_panel(candidates, panel_spec, seed, args.max_tries)
    print(f"[sample] Sampled {len(sampled)} agents.")

    config = build_session_config(panel_spec, guide, sampled, args.mode, seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(config, indent=2))
    print(f"[sample] Session config -> {args.out}")

    manifest_path = write_manifest(
        args.manifest_dir, panel_spec, guide, sampled, seed,
        args.mode, config["session_id"], args.out,
    )
    print(f"[sample] Manifest       -> {manifest_path}")

    print("\n[sample] Sampled agents:")
    for c in sampled:
        print(f"  {c['agent_id']:<12s}  {c['gender']:<8s}  "
              f"age={str(c['age']):<3s} ({c.get('age_bucket', '?')})  {c.get('region')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
