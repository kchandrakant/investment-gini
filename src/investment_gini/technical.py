from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Literal

from investment_gini.application import BenchmarkPoint, BenchmarkSeries, PricePoint, PriceSeries

FeatureStatus = Literal["ready", "insufficient_history"]
TrendState = Literal["confirmed_uptrend", "constructive", "not_confirmed", "insufficient_history"]

FORMULA_VERSION = "technical-v2"
MOMENTUM_FORMULA_VERSION = "momentum-v1"
_PRICE_QUANTUM = Decimal("0.0001")
_RATIO_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True)
class TechnicalFeature:
    name: str
    value: Decimal | None
    unit: str
    status: FeatureStatus
    required_observations: int
    actual_observations: int
    evidence_start: date | None
    evidence_end: date | None
    explanation: str


@dataclass(frozen=True)
class MomentumContribution:
    name: str
    points_awarded: Decimal | None
    max_points: Decimal
    status: FeatureStatus
    passed: bool | None
    input_features: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class MomentumScore:
    value: Decimal | None
    max_value: Decimal
    status: FeatureStatus
    trend_state: TrendState
    formula_version: str
    contributions: tuple[MomentumContribution, ...]


@dataclass(frozen=True)
class TechnicalSnapshot:
    isin: str
    symbol: str
    as_of: date
    formula_version: str
    adjustment_status: str
    observations_used: int
    input_start: date | None
    input_end: date | None
    source_identifiers: tuple[str, ...]
    benchmark_source_identifiers: tuple[str, ...]
    features: tuple[TechnicalFeature, ...]
    momentum_score: MomentumScore

    def feature(self, name: str) -> TechnicalFeature:
        try:
            return next(feature for feature in self.features if feature.name == name)
        except StopIteration as error:
            raise KeyError(name) from error


def calculate_technical_snapshot(
    series: PriceSeries,
    as_of: date,
    benchmark: BenchmarkSeries | None = None,
) -> TechnicalSnapshot:
    points = tuple(point for point in series.points if point.session_date <= as_of)
    benchmark_points = tuple(
        point for point in (benchmark.points if benchmark else ()) if point.session_date <= as_of
    )
    features = (
        _latest_close(points),
        *(_simple_moving_average(points, window) for window in (20, 50, 150, 200)),
        _sma_change(points, 200, 21),
        *(_exponential_moving_average(points, window) for window in (20, 50)),
        *(_period_return(points, sessions) for sessions in (21, 63, 126, 252)),
        _annualized_volatility(points, 63),
        _maximum_drawdown(points, 252),
        _distance_from_high(points, 252),
        _volume_ratio(points, 20),
        *(
            _relative_strength(points, benchmark_points, sessions)
            for sessions in (63, 126, 252)
        ),
    )
    momentum_score = _momentum_score(features)
    return TechnicalSnapshot(
        isin=series.instrument.isin,
        symbol=series.instrument.symbol,
        as_of=as_of,
        formula_version=FORMULA_VERSION,
        adjustment_status=series.adjustment_status,
        observations_used=len(points),
        input_start=points[0].session_date if points else None,
        input_end=points[-1].session_date if points else None,
        source_identifiers=tuple(sorted({point.source_identifier for point in points})),
        benchmark_source_identifiers=tuple(
            sorted({point.source_identifier for point in benchmark_points})
        ),
        features=features,
        momentum_score=momentum_score,
    )


def _insufficient(
    name: str,
    unit: str,
    required: int,
    points: tuple[PricePoint, ...],
    explanation: str,
) -> TechnicalFeature:
    return TechnicalFeature(
        name=name,
        value=None,
        unit=unit,
        status="insufficient_history",
        required_observations=required,
        actual_observations=len(points),
        evidence_start=points[0].session_date if points else None,
        evidence_end=points[-1].session_date if points else None,
        explanation=explanation,
    )


def _ready(
    name: str,
    value: Decimal,
    unit: str,
    required: int,
    evidence: tuple[PricePoint, ...],
    explanation: str,
) -> TechnicalFeature:
    return TechnicalFeature(
        name=name,
        value=value,
        unit=unit,
        status="ready",
        required_observations=required,
        actual_observations=len(evidence),
        evidence_start=evidence[0].session_date,
        evidence_end=evidence[-1].session_date,
        explanation=explanation,
    )


