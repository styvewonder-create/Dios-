"""
North Star Metric schemas.

GET /metrics/north-star → NorthStarResponse
GET /metrics/north-star/day → DailyClarityResponse
"""
from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class DailyClarityResponse(BaseModel):
    """Breakdown of a single day's Complete Day evaluation."""
    model_config = ConfigDict(from_attributes=True)

    day: str
    is_complete: bool
    event_count: int = Field(description="Number of entries logged this day.")
    has_outcome: bool = Field(
        description="True if ≥1 task completed OR ≥1 transaction recorded."
    )
    has_memory_snapshot: bool = Field(
        description="True if a daily narrative memory snapshot was compiled."
    )


class NorthStarResponse(BaseModel):
    """Clarity Score for the 7-day window ending on reference_date."""
    model_config = ConfigDict(from_attributes=True)

    reference_date: str = Field(
        description="Last day (inclusive) of the 7-day evaluation window."
    )
    weekly_clarity_score: float = Field(
        description="Fraction of Complete Days in the window. Range: 0.0–1.0.",
        examples=[0.71],
    )
    complete_days: int = Field(description="Number of days that met all criteria.")
    total_days: int = Field(description="Window size (always 7).")
    days: list[DailyClarityResponse] = Field(
        description="Per-day breakdown, oldest first."
    )
