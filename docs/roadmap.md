# Investment Gini Roadmap

Last updated: 2026-09-03

This is the maintained implementation-status document. The product requirements remain in the [master prompt](../Indian_Stock_Research_Decision_Engine_Master_Prompt.md), while technical decisions and boundaries remain in the [architecture proposal](architecture-proposal.md).

## Status legend

- **Complete**: acceptance criteria are implemented and verified.
- **Partial**: a tested vertical slice exists, but milestone acceptance criteria are not fully met.
- **Not started**: no production implementation exists.
- **Blocked**: an external decision, source, or dependency prevents implementation.

A milestone is complete only when its listed acceptance criteria pass, pytest, Ruff, and strict mypy pass, and source/provenance documentation is current.

## Progress summary

| Milestone | Status | Completion evidence | Next gate |
|---|---|---|---|
| 1. Foundation | Complete | Configuration, SQLite, Alembic, provenance, CLI, tests, Streamlit shell | Maintain quality gates |
| 2. Nifty 200 universe | Partial | Official current snapshot with 200 unique ISINs and source lineage | Point-in-time historical membership |
| 3. Historical prices | Complete | 268 sessions, 52,897 raw bars, official actions, deterministic query-time adjustment, membership safeguards, Stock Explorer | Maintain quality and source gates |
| 4. Technical features | Complete | Versioned indicators, official benchmark-relative strength, transparent momentum score, trend and comparison UI | Maintain quality gates |
| 5. Fundamental facts | Not started | None | Approve legal, stable source and definitions |
| 6. Research scores | Not started | None | Technical and fundamental facts |
| 7. Candidate ranking | Not started | None | Validated component scores |
| 8. Entry engine | Not started | None | Ranking and setup-state definitions |
| 9. Exit engine | Not started | None | Thesis and position state |
| 10. Portfolio and journal | Not started | None | Entry/exit decisions and risk rules |
| 11. Backtester | Not started | None | Point-in-time data and execution assumptions |
| 12. Historical validation | Not started | None | Complete research and backtest pipeline |

## Current priority

Begin Milestone 4 technical features while preserving the raw/derived boundary established in Milestone 3.

### Immediate execution plan

- [x] **M3.1 Resumable date-range ingestion**
  - Add a date-range application service and CLI command.
  - Skip weekends and classify official-archive 404 responses as non-trading or unavailable dates.
  - Continue after per-date failures and return a range summary.
  - Preserve one ingestion run and source record per archive.
  - Remain idempotent when interrupted or repeated.
  - Verified by focused tests plus a live 2026-08-31 through 2026-09-02 sync: 600 bars across three sessions; the repeated range inserted zero bars.
- [x] **M3.2 Backfill one analysis year**
  - Load at least 260 available NSE sessions for the selected Nifty 200 snapshot.
  - Rate-limit requests and use bounded retries.
  - Verify counts by session and instrument.
  - Report missing instruments, suspended securities, and incomplete sessions.
  - Verified 2025-08-01 through 2026-09-02: 268 available sessions, 52,897 raw bars, 268 distinct official archive URLs and checksums, and zero failed downloads.
  - Coverage audit reports 156 complete and 112 incomplete sessions with 703 explicit missing-row flags. Older gaps reflect current-snapshot survivorship, later listings, ISIN changes, or suspensions and must not be treated as unbiased historical membership.
- [x] **M3.3 Price query service**
  - Add application DTOs for instruments and date-bounded price series.
  - Keep Streamlit independent of SQLAlchemy and provider adapters.
  - Return provenance, freshness, adjustment status, and quality warnings.
  - Verified with focused tests and a live 268-point Reliance Industries query containing 268 archive references, raw/unadjusted status, freshness metadata, and no unresolved instrument warnings.
- [x] **M3.4 Stock Explorer UI**
  - Add searchable stock selection.
  - Add date-range controls, raw OHLC chart, volume chart, and price table.
  - Show return only with an explicit raw/unadjusted label.
  - Show coverage, source, retrieval date, and quality state.
  - Provide empty, loading, and incomplete-data states.
  - Verified with Streamlit AppTest against the populated database, desktop and mobile browser checks, stock-search interaction, date filtering from 248 to 23 sessions, nonblank responsive charts, and no runtime exceptions.
- [x] **M3.5 Corporate-action policy and ingestion**
  - Use the official NSE corporate-action publication with URL, retrieval time, checksum, and terms reference.
  - Store splits, bonuses, dividends, rights issues, and demergers with provenance; keep symbol history in the temporal instrument-symbol boundary.
  - Define deterministic adjustment factors and restatement behavior.
  - Reconcile adjusted series against documented cases.
