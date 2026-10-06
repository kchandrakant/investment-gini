from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class DataStatus(StrEnum):
    AVAILABLE = "available"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"
    STALE = "stale"
    ESTIMATED = "estimated"


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"


@dataclass(frozen=True)
class SourceMetadata:
    provider: str
    source_identifier: str
    retrieved_at: datetime
    checksum: str
    source_class: str = "file"
    reliability_tier: int = 6
    terms_reference: str | None = None


@dataclass(frozen=True)
class UniverseMembershipRecord:
    universe: str
    universe_version: str
    symbol: str
    isin: str
    company_name: str
    exchange: Exchange
    sector: str | None
    industry: str | None
    effective_from: date
    effective_to: date | None
    source: SourceMetadata


@dataclass(frozen=True)
class PriceBarRecord:
    isin: str
    symbol: str
    session_date: date
    series: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    previous_close: Decimal
    volume: int
    traded_value: Decimal
    trade_count: int
    source: SourceMetadata
    is_adjusted: bool = False


@dataclass(frozen=True)
class BenchmarkBarRecord:
    benchmark_code: str
    benchmark_name: str
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    source: SourceMetadata


@dataclass(frozen=True)
class CorporateActionRecord:
    isin: str
    action_type: str
    ex_date: date
    record_date: date | None
    ratio_numerator: Decimal | None
    ratio_denominator: Decimal | None
    cash_amount: Decimal | None
    currency: str
    verification_status: str
    source: SourceMetadata
    
@dataclass(frozen=True)
class MetricDefinitionRecord:
    code: str
    version: str
    name: str
    description: str
    unit: str
    period_type: str
    value_kind: str
    formula: str | None
    is_derived: bool

@dataclass(frozen=True)
class FundamentalFactRecord:
    isin: str
    metric_code: str
    metric_version: str
    period_start: date | None
    period_end: date
    filing_date: date
    available_at: datetime
    consolidation_scope: str
    value: Decimal | None
    status: DataStatus
    currency: str | None
    source: SourceMetadata
