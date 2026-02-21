"""
NorthStarSnapshot — persisted results of the Clarity Score calculation.

Append-only. The event store + narrative_memory remain the source of truth;
this table is a derived cache so callers don't recompute on every request.

period_type values:
  "daily"   — clarity for a single calendar day (bool: 1.0 or 0.0)
  "weekly"  — clarity score for a 7-day window ending at reference_date
"""
from datetime import datetime, date
from sqlalchemy import Integer, String, Numeric, DateTime, Date, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from app.db.base import Base


class NorthStarSnapshot(Base):
    __tablename__ = "north_star_snapshots"
    __table_args__ = (
        UniqueConstraint("period_type", "reference_date", name="uq_north_star_period_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    period_type: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True,
        comment='"daily" or "weekly"',
    )
    reference_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    clarity_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False,
        comment="0.0000–1.0000; for daily snapshots: exactly 0 or 1",
    )
    complete_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Count of days that meet Complete Day criteria (weekly only meaningful)",
    )
    total_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        comment="Window size; 1 for daily, 7 for weekly",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
