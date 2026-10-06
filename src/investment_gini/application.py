from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import sleep as time_sleep
from typing import TYPE_CHECKING

from alembic import command
from alembic.config import Config
from sqlalchemy import func, or_, select

from investment_gini.config import Settings, load_settings
from investment_gini.database import create_database_engine, create_session_factory, session_scope
from investment_gini.ingestion import (
    BenchmarkIngestionService,
    CorporateActionIngestionService,
    IngestionSummary,
    PriceIngestionService,
    UniverseIngestionService,
)
from investment_gini.models import (
    BenchmarkBar,
    CorporateAction,
    DataQualityFlag,
    DataSource,
    FundamentalFact,
    IngestionRun,
    Instrument,
    InstrumentSymbol,
    MetricDefinition,
    PriceBar,
    SourceRecord,
    Universe,
    UniverseMembership,
)
from investment_gini.providers import (
    CsvCorporateActionProvider,
    CsvUniverseProvider,
    NiftyHistoricalIndexProvider,
    NiftyIndicesUniverseProvider,
    NseArchiveUnavailableError,
    NseBhavcopyProvider,
    NseCorporateActionProvider,
)
from investment_gini.repositories import UniverseRepository

if TYPE_CHECKING:
    from investment_gini.technical import TechnicalSnapshot


@dataclass(frozen=True)
class DashboardSnapshot:
    instrument_count: int
    price_bar_count: int
    price_session_count: int
    price_first_session: date | None
    price_last_session: date | None
    adjusted_price_bar_count: int
    data_sources: tuple[str, ...]
    universe_versions: tuple[str, ...]
    open_quality_flags: int


@dataclass(frozen=True)
class MemberView:
    company_name: str
    isin: str
    exchange: str
    sector: str | None
    industry: str | None


@dataclass(frozen=True)
class InstrumentSearchResult:
    company_name: str
    isin: str
    symbol: str
    exchange: str
    sector: str | None
    industry: str | None


@dataclass(frozen=True)
class PricePoint:
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    previous_close: Decimal
    volume: int
    traded_value: Decimal
    trade_count: int
    is_adjusted: bool
    source_name: str
    source_identifier: str
    source_checksum: str
    retrieved_at: datetime


@dataclass(frozen=True)
class PriceQualityWarning:
    severity: str
    reason: str
    observed_value: str | None
    session_date: date | None


@dataclass(frozen=True)
class PriceSeries:
    instrument: InstrumentSearchResult
    requested_start: date
    requested_end: date
    points: tuple[PricePoint, ...]
    adjustment_status: str
    latest_session: date | None
    latest_retrieved_at: datetime | None
    source_names: tuple[str, ...]
    source_identifiers: tuple[str, ...]
    quality_warnings: tuple[PriceQualityWarning, ...]
    corporate_action_count: int = 0
    corporate_action_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkPoint:
    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    source_identifier: str
    source_checksum: str
    retrieved_at: datetime


@dataclass(frozen=True)
class BenchmarkSeries:
    benchmark_code: str
    benchmark_name: str
    requested_start: date
    requested_end: date
    points: tuple[BenchmarkPoint, ...]
    source_identifiers: tuple[str, ...]
    latest_session: date | None
    latest_retrieved_at: datetime | None


@dataclass(frozen=True)
class FundamentalFactPoint:
    metric_code: str
    metric_version: str
    metric_name: str
    period_start: date | None
    period_end: date
    filing_date: date
    available_at: datetime
    consolidation_scope: str
    value: Decimal | None
    status: str
    unit: str
    currency: str | None
    source_identifier: str
    source_checksum: str


@dataclass(frozen=True)
class BenchmarkRangeSyncSummary:
    start_date: date
    end_date: date
    requests: int
    bars_inserted: int
    bars_skipped: int
    quality_flags: int
    run_ids: tuple[int, ...]


@dataclass(frozen=True)
class MembershipCoverageSummary:
    requested_start: date
    requested_end: date
    snapshot_count: int
    first_snapshot: date | None
    last_snapshot: date | None
    is_point_in_time_covered: bool
    uncovered_start: date | None


@dataclass(frozen=True)
class PriceRangeDayOutcome:
    session_date: date
    status: str
    inserted: int = 0
    skipped: int = 0
    quality_flags: int = 0
    detail: str | None = None
    missing_isins: tuple[str, ...] = ()


