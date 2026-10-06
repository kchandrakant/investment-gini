from datetime import date

from typer.testing import CliRunner

from investment_gini import cli
from investment_gini.application import (
    InstrumentCoverageGap,
    PriceCoverageSummary,
    PriceRangeDayOutcome,
    PriceRangeSyncSummary,
)
from investment_gini.cli import app

runner = CliRunner()


def test_members_rejects_invalid_date() -> None:
    result = runner.invoke(app, ["members", "--as-of", "03-06-2024"])

    assert result.exit_code == 2
    assert "must use YYYY-MM-DD format" in result.output


def test_cli_help_loads_all_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "import-universe" in result.output
    assert "members" in result.output
    assert "price-coverage" in result.output
    assert "sync-nifty200" in result.output
    assert "sync-price-range" in result.output
    assert "sync-prices" in result.output


def test_sync_prices_rejects_invalid_date() -> None:
    result = runner.invoke(
        app,
        [
            "sync-prices",
            "--session-date",
            "02-09-2026",
            "--universe-as-of",
            "2026-08-31",
        ],
    )

    assert result.exit_code == 2
    assert "dates must use YYYY-MM-DD format" in result.output


def test_sync_price_range_prints_summary_and_unavailable_dates(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    summary = PriceRangeSyncSummary(
        start_date=date(2026, 8, 29),
        end_date=date(2026, 8, 31),
        outcomes=(
            PriceRangeDayOutcome(date(2026, 8, 29), "weekend"),
            PriceRangeDayOutcome(date(2026, 8, 30), "weekend"),
            PriceRangeDayOutcome(
                date(2026, 8, 31),
                "archive_unavailable",
                detail="official archive unavailable",
            ),
        ),
        sessions_ingested=0,
        sessions_already_complete=0,
        weekends_skipped=2,
        archives_unavailable=1,
        sessions_failed=0,
        bars_inserted=0,
        bars_skipped=0,
        quality_flags=0,
        incomplete_sessions=0,
    )
    received_options: dict[str, float] = {}

    def range_sync(*args, **kwargs):  # type: ignore[no-untyped-def]
        received_options.update(kwargs)
        return summary

    monkeypatch.setattr(cli, "sync_nifty200_price_range", range_sync)

    result = runner.invoke(
        app,
        [
            "sync-price-range",
            "--start-date",
            "2026-08-29",
            "--end-date",
            "2026-08-31",
            "--universe-as-of",
            "2026-08-31",
        ],
    )

    assert result.exit_code == 0
    assert "weekends=2" in result.output
    assert "unavailable=1" in result.output
    assert "incomplete=0" in result.output
    assert "2026-08-31\tarchive_unavailable" in result.output
    assert received_options["request_delay_seconds"] == 1.0


def test_sync_price_range_rejects_reversed_dates() -> None:
    result = runner.invoke(
        app,
        [
            "sync-price-range",
            "--start-date",
            "2026-09-02",
            "--end-date",
            "2026-09-01",
            "--universe-as-of",
            "2026-08-31",
        ],
    )

    assert result.exit_code == 1
    assert "end date must not precede start date" in result.output


def test_price_coverage_prints_summary_and_gaps(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    summary = PriceCoverageSummary(
        expected_instruments=200,
        total_bars=51990,
        total_sessions=260,
        complete_sessions=250,
        incomplete_sessions=10,
        first_session=date(2025, 8, 1),
        last_session=date(2026, 8, 31),
        minimum_bars_per_session=198,
        maximum_bars_per_session=200,
        instrument_gaps=(InstrumentCoverageGap("INE000000001", "Example Ltd.", 2),),
    )
    monkeypatch.setattr(cli, "get_nifty200_price_coverage", lambda *_: summary)

    result = runner.invoke(
        app,
        ["price-coverage", "--universe-as-of", "2026-08-31"],
    )

    assert result.exit_code == 0
    assert "sessions=260, complete=250, incomplete=10" in result.output
    assert "INE000000001\tmissing_sessions=2\tExample Ltd." in result.output