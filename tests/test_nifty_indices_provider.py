from datetime import date

from investment_gini.providers import NiftyIndicesUniverseProvider


def _official_csv(row_count: int = 200) -> bytes:
    rows = ["Company Name,Industry,Symbol,Series,ISIN Code"]
    rows.extend(
        f"Company {number},Industry {number % 5},STOCK{number},EQ,INE{number:09d}"
        for number in range(row_count)
    )
    return ("\n".join(rows) + "\n").encode()


def test_official_provider_builds_dated_snapshot() -> None:
    provider = NiftyIndicesUniverseProvider(fetcher=lambda _: _official_csv())

    batch = provider.fetch_memberships(date(2026, 8, 31))

    assert len(batch.records) == 200
    assert not batch.issues
    assert len({record.isin for record in batch.records}) == 200
    assert {record.universe_version for record in batch.records} == {"2026-08-31"}
    assert batch.source.provider == "nse_indices"
    assert batch.source.reliability_tier == 1
    assert batch.source.source_identifier == provider.constituent_url


def test_official_provider_rejects_incomplete_snapshot() -> None:
    provider = NiftyIndicesUniverseProvider(fetcher=lambda _: _official_csv(199))

    batch = provider.fetch_memberships(date(2026, 8, 31))

    assert len(batch.records) == 199
    assert any("expected 200" in issue.reason for issue in batch.issues)