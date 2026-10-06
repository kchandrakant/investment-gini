from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8))
    isin: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="INR")


class InstrumentSymbol(Base):
    __tablename__ = "instrument_symbols"
    __table_args__ = (
        UniqueConstraint("exchange", "symbol", "effective_from", name="uq_symbol_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    exchange: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class Universe(Base):
    __tablename__ = "universes"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_universe_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[str] = mapped_column(String(100))


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    source_class: Mapped[str] = mapped_column(String(40))
    reliability_tier: Mapped[int] = mapped_column()
    terms_reference: Mapped[str | None] = mapped_column(Text)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    requested_range: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    error_summary: Mapped[str | None] = mapped_column(Text)


class SourceRecord(Base):
    __tablename__ = "source_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    source_identifier: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    source_artifact_checksum: Mapped[str | None] = mapped_column(String(64))
    reported_period: Mapped[str | None] = mapped_column(String(50))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UniverseMembership(Base):
    __tablename__ = "universe_memberships"
    __table_args__ = (
        UniqueConstraint(
            "universe_id",
            "instrument_id",
            "effective_from",
            name="uq_membership_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    universe_id: Mapped[int] = mapped_column(ForeignKey("universes.id"), index=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_records.id"))
    ended_by_source_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_records.id")
    )
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True)


class DataQualityFlag(Base):
    __tablename__ = "data_quality_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    field_name: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    observed_value: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "session_date",
            "series",
            name="uq_price_bar_session",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_records.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    series: Mapped[str] = mapped_column(String(8))
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    previous_close: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    volume: Mapped[int] = mapped_column(BigInteger)
    traded_value: Mapped[Decimal] = mapped_column(Numeric(24, 4))
    trade_count: Mapped[int] = mapped_column(BigInteger)
    is_adjusted: Mapped[bool] = mapped_column(Boolean, default=False)


class BenchmarkBar(Base):
    __tablename__ = "benchmark_bars"
    __table_args__ = (
        UniqueConstraint(
            "benchmark_code",
            "session_date",
            name="uq_benchmark_bar_session",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_records.id"), index=True)
    benchmark_code: Mapped[str] = mapped_column(String(40), index=True)
    benchmark_name: Mapped[str] = mapped_column(String(100))
    session_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4))


class CorporateAction(Base):
    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "action_type",
            "ex_date",
            "ratio_numerator",
            "ratio_denominator",
            "cash_amount",
            name="uq_corporate_action_event",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_records.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(20), index=True)
    ex_date: Mapped[date] = mapped_column(Date, index=True)
    record_date: Mapped[date | None] = mapped_column(Date)
    ratio_numerator: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    ratio_denominator: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    verification_status: Mapped[str] = mapped_column(String(20), index=True)

class MetricDefinition(Base):
    __tablename__ = "metric_definitions"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_metric_definition_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(40))
    period_type: Mapped[str] = mapped_column(String(20))
    value_kind: Mapped[str] = mapped_column(String(20))
    formula: Mapped[str | None] = mapped_column(Text)
    is_derived: Mapped[bool] = mapped_column(Boolean, default=False)

class FundamentalFact(Base):
    __tablename__ = "fundamental_facts"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "metric_definition_id",
            "period_start",
            "period_end",
            "consolidation_scope",
            "available_at",
            name="uq_fundamental_fact_revision",
        ),
        CheckConstraint(
            "status != 'available' OR value IS NOT NULL",
            name="ck_available_fundamental_has_value",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    metric_definition_id: Mapped[int] = mapped_column(
        ForeignKey("metric_definitions.id"), index=True
    )
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_records.id"), index=True)
    supersedes_fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("fundamental_facts.id"), index=True
    )
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, index=True)
    filing_date: Mapped[date] = mapped_column(Date)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consolidation_scope: Mapped[str] = mapped_column(String(20))
    value: Mapped[Decimal | None] = mapped_column(Numeric(30, 8))
    status: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str | None] = mapped_column(String(3))
    reported_unit: Mapped[str] = mapped_column(String(40))
