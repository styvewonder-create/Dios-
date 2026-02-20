from datetime import date
from typing import Optional
from pydantic import BaseModel


class CloseDayRequest(BaseModel):
    day: Optional[date] = None
    summary: Optional[str] = None


class DailyLogResponse(BaseModel):
    id: int
    day: str
    is_closed: bool
    total_entries: int
    total_tasks: int
    total_transactions: int
    total_facts: int
    summary: Optional[str]
    closed_at: Optional[str]

    class Config:
        from_attributes = True
