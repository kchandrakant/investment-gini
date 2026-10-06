from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import ClassVar, cast
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from investment_gini.domain import (
    BenchmarkBarRecord,
    CorporateActionRecord,
    Exchange,
    FundamentalFactRecord,
    MetricDefinitionRecord,
    PriceBarRecord,
    SourceMetadata,
    UniverseMembershipRecord,
)


@dataclass(frozen=True)
class ProviderIssue:
    row_number: int
    field_name: str | None
    reason: str
    observed_value: str | None = None


@dataclass(frozen=True)
class UniverseBatch:
    records: tuple[UniverseMembershipRecord, ...]
    issues: tuple[ProviderIssue, ...]
    source: SourceMetadata
    is_complete_snapshot: bool = False


@dataclass(frozen=True)
class PriceBatch:
    records: tuple[PriceBarRecord, ...]
    issues: tuple[ProviderIssue, ...]
    source: SourceMetadata


@dataclass(frozen=True)
class BenchmarkBatch:
    records: tuple[BenchmarkBarRecord, ...]
    issues: tuple[ProviderIssue, ...]
    source: SourceMetadata


@dataclass(frozen=True)
class CorporateActionBatch:
    records: tuple[CorporateActionRecord, ...]
    issues: tuple[ProviderIssue, ...]
    source: SourceMetadata

@dataclass(frozen=True)
class FundamentalBatch:
    definitions: tuple[MetricDefinitionRecord, ...]
    records: tuple[FundamentalFactRecord, ...]
    issues: tuple[ProviderIssue, ...]
    source: SourceMetadata


class NseArchiveUnavailableError(RuntimeError):
    """The official archive has no file for the requested date."""


