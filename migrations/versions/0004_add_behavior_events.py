"""add behavior_events table

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-21

Stores system reactions produced by the Behavioral Engine.
Unique constraint (event_type, reference_date) enforces idempotency.
Append-only; downgrade drops cleanly.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "behavior_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=False),
        sa.Column("event_metadata", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_behavior_event_type", "behavior_events", ["event_type"])
    op.create_index("ix_behavior_reference_date", "behavior_events", ["reference_date"])
    op.create_unique_constraint(
        "uq_behavior_event_type_date",
        "behavior_events",
        ["event_type", "reference_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_behavior_event_type_date", "behavior_events", type_="unique")
    op.drop_index("ix_behavior_reference_date", table_name="behavior_events")
    op.drop_index("ix_behavior_event_type", table_name="behavior_events")
    op.drop_table("behavior_events")
