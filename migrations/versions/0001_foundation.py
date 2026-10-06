"""Create the provenance-aware universe foundation."""

from collections.abc import Sequence

from alembic import op

from investment_gini.models import Base

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table_names = {
        "instruments",
        "instrument_symbols",
        "universes",
        "data_sources",
        "ingestion_runs",
        "source_records",
        "universe_memberships",
        "data_quality_flags",
    }
    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[table for table in Base.metadata.sorted_tables if table.name in table_names],
    )


def downgrade() -> None:
    table_names = {
        "instruments",
        "instrument_symbols",
        "universes",
        "data_sources",
        "ingestion_runs",
        "source_records",
        "universe_memberships",
        "data_quality_flags",
    }
    Base.metadata.drop_all(
        bind=op.get_bind(),
        tables=[
            table for table in reversed(Base.metadata.sorted_tables) if table.name in table_names
        ],
    )