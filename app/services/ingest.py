"""
Ingest service: routes and persists entries, fans out to domain tables.

Public API
----------
ingest_raw(raw, db, source, day)   → IngestResult   (single, transactional)
ingest_batch(items, db)            → list[dict]      (per-item savepoints)

Internal
--------
_ingest_one(raw, db, source, day)  → IngestResult   (flush only, no commit)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entry import Entry, EntryType
from app.models.fact import Fact
from app.models.metric import MetricDaily
from app.models.transaction import Transaction, TransactionType
from app.models.task import Task, TaskStatus
from app.models.project import Project, ProjectStatus
from app.services.router import route_entry, RoutingResult


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class IngestResult:
    """Holds the persisted Entry and the domain entity created by fan-out."""
    entry: Entry
    domain_entity: Any = field(default=None)  # Task | Transaction | Fact | MetricDaily | Project | None


@dataclass
class BatchItem:
    """Lightweight DTO so the service layer stays schema-agnostic."""
    raw: str
    source: Optional[str] = None
    day: Optional[date] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today() -> date:
    return datetime.now(tz=timezone.utc).date()


def _extract_amount(text: str) -> Optional[Decimal]:
    """Extract the first numeric amount from free text."""
    match = re.search(r"[\$€]?\s*(\d[\d,\.]*)", text)
    if match:
        try:
            return Decimal(match.group(1).replace(",", ""))
        except InvalidOperation:
            pass
    return None


def _detect_tx_type(text: str) -> str:
    lower = text.lower()
    if re.search(r"(ingreso|income|cobr|recibi|recib[íi])", lower):
        return TransactionType.income
    if re.search(r"(transfer|envié|envi[eé])", lower):
        return TransactionType.transfer
    return TransactionType.expense


# ---------------------------------------------------------------------------
# Core — flush only (used by both single and batch paths)
# ---------------------------------------------------------------------------

def _ingest_one(
    raw: str,
    db: Session,
    source: Optional[str],
    day: Optional[date],
) -> IngestResult:
    """
    Route → persist entry → fan-out.
    Calls db.flush() to obtain entry.id but does NOT commit.
    The caller is responsible for commit / rollback.
    """
    target_day = day or _today()
    result: RoutingResult = route_entry(raw, db)

    entry = Entry(
        raw=raw,
        entry_type=result.entry_type,
        source=source,
        day=target_day,
        routed_to=result.target,
        rule_matched=result.rule_name,
    )
    db.add(entry)
    db.flush()  # get entry.id before fan-out

    domain_entity = _fan_out(entry, result, target_day, db)
    db.flush()

    return IngestResult(entry=entry, domain_entity=domain_entity)


def _fan_out(
    entry: Entry,
    result: RoutingResult,
    day: date,
    db: Session,
) -> Any:
    """Create the domain record corresponding to the routed target."""
    target = result.target

    if target == "tasks":
        title = re.sub(
            r"^(TODO|TASK|tarea|hacer)\s*[:\-]?\s*", "", entry.raw, flags=re.IGNORECASE
        ).strip()
        obj = Task(
            entry_id=entry.id,
            title=title or entry.raw,
            status=TaskStatus.pending,
            day=day,
        )
        db.add(obj)
        return obj

    if target == "transactions":
        amount = _extract_amount(entry.raw) or Decimal("0.00")
        obj = Transaction(
            entry_id=entry.id,
            amount=amount,
            currency="USD",
            tx_type=_detect_tx_type(entry.raw),
            description=entry.raw,
            day=day,
        )
        db.add(obj)
        return obj

    if target == "facts":
        obj = Fact(
            entry_id=entry.id,
            content=entry.raw,
            category=result.entry_type,
            day=day,
        )
        db.add(obj)
        return obj

    if target == "metrics_daily":
        name, value, unit = "unknown", Decimal("0"), None
        m = re.search(
            r"(?:METRIC|METRICA|KPI)\s*:\s*(\w[\w\s]*?)\s*=\s*([\d\.]+)\s*(\w+)?",
            entry.raw,
            re.IGNORECASE,
        )
        if m:
            name = m.group(1).strip()
            try:
                value = Decimal(m.group(2))
            except InvalidOperation:
                pass
            unit = m.group(3)
        obj = MetricDaily(entry_id=entry.id, name=name, value=value, unit=unit, day=day)
        db.add(obj)
        return obj

    if target == "projects":
        proj_name = re.sub(
            r"^(PROJECT|PROYECTO)\s*[:\-]?\s*", "", entry.raw, flags=re.IGNORECASE
        ).strip()
        obj = Project(name=proj_name or entry.raw, status=ProjectStatus.active)
        db.add(obj)
        return obj

    return None


# ---------------------------------------------------------------------------
# Public — single entry
# ---------------------------------------------------------------------------

def ingest_raw(
    raw: str,
    db: Session,
    source: Optional[str] = None,
    day: Optional[date] = None,
) -> IngestResult:
    """Route, persist, and commit a single entry. Returns IngestResult."""
    ir = _ingest_one(raw, db, source, day)
    db.commit()
    db.refresh(ir.entry)
    if ir.domain_entity is not None:
        try:
            db.refresh(ir.domain_entity)
        except Exception:
            pass
    return ir


# ---------------------------------------------------------------------------
# Public — batch
# ---------------------------------------------------------------------------

def ingest_batch(items: list[BatchItem], db: Session) -> list[dict]:
    """
    Ingest a list of items using one savepoint per item.
    A failure on one item does not cancel the others.
    Returns a list of raw dicts for the router to convert to BatchItemResult.
    """
    raw_results = []

    for i, item in enumerate(items):
        savepoint = db.begin_nested()
        try:
            ir = _ingest_one(item.raw, db, item.source, item.day)
            savepoint.commit()
            raw_results.append({"index": i, "ok": True, "result": ir, "error": None})
        except Exception as exc:
            savepoint.rollback()
            raw_results.append({"index": i, "ok": False, "result": None, "error": str(exc)})

    db.commit()

    # Refresh successfully persisted entities after the outer commit
    for r in raw_results:
        if r["ok"] and r["result"] is not None:
            try:
                db.refresh(r["result"].entry)
                if r["result"].domain_entity is not None:
                    db.refresh(r["result"].domain_entity)
            except Exception:
                pass

    return raw_results
