# Technical Feature Methodology

Technical formula version: `technical-v2`

Momentum formula version: `momentum-v1`

Technical snapshots use split- and bonus-adjusted NSE closes and volumes through an explicit as-of date. Raw bars remain unchanged. Dividends, rights issues, and demergers are not included, so these features are not based on a total-return series.

## Implemented features

- `sma_20`, `sma_50`, `sma_150`, `sma_200`: arithmetic mean of the latest closing prices in the stated session window.
- `sma_200_change_21`: percentage change in the 200-session SMA over 21 sessions.
- `ema_20`, `ema_50`: exponential moving average with alpha $2/(N+1)$, seeded by the first $N$-session SMA in the available input.
- `return_21`, `return_63`, `return_126`, `return_252`: latest close divided by the close $N$ trading-session intervals earlier, minus one.
- `annualized_volatility_63`: sample standard deviation of 63 daily close returns multiplied by $\sqrt{252}$.
- `maximum_drawdown_252`: the minimum peak-to-current-close return in the latest 252 sessions.
- `distance_from_high_252`: latest close divided by the highest close in the latest 252 sessions, minus one.
- `volume_ratio_20`: latest volume divided by mean volume over the latest 20 sessions.
- `relative_strength_63`, `relative_strength_126`, `relative_strength_252`: stock growth
	divided by Nifty 200 price-index growth over the stated number of common trading-session
	intervals, minus one. A positive value means the stock outperformed the benchmark.

Values are calculated with `Decimal`; prices use four decimal places and ratios use six. Each result records its required and actual observation counts plus evidence start and end dates. A feature with too little history returns `insufficient_history` and no value.

## Trend state and momentum score

`momentum-v1` is a transparent 100-point research score. It is not a BUY recommendation
and does not reproduce a proprietary Minervini/SEPA implementation.

| Component | Rule | Points |
|---|---|---:|
| Trend template | Close above SMA 50, 150, and 200; SMA 50 above SMA 150; SMA 150 above SMA 200; SMA 200 rising over 21 sessions | 30 (5 each) |
| Absolute momentum | Positive 63-, 126-, and 252-session return | 30 (10 each) |
| Relative momentum | Positive 63-, 126-, and 252-session relative strength versus Nifty 200 | 15 (5 each) |
| Risk context | 252-session maximum drawdown no worse than -25%; annualized 63-session volatility at most 40% | 10 (5 each) |
| High proximity | Latest close within 25% of the 252-session closing high | 10 |
| Volume confirmation | Latest volume at or above its 20-session mean | 5 |

The trend state is `confirmed_uptrend` when all six trend-template rules pass,
`constructive` when four or five pass, and `not_confirmed` otherwise. It is
`insufficient_history` if any trend input is unavailable. The total score is similarly
unavailable when any component lacks evidence; missing facts never receive zero points.

The score shares the public economic intuition of NSE momentum indices by emphasizing
multi-horizon price momentum and risk context, but it is a rule-based diagnostic rather
than an index replication. It does not apply constituent ranking, cross-sectional
standardization, index rebalancing, or index weights.

## Point-in-time rule

The engine discards every stock and benchmark observation after the requested as-of date before calculating any feature or collecting source identifiers. Relative strength aligns the two series by session date and never fills a missing close. Tests assert that an extreme future observation does not change an earlier snapshot.

## Chart evidence

The Stock Explorer plots rolling 50- and 200-session averages over adjusted closes. Its
relative-performance chart rebases the stock and Nifty 200 price index to 100 on their
first common session and does not fill missing dates.