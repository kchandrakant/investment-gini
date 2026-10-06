from pathlib import Path

import pytest
from pydantic import ValidationError

from investment_gini.config import ScoringConfig, load_settings


def test_load_settings() -> None:
    settings = load_settings(Path("config"))

    assert settings.app.base_currency == "INR"
    assert sum(settings.scoring.model_dump().values()) == pytest.approx(1.0)


def test_scoring_weights_must_sum_to_one() -> None:
    with pytest.raises(ValidationError, match=r"must sum to 1\.0"):
        ScoringConfig(
            quality=0.2,
            earnings=0.2,
            momentum=0.2,
            valuation=0.2,
            financial_health=0.1,
        )
