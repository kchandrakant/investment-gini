# Indian Stock Research & Decision Engine — Master Context & Build Prompt

## Purpose

Build a small, research-first application for Indian equities. The application is intended to help a long-term/medium-term investor systematically:

1. Build a high-quality basket of Indian stocks.
2. Screen stocks using transparent, evidence-based public-domain methodologies.
3. Evaluate business quality, earnings momentum, valuation and price momentum.
4. Identify disciplined entry conditions rather than blindly generating buy prices.
5. Define and monitor exit conditions before capital is deployed.
6. Backtest the rules without look-ahead or survivorship bias.
7. Maintain a paper portfolio before real-money use.
8. Explain every recommendation so that the user can understand and challenge it.

The application must be a **decision-support and research tool**, not an autonomous trading system, broker, order-execution system, or financial-advice engine.

---

# 1. User Context

The primary user is an experienced software professional in India who wants to begin investing directly in Indian stocks while continuing to use mutual funds as the core of the equity portfolio.

The user finds conventional stock analysis overwhelming and therefore wants a structured system that reduces complexity without becoming a black box.

The desired investing horizon is broadly **medium term: approximately 2–5 years**, while individual positions may be held shorter or longer depending on the investment thesis and price trend.

The user is interested in established public-domain methodologies, particularly:

- Mark Minervini / SEPA-style growth and momentum concepts
- Momentum investing
- Quality investing
- Earnings momentum
- Value/valuation discipline
- Financial-strength measures such as Piotroski-style signals
- Factor investing
- Portfolio risk management
- Systematic entry and exit rules

The user does **not** want to blindly copy any one investor.

The intended strategy is a transparent combination of complementary methods.

---

# 2. Core Investment Philosophy

The application should follow this high-level sequence:

Nifty 200 / defined Indian equity universe
→ Quality
→ Financial health
→ Earnings growth and acceleration
→ Valuation
→ Price momentum / trend
→ Candidate ranking
→ Entry setup
→ Position sizing
→ Portfolio monitoring
→ Exit evaluation
→ Post-trade analysis

The core philosophy is:

> Find good Indian businesses whose earnings outlook is attractive, whose valuation is not irrational, and whose price action confirms that the market is recognising the improvement.

The application must explicitly distinguish:

- **Good company**
- **Good stock**
- **Good price**
- **Good entry**
- **Good holding**
- **Good exit**

These are not interchangeable.

A high-quality company must NOT automatically receive a BUY recommendation.

A cheap stock must NOT automatically receive a BUY recommendation.

A strong momentum stock must NOT automatically receive a BUY recommendation.

The system should seek **confluence of independent evidence**.

---

# 3. Important Design Principle: No Black Box

Do not create a single opaque AI score such as "87/100 = BUY".

Instead, maintain independent component scores:

- Quality Score
- Earnings Score
- Momentum Score
- Valuation Score
- Financial Health Score
- Risk Score
- Setup Score

Then derive an overall ranking while retaining the underlying evidence.

Every score should be decomposable.

Example:

```text
ICICI Bank

Quality       88
Earnings      91
Momentum      84
Valuation     76
Financial     90
Risk          82
Setup         79

Overall       85

Status: WATCH / BUY CANDIDATE
```

The UI should allow the user to drill into why each score exists.

---

# 4. Initial Universe

Start with the **Nifty 200**.

Reasons:

- established companies
- adequate liquidity
- broad coverage of Indian large and mid caps
- manageable universe
- less exposure to very speculative small caps
- easier availability of reliable data

The architecture must allow future expansion to:

- Nifty 500
- Nifty Midcap 150
- selected small caps
- custom watchlists

But do not expand the universe in V1.

The universe must be versioned historically for backtesting.

IMPORTANT:
Do not use today's Nifty 200 constituents to backtest historical years without accounting for historical membership. That creates survivorship bias.

---

# 5. Research Methodologies to Incorporate