def _latest_close(points: tuple[PricePoint, ...]) -> TechnicalFeature:
    name = "latest_close"
    explanation = "Latest closing price on or before the snapshot as-of date."
    if not points:
        return _insufficient(name, "price", 1, points, explanation)
    evidence = points[-1:]
    return _ready(name, evidence[0].close, "price", 1, evidence, explanation)


def _simple_moving_average(
    points: tuple[PricePoint, ...], window: int
) -> TechnicalFeature:
    name = f"sma_{window}"
    explanation = f"Arithmetic mean of the latest {window} session closes."
    if len(points) < window:
        return _insufficient(name, "price", window, points, explanation)
    evidence = points[-window:]
    value = (sum((point.close for point in evidence), Decimal(0)) / window).quantize(
        _PRICE_QUANTUM
    )
    return _ready(name, value, "price", window, evidence, explanation)


def _sma_change(
    points: tuple[PricePoint, ...], window: int, interval: int
) -> TechnicalFeature:
    required = window + interval
    name = f"sma_{window}_change_{interval}"
    explanation = (
        f"Percentage change in the {window}-session SMA over {interval} sessions."
    )
    if len(points) < required:
        return _insufficient(name, "ratio", required, points, explanation)
    evidence = points[-required:]
    previous_window = evidence[:window]
    current_window = evidence[-window:]
    previous = sum((point.close for point in previous_window), Decimal(0)) / window
    if previous == 0:
        return _insufficient(name, "ratio", required, evidence, explanation)
    current = sum((point.close for point in current_window), Decimal(0)) / window
    value = (current / previous - Decimal(1)).quantize(_RATIO_QUANTUM)
    return _ready(name, value, "ratio", required, evidence, explanation)


def _exponential_moving_average(
    points: tuple[PricePoint, ...], window: int
) -> TechnicalFeature:
    name = f"ema_{window}"
    explanation = (
        f"EMA with alpha 2/({window}+1), seeded by the first {window}-session SMA."
    )
    if len(points) < window:
        return _insufficient(name, "price", window, points, explanation)
    alpha = Decimal(2) / Decimal(window + 1)
    seed = sum((point.close for point in points[:window]), Decimal(0)) / window
    value = seed
    for point in points[window:]:
        value = alpha * point.close + (Decimal(1) - alpha) * value
    return _ready(
        name,
        value.quantize(_PRICE_QUANTUM),
        "price",
        window,
        points,
        explanation,
    )


def _period_return(points: tuple[PricePoint, ...], sessions: int) -> TechnicalFeature:
    required = sessions + 1
    name = f"return_{sessions}"
    explanation = f"Close-to-close return across {sessions} trading-session intervals."
    if len(points) < required:
        return _insufficient(name, "ratio", required, points, explanation)
    evidence = points[-required:]
    value = (evidence[-1].close / evidence[0].close - Decimal(1)).quantize(_RATIO_QUANTUM)
    return _ready(name, value, "ratio", required, evidence, explanation)


def _annualized_volatility(
    points: tuple[PricePoint, ...], sessions: int
) -> TechnicalFeature:
    required = sessions + 1
    name = f"annualized_volatility_{sessions}"
    explanation = (
        f"Sample standard deviation of {sessions} daily close returns, annualized by sqrt(252)."
    )
    if len(points) < required:
        return _insufficient(name, "ratio", required, points, explanation)
    evidence = points[-required:]
    returns = tuple(
        evidence[index].close / evidence[index - 1].close - Decimal(1)
        for index in range(1, len(evidence))
    )
    mean = sum(returns, Decimal(0)) / len(returns)
    variance = sum(((value - mean) ** 2 for value in returns), Decimal(0)) / (
        len(returns) - 1
    )
    with localcontext() as context:
        context.prec = 28
        value = (variance * Decimal(252)).sqrt().quantize(_RATIO_QUANTUM)
    return _ready(name, value, "ratio", required, evidence, explanation)


