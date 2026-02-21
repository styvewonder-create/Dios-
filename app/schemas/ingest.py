"""
Ingest request / response schemas.

Single entry:  POST /ingest          → IngestRequest  → IngestResponse
Batch:         POST /ingest/batch    → BatchIngestRequest → BatchIngestResponse
"""
from __future__ import annotations

import enum
from datetime import date
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.domain import RoutedEntityOut

# ---------------------------------------------------------------------------
# Source channel enum
# ---------------------------------------------------------------------------

BATCH_MAX_ITEMS = 100


class SourceChannel(str, enum.Enum):
    voice = "voice"
    text = "text"
    cli = "cli"
    api = "api"
    slack = "slack"
    webhook = "webhook"


# ---------------------------------------------------------------------------
# Single-entry schemas
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    """A single raw-text entry to ingest."""
    model_config = ConfigDict(use_enum_values=True)

    raw: Annotated[str, Field(
        min_length=1,
        max_length=10_000,
        description="Raw free-text entry. Stripped of leading/trailing whitespace.",
        examples=["TODO: revisar el PR de Ana", "gasté $45 en almuerzo"],
    )]
    source: Optional[SourceChannel] = Field(
        default=None,
        description="Channel from which the entry originated.",
        examples=["voice", "text", "cli"],
    )
    day: Optional[date] = Field(
        default=None,
        description="ISO date to assign to the entry. Defaults to today (UTC).",
        examples=["2026-02-20"],
    )

    @field_validator("raw", mode="before")
    @classmethod
    def strip_and_check_empty(cls, v: str) -> str:
        stripped = v.strip() if isinstance(v, str) else v
        if not stripped:
            raise ValueError("raw text must not be empty after stripping whitespace")
        return stripped


class IngestResponse(BaseModel):
    """Result of ingesting a single entry."""
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="ID in the entries table.")
    raw: str = Field(description="Stripped raw text as stored.")
    entry_type: str = Field(description="Semantic type assigned by the router.")
    source: Optional[str] = Field(default=None, description="Source channel.")
    routed_to: Optional[str] = Field(default=None, description="Target domain table.")
    rule_matched: Optional[str] = Field(default=None, description="Rule name that matched.")
    day: str = Field(description="ISO date of the entry.")
    created_at: str = Field(description="UTC timestamp of creation.")
    routed_entity: Optional[RoutedEntityOut] = Field(
        default=None,
        description="The domain record created by fan-out (task, transaction, fact, etc.).",
    )


# ---------------------------------------------------------------------------
# Batch schemas
# ---------------------------------------------------------------------------

class BatchIngestRequest(BaseModel):
    """A batch of raw-text entries to ingest in a single request.

    - Items are processed in order.
    - Each item is independent: a failure on one does not cancel the others.
    - Items inherit `source` / `day` from the batch-level defaults unless
      overridden at the item level.
    """
    model_config = ConfigDict(use_enum_values=True)

    items: Annotated[list[IngestRequest], Field(
        min_length=1,
        max_length=BATCH_MAX_ITEMS,
        description=f"List of entries to ingest (1–{BATCH_MAX_ITEMS} items).",
    )]
    # Batch-level defaults (applied when an item omits the field)
    source: Optional[SourceChannel] = Field(
        default=None,
        description="Default source channel for all items that omit `source`.",
    )
    day: Optional[date] = Field(
        default=None,
        description="Default date for all items that omit `day`.",
    )

    @field_validator("items")
    @classmethod
    def check_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("items must contain at least one entry")
        return v


class BatchItemResult(BaseModel):
    """Outcome for a single item in a batch request."""
    index: int = Field(description="Zero-based position in the request items list.")
    ok: bool = Field(description="True if the item was ingested successfully.")
    entry: Optional[IngestResponse] = Field(
        default=None,
        description="Populated when ok=True.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message when ok=False.",
    )


class BatchIngestResponse(BaseModel):
    """Summary of a batch ingest operation."""
    total: int = Field(description="Total items received.")
    succeeded: int = Field(description="Items ingested successfully.")
    failed: int = Field(description="Items that failed.")
    items: list[BatchItemResult] = Field(description="Per-item results in input order.")
