"""Add raw end-of-day price bars."""

from collections.abc import Sequence

from alembic import op

from investment_gini.models import PriceBar

revision: str = "0002_price_bars"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    PriceBar.__table__.create(bind=op.get_bind())


def downgrade() -> None:
    PriceBar.__table__.drop(bind=op.get_bind())