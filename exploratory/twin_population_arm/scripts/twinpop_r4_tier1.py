#!/usr/bin/env python3
"""
twinpop_r4_tier1.py — the four-condition Tier-1 table, and the P1 verdict applied
exactly as pre-registered.

P1, verbatim from the pre-registration:
    "El recall de `twinpop` cae más cerca de `demoonly` que de `full`."
    Evaluated on the MEAN of the 3 replicates per FG; per-replicate classification
    also reported. Equidistance (< 0.01) is declared UNDECIDED, not favourable.
    PRIMARY EVALUATION IN FG3. Falsifier: twinpop reaching or exceeding full's mean.

No threshold is invented here. The only numeric constant is the 0.01 equidistance
band, which is quoted from the pre-registration and was fixed before any twinpop
document was coded.

REGRESSION CHECK
Recall is recomputed for the canonical conditions from the same cache entries, and
compared with facts the pre-registration asserted about them BEFORE this arm existed
(`demoonly` FG4 scoring zero of six codes three times; FG4's denominator of 6; FG3's
of 10). If the recomputation cannot reproduce what the corpus already published, the
twinpop numbers computed the same way mean nothing, and the script says so instead of
printing a table.

Offline. Reads the evaluator cache; makes no API call.

Usage:
    py scripts/twinpop_r4_tier1.py --out-dir analysis/production_evaluation/twinpop
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import thematic_coding as tc  # noqa: E402

CACHE = ROOT / "analysis" / "production_evaluation" / "evaluator_cache"
CONDITIONS = ("enriched", "demographics-only", "twinpop")
FULL, DEMO, TWIN = "enriched", "demographics-only", "twinpop"
EQUIDISTANCE_BAND = 0.01     # pre-registered, not chosen here
PRIMARY_FG = "fg3"


def load_docs() -> dict:
    """COMPLETE, batch-mode entries only. A quarantined entry is not a result, and a
    synchronous entry answers a different cache key than the corpus was coded under —
    mixing them would compare twinpop against a differently-keyed baseline."""
    docs: dict = {}
    for p in glob.glob(str(CACHE / "*.json")):
        e = json.loads(Path(p).read_text(encoding="utf-8"))
        if e.get("completeness", {}).get("status") != "COMPLETE":
            continue
        if e.get("execution_mode") != "batch":
            continue
        i = e.get("input", {})
        cond = i.get("condition") or i.get("side")
        docs.setdefault((cond, i.get("fg")), []).append(
            (i.get("canonical_replication_index"), i.get("physical_run"), e["tier1"]))
    return docs


def scores_for(docs: dict, cond: str, fg: str) -> list[dict]:
    human = tc.Tier1Result.model_validate(docs[("human", fg)][0][2])
    out = []
    for rep, run, t in sorted(docs[(cond, fg)]):
        s = tc.compute_tier1_scores(human, tc.Tier1Result.model_validate(t))
        out.append({"replicate": rep, "run": run,
                    "recall": round(s.subtheme_recall, 4),
                    "precision": round(s.subtheme_precision, 4),
                    "f1": round(s.subtheme_f1, 4)})
    return out


def human_code_count(docs: dict, fg: str) -> int:
    h = tc.Tier1Result.model_validate(docs[("human", fg)][0][2])
    return len({c.subtheme_id for c in h.codes if c.present and c.quote_verified})


def regression_check(docs: dict) -> tuple[bool, list[dict]]:
    """Facts the corpus published before this arm existed. Recomputing them from the
    cache is the only evidence that the twinpop numbers were produced by the same
    procedure as the numbers they will sit next to."""
    checks = []
    demo_fg4 = [r["recall"] for r in scores_for(docs, DEMO, "fg4")]
    checks.append({
        "claim": "demoonly FG4 scores zero of six codes, three times running",
        "source": "pre-registro §2.1",
        "observed": demo_fg4,
        "holds": demo_fg4 == [0.0, 0.0, 0.0]})
    n4 = human_code_count(docs, "fg4")
    checks.append({"claim": "FG4 human denominator is 6 (one code = 0.1667)",
                   "source": "pre-registro §2.1", "observed": n4, "holds": n4 == 6})
    n3 = human_code_count(docs, "fg3")
    checks.append({"claim": "FG3 human denominator is 10",
                   "source": "derived from the same corpus", "observed": n3,
                   "holds": n3 == 10})
    enr3 = [r["recall"] for r in scores_for(docs, FULL, "fg3")]
    dem3 = [r["recall"] for r in scores_for(docs, DEMO, "fg3")]
    checks.append({
        "claim": "FG3 enriched separates from demoonly with no overlap across replicates",
        "source": "pre-registro §2.1",
        "observed": {"enriched": enr3, "demoonly": dem3},
        "holds": min(enr3) > max(dem3)})
    return all(c["holds"] for c in checks), checks


def p1_verdict(means: dict) -> dict:
    """P1 applied literally, on the mean, for one FG."""
    d_full = abs(means[TWIN] - means[FULL])
    d_demo = abs(means[TWIN] - means[DEMO])
    falsifier = means[TWIN] >= means[FULL]
    if abs(d_full - d_demo) < EQUIDISTANCE_BAND:
        verdict = "UNDECIDED_EQUIDISTANT"
    elif d_demo < d_full:
        verdict = "P1_SUPPORTED_twinpop_closer_to_demoonly"
    else:
        verdict = "P1_REFUTED_twinpop_closer_to_full"
    return {"mean_full": round(means[FULL], 4), "mean_demoonly": round(means[DEMO], 4),
            "mean_twinpop": round(means[TWIN], 4),
            "distance_to_full": round(d_full, 4),
            "distance_to_demoonly": round(d_demo, 4),
            "equidistance_band": EQUIDISTANCE_BAND,
            "explicit_falsifier_twinpop_reaches_or_exceeds_full": falsifier,
            "verdict": verdict}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    docs = load_docs()

    ok, checks = regression_check(docs)
    print("CHEQUEO DE REGRESION — reproducir lo que el corpus ya publico\n")
    for c in checks:
        print(f"  {'OK   ' if c['holds'] else 'FALLA'} {c['claim']}")
        print(f"         observado: {c['observed']}")
    if not ok:
        print("\nFALLA: no se reproduce el corpus canonico; no se imprime tabla.")
        (args.out_dir / "twinpop_r4_tier1.json").write_text(
            json.dumps({"regression_ok": False, "checks": checks}, indent=1,
                       ensure_ascii=False), encoding="utf-8")
        return 1

    table, verdicts = {}, {}
    print("\n\nTABLA DE CUATRO CONDICIONES — recall Tier-1 contra la linea base humana\n")
    for fg in ("fg3", "fg4"):
        n = human_code_count(docs, fg)
        print(f"  {fg.upper()}  (denominador humano = {n} codigos)")
        means = {}
        table[fg] = {"human_codes": n, "conditions": {}}
        for cond in CONDITIONS:
            rows = scores_for(docs, cond, fg)
            rec = [r["recall"] for r in rows]
            means[cond] = statistics.fmean(rec)
            table[fg]["conditions"][cond] = {
                "per_replicate": rows, "mean_recall": round(means[cond], 4),
                "mean_precision": round(statistics.fmean([r["precision"] for r in rows]), 4)}
            label = {FULL: "enriched (full)", DEMO: "demographics-only",
                     TWIN: "twinpop (placebo)"}[cond]
            print(f"     {label:<22} recall {rec}  media {means[cond]:.4f}"
                  f"   precision media "
                  f"{statistics.fmean([r['precision'] for r in rows]):.4f}")
        v = p1_verdict(means)
        verdicts[fg] = v
        print(f"     -> twinpop dista {v['distance_to_full']:.4f} de full y "
              f"{v['distance_to_demoonly']:.4f} de demoonly")
        print(f"     -> {v['verdict']}\n")

    out = {"regression_ok": True, "regression_checks": checks,
           "equidistance_band_preregistered": EQUIDISTANCE_BAND,
           "primary_fg": PRIMARY_FG, "table": table, "p1_by_fg": verdicts,
           "p1_primary": verdicts[PRIMARY_FG],
           "fg4_is_floor_test_only": (
               "El pre-registro asigna a FG4 lectura de SUELO (cero vs no-cero), sin "
               "lectura de tamaño. Su veredicto P1 se registra pero no decide.")}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "twinpop_r4_tier1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"VEREDICTO PRIMARIO (FG3): {verdicts[PRIMARY_FG]['verdict']}")
    print(f"-> {args.out_dir / 'twinpop_r4_tier1.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