class NiftyHistoricalIndexProvider:
    endpoint = "https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString"
    terms_url = "https://www.niftyindices.com/terms-of-use"

    def __init__(self, fetcher: Callable[[str, bytes], bytes] | None = None) -> None:
        self._fetcher = fetcher or self._download

    def fetch_benchmark(
        self,
        benchmark_name: str,
        start_date: date,
        end_date: date,
    ) -> BenchmarkBatch:
        normalized_name = benchmark_name.strip()
        if not normalized_name:
            raise ValueError("benchmark name is required")
        if start_date > end_date:
            raise ValueError("start date cannot be after end date")
        if (end_date - start_date).days > 365:
            raise ValueError("official historical requests cannot exceed 365 days")

        cinfo = (
            "{'name':'"
            + normalized_name.upper()
            + "','startDate':'"
            + start_date.strftime("%d-%b-%Y")
            + "','endDate':'"
            + end_date.strftime("%d-%b-%Y")
            + "','indexName':'"
            + normalized_name
            + "'}"
        )
        request_body = json.dumps({"cinfo": cinfo}, separators=(",", ":")).encode("utf-8")
        contents = self._fetcher(self.endpoint, request_body)
        source = SourceMetadata(
            provider="nifty_historical_index",
            source_identifier=self.endpoint,
            retrieved_at=datetime.now(UTC),
            checksum=hashlib.sha256(contents).hexdigest(),
            source_class="official_endpoint",
            reliability_tier=1,
            terms_reference=self.terms_url,
        )
        try:
            payload: object = json.loads(contents.decode("utf-8-sig"))
            if isinstance(payload, dict) and "d" in payload:
                payload = payload["d"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
            if not isinstance(payload, list):
                raise ValueError("official response must be a list")
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid official historical-index response") from error

        benchmark_code = re.sub(r"[^A-Z0-9]+", "_", normalized_name.upper()).strip("_")
        records: list[BenchmarkBarRecord] = []
        issues: list[ProviderIssue] = []
        seen_dates: set[date] = set()
        for row_number, raw_row in enumerate(payload, start=1):
            if not isinstance(raw_row, dict):
                issues.append(
                    ProviderIssue(row_number, None, "official benchmark row must be an object")
                )
                continue
            row = cast(dict[str, object], raw_row)
            try:
                record = self._parse_row(
                    row,
                    row_number,
                    benchmark_code,
                    normalized_name,
                    start_date,
                    end_date,
                    source,
                )
                if record.session_date in seen_dates:
                    raise ValueError(f"row {row_number}: duplicate benchmark session")
                seen_dates.add(record.session_date)
                records.append(record)
            except ValueError as error:
                issues.append(
                    ProviderIssue(row_number, None, str(error), json.dumps(row, default=str))
                )
        records.sort(key=lambda record: record.session_date)
        return BenchmarkBatch(tuple(records), tuple(issues), source)

    @staticmethod
    def _parse_row(
        row: dict[str, object],
        row_number: int,
        benchmark_code: str,
        benchmark_name: str,
        start_date: date,
        end_date: date,
        source: SourceMetadata,
    ) -> BenchmarkBarRecord:
        returned_name = str(row.get("INDEX_NAME", "")).strip()
        if returned_name.casefold() != benchmark_name.casefold():
            raise ValueError(f"row {row_number}: unexpected index name {returned_name!r}")
        try:
            session_date = datetime.strptime(
                str(row.get("HistoricalDate", "")).strip(), "%d %b %Y"
            ).date()
            record = BenchmarkBarRecord(
                benchmark_code=benchmark_code,
                benchmark_name=returned_name,
                session_date=session_date,
                open=Decimal(str(row.get("OPEN", "")).strip()),
                high=Decimal(str(row.get("HIGH", "")).strip()),
                low=Decimal(str(row.get("LOW", "")).strip()),
                close=Decimal(str(row.get("CLOSE", "")).strip()),
                source=source,
            )
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"row {row_number}: invalid benchmark data: {error}") from error
        if not start_date <= record.session_date <= end_date:
            raise ValueError(f"row {row_number}: session is outside the requested range")
        if min(record.open, record.high, record.low, record.close) < 0:
            raise ValueError(f"row {row_number}: benchmark values cannot be negative")
        if record.low > record.high or not record.low <= record.open <= record.high:
            raise ValueError(f"row {row_number}: inconsistent OHLC range")
        if not record.low <= record.close <= record.high:
            raise ValueError(f"row {row_number}: close is outside the daily range")
        return record

    @staticmethod
    def _download(url: str, request_body: bytes) -> bytes:
        request = Request(
            url,
            data=request_body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "InvestmentGini/0.1 research-tool",
            },
            method="POST",
        )
        with urlopen(request, timeout=60) as response:
            return cast(bytes, response.read())


