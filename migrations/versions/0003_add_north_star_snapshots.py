"""add north_star_snapshots table

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-21

Stores cached Clarity Score results derived from the event store + narrative_memory.
Append-only; downgrade drops the table cleanly.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "north_star_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("period_type", sa.String(16), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("clarity_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("complete_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_north_star_period_type", "north_star_snapshots", ["period_type"])
    op.create_index("ix_north_star_reference_date", "north_star_snapshots", ["reference_date"])
    op.create_unique_constraint(
        "uq_north_star_period_date",
        "north_star_snapshots",
        ["period_type", "reference_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_north_star_period_date", "north_star_snapshots", type_="unique")
    op.drop_index("ix_north_star_reference_date", table_name="north_star_snapshots")
    op.drop_index("ix_north_star_period_type", table_name="north_star_snapshots")
    op.drop_table("north_star_snapshots")
