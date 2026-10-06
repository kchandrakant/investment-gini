from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from investment_gini.database import create_database_engine, create_session_factory, session_scope
from investment_gini.domain import (
    BenchmarkBarRecord,
    Exchange,
    PriceBarRecord,
    UniverseMembershipRecord,
)
from investment_gini.ingestion import (
    BenchmarkIngestionService,
    PriceIngestionService,
    UniverseIngestionService,
)
from investment_gini.models import (
    Base,
    BenchmarkBar,
    DataQualityFlag,
    IngestionRun,
    PriceBar,
    SourceRecord,
    UniverseMembership,
)
from investment_gini.providers import BenchmarkBatch, CsvUniverseProvider, PriceBatch, UniverseBatch
from investment_gini.repositories import UniverseRepository

FIXTURE = Path("tests/fixtures/universe.csv")


def test_csv_provider_reports_malformed_row(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.csv"
    malformed.write_text(
        "universe,universe_version,symbol,isin,company_name,exchange,effective_from,"
        "effective_to,sector,industry\n"
        "NIFTY 200,v1,BAD,,Bad Company,NSE,2024-01-01,,,\n",
        encoding="utf-8",
    )

    batch = CsvUniverseProvider().fetch_memberships(malformed)

    assert not batch.records
    assert len(batch.issues) == 1
    assert "missing values: isin" in batch.issues[0].reason


def test_ingestion_is_temporal_idempotent_and_traceable(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    batch = CsvUniverseProvider().fetch_memberships(FIXTURE)

    with session_scope(factory) as session:
        first = UniverseIngestionService(session).ingest(batch)
    with session_scope(factory) as session:
        second = UniverseIngestionService(session).ingest(batch)

    assert (first.inserted, first.skipped, first.quality_flags) == (3, 0, 0)
    assert (second.inserted, second.skipped, second.quality_flags) == (0, 3, 0)

    with session_scope(factory) as session:
        repository = UniverseRepository(session)
        historical = repository.members_as_of("NIFTY 200", date(2023, 6, 1))
        current = repository.members_as_of("NIFTY 200", date(2024, 6, 1))
        membership_count = session.scalar(select(func.count()).select_from(UniverseMembership))
        traced_count = session.scalar(
            select(func.count())
            .select_from(UniverseMembership)
            .join(
                SourceRecord,
                SourceRecord.id == UniverseMembership.source_record_id,
            )
            .join(IngestionRun)
        )

    assert [item.company_name for item in historical] == ["Legacy Consumer"]
    assert [item.company_name for item in current] == ["Alpha Industries", "Beta Financial"]
    assert membership_count == 3
    assert traced_count == 3


def test_overlapping_membership_creates_quality_flag(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    provider = CsvUniverseProvider()
    batch = provider.fetch_memberships(FIXTURE)
    original = batch.records[0]
    overlap = UniverseMembershipRecord(
        universe=original.universe,
        universe_version=original.universe_version,
        symbol=original.symbol,
        isin=original.isin,
        company_name=original.company_name,
        exchange=Exchange.NSE,
        sector=original.sector,
        industry=original.industry,
        effective_from=date(2024, 2, 1),
        effective_to=None,
        source=original.source,
    )

    with session_scope(factory) as session:
        UniverseIngestionService(session).ingest(batch)
    with session_scope(factory) as session:
        summary = UniverseIngestionService(session).ingest(
            UniverseBatch(records=(overlap,), issues=(), source=overlap.source)
        )
        flag_count = session.scalar(select(func.count()).select_from(DataQualityFlag))

    assert summary.inserted == 0
    assert summary.quality_flags == 1
    assert flag_count == 1


def test_complete_snapshot_reconciles_members_prospectively(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    first = CsvUniverseProvider().fetch_memberships(FIXTURE)
    active = first.records[:2]
    snapshot_date = date(2024, 10, 1)
    unchanged = UniverseMembershipRecord(
        **{
            **active[0].__dict__,
            "universe_version": snapshot_date.isoformat(),
            "effective_from": snapshot_date,
        }
    )
    addition = UniverseMembershipRecord(
        **{
            **active[1].__dict__,
            "universe_version": snapshot_date.isoformat(),
            "symbol": "GAMMA",
            "isin": "INE003A01004",
            "company_name": "Gamma Technology",
            "effective_from": snapshot_date,
        }
    )
    snapshot = UniverseBatch(
        records=(unchanged, addition),
        issues=(),
        source=first.source,
        is_complete_snapshot=True,
    )

    with session_scope(factory) as session:
        UniverseIngestionService(session).ingest(first)
    with session_scope(factory) as session:
        summary = UniverseIngestionService(session).ingest(snapshot)
    with session_scope(factory) as session:
        memberships = list(
            session.scalars(
                select(UniverseMembership).order_by(UniverseMembership.effective_from)
            )
        )
        repository = UniverseRepository(session)
        before = repository.members_as_of("NIFTY 200", date(2024, 9, 30))
        after = repository.members_as_of("NIFTY 200", snapshot_date)

    removed = next(item for item in memberships if item.instrument_id == 2)
    assert (summary.inserted, summary.skipped, summary.quality_flags) == (1, 1, 0)
    assert removed.effective_to == date(2024, 9, 30)
    assert removed.ended_by_source_record_id is not None
    assert [item.company_name for item in before] == ["Alpha Industries", "Beta Financial"]
    assert [item.company_name for item in after] == ["Alpha Industries", "Gamma Technology"]


def test_price_ingestion_is_idempotent_and_traceable(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    universe_batch = CsvUniverseProvider().fetch_memberships(FIXTURE)
    source = universe_batch.source
    universe_record = universe_batch.records[0]
    price_record = PriceBarRecord(
        isin=universe_record.isin,
        symbol=universe_record.symbol,
        session_date=date(2026, 9, 2),
        series="EQ",
        open=Decimal("100.10"),
        high=Decimal("105.00"),
        low=Decimal("99.50"),
        close=Decimal("103.25"),
        previous_close=Decimal("100.00"),
        volume=1_000,
        traded_value=Decimal("103250.00"),
        trade_count=42,
        source=source,
    )
    batch = PriceBatch(records=(price_record,), issues=(), source=source)

    with session_scope(factory) as session:
        UniverseIngestionService(session).ingest(universe_batch)
    with session_scope(factory) as session:
        first = PriceIngestionService(session).ingest(batch)
    with session_scope(factory) as session:
        second = PriceIngestionService(session).ingest(batch)
    with session_scope(factory) as session:
        bars = list(session.scalars(select(PriceBar)).all())

    assert (first.inserted, first.skipped) == (1, 0)
    assert (second.inserted, second.skipped) == (0, 1)
    assert len(bars) == 1
    assert bars[0].close == Decimal("103.2500")
    assert not bars[0].is_adjusted


def test_benchmark_ingestion_is_idempotent_and_traceable(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    source = CsvUniverseProvider().fetch_memberships(FIXTURE).source
    record = BenchmarkBarRecord(
        benchmark_code="NIFTY_200",
        benchmark_name="Nifty 200",
        session_date=date(2026, 1, 30),
        open=Decimal("14061.50"),
        high=Decimal("14117.05"),
        low=Decimal("14019.40"),
        close=Decimal("14093.05"),
        source=source,
    )
    batch = BenchmarkBatch(records=(record,), issues=(), source=source)

    with session_scope(factory) as session:
        first = BenchmarkIngestionService(session).ingest(batch)
    with session_scope(factory) as session:
        second = BenchmarkIngestionService(session).ingest(batch)
    with session_scope(factory) as session:
        bars = list(session.scalars(select(BenchmarkBar)).all())

    assert (first.inserted, first.skipped, first.quality_flags) == (1, 0, 0)
    assert (second.inserted, second.skipped, second.quality_flags) == (0, 1, 0)
    assert len(bars) == 1
    assert bars[0].close == Decimal("14093.0500")