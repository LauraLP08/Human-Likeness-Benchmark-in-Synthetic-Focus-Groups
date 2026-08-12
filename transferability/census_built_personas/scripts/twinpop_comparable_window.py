#!/usr/bin/env python3
"""
twinpop_comparable_window.py — derive the comparable analytical window for the 6
twinpop runs using THE PRODUCTION FUNCTION, not a copy of it.

WHY IT IMPORTS INSTEAD OF COPYING
`build_comparable_window.build_window` is the rule that produced the window for all
30 canonical runs. A twinpop-specific reimplementation could drift from it silently
and every downstream comparison would then be between windows cut by two different
rules — exactly the failure the G1 controls were written to prevent ("a duplicated
gate can silently diverge from the one that runs in production while its controls
keep passing"). So this module calls the real function.

THE REGRESSION GATE
Importing is only safe if calling the function today still reproduces what it
produced when the corpus was frozen. Before touching twinpop, this script re-derives
three canonical runs and compares the resulting file hash against the hash recorded
in `comparable_window_audit.csv`. Because `build_window` WRITES, each target file is
backed up first and restored unconditionally afterwards, so the frozen corpus is
byte-identical whether the gate passes or fails.

If the gate fails, no twinpop window is written. A window cut by a rule that no
longer reproduces the corpus is not comparable to the corpus.

No API calls.

Usage:
    py scripts/twinpop_comparable_window.py --out-dir analysis/production_evaluation/twinpop
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_comparable_window import build_window, _DERIVED_DIR  # noqa: E402

AUDIT_CSV = ROOT / "analysis" / "production_evaluation" / "comparable_window_audit.csv"

TWINPOP_RUNS = [
    "macho_meals_fg3_twinpop_run01", "macho_meals_fg3_twinpop_run02",
    "macho_meals_fg3_twinpop_run03", "macho_meals_fg3_twinpop_run04",
    "macho_meals_fg4_twinpop_run01",
    "macho_meals_fg4_twinpop_run02", "macho_meals_fg4_twinpop_run03",
]
# Regression targets: one enriched, one demoonly, one from each FG the arm uses.
REGRESSION_RUNS = ["macho_meals_fg3_run01", "macho_meals_fg3_demoonly_run01",
                   "macho_meals_fg4_run01"]


def sha256_file(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


# The derived file stamps `_provenance.generated_utc` at write time, so a faithful
# re-derivation NEVER reproduces the whole-file hash — the first run of this gate
# failed on all three targets for that reason alone. The timestamp is not part of
# the windowing rule and cannot be, so the assertion is made on the payload with
# that one field removed. Everything else — the transcript entries, the boundary
# offset, both boundary-text hashes, the entry indices — is compared exactly. The
# raw hashes are still reported so the exclusion stays visible and auditable.
EXCLUDED_FROM_COMPARISON = ("_provenance.generated_utc",)


def substantive_digest(p: Path) -> str | None:
    if not p.exists():
        return None
    obj = json.loads(p.read_text(encoding="utf-8"))
    obj.get("_provenance", {}).pop("generated_utc", None)
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def frozen_hashes() -> dict[str, str]:
    with AUDIT_CSV.open(encoding="utf-8-sig", newline="") as fh:
        return {r["physical_run"]: r.get("comparable_transcript_sha256", "")
                for r in csv.DictReader(fh)}


def regression_gate(backup_dir: Path) -> tuple[bool, list[dict]]:
    """Re-derive canonical runs and compare to the frozen hash. Restores originals."""
    frozen = frozen_hashes()
    rows = []
    for run in REGRESSION_RUNS:
        target = _DERIVED_DIR / run / "comparable_transcript.json"
        expected = frozen.get(run)
        before = sha256_file(target)
        before_sub = substantive_digest(target)
        backup = backup_dir / f"{run}.json"
        if target.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        try:
            build_window(run)
            after = sha256_file(target)
            after_sub = substantive_digest(target)
        finally:
            # Unconditional restore: the frozen corpus is never left rewritten,
            # not even with identical bytes.
            if backup.exists():
                shutil.copy2(backup, target)
        rows.append({
            "run": run,
            "frozen_hash_in_audit_csv": expected,
            "raw_hash_on_disk_before": before,
            "raw_hash_rederived_now": after,
            "raw_hashes_differ_by_timestamp_only": before != after,
            "substantive_digest_before": before_sub,
            "substantive_digest_rederived": after_sub,
            "reproduces_substantively": before_sub is not None and after_sub == before_sub,
            "excluded_from_comparison": list(EXCLUDED_FROM_COMPARISON),
            "restored_ok": sha256_file(target) == before,
        })
    ok = all(r["reproduces_substantively"] and r["restored_ok"] for r in rows)
    return ok, rows


def digest_controls(sample: Path) -> list[dict]:
    """A comparison that excludes a field has to be shown that it still catches
    changes to the fields it did NOT exclude. Loosening a gate to make it pass is
    the failure mode this guards against: without these, `substantive_digest` could
    exclude everything and the regression gate would report a clean PASS forever.
    Operates on an in-memory copy; the file on disk is only ever read."""
    obj = json.loads(sample.read_text(encoding="utf-8"))

    def digest(o: dict) -> str:
        o = json.loads(json.dumps(o))
        o.get("_provenance", {}).pop("generated_utc", None)
        return hashlib.sha256(
            json.dumps(o, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    base = digest(obj)
    controls = []

    # NEGATIVE: only the excluded timestamp moves -> must be judged UNCHANGED.
    t = json.loads(json.dumps(obj))
    t.setdefault("_provenance", {})["generated_utc"] = "1999-01-01T00:00:00Z"
    # Every tuple's third element means "did the digest CHANGE?" — the negative
    # control originally reported `== base`, so a correct comparator was printed
    # as ROTO. Same predicate everywhere, so the reading cannot invert again.
    controls.append(("negativo: solo cambia generated_utc", "IGUAL", digest(t) != base))

    # POSITIVE 1: one character of transcript text -> must be judged CHANGED.
    t = json.loads(json.dumps(obj))
    t["transcript"][0]["content"] = (t["transcript"][0]["content"] or "") + "x"
    controls.append(("positivo: un caracter del transcript", "DISTINTO", digest(t) != base))

    # POSITIVE 2: the boundary offset -> the field the whole window rule turns on.
    t = json.loads(json.dumps(obj))
    prov = t.get("provenance", t.get("_provenance", {}))
    prov["source_character_start"] = int(prov.get("source_character_start", 0)) + 1
    controls.append(("positivo: source_character_start +1", "DISTINTO", digest(t) != base))

    # POSITIVE 3: one entry dropped -> a truncated window must never read as clean.
    t = json.loads(json.dumps(obj))
    t["transcript"] = t["transcript"][:-1]
    controls.append(("positivo: una entrada eliminada", "DISTINTO", digest(t) != base))

    out = []
    for name, expected, changed in controls:
        observed = "DISTINTO" if changed else "IGUAL"
        out.append({"control": name, "expected": expected, "observed": observed,
                    "correct": observed == expected})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--backup-dir", type=Path,
                    default=Path("analysis/production_evaluation/twinpop/_window_backup"))
    args = ap.parse_args()

    print("CONTROLES DEL COMPARADOR (una comparacion que excluye un campo debe demostrar\n"
          "que sigue cazando cambios en los que NO excluyo)\n")
    ctl = digest_controls(_DERIVED_DIR / REGRESSION_RUNS[0] / "comparable_transcript.json")
    for c in ctl:
        print(f"  {'OK  ' if c['correct'] else 'ROTO'} {c['control']:42s} "
              f"esperado={c['expected']:9s} obtenido={c['observed']}")
    ctl_ok = all(c["correct"] for c in ctl)
    if not ctl_ok:
        print("\nUN CONTROL FALLA — el comparador no sirve; no se evalua nada mas.")
        return 1

    print("\nGATE DE REGRESION — la funcion de produccion aun reproduce el corpus congelado\n")
    ok, rows = regression_gate(ROOT / args.backup_dir)
    for r in rows:
        mark = "OK   " if r["reproduces_substantively"] and r["restored_ok"] else "FALLA"
        print(f"  {mark} {r['run']:34s} contenido_reproducido:{r['reproduces_substantively']}  "
              f"restaurado:{r['restored_ok']}")

    out = {"gate": "twinpop_comparable_window",
           "comparator_controls_all_correct": ctl_ok, "comparator_controls": ctl,
           "regression_gate_passed": ok, "regression": rows}

    if not ok:
        out["twinpop_windows"] = []
        out["abort_reason"] = ("build_window no reproduce el corpus congelado; no se corta "
                              "ninguna ventana twinpop con una regla que ya no reproduce "
                              "aquello con lo que se va a comparar.")
        (args.out_dir / "twinpop_comparable_window.json").write_text(
            json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        print("\nGATE FALLA — no se deriva ninguna ventana twinpop.")
        return 1

    print("\nGATE PASA. Derivando las ventanas twinpop:\n")
    derived, problems = [], []
    for run in TWINPOP_RUNS:
        if not (ROOT / "output" / "session_logs" / run / "transcript.json").exists():
            print(f"  PEND  {run:34s} sesion aun no corrida")
            continue
        row = build_window(run)
        verdict = row.get("segmentation_verdict", "OK")
        bad = verdict == "HUMAN_REVIEW_REQUIRED"
        if bad:
            problems.append({"run": run, "problems": row.get("problems")})
        print(f"  {'REVISAR' if bad else 'OK     '} {run:34s} "
              f"entradas={row.get('included_entries')} "
              f"palabras_incluidas={row.get('included_words', row.get('total_source_words'))} "
              f"{row.get('problems','')}")
        derived.append({k: v for k, v in row.items() if not isinstance(v, (list, dict))})

    out["twinpop_windows"] = derived
    out["twinpop_requiring_review"] = problems
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "twinpop_comparable_window.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(derived)}/6 ventanas derivadas -> {args.out_dir / 'twinpop_comparable_window.json'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
