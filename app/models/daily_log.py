from datetime import datetime, date
from sqlalchemy import Integer, String, Text, Boolean, DateTime, Date, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyLog(Base):
    """Summary log for each closed day."""

    __tablename__ = "daily_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_entries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_transactions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_facts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
