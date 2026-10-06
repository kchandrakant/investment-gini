# Architecture Proposal

## 1. Objective

Build a local, research-first decision-support application for medium-term investing in Indian equities. The application will rank Nifty 200 candidates using transparent evidence, identify entry and exit conditions, support paper portfolios, and backtest rules without look-ahead or survivorship bias.

It will not predict short-term prices, execute trades, or present recommendations as financial advice.

Priority order:

1. Correctness
2. Reproducibility
3. Explainability
4. Backtestability
5. Usability
6. Visual polish

## 2. Assumptions and Open Questions

### Proposed assumptions

- V1 is a single-user application running locally in VS Code.
- Python 3.12 is the implementation language.
- Streamlit is the V1 user interface.
- SQLite is the V1 transactional and analytical store.
- Daily end-of-day data is sufficient for V1; intraday data is excluded.
- Nifty 200 is the only built-in universe in V1.
- Data ingestion is provider-neutral. No provider is treated as available until access, licensing, historical depth, and field definitions are verified.
- Fundamental data can initially be imported through validated files when a compliant automated source is unavailable.
- Strategy decisions are deterministic. AI-generated research summaries remain optional and cannot alter scores directly.
- All persisted timestamps are UTC; exchange sessions and reporting dates use `Asia/Kolkata` semantics where applicable.

### Essential decisions before data ingestion

1. Which legally usable data source or licensed account will supply historical OHLCV?
2. Which source will supply period-correct fundamentals and their public availability dates?
3. Is manual CSV import acceptable as the first provider for universe and fundamental data?

These questions do not block Milestone 1 because provider contracts and fixture-based tests can be implemented first.

## 3. User Interface Decision

V1 should have a user interface. A research tool benefits from sortable tables, score drill-downs, charts, warnings, and portfolio state that are cumbersome to use through a CLI alone.

Use **Streamlit** for V1 because it:

- supports data tables, filters, forms, and Plotly charts with little presentation code;
- runs locally without a separate frontend build or API deployment;
- keeps iteration fast while data definitions and scoring rules are still changing;
- is sufficient for a single-user personal research laboratory.

The UI must remain a thin adapter over application services. It must not calculate indicators, score stocks, fetch provider data, or execute portfolio rules. This preserves a future path to a React/FastAPI interface without rewriting the research engine.

Initial screens:

- **Dashboard:** regime, leading candidates, holdings, alerts, and data freshness.
- **Screener:** sortable component scores, raw metrics, confidence, and filters.
- **Stock Detail:** evidence, price chart, score decomposition, setup, thesis, invalidation, and provenance.
- **Watchlist:** workflow state, readiness, reasons to wait, and alerts.
- **Portfolio:** positions, risk, concentration, thesis status, and exit warnings.
- **Backtest:** performance, drawdowns, trades, benchmarks, and regime analysis.
- **Journal:** decisions, outcomes, rule adherence, and lessons.

Only Dashboard, Screener, and a minimal Stock Detail view belong in the first end-to-end slice.

## 4. Simplest Viable Architecture

Use a modular monolith with explicit dependency direction:

```text
Providers / File imports
          |
          v
Ingestion and validation
          |
          v
Normalized repositories (SQLite)
          |
          v
Features -> Scores -> Entry/Exit rules
          |                  |
          +------> Ranking <-+
                     |
          Application services
             |             |
             v             v
        Streamlit UI    Backtester
```

Module boundaries:

- **domain:** immutable financial concepts and result types;
- **providers:** external-source contracts and provider-specific adapters;
- **ingestion:** validation, normalization, provenance, and persistence orchestration;
- **repositories:** storage interfaces and SQLite implementations;
- **features:** deterministic point-in-time metric calculations;
- **scoring:** decomposable score components and ranking;
- **rules:** entry, exit, risk, and regime evaluation;
- **portfolio:** paper positions, trades, sizing, and journal;
- **backtest:** event clock, point-in-time queries, execution simulation, and analytics;
- **application:** use cases consumed by UI and CLI;
- **ui:** Streamlit pages and presentation formatting only.

Avoid FastAPI in V1. Add it only when another client or process genuinely needs a stable network API.

## 5. Technology Choices

| Concern | Choice | Rationale |
|---|---|---|
| Runtime | Python 3.12 | Mature data ecosystem and stable typing support |
| Packaging | `pyproject.toml` | One standard location for dependencies and tooling |
| Data frames | pandas | Appropriate for daily equity research and provider normalization |
| Numeric calculations | NumPy | Efficient array calculations beneath features and analytics |
| Validation | Pydantic | Typed validation at provider and configuration boundaries |
| Database | SQLite | Reproducible, inspectable, zero-service local storage |
| ORM/migrations | SQLAlchemy + Alembic | Explicit schema, transactions, and controlled migrations |
| UI | Streamlit | Fast local interaction for a single-user research tool |
| Charts | Plotly | Interactive price, score, and backtest charts |
| Configuration | TOML | Typed application and strategy configuration without code changes |
| Testing | pytest | Unit, integration, and point-in-time regression tests |
| Quality | Ruff + mypy | Fast linting/formatting and practical static checks |

