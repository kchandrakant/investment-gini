# Fundamental Filing Facts

## Import policy

The application does not download, crawl, or scrape financial filings. The operator must
confirm that the original issuer or exchange filing may be used for this purpose and manually
transcribe selected reported facts to CSV. `terms_reference` records the applicable terms or
legal basis; it is provenance, not an automated legal approval.

## Source review

Reviewed 2026-10-06: the [Infosys annual-report index](https://www.infosys.com/investors/reports-filings/annual-report.html)
lists integrated annual reports, including 2024-25 and 2025-26. The linked [Infosys Terms
of Use](https://www.infosys.com/terms-of-use.html) grant a limited license to access and
display materials and restrict copying, reproduction, distribution, and derivative use. The
public listing does not provide a separate data-extraction license. Therefore Infosys is not
approved as an import source for this project without separate written permission or another
documented legal basis. No Infosys facts have been imported. A public URL alone is not source
approval.

The [BSE Infosys financial-results listing](https://www.bseindia.com/stock-share-price/infosys-ltd/infosys/500209/financials-results/)
was also reviewed. BSE's [website disclaimer](https://www.bseindia.com/static/about/Disclaimer.aspx)
states that reproduction, redistribution, or transmission of website information or data is
prohibited without express written consent. BSE is therefore not approved as an import source
without that consent. The NSE financial-results and terms pages could not be retrieved for
verification during this review; no reuse permission is assumed for NSE.

The [Screener.in Terms of Service](https://www.screener.in/guides/terms/) grant only
personal, non-commercial transitory viewing and expressly prohibit modifying or copying
materials on the site. They also require downloaded materials to be destroyed when the
viewing license terminates. This is not compatible with persistent ingestion into the local
fundamental-facts database, even when the database is for personal use. Screener may be opened
directly by the user for on-site viewing, but its figures must not be copied into this project
without separate written permission or a license that permits storage.

The import retains two separate hashes:

- `source_checksum`: SHA-256 of the exact CSV transcription imported.
- `source_artifact_checksum`: SHA-256 of the original filing document identified by
  `source_identifier`.

The filing publication timestamp must include its source timezone. Do not substitute the
financial period end date for the date/time the information became public. Report values
exactly as stated and populate `reported_unit` (for example, `INR lakh` or `INR crore`);
the importer does not rescale amounts.

## Supported metrics

`investment-gini fundamental-metrics` lists the versioned catalog. `reported-v1` contains:

| Metric code | Period | Meaning |
|---|---|---|
| `revenue` | Duration | Reported revenue |
| `net_profit` | Duration | Reported profit after tax |
| `operating_cash_flow` | Duration | Net cash from operating activities |
| `total_assets` | Instant | Reported total assets |
| `total_liabilities` | Instant | Reported total liabilities |
| `total_equity` | Instant | Reported total equity |
| `cash_and_equivalents` | Instant | Reported cash and cash equivalents |
| `borrowings` | Instant | Reported borrowings |
| `shares_outstanding` | Instant | Reported shares outstanding |
| `promoter_holding_pct` | Instant | Reported promoter holding percentage |
| `promoter_pledge_pct` | Instant | Reported pledged promoter holding percentage |

This is a reported-fact catalog, not a claim that differently named accounting line items are
interchangeable. The catalog intentionally contains no derived ratios or growth metrics.

## CSV contract

Required header:

```text
isin,metric_code,period_start,period_end,filing_date,available_at,consolidation_scope,value,status,currency,reported_unit
```

Dates use ISO `YYYY-MM-DD`; timestamps use ISO-8601 with a timezone offset. For duration
metrics, `period_start` must precede `period_end`. For instant metrics, leave `period_start`
empty; the importer records the instant date as both boundaries. Scope is `consolidated` or
`standalone`. Currency-valued facts require an ISO currency code. `status` may be `available`,
`unknown`, `not_applicable`, `stale`, or `estimated`; only numeric statuses carry a value.

Example invocation:

```powershell
investment-gini import-fundamentals .\filing-facts.csv `
  --source-name "Issuer annual report" `
  --source-url "https://issuer.example/investors/annual-report.pdf" `
  --terms-reference "Issuer annual-report terms URL or documented permission" `
  --source-artifact-checksum "<64-character SHA-256 of the original filing>"
```

The `example` URL and placeholder are documentation only. Supply the actual official filing
URL and its verified artifact hash. `available_at` is the point-in-time cutoff: later
restatements remain stored but do not appear in queries before their own publication time.

Query with a timezone-aware information cutoff:

```powershell
investment-gini fundamentals --isin INE000A01001 --as-of 2026-05-20T16:00:00+05:30
```

An import with parse errors records quality flags for rejected rows while retaining valid
rows; review the reported `quality_flags` count before using the batch. Reimporting the same
fact revision is idempotent. A later version of a reported fact is stored as a new revision
with a supersession link, never as an overwrite.