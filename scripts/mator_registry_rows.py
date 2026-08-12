"""
Register the Mator-comparable metrics in `metric_registry.csv`.

Idempotent and append-only: existing rows are never rewritten, and re-running
after the rows are present is a no-op that reports "already registered". The
file is rewritten with the same dialect it was read with, so the 46 pre-existing
rows round-trip byte-identically (asserted on the raw bytes before anything is
written).

Evidence class is `AUTOMATIC_PROXY_EXPLORATORY` for all five rows, as specified
by §3 of `INSTRUCTIONS_MATOR_BERTSCORE_METRICS.md`, which attributes the class to
the adenda of 3 August 2026 (`adenda_v2_saturacion_verificada_y_consenso_
automatico_2026-08-03.md`, which introduces it as a new namespace for automatic
deterministic non-LLM-judged proxies). `AUTOMATIC_VALIDATED` is deliberately not
reused: in this registry it is reserved for metrics already validated as primary
or secondary evidence.

THE CONSUMER, NOT JUST THE FILE. `AUTOMATIC_PROXY_EXPLORATORY` matches the
`startswith("AUTOMATIC")` test in
`aggregate_production_results.registry_automatic_metrics()`, so these rows enter
the AUTOMATIC parity set the moment they are written. Appending without also
declaring them in `PRODUCED_ELSEWHERE` breaks
`tests/test_aggregate_production_results.py::
test_pipeline_produces_exactly_the_registry_automatic_metrics`. This script
therefore refuses to write until parity would still hold *after* the append, and
until every declared artifact and column actually exists on disk.

Usage:
    py scripts/mator_registry_rows.py            # dry run, prints what it would add
    py scripts/mator_registry_rows.py --write
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REGISTRY = _REPO_ROOT / "analysis" / "production_evaluation" / "metric_registry.csv"

EVIDENCE_CLASS = "AUTOMATIC_PROXY_EXPLORATORY"
NAMESPACE = "_comparable_window"

_MATOR_CITE = (
    "Mator et al. (2025), 'Exploring Accessible Focus Groups with Cognitive Persona "
    "Generation and AI Agents', Table 4 (n=3 per side)"
)

NEW_ROWS = [
    {
        "metric_id": "mator_conversational_completeness",
        "tier": "exploratory",
        "category": "exploratory",
        "evidence_class": EVIDENCE_CLASS,
        "namespace": NAMESPACE,
        "unit_of_analysis": "focus group",
        "definition": (
            "Share of the prompted discussion-guide topics actually reached. A topic "
            "counts as reached when its guide section carries at least one participant "
            "turn: synthetic sections come from the logged moderator section_transition, "
            "human sections from the 'Question N.' header convention (both via "
            "scripts/tier2b_segmentation.py). Reported beside an independent token-match "
            "reading that does not consult section labels at all: a topic counts as "
            "reached when some moderator turn in the window carries at least half of that "
            "question's distinctive content tokens."
        ),
        "numerator": "substantive guide sections (1-5) with >=1 participant turn",
        "denominator": "5 substantive guide sections (0 introduction and 6 closing excluded: outside the comparable window and absent from the human transcripts)",
        "aggregation": "per run -> per FG x condition",
        "notes_and_caveats": (
            f"Mator-comparable proxy. {_MATOR_CITE}: 'Conversational completeness', "
            "AI 100%, Human 100%. Measures whether the topic was reached, not how well "
            "it was covered. On the human side a missing 'Question N.' header makes the "
            "topic unmeasurable rather than proven absent - fg5 has no Question 4 header "
            "and its material, if present, sits inside section 3, so human fg5 reads 4/5 "
            "and is the only unit of the 35 below 5/5. In 2 synthetic runs "
            "(macho_meals_fg1_demoonly_run01, macho_meals_fg4_demoonly_run01) the "
            "moderator asked question 1 while still inside guide section 0, so the "
            "label-based reading reaches the right answer by the wrong route: it counts 5 "
            "labels, and those labels carry Q2, Q2, Q3, Q4, Q5 while Q1 sits in label 0. "
            "All five questions were in fact asked - verifiable row by row in "
            "mator_completeness_openers.csv, which pairs every section-opening moderator "
            "turn with the guide question its label is supposed to carry. An automatic "
            "token-overlap cross-check was built and REMOVED rather than shipped: Q2's "
            "only content token (decide) is contained in Q4 (decided), so every setting "
            "flagged all 35 units. Computed by scripts/mator_completeness.py."
        ),
    },
    {
        "metric_id": "mator_relevance_of_response_bertscore_f1",
        "tier": "exploratory",
        "category": "exploratory",
        "evidence_class": EVIDENCE_CLASS,
        "namespace": NAMESPACE,
        "unit_of_analysis": "turn",
        "definition": (
            "BERTScore F1 (Zhang et al., 2019) between each participant turn and the "
            "most recent preceding moderator turn inside the comparable window. Actual "
            "bert-score package, roberta-large layer 17, no idf, no baseline rescaling - "
            "NOT sentence-transformer cosine."
        ),
        "numerator": "-",
        "denominator": "participant turns with a preceding moderator turn in the window",
        "aggregation": "mean over participant turns -> per run -> per FG x condition",
        "notes_and_caveats": (
            f"Mator-comparable proxy. {_MATOR_CITE}: 'Relevance of Response', AI 83%, "
            "Human 82%. (1) SCALE: the EXPECTED raw F1 for unrelated fluent English at "
            "this model/layer is 0.8312 (the package's rescaling baseline - a mean over "
            "a random-pair corpus, not a hard floor; unrelated pairs land on both sides "
            "of it), so a raw value in the 0.80-0.95 band is not by itself evidence of "
            "relevance and the baseline-rescaled companion should carry any substantive "
            "claim. Whether Mator's 83%/82% sit at that expectation is CONDITIONAL on a "
            "configuration their paper does not report: the same expectation is 0.35 for "
            "bert-base-uncased and 0.81 for roberta-base. Do not state it unconditionally. "
            "(2) LENGTH: synthetic participant turns average ~3.5x human ones and the "
            "synthetic moderator ~3x, and this project has already shown length drives "
            "most of the analogous published gap; a length-matched companion (both sides "
            "truncated to W = median human participant turn words for that FG) is "
            "reported beside the raw figure and is the one to quote for a fidelity claim. "
            "(3) 'The question it responds to' is the most recent preceding moderator "
            "turn, which includes mid-section probes; a variant scored against the "
            "section-opening question only is reported beside it. (4) Encoder truncates "
            "at 512 tokens, which bites the long (synthetic) side first. Computed by "
            "scripts/mator_bertscore_metrics.py; all 35 units."
        ),
    },
    {
        "metric_id": "mator_between_participant_similarity_bertscore_f1",
        "tier": "exploratory",
        "category": "exploratory",
        "evidence_class": EVIDENCE_CLASS,
        "namespace": NAMESPACE,
        "unit_of_analysis": "guide section",
        "definition": (
            "BERTScore F1 between all cross-speaker pairs of participant turns within a "
            "guide section, averaged within the section and then across sections. Actual "
            "bert-score package, roberta-large layer 17, no idf, no baseline rescaling - "
            "NOT sentence-transformer cosine."
        ),
        "numerator": "-",
        "denominator": "cross-speaker participant-turn pairs within each qualifying guide section",
        "aggregation": "mean within section -> mean across sections -> per run -> per FG x condition",
        "notes_and_caveats": (
            f"Mator-comparable proxy. {_MATOR_CITE}: 'Response similarity between "
            "participants', AI 91%, Human 83%. Mator asked 7 fixed questions once each; "
            "these sessions run emergent within guide SECTIONS, so 'responses to the same "
            "question' is operationalised as 'participant turns in the same guide section' "
            "- a wider unit than theirs. Carries the same SCALE and LENGTH caveats as "
            "mator_relevance_of_response_bertscore_f1, including its length-matched "
            "companion. UNIVERSE: 2 of the 30 synthetic runs are excluded entirely "
            "because the moderator asked guide question 1 while still inside guide "
            "section 0, so from that point every section label names a different guide "
            "question than its index (and two consecutive labels carry the same "
            "question); they are named in mator_bertscore_spec.json under "
            "corpus.section_label_misaligned_runs and remain in the relevance metric, "
            "which does not use section labels. Sections below the Tier 2b data floor "
            "(>=3 participant turns, >=150 words) or holding a single speaker are "
            "excluded and listed individually in mator_section_floor_skips.csv. Computed "
            "by scripts/mator_bertscore_metrics.py."
        ),
    },
    {
        "metric_id": "mator_agreement_consecutive_turn_similarity",
        "tier": "exploratory",
        "category": "exploratory",
        "evidence_class": EVIDENCE_CLASS,
        "namespace": NAMESPACE,
        "unit_of_analysis": "turn transition",
        "definition": (
            "Mean sentence-transformer cosine similarity between a participant turn and "
            "the immediately preceding turn when that turn is also a participant's, "
            "within the same guide section (the frozen response-act universe in "
            "consensus_dynamics/response_acts.csv). Sentence-pooled whole turn (R2, "
            "primary) and length-matched (R3, control), same model and same rules as "
            "scripts/consensus_dynamics_metrics.py. Computed by "
            "scripts/mator_agreement_strict.py; the BRIDGED variant "
            "(mator_agreement_R2/R3) is REUSED unchanged from "
            "consensus_dynamics/mator_d4_d5_by_unit.csv and reported beside it."
        ),
        "numerator": "-",
        "denominator": "strict participant-follows-participant response acts within a comparable guide section",
        "aggregation": "mean over response acts -> per run -> per FG x condition",
        "notes_and_caveats": (
            f"Mator-comparable proxy. {_MATOR_CITE}: 'Agreement among participants', AI "
            "92%, Human 42%. (1) NOT BERTSCORE and not a literal reproduction: Mator "
            "describe 'stance-aware sentence similarity' without specifying the method, "
            "so this is the closest reasonable operationalisation of their construct. "
            "(2) SIMILARITY IS NOT AGREEMENT - none of this distinguishes sharing a "
            "stance from discussing the same topic; that is what the WITHHELD "
            "interpretive agreement/disagreement metrics and the gold standard resolve. "
            "(3) WHY STRICT IS PRIMARY: the pre-existing bridged computation pairs turns "
            "that are consecutive among participants only, so it also pairs turns "
            "separated by a moderator turn - about 1% of human pairs but about 40% of "
            "synthetic ones, because the synthetic moderator intervenes far more often. "
            "The two sides were therefore not the same measurement. Computing the strict "
            "variant SETTLES that concern rather than confirming it: strict R2 gives "
            "human 0.537 / enriched 0.870 / demographics-only 0.862 against bridged "
            "0.538 / 0.870 / 0.858, and strict R3 gives 0.429 / 0.558 / 0.532 against "
            "bridged 0.430 / 0.545 / 0.520. The universes differ sharply but the contrast "
            "does not, so the existing bridged figures can be cited without correction. "
            "Both are reported; exact bridge rates are in "
            "mator_agreement_strict_spec.json. (4) The R2/R3 contrast already established "
            "that roughly two thirds of the published gap is turn length rather than "
            "consensus, and the strict variant reproduces that too (+0.33 at R2 falling "
            "to +0.13 at R3)."
        ),
    },
    {
        "metric_id": "mator_conversational_distribution",
        "tier": "exploratory",
        "category": "exploratory",
        "evidence_class": EVIDENCE_CLASS,
        "namespace": NAMESPACE,
        "unit_of_analysis": "focus group",
        "definition": (
            "Word share of the moderator and of each individual participant, in Mator's "
            "row format. REUSED, NOT RECOMPUTED: reshaped from the existing "
            "moderator_word_share metric and the participant_word_counts vector already "
            "retained in results/structural_distributions_long.csv."
        ),
        "numerator": "words spoken by the moderator, and by each participant",
        "denominator": "all words in the window",
        "aggregation": "per run -> per FG x condition",
        "notes_and_caveats": (
            f"Mator-comparable proxy. {_MATOR_CITE}: 'Conversational distribution', AI "
            "'M 18%, 3 participants 24-29% each', Human 'M 32%, 3 participants 18-26% "
            "each'. Presentation layer only over AUTOMATIC_VALIDATED inputs; it adds no "
            "new counting and does not supersede moderator_word_share or "
            "moderator_turn_share. Inherits their caveat: the sub-entry Q1 boundary drops "
            "moderator words only. Rosters here are 3-5 participants, not Mator's fixed 3, "
            "so per-participant shares are not directly comparable to theirs."
        ),
    },
]


def parity_after_append(new_ids: set[str]) -> list[str]:
    """What `test_pipeline_produces_exactly_the_registry_automatic_metrics` would say.

    Simulated against the live consumer rather than against a copy of its rules,
    because a copy is exactly what drifts.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import aggregate_production_results as agg

    problems = []
    registry = set(agg.registry_automatic_metrics()) | new_ids
    accounted = agg.automatic_parity_produced() | set(agg.PRODUCED_ELSEWHERE)

    unaccounted = registry - accounted
    if unaccounted:
        problems.append(
            "these registry metrics would be neither produced here nor declared in "
            f"aggregate_production_results.PRODUCED_ELSEWHERE: {sorted(unaccounted)}")
    orphaned = accounted - registry
    if orphaned:
        problems.append(
            "the pipeline would claim metrics absent from the registry: "
            f"{sorted(orphaned)}")
    both = agg.automatic_parity_produced() & set(agg.PRODUCED_ELSEWHERE)
    if both:
        problems.append(f"declared both produced-here and produced-elsewhere: {sorted(both)}")
    for p in agg.external_producer_problems():
        problems.append(f"external producer claim unmet: {p}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="actually modify the registry")
    args = ap.parse_args()

    raw_bytes = _REGISTRY.read_bytes()
    raw = raw_bytes.decode("utf-8")
    reader = csv.DictReader(io.StringIO(raw, newline=""))
    fields = list(reader.fieldnames or [])
    existing = list(reader)

    # The registry is CRLF on disk. Writing it back with the csv module's default
    # "\r\n", or with "\n", must not be guessed: detect the terminator actually in
    # use, then prove on the RAW BYTES that re-serialising the existing rows
    # reproduces the current file exactly. Comparing newline-normalised TEXT, as an
    # earlier version of this guard did, would have passed while silently rewriting
    # all 46 frozen rows from CRLF to LF.
    terminator = "\r\n" if raw_bytes.count(b"\r\n") else "\n"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator=terminator)
    w.writeheader()
    w.writerows(existing)
    if buf.getvalue().encode("utf-8") != raw_bytes:
        raise SystemExit(
            "refusing to write: re-serialising the existing registry does not reproduce "
            f"it byte for byte (detected terminator {terminator!r}; does it carry a BOM, "
            f"or embedded newlines inside a quoted field?), so appending would silently "
            f"reformat {len(existing)} frozen rows")

    have = {r["metric_id"] for r in existing}
    to_add = [r for r in NEW_ROWS if r["metric_id"] not in have]

    for r in NEW_ROWS:
        missing = set(fields) - set(r)
        extra = set(r) - set(fields)
        if missing or extra:
            raise SystemExit(f"{r['metric_id']}: schema mismatch "
                             f"(missing {sorted(missing)}, extra {sorted(extra)})")

    if not to_add:
        print(f"already registered: {sorted(r['metric_id'] for r in NEW_ROWS)}")
        problems = parity_after_append(set())
        print("parity check: " + ("OK" if not problems else "FAILING"))
        for p in problems:
            print(f"  ! {p}")
        return

    print(f"registry has {len(existing)} rows; adding {len(to_add)}:")
    for r in to_add:
        print(f"  + {r['metric_id']}  [{r['evidence_class']}, {r['namespace']}]")

    problems = parity_after_append({r["metric_id"] for r in NEW_ROWS})
    if problems:
        print("\nparity check after append: FAILING")
        for p in problems:
            print(f"  ! {p}")
        raise SystemExit(
            "refusing to write: appending these rows would break "
            "tests/test_aggregate_production_results.py. Declare them in "
            "aggregate_production_results.PRODUCED_ELSEWHERE (and make sure the "
            "artifacts exist) first.")
    print("parity check after append: OK")

    if not args.write:
        print("\ndry run — re-run with --write to modify metric_registry.csv")
        return

    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=fields, lineterminator=terminator)
    w.writeheader()
    w.writerows(existing + to_add)
    new_bytes = out.getvalue().encode("utf-8")
    if not new_bytes.startswith(raw_bytes):
        raise SystemExit("refusing to write: the new file is not the old file plus "
                         "appended rows")
    _REGISTRY.write_bytes(new_bytes)
    print(f"\nwrote {_REGISTRY} ({len(existing) + len(to_add)} rows, "
          f"terminator {terminator!r}, {len(new_bytes) - len(raw_bytes)} bytes appended)")


if __name__ == "__main__":
    main()
