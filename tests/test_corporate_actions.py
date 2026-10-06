from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from investment_gini.application import (
    get_adjusted_price_series,
    get_nifty200_membership_coverage,
    get_price_series,
    import_corporate_actions_csv,
)
from investment_gini.config import AppConfig, load_settings
from investment_gini.database import create_database_engine, create_session_factory, session_scope
from investment_gini.domain import PriceBarRecord, SourceMetadata
from investment_gini.ingestion import PriceIngestionService, UniverseIngestionService
from investment_gini.models import Base
from investment_gini.providers import CsvUniverseProvider, PriceBatch

UNIVERSE_FIXTURE = Path("tests/fixtures/universe.csv")


def _seed_database(tmp_path: Path):  # type: ignore[no-untyped-def]
    settings = load_settings().model_copy(
        update={"app": AppConfig(database_url=f"sqlite:///{tmp_path / 'test.db'}")}
    )
    engine = create_database_engine(settings.app.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        UniverseIngestionService(session).ingest(
            CsvUniverseProvider().fetch_memberships(UNIVERSE_FIXTURE)
        )

    source = SourceMetadata(
        provider="nse_bhavcopy",
        source_identifier="https://example.test/bhavcopy.zip",
        retrieved_at=datetime(2024, 6, 6, tzinfo=UTC),
        checksum="a" * 64,
    )
    records = tuple(
        PriceBarRecord(
            isin="INE000A01001",
            symbol="ALPHA",
            session_date=session_date,
            series="EQ",
            open=close,
            high=close,
            low=close,
            close=close,
            previous_close=close,
            volume=1_000,
            traded_value=close * 1_000,
            trade_count=10,
            source=source,
        )
        for session_date, close in (
            (date(2024, 6, 3), Decimal("100")),
            (date(2024, 6, 4), Decimal("52")),
        )
    )
    with session_scope(factory) as session:
        PriceIngestionService(session).ingest(PriceBatch(records, (), source))
    return settings


def test_split_ingestion_is_idempotent_and_adjustment_preserves_raw_prices(
    tmp_path: Path,
) -> None:
    settings = _seed_database(tmp_path)
    csv_path = tmp_path / "corporate-actions.csv"
    csv_path.write_text(
        "isin,action_type,ex_date,record_date,ratio_numerator,ratio_denominator,"
        "cash_amount,currency,verification_status\n"
        "INE000A01001,split,2024-06-04,2024-06-05,2,1,,,verified\n",
        encoding="utf-8",
    )

    first = import_corporate_actions_csv(
        csv_path,
        source_name="licensed_actions",
        terms_reference="https://example.test/licence",
        settings=settings,
    )
    second = import_corporate_actions_csv(
        csv_path,
        source_name="licensed_actions",
        terms_reference="https://example.test/licence",
        settings=settings,
    )

    assert (first.inserted, first.quality_flags) == (1, 0)
    assert (second.inserted, second.skipped) == (0, 1)
    raw = get_price_series(
        "INE000A01001", date(2024, 6, 3), date(2024, 6, 4), settings
    )
    adjusted = get_adjusted_price_series(
        "INE000A01001", date(2024, 6, 3), date(2024, 6, 4), settings
    )

    assert [point.close for point in raw.points] == [Decimal("100.0000"), Decimal("52.0000")]
    assert [point.close for point in adjusted.points] == [
        Decimal("50.0000"),
        Decimal("52.0000"),
    ]
    assert [point.volume for point in adjusted.points] == [2_000, 1_000]
    assert adjusted.adjustment_status == "adjusted_split_bonus"
    assert adjusted.corporate_action_count == 1


def test_membership_coverage_exposes_unsupported_historical_range(tmp_path: Path) -> None:
    settings = _seed_database(tmp_path)

    coverage = get_nifty200_membership_coverage(
        date(2022, 12, 1), date(2024, 6, 4), settings
    )

    assert coverage.snapshot_count == 2
    assert coverage.first_snapshot == date(2023, 1, 1)
    assert coverage.is_point_in_time_covered is False
    assert coverage.uncovered_start == date(2022, 12, 1)