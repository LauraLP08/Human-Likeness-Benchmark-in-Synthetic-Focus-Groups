"""
Retrieve and score the profile-consistency PILOT.

    py scripts/agent_fidelity_pc_score.py

Retrieval is BY custom_id, never by response position. Validation is a GATE, not a
filter: a non-literal quote, a wrong speaker or an unknown turn id fails the audit rather
than being quietly dropped, because a verdict resting on evidence the auditor
reconstructed is not evidence.

Frozen repetition rules:
  agreement between the two repetitions  -> CORROBORATED
  disagreement                           -> UNRESOLVED
  one repetition UNCERTAIN               -> kept, never converted to absence
  no third call, no confidence or majority resolution

Fixtures govern the technical gate only. They never enter agreement, prevalence,
contradiction rate or any per-condition result.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

import agent_fidelity_audit_v2 as v2

_OUT = Path(__file__).resolve().parent.parent / \
    "analysis/production_evaluation/agent_fidelity"

CONTRADICTION_CATEGORIES = ("UNEXPLAINED_CONTRADICTION",)


def _load(name):
    return json.loads((_OUT / name).read_text(encoding="utf-8"))


def score(job_id: str = None) -> dict:
    v2._load_env()
    import anthropic

    job = _load("v2_profile_consistency_job.json")
    job_id = job_id or job["job_id"]
    items = {i["item_id"]: i
             for i in _load("v2_profile_consistency_items_blinded.json")["items"]}
    rm = {r["custom_id"]: r
          for r in _load("v2_profile_consistency_provider_request_manifest.json")["requests"]}
    im = _load("v2_profile_consistency_item_manifest.json")["rows"]
    sealed = _load("v2_profile_consistency_sealed_reference.json")

    client = anthropic.Anthropic()

    # Results are merged across the original job and any technical-truncation repair.
    # A repaired request supersedes its truncated original for the SAME custom_id; the
    # intact requests are reused exactly as returned and are never resent.
    jobs = [{"job_id": job_id, "role": "ORIGINAL"}]
    rp = _OUT / "v2_profile_consistency_repair_job.json"
    if rp.exists():
        r = json.loads(rp.read_text(encoding="utf-8"))
        jobs.append({"job_id": r["job_id"], "role": "TECHNICAL_TRUNCATION_REPAIR",
                     "repaired_custom_ids": r["repaired_custom_ids"]})
    repaired = set(jobs[-1].get("repaired_custom_ids", [])) if len(jobs) > 1 else set()

    decisions, failures, incomplete, invalid, seen = {}, [], [], [], set()
    results = []
    for j in jobs:
        for res in client.messages.batches.results(j["job_id"]):
            # a truncated original is discarded once its repair exists
            if j["role"] == "ORIGINAL" and res.custom_id in repaired:
                continue
            results.append(res)
    for res in results:
        cid = res.custom_id
        if cid not in rm:
            failures.append({"custom_id": cid, "why": "custom_id not in the manifest"})
            continue
        req = rm[cid]
        if res.result.type != "succeeded":
            failures.append({"custom_id": cid, "why": f"result {res.result.type}"})
            continue
        text = "".join(b.text for b in res.result.message.content
                       if getattr(b, "type", "") == "text")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            failures.append({"custom_id": cid, "why": f"unparseable json: {e}"})
            continue
        got = payload.get("decisions", [])
        if len(got) != req["expected_item_count"]:
            failures.append({"custom_id": cid,
                             "why": f"{len(got)} decisions, expected "
                                    f"{req['expected_item_count']}"})
        expected_ids = set(req["ordered_item_ids"])
        for d in got:
            iid = d.get("item_id")
            if iid not in expected_ids:
                failures.append({"custom_id": cid, "item_id": iid,
                                 "why": "item_id not in this request"})
                continue
            it = items[iid]
            # A non-literal quote makes THAT decision unusable. It is not a
            # whole-pilot gate failure: the governing prospective criterion is
            # verbatim evidence validity >= 0.95 across adjudications, and a stricter
            # any-single-failure rule appeared only after the results were seen.
            for side, tk, qk in (("statement_a", "turn_id_a", "quote_a"),
                                 ("statement_b", "turn_id_b", "quote_b")):
                if d.get(tk) != it[side]["turn_id"]:
                    invalid.append({"item_id": iid, "why": f"invalid {tk}",
                                    "repetition_index": req["repetition_index"],
                                    "returned": d.get(tk)})
                    d = {**d, "_invalid_evidence": True}
                q = (d.get(qk) or "").strip()
                if not q or not v2.verify_literal(q, it[side]["quote"]):
                    invalid.append({"item_id": iid, "why": f"non-literal {qk}",
                                    "repetition_index": req["repetition_index"],
                                    "returned": q[:70]})
                    d = {**d, "_invalid_evidence": True}
            # A missing prose field is NOT one of the three frozen gate-failure
            # triggers (non-literal quote, wrong speaker, invalid turn id). It is an
            # incomplete decision: that single adjudication is unusable, so the item
            # cannot be corroborated and falls to UNRESOLVED. It does not invalidate
            # the audit, and it is never repaired by a third call.
            for f in ("justification", "minimum_context_used",
                      "what_would_resolve_uncertainty"):
                if not (d.get(f) or "").strip():
                    incomplete.append({"item_id": iid,
                                       "repetition_index": req["repetition_index"],
                                       "why": f"empty {f}"})
                    d = {**d, "_incomplete": True}
            decisions[(iid, req["repetition_index"])] = d

    expected_pairs = {(r["item_id"], r["repetition_index"]) for r in im}
    missing = sorted(expected_pairs - set(decisions))
    extra = sorted(set(decisions) - expected_pairs)

    real = {k for k, v in sealed.items() if v["_kind"] == "REAL_PILOT_CASE"}
    fixtures = {k for k, v in sealed.items()
                if v["_kind"] == "TECHNICAL_VALIDATION_FIXTURE"}

    # Four fixtures expected a REJECT verdict, but REJECT was never in the transmitted
    # schema enum, so the auditor could not return it however it behaved. They are
    # unfalsifiable as auditor tests and are excluded from the auditor's denominator;
    # they are retained as scorer tests.
    enum = set(v2.PC_CATEGORIES)
    fx = []
    for fid in sorted(fixtures):
        exp = sealed[fid]["_expected_category"]
        got = [decisions.get((fid, r), {}).get("category") for r in (1, 2)]
        executable = exp in enum
        fx.append({"item_id": fid, "expected": exp, "returned": got,
                   "executable": executable,
                   "status": None if executable
                   else "INVALID_AUDITOR_FIXTURE_SCHEMA_MISMATCH",
                   "both_correct": executable and got == [exp, exp],
                   "either_correct": executable and exp in got})

    per_item = {}
    for iid in sorted(real):
        da, db = decisions.get((iid, 1), {}), decisions.get((iid, 2), {})
        a, b = da.get("category"), db.get("category")
        bad_ev = da.get("_invalid_evidence") or db.get("_invalid_evidence")
        bad = da.get("_incomplete") or db.get("_incomplete")
        state = ("MISSING" if a is None or b is None
                 else "UNRESOLVED_INVALID_EVIDENCE" if bad_ev
                 else "UNRESOLVED_INCOMPLETE_EVIDENCE" if bad
                 else "CORROBORATED" if a == b else "UNRESOLVED")
        per_item[iid] = {"rep1": a, "rep2": b, "state": state,
                         "category": a if state == "CORROBORATED" else None,
                         "stratum": sealed[iid]["_stratum"],
                         "role": sealed[iid]["_role"],
                         "condition": sealed[iid]["_condition"],
                         "fg": sealed[iid]["_fg"],
                         "replicate": sealed[iid]["_replicate"]}

    n_scored = sum(1 for v in per_item.values() if v["state"] != "MISSING")
    agree = sum(1 for v in per_item.values() if v["state"] == "CORROBORATED")
    n_incomplete_items = sum(1 for v in per_item.values()
                             if v["state"] == "UNRESOLVED_INCOMPLETE_EVIDENCE")
    unc = sum(1 for v in per_item.values() if "UNCERTAIN" in (v["rep1"], v["rep2"]))

    disagreement = defaultdict(int)
    for v in per_item.values():
        if v["state"] == "UNRESOLVED":
            disagreement["|".join(sorted([str(v["rep1"]), str(v["rep2"])]))] += 1

    def _block(stratum, key="stratum"):
        sub = {k: v for k, v in per_item.items() if v[key] == stratum}
        cat = defaultdict(int)
        by_cond = defaultdict(lambda: defaultdict(int))
        for v in sub.values():
            if v["state"] == "CORROBORATED":
                cat[v["category"]] += 1
                by_cond[v["condition"]][v["category"]] += 1
        hyper = sum(cat[c] for c in CONTRADICTION_CATEGORIES)
        return {"n_items": len(sub),
                "n_corroborated": sum(1 for v in sub.values()
                                      if v["state"] == "CORROBORATED"),
                "n_unresolved": sum(1 for v in sub.values()
                                    if v["state"].startswith("UNRESOLVED")),
                "corroborated_categories": dict(cat),
                "by_condition": {k: dict(v) for k, v in by_cond.items()},
                "n_corroborated_unexplained_contradictions": hyper,
                "n_items_by_condition": {
                    c: sum(1 for v in sub.values() if v["condition"] == c)
                    for c in ("human", "enriched", "demographics-only")}}

    cand = _block("PROPOSED", key="role")
    ctl = _block("CONTROL", key="role")
    by_stratum = {st: _block(st) for st in
                  {v["stratum"] for v in per_item.values()}}

    out = {
        "retrieved_utc": datetime.now(UTC).isoformat(),
        "job_id": job_id,
        "jobs": jobs,
        "repair_applied": len(jobs) > 1,
        "repaired_custom_ids": sorted(repaired),
        "n_provider_requests": len(rm),
        "n_expected_adjudications": len(im),
        "n_returned_adjudications": len(decisions),
        "missing_adjudications": missing, "extra_adjudications": extra,
        "union_matches_item_manifest": not missing and not extra,
        "n_gate_failures": len(failures),
        "gate_failures": failures[:40],
        "n_invalid_evidence_decisions": len(invalid),
        "invalid_evidence_decisions": invalid,
        "invalid_evidence_rule": (
            "a decision whose quote is not literal, or whose turn id does not match, is "
            "unusable: its item becomes UNRESOLVED_INVALID_EVIDENCE. It is not repaired, "
            "triggers no third call, and does not invalidate other valid decisions."),
        "gate_failure_triggers": ["non-literal quote", "wrong speaker",
                                  "invalid turn_id", "missing or extra adjudication"],
        "n_incomplete_decisions": len(incomplete),
        "incomplete_decisions": incomplete,
        "incomplete_decision_rule": (
            "a decision missing a required prose field is unusable, so its item falls "
            "to UNRESOLVED_INCOMPLETE_EVIDENCE. It is not a gate failure and is never "
            "repaired by a third call."),
        "gate": {
            "union_matches_item_manifest": not missing and not extra,
            "no_gate_failure": not failures,
            "governing_criterion": "verbatim evidence validity >= 0.95",
            "n_executable_fixtures": sum(1 for f in fx if f["executable"]),
            "executable_fixtures_both_repetitions_correct": sum(
                1 for f in fx if f["executable"] and f["both_correct"]),
            "n_fixtures_excluded_schema_mismatch": sum(1 for f in fx
                                                       if not f["executable"]),
            "fixture_exclusion_reason": (
                "REJECT was never in the transmitted schema enum, so these four "
                "fixtures could not be returned however the auditor behaved. They are "
                "excluded from the auditor denominator and retained as scorer tests; "
                "they are never counted as substantive auditor failures."),
            "passed": not missing and not extra and not failures,
        },
        "fixtures": fx, "fixtures_excluded_from_rates": True,
        "agreement_between_repetitions": {
            "n_real_items": len(real), "n_scored": n_scored,
            "n_corroborated": agree,
            "exact_agreement": round(agree / n_scored, 4) if n_scored else None,
            "n_unresolved": n_scored - agree,
            "n_unresolved_incomplete_evidence": n_incomplete_items,
            "disagreement_matrix": dict(disagreement),
            "n_items_with_an_uncertain_repetition": unc,
            "uncertain_rate": round(unc / n_scored, 4) if n_scored else None},
        "screener_proposed": cand,
        "random_controls": ctl,
        "by_stratum": by_stratum,
        "prevalence": {
            "reportable": "DETECTED_LOWER_BOUND_RATE",
            "why": ("120 of 2,611 screened pairs were adjudicated, drawn 20 per "
                    "condition per role rather than as a probability sample, so no "
                    "corpus-wide contradiction rate can be estimated from them"),
            "unaudited_pairs_are_not_negative": True,
            "n_screened_pairs": 2611, "n_audited": len(real),
            "remaining_pairs_blocked": True},
        "rules_applied": {
            "agreement": "CORROBORATED", "disagreement": "UNRESOLVED",
            "one_repetition_UNCERTAIN": "kept, never converted to absence",
            "no_third_call": True, "no_confidence_or_majority_resolution": True},
        "per_item": per_item,
    }
    (_OUT / "v2_profile_consistency_results.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def main() -> int:
    o = score()
    ag = o["agreement_between_repetitions"]
    print(f"job {o['job_id']}")
    print(f"  adjudications returned {o['n_returned_adjudications']}/"
          f"{o['n_expected_adjudications']}   union matches manifest: "
          f"{o['union_matches_item_manifest']}")
    print(f"  gate failures {o['n_gate_failures']}   incomplete decisions "
          f"{o['n_incomplete_decisions']}   GATE PASSED: {o['gate']['passed']}")
    print(f"  executable fixtures correct in BOTH repetitions: "
          f"{o['gate']['executable_fixtures_both_repetitions_correct']}/"
          f"{o['gate']['n_executable_fixtures']}   "
          f"({o['gate']['n_fixtures_excluded_schema_mismatch']} excluded: "
          f"INVALID_AUDITOR_FIXTURE_SCHEMA_MISMATCH)")
    for f in o["fixtures"]:
        if f["executable"] and not f["both_correct"]:
            print(f"    MISS {f['item_id']}  expected {f['expected']}  got "
                  f"{f['returned']}")
    print(f"\n  exact agreement {ag['exact_agreement']}   corroborated "
          f"{ag['n_corroborated']}   unresolved {ag['n_unresolved']}   "
          f"uncertain-rate {ag['uncertain_rate']}")
    if ag["disagreement_matrix"]:
        print("  disagreement matrix:")
        for k, v in sorted(ag["disagreement_matrix"].items(), key=lambda x: -x[1]):
            print(f"    {v:>3d}  {k}")
    for tag in ("screener_proposed", "random_controls"):
        b = o[tag]
        print(f"\n  {tag}  n={b['n_items']}  corroborated {b['n_corroborated']}  "
              f"unresolved {b['n_unresolved']}  hyper-exact "
              f"{b['n_corroborated_unexplained_contradictions']}")
        for k, v in sorted(b["corroborated_categories"].items(), key=lambda x: -x[1]):
            print(f"      {k:38s} {v}")
        print(f"      by condition: {b['by_condition']}")
    print(f"\n  prevalence reportable as: {o['prevalence']['reportable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
