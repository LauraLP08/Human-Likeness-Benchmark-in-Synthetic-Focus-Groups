"""
Observed token usage, and money only when a rate table says so.

TWO DIFFERENT CLAIMS, KEPT APART.

    OBSERVED_USAGE_UNPRICED   tokens were counted; no rate exists. Cost = Undefined.
    OBSERVED_USAGE_PRICED     tokens were counted and priced with a versioned table.
    ESTIMATED_COST            a forecast. Never produced from a token CEILING - a
                              cap is what a run may not exceed, not what it will use,
                              and multiplying one by a rate produces a number that
                              looks like a prediction and is not.

The rate table is supplied by the researcher or an administrator and is versioned. The
platform never fetches rates, never updates them mid-run, and records the table's
version and hash beside any figure it produces. A missing rate leaves the money column
Undefined and the token column visible - which is the honest split.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..atomic import OnExists, atomic_write_text
from ..paths import safe_path
from ..projects import Project
from .credentials import provider_for_model

PRICING_FILENAME = "pricing_table.json"

ESTIMATED_COST = "ESTIMATED_COST"
OBSERVED_USAGE_PRICED = "OBSERVED_USAGE_PRICED"
OBSERVED_USAGE_UNPRICED = "OBSERVED_USAGE_UNPRICED"
# Cache WRITES are billed at a rate that depends on the time-to-live requested, and
# the ledger does not record which was asked for. Where the two rates differ, the
# price is not knowable from what was recorded - so it is not produced. A bound is
# reported instead, and a bound is not a cost.
CACHE_WRITE_TTL_UNKNOWN = "CACHE_WRITE_TTL_UNKNOWN"
SCENARIO_NOT_BUDGET = "SCENARIO_NOT_BUDGET"

# TTL fields the ledger might carry. If one of these names the TTL, the ambiguity
# disappears and the correct write rate is used.
TTL_5M_VALUES = frozenset({"5m", "5min", "300", "300s", "ephemeral_5m"})
TTL_1H_VALUES = frozenset({"1h", "60m", "3600", "3600s", "ephemeral_1h"})
TTL_FIELDS = ("cache_write_ttl", "cache_creation_ttl", "cache_ttl", "ttl")

UNDEFINED = None

# THE LEDGER NAMES THE MODEL. Found by the first real run: every token-bearing entry
# carries `model` and `role`, and `action` appears only on zero-token moderator
# decision summaries. Reading `action` attributed 55 of 66 entries to nothing.
# Attribution is now exact and needs no guessing - and where an entry names no model,
# it still is not guessed.
UNATTRIBUTED = "unattributed"

# Cache tokens are billed at rates of their own. A table without them cannot price a
# run that used them, and a total that ignored them would be wrong in both
# directions - too low for cache creation, too high for cache reads.
CACHE_FIELDS = ("cache_creation_input_tokens", "cache_read_input_tokens")


@dataclass
class RateRow:
    provider: str
    model: str
    input_rate: float
    output_rate: float
    unit: str = "per_1m_tokens"
    currency: str = "USD"
    effective_from: str = ""
    source: str = ""
    # Cache rates are optional, and a run that used caching cannot be priced without
    # them. WRITES ARE SPLIT BY TTL because the provider charges them differently; one
    # combined "cache_creation_rate" silently picked one of the two.
    cache_write_5m_rate: float | None = None
    cache_write_1h_rate: float | None = None
    cache_read_rate: float | None = None

    @property
    def cache_write_rates_agree(self) -> bool:
        """When both TTLs cost the same, not knowing which was used costs nothing."""
        return (self.cache_write_5m_rate is not None
                and self.cache_write_5m_rate == self.cache_write_1h_rate)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PricingTable:
    table_version: str
    rows: list[RateRow] = field(default_factory=list)
    currency: str = "USD"
    source: str = ""
    note: str = ""
    table_sha256: str = ""

    def rate_for(self, model: str) -> RateRow | None:
        provider = provider_for_model(model)
        for row in self.rows:
            if row.model == model and row.provider in (provider, "unknown"):
                return row
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rows"] = [r.to_dict() for r in self.rows]
        # ALWAYS RECOMPUTED. The stored value used to win, so a rate corrected in
        # memory kept the old hash and every report afterwards named a table that had
        # not priced it.
        d["table_sha256"] = compute_table_hash(self)
        return d


def compute_table_hash(table: PricingTable) -> str:
    body = {"table_version": table.table_version, "currency": table.currency,
            "rows": sorted(([r.provider, r.model, r.input_rate, r.output_rate,
                             r.unit, r.currency, r.effective_from,
                             r.cache_write_5m_rate, r.cache_write_1h_rate,
                             r.cache_read_rate]
                            for r in table.rows), key=lambda x: (x[0], x[1]))}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def table_from_dict(payload: dict) -> PricingTable:
    known = set(RateRow.__dataclass_fields__)
    rows, retired = [], []
    for raw in payload.get("rows", []):
        unknown = sorted(k for k in raw if k not in known)
        if "cache_creation_rate" in unknown:
            # NOT silently reused as a 5-minute rate. The old field did not say which
            # TTL it priced, and guessing would produce a number nobody entered.
            retired.append(str(raw.get("model", "?")))
        rows.append(RateRow(**{k: v for k, v in raw.items() if k in known}))
    table = PricingTable(
        table_version=str(payload.get("table_version", "")),
        rows=rows,
        currency=str(payload.get("currency", "USD")),
        source=str(payload.get("source", "")),
        note=str(payload.get("note", "")))
    if retired:
        table.note = ((table.note + " ") if table.note else "") + (
            f"the retired field `cache_creation_rate` was ignored for "
            f"{sorted(set(retired))}; enter cache_write_5m_rate and "
            f"cache_write_1h_rate, because the two TTLs are billed differently")
    table.table_sha256 = compute_table_hash(table)
    return table


def pricing_path(project: Project) -> Path:
    from .planner import generation_dir
    return safe_path(generation_dir(project), PRICING_FILENAME)


def save_pricing_table(project: Project, table: PricingTable) -> Path:
    target = pricing_path(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target, json.dumps(table.to_dict(), indent=1,
                                         ensure_ascii=False),
                      on_exists=OnExists.REPLACE,
                      verify=lambda written: json.loads(written))
    return target


def load_pricing_table(project: Project) -> PricingTable | None:
    target = pricing_path(project)
    if not target.is_file():
        return None
    try:
        return table_from_dict(json.loads(target.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


# --------------------------------------------------------------- the ledger
@dataclass
class UsageRow:
    job_id: str
    session_id: str
    model: str
    provider: str
    action: str
    n_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_write_unknown_ttl_tokens: int = 0
    input_cost: float | None = None
    output_cost: float | None = None
    total_cost: float | None = None
    # A bound, produced only when the TTL is unknown and the two rates differ. It is
    # never added into a total and is never displayed as a price.
    cost_lower_bound: float | None = None
    cost_upper_bound: float | None = None
    currency: str = ""
    cost_status: str = OBSERVED_USAGE_UNPRICED
    unpriced_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UsageReport:
    rows: list[UsageRow] = field(default_factory=list)
    n_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_unknown_ttl_tokens: int = 0
    total_cost: float | None = None
    cost_lower_bound: float | None = None
    cost_upper_bound: float | None = None
    currency: str = ""
    cost_status: str = OBSERVED_USAGE_UNPRICED
    pricing_table_version: str = ""
    pricing_table_sha256: str = ""
    unpriced_models: list[str] = field(default_factory=list)
    ledger_valid: bool = True
    # Entries with no token fields that look like a FAILED call rather than a decision
    # summary. They may have been billed; the ledger does not say.
    n_untokened_entries: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def cost_display(self) -> str:
        if self.total_cost is not None:
            return f"{self.total_cost:.4f} {self.currency}"
        if self.cost_status == CACHE_WRITE_TTL_UNKNOWN and (
                self.cost_lower_bound is not None):
            # Shown as a range, and named as one. It is not a total.
            return (f"between {self.cost_lower_bound:.4f} and "
                    f"{self.cost_upper_bound:.4f} {self.currency} (bounded: the "
                    f"cache-write time-to-live was not recorded)")
        return "Undefined"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rows"] = [r.to_dict() for r in self.rows]
        d["cost_display"] = self.cost_display
        return d


def read_calls(output_directory: str | Path) -> tuple[list[dict], list[str]]:
    """Every parseable line of `api_calls.jsonl`, plus what could not be read."""
    path = Path(output_directory) / "api_calls.jsonl"
    if not path.is_file():
        return [], [f"no api_calls.jsonl in {output_directory}"]
    calls, problems = [], []
    for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            calls.append(json.loads(line))
        except json.JSONDecodeError:
            problems.append(f"line {number} is not valid JSON and was skipped")
    return calls, problems


def _price(row: UsageRow, table: PricingTable | None) -> None:
    if row.model == UNATTRIBUTED:
        row.unpriced_reason = (
            f"this ledger entry names no model (role {row.action!r}). The tokens are "
            f"counted; no model is assumed, so no price is applied.")
        return
    if table is None:
        row.unpriced_reason = "no pricing table is configured"
        return
    rate = table.rate_for(row.model)
    if rate is None:
        row.unpriced_reason = (f"the pricing table {table.table_version} has no rate "
                               f"for {row.model!r}")
        return
    missing = []
    if row.cache_read_tokens and rate.cache_read_rate is None:
        missing.append("cache_read_rate")
    writes = (row.cache_creation_tokens or row.cache_write_5m_tokens
              or row.cache_write_1h_tokens or row.cache_write_unknown_ttl_tokens)
    if writes and rate.cache_write_5m_rate is None:
        missing.append("cache_write_5m_rate")
    if writes and rate.cache_write_1h_rate is None:
        missing.append("cache_write_1h_rate")
    if missing:
        row.unpriced_reason = (
            f"this row used cache tokens and the rate for {row.model!r} carries no "
            f"{', '.join(sorted(set(missing)))}; an incomplete price is not a price")
        return

    divisor = 1_000_000 if rate.unit == "per_1m_tokens" else 1_000
    row.input_cost = row.input_tokens / divisor * rate.input_rate
    row.output_cost = row.output_tokens / divisor * rate.output_rate
    base = row.input_cost + row.output_cost
    if rate.cache_read_rate is not None:
        base += row.cache_read_tokens / divisor * rate.cache_read_rate
    known_writes = 0.0
    if rate.cache_write_5m_rate is not None:
        known_writes += row.cache_write_5m_tokens / divisor * rate.cache_write_5m_rate
    if rate.cache_write_1h_rate is not None:
        known_writes += row.cache_write_1h_tokens / divisor * rate.cache_write_1h_rate
    base += known_writes
    row.currency = rate.currency

    ambiguous = row.cache_write_unknown_ttl_tokens
    if not ambiguous:
        row.total_cost = base
        row.cost_status = OBSERVED_USAGE_PRICED
        return
    low_rate = min(rate.cache_write_5m_rate, rate.cache_write_1h_rate)
    high_rate = max(rate.cache_write_5m_rate, rate.cache_write_1h_rate)
    if rate.cache_write_rates_agree:
        # The ambiguity has no consequence: both TTLs cost the same.
        row.total_cost = base + ambiguous / divisor * low_rate
        row.cost_status = OBSERVED_USAGE_PRICED
        return
    row.cost_lower_bound = base + ambiguous / divisor * low_rate
    row.cost_upper_bound = base + ambiguous / divisor * high_rate
    row.cost_status = CACHE_WRITE_TTL_UNKNOWN
    row.unpriced_reason = (
        f"{ambiguous} cache-write token(s) were recorded without a time-to-live, and "
        f"{row.model!r} is billed differently for 5-minute and 1-hour writes; the "
        f"cost lies between {row.cost_lower_bound:.4f} and "
        f"{row.cost_upper_bound:.4f} {rate.currency} and is not resolved to a figure")


def _declared_ttl(call: dict) -> str | None:
    """
    The TTL named by a STRING field, or None. Never inferred from anything else.

    This used to also read `cache_creation_5m_input_tokens` / `..._1h_...` and return
    on the first truthy one. That was wrong twice over: an entry carrying BOTH had all
    of its write tokens billed at one rate (33% out on a realistic split, and reported
    as determined rather than bounded), and the token counts in those fields were used
    as a flag and then never counted. They are now read as token counts by
    `_split_cache_writes`, which is what they are.
    """
    for field_name in TTL_FIELDS:
        raw = call.get(field_name)
        if raw is None:
            continue
        value = str(raw).strip().lower()
        if value in TTL_5M_VALUES:
            return "5m"
        if value in TTL_1H_VALUES:
            return "1h"
    return None


def _tokens(call: dict, field_name: str, report=None) -> int:
    """
    A non-negative integer token count, or 0 with a problem recorded.

    `read_calls` goes to some trouble to tolerate a corrupt LINE; a corrupt VALUE used
    to raise straight out of `consolidate` and take the whole cost report with it.
    """
    raw = call.get(field_name)
    if raw is None or raw is False:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        if report is not None:
            report.problems.append(
                f"{field_name}={raw!r} is not a token count; it is read as 0 and the "
                f"total is understated by whatever it was")
        return 0
    if value < 0:
        if report is not None:
            report.problems.append(
                f"{field_name}={value} is negative; a token count cannot be, so it is "
                f"read as 0")
        return 0
    return value


def _split_cache_writes(call: dict, report=None) -> tuple[int, int, int, int]:
    """
    (total, 5m, 1h, unknown_ttl) cache-write tokens for one ledger entry.

    Per-TTL fields are authoritative for the tokens they name. Whatever the aggregate
    carries beyond them is attributed by a declared TTL if there is one, and otherwise
    stays explicitly unknown - never folded into either bucket.
    """
    # THE PROVIDER NESTS THE BREAKDOWN. The usage object carries
    # `cache_creation_input_tokens` as the total and, alongside it,
    # `cache_creation: {ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}`.
    # An earlier version of this function invented flat names
    # (`cache_creation_5m_input_tokens`) that no writer emits, so the per-TTL branch
    # could never fire against a real ledger - a speculative path dressed as support.
    nested = call.get("cache_creation")
    nested = nested if isinstance(nested, dict) else {}
    five = _tokens(nested, "ephemeral_5m_input_tokens", report)
    hour = _tokens(nested, "ephemeral_1h_input_tokens", report)
    if not (five or hour):
        # Tolerated alias: a flattened re-serialisation of the same breakdown.
        five = _tokens(call, "cache_creation_5m_input_tokens", report)
        hour = _tokens(call, "cache_creation_1h_input_tokens", report)
    aggregate = _tokens(call, "cache_creation_input_tokens", report)
    # The aggregate is expected to INCLUDE the per-TTL fields. Where it does not add
    # up, the disagreement is reported rather than reconciled in silence: taking the
    # larger reading avoids losing tokens, but it is a guess about which convention
    # the writer used, and a guess about money should be visible.
    total = max(aggregate, five + hour)
    if aggregate and five + hour > aggregate and report is not None:
        report.problems.append(
            f"a ledger entry reports {aggregate} cache-write tokens in total but "
            f"{five + hour} across its per-TTL fields; {total} is used, and the "
            f"entry contradicts itself")
    remainder = total - five - hour

    unknown = 0
    if remainder > 0:
        ttl = _declared_ttl(call)
        if ttl == "5m":
            five += remainder
        elif ttl == "1h":
            hour += remainder
        else:
            unknown = remainder
    return total, five, hour, unknown


def consolidate(*, job_id: str, session_id: str, output_directory: str | Path,
                moderator_model: str, agent_models: dict[str, str],
                table: PricingTable | None = None) -> UsageReport:
    """
    Consolidate `api_calls.jsonl` by model and action.

    Attribution comes from the ledger itself: every billed entry names its `model`
    and its `role`. Entries with no tokens are moderator decision summaries and are
    skipped rather than counted as calls. An entry that names no model is counted and
    left unattributed - never assigned to one by inference.

    `moderator_model` and `agent_models` are accepted for the caller's convenience
    and are NOT used to attribute usage; the ledger is the authority on what ran.
    """
    calls, problems = read_calls(output_directory)
    report = UsageReport(problems=list(problems),
                         ledger_valid=bool(calls) or not problems)
    if table is not None:
        report.pricing_table_version = table.table_version
        report.pricing_table_sha256 = compute_table_hash(table)
        report.currency = table.currency

    buckets: dict[tuple[str, str], UsageRow] = {}
    for call in calls:
        input_tokens = _tokens(call, "input_tokens", report)
        output_tokens = _tokens(call, "output_tokens", report)
        cache_creation, five, hour, unknown_ttl = _split_cache_writes(call, report)
        cache_read = _tokens(call, "cache_read_input_tokens", report)
        if not any((input_tokens, output_tokens, cache_creation, cache_read)):
            # No tokens recorded. USUALLY a moderator decision summary - but not
            # always: `core.moderator_brain` wraps the response parsing in the same
            # `except` as the call itself, so a parse failure after a BILLED call also
            # lands here with no token fields. Those are counted separately and
            # reported, rather than silently dropped from the call count.
            if call.get("error") or "failed" in str(call.get("event_type", "")):
                report.n_untokened_entries += 1
            continue

        # The ledger names the model. Where it does not, nothing is assumed.
        model = str(call.get("model") or UNATTRIBUTED)
        role = str(call.get("role") or call.get("event_type") or "unknown")
        key = (model, role)
        row = buckets.get(key)
        if row is None:
            row = UsageRow(job_id=job_id, session_id=session_id, model=model,
                           provider=provider_for_model(model), action=role)
            buckets[key] = row
        row.n_calls += 1
        row.input_tokens += input_tokens
        row.output_tokens += output_tokens
        row.cache_creation_tokens += cache_creation
        row.cache_read_tokens += cache_read
        row.cache_write_5m_tokens += five
        row.cache_write_1h_tokens += hour
        row.cache_write_unknown_ttl_tokens += unknown_ttl

    for row in buckets.values():
        _price(row, table)
        report.n_calls += row.n_calls
        report.input_tokens += row.input_tokens
        report.output_tokens += row.output_tokens
        report.cache_creation_tokens += row.cache_creation_tokens
        report.cache_read_tokens += row.cache_read_tokens
        report.cache_write_unknown_ttl_tokens += row.cache_write_unknown_ttl_tokens
    report.rows = sorted(buckets.values(), key=lambda r: (r.model, r.action))

    priced = [r for r in report.rows if r.total_cost is not None]
    # A bounded row IS priced - to a range. Listing it as unpriced pointed the reader
    # at the wrong row and let a genuinely rate-less row pass as a normal bounded
    # result.
    report.unpriced_models = sorted({
        r.model for r in report.rows
        if r.total_cost is None and r.cost_status != CACHE_WRITE_TTL_UNKNOWN})

    priced_rows = [r for r in report.rows if r.total_cost is not None
                   or r.cost_lower_bound is not None]
    blank = [r for r in priced_rows if not r.currency]
    if blank:
        report.problems.append(
            f"{len(blank)} priced row(s) name no currency; a figure in no currency is "
            f"not added to one in dollars")
        report.total_cost = UNDEFINED
        report.cost_status = OBSERVED_USAGE_UNPRICED
        return report

    row_currencies = {r.currency for r in report.rows if r.currency}
    if (len(row_currencies) == 1 and table is not None and table.currency
            and row_currencies != {table.currency}):
        # A REAL TOTAL WITH THE WRONG LABEL is worse than no total. The report's
        # currency came from the table while every figure in it came from the rows.
        actual = next(iter(row_currencies))
        report.currency = actual
        report.problems.append(
            f"the rates price this run in {actual}, but the table is labelled "
            f"{table.currency!r}. The figures are {actual}; the label was wrong.")
    if len(row_currencies) > 1:
        report.problems.append(
            f"the rate table prices these models in {sorted(row_currencies)}; totals "
            f"in different currencies are not added, so no figure is produced")
        report.total_cost = UNDEFINED
        report.cost_status = OBSERVED_USAGE_UNPRICED
        return report
    if row_currencies and table is not None and table.currency and (
            row_currencies != {table.currency}):
        report.problems.append(
            f"the rows are priced in {sorted(row_currencies)} but the table is "
            f"labelled {table.currency!r}; the label is not evidence of the rates")

    if report.n_untokened_entries:
        report.problems.append(
            f"{report.n_untokened_entries} ledger entr(ies) record a failure with no "
            f"token counts. `core.moderator_brain` wraps response parsing in the same "
            f"handler as the call itself, so a parse failure AFTER a billed call looks "
            f"exactly like this. If any were billed, the total is understated.")

    cache_used = bool(report.cache_creation_tokens or report.cache_read_tokens)
    ambiguous_rows = [r for r in report.rows
                      if r.cost_status == CACHE_WRITE_TTL_UNKNOWN]
    unpriced_rows = [r for r in report.rows
                     if r.total_cost is None
                     and r.cost_status != CACHE_WRITE_TTL_UNKNOWN]

    if cache_used and unpriced_rows:
        report.problems.append(
            f"{report.cache_creation_tokens} cache-write and "
            f"{report.cache_read_tokens} cache-read token(s) were used and the rate "
            f"table does not price them. A total that ignored them would be wrong in "
            f"both directions, so no currency figure is produced.")

    if ambiguous_rows and unpriced_rows:
        # A BOUND IS ONLY A BOUND IF IT COVERS EVERY ROW. With an unpriced row in the
        # report, summing the rest would produce a confident-looking range that omits
        # real spending - a one-character typo in a model name once turned USD 1.16
        # into "between 0.09 and 0.11". No range is offered here at all.
        report.total_cost = UNDEFINED
        report.cost_status = OBSERVED_USAGE_UNPRICED
        report.problems.append(
            f"some rows are bounded and {len(unpriced_rows)} row(s) "
            f"({', '.join(sorted({r.model for r in unpriced_rows}))}) carry no rate "
            f"at all; a range over only the priced rows would understate the total, "
            f"so none is produced")
        return report

    if ambiguous_rows:
        # A bound for the whole report, and no total. The distinction matters: a
        # reader who sees a number treats it as the cost.
        report.cost_lower_bound = sum(
            (r.cost_lower_bound if r.cost_lower_bound is not None else r.total_cost)
            for r in report.rows)
        report.cost_upper_bound = sum(
            (r.cost_upper_bound if r.cost_upper_bound is not None else r.total_cost)
            for r in report.rows)
        report.total_cost = UNDEFINED
        report.cost_status = CACHE_WRITE_TTL_UNKNOWN
        report.problems.append(
            f"{report.cache_write_unknown_ttl_tokens} cache-write token(s) carry no "
            f"time-to-live in the ledger and the 5-minute and 1-hour rates differ; "
            f"the cost is bounded, not determined")
        return report

    if report.rows and not unpriced_rows:
        report.total_cost = sum(r.total_cost for r in priced)
        report.cost_status = OBSERVED_USAGE_PRICED
    else:
        report.total_cost = UNDEFINED
        report.cost_status = OBSERVED_USAGE_UNPRICED
    return report


def estimate_note(table: PricingTable | None) -> str:
    """
    There is no estimator, and there is a reason.

    An estimate needs an expected token count. The only number available before a run
    is `--max-turns`, which is a ceiling; pricing a ceiling produces a figure that
    reads as a forecast and is not one.
    """
    if table is None:
        return ("Cost estimate unavailable — no pricing table is configured. Token "
                "usage is still recorded after the run.")
    return (f"Cost estimate unavailable — pricing table {table.table_version} is "
            f"configured, but this platform has no token expectation for a session "
            f"that has not run. --max-turns is a ceiling, not a prediction. Actual "
            f"usage is priced from api_calls.jsonl afterwards.")

# ------------------------------------------------------- pricing context (3F)
RECONCILED = "RECONCILED"
DIVERGENT = "DIVERGENT"
NOT_COMPARABLE = "NOT_COMPARABLE"

# Within this fraction the two figures are treated as the same number seen twice.
# Rounding, per-call minimums and the provider's own aggregation all move the last
# decimal, and calling that a discrepancy would train the reader to ignore real ones.
RECONCILIATION_TOLERANCE = 0.02


@dataclass
class PricingContext:
    """
    WHOSE numbers these are, and WHEN they were true.

    A price without a date is not checkable. The platform fetches nothing: every rate
    in the table was typed in by a researcher, from a page that changes without
    telling anyone, and this record says so on the artefact rather than in a habit.
    """

    table_version: str
    table_sha256: str
    currency: str
    rates_entered_by: str = "researcher"
    rates_source: str = ""
    rates_effective_from: str = ""
    retrieved_utc: str = ""
    applies_to_runs_after_utc: str = ""
    applies_to_runs_before_utc: str = ""
    note: str = ("rates are entered by hand and are never fetched; a run priced with "
                 "this table was priced with the figures as they stood when they "
                 "were entered")

    @property
    def problems(self) -> list[str]:
        out = []
        if not self.rates_source:
            out.append("the rate source is not recorded, so the figures cannot be "
                       "checked against anything")
        if not self.rates_effective_from and not self.retrieved_utc:
            out.append("neither an effective date nor a retrieval date is recorded; "
                       "a price with no date cannot be verified later")
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        d["problems"] = self.problems
        return d


def context_from_table(table: PricingTable | None, *, retrieved_utc: str = "",
                       rates_source: str = "") -> PricingContext | None:
    if table is None:
        return None
    effective = sorted({r.effective_from for r in table.rows if r.effective_from})
    return PricingContext(
        table_version=table.table_version,
        # RECOMPUTED, like everywhere else. The stored value winning here meant the
        # provenance record named one table while the report named another.
        table_sha256=compute_table_hash(table),
        currency=table.currency,
        rates_source=rates_source or table.source,
        rates_effective_from=effective[0] if effective else "",
        retrieved_utc=retrieved_utc)


@dataclass
class ReconciliationRecord:
    """
    The platform's total set beside the provider's own figure.

    NEITHER IS CORRECTED TO MATCH THE OTHER. They are computed from different things -
    a per-call ledger written locally, and a billing system that aggregates across
    everything an account did - and a difference is a finding to report, not an error
    to absorb. The platform's figure is never adjusted to close the gap.
    """

    scope: str                              # what the comparison covers
    platform_total: float | None
    provider_total: float | None
    currency: str = ""
    provider_figure_source: str = ""
    provider_period: str = ""
    status: str = NOT_COMPARABLE
    difference: float | None = None
    relative_difference: float | None = None
    notes: list[str] = field(default_factory=list)
    reconciled_utc: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def reconcile(*, scope: str, platform_total: float | None,
              provider_total: float | None, currency: str = "USD",
              provider_figure_source: str = "", provider_period: str = "",
              utc: str = "") -> ReconciliationRecord:
    record = ReconciliationRecord(
        scope=scope, platform_total=platform_total, provider_total=provider_total,
        currency=currency, provider_figure_source=provider_figure_source,
        provider_period=provider_period, reconciled_utc=utc)

    if platform_total is None:
        record.notes.append(
            "the platform total is Undefined, so there is nothing to compare; an "
            "Undefined total is not read as zero")
        return record
    if provider_total is None:
        record.notes.append("no provider figure was supplied")
        return record
    if not provider_figure_source:
        record.notes.append(
            "the provider figure carries no source; where it came from is part of "
            "whether it means anything")

    record.difference = platform_total - provider_total
    if provider_total:
        record.relative_difference = record.difference / provider_total
        within = abs(record.relative_difference) <= RECONCILIATION_TOLERANCE
    else:
        record.relative_difference = None
        within = abs(record.difference) < 1e-9
    record.status = RECONCILED if within else DIVERGENT
    if record.status == DIVERGENT:
        record.notes.append(
            f"the platform priced {platform_total:.4f} {currency} and the provider "
            f"reports {provider_total:.4f} {currency}. Neither figure is adjusted: "
            f"the provider bills an entire account over a period, and this ledger "
            f"covers {scope}. Check the scope before reading this as an error.")
    return record


# ---------------------------------------------------------- projections (3F)
@dataclass
class ScenarioProjection:
    """
    What a study of this size WOULD have cost at the usage already observed.

    NOT A BUDGET, and labelled so on every artefact. It multiplies one or more
    observed sessions by a session count; it assumes the next sessions resemble the
    ones that ran, which is exactly the assumption a longer guide, a larger panel or a
    different model breaks. It is a scenario for planning conversations, and it is
    never presented as a figure anybody will be charged.
    """

    label: str
    n_sessions: int
    basis_session_ids: list[str] = field(default_factory=list)
    n_observations: int = 0
    per_session_cost: float | None = None
    per_session_cost_min: float | None = None
    per_session_cost_max: float | None = None
    projected_cost: float | None = None
    projected_cost_min: float | None = None
    projected_cost_max: float | None = None
    currency: str = ""
    dispersion_available: bool = False
    single_observation: bool = False
    status: str = SCENARIO_NOT_BUDGET
    assumptions: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = SCENARIO_NOT_BUDGET
        return d


def project_scenario(reports: list[UsageReport], *, n_sessions: int,
                     label: str = "", session_ids: list[str] | None = None
                     ) -> ScenarioProjection:
    """
    Scale observed per-session cost to `n_sessions`.

    Only PRICED observations count. A session whose cost is Undefined contributes
    nothing and is reported as excluded - averaging it in as zero would understate
    every projection that contained one.
    """
    try:
        count = 0 if isinstance(n_sessions, bool) else int(n_sessions)
    except (TypeError, ValueError, OverflowError):
        count = 0
    projection = ScenarioProjection(
        label=label or f"{count} session(s)", n_sessions=count,
        basis_session_ids=list(session_ids or []))
    if isinstance(n_sessions, bool) or count != n_sessions:
        projection.problems.append(
            f"a scenario is a whole number of sessions; {n_sessions!r} was read as "
            f"{count}")
    n_sessions = count
    if n_sessions <= 0:
        projection.problems.append("a scenario needs at least one session")
        return projection

    priced = [r for r in reports if r.total_cost is not None]
    excluded = len(reports) - len(priced)
    if excluded:
        bounded = [r for r in reports
                   if r.total_cost is None and r.cost_lower_bound is not None]
        projection.problems.append(
            f"{excluded} of {len(reports)} observed session(s) have an Undefined "
            f"cost and are excluded; they are not counted as zero")
        if bounded:
            # NOT MISSING AT RANDOM. The sessions that end up bounded are the
            # cache-heavy ones, so dropping them scales the cheapest, least
            # representative session and understates the scenario.
            low = min(r.cost_lower_bound for r in bounded)
            high = max(r.cost_upper_bound for r in bounded)
            projection.problems.append(
                f"{len(bounded)} of the excluded session(s) are BOUNDED, not unknown: "
                f"each lies between {low:.4f} and {high:.4f}. They are excluded "
                f"because a bound is not a figure, not because they were cheap - a "
                f"projection built without them is likely to understate.")
    if not priced:
        projection.problems.append(
            "no observed session carries a priced cost, so there is nothing to "
            "scale from")
        return projection

    costs = [r.total_cost for r in priced]
    projection.n_observations = len(costs)
    projection.currency = priced[0].currency
    currencies = {r.currency for r in priced if r.currency}
    if len(currencies) > 1:
        projection.problems.append(
            f"the observed sessions are priced in {sorted(currencies)}; they are not "
            f"added together")
        return projection

    projection.per_session_cost = sum(costs) / len(costs)
    projection.per_session_cost_min = min(costs)
    projection.per_session_cost_max = max(costs)
    projection.projected_cost = projection.per_session_cost * n_sessions
    projection.projected_cost_min = projection.per_session_cost_min * n_sessions
    projection.projected_cost_max = projection.per_session_cost_max * n_sessions
    projection.dispersion_available = len(costs) > 1
    projection.single_observation = len(costs) == 1
    if projection.single_observation:
        # One point has no spread. The min and max are that same point, and saying so
        # is honest; showing them as a range would invent a confidence nobody has.
        projection.problems.append(
            "this scenario rests on ONE observed session; it carries no dispersion "
            "and the range shown is that single value repeated")
    projection.assumptions = [
        f"every one of the {n_sessions} session(s) resembles the "
        f"{projection.n_observations} that ran",
        "the same models, guide length and panel size are used throughout",
        "provider rates do not change between now and the run",
        "no session fails and is repeated",
    ]
    return projection
