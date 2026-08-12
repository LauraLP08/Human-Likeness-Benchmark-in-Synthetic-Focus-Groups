"""
Cluster alignment and prompt-purity gate for the inductive accumulation design.

Offline; no API call. These are the mechanisms the design depends on, written now so
they can be tested before anything is executed.

WHY ALIGNMENT IS NOT ID EQUALITY
--------------------------------
If a taxonomy is built three times independently, `cluster_3` in one run and `cluster_3`
in another are unrelated labels. Comparing assignments by cluster id would then measure
nothing. Two mechanisms are provided:

  * `assignment_stability` — the RECOMMENDED path. One taxonomy is built in a canonical
    order; later passes REASSIGN the same raw themes against that fixed taxonomy, so ids
    are shared by construction and stability is a direct comparison.

  * `coassignment_alignment` — the fallback if independent taxonomies are ever built
    anyway. It compares two partitions through their co-assignment structure (do these
    two raw themes land together?), which is label-invariant, and reports the greedy
    one-to-one mapping plus the pairs the two partitions disagree about.
"""
from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CODEBOOK = _ROOT / "analysis/production_evaluation/gold_standard_sealed/codebook_reference.csv"

SAME_CLUSTER = "SAME_CLUSTER"
NEW_CLUSTER = "NEW_CLUSTER"
UNCERTAIN = "UNCERTAIN"
VERDICTS = (SAME_CLUSTER, NEW_CLUSTER, UNCERTAIN)


# --------------------------------------------------------------- ordering
def canonical_order(raw_themes):
    """
    Deterministic presentation order, independent of extraction sequence.

    Sorting by a content hash rather than by document, condition or extraction order
    means the taxonomy-construction pass cannot be influenced by corpus ordering — the
    synthetic themes do not arrive in a block after the human ones.
    """
    def key(t):
        blob = f"{t.get('label','')}|{t.get('definition','')}"
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return sorted(raw_themes, key=key)


# ------------------------------------------------------------- stability
def assignment_stability(passes: dict[str, dict[str, str]]):
    """
    passes: pass_name -> {raw_theme_id: cluster_id_or_verdict}

    All passes must assign against the SAME canonical taxonomy, so cluster ids are
    directly comparable. Returns per-theme stability and the unstable set.
    """
    names = sorted(passes)
    if len(names) < 2:
        raise ValueError("stability needs at least two passes")
    ids = set()
    for p in passes.values():
        ids |= set(p)
    out = {}
    for tid in sorted(ids):
        vals = [passes[n].get(tid) for n in names]
        present = [v for v in vals if v is not None]
        stable = (len(set(present)) == 1 and len(present) == len(names)
                  and present[0] != UNCERTAIN)
        out[tid] = {
            "assignments": {n: passes[n].get(tid) for n in names},
            "stable": stable,
            "any_uncertain": UNCERTAIN in present,
            "any_missing": len(present) != len(names),
            "distinct_values": sorted(set(present)),
        }
    unstable = sorted(t for t, v in out.items() if not v["stable"])
    return {"n_themes": len(out), "n_passes": len(names),
            "n_stable": len(out) - len(unstable),
            "n_unstable": len(unstable),
            "stability_rate": round((len(out) - len(unstable)) / len(out), 4) if out else None,
            "unstable_theme_ids": unstable, "per_theme": out}


# ------------------------------------------------------------- fallback
def _pairs(assign):
    """Set of raw-theme pairs that share a cluster."""
    by = defaultdict(list)
    for tid, cid in assign.items():
        by[cid].append(tid)
    out = set()
    for members in by.values():
        for a, b in combinations(sorted(members), 2):
            out.add((a, b))
    return out