class CsvCorporateActionProvider:
    required_fields: ClassVar[frozenset[str]] = frozenset({
        "isin",
        "action_type",
        "ex_date",
        "record_date",
        "ratio_numerator",
        "ratio_denominator",
        "cash_amount",
        "currency",
        "verification_status",
    })
    supported_action_types = frozenset({"split", "bonus", "dividend", "rights", "demerger"})
    supported_verification_states = frozenset({"verified", "provisional"})

    def fetch_actions(
        self,
        path: Path,
        source_name: str,
        terms_reference: str,
    ) -> CorporateActionBatch:
        if not source_name.strip() or not terms_reference.strip():
            raise ValueError("source name and terms reference are required")
        contents = path.read_bytes()
        source = SourceMetadata(
            provider=source_name.strip(),
            source_identifier=str(path.resolve()),
            retrieved_at=datetime.now(UTC),
            checksum=hashlib.sha256(contents).hexdigest(),
            source_class="licensed_or_official_export",
            reliability_tier=2,
            terms_reference=terms_reference.strip(),
        )
        records: list[CorporateActionRecord] = []
        issues: list[ProviderIssue] = []
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            missing_columns = self.required_fields - set(reader.fieldnames or ())
            if missing_columns:
                issue = ProviderIssue(
                    1,
                    None,
                    f"missing required columns: {', '.join(sorted(missing_columns))}",
                )
                return CorporateActionBatch((), (issue,), source)
            for row_number, row in enumerate(reader, start=2):
                try:
                    records.append(self._parse_row(row, row_number, source))
                except ValueError as error:
                    issues.append(ProviderIssue(row_number, None, str(error), str(row)))
        return CorporateActionBatch(tuple(records), tuple(issues), source)

    @classmethod
    def _parse_row(
        cls,
        row: dict[str, str | None],
        row_number: int,
        source: SourceMetadata,
    ) -> CorporateActionRecord:
        isin = (row.get("isin") or "").strip().upper()
        action_type = (row.get("action_type") or "").strip().lower()
        verification = (row.get("verification_status") or "").strip().lower()
        if len(isin) != 12:
            raise ValueError(f"row {row_number}: ISIN must contain 12 characters")
        if action_type not in cls.supported_action_types:
            raise ValueError(f"row {row_number}: unsupported action type {action_type!r}")
        if verification not in cls.supported_verification_states:
            raise ValueError(f"row {row_number}: invalid verification status {verification!r}")
        try:
            ex_date = date.fromisoformat((row.get("ex_date") or "").strip())
            record_raw = (row.get("record_date") or "").strip()
            record_date = date.fromisoformat(record_raw) if record_raw else None
            numerator_raw = (row.get("ratio_numerator") or "").strip()
            denominator_raw = (row.get("ratio_denominator") or "").strip()
            cash_raw = (row.get("cash_amount") or "").strip()
            numerator = Decimal(numerator_raw) if numerator_raw else None
            denominator = Decimal(denominator_raw) if denominator_raw else None
            cash_amount = Decimal(cash_raw) if cash_raw else None
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"row {row_number}: invalid date or decimal: {error}") from error
        if action_type in {"split", "bonus"} and (
            numerator is None
            or denominator is None
            or numerator <= 0
            or denominator <= 0
        ):
            raise ValueError(f"row {row_number}: split and bonus require positive ratios")
        if action_type == "dividend" and (cash_amount is None or cash_amount < 0):
            raise ValueError(f"row {row_number}: dividend requires a non-negative cash amount")
        return CorporateActionRecord(
            isin=isin,
            action_type=action_type,
            ex_date=ex_date,
            record_date=record_date,
            ratio_numerator=numerator,
            ratio_denominator=denominator,
            cash_amount=cash_amount,
            currency=(row.get("currency") or "INR").strip().upper() or "INR",
            verification_status=verification,
            source=source,
        )


