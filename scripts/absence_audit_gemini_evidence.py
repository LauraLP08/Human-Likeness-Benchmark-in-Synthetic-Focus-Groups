"""
Reconstruction of the original coder's per-code quotations from the evaluator cache,
and a two-evaluator comparison of the Stage-1 evidence.

    py scripts/absence_audit_gemini_evidence.py

WITHDRAWAL
----------
The Stage-1 report stated that the original coder's per-code quotations were not stored
in any results artefact and that no direct comparison against its evidence was possible.
That was wrong. I checked only the aggregated CSVs under results/ and did not open the
evaluator cache, where every COMPLETE batch record carries `tier1.codes[].
supporting_quotes` with turn_id, speaker and quote. This module withdraws that claim and
performs the comparison that was said to be impossible.

Nothing here changes a Stage-1 metric, the Gemini coding, the salience results, the
heatmap or the workbook. It is additive evidence only.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, UTC
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import absence_audit_build as B      # noqa: E402
import absence_audit_rules as R      # noqa: E402

_OUT = _ROOT / "analysis/production_evaluation/salience_absence_audit"
_SEALED = _OUT / "sealed"
_CACHE = _ROOT / "analysis/production_evaluation/evaluator_cache"


def _atomic(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = (s.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-").replace("…", "..."))
    return re.sub(r"\s+", " ", s).strip().lower()


# ------------------------------------------------------- cache selection
def select_cache_records() -> dict:
    """
    One COMPLETE record per document, selected objectively:

      * input.sha256 equals the frozen evaluator input hash;
      * completeness.status == "COMPLETE";
      * the record's presence pattern reproduces the frozen presence grid for all 11
        codes.

    fg1 has three cached records (one pre-completeness, two COMPLETE); only one satisfies
    all three conditions. Selection by timestamp is never used.
    """
    docs = {d["doc_key"]: d for d in B.documents()}
    grid = B.presence_grid()
    codes = sorted(B.codebook())

    by_doc, rejected = defaultdict(list), []
    for f in sorted(glob.glob(str(_CACHE / "*.json"))):
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        i = j["input"]
        k = i["physical_run"] if i["side"] == "synthetic" else f"human::{i['fg']}"
        why = []
        if k not in docs:
            why.append("document not in frozen inputs")
        elif i["sha256"] != docs[k]["sha256"]:
            why.append("input sha256 differs from frozen")
        comp = j.get("completeness") or {}
        if comp.get("status") != "COMPLETE":
            why.append(f"completeness {comp.get('status')!r}")
        pres = {c["subtheme_id"]: bool(c["present"]) for c in j["tier1"]["codes"]}
        if k in docs and any(pres.get(c) != grid[(k, c)] for c in codes):
            why.append("presence pattern differs from the frozen grid")
        (rejected if why else by_doc[k]).append(
            {"file": Path(f).name, "doc_key": k, "computed_utc": j["computed_utc"],
             "reasons": why} if why else j)

    problems = []
    for k in docs:
        if len(by_doc.get(k, [])) != 1:
            problems.append(f"{k}: {len(by_doc.get(k, []))} qualifying records")
    return {"selected": {k: v[0] for k, v in by_doc.items() if len(v) == 1},
            "n_selected": sum(1 for v in by_doc.values() if len(v) == 1),
            "rejected": rejected, "problems": problems, "pass": not problems,
            "selection_rule": ("frozen input sha256, completeness.status == COMPLETE, "
                               "and presence pattern reproducing the frozen grid; "
                               "never selection by timestamp")}


def gemini_evidence(records: dict) -> dict:
    """doc_key -> subtheme_id -> [{turn_id, speaker, quote}]"""
    out, total = {}, 0
    for k, j in records.items():
        per = {}
        for c in j["tier1"]["codes"]:
            qs = [{"turn_id": q.get("turn_id"), "speaker": q.get("speaker"),
                   "quote": q.get("quote")} for q in (c.get("supporting_quotes") or [])]
            per[c["subtheme_id"]] = qs
            total += len(qs)
        out[k] = per
    return {"by_doc": out, "total_quotations": total}


# ------------------------------------------- projection into audit space
#
# THE TWO EVALUATORS DO NOT SHARE A TURN NUMBERING.
#
# Measured over all 356 original quotations: the difference between the original coder's
# turn label and the audit turn holding that same text is +1 for all five human
# documents, but VARIES WITHIN every synthetic document (observed range -6 to +14). It is
# therefore not an index-base offset that could be corrected by addition, and the two
# label spaces cannot be compared directly at all.
#
# Comparing the labels would have manufactured agreement and disagreement out of nothing.
# The QUOTE TEXT is the reliable anchor: each original quotation is located in the audit
# rendering by exact normalised substring match, and the audit's own turn id and speaker
# are read off from where it lands. All comparison happens in that single space.
#
def project_to_audit_space(bid: str, store: dict, gem: dict) -> dict:
    """
    Returns per-code evidence in AUDIT space, plus the speaker correspondence and every
    quotation that could not be located.
    """
    turns = store[bid]["turns"]
    per_code, votes, unlocalised, ambiguous_loc = {}, defaultdict(Counter), [], []
    for code, qs in gem.items():
        out = []
        for q in qs:
            nq = _norm(q["quote"])
            hits = [(t, u["speaker"]) for t, us in turns.items() for u in us
                    if nq and nq in _norm(u["text"])]
            if len(hits) != 1:
                (unlocalised if not hits else ambiguous_loc).append(
                    {"subtheme_id": code, "original_turn_label": q["turn_id"],
                     "original_speaker": q["speaker"], "n_matches": len(hits),
                     "quote": (q["quote"] or "")[:120]})
                continue
            tid, spk = hits[0]
            votes[q["speaker"]][spk] += 1
            out.append({"audit_turn_id": tid, "audit_speaker": spk,
                        "original_turn_label": q["turn_id"],
                        "original_speaker": q["speaker"],
                        "turn_label_matches_audit": tid == q["turn_id"],
                        "quote": q["quote"]})
        per_code[code] = out

    mapping = {g: c.most_common(1)[0][0] for g, c in votes.items()}
    return {"per_code": per_code, "speaker_map": mapping,
            "speaker_map_ambiguous": {g: dict(c) for g, c in votes.items()
                                      if len(c) > 1},
            "unlocalised": unlocalised, "ambiguous_localisation": ambiguous_loc,
            "n_projected": sum(len(v) for v in per_code.values())}


# ------------------------------------------------------------- comparison
SAME_TURN_SAME_SPEAKER = "SAME_TURN_SAME_SPEAKER"
SAME_TURN_DIFFERENT_SPEAKER = "SAME_TURN_DIFFERENT_SPEAKER"
DIFF_TURN_SAME_SPEAKER = "DIFFERENT_VALID_EVIDENCE_SAME_SPEAKER"
DIFF_TURN_DIFF_SPEAKER = "DIFFERENT_VALID_EVIDENCE_DIFFERENT_SPEAKER"
ADJACENT_DIVERGENCE = "ADJACENT_CODE_DIVERGENCE"
CLAUDE_NO_EVIDENCE = "CLAUDE_PRODUCED_NO_GATED_EVIDENCE"


def build() -> dict:
    cb = B.codebook()
    codes = sorted(cb)
    store = B.render_store(cb, codes)
    sel = select_cache_records()
    if not sel["pass"]:
        raise RuntimeError(f"cache selection failed: {sel['problems']}")
    gem_all = gemini_evidence(sel["selected"])

    stage1 = json.loads(
        (_OUT / "stage1_calibration_results.json").read_text(encoding="utf-8"))
    raw = json.loads((_OUT / "stage1_raw_responses.json").read_text(encoding="utf-8"))
    sealed_map = json.loads(
        (_SEALED / "sealed_document_mapping.json").read_text(encoding="utf-8"))["mapping"]

    # Claude's gated evidence per (bid, code), union over the two repetitions
    parsed = {}
    for e in raw["responses"]:
        if e["result_type"] != "succeeded":
            continue
        j = json.loads(e["raw_text"])
        parsed[(e["blinded_document_id"], e["repetition_index"])] = {
            a["code_id"]: a for a in j["assessments"]}
    claude = defaultdict(list)
    for (bid, rep), by_code in parsed.items():
        for code, a in by_code.items():
            g = R.evidence_gate(a, store[bid]["turns"])
            if g["gate"] == R.GATE_PASS:
                claude[(bid, code)].append(
                    {"repetition_index": rep, "turn_id": a.get("turn_id"),
                     "speaker": g["speaker"], "quote": a.get("quotation")})

    stage1_bids = sorted({c["blinded_document_id"] for c in stage1["cells"]})
    projected = {}
    for bid in stage1_bids:
        dk = sealed_map[bid]["doc_key"]
        projected[bid] = project_to_audit_space(bid, store, gem_all["by_doc"][dk])

    # -------------------------------------- verify the 63 positive controls
    controls, verify = [], {"n_controls": 0, "with_quotes": 0, "with_turn": 0,
                            "with_speaker": 0, "n_quotations": 0,
                            "n_projected_into_audit_space": 0}
    rows = []
    for c in stage1["cells"]:
        if c["original_status"] != R.ORIGINAL_PRESENT:
            continue
        bid, code, dk = c["blinded_document_id"], c["subtheme_id"], c["doc_key"]
        gq = gem_all["by_doc"][dk].get(code, [])
        pq = projected[bid]["per_code"].get(code, [])
        verify["n_controls"] += 1
        verify["with_quotes"] += bool(gq)
        verify["with_turn"] += bool(gq) and all(q["turn_id"] for q in gq)
        verify["with_speaker"] += bool(gq) and all(q["speaker"] for q in gq)
        verify["n_quotations"] += len(gq)
        verify["n_projected_into_audit_space"] += len(pq)

        # comparison happens ONLY in audit space
        g_turns = {q["audit_turn_id"] for q in pq}
        g_pairs = {(q["audit_turn_id"], q["audit_speaker"]) for q in pq}
        cl = claude.get((bid, code), [])

        # adjacent: a Claude turn the original coder used for a SIBLING code
        fam = cb[code]["parent_theme"]
        sib_turns = {}
        for other, qs in projected[bid]["per_code"].items():
            if other != code and cb[other]["parent_theme"] == fam:
                for q in qs:
                    sib_turns.setdefault(q["audit_turn_id"], set()).add(other)

        if not cl:
            cat, detail = CLAUDE_NO_EVIDENCE, []
        else:
            cats = set()
            detail = []
            for e in cl:
                pair = (e["turn_id"], e["speaker"])
                if pair in g_pairs:
                    k = SAME_TURN_SAME_SPEAKER
                elif e["turn_id"] in g_turns:
                    k = SAME_TURN_DIFFERENT_SPEAKER
                elif e["turn_id"] in sib_turns:
                    k = ADJACENT_DIVERGENCE
                elif e["speaker"] in {p for _, p in g_pairs}:
                    k = DIFF_TURN_SAME_SPEAKER
                else:
                    k = DIFF_TURN_DIFF_SPEAKER
                cats.add(k)
                detail.append({**e, "category": k,
                               "sibling_codes_at_that_turn":
                                   sorted(sib_turns.get(e["turn_id"], []))})
            for k in (SAME_TURN_SAME_SPEAKER, SAME_TURN_DIFFERENT_SPEAKER,
                      ADJACENT_DIVERGENCE, DIFF_TURN_SAME_SPEAKER,
                      DIFF_TURN_DIFF_SPEAKER):
                if k in cats:
                    cat = k
                    break

        controls.append({
            "blinded_document_id": bid, "doc_key": dk, "subtheme_id": code,
            "parent_theme": fam, "auditor_verdict": c["auditor_verdict"],
            "n_gemini_quotations": len(gq),
            "n_projected": len(pq),
            "gemini_audit_turns": sorted(g_turns),
            "gemini_audit_speakers": sorted({s for _, s in g_pairs}),
            "gemini_original_turn_labels": sorted({q["turn_id"] for q in gq}),
            "claude_gated_evidence": detail, "category": cat})
        rows.append({
            "blinded_document_id": bid, "subtheme_id": code, "parent_theme": fam,
            "auditor_verdict": c["auditor_verdict"], "category": cat,
            "n_gemini_quotations": len(gq),
            "gemini_audit_turns": "|".join(sorted(g_turns)),
            "claude_turns": "|".join(sorted({e["turn_id"] for e in
                                             (detail if detail else [])})),
        })

    cats = Counter(c["category"] for c in controls)
    # The per-control category is a BEST MATCH over that cell's evidence items. Reported
    # alone it would hide a cell where one repetition matched and the other diverged, so
    # the per-item distribution is reported beside it.
    per_item = Counter(e["category"] for c in controls
                       for e in c["claude_gated_evidence"])

    # ---------------- adjacent analysis regenerated with BOTH evaluators
    both_adjacent = [c for c in controls if c["category"] == ADJACENT_DIVERGENCE]
    gem_within_family = []
    for bid in stage1_bids:
        dk = sealed_map[bid]["doc_key"]
        by_turn = defaultdict(set)
        for code, qs in projected[bid]["per_code"].items():
            for q in qs:
                by_turn[q["audit_turn_id"]].add(code)
        for tid, cs in by_turn.items():
            if len(cs) > 1 and len({cb[c]["parent_theme"] for c in cs}) == 1:
                gem_within_family.append({"doc_key": dk, "audit_turn_id": tid,
                                          "codes": sorted(cs),
                                          "parent_theme": cb[list(cs)[0]]["parent_theme"]})

    undetected = [c for c in controls if c["auditor_verdict"] != R.AUD_EVIDENCE]

    return {
        "built_utc": datetime.now(UTC).isoformat(),
        "classification": "TWO_EVALUATOR_EVIDENCE_COMPARISON",
        "withdrawal": ("the Stage-1 report claimed the original coder's per-code "
                       "quotations were unavailable and that no direct comparison was "
                       "possible; that claim is withdrawn — only the aggregated CSVs "
                       "under results/ had been checked, not the evaluator cache"),
        "changes_stage1_metrics": False,
        "cache_selection": {k: sel[k] for k in
                            ("n_selected", "selection_rule", "problems", "pass")},
        "rejected_records": sel["rejected"],
        "gemini_quotations_total_corpus": gem_all["total_quotations"],
        "verification_of_63_controls": verify,
        "turn_label_spaces_do_not_align": {
            "finding": ("the original coder's turn labels and the audit's turn ids are "
                        "different spaces; the difference is +1 for all five human "
                        "documents but varies within every synthetic document "
                        "(observed -6 to +14), so it is not a correctable index base"),
            "consequence": ("comparison is performed only after projecting each original "
                            "quotation into audit space by exact normalised text match; "
                            "turn labels are never compared directly"),
            "n_original_quotations_corpus": gem_all["total_quotations"],
            "n_uniquely_localisable_corpus": 351,
            "n_not_uniquely_localisable_corpus": 5},
        "speaker_reconciliation": {
            bid: {"map": projected[bid]["speaker_map"],
                  "ambiguous": projected[bid]["speaker_map_ambiguous"],
                  "n_projected": projected[bid]["n_projected"],
                  "unlocalised": projected[bid]["unlocalised"],
                  "ambiguous_localisation": projected[bid]["ambiguous_localisation"]}
            for bid in stage1_bids},
        "comparison_categories_per_control": dict(cats),
        "comparison_categories_per_evidence_item": dict(per_item),
        "category_note": ("per_control is a best match over that cell's evidence items, "
                          "in the order same-turn-same-speaker, same-turn-different-"
                          "speaker, adjacent-code divergence, different-valid-evidence; "
                          "per_evidence_item is the unaggregated distribution"),
        "controls": controls,
        "adjacent_two_evaluator": {
            "claude_evidence_at_a_turn_the_original_coder_used_for_a_sibling_code":
                both_adjacent,
            "n": len(both_adjacent),
            "original_coder_same_turn_two_codes_one_family": gem_within_family,
            "n_original_coder_within_family": len(gem_within_family)},
        "undetected_controls_with_original_evidence": [
            {"subtheme_id": c["subtheme_id"], "blinded_document_id":
             c["blinded_document_id"], "auditor_verdict": c["auditor_verdict"],
             "n_gemini_quotations": c["n_gemini_quotations"],
             "gemini_audit_turns": c["gemini_audit_turns"],
             "gemini_audit_speakers": c["gemini_audit_speakers"]}
            for c in undetected],
        "_rows": rows,
    }


def main() -> int:
    b = build()
    rows = b.pop("_rows")
    _atomic(_OUT / "stage1_two_evaluator_evidence.json", b)
    with (_OUT / "stage1_two_evaluator_controls.csv").open(
            "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    v = b["verification_of_63_controls"]
    print("=== cache reconstruction ===")
    print(f"  records selected            {b['cache_selection']['n_selected']}/35")
    print(f"  rejected                    {len(b['rejected_records'])}")
    print(f"  Gemini quotations, corpus   {b['gemini_quotations_total_corpus']}")
    print(f"\n=== the 63 Stage-1 positive controls ===")
    print(f"  controls                    {v['n_controls']}")
    print(f"  with supporting quotations  {v['with_quotes']}/{v['n_controls']}")
    print(f"  every quote has turn_id     {v['with_turn']}/{v['n_controls']}")
    print(f"  every quote has speaker     {v['with_speaker']}/{v['n_controls']}")
    print(f"  quotations on these 63      {v['n_quotations']}")
    print(f"  projected into audit space  {v['n_projected_into_audit_space']}"
          f"/{v['n_quotations']}")
    amb = sum(1 for s in b["speaker_reconciliation"].values() if s["ambiguous"])
    unl = sum(len(s["unlocalised"]) for s in b["speaker_reconciliation"].values())
    aml = sum(len(s["ambiguous_localisation"])
              for s in b["speaker_reconciliation"].values())
    print(f"\n  speaker maps ambiguous      {amb}/14")
    print(f"  quotes not located          {unl}   ambiguous location {aml}")
    print("  turn label spaces align     NO (projection by quote text is used)")
    print("\n=== Claude vs original coder ===")
    print("  per control (best match over that cell's evidence):")
    for k, n in sorted(b["comparison_categories_per_control"].items(),
                       key=lambda x: -x[1]):
        print(f"    {k:42s} {n}")
    print("  per evidence item (unaggregated):")
    for k, n in sorted(b["comparison_categories_per_evidence_item"].items(),
                       key=lambda x: -x[1]):
        print(f"    {k:42s} {n}")
    a = b["adjacent_two_evaluator"]
    print(f"\n=== adjacency, both evaluators ===")
    print(f"  Claude cited a turn the original coder used for a sibling code: {a['n']}")
    print(f"  original coder used one turn for two codes in one family: "
          f"{a['n_original_coder_within_family']}")
    for r in a["original_coder_same_turn_two_codes_one_family"][:8]:
        print(f"     {r['doc_key']:34s} {r['audit_turn_id']} {r['codes']}")
    print(f"\n=== the 3 undetected controls, with the original evidence ===")
    for c in b["undetected_controls_with_original_evidence"]:
        print(f"  {c['subtheme_id']:4s} {c['blinded_document_id']} "
              f"{c['auditor_verdict']}  gemini {c['n_gemini_quotations']} quotes at "
              f"{c['gemini_audit_turns']} by {c['gemini_audit_speakers']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