@dataclass(frozen=True)
class PriceRangeSyncSummary:
    start_date: date
    end_date: date
    outcomes: tuple[PriceRangeDayOutcome, ...]
    sessions_ingested: int
    sessions_already_complete: int
    weekends_skipped: int
    archives_unavailable: int
    sessions_failed: int
    bars_inserted: int
    bars_skipped: int
    quality_flags: int
    incomplete_sessions: int = 0


@dataclass(frozen=True)
class InstrumentCoverageGap:
    isin: str
    company_name: str
    missing_sessions: int


@dataclass(frozen=True)
class PriceCoverageSummary:
    expected_instruments: int
    total_bars: int
    total_sessions: int
    complete_sessions: int
    incomplete_sessions: int
    first_session: date | None
    last_session: date | None
    minimum_bars_per_session: int
    maximum_bars_per_session: int
    instrument_gaps: tuple[InstrumentCoverageGap, ...]


def initialize_database(settings: Settings | None = None) -> None:
    resolved = settings or load_settings()
    create_database_engine(resolved.app.database_url).dispose()
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", resolved.app.database_url)
    command.upgrade(alembic_config, "head")


def get_fundamental_facts_as_of(
    isin: str,
    as_of: datetime,
    settings: Settings | None = None,
) -> tuple[FundamentalFactPoint, ...]:
    resolved_settings = settings or load_settings()
    engine = create_database_engine(resolved_settings.app.database_url)
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        rows = session.execute(
            select(FundamentalFact, MetricDefinition, SourceRecord)
            .join(Instrument, Instrument.id == FundamentalFact.instrument_id)
            .join(
                MetricDefinition,
                MetricDefinition.id == FundamentalFact.metric_definition_id,
            )
            .join(SourceRecord, SourceRecord.id == FundamentalFact.source_record_id)
            .where(
                Instrument.isin == isin,
                FundamentalFact.available_at <= as_of,
            )
            .order_by(FundamentalFact.available_at.desc())
        ).all()

    latest: dict[tuple[int, date, str], FundamentalFactPoint] = {}
    for fact, definition, source_record in rows:
        key = (definition.id, fact.period_end, fact.consolidation_scope)
        if key not in latest:
            latest[key] = FundamentalFactPoint(
                metric_code=definition.code,
                metric_version=definition.version,
                metric_name=definition.name,
                period_start=fact.period_start,
                period_end=fact.period_end,
                filing_date=fact.filing_date,
                available_at=fact.available_at,
                consolidation_scope=fact.consolidation_scope,
                value=fact.value,
                status=fact.status,
                unit=definition.unit,
                currency=fact.currency,
                source_identifier=source_record.source_identifier,
                source_checksum=source_record.checksum,
            )
    return tuple(
        sorted(latest.values(), key=lambda item: (item.metric_code, item.period_end))
    )


def import_universe_csv(path: Path, settings: Settings | None = None) -> IngestionSummary:
    resolved = settings or load_settings()
    batch = CsvUniverseProvider().fetch_memberships(path)
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        return UniverseIngestionService(session).ingest(batch)


def import_corporate_actions_csv(
    path: Path,
    source_name: str,
    terms_reference: str,
    settings: Settings | None = None,
) -> IngestionSummary:
    resolved = settings or load_settings()
    batch = CsvCorporateActionProvider().fetch_actions(
        path,
        source_name,
        terms_reference,
    )
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        return CorporateActionIngestionService(session).ingest(batch)


def sync_nifty200_corporate_actions(
    start_date: date,
    end_date: date,
    universe_as_of: date,
    settings: Settings | None = None,
    provider: NseCorporateActionProvider | None = None,
) -> IngestionSummary:
    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        instruments = UniverseRepository(session).members_as_of("NIFTY 200", universe_as_of)
        requested_isins = {instrument.isin for instrument in instruments}
    if not requested_isins:
        raise ValueError(f"no Nifty 200 membership found for {universe_as_of.isoformat()}")

    batch = (provider or NseCorporateActionProvider()).fetch_actions(
        start_date, end_date, requested_isins
    )
    with session_scope(factory) as session:
        return CorporateActionIngestionService(session).ingest(batch)


