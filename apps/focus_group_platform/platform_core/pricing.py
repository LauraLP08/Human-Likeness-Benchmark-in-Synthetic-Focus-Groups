"""
Pricing SCHEMAS only (Phase 2A scope).

Deliberately incomplete: this module defines the shape of a dated, versioned rate
table and the shape of a cost estimate. It does NOT look up prices, does not ship
rates, and does not compute a cost from a run. Those arrive in Phase 2B together with
`api_calls.jsonl` reading.

Two rules are already encoded, because they are the ones that go wrong quietly:
  * a model absent from the table yields an UNDEFINED cost, never zero;
  * a total computed with any model unpriced is a LOWER BOUND and is labelled so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


class PricingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RateRow:
    model: str
    mode: str                       # standard | batch
    input_usd_per_mtok: float
    output_usd_per_mtok: float


@dataclass
class PricingTable:
    version: str                    # e.g. "2026-08-04.1"
    effective_date: date
    source_note: str                # where the rates came from and when they were read
    rates: list[RateRow] = field(default_factory=list)

    def rate_for(self, model: str, mode: str = "batch") -> RateRow | None:
        for row in self.rates:
            if row.model == model and row.mode == mode:
                return row
        return None

    def known_models(self, mode: str | None = None) -> list[str]:
        return sorted({r.model for r in self.rates
                       if mode is None or r.mode == mode})


@dataclass
class ModelUsage:
    model: str
    input_tokens: int
    output_tokens: int
    calls: int = 0


@dataclass
class CostEstimate:
    """
    Always an estimate. `is_estimate` is a literal, not a flag to be turned off.
    """

    by_model: dict[str, dict] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    total_usd: float | None = None
    pricing_table_version: str = ""
    unpriced_models: list[str] = field(default_factory=list)
    is_estimate: bool = True
    is_lower_bound: bool = False
    basis: str = "api_calls.jsonl token counts x local rate table"

    @property
    def label(self) -> str:
        if self.total_usd is None:
            return "cost undefined - no priced model in this run"
        if self.is_lower_bound:
            return (f"USD {self.total_usd:.4f} (lower bound - "
                    f"{len(self.unpriced_models)} model(s) missing from the rate "
                    f"table)")
        return f"USD {self.total_usd:.4f} (estimate, table {self.pricing_table_version})"


def empty_estimate(pricing_table_version: str = "") -> CostEstimate:
    """A zero-usage estimate. Note the total is None, not 0.0 - nothing was priced."""
    return CostEstimate(pricing_table_version=pricing_table_version, total_usd=None)
