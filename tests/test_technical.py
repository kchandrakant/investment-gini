from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from investment_gini.application import (
    BenchmarkPoint,
    BenchmarkSeries,
    InstrumentSearchResult,
    PricePoint,
    PriceSeries,
)
from investment_gini.technical import FORMULA_VERSION, calculate_technical_snapshot


def _series(closes: list[str]) -> PriceSeries:
    start = date(2024, 1, 1)
    instrument = InstrumentSearchResult(
        company_name="Alpha Industries",
        isin="INE000A01001",
        symbol="ALPHA",
        exchange="NSE",
        sector="Industrials",
        industry="Machinery",
    )
    points = tuple(
        PricePoint(
            session_date=start + timedelta(days=index),
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            previous_close=Decimal(closes[max(0, index - 1)]),
            volume=1_000 + index,
            traded_value=Decimal("100000"),
            trade_count=100,
            is_adjusted=True,
            source_name="nse_bhavcopy",
            source_identifier=f"https://example.test/{index}.zip",
            source_checksum="a" * 64,
            retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        for index, close in enumerate(closes)
    )
    return PriceSeries(
        instrument=instrument,
        requested_start=start,
        requested_end=points[-1].session_date,
        points=points,
        adjustment_status="adjusted_split_bonus",
        latest_session=points[-1].session_date,
        latest_retrieved_at=points[-1].retrieved_at,
        source_names=("nse_bhavcopy",),
        source_identifiers=tuple(point.source_identifier for point in points),
        quality_warnings=(),
    )


def _benchmark(series: PriceSeries, closes: list[str]) -> BenchmarkSeries:
    points = tuple(
        BenchmarkPoint(
            session_date=stock_point.session_date,
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            source_identifier=f"https://benchmark.test/{index}",
            source_checksum="b" * 64,
            retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        for index, (stock_point, close) in enumerate(zip(series.points, closes, strict=True))
    )
    return BenchmarkSeries(
        benchmark_code="NIFTY_200",
        benchmark_name="Nifty 200",
        requested_start=points[0].session_date,
        requested_end=points[-1].session_date,
        points=points,
        source_identifiers=tuple(point.source_identifier for point in points),
        latest_session=points[-1].session_date,
        latest_retrieved_at=points[-1].retrieved_at,
    )


def test_snapshot_calculates_independently_checkable_features() -> None:
    series = _series([str(value) for value in range(1, 261)])

    snapshot = calculate_technical_snapshot(series, series.points[-1].session_date)

    assert snapshot.formula_version == FORMULA_VERSION
    assert snapshot.observations_used == 260
    assert snapshot.feature("sma_20").value == Decimal("250.5000")
    assert snapshot.feature("sma_200_change_21").value == Decimal("0.150538")
    assert snapshot.feature("return_21").value == Decimal("0.087866")
    assert snapshot.feature("maximum_drawdown_252").value == Decimal("0.000000")
    assert snapshot.feature("distance_from_high_252").value == Decimal("0.000000")
    assert snapshot.feature("volume_ratio_20").value == Decimal("1.007603")


def test_snapshot_excludes_every_observation_after_as_of() -> None:
    base = _series([str(value) for value in range(1, 261)])
    as_of = base.points[-1].session_date
    future = replace(
        base.points[-1],
        session_date=as_of + timedelta(days=1),
        close=Decimal("999999"),
        source_identifier="https://example.test/future.zip",
    )
    extended = replace(base, points=(*base.points, future))

    expected = calculate_technical_snapshot(base, as_of)
    actual = calculate_technical_snapshot(extended, as_of)

    assert actual == expected
    assert actual.input_end == as_of
    assert future.source_identifier not in actual.source_identifiers


def test_snapshot_reports_insufficient_history_without_inventing_values() -> None:
    series = _series(["100", "110", "99"])

    snapshot = calculate_technical_snapshot(series, series.points[-1].session_date)

    assert snapshot.feature("latest_close").value == Decimal("99")
    sma = snapshot.feature("sma_20")
    assert sma.status == "insufficient_history"
    assert sma.value is None
    assert sma.required_observations == 20
    assert sma.actual_observations == 3
    assert snapshot.feature("return_21").value is None
    assert snapshot.momentum_score.status == "insufficient_history"
    assert snapshot.momentum_score.value is None


def test_relative_strength_uses_only_aligned_sessions_through_as_of() -> None:
    series = _series([str(100 + index) for index in range(65)])
    benchmark = _benchmark(series, [str(100 + index / 2) for index in range(65)])
    as_of = series.points[-2].session_date
    future_benchmark = replace(
        benchmark.points[-1],
        close=Decimal("999999"),
        source_identifier="https://benchmark.test/future",
    )
    benchmark = replace(benchmark, points=(*benchmark.points[:-1], future_benchmark))

    snapshot = calculate_technical_snapshot(series, as_of, benchmark)

    feature = snapshot.feature("relative_strength_63")
    expected = (
        (series.points[-2].close / series.points[0].close)
        / (benchmark.points[-2].close / benchmark.points[0].close)
        - Decimal(1)
    ).quantize(Decimal("0.000001"))
    assert feature.status == "ready"
    assert feature.value == expected
    assert feature.evidence_end == as_of
    assert future_benchmark.source_identifier not in snapshot.benchmark_source_identifiers


def test_relative_strength_requires_common_session_history() -> None:
    series = _series([str(100 + index) for index in range(64)])
    benchmark = _benchmark(series, [str(100 + index) for index in range(64)])
    benchmark = replace(benchmark, points=benchmark.points[1:])

    snapshot = calculate_technical_snapshot(series, series.points[-1].session_date, benchmark)

    feature = snapshot.feature("relative_strength_63")
    assert feature.status == "insufficient_history"
    assert feature.actual_observations == 63
    assert feature.value is None


def test_momentum_score_exposes_hand_checkable_component_contributions() -> None:
    series = _series([str(100 + index) for index in range(260)])
    benchmark = _benchmark(series, ["100"] * 260)

    snapshot = calculate_technical_snapshot(series, series.points[-1].session_date, benchmark)

    score = snapshot.momentum_score
    assert score.formula_version == "momentum-v1"
    assert score.status == "ready"
    assert score.trend_state == "confirmed_uptrend"
    assert score.value == Decimal(100)
    assert score.max_value == Decimal(100)
    assert sum(item.max_points for item in score.contributions) == Decimal(100)
    assert all(item.passed is True for item in score.contributions)
    assert all(item.points_awarded == item.max_points for item in score.contributions)


def test_momentum_score_does_not_treat_missing_benchmark_as_zero() -> None:
    series = _series([str(100 + index) for index in range(260)])

    snapshot = calculate_technical_snapshot(series, series.points[-1].session_date)

    score = snapshot.momentum_score
    relative = next(
        item for item in score.contributions if item.name == "positive_relative_strength_63"
    )
    assert score.status == "insufficient_history"
    assert score.value is None
    assert relative.status == "insufficient_history"
    assert relative.points_awarded is None