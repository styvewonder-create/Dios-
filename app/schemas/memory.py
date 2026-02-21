"""
Memory Engine request / response schemas.

POST /memory/compile-day   → CompileDayRequest  → NarrativeMemoryResponse
POST /memory/compile-week  → CompileWeekRequest → NarrativeMemoryResponse
GET  /memory/snapshots     → list[NarrativeMemoryResponse]
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field


class CompileDayRequest(BaseModel):
    """Compile a narrative memory for a single calendar day."""
    day: Optional[date] = Field(
        default=None,
        description="Day to compile. Defaults to today (UTC).",
        examples=["2026-02-20"],
    )


class CompileWeekRequest(BaseModel):
    """Compile a weekly narrative from 7 consecutive daily snapshots."""
    week_start: date = Field(
        description=(
            "First day of the week to compile (any weekday, typically Monday). "
            "The compiler will aggregate days [week_start, week_start+6]."
        ),
        examples=["2026-02-16"],
    )


class NarrativeMemoryResponse(BaseModel):
    """A structured narrative snapshot (daily or weekly)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: str = Field(description="ISO date this snapshot covers (or week start for weekly).")
    snapshot_type: str = Field(description='"daily" or "weekly".')
    summary: str = Field(description="One-paragraph human-readable narrative of the period.")
    key_events: list[str] = Field(
        default_factory=list,
        description="Notable events extracted from the period (tasks done, big transactions, etc.).",
    )
    emotional_state: Optional[str] = Field(
        default=None,
        description="Heuristic state tags joined by '+': productive, quiet, financially_positive …",
    )
    decisions_made: list[str] = Field(
        default_factory=list,
        description="Entries that signal a decision was taken.",
    )
    lessons: list[str] = Field(
        default_factory=list,
        description="Facts and lessons worth remembering from the period.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Inferred topic tags for fast lookup.",
    )
    created_at: str


class NarrativeMemoryListResponse(BaseModel):
    """Paginated list of narrative snapshots."""
    total: int
    items: list[NarrativeMemoryResponse]
