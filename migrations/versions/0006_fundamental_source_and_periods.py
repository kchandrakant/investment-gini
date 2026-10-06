"""Preserve filing artifact hashes, reported units, and full period identity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_fundamental_source_and_periods"
down_revision: str | None = "0005_fundamental_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    source_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("source_records")
    }
    if "source_artifact_checksum" not in source_columns:
        op.add_column(
            "source_records",
            sa.Column("source_artifact_checksum", sa.String(length=64), nullable=True),
        )

    fact_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("fundamental_facts")
    }
    if "reported_unit" not in fact_columns:
        with op.batch_alter_table("fundamental_facts") as batch_op:
            batch_op.add_column(sa.Column("reported_unit", sa.String(length=40), nullable=True))
        op.execute(
            "UPDATE fundamental_facts SET reported_unit = 'unspecified' "
            "WHERE reported_unit IS NULL"
        )
        with op.batch_alter_table("fundamental_facts") as batch_op:
            batch_op.alter_column(
                "reported_unit",
                existing_type=sa.String(length=40),
                nullable=False,
            )

    constraints = sa.inspect(bind).get_unique_constraints("fundamental_facts")
    revision_constraint = next(
        (
            constraint
            for constraint in constraints
            if constraint.get("name") == "uq_fundamental_fact_revision"
        ),
        None,
    )
    if (
        revision_constraint is not None
        and "period_start" not in revision_constraint["column_names"]
    ):
        with op.batch_alter_table("fundamental_facts") as batch_op:
            batch_op.drop_constraint("uq_fundamental_fact_revision", type_="unique")
            batch_op.create_unique_constraint(
                "uq_fundamental_fact_revision",
                [
                    "instrument_id",
                    "metric_definition_id",
                    "period_start",
                    "period_end",
                    "consolidation_scope",
                    "available_at",
                ],
            )


def downgrade() -> None:
    bind = op.get_bind()
    constraints = sa.inspect(bind).get_unique_constraints("fundamental_facts")
    revision_constraint = next(
        (
            constraint
            for constraint in constraints
            if constraint.get("name") == "uq_fundamental_fact_revision"
        ),
        None,
    )
    if revision_constraint is not None and "period_start" in revision_constraint["column_names"]:
        with op.batch_alter_table("fundamental_facts") as batch_op:
            batch_op.drop_constraint("uq_fundamental_fact_revision", type_="unique")
            batch_op.create_unique_constraint(
                "uq_fundamental_fact_revision",
                [
                    "instrument_id",
                    "metric_definition_id",
                    "period_end",
                    "consolidation_scope",
                    "available_at",
                ],
            )

    fact_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("fundamental_facts")
    }
    if "reported_unit" in fact_columns:
        with op.batch_alter_table("fundamental_facts") as batch_op:
            batch_op.drop_column("reported_unit")
    source_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("source_records")
    }
    if "source_artifact_checksum" in source_columns:
        op.drop_column("source_records", "source_artifact_checksum")