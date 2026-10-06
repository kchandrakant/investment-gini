import json
from datetime import date
from decimal import Decimal

from investment_gini.providers import NseCorporateActionProvider


def test_official_provider_parses_supported_actions_and_filters_instruments() -> None:
    payload = [
        {
            "isin": "INE000000001",
            "series": "EQ",
            "exDate": "12-Aug-2025",
            "recDate": "12-Aug-2025",
            "subject": (
                "Face Value Split (Sub-Division) - "
                "From Rs 10/- Per Share To Rs 5/- Per Share"
            ),
        },
        {
            "isin": "INE000000001",
            "series": "EQ",
            "exDate": "26-Aug-2025",
            "recDate": "27-Aug-2025",
            "subject": "Bonus 1:1",
        },
        {
            "isin": "INE000000001",
            "series": "EQ",
            "exDate": "16-Jan-2026",
            "recDate": "17-Jan-2026",
            "subject": "Interim Dividend Rs 11 Per Share/ Special Dividend Rs 46 Per Share",
        },
        {
            "isin": "INE000000002",
            "series": "EQ",
            "exDate": "16-Jan-2026",
            "recDate": "17-Jan-2026",
            "subject": "Bonus 1:1",
        },
    ]
    provider = NseCorporateActionProvider(
        fetcher=lambda _: json.dumps(payload).encode("utf-8")
    )

    batch = provider.fetch_actions(
        date(2025, 8, 1), date(2026, 2, 1), {"INE000000001"}
    )

    assert batch.issues == ()
    assert [record.action_type for record in batch.records] == [
        "split",
        "bonus",
        "dividend",
    ]
    assert batch.records[0].ratio_numerator == Decimal("10")
    assert batch.records[0].ratio_denominator == Decimal("5")
    assert batch.records[2].cash_amount == Decimal("57")
    assert batch.source.provider == "nse_corporate_actions"


def test_official_provider_flags_ambiguous_adjusting_action() -> None:
    payload = [
        {
            "isin": "INE000000001",
            "series": "EQ",
            "exDate": "12-Aug-2025",
            "recDate": "-",
            "subject": "Face Value Split pending details",
        }
    ]
    provider = NseCorporateActionProvider(
        fetcher=lambda _: json.dumps(payload).encode("utf-8")
    )

    batch = provider.fetch_actions(
        date(2025, 8, 1), date(2025, 8, 31), {"INE000000001"}
    )

    assert batch.records == ()
    assert "ambiguous split ratio" in batch.issues[0].reason