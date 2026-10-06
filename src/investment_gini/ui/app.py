from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import streamlit as st

from investment_gini.application import (
    BenchmarkPoint,
    InstrumentSearchResult,
    PricePoint,
    get_adjusted_price_series,
    get_benchmark_series,
    get_dashboard_snapshot,
    get_latest_nifty200_as_of,
    get_price_series,
    get_technical_snapshot,
    initialize_database,
    search_nifty200_instruments,
)

st.set_page_config(page_title="Investment Gini", page_icon=":material/monitoring:", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Literata:opsz,wght@7..72,600&display=swap');
    :root {
        --ink: #17221c;
        --paper: #f5f7f2;
        --signal: #b84028;
        --positive: #18794e;
        --line: #cfd7ce;
    }
    .stApp {
        background: var(--paper);
        color: var(--ink);
        font-family: 'IBM Plex Sans', sans-serif;
    }
    h1, h2, h3 { font-family: 'Literata', serif !important; letter-spacing: 0 !important; }
    [data-testid="stMetric"] { border-top: 2px solid var(--ink); padding-top: 0.75rem; }
    [data-testid="stSidebar"] { background: #e8ede6; }
    [data-baseweb="tab-list"] { gap: 1.5rem; border-bottom: 1px solid var(--line); }
    [data-baseweb="tab"] { font-weight: 600; padding-left: 0; padding-right: 0; }
    .stock-kicker { color: #55635a; font-size: 0.83rem; text-transform: uppercase; }
    </style>
    """,
    unsafe_allow_html=True,
)

database_path = Path("data/investment_gini.db")
if not database_path.exists():
    initialize_database()

st.title("Investment Gini")
st.caption("Indian equity research workspace / Raw market evidence")


def _option_label(instrument: InstrumentSearchResult) -> str:
    return f"{instrument.symbol}  |  {instrument.company_name}"


def _price_records(points: tuple[PricePoint, ...]) -> list[dict[str, Any]]:
    return [
        {
            "date": point.session_date.isoformat(),
            "open": float(point.open),
            "high": float(point.high),
            "low": float(point.low),
            "close": float(point.close),
            "volume": point.volume,
        }
        for point in points
    ]


def _raw_return(first_close: Decimal, last_close: Decimal) -> Decimal:
    if first_close == 0:
        return Decimal(0)
    return ((last_close / first_close) - 1) * 100


def _moving_average_records(
    points: tuple[PricePoint, ...], visible_start: date
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    closes: list[Decimal] = []
    for point in points:
        closes.append(point.close)
        if point.session_date < visible_start:
            continue
        record: dict[str, Any] = {
            "date": point.session_date.isoformat(),
            "Adjusted close": float(point.close),
        }
        for window in (50, 200):
            if len(closes) >= window:
                average = sum(closes[-window:], Decimal(0)) / window
                record[f"SMA {window}"] = float(average)
        records.append(record)
    return records


def _comparison_records(
    stock_points: tuple[PricePoint, ...],
    benchmark_points: tuple[BenchmarkPoint, ...],
) -> list[dict[str, Any]]:
    benchmark_by_date = {point.session_date: point for point in benchmark_points}
    aligned = [
        (point, benchmark_by_date[point.session_date])
        for point in stock_points
        if point.session_date in benchmark_by_date
    ]
    if not aligned or aligned[0][0].close == 0 or aligned[0][1].close == 0:
        return []
    stock_base = aligned[0][0].close
    benchmark_base = aligned[0][1].close
    records: list[dict[str, Any]] = []
    for stock, benchmark in aligned:
        records.extend(
            (
                {
                    "date": stock.session_date.isoformat(),
                    "series": "Stock adjusted close",
                    "normalized": float(stock.close / stock_base * 100),
                },
                {
                    "date": benchmark.session_date.isoformat(),
                    "series": "Nifty 200 price index",
                    "normalized": float(benchmark.close / benchmark_base * 100),
                },
            )
        )
    return records


snapshot = get_dashboard_snapshot()
composition_date = get_latest_nifty200_as_of()
explorer_tab, coverage_tab = st.tabs(["Stock Explorer", "Data coverage"])

with explorer_tab:
    if composition_date is None:
        st.info("No Nifty 200 snapshot is available yet.")
    elif snapshot.price_first_session is None or snapshot.price_last_session is None:
        st.info("No raw NSE price history is available yet.")
    else:
        instruments = search_nifty200_instruments("", composition_date, limit=250)
        controls = st.columns([2.2, 1, 1, 1.1])
        with controls[0]:
            selected = st.selectbox(
                "Stock",
                instruments,
                format_func=_option_label,
                index=0 if instruments else None,
                placeholder="Search by symbol or company",
            )
        default_start = max(
            snapshot.price_first_session,
            snapshot.price_last_session - timedelta(days=365),
        )
        with controls[1]:
            selected_start = st.date_input(
                "From",
                value=default_start,
                min_value=snapshot.price_first_session,
                max_value=snapshot.price_last_session,
            )
        with controls[2]:
            selected_end = st.date_input(
                "To",
                value=snapshot.price_last_session,
                min_value=snapshot.price_first_session,
                max_value=snapshot.price_last_session,
            )
        with controls[3]:
            adjusted_mode = st.toggle(
                "Split/bonus adjusted",
                value=False,
                help="Adjusts historical prices and volume for verified split and bonus events.",
            )

        if selected is None:
            st.info("Select a stock to inspect its raw NSE history.")
        elif not isinstance(selected_start, date) or not isinstance(selected_end, date):
            st.error("Choose one start date and one end date.")
        elif selected_start > selected_end:
            st.error("The start date must not be after the end date.")
        else:
            with st.spinner("Loading raw market history..."):
                query = get_adjusted_price_series if adjusted_mode else get_price_series
                series = query(selected.isin, selected_start, selected_end)
                technical = get_technical_snapshot(selected.isin, selected_end)
                overlay_start = selected_start - timedelta(days=320)
                adjusted_series = get_adjusted_price_series(
                    selected.isin, overlay_start, selected_end
                )
                benchmark_series = get_benchmark_series(
                    "NIFTY_200", selected_start, selected_end
                )

            st.markdown(
                f'<div class="stock-kicker">{series.instrument.exchange} / '
                f"{series.instrument.isin}</div>",
                unsafe_allow_html=True,
            )
            st.subheader(f"{series.instrument.symbol} · {series.instrument.company_name}")
            st.caption(
                f"{series.instrument.sector or 'Sector unavailable'} / "
                f"{series.instrument.industry or 'Industry unavailable'}"
            )

            if not series.points:
                st.warning(
                    "No raw EQ price rows were found for this stock in the selected period."
                )
            else:
                first_point = series.points[0]
                last_point = series.points[-1]
                raw_return = _raw_return(first_point.close, last_point.close)
                latest_retrieval = series.latest_retrieved_at
                metrics = st.columns(4)
                price_label = "Latest adjusted close" if adjusted_mode else "Latest raw close"
                return_label = "Adjusted return" if adjusted_mode else "Raw return"
                metrics[0].metric(price_label, f"₹{last_point.close:,.2f}")
                metrics[1].metric(return_label, f"{raw_return:+.2f}%")
                metrics[2].metric("Sessions", f"{len(series.points):,}")
                metrics[3].metric(
                    "Latest session",
                    series.latest_session.isoformat() if series.latest_session else "—",
                )
                if adjusted_mode:
                    st.caption(
                        "Verified splits and bonuses are reflected. Dividends, rights issues, "
                        "and demergers are stored as evidence but are not included in this "
                        "price-return series."
                    )
                else:
                    st.caption(
                        "Return uses unadjusted close prices. Splits, bonuses, dividends, rights "
                        "issues, and demergers are not reflected."
                    )

                records = _price_records(series.points)
                st.markdown("#### Raw OHLC")
                st.vega_lite_chart(
                    {
                        "data": {"values": records},
                        "height": 390,
                        "layer": [
                            {
                                "mark": {"type": "rule", "color": "#55635a"},
                                "encoding": {
                                    "x": {"field": "date", "type": "temporal", "title": None},
                                    "y": {
                                        "field": "low",
                                        "type": "quantitative",
                                        "title": "Price (₹)",
                                        "scale": {"zero": False},
                                    },
                                    "y2": {"field": "high"},
                                },
                            },
                            {
                                "mark": {"type": "bar", "size": 5},
                                "encoding": {
                                    "x": {"field": "date", "type": "temporal", "title": None},
                                    "y": {
                                        "field": "open",
                                        "type": "quantitative",
                                        "scale": {"zero": False},
                                    },
                                    "y2": {"field": "close"},
                                    "color": {
                                        "condition": {
                                            "test": "datum.close >= datum.open",
                                            "value": "#18794e",
                                        },
                                        "value": "#b84028",
                                    },
                                    "tooltip": [
                                        {"field": "date", "type": "temporal", "title": "Date"},
                                        {"field": "open", "type": "quantitative", "title": "Open"},
                                        {"field": "high", "type": "quantitative", "title": "High"},
                                        {"field": "low", "type": "quantitative", "title": "Low"},
                                        {
                                            "field": "close",
                                            "type": "quantitative",
                                            "title": "Close",
                                        },
                                    ],
                                },
                            },
                        ],
                    },
                    width="stretch",
                )

                st.markdown("#### Volume")
                st.vega_lite_chart(
                    {
                        "data": {"values": records},
                        "height": 180,
                        "mark": {"type": "bar", "color": "#3e6655"},
                        "encoding": {
                            "x": {"field": "date", "type": "temporal", "title": None},
                            "y": {
                                "field": "volume",
                                "type": "quantitative",
                                "title": "Shares",
                            },
                            "tooltip": [
                                {"field": "date", "type": "temporal", "title": "Date"},
                                {
                                    "field": "volume",
                                    "type": "quantitative",
                                    "title": "Volume",
                                    "format": ",",
                                },
                            ],
                        },
                    },
                    width="stretch",
                )

                st.markdown("#### Technical snapshot")
                st.caption(
                    f"As of {technical.as_of.isoformat()} · {technical.formula_version} · "
                    f"{technical.adjustment_status} · {technical.observations_used} sessions. "
                    "Calculations use split/bonus-adjusted closes and volumes; dividends, "
                    "rights issues, and demergers are not reflected."
                )
                score = technical.momentum_score
                score_columns = st.columns(3)
                score_columns[0].metric(
                    "Momentum score",
                    f"{score.value:.0f} / {score.max_value:.0f}"
                    if score.value is not None
                    else "Insufficient history",
                )
                score_columns[1].metric("Trend state", score.trend_state.replace("_", " "))
                score_columns[2].metric("Score formula", score.formula_version)
                st.dataframe(
                    [
                        {
                            "Component": contribution.name,
                            "Status": contribution.status,
                            "Passed": contribution.passed,
                            "Points": contribution.points_awarded,
                            "Maximum": contribution.max_points,
                            "Inputs": ", ".join(contribution.input_features),
                            "Definition": contribution.explanation,
                        }
                        for contribution in score.contributions
                    ],
                    hide_index=True,
                    width="stretch",
                )
                st.dataframe(
                    [
                        {
                            "Feature": feature.name,
                            "Status": feature.status,
                            "Value": feature.value,
                            "Unit": feature.unit,
                            "Required": feature.required_observations,
                            "Available": feature.actual_observations,
                            "Evidence from": feature.evidence_start,
                            "Evidence to": feature.evidence_end,
                            "Definition": feature.explanation,
                        }
                        for feature in technical.features
                    ],
                    hide_index=True,
                    width="stretch",
                )
                st.caption(
                    "Relative strength uses official Nifty 200 price-index history, aligned only "
                    "on common sessions. A missing component makes the total score unavailable "
                    "instead of silently awarding zero points."
                )

                overlay_records = _moving_average_records(
                    adjusted_series.points, selected_start
                )
                st.markdown("#### Adjusted trend overlays")
                st.vega_lite_chart(
                    {
                        "data": {"values": overlay_records},
                        "height": 300,
                        "transform": [
                            {
                                "fold": ["Adjusted close", "SMA 50", "SMA 200"],
                                "as": ["series", "price"],
                            },
                            {"filter": "isValid(datum.price)"},
                        ],
                        "mark": {"type": "line"},
                        "encoding": {
                            "x": {"field": "date", "type": "temporal", "title": None},
                            "y": {
                                "field": "price",
                                "type": "quantitative",
                                "title": "Adjusted price (₹)",
                                "scale": {"zero": False},
                            },
                            "color": {
                                "field": "series",
                                "type": "nominal",
                                "scale": {
                                    "domain": ["Adjusted close", "SMA 50", "SMA 200"],
                                    "range": ["#17221c", "#b84028", "#18794e"],
                                },
                            },
                            "tooltip": [
                                {"field": "date", "type": "temporal", "title": "Date"},
                                {"field": "series", "type": "nominal", "title": "Series"},
                                {"field": "price", "type": "quantitative", "title": "Price"},
                            ],
                        },
                    },
                    width="stretch",
                )

                comparison_records = _comparison_records(
                    tuple(
                        point
                        for point in adjusted_series.points
                        if point.session_date >= selected_start
                    ),
                    benchmark_series.points,
                )
                st.markdown("#### Relative performance")
                if comparison_records:
                    st.vega_lite_chart(
                        {
                            "data": {"values": comparison_records},
                            "height": 260,
                            "mark": {"type": "line"},
                            "encoding": {
                                "x": {
                                    "field": "date",
                                    "type": "temporal",
                                    "title": None,
                                },
                                "y": {
                                    "field": "normalized",
                                    "type": "quantitative",
                                    "title": "Common-session start = 100",
                                    "scale": {"zero": False},
                                },
                                "color": {
                                    "field": "series",
                                    "type": "nominal",
                                    "scale": {
                                        "domain": [
                                            "Stock adjusted close",
                                            "Nifty 200 price index",
                                        ],
                                        "range": ["#b84028", "#18794e"],
                                    },
                                },
                                "tooltip": [
                                    {
                                        "field": "date",
                                        "type": "temporal",
                                        "title": "Date",
                                    },
                                    {
                                        "field": "series",
                                        "type": "nominal",
                                        "title": "Series",
                                    },
                                    {
                                        "field": "normalized",
                                        "type": "quantitative",
                                        "title": "Indexed value",
                                        "format": ".2f",
                                    },
                                ],
                            },
                        },
                        width="stretch",
                    )
                else:
                    st.info("No common stock and Nifty 200 sessions exist in this range.")

                with st.expander("Price table"):
                    st.dataframe(
                        [
                            {
                                "Date": point.session_date,
                                "Open": point.open,
                                "High": point.high,
                                "Low": point.low,
                                "Close": point.close,
                                "Volume": point.volume,
                                "Trades": point.trade_count,
                            }
                            for point in reversed(series.points)
                        ],
                        hide_index=True,
                        width="stretch",
                    )

                quality_state = (
                    f"{len(series.quality_warnings)} warning(s)"
                    if series.quality_warnings
                    else "No instrument-specific warnings"
                )
                evidence_left, evidence_right = st.columns(2)
                with evidence_left:
                    st.markdown("**Evidence status**")
                    st.write(f"Adjustment: `{series.adjustment_status}`")
                    st.write(f"Corporate actions in range: {series.corporate_action_count}")
                    st.write(f"Quality: {quality_state}")
                    st.write(f"Source: {', '.join(series.source_names)}")
                with evidence_right:
                    st.markdown("**Freshness**")
                    st.write(
                        "Retrieved: "
                        + (
                            latest_retrieval.isoformat(sep=" ", timespec="seconds")
                            if latest_retrieval
                            else "Unavailable"
                        )
                    )
                    st.write(f"Archive records: {len(series.source_identifiers):,}")
                    st.write(f"Latest market session: {last_point.session_date.isoformat()}")

                if series.quality_warnings:
                    st.warning(
                        "This period has instrument-specific source gaps. Inspect the warnings "
                        "before drawing conclusions."
                    )
                    with st.expander("Quality warnings"):
                        for warning in series.quality_warnings:
                            warning_date = (
                                warning.session_date.isoformat()
                                if warning.session_date
                                else "Unknown date"
                            )
                            st.write(f"{warning_date} · {warning.severity} · {warning.reason}")

                with st.expander("Source archives"):
                    for source_identifier in series.source_identifiers:
                        st.code(source_identifier, language=None)

with coverage_tab:
    instruments_metric, prices_metric, sessions_metric, sources_metric, quality_metric = (
        st.columns(5)
    )
    instruments_metric.metric("Instruments", snapshot.instrument_count)
    prices_metric.metric("Raw price bars", snapshot.price_bar_count)
    sessions_metric.metric("Price sessions", snapshot.price_session_count)
    sources_metric.metric("Data sources", len(snapshot.data_sources))
    quality_metric.metric("Open quality flags", snapshot.open_quality_flags)

    if snapshot.price_first_session is not None and snapshot.price_last_session is not None:
        st.caption(
            f"Raw, unadjusted NSE coverage: {snapshot.price_first_session.isoformat()} to "
            f"{snapshot.price_last_session.isoformat()}; "
            f"{snapshot.adjusted_price_bar_count} adjusted bars."
        )

    left, right = st.columns(2)
    with left:
        st.markdown("**Universe versions**")
        for version in snapshot.universe_versions:
            st.write(version)
    with right:
        st.markdown("**Registered sources**")
        for source in snapshot.data_sources:
            st.write(source)

st.divider()
st.warning(
    "Research and decision-support only. Historical results do not guarantee future returns. "
    "Current-snapshot history has survivorship bias; investment decisions remain your "
    "responsibility."
)