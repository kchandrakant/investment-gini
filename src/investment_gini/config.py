from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class AppConfig(BaseModel):
    database_url: str = "sqlite:///data/investment_gini.db"
    timezone: str = "Asia/Kolkata"
    base_currency: str = "INR"


class ScoringConfig(BaseModel):
    quality: float = Field(ge=0)
    earnings: float = Field(ge=0)
    momentum: float = Field(ge=0)
    valuation: float = Field(ge=0)
    financial_health: float = Field(ge=0)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> ScoringConfig:
        if abs(sum(self.model_dump().values()) - 1.0) > 1e-9:
            raise ValueError("scoring weights must sum to 1.0")
        return self


class RiskConfig(BaseModel):
    max_position_weight: float = Field(gt=0, le=1)
    max_sector_weight: float = Field(gt=0, le=1)
    max_risk_per_position: float = Field(gt=0, le=1)


class BacktestConfig(BaseModel):
    initial_capital: float = Field(gt=0)
    signal_cutoff: str
    execution_model: str
    slippage_bps: float = Field(ge=0)


class Settings(BaseModel):
    app: AppConfig
    scoring: ScoringConfig
    risk: RiskConfig
    backtest: BacktestConfig


def _read_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as config_file:
        return tomllib.load(config_file)


def load_settings(config_dir: Path = Path("config")) -> Settings:
    return Settings(
        app=AppConfig.model_validate(_read_toml(config_dir / "app.toml")["app"]),
        scoring=ScoringConfig.model_validate(_read_toml(config_dir / "scoring.toml")["weights"]),
        risk=RiskConfig.model_validate(_read_toml(config_dir / "risk.toml")["risk"]),
        backtest=BacktestConfig.model_validate(
            _read_toml(config_dir / "backtest.toml")["backtest"]
        ),
    )
