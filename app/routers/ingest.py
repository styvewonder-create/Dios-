"""
Ingest router.

POST /ingest          — single entry
POST /ingest/batch    — batch of up to 100 entries
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.schemas.domain import (
    TaskOut, TransactionOut, FactOut, MetricOut, ProjectOut, RoutedEntityOut,
)
from app.schemas.ingest import (
    BatchIngestRequest,
    BatchIngestResponse,
    BatchItemResult,
    IngestRequest,
    IngestResponse,
    BATCH_MAX_ITEMS,
)
from app.services.ingest import BatchItem, IngestResult, ingest_raw, ingest_batch
from app.core.errors import BatchTooLargeError, EntryIngestionError
from app.models.task import Task
from app.models.transaction import Transaction
from app.models.fact import Fact
from app.models.metric import MetricDaily
from app.models.project import Project

router = APIRouter(prefix="/ingest", tags=["ingest"])


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _ev(v) -> str:
    """Extract bare string value from a str-enum or plain str."""
    return v.value if hasattr(v, "value") else str(v)


def _build_routed_entity(ir: IngestResult) -> RoutedEntityOut | None:
    """Map the ORM domain entity to a typed Pydantic output model."""
    entity = ir.domain_entity
    if entity is None:
        return None

    if isinstance(entity, Task):
        return TaskOut(
            id=entity.id,
            title=entity.title,
            status=_ev(entity.status),
            day=str(entity.day),
            due_date=str(entity.due_date) if entity.due_date else None,
            project_id=entity.project_id,
        )
    if isinstance(entity, Transaction):
        return TransactionOut(
            id=entity.id,
            amount=str(entity.amount),
            currency=entity.currency,
            tx_type=_ev(entity.tx_type),
            category=entity.category,
            description=entity.description,
            day=str(entity.day),
        )
    if isinstance(entity, Fact):
        return FactOut(
            id=entity.id,
            content=entity.content,
            category=entity.category,
            day=str(entity.day),
        )
    if isinstance(entity, MetricDaily):
        return MetricOut(
            id=entity.id,
            name=entity.name,
            value=str(entity.value),
            unit=entity.unit,
            day=str(entity.day),
        )
    if isinstance(entity, Project):
        return ProjectOut(
            id=entity.id,
            name=entity.name,
            status=_ev(entity.status),
            start_date=str(entity.start_date) if entity.start_date else None,
        )
    return None


def _ir_to_response(ir: IngestResult) -> IngestResponse:
    entry = ir.entry
    return IngestResponse(
        id=entry.id,
        raw=entry.raw,
        entry_type=_ev(entry.entry_type),
        source=_ev(entry.source) if entry.source else None,
        routed_to=entry.routed_to,
        rule_matched=entry.rule_matched,
        day=str(entry.day),
        created_at=entry.created_at.isoformat() if entry.created_at else "",
        routed_entity=_build_routed_entity(ir),
    )


# ---------------------------------------------------------------------------
# POST /ingest  — single
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a single entry",
    responses={
        422: {"description": "Validation error (empty raw, invalid source, etc.)"},
        500: {"description": "Internal routing / persistence error"},
    },
)
def ingest(payload: IngestRequest, db: Session = Depends(get_db)):
    """
    Accept a raw text entry, route it deterministically via `rules_router`,
    persist it in `entries`, and fan-out to the matching domain table.

    Returns the created entry enriched with the domain record produced by fan-out.
    """
    try:
        ir = ingest_raw(
            raw=payload.raw,
            db=db,
            source=payload.source,
            day=payload.day,
        )
    except Exception as exc:
        raise EntryIngestionError(message=str(exc), raw=payload.raw) from exc

    return _ir_to_response(ir)


# ---------------------------------------------------------------------------
# POST /ingest/batch
# ---------------------------------------------------------------------------

@router.post(
    "/batch",
    response_model=BatchIngestResponse,
    status_code=status.HTTP_207_MULTI_STATUS,
    summary="Ingest a batch of entries (up to 100)",
    responses={
        207: {"description": "Multi-status: check each item's `ok` field."},
        422: {"description": "Batch-level validation error (empty list, too many items)."},
    },
)
def ingest_batch_endpoint(
    payload: BatchIngestRequest,
    db: Session = Depends(get_db),
):
    """
    Ingest up to **100 entries** in a single request.

    Each item is processed independently using a database savepoint.
    A failure on one item does not roll back others.

    Item-level `source` and `day` override the batch-level defaults.
    Response HTTP status is **207 Multi-Status** — always inspect each `item.ok`.
    """
    if len(payload.items) > BATCH_MAX_ITEMS:
        raise BatchTooLargeError(max_items=BATCH_MAX_ITEMS, received=len(payload.items))

    # Merge batch-level defaults into each item where the item omits them
    service_items = [
        BatchItem(
            raw=req.raw,
            source=req.source if req.source is not None else payload.source,
            day=req.day if req.day is not None else payload.day,
        )
        for req in payload.items
    ]

    raw_results = ingest_batch(service_items, db)

    item_results: list[BatchItemResult] = [
        BatchItemResult(
            index=r["index"],
            ok=r["ok"],
            entry=_ir_to_response(r["result"]) if r["ok"] and r["result"] else None,
            error=r["error"],
        )
        for r in raw_results
    ]

    succeeded = sum(1 for r in item_results if r.ok)
    return BatchIngestResponse(
        total=len(item_results),
        succeeded=succeeded,
        failed=len(item_results) - succeeded,
        items=item_results,
    )
