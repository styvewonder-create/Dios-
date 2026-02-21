"""
Behavioral Engine response schemas.

GET /behavior/events → BehaviorEventListResponse
"""
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class BehaviorEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str = Field(
        description='"clarity_warning" | "reset_day_protocol" | "perfect_week"'
    )
    reference_date: str = Field(description="ISO date that triggered this event.")
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Context specific to each event_type.",
    )
    created_at: str


class BehaviorEventListResponse(BaseModel):
    total: int
    items: list[BehaviorEventResponse]