## 5.1 Quality Investing

Measure, where data permits:

- ROE
- ROCE
- operating margin
- net margin
- gross margin where useful
- consistency of profitability
- free cash flow generation
- operating cash flow
- debt/equity
- interest coverage
- asset turnover
- working-capital quality
- promoter holding
- promoter pledge
- governance red flags
- auditor-related concerns where reliably available

Quality should reward:

- persistent profitability
- strong returns on capital
- low financial leverage
- cash-backed profits
- stable/improving margins
- sensible capital allocation

Do not rely on a single ratio.

Sector-aware normalization is required because acceptable ROCE, leverage and margins vary materially by industry.

---

## 5.2 Earnings Momentum

Measure:

- 3-year revenue CAGR
- 5-year revenue CAGR
- 3-year EPS CAGR
- 5-year EPS CAGR
- latest quarterly revenue growth
- latest quarterly EPS/profit growth
- sequential growth where meaningful
- margin expansion/contraction
- earnings acceleration
- earnings surprises where reliable data exists
- analyst estimate revisions where reliable public data is available
- management guidance versus previous guidance
- order-book changes where relevant

Pay special attention to acceleration:

```text
EPS growth:
10% → 15% → 22% → 28%
```

should generally score better than:

```text
30% → 25% → 18% → 12%
```

Do not treat one unusually strong quarter as a sustainable trend automatically.

Use trailing and multi-quarter confirmation.

---

## 5.3 Momentum / Minervini-Inspired Trend Analysis

Implement a transparent approximation of public-domain Minervini/SEPA-style principles.

Do NOT claim that the application reproduces Minervini's proprietary implementation exactly.

Potential signals:

- price above 50 DMA
- price above 150 DMA
- price above 200 DMA
- 50 DMA above 150 DMA
- 150 DMA above 200 DMA
- 200 DMA rising
- price near 52-week high
- relative strength versus Nifty 200 / Nifty 50
- 3-month return
- 6-month return
- 12-month return
- volatility-adjusted momentum
- consolidation/base formation
- breakout detection
- breakout volume
- distance from breakout level
- abnormal volume
- failed breakout detection

The application should also compare its momentum score against established public index methodologies where possible, particularly NSE momentum indices.

Do not assume that a stock must be at a new high to qualify.

A constructive pullback in a strong uptrend can be a valid setup.

---

## 5.4 Valuation

Measure multiple valuation dimensions:

- P/E
- forward P/E if reliable
- EV/EBITDA
- P/B where meaningful
- Price/Sales where meaningful
- free-cash-flow yield
- earnings yield
- PEG or growth-adjusted valuation
- historical valuation percentile
- sector-relative valuation
- valuation versus expected earnings growth

Do not use fixed universal rules such as:

> P/E below 20 = BUY

Sector context is essential.

The system should distinguish:

- Cheap
- Reasonably valued
- Expensive
- Extremely expensive

A high P/E can be justified by high sustainable growth, but the system must make the growth assumptions explicit.

---

# 6. Financial Health / Piotroski-Style Module

Implement a transparent financial-strength score inspired by the Piotroski F-Score.

Do not present it as an exact Piotroski implementation unless every required input is available and definitions match the published methodology.

Potential dimensions:

Profitability:
- positive net income
- positive operating cash flow
- improving ROA
- operating cash flow greater than net income

Leverage/liquidity:
- declining leverage
- improving current ratio
- no excessive equity dilution

Operating efficiency:
- improving gross margin
- improving asset turnover

Where data is missing, show:

```text
N/A — insufficient data
```

Do NOT convert missing data into a false pass or fail.

---

# 7. Factor Model

The application should think in terms of established factors rather than endless technical indicators.

Core factors:

- Quality
- Momentum
- Earnings / profitability
- Value / valuation
- Financial strength

Optional later factors:

- Low volatility
- Size
- Dividend quality
- Industry momentum