def _maximum_drawdown(points: tuple[PricePoint, ...], window: int) -> TechnicalFeature:
    name = f"maximum_drawdown_{window}"
    explanation = f"Largest peak-to-trough close decline within the latest {window} sessions."
    if len(points) < window:
        return _insufficient(name, "ratio", window, points, explanation)
    evidence = points[-window:]
    peak = evidence[0].close
    maximum_drawdown = Decimal(0)
    for point in evidence:
        peak = max(peak, point.close)
        maximum_drawdown = min(maximum_drawdown, point.close / peak - Decimal(1))
    return _ready(
        name,
        maximum_drawdown.quantize(_RATIO_QUANTUM),
        "ratio",
        window,
        evidence,
        explanation,
    )


def _distance_from_high(points: tuple[PricePoint, ...], window: int) -> TechnicalFeature:
    name = f"distance_from_high_{window}"
    explanation = f"Latest close divided by the highest close in {window} sessions, minus one."
    if len(points) < window:
        return _insufficient(name, "ratio", window, points, explanation)
    evidence = points[-window:]
    highest_close = max(point.close for point in evidence)
    value = (evidence[-1].close / highest_close - Decimal(1)).quantize(_RATIO_QUANTUM)
    return _ready(name, value, "ratio", window, evidence, explanation)


def _volume_ratio(points: tuple[PricePoint, ...], window: int) -> TechnicalFeature:
    name = f"volume_ratio_{window}"
    explanation = f"Latest volume divided by mean volume over the latest {window} sessions."
    if len(points) < window:
        return _insufficient(name, "ratio", window, points, explanation)
    evidence = points[-window:]
    average_volume = Decimal(sum((point.volume for point in evidence), 0)) / Decimal(window)
    if average_volume == 0:
        return _insufficient(name, "ratio", window, evidence, explanation)
    value = (Decimal(evidence[-1].volume) / average_volume).quantize(_RATIO_QUANTUM)
    return _ready(name, value, "ratio", window, evidence, explanation)


def _relative_strength(
    points: tuple[PricePoint, ...],
    benchmark_points: tuple[BenchmarkPoint, ...],
    sessions: int,
) -> TechnicalFeature:
    required = sessions + 1
    name = f"relative_strength_{sessions}"
    explanation = (
        f"Stock growth divided by Nifty 200 growth across {sessions} common-session "
        "intervals, minus one."
    )
    benchmark_by_date = {point.session_date: point for point in benchmark_points}
    aligned = tuple(
        (point, benchmark_by_date[point.session_date])
        for point in points
        if point.session_date in benchmark_by_date
    )
    stock_evidence = tuple(point for point, _ in aligned)
    if len(aligned) < required:
        return _insufficient(name, "ratio", required, stock_evidence, explanation)
    evidence = aligned[-required:]
    stock_growth = evidence[-1][0].close / evidence[0][0].close
    benchmark_growth = evidence[-1][1].close / evidence[0][1].close
    if benchmark_growth == 0:
        return _insufficient(name, "ratio", required, stock_evidence[-required:], explanation)
    value = (stock_growth / benchmark_growth - Decimal(1)).quantize(_RATIO_QUANTUM)
    return _ready(name, value, "ratio", required, stock_evidence[-required:], explanation)


