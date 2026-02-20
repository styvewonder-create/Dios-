from datetime import datetime, date
from sqlalchemy import Integer, String, Text, DateTime, Date, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.db.base import Base


class EntryType(str, enum.Enum):
    note = "note"
    task = "task"
    transaction = "transaction"
    fact = "fact"
    event = "event"
    metric = "metric"
    project = "project"
    unknown = "unknown"


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    raw: Mapped[str] = mapped_column(Text, nullable=False)
    entry_type: Mapped[str] = mapped_column(
        Enum(EntryType, name="entry_type_enum"), nullable=False, default=EntryType.unknown
    )
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    routed_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_matched: Mapped[str | None] = mapped_column(String(128), nullable=True)