Do not add factors merely because they improve historical backtest results.

Every factor should have an economic or empirical rationale.

---

# 8. Scoring Framework

Initial conceptual weighting:

```text
Quality             20–25%
Earnings            20–25%
Momentum            20–25%
Valuation           15–20%
Financial Health    10%
Risk adjustment     separate overlay
```

Do not hard-code these weights permanently.

Make them configurable.

However, V1 should use a sensible default and avoid excessive parameter optimization.

The user must be able to see:

1. component scores
2. raw metrics
3. thresholds
4. reason for pass/fail
5. data freshness
6. confidence level

---

# 9. Entry Engine

The application must NOT simply generate a magical exact buy price.

It should identify **entry conditions**.

Possible entry states:

### A. Breakout Entry

Requirements may include:

- strong fundamental score
- strong earnings score
- strong momentum
- price forming a constructive base
- breakout above defined resistance
- volume confirmation
- market regime not strongly hostile

### B. Pullback Entry

Requirements may include:

- established uptrend
- price remains above key moving averages
- controlled pullback
- support holds
- volume contracts during decline
- relative strength remains healthy
- no fundamental deterioration

### C. Valuation Entry

For fundamentally strong stocks:

- valuation enters acceptable range
- long-term trend remains intact
- earnings thesis intact

The system should classify the setup:

```text
NOT READY
WATCH
PREPARE
BUY CANDIDATE
BUY CONFIRMATION
```

Do not use BUY unless the configured conditions are met.

---

# 10. Position Sizing

Position sizing should depend on:

- portfolio size
- maximum portfolio risk
- entry price
- invalidation level
- stock volatility
- portfolio concentration
- sector concentration

Basic risk-based sizing concept:

```text
Position Size =
Maximum Rupee Risk / (Entry Price - Invalidation Price)
```

Then cap position size using portfolio-level limits.

Example:

```text
Portfolio = ₹10,00,000
Maximum risk on one new position = 0.5% = ₹5,000

Entry = ₹1,000
Invalidation = ₹900

Risk/share = ₹100

Maximum shares = 50
Position value = ₹50,000
```

This is an example only.

The app should allow configurable risk limits.

Avoid recommending excessive leverage.

No derivatives/options in V1.

---

# 11. EXIT ENGINE — CRITICAL

Exit management must be as important as stock selection.

Every position must have predefined exit logic.

Use five major exit categories.

## 11.1 Thesis-Break Exit

Sell/review when the reason for owning the business no longer holds.

Examples:

- structural earnings deterioration
- competitive advantage lost
- major strategic failure
- unexpected debt problems
- major governance issue
- capital allocation deterioration
- industry economics materially change

This should override price-based optimism.

---

## 11.2 Earnings Deterioration Exit

Examples:

- earnings growth materially below thesis
- repeated negative surprises
- margin deterioration
- falling guidance
- meaningful analyst estimate cuts
- weakening order book

Do not automatically sell because of one weak quarter.

Classify:

```text
Temporary
Watch
Material deterioration
Structural deterioration
```

---

## 11.3 Technical Invalidation Exit

For momentum/breakout entries:

- failed breakout
- decisive close below setup support
- loss of major trend
- 50 DMA / 200 DMA breakdown where relevant
- abnormal-volume breakdown
- persistent relative-strength deterioration

Avoid rigid universal stop-loss percentages.

The invalidation level should be derived from the setup.

---

## 11.4 Valuation Exit / Reduce

If price rises much faster than earnings:

- valuation percentile becomes extreme
- expected return falls below threshold
- growth assumptions required to justify price become unrealistic

Default action should often be:

```text
REDUCE
```

rather than automatically SELL ALL.

---

## 11.5 Trailing Winner Exit

For large winners:

- do not automatically sell at +20%, +30%, etc.
- allow strong trends to continue
- progressively trail based on price structure / moving averages / major swing lows

The objective is:

> Let winners run while protecting against a material trend reversal.

