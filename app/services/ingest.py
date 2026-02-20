"""
Ingest service: persists a raw entry and fans out to the right table
based on the deterministic router result.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entry import Entry, EntryType
from app.models.fact import Fact
from app.models.metric import MetricDaily
from app.models.transaction import Transaction, TransactionType
from app.models.task import Task, TaskStatus
from app.models.project import Project, ProjectStatus
from app.services.router import route_entry, RoutingResult


def _today() -> date:
    return datetime.now(tz=timezone.utc).date()


def _extract_amount(text: str) -> Optional[Decimal]:
    """Try to extract a numeric amount from free text."""
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


def ingest_raw(
    raw: str,
    db: Session,
    source: Optional[str] = None,
    day: Optional[date] = None,
) -> Entry:
    """
    Main ingest function:
    1. Route the entry
    2. Persist to entries table
    3. Fan-out to domain table
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
    db.flush()  # get entry.id

    # --- Fan-out ---
    target = result.target

    if target == "facts":
        fact = Fact(
            entry_id=entry.id,
            content=raw,
            category=result.entry_type,
            day=target_day,
        )
        db.add(fact)

    elif target == "tasks":
        title = re.sub(r"^(TODO|TASK|tarea|hacer)\s*[:\-]?\s*", "", raw, flags=re.IGNORECASE).strip()
        task = Task(
            entry_id=entry.id,
            title=title or raw,
            status=TaskStatus.pending,
            day=target_day,
        )
        db.add(task)

    elif target == "transactions":
        amount = _extract_amount(raw) or Decimal("0.00")
        tx = Transaction(
            entry_id=entry.id,
            amount=amount,
            currency="USD",
            tx_type=_detect_tx_type(raw),
            description=raw,
            day=target_day,
        )
        db.add(tx)

    elif target == "metrics_daily":
        # Format expected: "METRIC: name=value unit"
        name = "unknown"
        value = Decimal("0")
        unit = None
        m = re.search(r"METRIC[A-Z]*\s*:\s*(\w[\w\s]*?)\s*=\s*([\d\.]+)\s*(\w+)?", raw, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            try:
                value = Decimal(m.group(2))
            except InvalidOperation:
                pass
            unit = m.group(3)
        metric = MetricDaily(
            entry_id=entry.id,
            name=name,
            value=value,
            unit=unit,
            day=target_day,
        )
        db.add(metric)

    elif target == "projects":
        proj_name = re.sub(r"^(PROJECT|PROYECTO)\s*[:\-]?\s*", "", raw, flags=re.IGNORECASE).strip()
        project = Project(
            name=proj_name or raw,
            status=ProjectStatus.active,
        )
        db.add(project)

    db.commit()
    db.refresh(entry)
    return entry
