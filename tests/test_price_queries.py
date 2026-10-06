from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from investment_gini.application import (
    get_latest_nifty200_as_of,
    get_price_series,
    search_nifty200_instruments,
)
from investment_gini.config import AppConfig, load_settings
from investment_gini.database import create_database_engine, create_session_factory, session_scope
from investment_gini.domain import PriceBarRecord, SourceMetadata
from investment_gini.ingestion import PriceIngestionService, UniverseIngestionService
from investment_gini.models import Base
from investment_gini.providers import CsvUniverseProvider, PriceBatch, ProviderIssue

FIXTURE = Path("tests/fixtures/universe.csv")


def _seed_prices(tmp_path: Path):  # type: ignore[no-untyped-def]
    settings = load_settings().model_copy(
        update={"app": AppConfig(database_url=f"sqlite:///{tmp_path / 'test.db'}")}
    )
    engine = create_database_engine(settings.app.database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    universe_batch = CsvUniverseProvider().fetch_memberships(FIXTURE)
    with session_scope(factory) as session:
        UniverseIngestionService(session).ingest(universe_batch)

    source = SourceMetadata(
        provider="nse_bhavcopy",
        source_identifier="https://example.test/bhavcopy-20240603.zip",
        retrieved_at=datetime(2024, 6, 4, 8, 30, tzinfo=UTC),
        checksum="a" * 64,
    )
    records = tuple(
        PriceBarRecord(
            isin="INE000A01001",
            symbol="ALPHA",
            session_date=session_date,
            series="EQ",
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=close,
            previous_close=Decimal("100"),
            volume=1_000,
            traded_value=Decimal("103000"),
            trade_count=42,
            source=source,
        )
        for session_date, close in (
            (date(2024, 6, 3), Decimal("103")),
            (date(2024, 6, 4), Decimal("104")),
        )
    )
    with session_scope(factory) as session:
        PriceIngestionService(session).ingest(
            PriceBatch(
                records=records,
                issues=(
                    ProviderIssue(
                        row_number=1,
                        field_name="ISIN",
                        reason="requested EQ ISIN not found",
                        observed_value="INE001A01002",
                    ),
                ),
                source=source,
            )
        )
    return settings


def test_instrument_search_matches_company_symbol_and_isin(tmp_path: Path) -> None:
    settings = _seed_prices(tmp_path)

    assert get_latest_nifty200_as_of(settings) == date(2024, 1, 1)
    by_company = search_nifty200_instruments("alpha", date(2024, 6, 1), settings)
    by_symbol = search_nifty200_instruments("BETA", date(2024, 6, 1), settings)
    by_isin = search_nifty200_instruments("INE000A01001", date(2024, 6, 1), settings)

    assert [(item.symbol, item.company_name) for item in by_company] == [
        ("ALPHA", "Alpha Industries")
    ]
    assert [item.symbol for item in by_symbol] == ["BETA"]
    assert [item.isin for item in by_isin] == ["INE000A01001"]


def test_price_series_is_bounded_traceable_and_explicitly_raw(tmp_path: Path) -> None:
    settings = _seed_prices(tmp_path)

    series = get_price_series(
        "INE000A01001", date(2024, 6, 4), date(2024, 6, 4), settings
    )

    assert series.instrument.symbol == "ALPHA"
    assert [point.session_date for point in series.points] == [date(2024, 6, 4)]
    assert series.points[0].close == Decimal("104.0000")
    assert series.adjustment_status == "raw_unadjusted"
    assert series.latest_session == date(2024, 6, 4)
    assert series.latest_retrieved_at == datetime(2024, 6, 4, 8, 30)
    assert series.source_names == ("nse_bhavcopy",)
    assert series.source_identifiers == ("https://example.test/bhavcopy-20240603.zip",)
    assert series.quality_warnings == ()


def test_price_series_returns_relevant_missing_instrument_warning(tmp_path: Path) -> None:
    settings = _seed_prices(tmp_path)

    series = get_price_series(
        "INE001A01002", date(2024, 6, 3), date(2024, 6, 4), settings
    )

    assert series.points == ()
    assert len(series.quality_warnings) == 1
    assert series.quality_warnings[0].reason == "requested EQ ISIN not found"


def test_price_series_rejects_reversed_date_range(tmp_path: Path) -> None:
    settings = _seed_prices(tmp_path)

    with pytest.raises(ValueError, match="end date must not precede start date"):
        get_price_series("INE000A01001", date(2024, 6, 4), date(2024, 6, 3), settings)