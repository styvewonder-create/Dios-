"""
NarrativeMemory — derived projection of a day (or week) in human-readable form.

Rules (CLAUDE.md):
- Append-only: no UPDATE or DELETE.
- Columns that store lists are JSON-encoded Text (stdlib json, no new deps).
- The event store (entries) remains the source of truth; this table is a projection.
"""
from datetime import datetime, date
from sqlalchemy import Integer, String, Text, DateTime, Date, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NarrativeMemory(Base):
    """
    Structured narrative snapshot compiled from a day's or week's raw events.

    snapshot_type:
      "daily"   — compiled from a single calendar day
      "weekly"  — compiled from 7 consecutive daily snapshots

    For daily snapshots: date = the calendar day.
    For weekly snapshots: date = the Monday that starts the week.

    Uniqueness: (date, snapshot_type) — one snapshot per day-type pair.
    Re-compiling the same day replaces the existing snapshot (upsert).
    """

    __tablename__ = "narrative_memory"
    __table_args__ = (
        UniqueConstraint("date", "snapshot_type", name="uq_narrative_date_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="daily", index=True
    )

    # Human-readable narrative fields
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_events: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON array of notable event strings",
    )
    emotional_state: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="Heuristic tag(s) joined by '+': productive, quiet, financially_positive …",
    )
    decisions_made: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON array of decision strings extracted from entries",
    )
    lessons: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON array of lessons / facts worth remembering",
    )
    tags: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
        comment="Comma-separated inferred tags (entry types present, topics)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
