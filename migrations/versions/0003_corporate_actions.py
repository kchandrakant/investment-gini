"""Add provenance-aware corporate actions."""

from collections.abc import Sequence

from alembic import op

from investment_gini.models import CorporateAction

revision: str = "0003_corporate_actions"
down_revision: str | None = "0002_price_bars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    CorporateAction.__table__.create(bind=op.get_bind())


def downgrade() -> None:
    CorporateAction.__table__.drop(bind=op.get_bind())