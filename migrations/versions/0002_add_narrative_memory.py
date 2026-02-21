"""add narrative_memory table

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-21

narrative_memory is an append-only projection table.
The event store (entries) remains the source of truth.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "narrative_memory",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("snapshot_type", sa.String(16), nullable=False, server_default="daily"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_events", sa.Text(), nullable=True),
        sa.Column("emotional_state", sa.String(128), nullable=True),
        sa.Column("decisions_made", sa.Text(), nullable=True),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column("tags", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_narrative_memory_date", "narrative_memory", ["date"])
    op.create_index("ix_narrative_memory_snapshot_type", "narrative_memory", ["snapshot_type"])
    op.create_unique_constraint(
        "uq_narrative_date_type", "narrative_memory", ["date", "snapshot_type"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_narrative_date_type", "narrative_memory", type_="unique")
    op.drop_index("ix_narrative_memory_snapshot_type", table_name="narrative_memory")
    op.drop_index("ix_narrative_memory_date", table_name="narrative_memory")
    op.drop_table("narrative_memory")
