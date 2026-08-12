"""
Shared presentation constants.

One place for the condition palette, the condition labels and the reader-facing names
of internal statuses. No chart, table or page defines a colour of its own: if
`enriched` were red in one figure and orange in another, the reader would have to
re-learn the legend on every screen.

The three colours are the ones the thesis figures use, so a screen and a printed
figure of the same quantity look like the same quantity.

This module holds NO logic. It is imported by the services (which put labels on their
own outputs) and by the interface. It reads nothing from disk.
"""
from __future__ import annotations

# --------------------------------------------------------------------- palette
HUMAN = "human"
ENRICHED = "enriched"
DEMOGRAPHICS_ONLY = "demographics-only"

CONDITION_ORDER = (HUMAN, ENRICHED, DEMOGRAPHICS_ONLY)

PALETTE = {
    HUMAN: "#1d4ed8",              # blue
    ENRICHED: "#dc2626",           # red
    DEMOGRAPHICS_ONLY: "#047857",  # green
}

CONDITION_LABELS = {
    HUMAN: "Human",
    ENRICHED: "Enriched",
    DEMOGRAPHICS_ONLY: "Demographics-only",
}

NEUTRAL = "#64748b"
UNDEFINED_DISPLAY = "Undefined"


def condition_label(condition: str | None) -> str:
    if condition is None:
        return UNDEFINED_DISPLAY
    return CONDITION_LABELS.get(condition, condition)


def condition_colour(condition: str | None) -> str:
    return PALETTE.get(condition or "", NEUTRAL)


def palette_for(conditions) -> list[str]:
    return [condition_colour(c) for c in conditions]


# ------------------------------------------------------------- status wording
CALCULATION_STATUS_LABELS = {
    "FROZEN_REPRODUCED": "Reproduced from frozen benchmark",
    "DERIVED_FROM_FROZEN": "Derived from frozen coded data",
    "EXPLORATORY": "Exploratory",
}

VERIFICATION_LABELS = {
    "RECOMPUTED_AND_MATCHED": "Recomputed and checked against the frozen table",
    "RECOMPUTED_NO_GOLDEN": "Recomputed; no frozen table to check against",
    "READ_FROM_FROZEN_ARTIFACT": "Read from the frozen artefact; not recomputed",
}

CODING_BASIS_LABELS = {
    "PRIMARY": "Primary coding",
    "SENSITIVITY": "Sensitivity re-coding",
    "BOTH": "Both, in separate columns",
}

COMPARABILITY_LABELS = {
    "DESCRIPTIVE_ONLY": "Descriptive only",
    "MATCHED_STRUCTURAL_COMPARISON": "Structural comparison (declared homologues)",
    "FROZEN_BENCHMARK_COMPATIBLE": "Frozen benchmark",
    "THEMATIC_COMPARISON_NOT_AVAILABLE": "Thematic comparison not available",
    "REQUIRES_REVIEW": "Requires review",
}

# The statistical name a reader should not have to know, and the name they see.
STATISTIC_LABELS = {
    "Kendall tau-b": "Agreement in thematic ordering",
}

METRIC_LABELS = {
    "total_words": "Total words",
    "participant_turns": "Participant turns",
    "words_per_turn_iqr": "Words per turn (IQR)",
    "short_turn_proportion_25w": "Short turns (<25 words)",
    "turn_balance_gini": "Turn balance (Gini)",
    "chain_depth": "Chain depth",
    "moderator_word_share": "Moderator word share",
    "words_per_turn_median": "Words per turn (median)",
    "short_turn_proportion_10w": "Short turns (<10 words)",
    "short_turn_proportion_50w": "Short turns (<50 words)",
    "word_balance_gini": "Word balance (Gini)",
    "moderator_turn_share": "Moderator turn share",
    "participant_participant_adjacency": "Participant-to-participant adjacency",
    "reference_density": "Reference density",
    "tier1_subtheme_recall": "Thematic recall",
    "tier1_matched_theme_precision": "Thematic precision",
    "tier1_f1_secondary": "Thematic F1 (secondary)",
    "tier1_participant_reach": "Participant reach",
    "tier1_participant_reach_shared_only": "Participant reach (shared subthemes)",
    "theme_recurrence_across_groups": "Thematic recurrence across groups",
    "tier1_salience_hierarchy": "Agreement in thematic ordering",
    "inductive_theme_accumulation": "Inductive theme accumulation",
}


def metric_label(metric_id: str) -> str:
    return METRIC_LABELS.get(metric_id, metric_id.replace("_", " "))


def calculation_status_label(status: str | None) -> str:
    if not status:
        return UNDEFINED_DISPLAY
    return CALCULATION_STATUS_LABELS.get(status, status)


def format_value(value, digits: int = 4) -> str:
    """
    None is "Undefined". Never 0, never a blank cell that reads as zero.

    A blank would be worse than wrong: a reader scanning a column sees an empty cell
    as "nothing there", which is the same mistake as reading it as zero.
    """
    if value is None:
        return UNDEFINED_DISPLAY
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def format_percent(value, digits: int = 1) -> str:
    if value is None:
        return UNDEFINED_DISPLAY
    return f"{value * 100:.{digits}f}%"
