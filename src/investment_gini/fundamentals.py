from investment_gini.domain import MetricDefinitionRecord

FUNDAMENTAL_METRIC_VERSION = "reported-v1"


def fundamental_metric_catalog() -> tuple[MetricDefinitionRecord, ...]:
    definitions = (
        (
            "revenue",
            "Revenue",
            "Reported revenue for the stated duration period.",
            "duration",
            "currency",
        ),
        (
            "net_profit",
            "Net profit",
            "Reported profit after tax for the stated duration period.",
            "duration",
            "currency",
        ),
        (
            "operating_cash_flow",
            "Operating cash flow",
            "Net cash generated from operating activities for the stated duration period.",
            "duration",
            "currency",
        ),
        (
            "total_assets",
            "Total assets",
            "Reported total assets at the period end.",
            "instant",
            "currency",
        ),
        (
            "total_liabilities",
            "Total liabilities",
            "Reported total liabilities at the period end.",
            "instant",
            "currency",
        ),
        (
            "total_equity",
            "Total equity",
            "Reported total equity at the period end.",
            "instant",
            "currency",
        ),
        (
            "cash_and_equivalents",
            "Cash and equivalents",
            "Reported cash and cash equivalents at the period end.",
            "instant",
            "currency",
        ),
        (
            "borrowings",
            "Borrowings",
            "Reported borrowings at the period end.",
            "instant",
            "currency",
        ),
        (
            "shares_outstanding",
            "Shares outstanding",
            "Reported shares outstanding at the period end.",
            "instant",
            "shares",
        ),
        (
            "promoter_holding_pct",
            "Promoter holding",
            "Reported promoter ownership percentage for the filing period.",
            "instant",
            "percentage",
        ),
        (
            "promoter_pledge_pct",
            "Promoter pledge",
            "Reported pledged promoter ownership percentage for the filing period.",
            "instant",
            "percentage",
        ),
    )
    return tuple(
        MetricDefinitionRecord(
            code=code,
            version=FUNDAMENTAL_METRIC_VERSION,
            name=name,
            description=description,
            unit=unit,
            period_type=period_type,
            value_kind=unit,
            formula=None,
            is_derived=False,
        )
        for code, name, description, period_type, unit in definitions
    )