Dependencies should be added only when the slice that needs them is implemented.

## 6. Proposed Repository Structure

```text
investment-gini/
|-- pyproject.toml
|-- README.md
|-- config/
|   |-- app.toml
|   |-- scoring.toml
|   |-- risk.toml
|   `-- backtest.toml
|-- data/
|   |-- imports/.gitkeep
|   `-- investment_gini.db
|-- docs/
|   |-- architecture-proposal.md
|   |-- methodology/
|   `-- data-sources/
|-- src/investment_gini/
|   |-- domain/
|   |-- providers/
|   |-- ingestion/
|   |-- repositories/
|   |-- features/
|   |-- scoring/
|   |-- rules/
|   |-- portfolio/
|   |-- backtest/
|   |-- application/
|   |-- ui/
|   `-- cli.py
`-- tests/
    |-- unit/
    |-- integration/
    |-- regression/
    `-- fixtures/
```

Generated databases and imported licensed data must not be committed. Small synthetic fixtures may be committed for tests.

## 7. Initial Database Schema

SQLite tables use integer surrogate primary keys, explicit natural uniqueness constraints, ISO currency codes, and UTC ingestion timestamps. Numeric financial values must retain units and must not be mixed across definitions.

### Identity and universe

- `instruments`: security identity, exchange, symbol, ISIN, company name, sector, industry, currency, active dates.
- `instrument_symbols`: symbol history with effective date ranges.
- `universes`: named and versioned universe definitions.
- `universe_memberships`: instrument membership with `effective_from` and `effective_to`.

### Provenance and ingestion

- `data_sources`: provider identity, source class, terms reference, and reliability tier.
- `ingestion_runs`: provider, requested range, start/end timestamps, status, and error summary.
- `source_records`: source URL or document identifier, retrieval timestamp, checksum, reported period, and availability timestamp.
- `data_quality_flags`: entity, field, severity, reason, observed value, expected condition, and resolution state.

### Market and fundamental facts

- `price_bars`: instrument, session date, OHLCV, adjusted fields, adjustment status, source record.
- `corporate_actions`: action type, ex-date, record date, ratio/value, verification status, source record.
- `fundamental_facts`: instrument, metric code, value, unit, fiscal period, period end, reported date, public availability timestamp, statement type, restatement version, source record.
- `estimates`: optional future table for provider-qualified analyst estimates with as-of timestamps.

### Derived research data

- `feature_snapshots`: instrument, as-of date, feature code, value, status, calculation version, inputs checksum.
- `score_snapshots`: instrument, as-of date, component, score, confidence, scoring version.
- `score_evidence`: score snapshot, metric, raw value, normalized value, contribution, threshold, status, explanation.
- `market_regimes`: as-of date, classification, evidence, calculation version.
- `research_theses`: instrument, version, status, thesis, risks, invalidation conditions, created/updated timestamps.
- `watchlist_items`: instrument, workflow state, setup state, notes, created/updated timestamps.

### Portfolio and testing

- `portfolios`: name, type (`paper` initially), base currency, created timestamp.
- `positions`: portfolio, instrument, quantity, average cost, opened/closed timestamps.
- `orders`: simulated intent, signal timestamp, execution timestamp, side, quantity, expected/actual price, status.
- `trades`: simulated fill, costs, slippage, realized result, linked decision.
- `journal_entries`: decision type, rationale, score snapshot references, thesis version, rule trigger, lesson.
- `backtest_runs`: configuration checksum, code version, data cutoff, universe version, status, timestamps.
- `backtest_equity`: run, date, equity, cash, exposure, benchmark values.
- `backtest_trades`: run-specific immutable simulated trades and costs.
- `backtest_metrics`: run, metric code, value, period or regime.

Critical uniqueness examples:

- one price bar per instrument, session, provider, and adjustment basis;
- one universe membership record per instrument and effective interval;
- one fundamental fact per instrument, metric definition, period, statement basis, restatement version, and provider;
- one derived feature per instrument, as-of date, feature code, and calculation version.

## 8. Data Provider Abstraction

Provider adapters return validated domain records and never write directly to the database.

