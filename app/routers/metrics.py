"""
Metrics router — North Star and future system-wide KPIs.

GET /metrics/north-star            — weekly Clarity Score (7-day window)
GET /metrics/north-star/day        — single-day Complete Day evaluation
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.schemas.north_star import DailyClarityResponse, NorthStarResponse
from app.services.north_star_service import (
    get_north_star,
    calculate_daily_clarity,
    WeeklyClarity,
    DailyClarity,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _daily_to_response(d: DailyClarity) -> DailyClarityResponse:
    return DailyClarityResponse(
        day=str(d.day),
        is_complete=d.is_complete,
        event_count=d.event_count,
        has_outcome=d.has_outcome,
        has_memory_snapshot=d.has_memory_snapshot,
    )


def _weekly_to_response(w: WeeklyClarity) -> NorthStarResponse:
    return NorthStarResponse(
        reference_date=str(w.reference_date),
        weekly_clarity_score=float(w.clarity_score),
        complete_days=w.complete_days,
        total_days=w.total_days,
        days=[_daily_to_response(d) for d in w.days],
    )


# ---------------------------------------------------------------------------
# GET /metrics/north-star
# ---------------------------------------------------------------------------

@router.get(
    "/north-star",
    response_model=NorthStarResponse,
    summary="Clarity Score — weekly North Star metric",
    responses={
        200: {"description": "Clarity Score for the 7-day window ending on reference_date."},
    },
)
def north_star(
    reference_date: Optional[date] = Query(
        default=None,
        description=(
            "Last day (inclusive) of the 7-day evaluation window. "
            "Defaults to today (UTC)."
        ),
        examples=["2026-02-21"],
    ),
    db: Session = Depends(get_db),
):
    """
    Calculate the **Clarity Score**: the fraction of days in the last 7 days
    that qualify as a *Complete Day*.

    ### Complete Day criteria (all three required)
    1. **≥ 3 logged events** in the event store for that day.
    2. **≥ 1 task completed** OR **≥ 1 transaction recorded**.
    3. A **daily narrative memory snapshot** has been compiled for that day.

    The result is persisted in `north_star_snapshots` (upsert) so historical
    scores can be queried without recalculating.

    Returns the score plus a per-day breakdown so clients can surface
    exactly which criterion failed for incomplete days.
    """
    result = get_north_star(db=db, reference_date=reference_date)
    return _weekly_to_response(result)


# ---------------------------------------------------------------------------
# GET /metrics/north-star/day
# ---------------------------------------------------------------------------

@router.get(
    "/north-star/day",
    response_model=DailyClarityResponse,
    summary="Single-day Complete Day evaluation",
    responses={
        200: {"description": "Whether the given day meets all Complete Day criteria."},
    },
)
def north_star_day(
    day: Optional[date] = Query(
        default=None,
        description="Day to evaluate. Defaults to today (UTC).",
        examples=["2026-02-21"],
    ),
    db: Session = Depends(get_db),
):
    """
    Evaluate whether a single day qualifies as a *Complete Day*.

    Returns the three-criterion breakdown so it's clear which
    condition is unmet, making it actionable for the user.
    """
    result = calculate_daily_clarity(db=db, day=day)
    return _daily_to_response(result)
