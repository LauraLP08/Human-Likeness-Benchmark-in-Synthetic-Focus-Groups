"""
Lexical diagnostics requiring no human coding and no model call.

STATUS: EXPLORATORY. The general indicators appear in the original methodology, but
these operationalisations were finalised after the main results were known.

THE CONFOUND THIS MODULE EXISTS TO ADDRESS
------------------------------------------
An unadjusted vocabulary-overlap comparison is confounded by how much each speaker
said. Jaccard overlap between two vocabularies depends on their sizes, and vocabulary
size grows with output; synthetic participants speak far more than human ones. A raw
comparison therefore partly measures speaker output rather than distinctiveness of
voice.

The correction is a token-budget sensitivity analysis: every compared participant
contributes the SAME number of tokens, drawn deterministically at several offsets, at
several budgets, under several tokenisation rules. If the unadjusted direction survives
budget equalisation it is worth something; if it does not, the unadjusted figure was
measuring output.

Three overlap measures are computed on the identical budgeted samples:

  * mean pairwise JACCARD on vocabulary sets — higher = MORE overlap = LESS distinct
  * mean pairwise JENSEN-SHANNON distance on token-frequency distributions —
    higher = MORE different = MORE distinct
  * mean pairwise COSINE similarity on term-frequency vectors —
    higher = MORE similar = LESS distinct

Jaccard ignores how often a word is used; the two frequency-based measures do not, so
agreement between them is informative and disagreement is a warning. No embeddings are
used: an embedding distance is not a measure of "voice" and would substitute an
unvalidated instrument for a transparent one.

MATTR is reported separately as a LESS LENGTH-SENSITIVE diversity diagnostic at three
window sizes. It is not evidence about voice distinctiveness.

The numeral count is a descriptive PROXY only. It is reported under its own name and
never under the registry's hyper-exactness indicator, which is
NOT_IN_REPORTED_INSTRUMENT.

    py scripts/lexical_analysis.py
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, UTC
from itertools import combinations
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RES = _ROOT / "analysis/production_evaluation/results"
_SYN = _ROOT / "analysis/production_evaluation/comparable_transcripts"
_HUM = _ROOT / "data/datasets_transcripts/standardized/macho_meals"
_OUT = _ROOT / "analysis/production_evaluation/final/lexical_analysis.json"

FGS = ["fg1", "fg2", "fg3", "fg4", "fg5"]
BUDGETS = [100, 200, 400]        # tokens per participant; only feasible ones are used
N_SUBSAMPLES = 10                # deterministic offsets, no randomness
MATTR_WINDOWS = [50, 100, 200]

STOP = set("""a an the and or but if then than that this these those of in on at to for
with without from by as is are was were be been being am it its it's they them their
there here what which who whom how why when we you i he she his her our your my me not
no yes do does did done have has had can could would should will just about into over
under more most less least very really quite so such own same other another each any
all some one two three thing things people person like get got make made go going went
say said know think really actually maybe probably yeah okay right well um uh oh
""".split())

_WORD = re.compile(r"[a-z']+")
_NUM = re.compile(r"""(?:\d+(?:[.,]\d+)?\s*%|\b\d+(?:[.,]\d+)?\b
                       |\b\d+(?:st|nd|rd|th)\b|\bper\s?cent\b|\bpercent(?:age)?\b)""",
                  re.X | re.I)

# Tokenisation arms for the sensitivity analysis.
TOKENISERS = {
    "content_min3_nostop": dict(min_len=3, drop_stopwords=True),
    "content_min1_nostop": dict(min_len=1, drop_stopwords=True),
    "all_min3_withstop": dict(min_len=3, drop_stopwords=False),
}


def _tok(text, min_len, drop_stopwords):
    out = [w for w in _WORD.findall(text.lower()) if len(w) >= min_len]
    return [w for w in out if w not in STOP] if drop_stopwords else out


# ------------------------------------------------------------------ loading
def _human_session(fg):
    t = json.loads((_HUM / fg / "transcript.json").read_text(encoding="utf-8"))
    return [{"speaker": e["canonical_speaker_id"],
             "role": e.get("speaker_role", ""), "text": e["content"]} for e in t]


def _synth_session(run):
    j = json.loads((_SYN / run / "comparable_transcript.json").read_text(
        encoding="utf-8"))
    return [{"speaker": e["speaker_id"],
             "role": "moderator" if e["speaker_id"] == "MODERATOR" else "participant",
             "text": e["content"]} for e in j["transcript"]]


def _sessions():
    """(condition, fg, replicate) -> turn list. Humans have replicate None."""
    out = {}
    for fg in FGS:
        out[("human", fg, None)] = _human_session(fg)
    for d in sorted(os.listdir(_SYN)):
        m = re.match(r"macho_meals_(fg\d)(_demoonly)?_run0(\d)$", d)
        if m:
            cond = "demographics-only" if m.group(2) else "enriched"
            out[(cond, m.group(1), m.group(3))] = _synth_session(d)
    return out


# ------------------------------------------------- budget-equalised overlap
def _speaker_tokens(turns, tk):
    by = defaultdict(list)
    for t in turns:
        if t["role"] == "participant":
            by[t["speaker"]].extend(_tok(t["text"], **tk))
    return {s: v for s, v in by.items() if v}


def _offsets(n_tokens, budget, n_sub):
    """
    Deterministic, evenly spread window starts. No RNG anywhere.

    Returns AT MOST n_sub offsets and never a duplicate: a speaker with only `span + 1`
    distinct start positions cannot supply more than that many distinct windows, and
    padding the list by cycling would resample the same text while inflating the
    apparent number of observations.
    """
    span = n_tokens - budget
    if span <= 0:
        return [0]
    if n_sub == 1:
        return [span // 2]
    k = min(n_sub, span + 1)
    return sorted({round(i * span / (k - 1)) for i in range(k)}) if k > 1 else [0]


def _max_unique_offsets(n_tokens, budget, n_sub):
    return len(_offsets(n_tokens, budget, n_sub))


def _js(a: Counter, b: Counter) -> float:
    """Jensen-Shannon DISTANCE (sqrt of divergence), base 2. Higher = more different."""
    vocab = set(a) | set(b)
    na, nb = sum(a.values()), sum(b.values())
    p = [a[w] / na for w in vocab]
    q = [b[w] / nb for w in vocab]
    m = [(x + y) / 2 for x, y in zip(p, q)]

    def _kl(u, v):
        return sum(x * math.log2(x / y) for x, y in zip(u, v) if x > 0)
    div = 0.5 * _kl(p, m) + 0.5 * _kl(q, m)
    return math.sqrt(max(div, 0.0))


def _cosine(a: Counter, b: Counter) -> float:
    vocab = set(a) | set(b)
    dot = sum(a[w] * b[w] for w in vocab)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _budgeted_overlap(turns, tk, budget, n_sub=N_SUBSAMPLES):
    """All three pairwise measures at a fixed per-participant token budget."""
    toks = _speaker_tokens(turns, tk)
    if len(toks) < 2:
        return None
    if min(len(v) for v in toks.values()) < budget:
        return None                       # budget not feasible for every participant
    speakers = sorted(toks)
    # A subsample pairs one window per speaker, so the number of DISTINCT subsamples is
    # capped by the least well-supplied speaker. Cycling a short speaker's offsets to
    # reach a fixed count resamples identical text while reporting it as new evidence,
    # which shrinks the spread and overstates how much was observed.
    n_unique = min(_max_unique_offsets(len(toks[sp]), budget, n_sub) for sp in speakers)
    offsets_used = {sp: _offsets(len(toks[sp]), budget, n_unique) for sp in speakers}
    for sp, o in offsets_used.items():
        assert len(o) == len(set(o)) == n_unique, (sp, o)

    per_sub = {"jaccard": [], "js": [], "cosine": []}
    pair_means = defaultdict(list)
    n_used = None
    for s in range(n_unique):
        sample = {}
        for sp in speakers:
            o = offsets_used[sp][s]
            sample[sp] = toks[sp][o:o + budget]
        j, d, c = [], [], []
        for a, b in combinations(speakers, 2):
            sa, sb = set(sample[a]), set(sample[b])
            ca, cb = Counter(sample[a]), Counter(sample[b])
            jv = len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0
            j.append(jv)
            d.append(_js(ca, cb))
            c.append(_cosine(ca, cb))
            pair_means[f"{a}|{b}"].append(jv)
        per_sub["jaccard"].append(statistics.mean(j))
        per_sub["js"].append(statistics.mean(d))
        per_sub["cosine"].append(statistics.mean(c))
        n_used = len(j)

    def _stats(v):
        # Computed over UNIQUE windows only. These windows are overlapping slices of the
        # same speaker's stream, so they are not independent observations: the spread
        # describes sampling position within a transcript, and no confidence interval or
        # p-value is derived from it anywhere.
        return {"mean": round(statistics.mean(v), 4),
                "sd_across_unique_windows": (round(statistics.stdev(v), 4)
                                             if len(v) > 1 else None),
                "min": round(min(v), 4), "max": round(max(v), 4),
                "n_values": len(v)}
    pm = {k: round(statistics.mean(v), 4) for k, v in pair_means.items()}
    step = {sp: (o[1] - o[0] if len(o) > 1 else None)
            for sp, o in offsets_used.items()}
    overlapping = {sp: (None if s is None else s < budget) for sp, s in step.items()}
    return {
        "budget": budget, "n_speakers": len(speakers), "n_pairs": n_used,
        "n_requested_subsamples": n_sub,
        "n_unique_subsamples": n_unique,
        "subsamples_were_padded_by_repetition": False,
        "offsets_used": offsets_used,
        "offsets_provenance": (
            "evenly spread deterministic start positions, recomputed for each speaker at "
            "exactly n_unique_subsamples; every offset is used once and none repeats"),
        "offset_step_per_speaker": step,
        "windows_overlap_per_speaker": overlapping,
        "any_windows_overlap": any(v for v in overlapping.values() if v is not None),
        "limiting_speaker": min(speakers,
                                key=lambda sp: _max_unique_offsets(len(toks[sp]),
                                                                   budget, n_sub)),
        "tokens_available_per_speaker": {s: len(toks[s]) for s in speakers},
        "independence_note": (
            "unique windows are overlapping slices of one stream and are NOT independent "
            "observations; no CI and no p-value is computed from their spread"),
        "jaccard": _stats(per_sub["jaccard"]),
        "jensen_shannon_distance": _stats(per_sub["js"]),
        "cosine_similarity": _stats(per_sub["cosine"]),
        "pairwise_jaccard_means": pm,
        "pairwise_spread": {"min": min(pm.values()), "max": max(pm.values()),
                            "range": round(max(pm.values()) - min(pm.values()), 4)},
    }


def _unadjusted_jaccard(turns, tk):
    toks = _speaker_tokens(turns, tk)
    if len(toks) < 2:
        return None
    v = {s: set(t) for s, t in toks.items()}
    sp = sorted(v)
    pairs = [len(v[a] & v[b]) / len(v[a] | v[b]) if (v[a] | v[b]) else 0.0
             for a, b in combinations(sp, 2)]
    return {"mean_pairwise_overlap": round(statistics.mean(pairs), 4),
            "mean_vocab_size": round(statistics.mean(len(x) for x in v.values()), 1),
            "min_tokens_per_speaker": min(len(t) for t in toks.values()),
            "max_tokens_per_speaker": max(len(t) for t in toks.values()),
            "token_imbalance_ratio": round(
                max(len(t) for t in toks.values())
                / min(len(t) for t in toks.values()), 3)}


# ------------------------------------------------------------- diversity
def _mattr(toks, w):
    if len(toks) < w:
        return None
    return statistics.mean(len(set(toks[i:i + w])) / w
                           for i in range(len(toks) - w + 1))


def _diversity(turns):
    toks = _tok(" ".join(t["text"] for t in turns if t["role"] == "participant"),
                min_len=1, drop_stopwords=False)
    if not toks:
        return None
    out = {"n_tokens": len(toks), "n_types": len(set(toks)),
           "ttr": round(len(set(toks)) / len(toks), 4)}
    for w in MATTR_WINDOWS:
        v = _mattr(toks, w)
        out[f"mattr_w{w}"] = round(v, 4) if v is not None else None
    return out


def _numerals(turns):
    text = " ".join(t["text"] for t in turns if t["role"] == "participant")
    n = len(text.split())
    return {"participant_words": n, "n_matches": len(_NUM.findall(text)),
            "per_1000_words": round(len(_NUM.findall(text)) / n * 1000, 4) if n else None}


# ------------------------------------------------------------------ build
def build() -> dict:
    sessions = _sessions()
    per_session = []
    for (cond, fg, rep), turns in sorted(sessions.items(),
                                         key=lambda kv: (kv[0][0], kv[0][1],
                                                         kv[0][2] or "")):
        rec = {"condition": cond, "fg": fg, "replicate": rep,
               "total_words": sum(len(t["text"].split()) for t in turns),
               "unadjusted": {name: _unadjusted_jaccard(turns, tk)
                              for name, tk in TOKENISERS.items()},
               "budgeted": {name: {str(b): _budgeted_overlap(turns, tk, b)
                                   for b in BUDGETS}
                            for name, tk in TOKENISERS.items()},
               "diversity": _diversity(turns),
               "numeral_proxy": _numerals(turns)}
        per_session.append(rec)

    def _fg_then_condition(getter):
        """FG-level mean first (replicates collapse), then across the five FGs."""
        out = {}
        for cond in ("human", "enriched", "demographics-only"):
            fg_means = []
            for fg in FGS:
                vals = [getter(r) for r in per_session
                        if r["condition"] == cond and r["fg"] == fg]
                vals = [v for v in vals if v is not None]
                if vals:
                    fg_means.append(statistics.mean(vals))
            out[cond] = ({"fg_means": [round(v, 4) for v in fg_means],
                          "mean_over_fgs": round(statistics.mean(fg_means), 4),
                          "n_fg": len(fg_means)} if fg_means else None)
        h, e, d = out["human"], out["enriched"], out["demographics-only"]
        if h and e and d:
            out["enriched_minus_human"] = round(e["mean_over_fgs"]
                                                - h["mean_over_fgs"], 4)
            out["demo_minus_human"] = round(d["mean_over_fgs"]
                                            - h["mean_over_fgs"], 4)
            out["enriched_minus_demo"] = round(e["mean_over_fgs"]
                                               - d["mean_over_fgs"], 4)
            out["n_fg_synthetic_above_human"] = sum(
                1 for i in range(len(h["fg_means"]))
                if e["fg_means"][i] > h["fg_means"][i]
                and d["fg_means"][i] > h["fg_means"][i])
        return out

    # ---- feasibility of each budget -------------------------------------
    feas = {}
    for name in TOKENISERS:
        for b in BUDGETS:
            ok = [r for r in per_session if r["budgeted"][name][str(b)] is not None]
            feas[f"{name}@{b}"] = {
                "n_sessions_feasible": len(ok), "n_sessions_total": len(per_session),
                "all_conditions_present": len({r["condition"] for r in ok}) == 3,
                "by_condition": {c: sum(1 for r in ok if r["condition"] == c)
                                 for c in ("human", "enriched", "demographics-only")}}

    # ---- summaries -------------------------------------------------------
    summary = {"unadjusted_jaccard": {}, "budget_equalised": {}}
    for name in TOKENISERS:
        summary["unadjusted_jaccard"][name] = _fg_then_condition(
            lambda r, n=name: (r["unadjusted"][n] or {}).get("mean_pairwise_overlap"))
    for name in TOKENISERS:
        for b in BUDGETS:
            if not feas[f"{name}@{b}"]["all_conditions_present"]:
                continue
            for measure in ("jaccard", "jensen_shannon_distance", "cosine_similarity"):
                summary["budget_equalised"][f"{name}@{b}::{measure}"] = \
                    _fg_then_condition(
                        lambda r, n=name, bb=b, m=measure:
                        ((r["budgeted"][n][str(bb)] or {}).get(m) or {}).get("mean"))

    diversity = {f"mattr_w{w}": _fg_then_condition(
        lambda r, ww=w: r["diversity"][f"mattr_w{ww}"]) for w in MATTR_WINDOWS}
    diversity["ttr"] = _fg_then_condition(lambda r: r["diversity"]["ttr"])
    numerals = _fg_then_condition(lambda r: r["numeral_proxy"]["per_1000_words"])

    # ---- does budget equalisation preserve the unadjusted direction? -----
    # A higher budget is only feasible where every speaker can supply it, and human
    # participants speak far less. At budget 200 (content) and 400 (all-token) only ONE
    # human focus group qualifies, so those specifications compare 1 human FG against 5
    # synthetic FGs. They are computed and reported, but they cannot carry the verdict:
    # the comparison is FG-level and a one-group human side is not an FG-level side.
    verdict, thin = {}, {}
    for key, s in summary["budget_equalised"].items():
        if s.get("enriched_minus_human") is None:
            continue
        measure = key.split("::")[1]
        # direction meaning "synthetic vocabularies overlap MORE than human ones"
        more_overlap = ((s["enriched_minus_human"] < 0 and s["demo_minus_human"] < 0)
                        if measure == "jensen_shannon_distance"
                        else (s["enriched_minus_human"] > 0
                              and s["demo_minus_human"] > 0))
        n_fg = {c: s[c]["n_fg"] for c in ("human", "enriched", "demographics-only")}
        rec = {"synthetic_less_distinct_than_human": more_overlap,
               "enriched_minus_human": s["enriched_minus_human"],
               "demo_minus_human": s["demo_minus_human"],
               "n_fg": n_fg,
               "n_fg_both_synthetic_above_human": s.get("n_fg_synthetic_above_human")}
        (verdict if all(v == 5 for v in n_fg.values()) else thin)[key] = rec
    agree = sum(1 for v in verdict.values() if v["synthetic_less_distinct_than_human"])
    confirmed = bool(verdict) and agree == len(verdict)

    out = {
        "built_utc": datetime.now(UTC).isoformat(),
        "status": "EXPLORATORY",
        "temporal_transparency": (
            "The general indicators appear in the original methodology, but these "
            "operationalisations — token-budget equalisation, the subsample scheme, the "
            "frequency-based measures, the MATTR window set — were finalised AFTER the "
            "main results were known. Exploratory, not pre-registered in this form."),
        "source_synthetic": "analysis/production_evaluation/comparable_transcripts",
        "source_human": "data/datasets_transcripts/standardized/macho_meals",
        "window": ("same comparable window as the structural metrics; total word counts "
                   "reconcile exactly against "
                   "results/structural_interaction_metrics_long.csv"),
        "no_api_calls": True, "no_new_human_coding": True, "no_embeddings": True,
        "unit_of_analysis": "focus group (n=5); replicates collapse to their FG mean",
        "confound_addressed": (
            "vocabulary size grows with speaker output, and synthetic participants speak "
            "far more than human ones, so an unadjusted overlap comparison partly "
            "measures output rather than distinctiveness of voice"),
        "budget_design": {
            "budgets_tokens": BUDGETS,
            "n_subsamples": N_SUBSAMPLES,
            "subsample_scheme": ("evenly spread deterministic window offsets over each "
                                 "speaker's token stream; no RNG, fully reproducible"),
            "feasibility_rule": ("a budget is used for a session only if EVERY compared "
                                 "participant can supply that many tokens"),
            "tokenisation_arms": TOKENISERS,
            "measures": {
                "jaccard": "vocabulary set overlap; higher = MORE overlap = LESS distinct",
                "jensen_shannon_distance": ("frequency distributions; higher = MORE "
                                            "different = MORE distinct"),
                "cosine_similarity": ("term-frequency vectors; higher = MORE similar = "
                                      "LESS distinct")},
        },
        "budget_feasibility": feas,
        "summary": summary,
        "diversity": diversity,
        "diversity_note": ("MATTR is LESS length-sensitive than raw TTR, not "
                           "length-insensitive; it remains a diversity diagnostic and is "
                           "NOT evidence about voice distinctiveness"),
        "numeral_proxy": numerals,
        "numeral_proxy_note": ("descriptive PROXY only. It counts how many figures "
                               "appear, not how they are used, and does NOT discharge "
                               "the registry's hyper-exactness indicator, which is "
                               "NOT_IN_REPORTED_INSTRUMENT"),
        "sensitivity_verdict": {
            "decisive_specifications_require": "n_fg == 5 in every condition",
            "per_specification": verdict,
            "n_specifications": len(verdict),
            "n_agreeing_synthetic_less_distinct": agree,
            "unadjusted_direction_confirmed": confirmed,
            "excluded_thin_specifications": thin,
            "n_excluded_thin": len(thin),
            "why_excluded": (
                "higher budgets are feasible only where every speaker can supply them, "
                "and human participants speak far less; in these specifications only 1 "
                "of 5 human focus groups qualifies, so the human side is not an "
                "FG-level side and cannot carry an FG-level comparison"),
            "reporting_rule": (
                "if not confirmed across every specification, report only: 'the "
                "unadjusted vocabulary-overlap diagnostic was higher in synthetic "
                "sessions, but the comparison remains potentially confounded by unequal "
                "speaker output'"),
        },
        "per_session": per_session,
    }
    tmp = _OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _OUT)
    return out


def main() -> int:
    o = build()
    print(f"sessions: {len(o['per_session'])} (5 human + 30 synthetic)\n")
    print("=== budget feasibility (a budget is used only where EVERY speaker can supply it) ===")
    for k, v in o["budget_feasibility"].items():
        print(f"  {k:28s} {v['n_sessions_feasible']:>2d}/{v['n_sessions_total']} "
              f"sessions  by condition {v['by_condition']}  "
              f"usable={v['all_conditions_present']}")
    print("\n=== unadjusted Jaccard (CONFOUNDED by unequal output) ===")
    for name, s in o["summary"]["unadjusted_jaccard"].items():
        print(f"  {name:22s} human {s['human']['mean_over_fgs']:.4f}  "
              f"enriched {s['enriched']['mean_over_fgs']:.4f}  "
              f"demo {s['demographics-only']['mean_over_fgs']:.4f}")
    print("\n=== budget-equalised ===")
    for k, s in o["summary"]["budget_equalised"].items():
        print(f"  {k:44s} H {s['human']['mean_over_fgs']:>7.4f}  "
              f"E {s['enriched']['mean_over_fgs']:>7.4f}  "
              f"D {s['demographics-only']['mean_over_fgs']:>7.4f}")
    v = o["sensitivity_verdict"]
    print(f"\ndecisive specifications (n_fg == 5 in every condition): "
          f"{v['n_specifications']}  agreeing: "
          f"{v['n_agreeing_synthetic_less_distinct']}")
    print(f"excluded as thin (human side rests on 1 FG): {v['n_excluded_thin']} -> "
          f"{sorted({k.split('::')[0] for k in v['excluded_thin_specifications']})}")
    print("UNADJUSTED DIRECTION CONFIRMED:", v["unadjusted_direction_confirmed"])
    print("\n=== diversity (MATTR: less length-sensitive, NOT length-insensitive) ===")
    for k, s in o["diversity"].items():
        print(f"  {k:12s} human {s['human']['mean_over_fgs']:.4f}  "
              f"enriched {s['enriched']['mean_over_fgs']:.4f}  "
              f"demo {s['demographics-only']['mean_over_fgs']:.4f}")
    n = o["numeral_proxy"]
    print(f"\nnumeral proxy per 1000 words: human {n['human']['mean_over_fgs']:.4f}  "
          f"enriched {n['enriched']['mean_over_fgs']:.4f}  "
          f"demo {n['demographics-only']['mean_over_fgs']:.4f}  (PROXY ONLY)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
