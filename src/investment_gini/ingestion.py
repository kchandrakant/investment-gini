from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    BenchmarkBatch,
    CorporateActionBatch,
    FundamentalBatch,
    PriceBatch,
    UniverseBatch,
)
from investment_gini.repositories import UniverseRepository


@dataclass(frozen=True)
class IngestionSummary:
    run_id: int
    inserted: int
    skipped: int
    quality_flags: int


class UniverseIngestionService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repository = UniverseRepository(session)

    def ingest(self, batch: UniverseBatch) -> IngestionSummary:
        data_source = self._get_or_create_source(batch)
        run = IngestionRun(
            data_source_id=data_source.id,
            requested_range=None,
            started_at=datetime.now(UTC),
            status="running",
        )
        self._session.add(run)
        self._session.flush()

        source_record = SourceRecord(
            ingestion_run_id=run.id,
            source_identifier=batch.source.source_identifier,
            retrieved_at=batch.source.retrieved_at,
            checksum=batch.source.checksum,
        )
        self._session.add(source_record)
        self._session.flush()

        quality_flags = self._record_provider_issues(run.id, batch)
        inserted = 0
        skipped = 0
        unchanged_isins: set[str] = set()
        if batch.is_complete_snapshot and not batch.issues:
            unchanged_isins = self._reconcile_complete_snapshot(batch, source_record)

        for record in batch.records:
            instrument = self._get_or_create_instrument(record)
            universe = self._get_or_create_universe(record.universe, record.universe_version)
            self._get_or_create_symbol(instrument, record)

            if record.isin in unchanged_isins:
                skipped += 1
                continue

            exact_membership = self._session.scalar(
                select(UniverseMembership).where(
                    UniverseMembership.universe_id == universe.id,
                    UniverseMembership.instrument_id == instrument.id,
                    UniverseMembership.effective_from == record.effective_from,
                    UniverseMembership.effective_to == record.effective_to,
                )
            )
            if exact_membership is not None:
                skipped += 1
                continue

            if self._repository.has_overlapping_membership(
                universe.id,
                instrument.id,
                record.effective_from,
                record.effective_to,
            ):
                self._session.add(
                    DataQualityFlag(
                        ingestion_run_id=run.id,
                        entity_type="universe_membership",
                        field_name="effective_range",
                        severity="error",
                        reason="membership interval overlaps an existing interval",
                        observed_value=f"{record.isin}:{record.effective_from}:{record.effective_to}",
                    )
                )
                quality_flags += 1
                skipped += 1
                continue

            self._session.add(
                UniverseMembership(
                    universe_id=universe.id,
                    instrument_id=instrument.id,
                    source_record_id=source_record.id,
                    effective_from=record.effective_from,
                    effective_to=record.effective_to,
                )
            )
            inserted += 1

        run.status = "completed_with_warnings" if quality_flags else "completed"
        run.ended_at = datetime.now(UTC)
        self._session.flush()
        return IngestionSummary(run.id, inserted, skipped, quality_flags)

    def _reconcile_complete_snapshot(
        self, batch: UniverseBatch, source_record: SourceRecord
    ) -> set[str]:
        names = {record.universe for record in batch.records}
        dates = {record.effective_from for record in batch.records}
        if len(names) != 1 or len(dates) != 1:
            raise ValueError(
                "complete universe snapshot requires one universe and one effective date"
            )
        universe_name = next(iter(names))
        snapshot_date = next(iter(dates))
        incoming_isins = {record.isin for record in batch.records}
        active = list(
            self._session.execute(
                select(UniverseMembership, Instrument.isin)
                .join(Universe, Universe.id == UniverseMembership.universe_id)
                .join(Instrument, Instrument.id == UniverseMembership.instrument_id)
                .where(
                    Universe.name == universe_name,
                    UniverseMembership.effective_to.is_(None),
                )
            ).all()
        )
        unchanged_isins: set[str] = set()
        for membership, isin in active:
            if membership.effective_from > snapshot_date:
                raise ValueError("complete universe snapshots must be ingested chronologically")
            if isin in incoming_isins:
                unchanged_isins.add(isin)
                continue
            membership.effective_to = snapshot_date - timedelta(days=1)
            membership.ended_by_source_record_id = source_record.id
        return unchanged_isins

    def _get_or_create_source(self, batch: UniverseBatch) -> DataSource:
        metadata = batch.source
        source = self._session.scalar(
            select(DataSource).where(DataSource.name == metadata.provider)
        )
        if source is None:
            source = DataSource(
                name=metadata.provider,
                source_class=metadata.source_class,
                reliability_tier=metadata.reliability_tier,
                terms_reference=metadata.terms_reference,
            )
            self._session.add(source)
            self._session.flush()
        return source

    def _get_or_create_instrument(self, record: object) -> Instrument:
        from investment_gini.domain import UniverseMembershipRecord

        assert isinstance(record, UniverseMembershipRecord)
        instrument = self._session.scalar(select(Instrument).where(Instrument.isin == record.isin))
        if instrument is None:
            instrument = Instrument(
                exchange=record.exchange.value,
                isin=record.isin,
                company_name=record.company_name,
                sector=record.sector,
                industry=record.industry,
            )
            self._session.add(instrument)
            self._session.flush()
        return instrument

    def _get_or_create_universe(self, name: str, version: str) -> Universe:
        universe = self._session.scalar(
            select(Universe).where(Universe.name == name, Universe.version == version)
        )
        if universe is None:
            universe = Universe(name=name, version=version)
            self._session.add(universe)
            self._session.flush()
        return universe

    def _get_or_create_symbol(self, instrument: Instrument, record: object) -> None:
        from investment_gini.domain import UniverseMembershipRecord

        assert isinstance(record, UniverseMembershipRecord)
        exists = self._session.scalar(
            select(InstrumentSymbol.id).where(
                InstrumentSymbol.instrument_id == instrument.id,
                InstrumentSymbol.exchange == record.exchange.value,
                InstrumentSymbol.symbol == record.symbol,
                InstrumentSymbol.effective_from == record.effective_from,
            )
        )
        if exists is None:
            self._session.add(
                InstrumentSymbol(
                    instrument_id=instrument.id,
                    exchange=record.exchange.value,
                    symbol=record.symbol,
                    effective_from=record.effective_from,
                    effective_to=record.effective_to,
                )
            )

    def _record_provider_issues(self, run_id: int, batch: UniverseBatch) -> int:
        for issue in batch.issues:
            self._session.add(
                DataQualityFlag(
                    ingestion_run_id=run_id,
                    entity_type="csv_row",
                    field_name=issue.field_name,
                    severity="error",
                    reason=issue.reason,
                    observed_value=issue.observed_value,
                )
            )
        return len(batch.issues)


class PriceIngestionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ingest(self, batch: PriceBatch) -> IngestionSummary:
        source = self._session.scalar(
            select(DataSource).where(DataSource.name == batch.source.provider)
        )
        if source is None:
            source = DataSource(
                name=batch.source.provider,
                source_class=batch.source.source_class,
                reliability_tier=batch.source.reliability_tier,
                terms_reference=batch.source.terms_reference,
            )
            self._session.add(source)
            self._session.flush()

        dates = {record.session_date for record in batch.records}
        requested_range = next(iter(dates)).isoformat() if len(dates) == 1 else None
        run = IngestionRun(
            data_source_id=source.id,
            requested_range=requested_range,
            started_at=datetime.now(UTC),
            status="running",
        )
        self._session.add(run)
        self._session.flush()
        source_record = SourceRecord(
            ingestion_run_id=run.id,
            source_identifier=batch.source.source_identifier,
            retrieved_at=batch.source.retrieved_at,
            checksum=batch.source.checksum,
            reported_period=requested_range,
        )
        self._session.add(source_record)
        self._session.flush()

        for issue in batch.issues:
            self._session.add(
                DataQualityFlag(
                    ingestion_run_id=run.id,
                    entity_type="price_bar",
                    field_name=issue.field_name,
                    severity="error",
                    reason=issue.reason,
                    observed_value=issue.observed_value,
                )
            )
        quality_flags = len(batch.issues)
        inserted = 0
        skipped = 0
        for record in batch.records:
            instrument = self._session.scalar(
                select(Instrument).where(Instrument.isin == record.isin)
            )
            if instrument is None:
                self._session.add(
                    DataQualityFlag(
                        ingestion_run_id=run.id,
                        entity_type="price_bar",
                        field_name="ISIN",
                        severity="error",
                        reason="price row references an unknown instrument",
                        observed_value=record.isin,
                    )
                )
                quality_flags += 1
                skipped += 1
                continue
            exists = self._session.scalar(
                select(PriceBar.id).where(
                    PriceBar.instrument_id == instrument.id,
                    PriceBar.session_date == record.session_date,
                    PriceBar.series == record.series,
                )
            )
            if exists is not None:
                skipped += 1
                continue
            self._session.add(
                PriceBar(
                    instrument_id=instrument.id,
                    source_record_id=source_record.id,
                    session_date=record.session_date,
                    series=record.series,
                    open=record.open,
                    high=record.high,
                    low=record.low,
                    close=record.close,
                    previous_close=record.previous_close,
                    volume=record.volume,
                    traded_value=record.traded_value,
                    trade_count=record.trade_count,
                    is_adjusted=record.is_adjusted,
                )
            )
            inserted += 1

        run.status = "completed_with_warnings" if quality_flags else "completed"
        run.ended_at = datetime.now(UTC)
        self._session.flush()
        return IngestionSummary(run.id, inserted, skipped, quality_flags)


class BenchmarkIngestionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ingest(self, batch: BenchmarkBatch) -> IngestionSummary:
        source = self._session.scalar(
            select(DataSource).where(DataSource.name == batch.source.provider)
        )
        if source is None:
            source = DataSource(
                name=batch.source.provider,
                source_class=batch.source.source_class,
                reliability_tier=batch.source.reliability_tier,
                terms_reference=batch.source.terms_reference,
            )
            self._session.add(source)
            self._session.flush()

        dates = {record.session_date for record in batch.records}
        requested_range = None
        if dates:
            requested_range = f"{min(dates).isoformat()}:{max(dates).isoformat()}"
        run = IngestionRun(
            data_source_id=source.id,
            requested_range=requested_range,
            started_at=datetime.now(UTC),
            status="running",
        )
        self._session.add(run)
        self._session.flush()
        source_record = SourceRecord(
            ingestion_run_id=run.id,
            source_identifier=batch.source.source_identifier,
            retrieved_at=batch.source.retrieved_at,
            checksum=batch.source.checksum,
            reported_period=requested_range,
        )
        self._session.add(source_record)
        self._session.flush()

        for issue in batch.issues:
            self._session.add(
                DataQualityFlag(
                    ingestion_run_id=run.id,
                    entity_type="benchmark_bar",
                    field_name=issue.field_name,
                    severity="error",
                    reason=issue.reason,
                    observed_value=issue.observed_value,
                )
            )
        quality_flags = len(batch.issues)
        inserted = 0
        skipped = 0
        for record in batch.records:
            exists = self._session.scalar(
                select(BenchmarkBar.id).where(
                    BenchmarkBar.benchmark_code == record.benchmark_code,
                    BenchmarkBar.session_date == record.session_date,
                )
            )
            if exists is not None:
                skipped += 1
                continue
            self._session.add(
                BenchmarkBar(
                    source_record_id=source_record.id,
                    benchmark_code=record.benchmark_code,
                    benchmark_name=record.benchmark_name,
                    session_date=record.session_date,
                    open=record.open,
                    high=record.high,
                    low=record.low,
                    close=record.close,
                )
            )
            inserted += 1

        run.status = "completed_with_warnings" if quality_flags else "completed"
        run.ended_at = datetime.now(UTC)
        self._session.flush()
        return IngestionSummary(run.id, inserted, skipped, quality_flags)


class FundamentalIngestionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ingest(self, batch: FundamentalBatch) -> IngestionSummary:
        source = self._session.scalar(
            select(DataSource).where(DataSource.name == batch.source.provider)
        )
        if source is None:
            source = DataSource(
                name=batch.source.provider,
                source_class=batch.source.source_class,
                reliability_tier=batch.source.reliability_tier,
                terms_reference=batch.source.terms_reference,
            )
            self._session.add(source)
            self._session.flush()
        run = IngestionRun(
            data_source_id=source.id,
            requested_range=None,
            started_at=datetime.now(UTC),
            status="running",
        )
        self._session.add(run)
        self._session.flush()
        source_record = SourceRecord(
            ingestion_run_id=run.id,
            source_identifier=batch.source.source_identifier,
            retrieved_at=batch.source.retrieved_at,
            checksum=batch.source.checksum,
            source_artifact_checksum=batch.source.source_artifact_checksum,
            available_at=min(
                (record.available_at for record in batch.records), default=None
            ),
        )
        self._session.add(source_record)
        self._session.flush()

        definitions: dict[tuple[str, str], MetricDefinition] = {}
        definition_conflicts = 0
        for definition_record in batch.definitions:
            definition = self._session.scalar(
                select(MetricDefinition).where(
                    MetricDefinition.code == definition_record.code,
                    MetricDefinition.version == definition_record.version,
                )
            )
            if definition is None:
                definition = MetricDefinition(
                    code=definition_record.code,
                    version=definition_record.version,
                    name=definition_record.name,
                    description=definition_record.description,
                    unit=definition_record.unit,
                    period_type=definition_record.period_type,
                    value_kind=definition_record.value_kind,
                    formula=definition_record.formula,
                    is_derived=definition_record.is_derived,
                )
                self._session.add(definition)
                self._session.flush()
            elif (
                definition.name != definition_record.name
                or definition.description != definition_record.description
                or definition.unit != definition_record.unit
                or definition.period_type != definition_record.period_type
                or definition.value_kind != definition_record.value_kind
                or definition.formula != definition_record.formula
                or definition.is_derived != definition_record.is_derived
            ):
                self._session.add(
                    DataQualityFlag(
                        ingestion_run_id=run.id,
                        entity_type="metric_definition",
                        field_name="version",
                        severity="error",
                        reason=(
                            "metric definition version is immutable and conflicts "
                            "with stored definition"
                        ),
                        observed_value=f"{definition_record.code}:{definition_record.version}",
                    )
                )
                definition_conflicts += 1
                continue
            definitions[(definition_record.code, definition_record.version)] = definition

        for issue in batch.issues:
            self._session.add(
                DataQualityFlag(
                    ingestion_run_id=run.id,
                    entity_type="fundamental_fact",
                    field_name=issue.field_name,
                    severity="error",
                    reason=issue.reason,
                    observed_value=issue.observed_value,
                )
            )
        quality_flags = len(batch.issues) + definition_conflicts
        inserted = 0
        skipped = 0
        for fact_record in sorted(batch.records, key=lambda item: item.available_at):
            instrument = self._session.scalar(
                select(Instrument).where(Instrument.isin == fact_record.isin)
            )
            definition = definitions.get(
                (fact_record.metric_code, fact_record.metric_version)
            )
            reason: str | None = None
            if instrument is None:
                reason = "fundamental fact references an unknown instrument"
            elif definition is None:
                reason = "fundamental fact references an unknown metric definition"
            elif fact_record.source != batch.source:
                reason = "fundamental fact source metadata differs from batch source"
            elif definition.is_derived:
                reason = "derived metrics cannot be ingested as raw fundamental facts"

            if reason is None and (
                fact_record.status.value in {"available", "estimated"}
                and fact_record.value is None
            ):
                reason = "available or estimated fundamental fact requires a numeric value"
            elif reason is None and (
                fact_record.status.value in {"unknown", "not_applicable", "stale"}
                and fact_record.value is not None
            ):
                reason = "unavailable fundamental fact cannot carry a numeric value"
            elif reason is None and fact_record.period_start is None:
                reason = "fundamental fact requires an explicit period start or instant date"
            if reason is None and definition is not None:
                if (
                    definition.period_type == "duration"
                    and fact_record.period_start is not None
                    and fact_record.period_start >= fact_record.period_end
                ):
                    reason = "duration metric period_start must precede period_end"
                elif (
                    definition.period_type == "instant"
                    and fact_record.period_start != fact_record.period_end
                ):
                    reason = "instant metric period_start must equal period_end"
            if reason is None and (
                fact_record.available_at.tzinfo is None
                or fact_record.available_at.utcoffset() is None
            ):
                reason = "fundamental fact availability timestamp requires a timezone"
            elif reason is None and fact_record.available_at.date() < fact_record.filing_date:
                reason = "fundamental fact availability cannot precede filing date"
            if reason is not None:
                self._session.add(
                    DataQualityFlag(
                        ingestion_run_id=run.id,
                        entity_type="fundamental_fact",
                        field_name="record",
                        severity="error",
                        reason=reason,
                        observed_value=(
                            f"{fact_record.isin}:{fact_record.metric_code}:"
                            f"{fact_record.period_end}"
                        ),
                    )
                )
                quality_flags += 1
                skipped += 1
                continue
            assert instrument is not None
            assert definition is not None
            existing_fact = self._session.scalar(
                select(FundamentalFact).where(
                    FundamentalFact.instrument_id == instrument.id,
                    FundamentalFact.metric_definition_id == definition.id,
                    FundamentalFact.period_start == fact_record.period_start,
                    FundamentalFact.period_end == fact_record.period_end,
                    FundamentalFact.consolidation_scope
                    == fact_record.consolidation_scope,
                    FundamentalFact.available_at == fact_record.available_at,
                )
            )
            if existing_fact is not None:
                if (
                    existing_fact.filing_date != fact_record.filing_date
                    or existing_fact.value != fact_record.value
                    or existing_fact.status != fact_record.status.value
                    or existing_fact.currency != fact_record.currency
                    or existing_fact.reported_unit != fact_record.reported_unit
                ):
                    self._session.add(
                        DataQualityFlag(
                            ingestion_run_id=run.id,
                            entity_type="fundamental_fact",
                            field_name="revision_identity",
                            severity="error",
                            reason=(
                                "conflicting fact content reuses an existing availability "
                                "timestamp and period identity"
                            ),
                            observed_value=(
                                f"{fact_record.isin}:{fact_record.metric_code}:"
                                f"{fact_record.period_start}:{fact_record.period_end}:"
                                f"{fact_record.available_at.isoformat()}"
                            ),
                        )
                    )
                    quality_flags += 1
                skipped += 1
                continue
            superseded = self._session.scalar(
                select(FundamentalFact)
                .where(
                    FundamentalFact.instrument_id == instrument.id,
                    FundamentalFact.metric_definition_id == definition.id,
                    FundamentalFact.period_start == fact_record.period_start,
                    FundamentalFact.period_end == fact_record.period_end,
                    FundamentalFact.consolidation_scope
                    == fact_record.consolidation_scope,
                    FundamentalFact.available_at < fact_record.available_at,
                )
                .order_by(FundamentalFact.available_at.desc())
                .limit(1)
            )
            self._session.add(
                FundamentalFact(
                    instrument_id=instrument.id,
                    metric_definition_id=definition.id,
                    source_record_id=source_record.id,
                    supersedes_fact_id=superseded.id if superseded else None,
                    period_start=fact_record.period_start,
                    period_end=fact_record.period_end,
                    filing_date=fact_record.filing_date,
                    available_at=fact_record.available_at,
                    consolidation_scope=fact_record.consolidation_scope,
                    value=fact_record.value,
                    status=fact_record.status.value,
                    currency=fact_record.currency,
                    reported_unit=fact_record.reported_unit,
                )
            )
            self._session.flush()
            inserted += 1

        run.status = "completed_with_warnings" if quality_flags else "completed"
        run.ended_at = datetime.now(UTC)
        self._session.flush()
        return IngestionSummary(run.id, inserted, skipped, quality_flags)


class CorporateActionIngestionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ingest(self, batch: CorporateActionBatch) -> IngestionSummary:
        source = self._session.scalar(
            select(DataSource).where(DataSource.name == batch.source.provider)
        )
        if source is None:
            source = DataSource(
                name=batch.source.provider,
                source_class=batch.source.source_class,
                reliability_tier=batch.source.reliability_tier,
                terms_reference=batch.source.terms_reference,
            )
            self._session.add(source)
            self._session.flush()
        run = IngestionRun(
            data_source_id=source.id,
            requested_range=None,
            started_at=datetime.now(UTC),
            status="running",
        )
        self._session.add(run)
        self._session.flush()
        source_record = SourceRecord(
            ingestion_run_id=run.id,
            source_identifier=batch.source.source_identifier,
            retrieved_at=batch.source.retrieved_at,
            checksum=batch.source.checksum,
        )
        self._session.add(source_record)
        self._session.flush()
        for issue in batch.issues:
            self._session.add(
                DataQualityFlag(
                    ingestion_run_id=run.id,
                    entity_type="corporate_action",
                    field_name=issue.field_name,
                    severity="error",
                    reason=issue.reason,
                    observed_value=issue.observed_value,
                )
            )
        inserted = 0
        skipped = 0
        quality_flags = len(batch.issues)
        for record in batch.records:
            instrument = self._session.scalar(
                select(Instrument).where(Instrument.isin == record.isin)
            )
            if instrument is None:
                quality_flags += 1
                skipped += 1
                self._session.add(
                    DataQualityFlag(
                        ingestion_run_id=run.id,
                        entity_type="corporate_action",
                        field_name="isin",
                        severity="error",
                        reason="corporate action references an unknown instrument",
                        observed_value=record.isin,
                    )
                )
                continue
            exists = self._session.scalar(
                select(CorporateAction.id).where(
                    CorporateAction.instrument_id == instrument.id,
                    CorporateAction.action_type == record.action_type,
                    CorporateAction.ex_date == record.ex_date,
                    CorporateAction.ratio_numerator == record.ratio_numerator,
                    CorporateAction.ratio_denominator == record.ratio_denominator,
                    CorporateAction.cash_amount == record.cash_amount,
                )
            )
            if exists is not None:
                skipped += 1
                continue
            self._session.add(
                CorporateAction(
                    instrument_id=instrument.id,
                    source_record_id=source_record.id,
                    action_type=record.action_type,
                    ex_date=record.ex_date,
                    record_date=record.record_date,
                    ratio_numerator=record.ratio_numerator,
                    ratio_denominator=record.ratio_denominator,
                    cash_amount=record.cash_amount,
                    currency=record.currency,
                    verification_status=record.verification_status,
                )
            )
            inserted += 1
        run.status = "completed_with_warnings" if quality_flags else "completed"
        run.ended_at = datetime.now(UTC)
        self._session.flush()
        return IngestionSummary(run.id, inserted, skipped, quality_flags)
