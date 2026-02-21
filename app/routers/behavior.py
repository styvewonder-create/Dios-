"""
Behavioral Engine router.

GET /behavior/events   — list all behavior events (paginated, newest first)
"""
from __future__ import annotations

import json
from typing import Optional, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.behavior_event import BehaviorEvent
from app.schemas.behavior import BehaviorEventListResponse, BehaviorEventResponse
from app.services.behavior_engine import get_behavior_events, EventType

router = APIRouter(prefix="/behavior", tags=["behavior"])


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _parse_metadata(raw: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _event_to_response(ev: BehaviorEvent) -> BehaviorEventResponse:
    return BehaviorEventResponse(
        id=ev.id,
        event_type=ev.event_type,
        reference_date=str(ev.reference_date),
        metadata=_parse_metadata(ev.event_metadata),
        created_at=ev.created_at.isoformat() if ev.created_at else "",
    )


# ---------------------------------------------------------------------------
# GET /behavior/events
# ---------------------------------------------------------------------------

@router.get(
    "/events",
    response_model=BehaviorEventListResponse,
    summary="List behavioral engine events (newest first)",
    responses={
        200: {"description": "Paginated list of system reaction events."},
    },
)
def list_behavior_events(
    event_type: Optional[str] = Query(
        default=None,
        description=(
            f'Filter by type: '
            f'"{EventType.CLARITY_WARNING}", '
            f'"{EventType.RESET_DAY_PROTOCOL}", '
            f'"{EventType.PERFECT_WEEK}". '
            "Omit for all."
        ),
        examples=["clarity_warning"],
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Skip N items."),
    db: Session = Depends(get_db),
):
    """
    Return behavioral engine events produced by `GET /metrics/north-star`.

    ### Event types
    | Type | Trigger |
    |---|---|
    | `clarity_warning`    | weekly score < 0.4 |
    | `reset_day_protocol` | 3 consecutive incomplete days (also creates a Task) |
    | `perfect_week`       | all 7 days complete (score == 1.0) |

    Events are idempotent: at most one per (event_type, reference_date).
    """
    total, items = get_behavior_events(
        db=db, event_type=event_type, limit=limit, offset=offset
    )
    return BehaviorEventListResponse(
        total=total,
        items=[_event_to_response(ev) for ev in items],
    )
