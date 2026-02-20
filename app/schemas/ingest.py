from datetime import date
from typing import Optional
from pydantic import BaseModel, field_validator


class IngestRequest(BaseModel):
    raw: str
    source: Optional[str] = None
    day: Optional[date] = None

    @field_validator("raw")
    @classmethod
    def raw_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("raw text must not be empty")
        return v.strip()


class IngestResponse(BaseModel):
    id: int
    raw: str
    entry_type: str
    routed_to: Optional[str]
    rule_matched: Optional[str]
    day: str
    created_at: Optional[str]

    class Config:
        from_attributes = True