- [x] **M3.6 Historical membership safeguards**
  - Document that point-in-time Nifty 200 compositions still require an approved historical or licensed source.
  - Prevent current-membership data from being labeled survivorship-bias-free.
  - Add temporal coverage and gap reporting.
  - This safeguard completes the Milestone 3 dependency boundary; it does not complete Milestone 2 or provide unbiased historical constituents.

### Milestone 3 completion criteria

- At least 260 trading sessions are stored with reproducible source lineage.
- Interrupted and repeated backfills resume without duplicate bars.
- Missing archives and rows produce explicit, reviewable outcomes.
- Corporate-action adjustment is deterministic, tested, and never confused with raw prices.
- Historical-universe limitations are visible in services, UI, and backtesting inputs.
- The Stock Explorer lets a user inspect a stock's history, volume, provenance, and quality.

## Milestone details

### Milestone 1: Foundation

**Status: Complete**

Delivered:

- Python `src` project, typed configuration, SQLAlchemy, Alembic, and SQLite.
- Provenance tables, quality flags, repository boundary, CLI, and Streamlit shell.
- Idempotent fixture ingestion and temporal membership queries.
- Automated pytest, Ruff, and strict mypy validation.

Completion gate: keep all quality checks passing as later milestones are added.

### Milestone 2: Verified Nifty 200 universe

**Status: Externally blocked; prospective coverage active**

Delivered:

- Official NSE Indices current-constituent provider.
- Exactly 200 unique ISINs validated and persisted.
- Explicit composition date, retrieval timestamp, URL, checksum, and terms reference.
- Prospective complete-snapshot reconciliation: additions open on the observed snapshot
  date, removals close on the preceding date, unchanged memberships retain their original
  start date, and closure evidence is traceable.
- Explicit unsupported-range reporting before the earliest stored official snapshot.

External blocker:

- Authoritative historical Nifty 200 constituents require licensed NSE Indices data that is
  not available to this project. Public index-level history does not establish membership.
- Historical dates before the earliest stored official constituent snapshot remain
  unsupported and must not be described as survivorship-bias-free.

Remaining local work:

- Continue collecting complete official constituent snapshots prospectively, including
  scheduled and exceptional reconstitutions.
- Reconcile symbol changes as separately sourced instrument-history events.

Completion criteria:

- Queries return the actual Nifty 200 composition for supported historical dates.
- Changes between snapshots are traceable and non-overlapping.
- Unsupported dates fail explicitly instead of falling back to current members.

### Milestone 3: OHLCV and corporate actions

**Status: Complete**

Delivered:

- Official NSE new-format bhavcopy ZIP parser.
- Strict `CM` / `NSE` / `STK` / `EQ` and ISIN filtering.
- Raw decimal OHLC, previous close, volume, traded value, and trade count storage.
- Provenance-aware, idempotent one-session ingestion.
- Resumable inclusive range ingestion with weekend, unavailable-archive, partial-session, and per-date failure handling.
- Rate-limited one-analysis-year backfill with bounded provider retries.
- 268 verified sessions containing 52,897 raw bars with distinct official archive lineage per session.
- Reproducible coverage reporting for complete sessions, incomplete sessions, and frequently missing current constituents.
- UI-safe temporal instrument search and date-bounded price-series DTOs with source provenance, freshness, adjustment state, and relevant quality warnings.
- Responsive Streamlit Stock Explorer with searchable selection, bounded date filtering, raw OHLC and volume charts, price table, provenance, freshness, and explicit data-quality states.
- Provenance-aware corporate-action schema, official NSE provider, CSV fallback, idempotent ingestion, and CLI sync.
- Query-time split and bonus adjustment that preserves raw bars; dividends, rights issues, and demergers remain non-adjusting evidence.
- Membership coverage service and CLI failure state for history predating imported composition evidence.
- Live official-action sync for 2025-09-02 through 2026-09-02: 192 actions with zero quality flags (3 bonuses, 3 demergers, 185 dividends, and 1 rights issue).
- Reconciled Patanjali Foods 2:1 bonus: pre-ex-date closes of 1,802.10 and 1,802.00 derive to 600.70 and 600.6667, while raw rows and ex-date values remain unchanged.
- Verified by 29 pytest tests, repository-wide Ruff, strict mypy, clean migration through revision 0003, Streamlit raw/adjusted AppTest, and responsive browser checks.

Milestone 2 remains partial: the current Nifty 200 snapshot cannot establish historical additions, removals, or survivorship-bias-free membership.

### Milestone 4: Technical features and momentum

