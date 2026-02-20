from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.schemas.state import CloseDayRequest, DailyLogResponse
from app.services.state import get_state_today, get_state_active, close_day
from app.models.daily_log import DailyLog

router = APIRouter(prefix="/state", tags=["state"])


@router.get("/today")
def state_today(
    day: Optional[date] = Query(default=None, description="ISO date, defaults to today"),
    db: Session = Depends(get_db),
):
    """Return the full state snapshot for a given day (default: today)."""
    return get_state_today(db=db, day=day)


@router.get("/active")
def state_active(db: Session = Depends(get_db)):
    """Return all active/open items: open tasks, active projects, and open days."""
    return get_state_active(db=db)


@router.post("/close-day", response_model=DailyLogResponse)
def state_close_day(payload: CloseDayRequest, db: Session = Depends(get_db)):
    """
    Close a day: compute totals, mark the daily_log as closed,
    and create a memory snapshot.
    """
    target = payload.day
    # Check if already closed
    existing: Optional[DailyLog] = (
        db.query(DailyLog).filter(DailyLog.day == target).first()
        if target
        else db.query(DailyLog).filter(DailyLog.day == date.today()).first()
    )
    if existing and existing.is_closed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Day {existing.day} is already closed.",
        )

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
