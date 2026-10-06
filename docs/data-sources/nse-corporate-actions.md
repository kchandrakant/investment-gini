# NSE Corporate Actions

## Accepted official source

- Publication: <https://www.nseindia.com/companies-listing/corporate-filings-actions>
- Data endpoint: `https://www.nseindia.com/api/corporates-corporateActions`
- Terms of use: <https://www.nseindia.com/nse-terms-of-use>

The endpoint is accepted for this local research tool as NSE's official public corporate-action publication. Each ingestion stores the exact filtered URL, retrieval timestamp, SHA-256 response checksum, and terms reference. The adapter filters to `EQ` records whose ISIN belongs to the explicitly selected Nifty 200 snapshot. The endpoint is an external publication surface and may change; malformed or ambiguous adjusting records become quality flags rather than guessed factors.

The validated CSV importer remains available for an official or licensed replacement source. Its required columns are:

```text
isin,action_type,ex_date,record_date,ratio_numerator,ratio_denominator,cash_amount,currency,verification_status
```

## Adjustment policy

Raw NSE bhavcopy rows are immutable. Adjustments are derived only when the adjusted query mode is selected and only from verified splits and ordinary equity bonuses.

For a split from old face value $O$ to new face value $N$, observations before the ex-date use price factor $N/O$ and volume factor $O/N$.

For a bonus ratio $B:H$ (bonus shares issued for shares held), observations before the ex-date use price factor $H/(B+H)$ and volume factor $(B+H)/H$.

Multiple later actions compound multiplicatively. The ex-date and later observations are not restated for that action. Prices are quantized to four decimal places and adjusted volume is rounded to an integer.

## Non-adjusting evidence

Dividends, rights issues, and demergers are stored with their official ex-date, record date, and available terms, but do not alter the derived price series. Therefore:

- adjusted mode is not a dividend-adjusted or total-return series;
- rights entitlement value is not estimated;
- demerger value allocation is not inferred;
- buybacks and other unmodeled subjects are ignored by this adapter;
- symbol changes belong to dated `instrument_symbols` records and require separate membership/security-master evidence.

## Verified case

The 2:1 Patanjali Foods bonus with ex-date 2025-09-11 produces a factor of $1/3$. Stored closes of 1,802.10 and 1,802.00 on the two preceding sessions derive to 600.7000 and 600.6667. The ex-date close of 598.9000 remains 598.9000, and all stored raw bars remain unchanged.