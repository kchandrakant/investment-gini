from datetime import date
from http.client import HTTPMessage
from io import BytesIO
from urllib.error import HTTPError
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from investment_gini import providers
from investment_gini.providers import NseArchiveUnavailableError, NseBhavcopyProvider

HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,ISIN,TckrSymb,SctySrs,OpnPric,HghPric,"
    "LwPric,ClsPric,PrvsClsgPric,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd"
)


def _archive(*rows: str) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("BhavCopy.csv", "\n".join((HEADER, *rows)) + "\n")
    return output.getvalue()


def test_provider_parses_only_requested_eq_stock_rows() -> None:
    valid = "2026-09-02,2026-09-02,CM,NSE,STK,INE000000001,ALPHA,EQ,10,12,9,11,10,100,1100,20"
    wrong_series = (
        "2026-09-02,2026-09-02,CM,NSE,STK,INE000000002,BETA,BE,20,22,19,21,20,50,1050,10"
    )
    irrelevant = (
        "2026-09-02,2026-09-02,CM,NSE,STK,INE000000003,GAMMA,EQ,30,32,29,31,30,50,1550,8"
    )
    provider = NseBhavcopyProvider(fetcher=lambda _: _archive(valid, wrong_series, irrelevant))

    batch = provider.fetch_prices(date(2026, 9, 2), {"INE000000001", "INE000000002"})

    assert [record.isin for record in batch.records] == ["INE000000001"]
    assert batch.records[0].close.as_tuple().exponent == 0
    assert not batch.records[0].is_adjusted
    assert any("INE000000002 not found" in issue.reason for issue in batch.issues)
    assert batch.source.provider == "nse_bhavcopy"


def test_provider_rejects_a_mismatched_session_date() -> None:
    row = "2026-09-01,2026-09-01,CM,NSE,STK,INE000000001,ALPHA,EQ,10,12,9,11,10,100,1100,20"
    provider = NseBhavcopyProvider(fetcher=lambda _: _archive(row))

    batch = provider.fetch_prices(date(2026, 9, 2), {"INE000000001"})

    assert not batch.records
    assert any("dates must match" in issue.reason for issue in batch.issues)


def test_download_classifies_a_404_as_archive_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_archive(*args: object, **kwargs: object) -> None:
        raise HTTPError("fixture://missing", 404, "Not Found", HTTPMessage(), None)

    monkeypatch.setattr(providers, "urlopen", missing_archive)

    with pytest.raises(NseArchiveUnavailableError, match="archive is unavailable"):
        NseBhavcopyProvider._download("fixture://missing")