def sync_nifty200(
    as_of: date,
    settings: Settings | None = None,
    provider: NiftyIndicesUniverseProvider | None = None,
) -> IngestionSummary:
    resolved = settings or load_settings()
    batch = (provider or NiftyIndicesUniverseProvider()).fetch_memberships(as_of)
    if batch.issues:
        reasons = "; ".join(issue.reason for issue in batch.issues)
        raise ValueError(f"official Nifty 200 snapshot failed validation: {reasons}")

    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        return UniverseIngestionService(session).ingest(batch)


def sync_nifty200_prices(
    session_date: date,
    universe_as_of: date,
    settings: Settings | None = None,
    provider: NseBhavcopyProvider | None = None,
) -> IngestionSummary:
    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        instruments = UniverseRepository(session).members_as_of("NIFTY 200", universe_as_of)
        requested_isins = {instrument.isin for instrument in instruments}
    if not requested_isins:
        raise ValueError(f"no Nifty 200 membership found for {universe_as_of.isoformat()}")

    batch = (provider or NseBhavcopyProvider()).fetch_prices(session_date, requested_isins)
    with session_scope(factory) as session:
        return PriceIngestionService(session).ingest(batch)


def sync_nifty200_benchmark(
    start_date: date,
    end_date: date,
    settings: Settings | None = None,
    provider: NiftyHistoricalIndexProvider | None = None,
    request_delay_seconds: float = 0,
    sleep: Callable[[float], None] = time_sleep,
) -> BenchmarkRangeSyncSummary:
    if end_date < start_date:
        raise ValueError("end date must not precede start date")
    if request_delay_seconds < 0:
        raise ValueError("request delay must not be negative")

    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    resolved_provider = provider or NiftyHistoricalIndexProvider()
    summaries: list[IngestionSummary] = []
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=365), end_date)
        if summaries and request_delay_seconds:
            sleep(request_delay_seconds)
        batch = resolved_provider.fetch_benchmark("Nifty 200", chunk_start, chunk_end)
        with session_scope(factory) as session:
            summaries.append(BenchmarkIngestionService(session).ingest(batch))
        chunk_start = chunk_end + timedelta(days=1)

    return BenchmarkRangeSyncSummary(
        start_date=start_date,
        end_date=end_date,
        requests=len(summaries),
        bars_inserted=sum(summary.inserted for summary in summaries),
        bars_skipped=sum(summary.skipped for summary in summaries),
        quality_flags=sum(summary.quality_flags for summary in summaries),
        run_ids=tuple(summary.run_id for summary in summaries),
    )


def sync_nifty200_price_range(
    start_date: date,
    end_date: date,
    universe_as_of: date,
    settings: Settings | None = None,
    provider: NseBhavcopyProvider | None = None,
    request_delay_seconds: float = 0,
    sleep: Callable[[float], None] = time_sleep,
) -> PriceRangeSyncSummary:
    if end_date < start_date:
        raise ValueError("end date must not precede start date")
    if request_delay_seconds < 0:
        raise ValueError("request delay must not be negative")

    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        instruments = UniverseRepository(session).members_as_of("NIFTY 200", universe_as_of)
        requested_isins = {instrument.isin for instrument in instruments}
    if not requested_isins:
        raise ValueError(f"no Nifty 200 membership found for {universe_as_of.isoformat()}")

    resolved_provider = provider or NseBhavcopyProvider()
    outcomes: list[PriceRangeDayOutcome] = []
    archive_requested = False
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() >= 5:
            outcomes.append(PriceRangeDayOutcome(current_date, "weekend"))
            current_date += timedelta(days=1)
            continue

        with session_scope(factory) as session:
            existing_isins = set(
                session.scalars(
                    select(Instrument.isin)
                    .join(PriceBar, PriceBar.instrument_id == Instrument.id)
                    .where(
                        PriceBar.session_date == current_date,
                        Instrument.isin.in_(requested_isins),
                    )
                )
            )
        missing_isins = requested_isins - existing_isins
        if not missing_isins:
            outcomes.append(
                PriceRangeDayOutcome(
                    current_date,
                    "already_complete",
                    skipped=len(requested_isins),
                )
            )
            current_date += timedelta(days=1)
            continue

        try:
            if archive_requested and request_delay_seconds:
                sleep(request_delay_seconds)
            batch = resolved_provider.fetch_prices(current_date, missing_isins)
            archive_requested = True
            with session_scope(factory) as session:
                summary = PriceIngestionService(session).ingest(batch)
            returned_isins = {record.isin for record in batch.records}
            still_missing = tuple(sorted(missing_isins - returned_isins))
            status = (
                "ingested_with_warnings"
                if summary.quality_flags or still_missing
                else "ingested"
            )
            outcomes.append(
                PriceRangeDayOutcome(
                    current_date,
                    status,
                    inserted=summary.inserted,
                    skipped=summary.skipped,
                    quality_flags=summary.quality_flags,
                    detail=(
                        f"{len(still_missing)} requested instruments remain missing"
                        if still_missing
                        else None
                    ),
                    missing_isins=still_missing,
                )
            )
        except NseArchiveUnavailableError as error:
            archive_requested = True
            outcomes.append(
                PriceRangeDayOutcome(current_date, "archive_unavailable", detail=str(error))
            )
        except (RuntimeError, ValueError) as error:
            archive_requested = True
            outcomes.append(PriceRangeDayOutcome(current_date, "failed", detail=str(error)))
        current_date += timedelta(days=1)

    return PriceRangeSyncSummary(
        start_date=start_date,
        end_date=end_date,
        outcomes=tuple(outcomes),
        sessions_ingested=sum(outcome.status.startswith("ingested") for outcome in outcomes),
        sessions_already_complete=sum(
            outcome.status == "already_complete" for outcome in outcomes
        ),
        weekends_skipped=sum(outcome.status == "weekend" for outcome in outcomes),
        archives_unavailable=sum(
            outcome.status == "archive_unavailable" for outcome in outcomes
        ),
        sessions_failed=sum(outcome.status == "failed" for outcome in outcomes),
        bars_inserted=sum(outcome.inserted for outcome in outcomes),
        bars_skipped=sum(outcome.skipped for outcome in outcomes),
        quality_flags=sum(outcome.quality_flags for outcome in outcomes),
        incomplete_sessions=sum(bool(outcome.missing_isins) for outcome in outcomes),
    )


