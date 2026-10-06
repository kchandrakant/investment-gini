from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from investment_gini.application import (
    get_fundamental_facts_as_of,
    get_fundamental_metric_catalog,
    get_members,
    get_nifty200_membership_coverage,
    get_nifty200_price_coverage,
    import_corporate_actions_csv,
    import_fundamental_csv,
    import_universe_csv,
    initialize_database,
    sync_nifty200,
    sync_nifty200_benchmark,
    sync_nifty200_corporate_actions,
    sync_nifty200_price_range,
    sync_nifty200_prices,
)

app = typer.Typer(help="Investment Gini local research utilities.", no_args_is_help=True)


@app.command("init-db")
def init_db() -> None:
    """Apply all database migrations."""
    initialize_database()
    typer.echo("Database initialized.")


@app.command("import-universe")
def import_universe(
    path: Annotated[Path, typer.Argument(exists=True, readable=True, dir_okay=False)],
) -> None:
    """Import a validated universe membership CSV file."""
    summary = import_universe_csv(path)
    typer.echo(
        f"Run {summary.run_id}: inserted={summary.inserted}, skipped={summary.skipped}, "
        f"quality_flags={summary.quality_flags}"
    )


@app.command("import-corporate-actions")
def import_corporate_actions(
    path: Annotated[Path, typer.Argument(exists=True, readable=True, dir_okay=False)],
    source_name: Annotated[
        str,
        typer.Option(help="Stable name of the official or licensed source."),
    ],
    terms_reference: Annotated[
        str,
        typer.Option(help="URL or document reference governing use of the source."),
    ],
) -> None:
    """Import provenance-linked corporate actions from a validated CSV export."""
    summary = import_corporate_actions_csv(path, source_name, terms_reference)
    typer.echo(
        f"Run {summary.run_id}: inserted={summary.inserted}, skipped={summary.skipped}, "
        f"quality_flags={summary.quality_flags}"
    )


@app.command("import-fundamentals")
def import_fundamentals(
    path: Annotated[Path, typer.Argument(exists=True, readable=True, dir_okay=False)],
    source_name: Annotated[str, typer.Option(help="Name of the filing issuer/source.")],
    source_url: Annotated[
        str, typer.Option(help="URL of the original official filing document.")
    ],
    terms_reference: Annotated[
        str, typer.Option(help="Terms or legal basis for use of this filing.")
    ],
    source_artifact_checksum: Annotated[
        str,
        typer.Option(help="SHA-256 of the original filing artifact, not the CSV."),
    ],
) -> None:
    """Import manually transcribed point-in-time facts from an official filing."""
    try:
        summary = import_fundamental_csv(
            path,
            source_name,
            source_url,
            terms_reference,
            source_artifact_checksum,
        )
    except ValueError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Run {summary.run_id}: inserted={summary.inserted}, skipped={summary.skipped}, "
        f"quality_flags={summary.quality_flags}"
    )


@app.command("fundamental-metrics")
def fundamental_metrics() -> None:
    """List supported reported fundamental metrics and period semantics."""
    for definition in get_fundamental_metric_catalog():
        typer.echo(
            f"{definition.code}\t{definition.version}\t{definition.period_type}\t"
            f"{definition.value_kind}\t{definition.name}"
        )


@app.command("fundamentals")
def fundamentals(
    isin: Annotated[str, typer.Option(help="Instrument ISIN.")],
    as_of: Annotated[
        str,
        typer.Option(help="Information cutoff timestamp with timezone, ISO-8601."),
    ],
) -> None:
    """Query the latest reported fundamental facts known by an as-of timestamp."""
    try:
        cutoff = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("as-of timestamp must include an explicit timezone")
    except ValueError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    facts = get_fundamental_facts_as_of(isin, cutoff)
    if not facts:
        typer.echo("No fundamental facts available by that timestamp.")
        return
    for fact in facts:
        typer.echo(
            f"{fact.metric_code}\t{fact.period_start}/{fact.period_end}\t"
            f"{fact.consolidation_scope}\t{fact.value if fact.value is not None else fact.status} "
            f"{fact.unit}\tfiled={fact.filing_date}\tavailable={fact.available_at.isoformat()}\t"
            f"source={fact.source_identifier}\ttranscription_sha256={fact.source_checksum}\t"
            f"filing_sha256={fact.source_artifact_checksum or 'not-recorded'}"
        )


