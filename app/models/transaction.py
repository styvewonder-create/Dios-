from datetime import datetime, date
from sqlalchemy import Integer, String, Text, Numeric, DateTime, Date, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal
import enum

from app.db.base import Base


class TransactionType(str, enum.Enum):
    income = "income"
    expense = "expense"
    transfer = "transfer"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    tx_type: Mapped[str] = mapped_column(
        Enum(TransactionType, name="transaction_type_enum"),
        nullable=False,
        default=TransactionType.expense,
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