def get_nifty200_price_coverage(
    universe_as_of: date,
    settings: Settings | None = None,
) -> PriceCoverageSummary:
    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        instruments = UniverseRepository(session).members_as_of("NIFTY 200", universe_as_of)
        instrument_by_id = {instrument.id: instrument for instrument in instruments}
        if not instrument_by_id:
            raise ValueError(f"no Nifty 200 membership found for {universe_as_of.isoformat()}")

        session_counts = session.execute(
            select(PriceBar.session_date, func.count(PriceBar.id))
            .where(PriceBar.instrument_id.in_(instrument_by_id))
            .group_by(PriceBar.session_date)
            .order_by(PriceBar.session_date)
        ).all()
        instrument_counts: dict[int, int] = {
            instrument_id: count
            for instrument_id, count in session.execute(
                select(PriceBar.instrument_id, func.count(PriceBar.id))
                .where(PriceBar.instrument_id.in_(instrument_by_id))
                .group_by(PriceBar.instrument_id)
            ).all()
        }

    expected = len(instrument_by_id)
    total_sessions = len(session_counts)
    counts = [count for _, count in session_counts]
    gaps = tuple(
        sorted(
            (
                InstrumentCoverageGap(
                    instrument.isin,
                    instrument.company_name,
                    total_sessions - instrument_counts.get(instrument_id, 0),
                )
                for instrument_id, instrument in instrument_by_id.items()
                if instrument_counts.get(instrument_id, 0) < total_sessions
            ),
            key=lambda gap: (-gap.missing_sessions, gap.isin),
        )
    )
    return PriceCoverageSummary(
        expected_instruments=expected,
        total_bars=sum(counts),
        total_sessions=total_sessions,
        complete_sessions=sum(count == expected for count in counts),
        incomplete_sessions=sum(count < expected for count in counts),
        first_session=session_counts[0][0] if session_counts else None,
        last_session=session_counts[-1][0] if session_counts else None,
        minimum_bars_per_session=min(counts, default=0),
        maximum_bars_per_session=max(counts, default=0),
        instrument_gaps=gaps,
    )


def get_latest_nifty200_as_of(settings: Settings | None = None) -> date | None:
    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        return session.scalar(
            select(func.max(UniverseMembership.effective_from))
            .join(Universe, Universe.id == UniverseMembership.universe_id)
            .where(Universe.name == "NIFTY 200")
        )


