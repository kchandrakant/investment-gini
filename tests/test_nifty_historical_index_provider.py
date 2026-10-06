import hashlib
import json
from datetime import date
from decimal import Decimal

import pytest

from investment_gini.providers import NiftyHistoricalIndexProvider


def test_provider_posts_official_contract_and_parses_nifty_200() -> None:
    payload = [
        {
            "INDEX_NAME": "Nifty 200",
            "HistoricalDate": "30 Jan 2026",
            "OPEN": "14061.5",
            "HIGH": "14117.05",
            "LOW": "14019.4",
            "CLOSE": "14093.05",
        }
    ]
    contents = json.dumps(payload).encode("utf-8")
    requests: list[tuple[str, bytes]] = []

    def fetcher(url: str, body: bytes) -> bytes:
        requests.append((url, body))
        return contents

    provider = NiftyHistoricalIndexProvider(fetcher=fetcher)
    batch = provider.fetch_benchmark("Nifty 200", date(2026, 1, 1), date(2026, 1, 31))

    assert requests == [
        (
            provider.endpoint,
            b'{"cinfo":"{\'name\':\'NIFTY 200\',\'startDate\':\'01-Jan-2026\','
            b"'endDate':'31-Jan-2026','indexName':'Nifty 200'}\"}",
        )
    ]
    assert batch.issues == ()
    assert batch.records[0].benchmark_code == "NIFTY_200"
    assert batch.records[0].session_date == date(2026, 1, 30)
    assert batch.records[0].close == Decimal("14093.05")
    assert batch.source.checksum == hashlib.sha256(contents).hexdigest()
    assert batch.source.reliability_tier == 1


def test_provider_flags_mismatched_index_and_invalid_ohlc() -> None:
    payload = [
        {
            "INDEX_NAME": "Nifty 50",
            "HistoricalDate": "30 Jan 2026",
            "OPEN": "100",
            "HIGH": "90",
            "LOW": "95",
            "CLOSE": "92",
        },
        {
            "INDEX_NAME": "Nifty 200",
            "HistoricalDate": "29 Jan 2026",
            "OPEN": "100",
            "HIGH": "90",
            "LOW": "95",
            "CLOSE": "92",
        },
    ]
    provider = NiftyHistoricalIndexProvider(
        fetcher=lambda _url, _body: json.dumps(payload).encode("utf-8")
    )

    batch = provider.fetch_benchmark("Nifty 200", date(2026, 1, 1), date(2026, 1, 31))

    assert batch.records == ()
    assert "unexpected index name" in batch.issues[0].reason
    assert "inconsistent OHLC range" in batch.issues[1].reason


def test_provider_rejects_ranges_over_official_limit() -> None:
    provider = NiftyHistoricalIndexProvider(fetcher=lambda _url, _body: b"[]")

    with pytest.raises(ValueError, match="cannot exceed 365 days"):
        provider.fetch_benchmark("Nifty 200", date(2025, 1, 1), date(2026, 1, 2))