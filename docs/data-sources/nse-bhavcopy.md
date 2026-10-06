# NSE Cash-Market Bhavcopy

## Official source

- Archive pattern: `https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`
- Terms of use: <https://www.nseindia.com/nse-terms-of-use>

## Ingestion rules

The provider validates the ZIP, single CSV member, official header, trade date, and business date. It retains only `CM` / `NSE` / `STK` / `EQ` rows whose ISIN belongs to the explicitly selected Nifty 200 composition snapshot.

Stored fields are raw open, high, low, close, previous close, volume, traded value, and transaction count. Retrieval timestamp, archive URL, SHA-256 checksum, and reported session are persisted. Imports are idempotent by instrument, session, and series.

## Limitations

Stored prices are unadjusted. The application may derive split- and bonus-adjusted series at query time without mutating these rows. It does not derive dividend total return or rights/demerger adjustment. Selecting a current constituent snapshot for an earlier session introduces survivorship bias; unbiased backtests require point-in-time historical index membership.