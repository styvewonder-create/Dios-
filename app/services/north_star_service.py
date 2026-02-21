"""
North Star Metric service — Clarity Score.

Definition
----------
Clarity Score = percentage of days in the last 7 days that are "Complete Days".

A day is "complete" when ALL three conditions hold:
  1. At least 3 logged events in `entries`.
  2. At least 1 task marked done OR at least 1 transaction recorded.
  3. A daily narrative memory snapshot has been compiled for that day.

All data is derived from the event store (`entries`) + `narrative_memory`.
No hardcoded assumptions about what constitutes "activity".

Public API
----------
calculate_daily_clarity(db, day)            -> DailyClarity
calculate_weekly_clarity(db, reference_date) -> WeeklyClarity
get_north_star(db, reference_date)          -> WeeklyClarity   (main endpoint helper)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.entry import Entry
from app.models.task import Task, TaskStatus
from app.models.transaction import Transaction
from app.models.narrative_memory import NarrativeMemory
from app.models.north_star import NorthStarSnapshot


# ---------------------------------------------------------------------------
# Result types (plain dataclasses — no ORM, no Pydantic)
# ---------------------------------------------------------------------------

@dataclass
class DailyClarity:
    day: date
    is_complete: bool
    # Breakdown for transparency
    event_count: int         # entries on this day
    has_outcome: bool        # task done OR transaction recorded
    has_memory_snapshot: bool


@dataclass
class WeeklyClarity:
    reference_date: date     # last day of the 7-day window
    clarity_score: Decimal   # 0.0000 – 1.0000
    complete_days: int
    total_days: int          # always 7
    days: list[DailyClarity]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIN_EVENTS = 3


def _today() -> date:
    return datetime.now(tz=timezone.utc).date()


def _ev(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


# ---------------------------------------------------------------------------
# Core — single day check (pure query, no writes)
# ---------------------------------------------------------------------------

def _check_day(db: Session, day: date) -> DailyClarity:
    """
    Evaluate whether a single day meets the Complete Day criteria.
    Reads only from: entries, tasks, transactions, narrative_memory.
    """
    # Criterion 1: at least MIN_EVENTS entries
    event_count: int = (
        db.query(func.count(Entry.id))
        .filter(Entry.day == day)
        .scalar()
        or 0
    )

    # Criterion 2: at least 1 task done OR 1 transaction
    task_done: int = (
        db.query(func.count(Task.id))
        .filter(Task.day == day, Task.status == TaskStatus.done)
        .scalar()
        or 0
    )
    tx_count: int = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.day == day)
        .scalar()
        or 0
    )
    has_outcome = (task_done > 0) or (tx_count > 0)

    # Criterion 3: daily narrative memory snapshot exists
    has_memory_snapshot: bool = (
        db.query(NarrativeMemory.id)
        .filter(
            NarrativeMemory.date == day,
            NarrativeMemory.snapshot_type == "daily",
        )
        .first()
        is not None
    )

    is_complete = (event_count >= MIN_EVENTS) and has_outcome and has_memory_snapshot

    return DailyClarity(
        day=day,
        is_complete=is_complete,
        event_count=event_count,
        has_outcome=has_outcome,
        has_memory_snapshot=has_memory_snapshot,
    )


# ---------------------------------------------------------------------------
# Public — single day
# ---------------------------------------------------------------------------

def calculate_daily_clarity(db: Session, day: Optional[date] = None) -> DailyClarity:
    """Return the Complete Day evaluation for a single calendar day."""
    return _check_day(db, day or _today())


# ---------------------------------------------------------------------------
# Public — weekly window
# ---------------------------------------------------------------------------

def calculate_weekly_clarity(
    db: Session,
    reference_date: Optional[date] = None,
) -> WeeklyClarity:
    """
    Evaluate the Clarity Score for the 7-day window ending on reference_date.
    Window: [reference_date - 6, reference_date] inclusive.
    """
    end = reference_date or _today()
    days = [end - timedelta(days=i) for i in range(6, -1, -1)]  # oldest → newest

    daily_results = [_check_day(db, d) for d in days]
    complete = sum(1 for r in daily_results if r.is_complete)
    total = len(days)

    raw_score = Decimal(complete) / Decimal(total)
    score = raw_score.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    return WeeklyClarity(
        reference_date=end,
        clarity_score=score,
        complete_days=complete,
        total_days=total,
        days=daily_results,
    )


# ---------------------------------------------------------------------------
# Public — main endpoint helper (calculate + upsert cache)
# ---------------------------------------------------------------------------

def get_north_star(
    db: Session,
    reference_date: Optional[date] = None,
) -> WeeklyClarity:
    """
    Calculate the current Clarity Score and persist the result in
    north_star_snapshots (upsert by reference_date + 'weekly').
    Returns the WeeklyClarity dataclass for serialization by the router.
    """
    result = calculate_weekly_clarity(db, reference_date)
    _upsert_snapshot(db, result)
    return result


def _upsert_snapshot(db: Session, result: WeeklyClarity) -> None:
    """Persist or refresh a weekly north_star_snapshots row."""
    existing = (
        db.query(NorthStarSnapshot)
        .filter(
            NorthStarSnapshot.period_type == "weekly",
            NorthStarSnapshot.reference_date == result.reference_date,
        )
        .first()
    )
    if existing is not None:
        existing.clarity_score = result.clarity_score
        existing.complete_days = result.complete_days
        existing.total_days = result.total_days
    else:
        db.add(NorthStarSnapshot(
            period_type="weekly",
            reference_date=result.reference_date,
            clarity_score=result.clarity_score,
            complete_days=result.complete_days,
            total_days=result.total_days,
        ))
    db.commit()
