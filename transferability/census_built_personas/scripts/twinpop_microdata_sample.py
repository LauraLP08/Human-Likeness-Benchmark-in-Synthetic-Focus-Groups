#!/usr/bin/env python3
"""
twinpop_microdata_sample.py — Phase 3, step 1 of the twin-population arm.

Draws one REAL person record per candidate from the ONS Census 2021 Safeguarded
Individual Microdata Sample at Region Level (SN 9154, 5% of individual records,
England & Wales), matched on region, sex and EXACT age.

Why microdata rather than aggregate tables (supersedes twinpop_census_sample.py):
    Sampling aggregate marginals independently yields the PRODUCT of marginals,
    not the population joint. It produced people who do not exist (a 47-year-old
    in a household defined as all aged 66+) and destroyed the correlations
    between occupation, education, household and tenure that make a person
    coherent. One microdata row is one real respondent, so the joint is given
    rather than reconstructed — the structural analogue of Twin-2K-500.

Source: UK Data Service SN 9154, safeguarded access, End User Licence.
Anonymised records; no reidentification is attempted at any point.

Deterministic: same seed, same inputs, same draw. No API calls.

Usage:
    py scripts/twinpop_microdata_sample.py --out-dir analysis/production_evaluation/twinpop
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parent.parent
CENSUS = ROOT / "data" / "census2021"
SAV = CENSUS / "sn9154" / "UKDA-9154-spss" / "spss" / "spss25" / "safeguarded_reg_final_csv2023_07_12.sav"
CACHE = CENSUS / "sn9154_subset.pkl"
LABELS = CENSUS / "sn9154_value_labels.json"
SEED = 20260804
N_CANDIDATES = 3

REGION_CODE = {
    "North West": "E12000002",
    "East of England": "E12000006",
    "South East": "E12000008",
    "South West": "E12000009",
}
SEX_MALE = 2
PRIVATE_HOUSEHOLD = 1

PERSONA_FIELDS = {
    "working_life": [
        "economic_activity_status_17m", "ns_sec", "occupation_105a", "industry_22a",
        "employment_status", "employment_history", "supervises_or_manages",
        "hours_per_week_worked", "highest_qualification",
    ],
    "home_and_household": [
        "hh_tenure", "accommodation_type_7a", "hh_size_9a", "living_arrangements_11a",
        "legal_partnership_status_7a", "family_dependent_children",
        "hh_adults_and_children_11a", "relat_to_hrp", "occupancy_rating_bedrooms_6a",
    ],
    "week_and_hobbies": [
        "transport_to_workplace_12a", "workplace_travel", "place_of_work_ind",
    ],
}

MATCH_KEYS = ["region", "sex", "resident_age_74m", "residence_type"]

# Every one of the 89 variables not used, with the reason. Grouped by ground.
WITHHELD = {
    "topic_leakage": {
        "variables": [
            "hh_deprivation", "hh_deprivation_education", "hh_deprivation_employment",
            "hh_deprivation_health", "hh_deprivation_housing",
            "religion_tb", "hh_multi_religion",
            "health_in_general", "disability_4a", "hh_disabled_4a",
            "is_carer_5a", "hh_carers_6a",
        ],
        "reason": (
            "Household deprivation is tied to food insecurity, squarely inside the study topic. "
            "Dietary rules are religion-linked (halal, kosher, Hindu vegetarianism). Health, body "
            "and disability sit on the frozen domain negative list. Unpaid care cues who shops and "
            "who cooks, which is subtheme A.3 of the codebook verbatim."
        ),
    },
    "stereotype_amplification": {
        "variables": ["uk_armed_forces"],
        "reason": "Military service is a masculinity marker; supplying it would seed the very artefact §4.4 exists to detect.",
    },
    "ethnicity_origin_language": {
        "variables": [
            "ethnic_group_tb_20b", "hrp_ethnic_group_tb", "hh_multi_ethnic_group",
            "country_of_birth_25a", "hrp_cob_25m", "year_arrival_uk",
            "migrant_ind", "migrant_origin_country_7m", "migrant_region", "migration_distance_19m",
            "passports_all_27a", "multi_passports_9a",
            "nat_id_british", "nat_id_english", "nat_id_irish", "nat_id_northern_irish",
            "nat_id_other", "nat_id_scottish", "nat_id_welsh", "national_identity_detailed_23m",
            "main_language_detailed_23a", "english_proficiency_5a", "hh_language",
            "welsh_skills_read", "welsh_skills_speak", "welsh_skills_understand", "welsh_skills_write",
        ],
        "reason": (
            "Ethnicity is a frozen omission (pre-registro §3.1): it is a stereotype vector on the "
            "study's own identity axis, and the real participants' first names are retained. "
            "Nationality, passports, migration and language are proxies for it, and country of "
            "birth is additionally a direct cuisine cue."
        ),
    },
    "inapplicable_or_redundant": {
        "variables": [
            "ce_management_type_12a", "position_in_ce", "student_accommodation",
            "student_add_1_year_ago_ind", "usual_short_student", "in_full_time_education",
            "iol22cd", "fm_iol22cd", "second_address_country", "second_address_type_priority",
            "concealed_family_ind", "hh_number_of_visitors_2a", "workers_in_generation_1",
            "address_1_year_ago", "moving_hh_ind_2", "hrp_age_59m", "hrp_ns_sec",
            "heating_type", "self_contained", "occupancy_rating_rooms_6a", "hh_66_plus",
            "number_of_cars_6a", "approx_social_grade",
        ],
        "reason": (
            "Communal-establishment and student variables do not apply once the draw is filtered "
            "to private households. London indicators do not apply to the four arm regions. "
            "Student and education-status flags are implied by economic activity. Household "
            "reference person attributes are covered by relat_to_hrp. The rest add nothing beyond "
            "variables already included. approx_social_grade is a cruder derived duplicate of "
            "ns_sec, and its derivation quirks produce apparent contradictions (L13 Routine "
            "occupations carrying grade AB), which would surface as incoherent prose."
        ),
    },
}


def load_frame():
    import pandas as pd
    if CACHE.exists():
        return pd.read_pickle(CACHE)
    import pyreadstat
    cols = MATCH_KEYS + ["resident_id_m"] + [v for vs in PERSONA_FIELDS.values() for v in vs]
    df, _meta = pyreadstat.read_sav(str(SAV), usecols=cols)
    df.to_pickle(CACHE)
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    df = load_frame()
    labels: dict[str, dict[str, str]] = json.loads(LABELS.read_text(encoding="utf-8"))

    def label(var: str, value) -> str:
        table = labels.get(var, {})
        for key in (str(value), str(float(value)), str(int(value)) if value == value else ""):
            if key in table:
                return table[key]
        return str(value)

    roster = sorted((ROOT / "agents" / "macho_meals").glob("mm_fg[34]_*.json"), key=lambda p: p.name)
    rng = random.Random(SEED)
    cells, used = [], set()

    for path in roster:
        payload = json.loads(path.read_text(encoding="utf-8"))
        demo = payload["persona"]["demographics"]
        region, age = demo["location"]["region"], demo["age"]

        pool = df[(df.region == REGION_CODE[region]) & (df.sex == SEX_MALE)
                  & (df.resident_age_74m == age) & (df.residence_type == PRIVATE_HOUSEHOLD)]
        pool = pool[~pool.resident_id_m.isin(used)]
        if len(pool) < N_CANDIDATES:
            raise SystemExit(f"pool too small for {demo['name']}: {len(pool)}")

        picks = rng.sample(sorted(pool.resident_id_m.tolist()), N_CANDIDATES)
        candidates = []
        for idx, rid in enumerate(picks, start=1):
            used.add(rid)
            rec = pool[pool.resident_id_m == rid].iloc[0]
            candidates.append({
                "candidate_index": idx,
                "microdata_record_id": str(rid),
                "attributes": {
                    field: {v: label(v, rec[v]) for v in variables}
                    for field, variables in PERSONA_FIELDS.items()
                },
            })

        cells.append({
            "agent_id": payload["agent_id"], "name": demo["name"], "age": age,
            "gender": demo["gender"], "urban_rural": demo["location"]["urban_rural"],
            "region": region, "country": demo["location"]["country"],
            "matched_on": {"region": region, "sex": "Male", "age": f"exactly {age}",
                           "residence_type": "private household"},
            "pool_size": int(len(pool)), "candidates": candidates,
        })

    manifest = {
        "gate": "phase3_step1", "arm": "twinpop", "seed": SEED,
        "method": "one real microdata person record per candidate — joint distribution given, not reconstructed",
        "supersedes": [
            "scripts/twinpop_census_sample.py (aggregate TS tables, product of marginals)",
            "the 1% public teaching sample draw (band-level age, no qualification or tenure)",
        ],
        "source": {
            "study": "SN 9154 — 2021 Census: Safeguarded Individual Microdata Sample at Region Level (England and Wales)",
            "publisher": "Office for National Statistics, via UK Data Service",
            "access": "Safeguarded, End User Licence. Anonymised records; no reidentification attempted.",
            "file": SAV.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(SAV.read_bytes()).hexdigest(),
            "n_records_total": int(len(df)),
            "n_variables_available": 89,
            "n_variables_used": len(MATCH_KEYS) + sum(len(v) for v in PERSONA_FIELDS.values()),
        },
        "matching": {
            "keys": MATCH_KEYS,
            "age": "EXACT single year (resident_age_74m is single years to age 70)",
            "not_matched": {"urban_rural": "absent from the microdata; retained from the real participant, not drawn"},
            "sampling": f"{N_CANDIDATES} candidates per cell, without replacement across the whole draw",
        },
        "persona_fields": PERSONA_FIELDS,
        "withheld_variables": WITHHELD,
        "limitations": [
            "Hobbies and leisure are not collected by the census. 'week_and_hobbies' is anchored "
            "only by commuting (mode, distance, place-of-work); the leisure content is invented by "
            "the renderer under the §4.1 constraints and is NOT census-grounded. State in methods.",
            "urban_rural is not in the microdata, so a Village-or-Rural participant may be matched "
            "to a record from an urban part of the same region.",
        ],
        "n_cells": len(cells),
        "n_candidates_total": sum(len(c["candidates"]) for c in cells),
    }

    (args.out_dir / "microdata_manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    (args.out_dir / "microdata_cells.json").write_text(
        json.dumps(cells, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"SN 9154: {len(df):,} records, {manifest['source']['n_variables_used']} of 89 variables used")
    print(f"{len(cells)} cells x {N_CANDIDATES} candidates = {manifest['n_candidates_total']} real person records\n")
    for c in cells:
        print(f"{c['name']:8s} {c['age']} {c['urban_rural']:16s} {c['region']}  (pool {c['pool_size']:,})")
        a = c["candidates"][0]["attributes"]
        for field in PERSONA_FIELDS:
            for v, lab in a[field].items():
                print(f"   {v:30s} {lab[:70]}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
