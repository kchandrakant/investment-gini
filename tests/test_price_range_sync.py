from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from investment_gini.application import get_nifty200_price_coverage, sync_nifty200_price_range
from investment_gini.config import AppConfig, load_settings
from investment_gini.database import create_database_engine, create_session_factory, session_scope
from investment_gini.domain import PriceBarRecord, SourceMetadata
from investment_gini.ingestion import UniverseIngestionService
from investment_gini.models import Base
from investment_gini.providers import (
    CsvUniverseProvider,
    NseArchiveUnavailableError,
    NseBhavcopyProvider,
    PriceBatch,
    ProviderIssue,
)

FIXTURE = Path("tests/fixtures/universe.csv")


def _settings(tmp_path: Path):  # type: ignore[no-untyped-def]
    settings = load_settings()
    return settings.model_copy(
        update={"app": AppConfig(database_url=f"sqlite:///{tmp_path / 'test.db'}")}
    )


def _seed_universe(tmp_path: Path):  # type: ignore[no-untyped-def]
    settings = _settings(tmp_path)
    engine = create_database_engine(settings.app.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        UniverseIngestionService(session).ingest(
            CsvUniverseProvider().fetch_memberships(FIXTURE)
        )
    return settings


def _source(session_date: date) -> SourceMetadata:
    return SourceMetadata(
        provider="nse_bhavcopy",
        source_identifier=f"fixture://{session_date.isoformat()}",
        retrieved_at=datetime(2026, 9, 3, tzinfo=UTC),
        checksum=session_date.strftime("%Y%m%d").ljust(64, "0"),
    )


def _record(isin: str, session_date: date, source: SourceMetadata) -> PriceBarRecord:
    return PriceBarRecord(
        isin=isin,
        symbol=isin[-4:],
        session_date=session_date,
        series="EQ",
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("103"),
        previous_close=Decimal("100"),
        volume=1_000,
        traded_value=Decimal("103000"),
        trade_count=42,
        source=source,
    )


class StubProvider(NseBhavcopyProvider):
    def __init__(self, unavailable_dates: set[date] | None = None) -> None:
        self.calls: list[tuple[date, set[str]]] = []
        self.unavailable_dates = unavailable_dates or set()

    def fetch_prices(self, session_date: date, requested_isins: set[str]) -> PriceBatch:
        self.calls.append((session_date, requested_isins))
        if session_date in self.unavailable_dates:
            raise NseArchiveUnavailableError("fixture archive unavailable")
        source = _source(session_date)
        return PriceBatch(
            records=tuple(_record(isin, session_date, source) for isin in requested_isins),
            issues=(),
            source=source,
        )


def test_range_sync_skips_weekends_and_continues_after_missing_archive(tmp_path: Path) -> None:
    settings = _seed_universe(tmp_path)
    provider = StubProvider(unavailable_dates={date(2024, 6, 10)})

    summary = sync_nifty200_price_range(
        date(2024, 6, 7),
        date(2024, 6, 10),
        date(2024, 6, 1),
        settings,
        provider,
    )

    assert summary.sessions_ingested == 1
    assert summary.weekends_skipped == 2
    assert summary.archives_unavailable == 1
    assert summary.sessions_failed == 0
    assert summary.bars_inserted == 2
    assert [call[0] for call in provider.calls] == [date(2024, 6, 7), date(2024, 6, 10)]


def test_range_sync_resumes_only_missing_instruments(tmp_path: Path) -> None:
    settings = _seed_universe(tmp_path)
    session_date = date(2024, 6, 7)
    initial_source = _source(session_date)
    partial_provider = StubProvider()
    requested_isins: set[str] = set()

    def partial_fetch(date_value: date, isins: set[str]) -> PriceBatch:
        requested_isins.update(isins)
        retained = sorted(isins)[:1]
        missing = sorted(isins)[1]
        return PriceBatch(
            records=tuple(_record(isin, date_value, initial_source) for isin in retained),
            issues=(ProviderIssue(1, "ISIN", "requested EQ ISIN not found", missing),),
            source=initial_source,
        )

    partial_provider.fetch_prices = partial_fetch  # type: ignore[method-assign]
    first = sync_nifty200_price_range(
        session_date, session_date, date(2024, 6, 1), settings, partial_provider
    )
    partial_coverage = get_nifty200_price_coverage(date(2024, 6, 1), settings)
    resume_provider = StubProvider()
    second = sync_nifty200_price_range(
        session_date, session_date, date(2024, 6, 1), settings, resume_provider
    )
    third = sync_nifty200_price_range(
        session_date, session_date, date(2024, 6, 1), settings, resume_provider
    )

    assert first.bars_inserted == 1
    assert first.quality_flags == 1
    assert first.incomplete_sessions == 1
    assert first.outcomes[0].missing_isins == (sorted(requested_isins)[1],)
    assert partial_coverage.total_sessions == 1
    assert partial_coverage.complete_sessions == 0
    assert partial_coverage.incomplete_sessions == 1
    assert partial_coverage.instrument_gaps[0].missing_sessions == 1
    assert len(requested_isins) == 2
    assert second.bars_inserted == 1
    assert len(resume_provider.calls[0][1]) == 1
    assert third.sessions_already_complete == 1
    assert len(resume_provider.calls) == 1


def test_range_sync_delays_only_between_archive_requests(tmp_path: Path) -> None:
    settings = _seed_universe(tmp_path)
    provider = StubProvider()
    delays: list[float] = []

    summary = sync_nifty200_price_range(
        date(2024, 6, 7),
        date(2024, 6, 11),
        date(2024, 6, 1),
        settings,
        provider,
        request_delay_seconds=1.5,
        sleep=delays.append,
    )

    assert summary.sessions_ingested == 3
    assert summary.weekends_skipped == 2
    assert delays == [1.5, 1.5]