class NseCorporateActionProvider:
    endpoint = "https://www.nseindia.com/api/corporates-corporateActions"
    terms_url = "https://www.nseindia.com/nse-terms-of-use"
    _ratio_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)")
    _split_pattern = re.compile(
        r"from\s+(?:rs\.?|re\.?)\s*(\d+(?:\.\d+)?)\s*/?-?\s*per\s+share\s+"
        r"to\s+(?:rs\.?|re\.?)\s*(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    _cash_pattern = re.compile(
        r"(?:rs\.?|re\.?)\s*(\d+(?:\.\d+)?)\s*per\s+share",
        re.IGNORECASE,
    )

    def __init__(self, fetcher: Callable[[str], bytes] | None = None) -> None:
        self._fetcher = fetcher or self._download

    def fetch_actions(
        self,
        start_date: date,
        end_date: date,
        requested_isins: set[str],
    ) -> CorporateActionBatch:
        if end_date < start_date:
            raise ValueError("end date must not precede start date")
        query = urlencode(
            {
                "index": "equities",
                "from_date": start_date.strftime("%d-%m-%Y"),
                "to_date": end_date.strftime("%d-%m-%Y"),
            }
        )
        url = f"{self.endpoint}?{query}"
        contents = self._fetcher(url)
        source = SourceMetadata(
            provider="nse_corporate_actions",
            source_identifier=url,
            retrieved_at=datetime.now(UTC),
            checksum=hashlib.sha256(contents).hexdigest(),
            source_class="official_web",
            reliability_tier=1,
            terms_reference=self.terms_url,
        )
        try:
            payload = json.loads(contents)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid official corporate-action response") from error
        if not isinstance(payload, list):
            raise ValueError("official corporate-action response must be a list")

        normalized_isins = {isin.strip().upper() for isin in requested_isins}
        records: list[CorporateActionRecord] = []
        issues: list[ProviderIssue] = []
        for row_number, row in enumerate(payload, start=1):
            if not isinstance(row, dict):
                issues.append(ProviderIssue(row_number, None, "record must be an object"))
                continue
            isin = str(row.get("isin") or "").strip().upper()
            if isin not in normalized_isins or str(row.get("series") or "").upper() != "EQ":
                continue
            try:
                record = self._parse_row(row, row_number, source)
                if record is not None:
                    records.append(record)
            except ValueError as error:
                issues.append(ProviderIssue(row_number, None, str(error), str(row)))
        return CorporateActionBatch(tuple(records), tuple(issues), source)

    @classmethod
    def _parse_row(
        cls,
        row: dict[object, object],
        row_number: int,
        source: SourceMetadata,
    ) -> CorporateActionRecord | None:
        isin = str(row.get("isin") or "").strip().upper()
        subject = str(row.get("subject") or "").strip()
        subject_lower = subject.lower()
        try:
            ex_date = datetime.strptime(str(row.get("exDate")), "%d-%b-%Y").date()
            record_raw = str(row.get("recDate") or "").strip()
            record_date = (
                datetime.strptime(record_raw, "%d-%b-%Y").date()
                if record_raw and record_raw != "-"
                else None
            )
        except ValueError as error:
            raise ValueError(f"row {row_number}: invalid NSE date") from error

        numerator: Decimal | None = None
        denominator: Decimal | None = None
        cash_amount: Decimal | None = None
        if "face value split" in subject_lower or "sub-division" in subject_lower:
            action_type = "split"
            match = cls._split_pattern.search(subject)
            if match is None:
                raise ValueError(f"row {row_number}: ambiguous split ratio")
            numerator, denominator = map(Decimal, match.groups())
        elif subject_lower.startswith("bonus"):
            action_type = "bonus"
            match = cls._ratio_pattern.search(subject)
            if match is None:
                raise ValueError(f"row {row_number}: ambiguous bonus ratio")
            numerator, denominator = map(Decimal, match.groups())
        elif "dividend" in subject_lower:
            action_type = "dividend"
            amounts = [Decimal(value) for value in cls._cash_pattern.findall(subject)]
            cash_amount = sum(amounts, start=Decimal(0)) if amounts else None
        elif subject_lower.startswith("rights"):
            action_type = "rights"
            match = cls._ratio_pattern.search(subject)
            if match is not None:
                numerator, denominator = map(Decimal, match.groups())
        elif "demerger" in subject_lower:
            action_type = "demerger"
        else:
            return None

        return CorporateActionRecord(
            isin=isin,
            action_type=action_type,
            ex_date=ex_date,
            record_date=record_date,
            ratio_numerator=numerator,
            ratio_denominator=denominator,
            cash_amount=cash_amount,
            currency="INR",
            verification_status="verified",
            source=source,
        )

    @staticmethod
    def _download(url: str) -> bytes:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
                "User-Agent": "InvestmentGini/0.1 research-tool",
            },
        )
        with urlopen(request, timeout=30) as response:
            return cast(bytes, response.read())


