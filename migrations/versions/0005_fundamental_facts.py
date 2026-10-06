"""Add versioned metric definitions and fundamental fact revisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from investment_gini.models import FundamentalFact, MetricDefinition

revision: str = "0005_fundamental_facts"
down_revision: str | None = "0004_benchmark_bars"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("universe_memberships")
    }
    if "ended_by_source_record_id" not in columns:
        with op.batch_alter_table("universe_memberships") as batch_op:
            batch_op.add_column(
                sa.Column("ended_by_source_record_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_membership_closure_source",
                "source_records",
                ["ended_by_source_record_id"],
                ["id"],
            )
    MetricDefinition.__table__.create(bind=op.get_bind())
    FundamentalFact.__table__.create(bind=op.get_bind())


def downgrade() -> None:
    FundamentalFact.__table__.drop(bind=op.get_bind())
    MetricDefinition.__table__.drop(bind=op.get_bind())
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("universe_memberships")
    }
    if "ended_by_source_record_id" in columns:
        with op.batch_alter_table("universe_memberships") as batch_op:
            batch_op.drop_column("ended_by_source_record_id")