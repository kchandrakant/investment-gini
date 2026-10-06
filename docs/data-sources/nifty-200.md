# Nifty 200 Current Constituents

## Official sources

- Index page: <https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-200>
- Constituent CSV: <https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv>
- Methodology: <https://www.niftyindices.com/Methodology/Method_NIFTY_Equity_Indices.pdf>
- Terms of use: <https://www.niftyindices.com/terms-of-use>

## Verified on 2026-09-03

The official index page reported its composition data as of 2026-08-31. The constituent endpoint returned HTTP 200 with 200 rows and 200 unique ISINs. Its columns were:

```text
Company Name,Industry,Symbol,Series,ISIN Code
```

The file does not embed its own composition date. Imports therefore require an explicit date observed on the official index page. The retrieval timestamp, source URL, SHA-256 checksum, and supplied composition date are persisted.

This source provides a current constituent snapshot, not historical index membership. It is suitable for the current research universe but insufficient for survivorship-bias-free historical backtesting.