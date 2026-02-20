from datetime import date
from sqlalchemy import Integer, String, Numeric, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from app.db.base import Base


class MetricDaily(Base):
    __tablename__ = "metrics_daily"
    __table_args__ = (UniqueConstraint("name", "day", name="uq_metric_name_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
