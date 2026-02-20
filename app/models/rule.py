from datetime import datetime
from sqlalchemy import Integer, String, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RuleRouter(Base):
    """Deterministic routing rules used by the ingest router."""

    __tablename__ = "rules_router"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # Keyword/prefix pattern (simple string match or regex prefix)
    pattern: Mapped[str] = mapped_column(String(256), nullable=False)
    # target table / domain
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
