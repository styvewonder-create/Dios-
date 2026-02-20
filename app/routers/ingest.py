from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.schemas.ingest import IngestRequest, IngestResponse
from app.services.ingest import ingest_raw

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
def ingest(payload: IngestRequest, db: Session = Depends(get_db)):
    """
    Accept a raw text entry, route it deterministically, and persist
    it in the appropriate domain table.
    """
    try:
        entry = ingest_raw(
            raw=payload.raw,
            db=db,
            source=payload.source,
            day=payload.day,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return IngestResponse(
        id=entry.id,
        raw=entry.raw,
        entry_type=entry.entry_type,
        routed_to=entry.routed_to,
        rule_matched=entry.rule_matched,
        day=str(entry.day),
        created_at=entry.created_at.isoformat() if entry.created_at else None,
    )