def get_nifty200_membership_coverage(
    start_date: date,
    end_date: date,
    settings: Settings | None = None,
) -> MembershipCoverageSummary:
    if end_date < start_date:
        raise ValueError("end date must not precede start date")
    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        snapshots = tuple(
            session.scalars(
                select(UniverseMembership.effective_from)
                .join(Universe, Universe.id == UniverseMembership.universe_id)
                .where(Universe.name == "NIFTY 200")
                .distinct()
                .order_by(UniverseMembership.effective_from)
            )
        )
    first_snapshot = snapshots[0] if snapshots else None
    covered = first_snapshot is not None and start_date >= first_snapshot
    return MembershipCoverageSummary(
        requested_start=start_date,
        requested_end=end_date,
        snapshot_count=len(snapshots),
        first_snapshot=first_snapshot,
        last_snapshot=snapshots[-1] if snapshots else None,
        is_point_in_time_covered=covered,
        uncovered_start=None if covered else start_date,
    )


def search_nifty200_instruments(
    query: str,
    universe_as_of: date,
    settings: Settings | None = None,
    limit: int = 50,
) -> tuple[InstrumentSearchResult, ...]:
    if limit < 1:
        raise ValueError("limit must be positive")

    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    statement = (
        select(Instrument, InstrumentSymbol.symbol)
        .join(UniverseMembership, UniverseMembership.instrument_id == Instrument.id)
        .join(Universe, Universe.id == UniverseMembership.universe_id)
        .join(InstrumentSymbol, InstrumentSymbol.instrument_id == Instrument.id)
        .where(
            Universe.name == "NIFTY 200",
            UniverseMembership.effective_from <= universe_as_of,
            or_(
                UniverseMembership.effective_to.is_(None),
                UniverseMembership.effective_to >= universe_as_of,
            ),
            InstrumentSymbol.effective_from <= universe_as_of,
            or_(
                InstrumentSymbol.effective_to.is_(None),
                InstrumentSymbol.effective_to >= universe_as_of,
            ),
        )
        .distinct()
        .order_by(Instrument.company_name, InstrumentSymbol.symbol)
        .limit(limit)
    )
    normalized_query = query.strip().lower()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                func.lower(Instrument.company_name).like(pattern),
                func.lower(Instrument.isin).like(pattern),
                func.lower(InstrumentSymbol.symbol).like(pattern),
            )
        )

    with session_scope(factory) as session:
        rows = session.execute(statement).all()
        return tuple(
            InstrumentSearchResult(
                company_name=instrument.company_name,
                isin=instrument.isin,
                symbol=symbol,
                exchange=instrument.exchange,
                sector=instrument.sector,
                industry=instrument.industry,
            )
            for instrument, symbol in rows
        )


