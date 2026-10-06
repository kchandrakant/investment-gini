from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from investment_gini.application import get_fundamental_facts_as_of
from investment_gini.config import load_settings
from investment_gini.database import create_database_engine, create_session_factory, session_scope
from investment_gini.domain import (
    DataStatus,
    FundamentalFactRecord,
    MetricDefinitionRecord,
    SourceMetadata,
)
from investment_gini.ingestion import FundamentalIngestionService, UniverseIngestionService
from investment_gini.models import Base, FundamentalFact
from investment_gini.providers import (
    CsvFundamentalProvider,
    CsvUniverseProvider,
    FundamentalBatch,
)

FIXTURE = Path("tests/fixtures/universe.csv")


def _source(identifier: str) -> SourceMetadata:
    return SourceMetadata(
        provider="filing_fixture",
        source_identifier=identifier,
        retrieved_at=datetime(2026, 9, 28, tzinfo=UTC),
        checksum=identifier.encode().hex().ljust(64, "0")[:64],
        source_class="official_filing",
        reliability_tier=1,
        terms_reference="fixture://terms",
        source_artifact_checksum="b" * 64,
    )


def test_restatement_is_linked_without_overwriting_original_fact(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    universe = CsvUniverseProvider().fetch_memberships(FIXTURE)
    isin = universe.records[0].isin
    definition = MetricDefinitionRecord(
        code="revenue",
        version="ifrs-v1",
        name="Revenue",
        description="Reported consolidated revenue.",
        unit="INR",
        period_type="duration",
        value_kind="monetary",
        formula=None,
        is_derived=False,
    )
    original_source = _source("fixture://original")
    restated_source = _source("fixture://restated")
    original = FundamentalFactRecord(
        isin=isin,
        metric_code="revenue",
        metric_version="ifrs-v1",
        period_start=date(2025, 4, 1),
        period_end=date(2026, 3, 31),
        filing_date=date(2026, 5, 20),
        available_at=datetime(2026, 5, 20, 12, tzinfo=UTC),
        consolidation_scope="consolidated",
        value=Decimal("1000000"),
        status=DataStatus.AVAILABLE,
        currency="INR",
        reported_unit="INR crore",
        source=original_source,
    )
    restated = FundamentalFactRecord(
        **{
            **original.__dict__,
            "filing_date": date(2026, 8, 1),
            "available_at": datetime(2026, 8, 1, 12, tzinfo=UTC),
            "value": Decimal("1100000"),
            "source": restated_source,
        }
    )

    with session_scope(factory) as session:
        UniverseIngestionService(session).ingest(universe)
    with session_scope(factory) as session:
        first = FundamentalIngestionService(session).ingest(
            FundamentalBatch((definition,), (original,), (), original_source)
        )
    with session_scope(factory) as session:
        second = FundamentalIngestionService(session).ingest(
            FundamentalBatch((definition,), (restated,), (), restated_source)
        )
    with session_scope(factory) as session:
        repeated = FundamentalIngestionService(session).ingest(
            FundamentalBatch((definition,), (restated,), (), restated_source)
        )
    conflicting = FundamentalFactRecord(
        **{**restated.__dict__, "value": Decimal("1200000")}
    )
    with session_scope(factory) as session:
        conflict = FundamentalIngestionService(session).ingest(
            FundamentalBatch((definition,), (conflicting,), (), restated_source)
        )
    with session_scope(factory) as session:
        facts = list(
            session.scalars(select(FundamentalFact).order_by(FundamentalFact.available_at))
        )

    settings = load_settings()
    settings.app.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    before_restatement = get_fundamental_facts_as_of(
        isin, datetime(2026, 7, 1, tzinfo=UTC), settings
    )
    after_restatement = get_fundamental_facts_as_of(
        isin, datetime(2026, 9, 1, tzinfo=UTC), settings
    )

    assert (first.inserted, first.quality_flags) == (1, 0)
    assert (second.inserted, second.quality_flags) == (1, 0)
    assert (repeated.inserted, repeated.skipped, repeated.quality_flags) == (0, 1, 0)
    assert (conflict.inserted, conflict.skipped, conflict.quality_flags) == (0, 1, 1)
    assert [fact.value for fact in facts] == [
        Decimal("1000000.00000000"),
        Decimal("1100000.00000000"),
    ]
    assert facts[0].supersedes_fact_id is None
    assert facts[1].supersedes_fact_id == facts[0].id
    assert before_restatement[0].value == Decimal("1000000.00000000")
    assert before_restatement[0].source_identifier == "fixture://original"
    assert before_restatement[0].unit == "INR crore"
    assert after_restatement[0].value == Decimal("1100000.00000000")
    assert after_restatement[0].source_identifier == "fixture://restated"
    assert after_restatement[0].source_artifact_checksum == "b" * 64


def test_manual_filing_csv_requires_and_preserves_filing_evidence(tmp_path: Path) -> None:
    path = tmp_path / "facts.csv"
    path.write_text(
        "isin,metric_code,period_start,period_end,filing_date,available_at,"
        "consolidation_scope,value,status,currency,reported_unit\n"
        "INE000A01001,revenue,2025-04-01,2026-03-31,2026-05-20,"
        "2026-05-20T12:00:00+05:30,consolidated,1234,available,INR,INR crore\n"
        "INE000A01001,total_assets,,2026-03-31,2026-05-20,"
        "2026-05-20T12:00:00+05:30,consolidated,,unknown,INR,INR lakh\n",
        encoding="utf-8",
    )

    batch = CsvFundamentalProvider().fetch_facts(
        path,
        "Issuer annual report",
        "https://issuer.example/annual-report.pdf",
        "issuer-document-terms",
        "a" * 64,
    )

    assert len(batch.records) == 2
    assert not batch.issues
    assert batch.source.source_identifier == "https://issuer.example/annual-report.pdf"
    assert batch.source.checksum != batch.source.source_artifact_checksum
    assert batch.source.source_artifact_checksum == "a" * 64
    assert batch.records[0].reported_unit == "INR crore"
    assert batch.records[1].period_start == batch.records[1].period_end
    assert batch.records[1].value is None
    assert batch.records[1].status is DataStatus.UNKNOWN