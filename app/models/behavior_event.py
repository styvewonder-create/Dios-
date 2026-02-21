"""
BehaviorEvent — system reactions produced by the Behavioral Engine.

Append-only. One row per (event_type, reference_date) — the unique
constraint enforces idempotency at the DB level.

event_type values (see app/services/behavior_engine.py for full docs):
  "clarity_warning"     — weekly_clarity_score < 0.4
  "reset_day_protocol"  — 3 consecutive incomplete days (also creates a Task)
  "perfect_week"        — weekly_clarity_score == 1.0

metadata: JSON-encoded dict stored as Text (no external deps).
"""
from datetime import datetime, date
from sqlalchemy import Integer, String, Text, DateTime, Date, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BehaviorEvent(Base):
    __tablename__ = "behavior_events"
    __table_args__ = (
        UniqueConstraint("event_type", "reference_date", name="uq_behavior_event_type_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reference_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_metadata: Mapped[str | None] = mapped_column(
        "event_metadata", Text, nullable=True,
        comment="JSON-encoded dict with context specific to each event_type",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