def coassignment_alignment(a: dict[str, str], b: dict[str, str]):
    """
    Compare two INDEPENDENT partitions of the same raw themes without using cluster ids
    as if they were shared. Label-invariant by construction.
    """
    shared = sorted(set(a) & set(b))
    if not shared:
        raise ValueError("no shared raw themes to align")
    a = {k: a[k] for k in shared}
    b = {k: b[k] for k in shared}
    pa, pb = _pairs(a), _pairs(b)
    inter = pa & pb
    union = pa | pb

    matrix = defaultdict(lambda: defaultdict(int))
    for tid in shared:
        matrix[a[tid]][b[tid]] += 1
    # greedy one-to-one mapping on the co-assignment matrix
    cand = sorted(((n, ca, cb) for ca, row in matrix.items() for cb, n in row.items()),
                  key=lambda x: (-x[0], str(x[1]), str(x[2])))
    used_a, used_b, mapping = set(), set(), {}
    for n, ca, cb in cand:
        if ca in used_a or cb in used_b:
            continue
        mapping[ca] = {"maps_to": cb, "n_shared_themes": n}
        used_a.add(ca)
        used_b.add(cb)
    return {
        "n_shared_themes": len(shared),
        "n_clusters_a": len({*a.values()}), "n_clusters_b": len({*b.values()}),
        "pair_jaccard": round(len(inter) / len(union), 4) if union else 1.0,
        "n_pairs_together_in_both": len(inter),
        "n_pairs_only_in_a": len(pa - pb),
        "n_pairs_only_in_b": len(pb - pa),
        "greedy_one_to_one": mapping,
        "unmapped_clusters_a": sorted({*a.values()} - used_a),
        "unmapped_clusters_b": sorted({*b.values()} - used_b),
        "disagreeing_pairs": sorted(pa ^ pb),
        "note": ("alignment is by co-assignment structure, never by cluster_id equality; "
                 "ids from independently built taxonomies carry no shared meaning"),
    }


# ---------------------------------------------------------- prompt purity
def codebook_terms():
    """Structural identifiers and verbatim strings from the deductive codebook."""
    ids, labels, themes, descriptions = [], [], [], []
    with _CODEBOOK.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ids.append(r["subtheme_id"].strip())
            labels.append(r["subtheme_label"].strip())
            themes.append(r["theme"].strip())
            descriptions.append(r["description"].strip())
    return {"subtheme_ids": ids, "subtheme_labels": sorted(set(labels)),
            "themes": sorted(set(themes)), "descriptions": descriptions,
            "filenames": ["CodeBook_Macho Meals.xlsx", "codebook_reference.csv"]}


def codebook_leak_problems(scaffold: str, transcript: str = ""):
    """
    Assert the deductive codebook is absent from a prompt.

    SPLIT CHECK, deliberately. The scaffolding is text we author and is checked against
    every codebook string. The transcript segment is participant speech and is checked
    only for STRUCTURAL identifiers. The codebook's descriptions contain ordinary words
    — 'natural', 'animal', 'normal' — that participants use legitimately, and redacting
    them would corrupt the data being coded. A false positive of exactly this kind was
    caught earlier in this project on the word 'macho'.
    """
    t = codebook_terms()
    bad = []
    low = scaffold.lower()
    for i in t["subtheme_ids"]:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(i)}(?![A-Za-z0-9])", scaffold):
            bad.append(f"codebook subtheme_id in scaffold: {i!r}")
    for s in t["subtheme_labels"] + t["themes"]:
        if s and s.lower() in low:
            bad.append(f"codebook label/theme in scaffold: {s!r}")
    for s in t["descriptions"]:
        if s and len(s) > 20 and s.lower() in low:
            bad.append(f"codebook description in scaffold: {s[:40]!r}")
    for s in t["filenames"]:
        if s.lower() in low:
            bad.append(f"codebook filename in scaffold: {s!r}")
    for word in ("codebook", "code book", "deductive code", "subtheme id"):
        if word in low:
            bad.append(f"codebook reference in scaffold: {word!r}")
    # transcript: structural identifiers only
    for i in t["subtheme_ids"]:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(i)}(?![A-Za-z0-9])", transcript):
            bad.append(f"codebook subtheme_id inside the transcript segment: {i!r}")
    return sorted(set(bad))


# ---------------------------------------------------- balanced subsample (E1)
def balanced_subsample(raw_themes, per_condition=None):
    """
    Select the balanced subsample that Stage E1 is allowed to see.

    All human raw themes for the question, plus an equal number drawn deterministically
    (canonical content-hash order) from each synthetic condition. Deterministic: no RNG,
    reproducible from the raw themes alone.
    """
    by = defaultdict(list)
    for t in raw_themes:
        by[t["condition"]].append(t)
    human = canonical_order(by.get("human", []))
    n = per_condition if per_condition is not None else len(human)
    out = list(human[:n]) if per_condition is not None else list(human)
    for cond in sorted(k for k in by if k != "human"):
        out.extend(canonical_order(by[cond])[:n])
    return canonical_order(out)