@app.command("sync-corporate-actions")
def sync_corporate_actions_command(
    start_date: Annotated[str, typer.Option(help="Inclusive ex-date in YYYY-MM-DD format.")],
    end_date: Annotated[str, typer.Option(help="Inclusive ex-date in YYYY-MM-DD format.")],
    universe_as_of: Annotated[
        str,
        typer.Option(help="Nifty 200 composition snapshot in YYYY-MM-DD format."),
    ],
) -> None:
    """Download official NSE actions for instruments in a Nifty 200 snapshot."""
    try:
        range_start = date.fromisoformat(start_date)
        range_end = date.fromisoformat(end_date)
        composition_date = date.fromisoformat(universe_as_of)
        summary = sync_nifty200_corporate_actions(
            range_start, range_end, composition_date
        )
    except (RuntimeError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Run {summary.run_id}: inserted={summary.inserted}, skipped={summary.skipped}, "
        f"quality_flags={summary.quality_flags}; only splits and bonuses adjust prices"
    )


@app.command("members")
def members(
    as_of: Annotated[str, typer.Option(help="Historical date in YYYY-MM-DD format.")],
    universe: Annotated[str, typer.Option()] = "NIFTY 200",
) -> None:
    """List members effective on a historical date."""
    try:
        effective_date = date.fromisoformat(as_of)
    except ValueError as error:
        raise typer.BadParameter("must use YYYY-MM-DD format", param_hint="--as-of") from error

    for member in get_members(universe, effective_date):
        typer.echo(f"{member.isin}\t{member.company_name}\t{member.sector or 'Unknown'}")


@app.command("sync-nifty200")
def sync_nifty200_command(
    as_of: Annotated[
        str,
        typer.Option(help="Composition date confirmed by the official index page (YYYY-MM-DD)."),
    ],
) -> None:
    """Download and import the official current Nifty 200 snapshot."""
    try:
        effective_date = date.fromisoformat(as_of)
    except ValueError as error:
        raise typer.BadParameter("must use YYYY-MM-DD format", param_hint="--as-of") from error

    try:
        summary = sync_nifty200(effective_date)
    except ValueError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Run {summary.run_id}: inserted={summary.inserted}, skipped={summary.skipped}, "
        f"quality_flags={summary.quality_flags}"
    )


@app.command("sync-prices")
def sync_prices_command(
    session_date: Annotated[
        str,
        typer.Option(help="NSE trading session in YYYY-MM-DD format."),
    ],
    universe_as_of: Annotated[
        str,
        typer.Option(
            help="Nifty 200 composition snapshot to use; this controls survivorship bias."
        ),
    ],
) -> None:
    """Download official raw, unadjusted NSE OHLCV for one session."""
    try:
        trading_date = date.fromisoformat(session_date)
        composition_date = date.fromisoformat(universe_as_of)
    except ValueError as error:
        raise typer.BadParameter(
            "dates must use YYYY-MM-DD format",
            param_hint="--session-date",
        ) from error
    try:
        summary = sync_nifty200_prices(trading_date, composition_date)
    except (RuntimeError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Run {summary.run_id}: inserted={summary.inserted}, skipped={summary.skipped}, "
        f"quality_flags={summary.quality_flags}; prices are raw and unadjusted"
    )


@app.command("sync-price-range")
def sync_price_range_command(
    start_date: Annotated[str, typer.Option(help="Inclusive start date in YYYY-MM-DD format.")],
    end_date: Annotated[str, typer.Option(help="Inclusive end date in YYYY-MM-DD format.")],
    universe_as_of: Annotated[
        str,
        typer.Option(
            help="Nifty 200 composition snapshot to use; this controls survivorship bias."
        ),
    ],
    request_delay_seconds: Annotated[
        float,
        typer.Option(
            min=0,
            help="Minimum delay between official archive requests.",
        ),
    ] = 1.0,
) -> None:
    """Resume official raw NSE OHLCV ingestion across a date range."""
    try:
        range_start = date.fromisoformat(start_date)
        range_end = date.fromisoformat(end_date)
        composition_date = date.fromisoformat(universe_as_of)
    except ValueError as error:
        raise typer.BadParameter(
            "dates must use YYYY-MM-DD format",
            param_hint="--start-date",
        ) from error
    try:
        summary = sync_nifty200_price_range(
            range_start,
            range_end,
            composition_date,
            request_delay_seconds=request_delay_seconds,
        )
    except ValueError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Range {summary.start_date} to {summary.end_date}: "
        f"ingested={summary.sessions_ingested}, "
        f"already_complete={summary.sessions_already_complete}, "
        f"weekends={summary.weekends_skipped}, "
        f"unavailable={summary.archives_unavailable}, "
        f"failed={summary.sessions_failed}, incomplete={summary.incomplete_sessions}, "
        f"bars_inserted={summary.bars_inserted}, "
        f"bars_skipped={summary.bars_skipped}, quality_flags={summary.quality_flags}; "
        "prices are raw and unadjusted"
    )
    for outcome in summary.outcomes:
        if outcome.status in {"archive_unavailable", "failed"} or outcome.missing_isins:
            missing = ",".join(outcome.missing_isins)
            detail = outcome.detail or ""
            typer.echo(f"{outcome.session_date}\t{outcome.status}\t{detail}\t{missing}")
    if summary.sessions_failed:
        raise typer.Exit(code=1)


