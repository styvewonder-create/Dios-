"""
State router.

GET  /state/today
GET  /state/active
POST /state/close-day
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.schemas.state import CloseDayRequest, DailyLogResponse
from app.services.state import get_state_today, get_state_active, close_day
from app.models.daily_log import DailyLog
from app.core.errors import DayAlreadyClosedError

router = APIRouter(prefix="/state", tags=["state"])


@router.get(
    "/today",
    summary="Full snapshot of a day",
    responses={200: {"description": "Day snapshot with all entries, tasks, transactions, etc."}},
)
def state_today(
    day: Optional[date] = Query(
        default=None,
        description="ISO date (YYYY-MM-DD). Defaults to today UTC.",
        examples=["2026-02-20"],
    ),
    db: Session = Depends(get_db),
):
    """Return all ingested data for a given day, grouped by domain."""
    return get_state_today(db=db, day=day)


@router.get(
    "/active",
    summary="All open/active items across all days",
    responses={200: {"description": "Open tasks, active projects, and unclosed days."}},
)
def state_active(db: Session = Depends(get_db)):
    """Return open tasks, active projects, and days that have entries but are not yet closed."""
    return get_state_active(db=db)


@router.post(
    "/close-day",
    response_model=DailyLogResponse,
    summary="Close a day and create a memory snapshot",
    responses={
        200: {"description": "Day closed successfully."},
        409: {"description": "Day is already closed."},
    },
)
def state_close_day(payload: CloseDayRequest, db: Session = Depends(get_db)):
    """
    Close a day:
    - Compute total counts for entries, tasks, transactions, facts.
    - Mark the `daily_logs` record as closed.
    - Create a `memory_snapshots` record for LLM context.

    Raises **409** if the day is already closed.
    """
    target = payload.day or date.today()
    existing: Optional[DailyLog] = (
        db.query(DailyLog).filter(DailyLog.day == target).first()
    )
    if existing and existing.is_closed:
        raise DayAlreadyClosedError(day=existing.day)

    log = close_day(db=db, day=payload.day, summary=payload.summary)
    return DailyLogResponse(
        id=log.id,
        day=str(log.day),
        is_closed=log.is_closed,
        total_entries=log.total_entries,
        total_tasks=log.total_tasks,
        total_transactions=log.total_transactions,
        total_facts=log.total_facts,
        summary=log.summary,
        closed_at=log.closed_at.isoformat() if log.closed_at else None,
    )
