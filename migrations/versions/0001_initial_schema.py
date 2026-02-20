"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-02-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ENUM types ---
    entry_type_enum = sa.Enum(
        "note", "task", "transaction", "fact", "event", "metric", "project", "unknown",
        name="entry_type_enum",
    )
    entry_type_enum.create(op.get_bind(), checkfirst=True)

    transaction_type_enum = sa.Enum(
        "income", "expense", "transfer", name="transaction_type_enum"
    )
    transaction_type_enum.create(op.get_bind(), checkfirst=True)

    task_status_enum = sa.Enum(
        "pending", "in_progress", "done", "cancelled", name="task_status_enum"
    )
    task_status_enum.create(op.get_bind(), checkfirst=True)

    project_status_enum = sa.Enum(
        "active", "paused", "done", "archived", name="project_status_enum"
    )
    project_status_enum.create(op.get_bind(), checkfirst=True)

    # --- entries ---
    op.create_table(
        "entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raw", sa.Text(), nullable=False),
        sa.Column("entry_type", sa.Enum(
            "note", "task", "transaction", "fact", "event", "metric", "project", "unknown",
            name="entry_type_enum", create_type=False,
        ), nullable=False),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("routed_to", sa.String(64), nullable=True),
        sa.Column("rule_matched", sa.String(128), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entries_id", "entries", ["id"])

    # --- facts ---
    op.create_table(
        "facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_facts_id", "facts", ["id"])
    op.create_index("ix_facts_entry_id", "facts", ["entry_id"])

    # --- metrics_daily ---
    op.create_table(
        "metrics_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("value", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "day", name="uq_metric_name_day"),
    )
    op.create_index("ix_metrics_daily_id", "metrics_daily", ["id"])
    op.create_index("ix_metrics_daily_name", "metrics_daily", ["name"])
    op.create_index("ix_metrics_daily_day", "metrics_daily", ["day"])

    # --- transactions ---
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("tx_type", sa.Enum(
            "income", "expense", "transfer", name="transaction_type_enum", create_type=False
        ), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_id", "transactions", ["id"])
    op.create_index("ix_transactions_entry_id", "transactions", ["entry_id"])
    op.create_index("ix_transactions_day", "transactions", ["day"])

    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum(
            "active", "paused", "done", "archived", name="project_status_enum", create_type=False
        ), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_id", "projects", ["id"])

    # --- tasks ---
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum(
            "pending", "in_progress", "done", "cancelled", name="task_status_enum", create_type=False
        ), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_id", "tasks", ["id"])
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_day", "tasks", ["day"])

    # --- rules_router ---
    op.create_table(
        "rules_router",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("pattern", sa.String(256), nullable=False),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("entry_type", sa.String(64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_rules_router_id", "rules_router", ["id"])

    # --- memory_snapshots ---
    op.create_table(
        "memory_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("snapshot_type", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_snapshots_id", "memory_snapshots", ["id"])
    op.create_index("ix_memory_snapshots_day", "memory_snapshots", ["day"])

    # --- daily_logs ---
    op.create_table(
        "daily_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("total_entries", sa.Integer(), nullable=False),
        sa.Column("total_tasks", sa.Integer(), nullable=False),
        sa.Column("total_transactions", sa.Integer(), nullable=False),
        sa.Column("total_facts", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day"),
    )
    op.create_index("ix_daily_logs_id", "daily_logs", ["id"])
    op.create_index("ix_daily_logs_day", "daily_logs", ["day"])

    # --- seed default rules ---
    op.execute("""
        INSERT INTO rules_router (name, pattern, target, entry_type, priority, is_active, description)
        VALUES
          ('task_prefix',      '^(TODO|TASK|tarea|hacer)',         'tasks',         'task',        100, true, 'Lines starting with TODO/TASK/tarea/hacer'),
          ('income_keyword',   '(ingreso|income|cobré|cobré|cobr)', 'transactions', 'transaction', 90,  true, 'Income transactions'),
          ('expense_keyword',  '(gast|pagué|pague|compré|compre|expense|paid)', 'transactions', 'transaction', 80, true, 'Expense transactions'),
          ('fact_keyword',     '^(FACT|DATO|nota|note):',           'facts',         'fact',        70,  true, 'Explicit fact entries'),
          ('metric_keyword',   '^(METRIC|METRICA|KPI):',            'metrics_daily', 'metric',     60,  true, 'Metric entries'),
          ('project_keyword',  '^(PROJECT|PROYECTO):',              'projects',      'project',    50,  true, 'Project entries'),
          ('default_note',     '.*',                                'facts',         'note',        0,   true, 'Catch-all: store as fact/note')
    """)


def downgrade() -> None:
    op.drop_table("daily_logs")
    op.drop_table("memory_snapshots")
    op.drop_table("rules_router")
    op.drop_table("tasks")
    op.drop_table("projects")
    op.drop_table("transactions")
    op.drop_table("metrics_daily")
    op.drop_table("facts")
    op.drop_table("entries")

    op.execute("DROP TYPE IF EXISTS project_status_enum")
    op.execute("DROP TYPE IF EXISTS task_status_enum")
    op.execute("DROP TYPE IF EXISTS transaction_type_enum")
    op.execute("DROP TYPE IF EXISTS entry_type_enum")
