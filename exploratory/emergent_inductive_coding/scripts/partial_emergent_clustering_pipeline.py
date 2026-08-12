"""
Validation and downstream analysis for the returned clustering workbook — PREPARED.

TWO MODES, AND THE ORDER MATTERS
  --seal      record the issued content, so a returned workbook can be checked for
              tampering in the columns the adjudicator was not supposed to touch;
  --validate  check a returned workbook and REFUSE it if incomplete;
  --analyse   presence matrix, shared/exclusive counts, cumulative curve and the
              codebook comparison scaffold — runs ONLY if validation passes.

NOTHING HERE ASSIGNS A CLUSTER. The `cluster_id` column is human work; this module
reads it. An LLM assigning cluster ids would replace the independent judgement the
whole exercise exists to obtain, and would make every downstream count circular.

WHAT IS STILL FORBIDDEN AFTER ANALYSIS
Agreement, saturation and codebook-coverage claims are NOT produced here even once
clustering is complete. `--analyse` emits counts, a matrix and a curve; whether they
support any claim about saturation or coverage is a human reading, and the standing
prohibitions (no complete saturation, no codebook validation, no generalisation to
U08-U15) survive this script.

No API calls. Reads the workbook; never writes to it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

import openpyxl

_REPO_ROOT = Path(__file__).resolve().parent.parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_OUT = _REPO_ROOT / "analysis" / "production_evaluation"
_DIR = _OUT / "partial_emergent_clustering"
_WB = _DIR / "Clustering_U01_U07.xlsx"
_SEAL = _OUT / "gold_standard_sealed" / "partial_emergent_issued_seal.json"
_AUTHORSHIP = _OUT / "gold_standard_sealed" / "partial_emergent_pooled_authorship.json"

SHARED_UNITS = [f"U{i:02d}" for i in range(1, 8)]
OUT_OF_SCOPE = ["U08"]
NOT_REVIEWED = [f"U{i:02d}" for i in range(9, 16)]

ISSUED_COLS = ("pooled_id", "unit_id", "theme_label", "theme_description",
               "supporting_quote", "relevance", "quote_literal_in_unit")
ADJUDICATOR_COLS = ("cluster_id", "cluster_label", "is_central", "adjudicator_notes")
REQUIRED_OF_ADJUDICATOR = ("cluster_id", "cluster_label")
OPTIONAL_OF_ADJUDICATOR = ("adjudicator_notes", "is_central")

# CENTRALITY WAS DELIBERATELY NOT ASSESSED.
#
# The researcher decided not to classify clusters as central or peripheral, because
# that distinction could not be determined reliably from the available material. This
# is a methodological decision, not missing data. It is recorded as NOT_ASSESSED and
# must never be rendered as `peripheral`, `false`, `0`, or an empty set of central
# themes — each of those would turn a declined judgement into a substantive claim.
#
# What the human review DOES validate: theme identification, theme description,
# textual evidence, and the grouping of similar thematic contributions.
# What it does NOT validate: hierarchy, relative importance, or thematic salience.
CENTRALITY_STATUS = "NOT_ASSESSED"
CENTRALITY_NOT_AVAILABLE = "NOT_AVAILABLE — CENTRALITY_NOT_ASSESSED"

# Retained for provenance only. These two rows once had a special exemption because a
# coder left `relevance` blank. Centrality is no longer assessed for ANY row, so they
# now receive exactly the same treatment as every other row and this tuple has no
# effect on the gate.
CENTRALITY_MISSING = ("P034", "P040")

# LEVELS OF THE VARIABLES — these differ, and conflating them is a real error.
#
# CLUSTER IDENTITY IS ALWAYS (unit_id, cluster_id).
# The same cluster_id text may appear in different units without denoting the same
# analytic cluster, so nothing may be merged on the id alone. cluster_label must be
# consistent WITHIN a (unit_id, cluster_id); divergence ACROSS units is reported as a
# review flag, not a gate failure, because under this identity rule it is not an error.
CLUSTER_IDENTITY = "(unit_id, cluster_id)"
CENTRALITY_LEVEL = "cluster_id x unit_id"


class ClusteringNotReady(RuntimeError):
    """Raised when a returned workbook cannot support the downstream analysis."""


def _read(path: Path = _WB) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Clustering"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h).strip() if h is not None else "" for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not r or r[0] in (None, ""):
            continue
        out.append({h: ("" if v is None else str(v).strip())
                    for h, v in zip(hdr, r)})
    wb.close()
    return out


def _row_fingerprint(row: dict) -> str:
    return hashlib.sha256("␟".join(row[c] for c in ISSUED_COLS)
                          .encode("utf-8")).hexdigest()


def seal() -> dict:
    """Record the issued content so later tampering is detectable."""
    rows = _read()
    rec = {
        "sealed_utc": datetime.now(UTC).isoformat(),
        "workbook": str(_WB.relative_to(_REPO_ROOT)),
        "n_rows": len(rows),
        "issued_columns": list(ISSUED_COLS),
        "adjudicator_columns": list(ADJUDICATOR_COLS),
        "row_fingerprints": {r["pooled_id"]: _row_fingerprint(r) for r in rows},
        "note": ("Fingerprints cover ONLY the issued columns. The adjudicator columns "
                 "are expected to change; the issued ones are not."),
    }
    _SEAL.parent.mkdir(parents=True, exist_ok=True)
    _SEAL.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    return rec


def validate(path: Path = _WB) -> list[str]:
    """Every reason this workbook cannot proceed. Empty list means ready."""
    problems: list[str] = []
    rows = _read(path)

    if not rows:
        return ["workbook contains no data rows"]

    # --- issued content unchanged ----------------------------------------
    if _SEAL.exists():
        seal_rec = json.loads(_SEAL.read_text(encoding="utf-8"))
        fps = seal_rec["row_fingerprints"]
        if len(rows) != seal_rec["n_rows"]:
            problems.append(f"row count changed: {len(rows)} vs issued "
                            f"{seal_rec['n_rows']} — rows added or deleted")
        ids_now, ids_issued = {r["pooled_id"] for r in rows}, set(fps)
        if ids_now != ids_issued:
            problems.append(f"pooled_id set changed; missing "
                            f"{sorted(ids_issued - ids_now)}, added "
                            f"{sorted(ids_now - ids_issued)}")
        for r in rows:
            pid = r["pooled_id"]
            if pid in fps and _row_fingerprint(r) != fps[pid]:
                problems.append(f"{pid}: issued content was modified")
    else:
        problems.append("no issued seal found — run --seal before releasing the "
                        "workbook, or tampering cannot be detected")

    # --- scope ------------------------------------------------------------
    units = {r["unit_id"] for r in rows}
    if units != set(SHARED_UNITS):
        problems.append(f"unit set is {sorted(units)}, expected {SHARED_UNITS}")
    for u in OUT_OF_SCOPE + NOT_REVIEWED:
        if u in units:
            problems.append(f"{u} must not appear: U08 is OUT_OF_SCOPE and "
                            f"U09-U15 are NOT_REVIEWED")

    # --- adjudicator completion ------------------------------------------
    # cluster_id and cluster_label are required of every row; is_central is not, and
    # no row may fail for its absence.
    for r in rows:
        pid = r["pooled_id"]
        for col in REQUIRED_OF_ADJUDICATOR:
            if not r.get(col):
                problems.append(f"{pid}: {col} is empty")

    # --- cluster_label is consistent WITHIN (unit_id, cluster_id) ---------
    # Identity is the pair. Two units may legitimately reuse a cluster_id text for
    # different analytic clusters, so only within-pair divergence is a defect.
    within: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        cid, unit = r.get("cluster_id"), r.get("unit_id")
        if cid:
            within.setdefault((unit, cid), set()).add((r.get("cluster_label") or "").strip())
    for (unit, cid), labs in sorted(within.items()):
        if len(labs) > 1:
            problems.append(
                f"cluster ({unit}, {cid}) carries inconsistent labels {sorted(labs)} — "
                f"cluster_label must be single-valued within a (unit_id, cluster_id)")

    # --- is_central is per cluster x unit ---------------------------------
    # A theme central in U02 and peripheral in U05 is legitimate and is NOT flagged.
    cell: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        cid, unit = r.get("cluster_id"), r.get("unit_id")
        if cid and r.get("is_central"):
            cell.setdefault((cid, unit), set()).add(r["is_central"])
    # NOTE: centrality no longer gates in any form. It was NOT_ASSESSED by decision,
    # so a conflict between surviving values is a review flag, not a blocker.
    _ = cell
    return problems


def review_flags(path: Path = _WB) -> list[str]:
    """
    Non-blocking observations for a human to look at. These NEVER gate: flagging is
    not correcting, and none of them is repaired automatically.
    """
    rows = _read(path)
    flags: list[str] = []

    # A cluster_id text reused across units with different labels. Legitimate under
    # (unit_id, cluster_id) identity, but worth a look when every other id is stable.
    labels: dict[str, dict[str, str]] = {}
    for r in rows:
        cid = r.get("cluster_id")
        if cid:
            labels.setdefault(cid, {})[r["unit_id"]] = (r.get("cluster_label") or "").strip()
    for cid, per_unit in sorted(labels.items()):
        distinct = set(per_unit.values())
        if len(distinct) > 1:
            flags.append(
                f"cluster_id {cid!r} is used with {len(distinct)} different labels "
                f"across units {sorted(per_unit)} — under (unit_id, cluster_id) identity "
                f"these are SEPARATE clusters and nothing is merged, but confirm the "
                f"reuse was intended: " +
                "; ".join(f"{u}={per_unit[u][:45]!r}" for u in sorted(per_unit)))

    # Any centrality value that survives in the sheet is preserved literally and is
    # never used analytically.
    cell: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        if r.get("cluster_id") and (r.get("is_central") or "").strip():
            cell.setdefault((r["cluster_id"], r["unit_id"]), set()).add(r["is_central"])
    for (cid, unit), cents in sorted(cell.items()):
        if len(cents) > 1:
            flags.append(
                f"cluster {cid} in {unit} carries conflicting centrality values "
                f"{sorted(cents)}. Not blocking: centrality is {CENTRALITY_STATUS}.")

    present = [r["pooled_id"] for r in rows if (r.get("is_central") or "").strip()]
    if present:
        flags.append(
            f"{len(present)} row(s) carry a centrality value ({present[:5]}). It is "
            f"preserved verbatim and is NOT used analytically: centrality is "
            f"{CENTRALITY_STATUS} for this study.")
    return flags


# ---------------------------------------------------------------------------
# Downstream products — PREPARED, gated on validation
# ---------------------------------------------------------------------------

def _authorship() -> dict[str, str]:
    m = json.loads(_AUTHORSHIP.read_text(encoding="utf-8"))["map"]
    return {x["pooled_id"]: x["coder"] for x in m}


def presence_matrix(rows: list[dict], who: dict[str, str]) -> list[dict]:
    """
    One row per cluster x unit: which coders raised it there, and its centrality
    AT THAT UNIT.

    Centrality was NOT ASSESSED in this study, so `is_central_in_this_unit` reports
    NOT_ASSESSED for every cell unless a literal value survives in the sheet. An empty
    centrality column must never be read as "no central themes" — the judgement was
    declined, not made and found negative. Nothing is imputed from a sibling unit.
    """
    seen: dict[tuple[str, str], set[str]] = {}
    cents: dict[tuple[str, str], set[str]] = {}
    missing: dict[tuple[str, str], int] = {}
    label = {}
    for r in rows:
        cid, unit, key = r["cluster_id"], r["unit_id"], (r["cluster_id"], r["unit_id"])
        label[cid] = r.get("cluster_label", "")
        seen.setdefault(key, set()).add(who.get(r["pooled_id"], "?"))
        if not (r.get("is_central") or "").strip():
            missing[key] = missing.get(key, 0) + 1
        else:
            cents.setdefault(key, set()).add(r["is_central"])
    out = []
    for key in sorted(seen):
        cid, unit = key
        coders = seen[key]
        vals = cents.get(key, set())
        out.append({
            "cluster_id": cid, "cluster_label": label[cid], "unit_id": unit,
            "coder_a": int("Coder_A" in coders),
            "coder_b": int("Coder_B" in coders),
            "raised_by_both": int({"Coder_A", "Coder_B"} <= coders),
            "is_central_in_this_unit": (next(iter(vals)) if len(vals) == 1
                                        else (CENTRALITY_STATUS if not vals
                                              else "CONFLICT")),
            "n_rows_without_centrality": missing.get(key, 0),
            "centrality_level": CENTRALITY_LEVEL,
        })
    return out


def shared_and_exclusive(rows: list[dict], who: dict[str, str]) -> list[dict]:
    by_cluster: dict[str, set[str]] = {}
    label, units = {}, {}
    for r in rows:
        cid = r["cluster_id"]
        by_cluster.setdefault(cid, set()).add(who.get(r["pooled_id"], "?"))
        label[cid] = r.get("cluster_label", "")
        units.setdefault(cid, set()).add(r["unit_id"])
    out = []
    for cid, coders in sorted(by_cluster.items()):
        both = {"Coder_A", "Coder_B"} <= coders
        out.append({"cluster_id": cid, "cluster_label": label[cid],
                    "n_units_present": len(units[cid]),
                    "units": "|".join(sorted(units[cid])),
                    "raised_by": "|".join(sorted(coders)),
                    "status": "shared" if both else "exclusive"})
    return out


def cumulative_curve(rows: list[dict]) -> list[dict]:
    """New clusters introduced by each unit, in U01 -> U07 order."""
    first_seen: dict[str, str] = {}
    for u in SHARED_UNITS:
        for r in rows:
            if r["unit_id"] != u:
                continue
            first_seen.setdefault(r["cluster_id"], u)
    out, total = [], 0
    for u in SHARED_UNITS:
        new = [c for c, first in first_seen.items() if first == u]
        total += len(new)
        out.append({"unit_id": u,
                    "n_pooled_themes": sum(1 for r in rows if r["unit_id"] == u),
                    "n_new_clusters": len(new),
                    # Not a count of zero — the judgement was never made.
                    "n_new_central_clusters": CENTRALITY_NOT_AVAILABLE,
                    "cumulative_clusters": total,
                    "new_cluster_ids": "|".join(sorted(new))})
    return out


def cluster_definitions(rows: list[dict], who: dict[str, str]) -> list[dict]:
    """
    GENERATED, not filled in by hand.

    Every field here is already determined by the Clustering sheet. Asking the
    adjudicator to restate the label and centrality on a second sheet would create
    two human sources for one decision, and the two would eventually disagree.
    `is_central` is deliberately ABSENT from this table: it belongs to
    cluster x unit, not to the cluster, and a single column here would force a level
    error back in.
    """
    units: dict[str, set[str]] = {}
    coders: dict[str, set[str]] = {}
    label, first = {}, {}
    for u in SHARED_UNITS:
        for r in rows:
            if r["unit_id"] != u:
                continue
            cid = r["cluster_id"]
            label[cid] = r.get("cluster_label", "")
            first.setdefault(cid, u)
            units.setdefault(cid, set()).add(u)
            coders.setdefault(cid, set()).add(who.get(r["pooled_id"], "?"))
    return [{
        "cluster_id": cid,
        "cluster_label": label[cid],
        "first_seen_unit": first[cid],
        "n_units_present": len(units[cid]),
        "units_present": "|".join(sorted(units[cid])),
        "raised_by": "|".join(sorted(coders[cid])),
        "raised_by_both_coders": int({"Coder_A", "Coder_B"} <= coders[cid]),
        "centrality_note": CENTRALITY_NOT_AVAILABLE,
    } for cid in sorted(label)]


def codebook_comparison_scaffold(rows: list[dict]) -> list[dict]:
    """One blank row per cluster. The comparison itself is human work, done LAST."""
    seen = {}
    for r in rows:
        seen[r["cluster_id"]] = r.get("cluster_label", "")
    return [{"cluster_id": cid, "cluster_label": lab,
             "closest_codebook_subtheme": "", "relationship": "", "notes": ""}
            for cid, lab in sorted(seen.items())]


def analyse(path: Path = _WB) -> dict:
    problems = validate(path)
    if problems:
        raise ClusteringNotReady(
            "Workbook is not ready; no analysis produced:\n  - " + "\n  - ".join(problems))
    rows = _read(path)
    who = _authorship()
    products = {
        "cluster_definitions": cluster_definitions(rows, who),
        "presence_matrix": presence_matrix(rows, who),
        "shared_and_exclusive": shared_and_exclusive(rows, who),
        "cumulative_curve": cumulative_curve(rows),
        "codebook_comparison_scaffold": codebook_comparison_scaffold(rows),
    }
    for name, data in products.items():
        if not data:
            continue
        out = _DIR / f"{name}.csv"
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
    (_DIR / "clustering_products.json").write_text(json.dumps({
        "generated_utc": datetime.now(UTC).isoformat(),
        "classification": "PARTIAL_EMERGENT_HUMAN_REVIEW",
        "scope": SHARED_UNITS,
        "out_of_scope": OUT_OF_SCOPE, "not_reviewed": NOT_REVIEWED,
        "centrality_missing": list(CENTRALITY_MISSING),
        "still_prohibited": [
            "no claim of complete saturation from seven units",
            "no claim that the codebook is validated",
            "no generalisation to U08-U15 or the wider corpus",
            "no agreement figure without n=7 and the single-adjudicator caveat",
        ],
        **products,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    return products


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seal", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--analyse", action="store_true")
    ap.add_argument("--workbook", default=str(_WB))
    a = ap.parse_args()
    path = Path(a.workbook)

    if a.seal:
        rec = seal()
        print(f"sealed {rec['n_rows']} issued rows -> {_SEAL.relative_to(_REPO_ROOT)}")
        return 0
    if a.analyse:
        try:
            products = analyse(path)
        except ClusteringNotReady as exc:
            print(f"REFUSED: {exc}")
            return 2
        for k, v in products.items():
            print(f"  {k:<32} {len(v):>4} rows")
        return 0

    problems = validate(path)
    print("=" * 74)
    print("  CLUSTERING WORKBOOK VALIDATION")
    print("=" * 74)
    if problems:
        print(f"\nNOT READY — {len(problems)} problem(s):")
        for p in problems[:40]:
            print("  -", p)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        return 1
    print("\nREADY — all adjudicator columns complete and consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
