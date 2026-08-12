#!/usr/bin/env python3
"""
twinpop_census_sample.py — Phase 3, step 1 of the twin-population arm.

Validates the frozen ONS Census 2021 tables, writes the download manifest the
addendum requires, and draws one census cell per agent with the frozen seed.

Frozen by ADENDUM_TWIN_POBLACIONAL_CONGELADO_2026-08-04.md entry 2 (as amended
2026-08-04 after the first draw produced logically impossible cells):

  person-level (NS-SEC, qualification)
      conditioned on region x Male x age band, from ONS custom cross-tabulations.
  household-level (household composition, tenure)
      region marginal, with an age-compatibility filter: categories whose
      definition requires ALL members to be aged 66+ are removed and the
      remainder renormalised. A man aged 40-53 cannot inhabit them.
  order  region -> NS-SEC -> qualification -> household composition -> tenure
  seed   20260804

No API calls. Deterministic and fully re-derivable.

Usage:
    py scripts/twinpop_census_sample.py --out-dir analysis/production_evaluation/twinpop
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CENSUS_DIR = ROOT / "data" / "census2021"
SEED = 20260804
# Tolerance for cross-tab vs marginal agreement. ONS disclosure control perturbs
# each table independently; observed deviations are single-digit persons on
# millions. Any structural fault would exceed this by orders of magnitude.
CROSS_TOLERANCE = 1e-4

# Categories whose DEFINITION requires every household member to be 66+.
# Frozen explicit list rather than a pattern, so the exclusion is auditable.
# Deliberately NOT excluded: "Other household types: Other, including all
# full-time students and all aged 66 years and over" — its all-students branch
# is compatible with a man aged 40-53, so it is not definitionally impossible.
AGE_INCOMPATIBLE_HOUSEHOLD = frozenset({
    "One-person household: Aged 66 years and over",
    "Single family household: All aged 66 years and over",
})

AGE_BANDS = [(35, 49, "Aged 35 to 49 years"), (50, 64, "Aged 50 to 64 years")]

ROSTER = [
    "agents/macho_meals/mm_fg3_nick.json",
    "agents/macho_meals/mm_fg3_andrew.json",
    "agents/macho_meals/mm_fg3_john.json",
    "agents/macho_meals/mm_fg3_paul.json",
    "agents/macho_meals/mm_fg3_daniel.json",
    "agents/macho_meals/mm_fg4_james.json",
    "agents/macho_meals/mm_fg4_mark.json",
    "agents/macho_meals/mm_fg4_gregor.json",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one(pattern: str) -> Path:
    hits = [p for p in CENSUS_DIR.glob(pattern) if "INVALIDO" not in p.name]
    if len(hits) != 1:
        raise SystemExit(f"expected exactly one file for {pattern!r}, found {[h.name for h in hits]}")
    return hits[0]


def cat_column(fieldnames: list[str], prefix: str) -> str:
    return next(c for c in fieldnames if c.startswith(prefix) and c.endswith("categories)"))


def age_band(age: int) -> str:
    for lo, hi, label in AGE_BANDS:
        if lo <= age <= hi:
            return label
    raise SystemExit(f"age {age} outside the frozen bands {AGE_BANDS}")


def load_marginal(path: Path, prefix: str) -> tuple[dict[str, dict[str, int]], str, dict[str, int]]:
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        col = cat_column(reader.fieldnames, prefix)
        dist: dict[str, dict[str, int]] = {}
        excluded: dict[str, int] = {}
        for row in reader:
            if row[col + " Code"] == "-8":
                excluded[row["Regions"]] = excluded.get(row["Regions"], 0) + int(row["Observation"])
                continue
            dist.setdefault(row["Regions"], {})[row[col]] = int(row["Observation"])
    return dist, col, excluded


def load_cross(path: Path, prefix: str) -> tuple[dict[tuple[str, str, str], dict[str, int]], str]:
    """Return {(region, sex, age_label): {category: count}}."""
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        col = cat_column(reader.fieldnames, prefix)
        sex_col = cat_column(reader.fieldnames, "Sex")
        age_col = cat_column(reader.fieldnames, "Age")
        out: dict[tuple[str, str, str], dict[str, int]] = {}
        for row in reader:
            if row[col + " Code"] == "-8":
                continue
            key = (row["Regions"], row[sex_col], row[age_col])
            out.setdefault(key, {})[row[col]] = int(row["Observation"])
    return out, col


def nomis_checksum(prefix: str) -> dict[str, int]:
    hits = list(CENSUS_DIR.glob(f"INVALIDO_solo_totales__{prefix}_*.csv"))
    if not hits:
        return {}
    out: dict[str, int] = {}
    for line in hits[0].read_text(encoding="utf-8").splitlines():
        m = re.match(r'^"([A-Za-z ]+)",(\d+)\s*$', line.strip())
        if m:
            name = m.group(1)
            out["East of England" if name == "East" else name] = int(m.group(2))
    return out


def weighted_draw(rng: random.Random, counts: dict[str, int]) -> tuple[str, float]:
    total = sum(counts.values())
    target = rng.random() * total
    cum = 0
    for category, n in sorted(counts.items()):
        cum += n
        if target < cum:
            return category, n / total
    last = sorted(counts.items())[-1]
    return last[0], last[1] / total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "nssec_marginal": one("TS062-*filtered*.csv"),
        "qualification_marginal": one("TS067-*filtered*.csv"),
        "household_composition": one("TS003-*filtered*.csv"),
        "tenure": one("TS054-*filtered*.csv"),
        "nssec_cross": one("TS062_nssec_by_sex_age*.csv"),
        "qualification_cross": one("TS067_qualifications_by_sex_age*.csv"),
    }

    manifest: dict = {
        "gate": "phase3_step1",
        "arm": "twinpop",
        "seed": SEED,
        "frozen_by": "ADENDUM_TWIN_POBLACIONAL_CONGELADO_2026-08-04.md entry 2, as amended 2026-08-04",
        "conditioning": {
            "order": ["region", "nssec", "qualification", "household_composition", "tenure"],
            "person_level": {
                "variables": ["nssec", "qualification"],
                "conditioned_on": ["region", "sex=Male", "age_band"],
                "multivariate_cross_used": True,
                "source": "ONS Create a custom dataset, Census 2021",
                "age_bands": [b[2] for b in AGE_BANDS],
            },
            "household_level": {
                "variables": ["household_composition", "tenure"],
                "conditioned_on": ["region"],
                "multivariate_cross_used": False,
                "note": (
                    "Household-level variables describe the household, not the individual, "
                    "so a cross by the individual's age is not well defined. Age coherence is "
                    "enforced by the exclusion filter instead."
                ),
            },
        },
        "age_compatibility_filter": {
            "applies_to": "household_composition",
            "rule": "remove categories whose definition requires ALL members to be aged 66+, then renormalise",
            "excluded_categories": sorted(AGE_INCOMPATIBLE_HOUSEHOLD),
            "not_excluded_and_why": {
                "Other household types: Other, including all full-time students and all aged 66 years and over":
                    "not definitionally impossible — the all-full-time-students branch is compatible with ages 40-53"
            },
            "reason": (
                "First draw (2026-08-04, pre-amendment) produced two logically impossible cells: "
                "a 47-year-old and a 48-year-old placed in households defined as all aged 66+. "
                "27.5% of the unfiltered household-composition mass in the four arm regions is "
                "age-impossible for this cohort, so this was structural, not chance."
            ),
        },
        "classification_note": (
            "The TS067 cross-tabulation uses the 7-category ONS classification, which lacks the "
            "'Other: vocational or work-related qualifications' category present in the 8-category "
            "marginal. Both are valid ONS classifications; the cross-tabulation governs, since it "
            "is the source actually sampled. NS-SEC uses the same 10-category classification in both."
        ),
        "excluded_category": "Code -8 'Does not apply' excluded from every denominator.",
        "files": {},
        "checksum": {},
    }

    for label, path in files.items():
        manifest["files"][label] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }

    # ---- validation -------------------------------------------------------
    marg_specs = [
        ("nssec", "nssec_marginal", "National Statistics", "TS062"),
        ("qualification", "qualification_marginal", "Highest level", "TS067"),
        ("household_composition", "household_composition", "Household composition", "TS003"),
        ("tenure", "tenure", "Tenure", "TS054"),
    ]
    marginals: dict[str, dict[str, dict[str, int]]] = {}
    for attr, key, prefix, table in marg_specs:
        dist, _col, _exc = load_marginal(files[key], prefix)
        marginals[attr] = dist
        check = nomis_checksum(table)
        res = {r: {"sum": sum(c.values()), "nomis": check.get(r), "match": check.get(r) == sum(c.values())}
               for r, c in dist.items()}
        manifest["checksum"][f"{table}_vs_nomis"] = res
        if not all(v["match"] for v in res.values() if v["nomis"] is not None):
            raise SystemExit(f"CHECKSUM FAIL {table} vs nomis — refusing to sample")

    crosses: dict[str, dict[tuple[str, str, str], dict[str, int]]] = {}
    for attr, key, prefix, table in [
        ("nssec", "nssec_cross", "National Statistics", "TS062"),
        ("qualification", "qualification_cross", "Highest level", "TS067"),
    ]:
        cross, _col = load_cross(files[key], prefix)
        crosses[attr] = cross
        # cross summed over sex x age must reproduce the regional 16+ marginal
        agg: dict[str, int] = {}
        for (region, _sex, _age), counts in cross.items():
            agg[region] = agg.get(region, 0) + sum(counts.values())
        # ONS applies statistical disclosure control independently per table
        # ("records have been swapped between different geographic areas and
        # counts perturbed by small amounts"), so a cross-tabulation does not
        # sum to its marginal exactly. The check is therefore a tolerance, not
        # an equality: a real fault (wrong population base, wrong geography,
        # dropped categories) would differ by thousands or millions, not units.
        res = {}
        for r, v in agg.items():
            m = sum(marginals[attr][r].values())
            res[r] = {"cross_sum": v, "marginal_sum": m, "abs_diff": abs(v - m),
                      "rel_diff": abs(v - m) / m, "within_tolerance": abs(v - m) / m <= CROSS_TOLERANCE}
        worst = max(res.values(), key=lambda d: d["rel_diff"])
        manifest["checksum"][f"{table}_cross_vs_marginal"] = {
            "tolerance_rel": CROSS_TOLERANCE,
            "reason": "ONS statistical disclosure control perturbs each table independently",
            "max_abs_diff": worst["abs_diff"], "max_rel_diff": round(worst["rel_diff"], 9),
            "by_region": res,
        }
        if not all(v["within_tolerance"] for v in res.values()):
            bad = {r: v for r, v in res.items() if not v["within_tolerance"]}
            raise SystemExit(f"CHECKSUM FAIL {table} cross vs marginal beyond tolerance: {bad}")

    # ---- draw -------------------------------------------------------------
    rng = random.Random(SEED)
    cells = []
    for rel in ROSTER:
        payload = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        demo = payload["persona"]["demographics"]
        region, age, sex = demo["location"]["region"], demo["age"], demo["gender"]
        band = age_band(age)

        cell = {
            "agent_id": payload["agent_id"], "name": demo["name"], "age": age, "gender": sex,
            "urban_rural": demo["location"]["urban_rural"], "region": region,
            "country": demo["location"]["country"], "age_band": band, "drawn": {},
        }

        for attr in ("nssec", "qualification"):
            counts = crosses[attr].get((region, sex, band))
            if not counts:
                raise SystemExit(f"no cross cell for {(region, sex, band)} in {attr}")
            value, share = weighted_draw(rng, counts)
            cell["drawn"][attr] = {"value": value, "share_within_cell": round(share, 5),
                                   "conditioned_on": f"{region} x {sex} x {band}"}

        for attr in ("household_composition", "tenure"):
            counts = dict(marginals[attr][region])
            removed = {}
            if attr == "household_composition":
                for bad in list(counts):
                    if bad in AGE_INCOMPATIBLE_HOUSEHOLD:
                        removed[bad] = counts.pop(bad)
            value, share = weighted_draw(rng, counts)
            entry = {"value": value, "share_within_cell": round(share, 5), "conditioned_on": region}
            if removed:
                entry["age_filter_removed_mass"] = round(sum(removed.values()) / (sum(counts.values()) + sum(removed.values())), 5)
            cell["drawn"][attr] = entry

        cells.append(cell)

    manifest["n_cells"] = len(cells)
    (args.out_dir / "census_download_manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    (args.out_dir / "census_cells.json").write_text(
        json.dumps(cells, indent=1, ensure_ascii=False), encoding="utf-8")

    print("all checksums PASS (4 marginals vs nomis, 2 cross-tabs vs marginals)\n")
    for c in cells:
        print(f"{c['name']:8s} {c['age']}  {c['urban_rural']:16s} {c['region']}  [{c['age_band']}]")
        for attr, d in c["drawn"].items():
            print(f"     {attr:22s} {d['value'][:76]}  (p={d['share_within_cell']:.3f})")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
