# Investment Gini

A local, research-first decision-support laboratory for Indian equities.

This project does not provide financial advice or execute trades. Historical results do not guarantee future returns, and all decisions remain the user's responsibility.

## Development

Requires Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
investment-gini init-db
investment-gini import-universe tests/fixtures/universe.csv
investment-gini sync-nifty200 --as-of 2026-08-31
investment-gini sync-prices --session-date 2026-09-02 --universe-as-of 2026-08-31
investment-gini sync-price-range --start-date 2025-08-01 --end-date 2026-09-02 --universe-as-of 2026-08-31 --request-delay-seconds 1
investment-gini price-coverage --universe-as-of 2026-08-31
investment-gini sync-corporate-actions --start-date 2025-09-02 --end-date 2026-09-02 --universe-as-of 2026-09-02
investment-gini membership-coverage --start-date 2025-09-02 --end-date 2026-09-02
investment-gini members --as-of 2024-06-01
pytest
ruff check .
mypy src
streamlit run src/investment_gini/ui/app.py
```

The Streamlit UI is available at `http://localhost:8501` while the final command is running. Its Stock Explorer provides searchable Nifty 200 selection, date-bounded raw or split/bonus-adjusted OHLC and volume charts, a price table, a versioned as-of technical snapshot, source lineage, retrieval freshness, and data-quality warnings. A separate tab summarizes stored coverage.

## Universe CSV

Universe imports require these columns:

```text
universe,universe_version,symbol,isin,company_name,exchange,effective_from,effective_to,sector,industry
```

Dates use ISO `YYYY-MM-DD`. `effective_to`, `sector`, and `industry` may be empty. Missing identifiers, invalid dates, malformed rows, and overlapping membership intervals are retained as explicit data-quality results. Reimporting an identical file is idempotent.

The committed file under `tests/fixtures` contains synthetic data only. It is not an official Nifty 200 constituent file.

For real current constituents, `sync-nifty200` downloads the official NSE Indices constituent CSV. The CSV does not contain its own composition date, so `--as-of` must be confirmed from the official index page and supplied explicitly. A current snapshot is not historical membership data and must not be used by itself for historical backtests.

`sync-prices` downloads one official NSE cash-market bhavcopy and stores raw, unadjusted EQ OHLCV rows for the selected Nifty 200 snapshot. `sync-price-range` does the same for an inclusive date range, skips weekends and complete sessions, resumes partial sessions by requesting only missing ISINs, rate-limits archive requests, and reports unavailable archives separately from failures. `price-coverage` reports complete and incomplete sessions plus the current constituents most often absent from the stored history. `--session-date` is the trading session; `--universe-as-of` selects the separately dated composition snapshot. Using a current composition for old sessions introduces survivorship bias, and older sessions can be incomplete because of later listings, ISIN changes, or suspended securities.

`sync-corporate-actions` downloads the official NSE corporate-action publication for an inclusive ex-date range and retains actions for the selected Nifty 200 snapshot. Raw bars never change. The adjusted query mode derives split- and bonus-adjusted prices and volumes at read time from verified actions. Dividends, rights issues, and demergers remain provenance-linked evidence but do not change this price-return series. See the [corporate-action source and formula policy](docs/data-sources/nse-corporate-actions.md).

`membership-coverage` fails when a requested period predates imported Nifty 200 membership evidence. This safeguard prevents unsupported history from being labeled point-in-time or survivorship-bias-free; it does not supply the historical compositions still required to complete Milestone 2.

`fundamental-metrics` lists the versioned reported-fact catalog. `import-fundamentals` accepts
manually transcribed facts from a filing only when the operator supplies the original filing
URL, terms reference, and filing artifact SHA-256. The application does not crawl or download
filings. `fundamentals --isin ... --as-of ...` queries the latest reported facts that were
available by a timezone-aware timestamp. See the
[fundamental filing import contract](docs/data-sources/fundamental-facts.md).

## Current Scope

The current foundation provides configuration, provenance-aware universe, raw market-price,
corporate-action, benchmark, and fundamental-fact storage; versioned migrations;
membership-coverage safeguards; searchable instrument and raw/adjusted price-series
services; deterministic technical features and momentum; a CLI; and a Streamlit Stock
Explorer and coverage dashboard. Fundamental filing imports are manual and source-cited;
the M5 roadmap remains open until documented filing facts are approved and reconciled.
Portfolio management and backtesting remain deferred.

See the [implementation roadmap](docs/roadmap.md) for milestone status, completion criteria, and
the current execution checklist. The [architecture proposal](docs/architecture-proposal.md)
records technical decisions and boundaries, while the
[master prompt](Indian_Stock_Research_Decision_Engine_Master_Prompt.md) remains the product
requirements source.