def e1_prompt_problems(prompt_text: str, subsample, all_raw_themes):
    """
    Assert Stage E1 sees ONLY the balanced subsample.

    A theme outside the subsample appearing in the E1 prompt would mean the balanced
    taxonomy was in fact induced from the dominant pool, which is exactly what the
    sensitivity analysis exists to test against.
    """
    inside = {t["raw_theme_id"] for t in subsample}
    bad = []
    for t in all_raw_themes:
        if t["raw_theme_id"] in inside:
            continue
        if t["raw_theme_id"] in prompt_text:
            bad.append(f"out-of-subsample raw_theme_id in E1 prompt: {t['raw_theme_id']}")
        lab = (t.get("label") or "").strip()
        if lab and len(lab) > 8 and lab in prompt_text:
            bad.append(f"out-of-subsample label in E1 prompt: {lab!r}")
    return sorted(set(bad))


def frozen_taxonomy_key(taxonomy) -> str:
    """Hash of a taxonomy, so a later stage can prove it used the frozen version."""
    blob = "\n".join(
        f"{c['cluster_id']}|{c.get('label','')}|{c.get('definition','')}"
        for c in sorted(taxonomy, key=lambda c: str(c["cluster_id"])))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def e2_problems(e1_taxonomy, e1_frozen_key, assignments):
    """
    Stage E2 must assign against the FROZEN E1 taxonomy and must not revise it.

    Every assignment must name an E1 cluster, or NEW_CLUSTER, or UNCERTAIN. A cluster id
    that is not in E1 and is not one of those verdicts means E1 was silently extended.
    """
    bad = []
    if frozen_taxonomy_key(e1_taxonomy) != e1_frozen_key:
        bad.append("E1 taxonomy hash does not match the frozen key — E1 was revised")
    known = {str(c["cluster_id"]) for c in e1_taxonomy}
    for tid, verdict in assignments.items():
        v = str(verdict)
        if v in (NEW_CLUSTER, UNCERTAIN):
            continue
        if v not in known:
            bad.append(f"{tid} assigned to {v!r}, which is not in the frozen E1 taxonomy")
    return sorted(set(bad))


# ------------------------------------------- Stage F pass-2 assignment
def stage_f_assignment_problems(records):
    """
    Stage F must assign pass-2 themes DIRECTLY against the canonical taxonomy.

    An earlier draft measured stability by matching each pass-2 theme to its "nearest
    pass-1 counterpart". That lets a similarity score decide a correspondence, which
    contradicts the rule that similarity may propose but never decide. Each record must
    therefore carry an adjudicated verdict, and must not carry a nearest-neighbour
    decision field.
    """
    bad = []
    banned = ("nearest_pass1_theme", "nearest_neighbour", "nearest_neighbor",
              "matched_by_similarity", "similarity_decided", "nearest_match")
    for r in records:
        rid = r.get("pass2_theme_id", "?")
        v = r.get("verdict")
        if v not in VERDICTS:
            bad.append(f"{rid}: verdict {v!r} is not one of {VERDICTS}")
        if v == SAME_CLUSTER and not r.get("canonical_cluster_id"):
            bad.append(f"{rid}: SAME_CLUSTER without a canonical_cluster_id")
        if v in (NEW_CLUSTER, UNCERTAIN) and r.get("canonical_cluster_id"):
            bad.append(f"{rid}: {v} must not name a canonical cluster")
        for k in banned:
            if k in r:
                bad.append(f"{rid}: forbidden nearest-neighbour field {k!r}")
        order = r.get("similarity_ordered_candidates")
        if order is not None and not isinstance(order, list):
            bad.append(f"{rid}: similarity_ordered_candidates must be a list")
        if r.get("decided_by") not in (None, "adjudicator"):
            bad.append(f"{rid}: decided_by {r.get('decided_by')!r} is not the adjudicator")
    return sorted(set(bad))


# ------------------------------------------- E3: NEW_CLUSTER consolidation
EXTENDED_VERSION = "BALANCED_TAXONOMY_EXTENDED_V1"