**Status: Complete**

Delivered:

- Pure, deterministic technical feature engine over split/bonus-adjusted price-series DTOs.
- SMA 20/50/150/200, EMA 20/50, 21/63/126/252-session returns, 63-session annualized volatility, 252-session maximum drawdown and high distance, and 20-session volume ratio.
- Official Nifty 200 price-index OHLC provider using the published historical-data endpoint,
  bounded 365-day requests, strict response validation, and raw-response checksums.
- Dedicated benchmark storage, migration, idempotent range ingestion, CLI sync, and
  provenance-rich application query boundary that remains separate from constituent history.
- 63/126/252-session relative strength using stock growth divided by benchmark growth over
  common sessions, with explicit insufficient-history states.
- Versioned 100-point momentum score with visible trend, absolute momentum, relative
  momentum, risk, high-proximity, and volume contributions.
- Explicit confirmed, constructive, not-confirmed, and insufficient-history trend states.
- Adjusted-close 50/200-session moving-average overlays and common-session normalized
  stock-versus-Nifty-200 comparison chart.
- Frozen as-of filtering, formula version, source identifiers, adjustment status, and per-feature evidence windows.
- Explicit `insufficient_history` status with required and available observations; no invented fallback values.
- Stock Explorer technical table with definitions and source-series limitations.
- Focused fixtures verify independently calculated values and prove post-as-of observations cannot enter a snapshot.

Independent fixtures reconcile the moving-average slope, relative-strength formula, every
score contribution, the 100-point maximum, no-look-ahead behavior, and missing-data policy.

Scope:

- Deterministic SMA/EMA, returns, relative strength, volatility, drawdown, trend, and volume features.
- Feature values tied to an as-of date, input series, formula version, and evidence.
- Transparent momentum score with component-level explanations.

Completion criteria:

- Indicator fixtures match independently calculated expected values.
- No future observations can enter an as-of calculation.
- Insufficient history returns an explicit data status, not an invented score.
- UI explains every momentum component and source series.

### Milestone 5: Fundamental facts and definitions

**Status: Implementation complete; filing evidence pending**

Delivered:

- Source-independent, versioned metric-definition registry with unit, period type, value
  kind, formula, and reported-versus-derived classification.
- Immutable point-in-time fundamental facts with filing date, public availability timestamp,
  consolidation scope, currency, reported unit/scale, explicit data status, and complete
  source provenance.
- Restatements preserve prior reported values through explicit supersession links.
- Baseline reported metric catalog covers revenue, net profit, operating cash flow, balance
  sheet, shares outstanding, promoter holding, and promoter pledge.
- Manual CSV import requires an official filing URL, terms reference, and original artifact
  SHA-256; the exact transcription file gets its own checksum. No automatic filing scraping.
- Period-aware deduplication, timezone-aware publication timestamps, explicit missing versus
  not-applicable states, immutable definition versions, and CLI catalog/import/as-of queries.
- Raw-fact ingestion rejects derived definitions, malformed periods, future-restatement
  leakage, and invalid value/status combinations.

No company values have been imported. Milestone sign-off still requires selecting a filing
whose terms permit this use and reconciling representative reported facts against that exact
company document. Synthetic tests validate the workflow only; they are not company evidence.
The Infosys annual-report site was reviewed as a candidate on 2026-10-06, but its Terms of Use
do not provide a data-extraction license; it was not approved or imported.
The BSE Infosys financial-results listing was also reviewed; the BSE website disclaimer
prohibits reproduction, redistribution, or transmission without express written consent. It
was not approved or imported. NSE terms were not verifiable during this review.
Screener.in's current terms permit only personal, non-commercial transitory viewing and
prohibit copying; they do not authorize persistent database ingestion. No Screener data has
been copied or imported.

Scope:

- Select and approve the legal basis for each manually supplied issuer/exchange filing.
- Populate and independently reconcile revenue, profit, cash flow, balance sheet, share count,
  and ownership facts against cited original filings.
- Define derived metric formulas separately before any derived facts are computed.

Completion criteria:

- Revenue, profit, cash flow, balance sheet, share count, ownership, and filing provenance are
  populated and queryable point in time from an approved documented filing.
- Restatements preserve history and supersession relationships.
- Missing and non-applicable values remain distinct.
- Selected metrics reconcile against documented company filings.

### Milestone 6: Quality, earnings, valuation, and financial-health scores

**Status: Not started**

Scope:

- Versioned score definitions, weights, normalization, caps, and missing-data policies.
- Business quality, earnings momentum, valuation, and financial-health components.
- Sector-aware treatment where accounting economics differ materially.

