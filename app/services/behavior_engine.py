"""
Behavioral Engine — automatic system reactions driven by the North Star metric.

Rules (evaluated every time GET /metrics/north-star is called)
--------------------------------------------------------------
  1. CLARITY_WARNING
     Trigger : weekly_clarity_score < 0.4
     Action  : emit BehaviorEvent(event_type="clarity_warning")

  2. RESET_DAY_PROTOCOL
     Trigger : last 3 days in the 7-day window are all incomplete
     Action  : emit BehaviorEvent(event_type="reset_day_protocol")
              + create Task(title="Reset Day Protocol", status=pending)

  3. PERFECT_WEEK
     Trigger : weekly_clarity_score == 1.0  (all 7 days complete)
     Action  : emit BehaviorEvent(event_type="perfect_week")

Idempotency
-----------
Each (event_type, reference_date) pair is unique in `behavior_events`.
Before emitting, the engine checks whether that pair already exists.
If it does, the rule is skipped — no duplicate events, no duplicate tasks.

Zero LLM, no HTTP, stdlib-only. db.commit() called once at the end.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.behavior_event import BehaviorEvent
from app.models.task import Task, TaskStatus
from app.services.north_star_service import WeeklyClarity, DailyClarity


# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

class EventType:
    CLARITY_WARNING    = "clarity_warning"
    RESET_DAY_PROTOCOL = "reset_day_protocol"
    PERFECT_WEEK       = "perfect_week"


# Thresholds
_CLARITY_WARNING_THRESHOLD = Decimal("0.4")
_CONSECUTIVE_INCOMPLETE    = 3


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class EngineResult:
    """Summary of what the engine did for a given evaluation run."""
    reference_date: date
    events_created: list[str]   # event_type strings
    events_skipped: list[str]   # already existed (idempotency)
    task_created: bool          # True if "Reset Day Protocol" task was made


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------

def _event_exists(db: Session, event_type: str, ref_date: date) -> bool:
    return (
        db.query(BehaviorEvent.id)
        .filter(
            BehaviorEvent.event_type == event_type,
            BehaviorEvent.reference_date == ref_date,
        )
        .first()
        is not None
    )


def _emit(
    db: Session,
    event_type: str,
    ref_date: date,
    meta: dict,
) -> bool:
    """
    Try to insert a BehaviorEvent. Returns True if inserted, False if skipped.
    Uses the DB unique constraint as the final idempotency guard.
    """
    if _event_exists(db, event_type, ref_date):
        return False
    db.add(BehaviorEvent(
        event_type=event_type,
        reference_date=ref_date,
        event_metadata=json.dumps(meta, default=str),
    ))
    return True


# ---------------------------------------------------------------------------
# Individual rule evaluators
# ---------------------------------------------------------------------------

def _rule_clarity_warning(
    db: Session,
    weekly: WeeklyClarity,
    result: EngineResult,
) -> None:
    """Rule 1: score < 0.4 → clarity_warning event."""
    if weekly.clarity_score >= _CLARITY_WARNING_THRESHOLD:
        return
    event_type = EventType.CLARITY_WARNING
    inserted = _emit(
        db, event_type, weekly.reference_date,
        meta={
            "score": str(weekly.clarity_score),
            "complete_days": weekly.complete_days,
            "total_days": weekly.total_days,
            "threshold": str(_CLARITY_WARNING_THRESHOLD),
        },
    )
    if inserted:
        result.events_created.append(event_type)
    else:
        result.events_skipped.append(event_type)


def _rule_reset_day_protocol(
    db: Session,
    weekly: WeeklyClarity,
    result: EngineResult,
) -> None:
    """
    Rule 2: last N consecutive days all incomplete → reset_day_protocol event
    + Task "Reset Day Protocol".
    """
    tail: list[DailyClarity] = weekly.days[-_CONSECUTIVE_INCOMPLETE:]
    if len(tail) < _CONSECUTIVE_INCOMPLETE:
        return
    if not all(not d.is_complete for d in tail):
        return

    event_type = EventType.RESET_DAY_PROTOCOL
    if _event_exists(db, event_type, weekly.reference_date):
        result.events_skipped.append(event_type)
        return

    # Create the task first to capture its id in metadata
    task = Task(
        title="Reset Day Protocol",
        status=TaskStatus.pending,
        day=weekly.reference_date,
        description=(
            "Auto-generated by Behavioral Engine: "
            f"{_CONSECUTIVE_INCOMPLETE} consecutive incomplete days detected."
        ),
    )
    db.add(task)
    db.flush()  # get task.id

    db.add(BehaviorEvent(
        event_type=event_type,
        reference_date=weekly.reference_date,
        event_metadata=json.dumps({
            "consecutive_incomplete_days": _CONSECUTIVE_INCOMPLETE,
            "incomplete_days": [str(d.day) for d in tail],
            "task_id": task.id,
        }),
    ))
    result.events_created.append(event_type)
    result.task_created = True


def _rule_perfect_week(
    db: Session,
    weekly: WeeklyClarity,
    result: EngineResult,
) -> None:
    """Rule 3: score == 1.0 → perfect_week event."""
    if weekly.clarity_score < Decimal("1.0"):
        return
    event_type = EventType.PERFECT_WEEK
    inserted = _emit(
        db, event_type, weekly.reference_date,
        meta={
            "score": str(weekly.clarity_score),
            "complete_days": weekly.complete_days,
            "total_days": weekly.total_days,
        },
    )
    if inserted:
        result.events_created.append(event_type)
    else:
        result.events_skipped.append(event_type)


# ---------------------------------------------------------------------------
# Public — main entry point
# ---------------------------------------------------------------------------

def evaluate_and_react(db: Session, weekly: WeeklyClarity) -> EngineResult:
    """
    Evaluate all behavioral rules against the given WeeklyClarity snapshot.
    Idempotent: safe to call multiple times for the same reference_date.
    Commits once at the end if any new events were created.
    """
    result = EngineResult(
        reference_date=weekly.reference_date,
        events_created=[],
        events_skipped=[],
        task_created=False,
    )

    _rule_clarity_warning(db, weekly, result)
    _rule_reset_day_protocol(db, weekly, result)
    _rule_perfect_week(db, weekly, result)

    if result.events_created:
        try:
            db.commit()
        except IntegrityError:
            # Race condition: another process inserted first — safe to ignore
            db.rollback()

    return result


# ---------------------------------------------------------------------------
# Public — query helpers
# ---------------------------------------------------------------------------

def get_behavior_events(
    db: Session,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[BehaviorEvent]]:
    """Return (total, page) of BehaviorEvents ordered by created_at desc."""
    q = db.query(BehaviorEvent)
    if event_type:
        q = q.filter(BehaviorEvent.event_type == event_type)
    total = q.count()
    items = (
        q.order_by(BehaviorEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, items
