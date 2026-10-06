"""Add provenance-aware benchmark index bars."""

from collections.abc import Sequence

from alembic import op

from investment_gini.models import BenchmarkBar

revision: str = "0004_benchmark_bars"
down_revision: str | None = "0003_corporate_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    BenchmarkBar.__table__.create(bind=op.get_bind())


def downgrade() -> None:
    BenchmarkBar.__table__.drop(bind=op.get_bind())