class CsvUniverseProvider:
    required_fields: ClassVar[frozenset[str]] = frozenset({
        "universe",
        "universe_version",
        "symbol",
        "isin",
        "company_name",
        "exchange",
        "effective_from",
        "effective_to",
        "sector",
        "industry",
    })

    def fetch_memberships(self, path: Path) -> UniverseBatch:
        contents = path.read_bytes()
        source = SourceMetadata(
            provider="csv_import",
            source_identifier=str(path.resolve()),
            retrieved_at=datetime.now(UTC),
            checksum=hashlib.sha256(contents).hexdigest(),
        )
        records: list[UniverseMembershipRecord] = []
        issues: list[ProviderIssue] = []

        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            missing_columns = self.required_fields - set(reader.fieldnames or ())
            if missing_columns:
                issue = ProviderIssue(
                    row_number=1,
                    field_name=None,
                    reason=f"missing required columns: {', '.join(sorted(missing_columns))}",
                )
                return UniverseBatch(records=(), issues=(issue,), source=source)

            for row_number, row in enumerate(reader, start=2):
                try:
                    records.append(self._parse_row(row, row_number, source))
                except ValueError as error:
                    issues.append(
                        ProviderIssue(
                            row_number=row_number,
                            field_name=None,
                            reason=str(error),
                            observed_value=str(row),
                        )
                    )

        return UniverseBatch(records=tuple(records), issues=tuple(issues), source=source)

    @staticmethod
    def _parse_row(
        row: dict[str, str | None], row_number: int, source: SourceMetadata
    ) -> UniverseMembershipRecord:
        required_values = ("universe", "universe_version", "symbol", "isin", "company_name")
        missing_values = [field for field in required_values if not (row.get(field) or "").strip()]
        if missing_values:
            raise ValueError(f"row {row_number}: missing values: {', '.join(missing_values)}")

        isin = (row["isin"] or "").strip().upper()
        if len(isin) != 12:
            raise ValueError(f"row {row_number}: ISIN must contain 12 characters")

        try:
            exchange = Exchange((row["exchange"] or "").strip().upper())
            effective_from = date.fromisoformat((row["effective_from"] or "").strip())
            effective_to_raw = (row["effective_to"] or "").strip()
            effective_to = date.fromisoformat(effective_to_raw) if effective_to_raw else None
        except ValueError as error:
            raise ValueError(f"row {row_number}: invalid exchange or date: {error}") from error

        if effective_to is not None and effective_to < effective_from:
            raise ValueError(f"row {row_number}: effective_to precedes effective_from")

        return UniverseMembershipRecord(
            universe=(row["universe"] or "").strip(),
            universe_version=(row["universe_version"] or "").strip(),
            symbol=(row["symbol"] or "").strip().upper(),
            isin=isin,
            company_name=(row["company_name"] or "").strip(),
            exchange=exchange,
            sector=(row["sector"] or "").strip() or None,
            industry=(row["industry"] or "").strip() or None,
            effective_from=effective_from,
            effective_to=effective_to,
            source=source,
        )


class NiftyIndicesUniverseProvider:
    constituent_url = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"
    terms_url = "https://www.niftyindices.com/terms-of-use"
    expected_fields: ClassVar[frozenset[str]] = frozenset(
        {"Company Name", "Industry", "Symbol", "Series", "ISIN Code"}
    )

    def __init__(self, fetcher: Callable[[str], bytes] | None = None) -> None:
        self._fetcher = fetcher or self._download

    def fetch_memberships(self, as_of: date) -> UniverseBatch:
        contents = self._fetcher(self.constituent_url)
        source = SourceMetadata(
            provider="nse_indices",
            source_identifier=self.constituent_url,
            retrieved_at=datetime.now(UTC),
            checksum=hashlib.sha256(contents).hexdigest(),
            source_class="official_web",
            reliability_tier=1,
            terms_reference=self.terms_url,
        )
        records: list[UniverseMembershipRecord] = []
        issues: list[ProviderIssue] = []
        reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig")))
        missing_columns = self.expected_fields - set(reader.fieldnames or ())
        if missing_columns:
            issue = ProviderIssue(
                row_number=1,
                field_name=None,
                reason=f"missing official columns: {', '.join(sorted(missing_columns))}",
            )
            return UniverseBatch(records=(), issues=(issue,), source=source)

        seen_isins: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            try:
                record = self._parse_official_row(row, row_number, as_of, source)
                if record.isin in seen_isins:
                    raise ValueError(f"row {row_number}: duplicate ISIN {record.isin}")
                seen_isins.add(record.isin)
                records.append(record)
            except ValueError as error:
                issues.append(
                    ProviderIssue(
                        row_number=row_number,
                        field_name=None,
                        reason=str(error),
                        observed_value=str(row),
                    )
                )

        if len(records) != 200:
            issues.append(
                ProviderIssue(
                    row_number=1,
                    field_name=None,
                    reason=f"expected 200 unique constituents, received {len(records)}",
                )
            )
        return UniverseBatch(
            records=tuple(records),
            issues=tuple(issues),
            source=source,
            is_complete_snapshot=True,
        )

    @staticmethod
    def _parse_official_row(
        row: dict[str, str | None],
        row_number: int,
        as_of: date,
        source: SourceMetadata,
    ) -> UniverseMembershipRecord:
        company_name = (row.get("Company Name") or "").strip()
        symbol = (row.get("Symbol") or "").strip().upper()
        isin = (row.get("ISIN Code") or "").strip().upper()
        series = (row.get("Series") or "").strip().upper()
        if not company_name or not symbol or not isin:
            raise ValueError(f"row {row_number}: company name, symbol, and ISIN are required")
        if len(isin) != 12:
            raise ValueError(f"row {row_number}: ISIN must contain 12 characters")
        if series != "EQ":
            raise ValueError(f"row {row_number}: unsupported NSE series {series!r}")

        return UniverseMembershipRecord(
            universe="NIFTY 200",
            universe_version=as_of.isoformat(),
            symbol=symbol,
            isin=isin,
            company_name=company_name,
            exchange=Exchange.NSE,
            sector=None,
            industry=(row.get("Industry") or "").strip() or None,
            effective_from=as_of,
            effective_to=None,
            source=source,
        )

    @staticmethod
    def _download(url: str) -> bytes:
        request = Request(url, headers={"User-Agent": "InvestmentGini/0.1 research-tool"})
        with urlopen(request, timeout=30) as response:
            return cast(bytes, response.read())


