from datetime import datetime, date
from sqlalchemy import Integer, String, Text, DateTime, Date, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MemorySnapshot(Base):
    """Periodic snapshots of system state / context for LLM or review."""

    __tablename__ = "memory_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(64), nullable=False, default="daily")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
