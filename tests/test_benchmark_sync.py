from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from investment_gini.application import get_benchmark_series, sync_nifty200_benchmark
from investment_gini.config import AppConfig, load_settings
from investment_gini.database import create_database_engine
from investment_gini.domain import BenchmarkBarRecord, SourceMetadata
from investment_gini.models import Base
from investment_gini.providers import BenchmarkBatch, NiftyHistoricalIndexProvider


def _settings(tmp_path: Path):  # type: ignore[no-untyped-def]
    settings = load_settings()
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    Base.metadata.create_all(create_database_engine(database_url))
    return settings.model_copy(update={"app": AppConfig(database_url=database_url)})


class StubProvider(NiftyHistoricalIndexProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[date, date]] = []

    def fetch_benchmark(
        self, benchmark_name: str, start_date: date, end_date: date
    ) -> BenchmarkBatch:
        self.calls.append((start_date, end_date))
        source = SourceMetadata(
            provider="nifty_historical_index",
            source_identifier=f"fixture://{start_date}:{end_date}",
            retrieved_at=datetime(2026, 2, 1, tzinfo=UTC),
            checksum=start_date.isoformat().replace("-", "").ljust(64, "0"),
            source_class="official_endpoint",
            reliability_tier=1,
            terms_reference="https://www.niftyindices.com/terms-of-use",
        )
        record = BenchmarkBarRecord(
            benchmark_code="NIFTY_200",
            benchmark_name=benchmark_name,
            session_date=start_date,
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=Decimal("103"),
            source=source,
        )
        return BenchmarkBatch((record,), (), source)


def test_sync_chunks_official_requests_and_query_preserves_provenance(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    provider = StubProvider()
    delays: list[float] = []

    summary = sync_nifty200_benchmark(
        date(2024, 1, 1),
        date(2025, 1, 2),
        settings,
        provider,
        request_delay_seconds=1.5,
        sleep=delays.append,
    )
    series = get_benchmark_series(
        "NIFTY_200", date(2024, 1, 1), date(2025, 1, 2), settings
    )

    assert provider.calls == [
        (date(2024, 1, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 1, 2)),
    ]
    assert delays == [1.5]
    assert (summary.requests, summary.bars_inserted, summary.quality_flags) == (2, 2, 0)
    assert [point.session_date for point in series.points] == [
        date(2024, 1, 1),
        date(2025, 1, 1),
    ]
    assert series.source_identifiers == (
        "fixture://2024-01-01:2024-12-31",
        "fixture://2025-01-01:2025-01-02",
    )