class NseBhavcopyProvider:
    archive_url_template = (
        "https://nsearchives.nseindia.com/content/cm/"
        "BhavCopy_NSE_CM_0_0_0_{session}_F_0000.csv.zip"
    )
    terms_url = "https://www.nseindia.com/terms-of-use"
    expected_fields: ClassVar[frozenset[str]] = frozenset(
        {
            "TradDt",
            "BizDt",
            "Sgmt",
            "Src",
            "FinInstrmTp",
            "ISIN",
            "TckrSymb",
            "SctySrs",
            "OpnPric",
            "HghPric",
            "LwPric",
            "ClsPric",
            "PrvsClsgPric",
            "TtlTradgVol",
            "TtlTrfVal",
            "TtlNbOfTxsExctd",
        }
    )

    def __init__(self, fetcher: Callable[[str], bytes] | None = None) -> None:
        self._fetcher = fetcher or self._download

    def fetch_prices(self, session_date: date, requested_isins: set[str]) -> PriceBatch:
        url = self.archive_url_template.format(session=session_date.strftime("%Y%m%d"))
        contents = self._fetcher(url)
        source = SourceMetadata(
            provider="nse_bhavcopy",
            source_identifier=url,
            retrieved_at=datetime.now(UTC),
            checksum=hashlib.sha256(contents).hexdigest(),
            source_class="official_archive",
            reliability_tier=1,
            terms_reference=self.terms_url,
        )
        try:
            archive = ZipFile(io.BytesIO(contents))
            csv_members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_members) != 1:
                raise ValueError("official archive must contain exactly one CSV file")
            text = archive.read(csv_members[0]).decode("utf-8-sig")
        except (BadZipFile, UnicodeDecodeError) as error:
            raise ValueError("invalid official bhavcopy archive") from error

        reader = csv.DictReader(io.StringIO(text))
        missing_columns = self.expected_fields - set(reader.fieldnames or ())
        if missing_columns:
            issue = ProviderIssue(
                row_number=1,
                field_name=None,
                reason=f"missing official columns: {', '.join(sorted(missing_columns))}",
            )
            return PriceBatch(records=(), issues=(issue,), source=source)

        normalized_isins = {isin.strip().upper() for isin in requested_isins}
        records: list[PriceBarRecord] = []
        issues: list[ProviderIssue] = []
        seen_isins: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            isin = (row.get("ISIN") or "").strip().upper()
            if isin not in normalized_isins:
                continue
            if not self._is_equity_row(row):
                continue
            try:
                record = self._parse_price_row(row, row_number, session_date, source)
                if record.isin in seen_isins:
                    raise ValueError(f"row {row_number}: duplicate EQ row for ISIN {record.isin}")
                seen_isins.add(record.isin)
                records.append(record)
            except ValueError as error:
                issues.append(
                    ProviderIssue(
                        row_number=row_number,
                        field_name=None,
                        reason=str(error),
                        observed_value=str(row),
                    )
                )

        for missing_isin in sorted(normalized_isins - seen_isins):
            issues.append(
                ProviderIssue(
                    row_number=1,
                    field_name="ISIN",
                    reason=f"requested EQ ISIN {missing_isin} not found",
                    observed_value=missing_isin,
                )
            )
        return PriceBatch(records=tuple(records), issues=tuple(issues), source=source)

    @staticmethod
    def _is_equity_row(row: dict[str, str | None]) -> bool:
        return (
            (row.get("Sgmt") or "").strip().upper() == "CM"
            and (row.get("Src") or "").strip().upper() == "NSE"
            and (row.get("FinInstrmTp") or "").strip().upper() == "STK"
            and (row.get("SctySrs") or "").strip().upper() == "EQ"
        )

    @staticmethod
    def _parse_price_row(
        row: dict[str, str | None],
        row_number: int,
        expected_date: date,
        source: SourceMetadata,
    ) -> PriceBarRecord:
        try:
            trade_date = date.fromisoformat((row.get("TradDt") or "").strip())
            business_date = date.fromisoformat((row.get("BizDt") or "").strip())
            if trade_date != expected_date or business_date != expected_date:
                raise ValueError("trade and business dates must match the requested session")
            record = PriceBarRecord(
                isin=(row.get("ISIN") or "").strip().upper(),
                symbol=(row.get("TckrSymb") or "").strip().upper(),
                session_date=trade_date,
                series=(row.get("SctySrs") or "").strip().upper(),
                open=Decimal((row.get("OpnPric") or "").strip()),
                high=Decimal((row.get("HghPric") or "").strip()),
                low=Decimal((row.get("LwPric") or "").strip()),
                close=Decimal((row.get("ClsPric") or "").strip()),
                previous_close=Decimal((row.get("PrvsClsgPric") or "").strip()),
                volume=int((row.get("TtlTradgVol") or "").strip()),
                traded_value=Decimal((row.get("TtlTrfVal") or "").strip()),
                trade_count=int((row.get("TtlNbOfTxsExctd") or "").strip()),
                source=source,
            )
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"row {row_number}: invalid price data: {error}") from error
        if not record.isin or not record.symbol:
            raise ValueError(f"row {row_number}: ISIN and symbol are required")
        if min(record.open, record.high, record.low, record.close, record.previous_close) < 0:
            raise ValueError(f"row {row_number}: prices cannot be negative")
        if record.low > record.high or not record.low <= record.open <= record.high:
            raise ValueError(f"row {row_number}: inconsistent OHLC range")
        if not record.low <= record.close <= record.high:
            raise ValueError(f"row {row_number}: close is outside the daily range")
        if record.volume < 0 or record.traded_value < 0 or record.trade_count < 0:
            raise ValueError(f"row {row_number}: trading activity cannot be negative")
        return record

    @staticmethod
    def _download(url: str) -> bytes:
        last_error: OSError | None = None
        for attempt in range(3):
            try:
                request = Request(url, headers={"User-Agent": "InvestmentGini/0.1 research-tool"})
                with urlopen(request, timeout=60) as response:
                    return cast(bytes, response.read())
            except HTTPError as error:
                if error.code == 404:
                    raise NseArchiveUnavailableError(
                        f"official NSE archive is unavailable: {url}"
                    ) from error
                last_error = error
                if attempt < 2:
                    time.sleep(2**attempt)
            except OSError as error:
                last_error = error
                if attempt < 2:
                    time.sleep(2**attempt)
        raise RuntimeError(f"NSE archive download failed after 3 attempts: {last_error}")