---

# 12. The 12-Month Question

Add a simple portfolio review rule:

> If I had fresh cash today, would I buy this stock at today's price?

Answers:

- YES → HOLD / ADD if setup permits
- MAYBE → REVIEW
- NO → consider REDUCE / EXIT

This is a behavioural guard against anchoring.

---

# 13. Market Regime Filter

Add a market-level overlay.

Potential inputs:

- Nifty 50 trend
- Nifty 200 trend
- breadth
- percentage of stocks above 50 DMA
- percentage above 200 DMA
- volatility
- index momentum
- market drawdown

Classify:

```text
GREEN  = favourable
YELLOW = selective
RED    = defensive
```

The market regime should NOT override strong individual opportunities automatically.

It should influence:

- number of new positions
- position size
- required confirmation
- cash allocation

---

# 14. Portfolio Construction

Initial target:

- 8–12 direct equity positions eventually
- start with 2–3 positions
- avoid immediate full deployment
- diversify across industries
- avoid hidden concentration

The application must show:

- stock weight
- sector weight
- factor exposure
- unrealised gain/loss
- realised gain/loss
- risk contribution
- correlation where feasible
- portfolio beta where feasible
- cash allocation

The user already has mutual funds, so the app should eventually allow manual entry/import of mutual-fund holdings and show overlap.

Example:

If the user owns ICICI Bank directly and also has large indirect exposure through mutual funds, the app should flag:

```text
Potential concentration:
Direct ICICI Bank + estimated MF exposure
```

Do not require MF look-through in V1 unless reliable holdings data is available.

---

# 15. Watchlist Workflow

Use:

```text
UNIVERSE
↓
SCREENED
↓
RESEARCH
↓
WATCHLIST
↓
ENTRY SETUP
↓
BUY
↓
HOLD
↓
REDUCE / EXIT
↓
POST-TRADE REVIEW
```

Each stock should have a state.

---

# 16. Explainability

For every stock, show:

### Why it is here

Example:

```text
Reasons:
+ EPS growth accelerating
+ ROCE > sector median
+ Debt low
+ Relative strength strong
+ Price above rising 200 DMA
+ Valuation within historical range

Concerns:
- P/E above sector median
- Recent volume weakening
```

Also show:

### What would make us wrong?

This is essential.

Example:

```text
Thesis invalidation:
1. EPS growth falls below 10% for two consecutive quarters.
2. Core margin declines materially.
3. Price breaks major support with high volume.
```

The user should never own a stock without knowing the thesis and invalidation.

---

# 17. Data Reliability Architecture

This is one of the most important parts of the project.

Prefer data sources in roughly this hierarchy:

1. NSE / BSE official data
2. Company annual reports / investor presentations / exchange filings
3. SEBI-related disclosures
4. Official index methodology and constituent files
5. High-quality commercial/public financial-data providers
6. Reputable secondary sources
7. News sources only for contextual events

Every data field should have:

- source
- retrieval timestamp
- period/end date
- reported/as-of date
- transformation method
- confidence level

Never silently mix stale and current data.

Do not scrape sites in violation of terms of service.

Where an API is unavailable, design a clean provider abstraction so another data source can be substituted.

---

# 18. Corporate Actions

Price data must be adjusted correctly for:

- stock splits
- bonuses
- rights issues where relevant
- dividends where required by the methodology
- mergers/demergers
- symbol changes

Fundamental histories must also remain period-correct.

Do not use today's fundamentals for historical backtests.

---

# 19. Backtesting Requirements

Backtesting is mandatory before trusting the strategy.

The backtester must avoid:

### Look-ahead bias

Only use information that was publicly available on the simulated date.

Example:
Q1 results released on August 10 cannot influence a simulated trade on August 5.

### Survivorship bias

Use historical index membership.

### Selection bias

Do not manually choose stocks after seeing their future performance.

### Corporate-action bias

Use correctly adjusted prices.