def get_price_series(
    isin: str,
    start_date: date,
    end_date: date,
    settings: Settings | None = None,
) -> PriceSeries:
    if end_date < start_date:
        raise ValueError("end date must not precede start date")

    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    normalized_isin = isin.strip().upper()
    with session_scope(factory) as session:
        instrument = session.scalar(select(Instrument).where(Instrument.isin == normalized_isin))
        if instrument is None:
            raise ValueError(f"unknown instrument ISIN: {normalized_isin}")
        symbol = session.scalar(
            select(InstrumentSymbol.symbol)
            .where(
                InstrumentSymbol.instrument_id == instrument.id,
                InstrumentSymbol.effective_from <= end_date,
                or_(
                    InstrumentSymbol.effective_to.is_(None),
                    InstrumentSymbol.effective_to >= end_date,
                ),
            )
            .order_by(InstrumentSymbol.effective_from.desc())
            .limit(1)
        )
        if symbol is None:
            symbol = session.scalar(
                select(InstrumentSymbol.symbol)
                .where(InstrumentSymbol.instrument_id == instrument.id)
                .order_by(InstrumentSymbol.effective_from.desc())
                .limit(1)
            )
        if symbol is None:
            raise ValueError(f"no symbol history found for ISIN: {normalized_isin}")

        rows = session.execute(
            select(PriceBar, SourceRecord, DataSource.name)
            .join(SourceRecord, SourceRecord.id == PriceBar.source_record_id)
            .join(IngestionRun, IngestionRun.id == SourceRecord.ingestion_run_id)
            .join(DataSource, DataSource.id == IngestionRun.data_source_id)
            .where(
                PriceBar.instrument_id == instrument.id,
                PriceBar.session_date >= start_date,
                PriceBar.session_date <= end_date,
            )
            .order_by(PriceBar.session_date)
        ).all()
        warning_rows = session.execute(
            select(DataQualityFlag, SourceRecord.reported_period)
            .join(IngestionRun, IngestionRun.id == DataQualityFlag.ingestion_run_id)
            .join(SourceRecord, SourceRecord.ingestion_run_id == IngestionRun.id)
            .where(
                DataQualityFlag.entity_type == "price_bar",
                DataQualityFlag.observed_value == normalized_isin,
                or_(
                    SourceRecord.reported_period.is_(None),
                    SourceRecord.reported_period.between(
                        start_date.isoformat(), end_date.isoformat()
                    ),
                ),
            )
            .order_by(SourceRecord.reported_period, DataQualityFlag.id)
        ).all()

        instrument_view = InstrumentSearchResult(
            company_name=instrument.company_name,
            isin=instrument.isin,
            symbol=symbol,
            exchange=instrument.exchange,
            sector=instrument.sector,
            industry=instrument.industry,
        )
        points = tuple(
            PricePoint(
                session_date=bar.session_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                previous_close=bar.previous_close,
                volume=bar.volume,
                traded_value=bar.traded_value,
                trade_count=bar.trade_count,
                is_adjusted=bar.is_adjusted,
                source_name=source_name,
                source_identifier=source.source_identifier,
                source_checksum=source.checksum,
                retrieved_at=source.retrieved_at,
            )
            for bar, source, source_name in rows
        )
        warnings = tuple(
            PriceQualityWarning(
                severity=flag.severity,
                reason=flag.reason,
                observed_value=flag.observed_value,
                session_date=date.fromisoformat(reported_period) if reported_period else None,
            )
            for flag, reported_period in warning_rows
        )

    adjustment_states = {point.is_adjusted for point in points}
    if not points:
        adjustment_status = "no_data"
    elif adjustment_states == {False}:
        adjustment_status = "raw_unadjusted"
    elif adjustment_states == {True}:
        adjustment_status = "adjusted"
    else:
        adjustment_status = "mixed"
    return PriceSeries(
        instrument=instrument_view,
        requested_start=start_date,
        requested_end=end_date,
        points=points,
        adjustment_status=adjustment_status,
        latest_session=points[-1].session_date if points else None,
        latest_retrieved_at=max((point.retrieved_at for point in points), default=None),
        source_names=tuple(sorted({point.source_name for point in points})),
        source_identifiers=tuple(sorted({point.source_identifier for point in points})),
        quality_warnings=warnings,
    )


def get_benchmark_series(
    benchmark_code: str,
    start_date: date,
    end_date: date,
    settings: Settings | None = None,
) -> BenchmarkSeries:
    if end_date < start_date:
        raise ValueError("end date must not precede start date")
    normalized_code = benchmark_code.strip().upper()
    if not normalized_code:
        raise ValueError("benchmark code is required")

    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        rows = session.execute(
            select(BenchmarkBar, SourceRecord)
            .join(SourceRecord, SourceRecord.id == BenchmarkBar.source_record_id)
            .where(
                BenchmarkBar.benchmark_code == normalized_code,
                BenchmarkBar.session_date >= start_date,
                BenchmarkBar.session_date <= end_date,
            )
            .order_by(BenchmarkBar.session_date)
        ).all()

    points = tuple(
        BenchmarkPoint(
            session_date=bar.session_date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            source_identifier=source.source_identifier,
            source_checksum=source.checksum,
            retrieved_at=source.retrieved_at,
        )
        for bar, source in rows
    )
    return BenchmarkSeries(
        benchmark_code=normalized_code,
        benchmark_name=rows[0][0].benchmark_name if rows else normalized_code,
        requested_start=start_date,
        requested_end=end_date,
        points=points,
        source_identifiers=tuple(sorted({point.source_identifier for point in points})),
        latest_session=points[-1].session_date if points else None,
        latest_retrieved_at=max((point.retrieved_at for point in points), default=None),
    )