Completion criteria:

- Every score is reproducible from stored facts and a versioned configuration.
- Every contribution and penalty is inspectable.
- Missing evidence lowers confidence and never silently becomes zero.
- Known-company fixtures exercise normal, weak, and insufficient-data cases.

### Milestone 7: Candidate ranking

**Status: Not started**

Scope:

- Combine approved component scores into ranked research candidates.
- Add eligibility gates, confidence, freshness, and data-quality penalties.
- Provide ranking explanations and comparison views.

Completion criteria:

- Rankings are deterministic for an as-of date and model version.
- Ineligible and low-confidence companies are clearly separated.
- Users can trace rank differences to facts and score components.
- Historical rankings use only information available at the time.

### Milestone 8: Entry engine

**Status: Not started**

Scope:

- Model setup states and disciplined entry conditions rather than exact-price predictions.
- Include trend, base, breakout/pullback, valuation, liquidity, and risk evidence.
- Produce `WAIT`, `WATCH`, `REVIEW`, or paper-entry candidates with invalidation conditions.

Completion criteria:

- Rules are versioned, deterministic, and fully explained.
- No rule claims certainty or predicts tomorrow's price.
- Every candidate includes evidence, invalidation, freshness, and risk context.
- Conflicting conditions resolve through documented precedence.

### Milestone 9: Exit engine and thesis monitoring

**Status: Not started**

Scope:

- Store thesis, expected evidence, invalidation, review dates, and material events.
- Evaluate thesis breaks, governance concerns, financial deterioration, valuation, and price structure.
- Produce `HOLD`, `REVIEW`, `REDUCE`, or `EXIT` research states.

Completion criteria:

- Thesis and governance evidence can override price optimism.
- Temporary weakness does not automatically become a full exit.
- Each state transition is timestamped, reproducible, and explained.
- No broker order is generated.

### Milestone 10: Paper portfolio and decision journal

**Status: Not started**

Scope:

- Paper accounts, positions, cash, transactions, sizing, sector exposure, and risk limits.
- Decision journal connecting thesis, entry, reviews, changes, and exit.
- Portfolio-level concentration and drawdown monitoring.

Completion criteria:

- Holdings reconcile from an immutable transaction ledger.
- Sizing obeys configured position, sector, and rupee-risk limits.
- Every simulated action links to the evidence and rule version that produced it.
- UI distinguishes research candidates from owned paper positions.

### Milestone 11: Point-in-time backtester

**Status: Not started**

Scope:

- Event-driven simulation with signal cutoff, next-session execution, costs, slippage, liquidity, and delistings.
- Point-in-time universes, fundamentals, corporate actions, and model versions.
- Benchmark, attribution, turnover, drawdown, and exposure analytics.

Completion criteria:

- Tests detect look-ahead and survivorship leakage.
- Execution timing and price assumptions are explicit.
- Results are reproducible from a frozen dataset and configuration.
- Reports include CAGR, volatility, drawdown, turnover, hit rate, and benchmark comparison.

### Milestone 12: Historical validation and readiness review

**Status: Not started**

Scope:

- Validate known historical cases, edge cases, and failure modes.
- Run sensitivity, ablation, regime, and data-quality analyses.
- Conduct a paper-trading period and document operational procedures.

Completion criteria:

- Expected historical decisions are explained case by case.
- Conclusions remain reasonable under documented parameter perturbations.
- Known limitations, source licenses, reproducibility steps, and model risks are published.
- A readiness review decides whether to continue paper use; live autonomous trading remains out of scope.

## Cross-cutting rules

These apply to every milestone:

1. The application is research and decision support, not financial advice or autonomous trading.
2. UI modules consume application DTOs and services only.
3. Raw facts remain separate from derived features, scores, and decisions.
4. Every external fact retains provider, source identifier, retrieval time, checksum, and effective/availability dates where applicable.
5. Point-in-time calculations must not use information unavailable at the as-of timestamp.
6. Missing, stale, estimated, and non-applicable data remain explicit.
7. Formulas, rules, weights, and assumptions are versioned and explainable.
8. New behavior includes focused tests proportional to its risk.
9. pytest, Ruff, and strict mypy must pass before a task or milestone is marked complete.
10. Raw and adjusted price series must never be mislabeled or silently mixed.

## Update procedure

After each implementation slice:

1. Check completed task boxes and add concise evidence.
2. Update the progress summary and milestone status.
3. Record new limitations or external blockers.
4. Run the milestone's focused tests plus the full quality suite.
5. Mark a milestone complete only when all acceptance criteria are met.