```python
class UniverseProvider(Protocol):
    def fetch_memberships(self, universe: str, as_of: date) -> ProviderBatch[UniverseMembership]: ...

class PriceProvider(Protocol):
    def fetch_daily_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> ProviderBatch[PriceBar]: ...

class FundamentalProvider(Protocol):
    def fetch_facts(
        self, instrument: InstrumentRef, known_at: datetime
    ) -> ProviderBatch[FundamentalFact]: ...

class CorporateActionProvider(Protocol):
    def fetch_actions(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> ProviderBatch[CorporateAction]: ...
```

Every `ProviderBatch` includes:

- provider and source identifiers;
- retrieval timestamp;
- requested and returned coverage;
- raw-record checksum;
- warnings and field-level quality flags;
- records with reported dates and public availability timestamps where applicable.

The ingestion service performs schema validation, idempotency checks, discrepancy detection, normalization, and transaction handling. Raw source files may be retained only when licensing permits it.

The first adapter should be `CsvImportProvider`, using documented schemas and synthetic fixtures. Automated providers are selected only after a source evaluation records legality, terms, field coverage, historical membership, corporate actions, publication timestamps, stability, and cost.

## 9. Scoring Interfaces

Scores are independent, decomposable, versioned, and evaluated as of a timestamp.

```python
class ScoreComponent(Protocol):
    @property
    def name(self) -> ScoreName: ...

    def evaluate(self, context: PointInTimeContext) -> ComponentScore: ...

@dataclass(frozen=True)
class ComponentScore:
    name: ScoreName
    value: Decimal | None
    confidence: Decimal
    status: DataStatus
    evidence: tuple[ScoreEvidence, ...]
    calculation_version: str

class RankingPolicy(Protocol):
    def rank(
        self,
        components: Mapping[ScoreName, ComponentScore],
        config: RankingConfig,
    ) -> RankingResult: ...
```

V1 components:

- `QualityScore`
- `EarningsScore`
- `MomentumScore`
- `ValuationScore`
- `FinancialHealthScore`
- `RiskAssessment` as a separate overlay
- `SetupScore`

Default conceptual weights are configurable and sum to 100% across eligible components. A missing component is not zero. The ranking policy must apply an explicit configured missing-data policy, reduce confidence, and expose the decision in evidence.

Each evidence item records raw value, unit, comparison group, normalization method, threshold or percentile, weighted contribution, data status, source references, and human-readable reason.

Sector-aware normalization should use point-in-time peer groups. It must fall back to broader groups only through an explicit, recorded policy.

## 10. Entry and Exit Rule Interfaces

Rules return decisions and evidence; they do not place orders.

```python
class DecisionRule(Protocol):
    @property
    def rule_id(self) -> str: ...

    def evaluate(self, context: DecisionContext) -> RuleEvaluation: ...

@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    outcome: RuleOutcome
    severity: Severity
    evidence: tuple[RuleEvidence, ...]
    evaluated_at: datetime
    rule_version: str
```

The `EntryEngine` combines applicable rules into one of:

- `NOT_READY`
- `WATCH`
- `PREPARE`
- `BUY_CANDIDATE`
- `BUY_CONFIRMATION`

Initial entry families:

- breakout entry;
- constructive pullback entry;
- valuation entry for a fundamentally qualified stock.

The `ExitEngine` evaluates independently:

- thesis break;
- earnings deterioration;
- technical invalidation;
- valuation reduce/exit;
- trailing winner protection.

Its possible actions are `HOLD`, `REVIEW`, `REDUCE`, and `EXIT`. A configured precedence policy resolves conflicting rules. Thesis-break and severe governance evidence can override price-based optimism, while temporary earnings weakness must not automatically trigger a full exit.

Every entry decision stores a setup-specific invalidation level or condition. Position sizing is a separate service using rupee risk, entry, invalidation, volatility, and portfolio/sector caps.

## 11. Initial Backtesting Architecture

Use a deterministic daily event-driven simulator rather than a vector-only backtest. The same feature, scoring, entry, exit, and sizing services used by the application must be called through a point-in-time context.

Daily cycle:

1. Advance simulation clock to an exchange session.
2. Resolve universe membership effective on that date.
3. Expose only market data available by the configured signal cutoff.
4. Expose fundamentals whose public availability timestamp is not later than the simulation clock.
5. Calculate features and scores using versioned configuration.
6. Evaluate exits before new entries according to configured policy.
7. Generate simulated orders.
8. Fill orders using the configured next-session execution model.
9. Apply brokerage, exchange charges, STT, GST, stamp duty, and slippage from versioned cost configuration.
10. Mark positions and record immutable daily state.

Required safeguards:

- point-in-time universe membership;
- public availability timestamps for fundamentals;
- no forward-filled facts before publication;
- corporate-action-aware price series;
- delisted security handling when source data permits;
- deterministic ordering and random seeds;
- immutable run configuration and data checksums;
- explicit benchmark series and calendars;
- no use of current database state beyond the run's declared cutoff.