def consolidate_new_clusters(e1_taxonomy, e1_frozen_key, e2_assignments,
                             new_cluster_groups):
    """
    E3 — turn E2's NEW_CLUSTER themes into a versioned EXTENDED taxonomy.

    Three rules this enforces, each of which would otherwise silently corrupt a curve:

      * **E1 is never overwritten.** The extended taxonomy is a new, versioned object
        that carries E1's clusters unchanged plus the consolidated new ones, and records
        E1's hash as its parent.
      * **A NEW_CLUSTER is not automatically a distinct theme.** Several raw themes may
        be the same idea the E1 subsample happened not to contain. `new_cluster_groups`
        is the adjudicated grouping; two equivalent NEW_CLUSTERs collapse into one
        extended cluster.
      * **UNCERTAIN is not silently dropped.** It is counted and reported, and never
        folded into either taxonomy.

    `new_cluster_groups`: list of lists of raw_theme_ids, the adjudicated grouping.
    """
    if frozen_taxonomy_key(e1_taxonomy) != e1_frozen_key:
        raise ValueError("E1 taxonomy hash does not match its frozen key")

    new_ids = sorted(t for t, v in e2_assignments.items() if v == NEW_CLUSTER)
    unc_ids = sorted(t for t, v in e2_assignments.items() if v == UNCERTAIN)
    grouped = [tid for g in new_cluster_groups for tid in g]

    problems = []
    if sorted(grouped) != new_ids:
        missing = sorted(set(new_ids) - set(grouped))
        extra = sorted(set(grouped) - set(new_ids))
        if missing:
            problems.append(f"NEW_CLUSTER themes not grouped by E3: {missing}")
        if extra:
            problems.append(f"E3 grouped themes that were not NEW_CLUSTER: {extra}")
    if len(grouped) != len(set(grouped)):
        problems.append("a raw theme appears in more than one E3 group")
    for tid in unc_ids:
        if tid in grouped:
            problems.append(f"UNCERTAIN theme {tid} was folded into an E3 group")

    extended = [dict(c) for c in e1_taxonomy]
    for i, group in enumerate(new_cluster_groups, start=1):
        extended.append({"cluster_id": f"EXT{i:03d}", "origin": "E3",
                         "from_raw_theme_ids": sorted(group),
                         "n_raw_themes": len(group)})

    return {
        "version": EXTENDED_VERSION,
        "parent_taxonomy_sha256": e1_frozen_key,
        "e1_cluster_ids": sorted(str(c["cluster_id"]) for c in e1_taxonomy),
        "e1_unchanged": [str(c["cluster_id"]) for c in extended
                         if c.get("origin") != "E3"] ==
                        [str(c["cluster_id"]) for c in e1_taxonomy],
        "extended_taxonomy": extended,
        "extended_taxonomy_sha256": frozen_taxonomy_key(extended),
        "counts": {
            "n_new_cluster_raw_themes": len(new_ids),
            "n_consolidated_extended_clusters": len(new_cluster_groups),
            "n_uncertain_raw_themes": len(unc_ids),
            "uncertain_raw_theme_ids": unc_ids,
            "collapsed": len(new_ids) - len(new_cluster_groups)},
        "never_auto_one_cluster_per_new": True,
        "curves_reported_separately": ["strict_vs_E1", "extended_vs_" + EXTENDED_VERSION],
        "problems": problems,
        "pass": not problems,
    }


def curve_denominators(e2_assignments, e3):
    """
    Denominators for the two curve families, with UNCERTAIN shown rather than dropped.

    STRICT counts only E1 clusters. EXTENDED adds the consolidated E3 clusters.
    UNCERTAIN is in neither numerator and is reported in both.
    """
    e1_ids = set(e3["e1_cluster_ids"])
    strict = {t: v for t, v in e2_assignments.items() if str(v) in e1_ids}
    n_new = e3["counts"]["n_new_cluster_raw_themes"]
    n_unc = e3["counts"]["n_uncertain_raw_themes"]
    return {
        "strict_vs_E1": {
            "n_raw_themes_counted": len(strict),
            "n_clusters_available": len(e1_ids),
            "excluded_new_cluster": n_new,
            "excluded_uncertain": n_unc,
            "excluded_shown_not_dropped": True},
        "extended": {
            "n_raw_themes_counted": len(strict) + n_new,
            "n_clusters_available": len(e1_ids)
            + e3["counts"]["n_consolidated_extended_clusters"],
            "excluded_uncertain": n_unc,
            "excluded_shown_not_dropped": True},
        "uncertain_never_silently_dropped": True,
    }