### Delisting bias

Where possible, include delisted stocks.

### Transaction costs

Model:

- brokerage
- exchange charges
- STT
- GST
- stamp duty
- slippage

Use configurable assumptions.

---

# 20. Backtest Outputs

Show:

- CAGR
- annual returns
- maximum drawdown
- volatility
- Sharpe ratio
- Sortino ratio
- Calmar ratio
- win rate
- average winner
- average loser
- profit factor
- expectancy
- turnover
- number of trades
- average holding period
- exposure
- cash level
- worst trade
- longest drawdown
- performance versus Nifty 50
- performance versus Nifty 200
- performance versus relevant factor benchmark

Also show performance by market regime.

---

# 21. Out-of-Sample Testing

Do not optimise everything on the full historical period.

Use:

```text
Training period
→ Validation period
→ Out-of-sample test
```

For example:

```text
2014–2021  = development
2022–2023  = validation
2024–2026  = out-of-sample
```

Exact dates can be configurable.

Use walk-forward testing later.

---

# 22. Avoid Overfitting

Strong rule:

> Prefer simple rules with economic rationale over highly optimised thresholds.

Do not search endlessly for:

- perfect moving-average combinations
- perfect RSI values
- perfect stop percentages
- perfect P/E thresholds
- perfect volume multipliers

If a small parameter change completely destroys performance, the strategy is probably fragile.

The application should optionally perform sensitivity analysis.

Example:

```text
200 DMA strategy:
180–220 DMA range

Result:
CAGR changes only slightly
→ robust

OR

CAGR collapses outside 197 DMA
→ likely overfit
```

---

# 23. Paper Trading Mode

Before real-money usage:

- create virtual portfolio
- simulate entries/exits
- record signal timestamp
- record decision rationale
- compare theoretical versus actual execution
- track slippage
- track emotional overrides

The app should maintain a decision journal.

---

# 24. Decision Journal

For every buy:

```text
Date
Stock
Entry price
Position size
Why bought
Quality score
Earnings score
Momentum score
Valuation score
Market regime
Entry setup
Invalidation level
Expected thesis
Exit conditions
```

For every sell:

```text
Date
Stock
Exit price
Reason
Profit/loss
Holding period
Which rule triggered?
Was the original thesis correct?
What was learned?
```

This becomes a valuable learning dataset.

---

# 25. AI Usage

AI should be used as an assistant, NOT the core scoring engine.

Good AI uses:

- summarize annual reports
- summarize quarterly results
- extract management guidance
- compare current results with thesis
- explain score changes
- identify potential risks
- summarize news
- generate research notes
- help interpret unusual changes

Bad AI uses:

- "predict tomorrow's price"
- "tell me which stock will rise"
- ungrounded buy/sell decisions
- invented financial metrics
- replacing deterministic calculations

Every AI-generated statement should be traceable to source data.

---

# 26. Recommended Technical Architecture

Prefer a simple architecture suitable for a software engineer building a personal research tool.

Possible stack:

### Backend
Python

Recommended libraries as appropriate:

- pandas
- numpy
- scipy
- statsmodels
- scikit-learn only where genuinely useful
- pydantic
- FastAPI if an API layer is needed

### Data storage

Start simple:

- SQLite for V1

Move to PostgreSQL only if justified.

### Frontend

Choose one simple approach:

- Streamlit for fastest research MVP

OR

- React/TypeScript frontend + FastAPI backend for a more durable application

Do not overengineer V1.

### Charts

Use Plotly or a similarly capable charting library.

### Testing

Use pytest.

### Configuration

Use YAML/TOML/JSON for:

- scoring weights
- thresholds
- risk limits
- data-provider configuration
- backtest assumptions

Never bury important strategy parameters throughout the code.

---

# 27. Suggested Application Screens

## Dashboard

Show:

- market regime
- top candidates
- current holdings
- alerts
- upcoming earnings
- recent score changes