@app.command("sync-benchmark")
def sync_benchmark_command(
    start_date: Annotated[str, typer.Option(help="Inclusive start date in YYYY-MM-DD format.")],
    end_date: Annotated[str, typer.Option(help="Inclusive end date in YYYY-MM-DD format.")],
    request_delay_seconds: Annotated[
        float,
        typer.Option(min=0, help="Minimum delay between official index requests."),
    ] = 1.0,
) -> None:
    """Download official Nifty 200 index OHLC history in bounded requests."""
    try:
        range_start = date.fromisoformat(start_date)
        range_end = date.fromisoformat(end_date)
        summary = sync_nifty200_benchmark(
            range_start,
            range_end,
            request_delay_seconds=request_delay_seconds,
        )
    except (RuntimeError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Benchmark {summary.start_date} to {summary.end_date}: requests={summary.requests}, "
        f"bars_inserted={summary.bars_inserted}, bars_skipped={summary.bars_skipped}, "
        f"quality_flags={summary.quality_flags}; this is index-level evidence, not "
        "historical constituent evidence"
    )


@app.command("price-coverage")
def price_coverage_command(
    universe_as_of: Annotated[
        str,
        typer.Option(help="Nifty 200 composition snapshot in YYYY-MM-DD format."),
    ],
    gap_limit: Annotated[
        int,
        typer.Option(min=0, help="Maximum number of missing-instrument rows to print."),
    ] = 20,
) -> None:
    """Report raw price-session completeness for a Nifty 200 snapshot."""
    try:
        composition_date = date.fromisoformat(universe_as_of)
    except ValueError as error:
        raise typer.BadParameter(
            "must use YYYY-MM-DD format", param_hint="--universe-as-of"
        ) from error
    try:
        summary = get_nifty200_price_coverage(composition_date)
    except ValueError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Coverage {summary.first_session} to {summary.last_session}: "
        f"sessions={summary.total_sessions}, complete={summary.complete_sessions}, "
        f"incomplete={summary.incomplete_sessions}, bars={summary.total_bars}, "
        f"bars_per_session={summary.minimum_bars_per_session}-"
        f"{summary.maximum_bars_per_session}, expected_instruments="
        f"{summary.expected_instruments}; prices are raw and unadjusted"
    )
    for gap in summary.instrument_gaps[:gap_limit]:
        typer.echo(
            f"{gap.isin}\tmissing_sessions={gap.missing_sessions}\t{gap.company_name}"
        )


@app.command("membership-coverage")
def membership_coverage_command(
    start_date: Annotated[str, typer.Option(help="Inclusive start date in YYYY-MM-DD format.")],
    end_date: Annotated[str, typer.Option(help="Inclusive end date in YYYY-MM-DD format.")],
) -> None:
    """Report whether imported Nifty 200 evidence supports a historical range."""
    try:
        range_start = date.fromisoformat(start_date)
        range_end = date.fromisoformat(end_date)
        summary = get_nifty200_membership_coverage(range_start, range_end)
    except ValueError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        f"Membership evidence: snapshots={summary.snapshot_count}, "
        f"first={summary.first_snapshot}, last={summary.last_snapshot}, "
        f"point_in_time_covered={str(summary.is_point_in_time_covered).lower()}"
    )
    if not summary.is_point_in_time_covered:
        typer.echo(
            "Requested history predates imported membership evidence; do not label results "
            "survivorship-bias-free."
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
