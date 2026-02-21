"""
Memory Engine router.

POST /memory/compile-day   — Compile narrative snapshot for one day
POST /memory/compile-week  — Compile weekly narrative (aggregates 7 daily)
GET  /memory/snapshots     — List narrative snapshots (paginated)
GET  /memory/snapshots/{id} — Single snapshot by ID
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.narrative_memory import NarrativeMemory
from app.schemas.memory import (
    CompileDayRequest,
    CompileWeekRequest,
    NarrativeMemoryListResponse,
    NarrativeMemoryResponse,
)
from app.services.memory import compile_day_memory, compile_week_memory, get_snapshots
from app.core.errors import DIOSException

router = APIRouter(prefix="/memory", tags=["memory"])


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _snap_to_response(snap: NarrativeMemory) -> NarrativeMemoryResponse:
    def _parse_list(text: Optional[str]) -> list[str]:
        if not text:
            return []
        try:
            result = json.loads(text)
            return result if isinstance(result, list) else []
        except (ValueError, TypeError):
            return []

    def _parse_tags(text: Optional[str]) -> list[str]:
        if not text:
            return []
        return [t.strip() for t in text.split(",") if t.strip()]

    return NarrativeMemoryResponse(
        id=snap.id,
        date=str(snap.date),
        snapshot_type=snap.snapshot_type,
        summary=snap.summary,
        key_events=_parse_list(snap.key_events),
        emotional_state=snap.emotional_state,
        decisions_made=_parse_list(snap.decisions_made),
        lessons=_parse_list(snap.lessons),
        tags=_parse_tags(snap.tags),
        created_at=snap.created_at.isoformat() if snap.created_at else "",
    )


# ---------------------------------------------------------------------------
# POST /memory/compile-day
# ---------------------------------------------------------------------------

class NarrativeNotFoundError(DIOSException):
    http_status = 404
    code = "NARRATIVE_NOT_FOUND"

    def __init__(self, snapshot_id: int):
        super().__init__(
            message=f"Narrative snapshot {snapshot_id} not found.",
            details={"id": snapshot_id},
        )


@router.post(
    "/compile-day",
    response_model=NarrativeMemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Compile narrative memory for a single day",
    responses={
        201: {"description": "Snapshot compiled (or re-compiled) successfully."},
        422: {"description": "Validation error."},
    },
)
def compile_day(payload: CompileDayRequest, db: Session = Depends(get_db)):
    """
    Read all entries, tasks, transactions, facts, and metrics for the given day
    from the event store and compile them into a structured narrative snapshot.

    **Idempotent**: calling again for the same day updates the existing snapshot.
    The event store (`entries`) is always the source of truth.

    Narrative components:
    - **summary** — one-paragraph human-readable overview.
    - **key_events** — notable tasks completed, big transactions, projects created, metrics.
    - **emotional_state** — heuristic label(s): `productive`, `financially_positive`, etc.
    - **decisions_made** — entries matching decision-keyword patterns.
    - **lessons** — FACT / DATO / learned-prefixed entries worth remembering.
    - **tags** — inferred from entry types and financial activity.
    """
    snap = compile_day_memory(db=db, day=payload.day)
    return _snap_to_response(snap)


# ---------------------------------------------------------------------------
# POST /memory/compile-week
# ---------------------------------------------------------------------------

@router.post(
    "/compile-week",
    response_model=NarrativeMemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Compile weekly narrative from 7 daily snapshots",
    responses={
        201: {"description": "Weekly snapshot compiled (or updated) successfully."},
        422: {"description": "Validation error."},
    },
)
def compile_week(payload: CompileWeekRequest, db: Session = Depends(get_db)):
    """
    Aggregate 7 consecutive daily snapshots starting from `week_start`.
    If a daily snapshot for any of those days is missing it is auto-compiled
    from the event store before the weekly aggregation runs.

    **Idempotent**: re-running for the same `week_start` replaces the existing
    weekly snapshot.

    The weekly snapshot stores:
    - Merged key events (deduplicated, capped at 15).
    - Merged decisions and lessons (deduplicated, capped at 10 each).
    - Dominant emotional-state labels across the 7 days.
    - Union of all tags seen during the week.
    """
    snap = compile_week_memory(db=db, week_start=payload.week_start)
    return _snap_to_response(snap)


# ---------------------------------------------------------------------------
# GET /memory/snapshots
# ---------------------------------------------------------------------------

@router.get(
    "/snapshots",
    response_model=NarrativeMemoryListResponse,
    summary="List narrative snapshots (paginated, newest first)",
)
def list_snapshots(
    snapshot_type: Optional[str] = Query(
        default=None,
        description='Filter by type: "daily" or "weekly". Omit for all.',
        examples=["daily"],
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Skip N items."),
    db: Session = Depends(get_db),
):
    """Return a paginated list of narrative memory snapshots ordered by date (newest first)."""
    total, items = get_snapshots(db=db, snapshot_type=snapshot_type, limit=limit, offset=offset)
    return NarrativeMemoryListResponse(
        total=total,
        items=[_snap_to_response(s) for s in items],
    )


# ---------------------------------------------------------------------------
# GET /memory/snapshots/{snapshot_id}
# ---------------------------------------------------------------------------

@router.get(
    "/snapshots/{snapshot_id}",
    response_model=NarrativeMemoryResponse,
    summary="Retrieve a single narrative snapshot by ID",
    responses={
        200: {"description": "Snapshot found."},
        404: {"description": "Snapshot not found."},
    },
)
def get_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    """Retrieve a specific narrative memory snapshot by its database ID."""
    snap = db.query(NarrativeMemory).filter(NarrativeMemory.id == snapshot_id).first()
    if snap is None:
        raise NarrativeNotFoundError(snapshot_id=snapshot_id)
    return _snap_to_response(snap)