## Screener

Filters:

- quality
- earnings
- momentum
- valuation
- sector
- market cap
- setup status

## Stock Detail

Show:

- price chart
- moving averages
- relative strength
- fundamentals
- earnings history
- valuation history
- score breakdown
- thesis
- entry setup
- exit rules
- source data

## Watchlist

Show:

- candidate
- score
- current price
- entry zone
- setup status
- reasons to wait
- alerts

## Portfolio

Show:

- holdings
- weights
- P&L
- risk
- thesis status
- exit warnings

## Backtest

Show:

- equity curve
- drawdown
- annual returns
- trade list
- benchmark comparison
- regime analysis

## Journal

Show:

- decisions
- outcomes
- mistakes
- lessons

---

# 28. Alerts

The application should eventually alert when:

- candidate enters entry zone
- breakout occurs
- breakout fails
- price crosses key trend level
- earnings released
- earnings surprise occurs
- estimate changes
- thesis flag changes
- valuation enters/exits target range
- portfolio concentration exceeds limit
- market regime changes

Alerts should be informational, not automatic trade execution.

---

# 29. V1 Scope

Keep V1 intentionally small.

### Must have

1. Nifty 200 universe
2. Historical OHLCV data
3. Basic fundamental data
4. Quality score
5. Earnings score
6. Momentum/Minervini-inspired score
7. Valuation score
8. Financial-health checks
9. Candidate ranking
10. Watchlist
11. Entry-condition engine
12. Exit-condition engine
13. Basic portfolio tracking
14. Basic backtesting
15. Explainability
16. Source/timestamp metadata

### Do NOT build initially

- broker integration
- automated trading
- options
- intraday trading
- machine-learning price prediction
- mobile application
- social features
- complex authentication
- microservices
- cloud deployment unless needed

---

# 30. Development Method

Work in small vertical slices.

Recommended order:

### Milestone 1
Project skeleton + configuration + database schema.

### Milestone 2
Import/store Nifty 200 universe.

### Milestone 3
Import historical price data.

### Milestone 4
Calculate technical indicators and momentum.

### Milestone 5
Add fundamental metrics.

### Milestone 6
Implement Quality/Earnings/Valuation/Financial Health scores.

### Milestone 7
Implement candidate ranking.

### Milestone 8
Implement entry engine.

### Milestone 9
Implement exit engine.

### Milestone 10
Implement portfolio and journal.

### Milestone 11
Implement backtester.

### Milestone 12
Validate against known historical cases.

Only after these should UI polish become a priority.

---

# 31. Engineering Principles

The code must be:

- modular
- testable
- typed where practical
- documented
- deterministic for calculations
- reproducible
- configurable
- source-aware
- timezone/date aware
- resilient to missing data

Use clear domain models such as:

```text
Stock
PriceBar
FundamentalSnapshot
EarningsSnapshot
ValuationSnapshot
TechnicalSnapshot
Score
InvestmentThesis
EntrySetup
ExitRule
Position
Trade
Portfolio
BacktestRun
DataSource
```

Separate:

```text
Data ingestion
→ Normalization
→ Feature calculation
→ Scoring
→ Signal generation
→ Portfolio logic
→ Backtesting
→ UI
```

Do not mix scraping, financial calculations and UI code.

---

# 32. Data Quality Rules

Never silently fill missing financial data.

Clearly distinguish:

```text
0
N/A
Not applicable
Unknown
Stale
Estimated
```

If data is older than an allowed freshness window, flag it.

If two sources disagree materially:

- do not silently choose one
- record both
- flag discrepancy
- prefer official filings

---

# 33. Research Governance

The application must display a disclaimer that it is a research and decision-support tool.

It should explicitly state:

- historical backtests do not guarantee future returns
- factor premiums can weaken or disappear
- transaction costs and slippage matter
- data quality can affect results
- model assumptions can be wrong
- market regimes change
- the user is responsible for investment decisions