def _momentum_score(features: tuple[TechnicalFeature, ...]) -> MomentumScore:
    feature_by_name = {feature.name: feature for feature in features}
    contributions = (
        _score_comparison(
            "price_above_sma_50", Decimal(5), feature_by_name, "latest_close", "sma_50", ">",
            "Latest close is above the 50-session SMA.",
        ),
        _score_comparison(
            "price_above_sma_150", Decimal(5), feature_by_name, "latest_close", "sma_150", ">",
            "Latest close is above the 150-session SMA.",
        ),
        _score_comparison(
            "price_above_sma_200", Decimal(5), feature_by_name, "latest_close", "sma_200", ">",
            "Latest close is above the 200-session SMA.",
        ),
        _score_comparison(
            "sma_50_above_sma_150", Decimal(5), feature_by_name, "sma_50", "sma_150", ">",
            "The 50-session SMA is above the 150-session SMA.",
        ),
        _score_comparison(
            "sma_150_above_sma_200", Decimal(5), feature_by_name, "sma_150", "sma_200", ">",
            "The 150-session SMA is above the 200-session SMA.",
        ),
        _score_threshold(
            "sma_200_rising", Decimal(5), feature_by_name, "sma_200_change_21", ">", Decimal(0),
            "The 200-session SMA has risen over 21 sessions.",
        ),
        *(
            _score_threshold(
                f"positive_return_{sessions}", Decimal(10), feature_by_name,
                f"return_{sessions}", ">", Decimal(0),
                f"The {sessions}-session stock return is positive.",
            )
            for sessions in (63, 126, 252)
        ),
        *(
            _score_threshold(
                f"positive_relative_strength_{sessions}", Decimal(5), feature_by_name,
                f"relative_strength_{sessions}", ">", Decimal(0),
                f"The stock outperformed Nifty 200 over {sessions} common-session intervals.",
            )
            for sessions in (63, 126, 252)
        ),
        _score_threshold(
            "drawdown_within_25_percent", Decimal(5), feature_by_name,
            "maximum_drawdown_252", ">=", Decimal("-0.25"),
            "The maximum 252-session drawdown is no worse than 25%.",
        ),
        _score_threshold(
            "volatility_at_most_40_percent", Decimal(5), feature_by_name,
            "annualized_volatility_63", "<=", Decimal("0.40"),
            "Annualized 63-session volatility is at most 40%.",
        ),
        _score_threshold(
            "within_25_percent_of_high", Decimal(10), feature_by_name,
            "distance_from_high_252", ">=", Decimal("-0.25"),
            "Latest close is within 25% of the 252-session closing high.",
        ),
        _score_threshold(
            "volume_at_or_above_average", Decimal(5), feature_by_name,
            "volume_ratio_20", ">=", Decimal(1),
            "Latest volume is at or above its 20-session mean.",
        ),
    )
    trend_contributions = contributions[:6]
    if any(item.status != "ready" for item in trend_contributions):
        trend_state: TrendState = "insufficient_history"
    else:
        passed = sum(item.passed is True for item in trend_contributions)
        if passed == 6:
            trend_state = "confirmed_uptrend"
        elif passed >= 4:
            trend_state = "constructive"
        else:
            trend_state = "not_confirmed"

    if any(item.status != "ready" for item in contributions):
        value = None
        status: FeatureStatus = "insufficient_history"
    else:
        value = sum(
            (item.points_awarded or Decimal(0) for item in contributions), Decimal(0)
        )
        status = "ready"
    return MomentumScore(
        value=value,
        max_value=Decimal(100),
        status=status,
        trend_state=trend_state,
        formula_version=MOMENTUM_FORMULA_VERSION,
        contributions=contributions,
    )


def _score_comparison(
    name: str,
    max_points: Decimal,
    features: dict[str, TechnicalFeature],
    left_name: str,
    right_name: str,
    operator: str,
    explanation: str,
) -> MomentumContribution:
    left = features[left_name]
    right = features[right_name]
    if left.value is None or right.value is None:
        return _missing_contribution(
            name, max_points, (left_name, right_name), explanation
        )
    passed = _compare(left.value, operator, right.value)
    return _ready_contribution(
        name, max_points, passed, (left_name, right_name), explanation
    )


def _score_threshold(
    name: str,
    max_points: Decimal,
    features: dict[str, TechnicalFeature],
    feature_name: str,
    operator: str,
    threshold: Decimal,
    explanation: str,
) -> MomentumContribution:
    feature = features[feature_name]
    if feature.value is None:
        return _missing_contribution(name, max_points, (feature_name,), explanation)
    passed = _compare(feature.value, operator, threshold)
    return _ready_contribution(name, max_points, passed, (feature_name,), explanation)


def _compare(left: Decimal, operator: str, right: Decimal) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    raise ValueError(f"unsupported score operator: {operator}")


def _ready_contribution(
    name: str,
    max_points: Decimal,
    passed: bool,
    input_features: tuple[str, ...],
    explanation: str,
) -> MomentumContribution:
    return MomentumContribution(
        name=name,
        points_awarded=max_points if passed else Decimal(0),
        max_points=max_points,
        status="ready",
        passed=passed,
        input_features=input_features,
        explanation=explanation,
    )


def _missing_contribution(
    name: str,
    max_points: Decimal,
    input_features: tuple[str, ...],
    explanation: str,
) -> MomentumContribution:
    return MomentumContribution(
        name=name,
        points_awarded=None,
        max_points=max_points,
        status="insufficient_history",
        passed=None,
        input_features=input_features,
        explanation=explanation,
    )