Testing layers:

- unit tests for indicators, scores, costs, sizing, and performance formulas;
- integration tests for provider-to-database normalization;
- temporal tests designed to fail if future data leaks into a decision;
- regression tests using small synthetic histories with known trades and metrics;
- later validation against manually reconstructed historical cases.

Development, validation, and out-of-sample intervals are configuration, not hard-coded logic.

## 12. Highest-Risk Problems

1. **Period-correct fundamental data:** publication timestamps and restatements are often harder to obtain than metric values.
2. **Historical Nifty 200 membership:** current constituents cannot support unbiased historical tests.
3. **Corporate actions and identifier history:** symbol changes, demergers, delistings, bonuses, and rights issues can corrupt series.
4. **Data rights and provider stability:** technically accessible data may not be legally reusable or operationally dependable.
5. **Metric definition drift:** ROCE, EPS, debt, free cash flow, and adjusted prices can differ materially across providers.
6. **Sector comparability:** banks, insurers, and non-financial firms need different financial and valuation definitions.
7. **False precision from missing data:** absent values must reduce confidence rather than become passes, failures, or zeros.
8. **Backtest leakage:** joins, revisions, rolling windows, and signal/execution timing can introduce subtle look-ahead bias.
9. **Overfitting:** many thresholds on a 200-stock universe can produce fragile historical results.
10. **Recommendation language:** UI labels and explanations must remain decision support, not imply certainty or personalized financial advice.

Mitigation starts with provenance-first storage, synthetic point-in-time tests, explicit metric definitions, immutable configuration, and a small initial rule set.

## 13. Milestone 1: Foundation

### Goal

Create a runnable local skeleton that proves configuration, domain boundaries, persistence, provenance, and testing before any external data dependency is introduced.

### Deliverables

1. Python project with `src` layout and locked direct dependencies.
2. Typed configuration models for app, scoring, risk, and backtest settings.
3. Core enums/value objects for data status, provenance, instruments, dates, and score evidence.
4. SQLAlchemy models and first Alembic migration for:
   - `instruments`
   - `instrument_symbols`
   - `universes`
   - `universe_memberships`
   - `data_sources`
   - `ingestion_runs`
   - `source_records`
   - `data_quality_flags`
5. Repository interfaces plus SQLite implementations for instruments and universe membership.
6. `CsvImportProvider` contract and fixture implementation for a small synthetic universe.
7. Idempotent ingestion use case with provenance and validation failures recorded.
8. Minimal Streamlit shell showing application identity, data-source status, universe versions, and the research-tool disclaimer.
9. CLI commands to initialize the database and import a fixture universe.
10. Tests for configuration parsing, migration, duplicate imports, membership date ranges, missing values, and source metadata.
11. Developer commands documented in `README.md`.

### Acceptance criteria

- A fresh checkout can create an environment, initialize SQLite, import a synthetic universe twice without duplication, run tests, and launch Streamlit using documented commands.
- A query for an `as_of` date returns only memberships effective on that date.
- Every imported membership can be traced to an ingestion run and source record.
- Invalid dates, overlapping memberships, missing identifiers, and malformed rows produce explicit validation or quality results.
- No UI module imports provider adapters, SQLAlchemy models, or scoring internals directly.
- Ruff, mypy, and pytest pass for the implemented slice.

### Explicitly deferred

- live or automated market-data access;
- real Nifty 200 constituent import;
- price and fundamental tables beyond approved schema migrations;
- scoring calculations;
- portfolio and backtesting execution;
- authentication, cloud deployment, and broker integration.

## 14. Implementation Milestones

1. Foundation, configuration, provenance, universe schema, and UI shell.
2. Verified Nifty 200 provider and historical membership import.
3. OHLCV ingestion, corporate-action policy, and data-quality reporting.
4. Technical features and transparent momentum score.
5. Fundamental facts and metric-definition registry.
6. Quality, earnings, valuation, and financial-health scores.
7. Candidate ranking and full score explanations.
8. Entry engine and setup states.
9. Exit engine and thesis monitoring.
10. Paper portfolio, position sizing, and decision journal.
11. Point-in-time backtester and performance analytics.
12. Historical case validation, sensitivity analysis, and paper-trading readiness review.

## 15. Approval Boundary

Approval of this proposal authorizes Milestone 1 only. Data providers, scoring formulas, thresholds, and execution assumptions each require documented validation before they become trusted defaults.

Recommended default decision: approve Streamlit, modular Python, SQLite, SQLAlchemy/Alembic, provider-neutral contracts, and fixture-first Milestone 1.