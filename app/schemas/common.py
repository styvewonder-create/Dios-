"""
Shared schema primitives used across the API.
"""
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """A single field-level validation error."""
    field: str
    message: str
    type: str


class ErrorResponse(BaseModel):
    """Standard error envelope returned for all 4xx/5xx responses."""
    model_config = ConfigDict(from_attributes=True)

    code: str
    message: str
    details: Optional[dict[str, Any]] = None