def get_adjusted_price_series(
    isin: str,
    start_date: date,
    end_date: date,
    settings: Settings | None = None,
) -> PriceSeries:
    raw = get_price_series(isin, start_date, end_date, settings)
    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        action_rows = session.execute(
            select(CorporateAction, SourceRecord.source_identifier)
            .join(Instrument, Instrument.id == CorporateAction.instrument_id)
            .join(SourceRecord, SourceRecord.id == CorporateAction.source_record_id)
            .where(
                Instrument.isin == isin.strip().upper(),
                CorporateAction.ex_date <= end_date,
                CorporateAction.verification_status == "verified",
            )
            .order_by(CorporateAction.ex_date)
        ).all()

    applicable_actions = tuple(
        (action, source_identifier)
        for action, source_identifier in action_rows
        if action.action_type in {"split", "bonus"}
    )
    adjusted_points: list[PricePoint] = []
    for point in raw.points:
        factor = Decimal(1)
        for action, _ in applicable_actions:
            if action.ex_date <= point.session_date:
                continue
            if action.action_type == "split":
                assert action.ratio_numerator is not None
                assert action.ratio_denominator is not None
                factor *= action.ratio_denominator / action.ratio_numerator
            elif action.action_type == "bonus":
                assert action.ratio_numerator is not None
                assert action.ratio_denominator is not None
                factor *= action.ratio_denominator / (
                    action.ratio_numerator + action.ratio_denominator
                )
        adjusted_points.append(
            replace(
                point,
                open=(point.open * factor).quantize(Decimal("0.0001")),
                high=(point.high * factor).quantize(Decimal("0.0001")),
                low=(point.low * factor).quantize(Decimal("0.0001")),
                close=(point.close * factor).quantize(Decimal("0.0001")),
                previous_close=(point.previous_close * factor).quantize(Decimal("0.0001")),
                volume=int((Decimal(point.volume) / factor).to_integral_value()),
                is_adjusted=bool(applicable_actions),
            )
        )
    sources = tuple(sorted({source_identifier for _, source_identifier in action_rows}))
    return replace(
        raw,
        points=tuple(adjusted_points),
        adjustment_status=(
            "adjusted_split_bonus"
            if raw.points and applicable_actions
            else raw.adjustment_status
        ),
        corporate_action_count=len(action_rows),
        corporate_action_sources=sources,
    )


def get_technical_snapshot(
    isin: str,
    as_of: date,
    settings: Settings | None = None,
) -> TechnicalSnapshot:
    from investment_gini.technical import calculate_technical_snapshot

    history_start = as_of - timedelta(days=550)
    series = get_adjusted_price_series(isin, history_start, as_of, settings)
    benchmark = get_benchmark_series("NIFTY_200", history_start, as_of, settings)
    return calculate_technical_snapshot(series, as_of, benchmark)


def get_members(
    universe_name: str, as_of: date, settings: Settings | None = None
) -> tuple[MemberView, ...]:
    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        instruments = UniverseRepository(session).members_as_of(universe_name, as_of)
        return tuple(
            MemberView(
                company_name=instrument.company_name,
                isin=instrument.isin,
                exchange=instrument.exchange,
                sector=instrument.sector,
                industry=instrument.industry,
            )
            for instrument in instruments
        )


def get_dashboard_snapshot(settings: Settings | None = None) -> DashboardSnapshot:
    resolved = settings or load_settings()
    factory = create_session_factory(create_database_engine(resolved.app.database_url))
    with session_scope(factory) as session:
        instrument_count = session.scalar(select(func.count()).select_from(Instrument)) or 0
        price_coverage = session.execute(
            select(
                func.count(PriceBar.id),
                func.count(func.distinct(PriceBar.session_date)),
                func.min(PriceBar.session_date),
                func.max(PriceBar.session_date),
                func.sum(PriceBar.is_adjusted),
            )
        ).one()
        source_names = tuple(session.scalars(select(DataSource.name).order_by(DataSource.name)))
        versions = tuple(
            session.execute(
                select(Universe.name, Universe.version).order_by(Universe.name, Universe.version)
            ).tuples()
        )
        quality_count = (
            session.scalar(
                select(func.count())
                .select_from(DataQualityFlag)
                .where(DataQualityFlag.status == "open")
            )
            or 0
        )

    return DashboardSnapshot(
        instrument_count=instrument_count,
        price_bar_count=price_coverage[0] or 0,
        price_session_count=price_coverage[1] or 0,
        price_first_session=price_coverage[2],
        price_last_session=price_coverage[3],
        adjusted_price_bar_count=price_coverage[4] or 0,
        data_sources=source_names,
        universe_versions=tuple(f"{name} / {version}" for name, version in versions),
        open_quality_flags=quality_count,
    )