Do not use language implying certainty.

Avoid:

```text
Guaranteed
Safe
Sure shot
Will rise
Best stock
Certain return
```

Prefer:

```text
Higher score
Historical tendency
Candidate
Evidence supports
Risk flag
Setup confirmation
Thesis intact
```

---

# 34. What the System Should Ultimately Answer

For any stock, the user should be able to ask:

### "Why is this stock on my watchlist?"

### "Why is it not a buy yet?"

### "What needs to happen before I buy?"

### "What is my initial risk?"

### "What would invalidate the trade?"

### "Why did its score change?"

### "Why should I continue holding it?"

### "What would make me reduce?"

### "What would make me exit?"

### "How did this strategy perform historically?"

These are more valuable questions than:

> "Will this stock go up tomorrow?"

---

# 35. Important Research Sources / Methodology References

The implementation should research and cite authoritative/public sources for methodology rather than relying on blogs alone.

Priority sources include:

- NSE index methodologies
- NSE historical/index data
- BSE disclosures
- company annual reports
- company investor presentations
- exchange filings
- SEBI material
- academic research on momentum, value, quality and factor investing
- original Piotroski research
- published material describing Minervini/SEPA concepts
- reputable academic/industry research on factor robustness

Do not copy proprietary paid datasets or proprietary strategy code.

Implement publicly describable concepts independently.

---

# 36. Important Conceptual Distinction

The application is NOT trying to predict the future.

It is trying to create a **positive expected-value decision process**.

Think:

```text
Good Business
+
Good Earnings
+
Reasonable Valuation
+
Strong Price Behaviour
+
Disciplined Entry
+
Controlled Risk
+
Disciplined Exit
=
Repeatable Process
```

The process can still lose money.

Success should be measured by whether the process is robust, not by whether every trade wins.

---

# 37. First Development Task

Do NOT immediately write the whole application.

First produce:

1. proposed architecture
2. repository structure
3. technology choices and rationale
4. data-source strategy
5. database schema
6. scoring model
7. entry/exit rule specification
8. backtesting design
9. implementation milestones
10. risks and assumptions

Then ask for approval before making major architectural commitments.

After approval, implement the smallest end-to-end vertical slice:

```text
Nifty 200
→ price data
→ basic momentum score
→ basic quality/earnings/valuation placeholders
→ candidate table
```

The application should run locally in VS Code.

---

# 38. Working Style for ChatGPT

You are acting as a senior software architect + quantitative research engineer + investment-research assistant.

When making implementation decisions:

- explain the reason briefly
- prefer simplicity
- avoid overengineering
- distinguish facts from assumptions
- identify data limitations
- never fabricate data
- never invent APIs
- never claim a data source is available without verifying it
- test calculations
- write unit tests for financial formulas
- keep strategy parameters configurable

When a methodology is uncertain or proprietary:

- state what is publicly known
- implement only the transparent/publicly describable portion
- do not pretend to reproduce a proprietary method exactly

When research is required, use authoritative sources and cite them in the research notes.

---

# 39. First Prompt to Execute

Start by acting as the lead architect.

Do NOT generate the complete codebase yet.

First:

1. Restate the objective in your own words.
2. Identify ambiguities and assumptions.
3. Propose the simplest viable architecture.
4. Propose the repository structure.
5. Define the initial database schema.
6. Define the data-provider abstraction.
7. Define the scoring interfaces.
8. Define the entry/exit rule interfaces.
9. Define the initial backtesting architecture.
10. Identify the highest-risk technical and research problems.
11. Define Milestone 1 in enough detail that it can be implemented immediately.
12. Ask only essential clarification questions; otherwise make sensible assumptions and proceed.

Do not build unnecessary features.

The priority is:

**Correctness → Reproducibility → Explainability → Backtestability → Usability → Visual polish.**

The final product should feel like a disciplined personal equity-research laboratory, not a stock-tip application.
