from pathlib import Path

from sqlalchemy import create_engine, inspect

from investment_gini.application import initialize_database
from investment_gini.config import load_settings


def test_initial_migration_creates_foundation_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    settings = load_settings()
    settings.app.database_url = f"sqlite:///{database_path}"

    initialize_database(settings)

    tables = set(inspect(create_engine(settings.app.database_url)).get_table_names())
    assert {
        "alembic_version",
        "benchmark_bars",
        "corporate_actions",
        "data_quality_flags",
        "data_sources",
        "fundamental_facts",
        "ingestion_runs",
        "instrument_symbols",
        "instruments",
        "metric_definitions",
        "price_bars",
        "source_records",
        "universe_memberships",
        "universes",
    } == tables
    inspector = inspect(create_engine(settings.app.database_url))
    assert "source_artifact_checksum" in {
        column["name"] for column in inspector.get_columns("source_records")
    }
    assert "reported_unit" in {
        column["name"] for column in inspector.get_columns("fundamental_facts")
    }
    assert "period_start" in next(
        constraint["column_names"]
        for constraint in inspector.get_unique_constraints("fundamental_facts")
        if constraint["name"] == "uq_fundamental_fact_revision"
    )