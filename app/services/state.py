"""
State service: query today's data and close-day logic.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.entry import Entry
from app.models.task import Task, TaskStatus
from app.models.transaction import Transaction
from app.models.fact import Fact
from app.models.metric import MetricDaily
from app.models.project import Project, ProjectStatus
from app.models.daily_log import DailyLog
from app.models.memory import MemorySnapshot


def _today() -> date:
    return datetime.now(tz=timezone.utc).date()


def get_state_today(db: Session, day: Optional[date] = None):
    target = day or _today()
    entries = db.query(Entry).filter(Entry.day == target).all()
    tasks = db.query(Task).filter(Task.day == target).all()
    transactions = db.query(Transaction).filter(Transaction.day == target).all()
    facts = db.query(Fact).filter(Fact.day == target).all()
    metrics = db.query(MetricDaily).filter(MetricDaily.day == target).all()
    daily_log = db.query(DailyLog).filter(DailyLog.day == target).first()
    return {
        "day": str(target),
        "is_closed": daily_log.is_closed if daily_log else False,
        "totals": {
            "entries": len(entries),
            "tasks": len(tasks),
            "transactions": len(transactions),
            "facts": len(facts),
            "metrics": len(metrics),
        },
        "entries": [_entry_dict(e) for e in entries],
        "tasks": [_task_dict(t) for t in tasks],
        "transactions": [_tx_dict(t) for t in transactions],
        "facts": [_fact_dict(f) for f in facts],
        "metrics": [_metric_dict(m) for m in metrics],
    }


def get_state_active(db: Session):
    """Return all active (non-closed) days with open tasks and projects."""
    open_tasks = (
        db.query(Task)
        .filter(Task.status.in_([TaskStatus.pending, TaskStatus.in_progress]))
        .all()
    )
    active_projects = (
        db.query(Project)
        .filter(Project.status == ProjectStatus.active)
        .all()
    )
    # Days that have entries but no closed daily_log
    closed_days = {
        row.day
        for row in db.query(DailyLog.day).filter(DailyLog.is_closed == True).all()  # noqa
    }
    open_days_query = (
        db.query(Entry.day, func.count(Entry.id).label("count"))
        .filter(Entry.day.notin_(closed_days))
        .group_by(Entry.day)
        .order_by(Entry.day.desc())
        .limit(30)
        .all()
    )
    return {
        "open_tasks": [_task_dict(t) for t in open_tasks],
        "active_projects": [_project_dict(p) for p in active_projects],
        "open_days": [{"day": str(r.day), "entries": r.count} for r in open_days_query],
    }


def close_day(db: Session, day: Optional[date] = None, summary: Optional[str] = None) -> DailyLog:
    target = day or _today()

    total_entries = db.query(func.count(Entry.id)).filter(Entry.day == target).scalar() or 0
    total_tasks = db.query(func.count(Task.id)).filter(Task.day == target).scalar() or 0
    total_transactions = db.query(func.count(Transaction.id)).filter(Transaction.day == target).scalar() or 0
    total_facts = db.query(func.count(Fact.id)).filter(Fact.day == target).scalar() or 0

    daily_log = db.query(DailyLog).filter(DailyLog.day == target).first()
    if daily_log is None:
        daily_log = DailyLog(day=target)
        db.add(daily_log)

    daily_log.is_closed = True
    daily_log.total_entries = total_entries
    daily_log.total_tasks = total_tasks
    daily_log.total_transactions = total_transactions
    daily_log.total_facts = total_facts
    daily_log.closed_at = datetime.now(tz=timezone.utc)
    if summary:
        daily_log.summary = summary

    # Create memory snapshot
    snapshot_content = (
        f"Day {target} closed. "
        f"entries={total_entries} tasks={total_tasks} "
        f"transactions={total_transactions} facts={total_facts}. "
        f"Summary: {summary or 'n/a'}"
    )
    snapshot = MemorySnapshot(
        day=target,
        snapshot_type="daily_close",
        content=snapshot_content,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(daily_log)
    return daily_log


# --- dict helpers ---

def _entry_dict(e: Entry) -> dict:
    return {
        "id": e.id,
        "raw": e.raw,
        "entry_type": e.entry_type,
        "source": e.source,
        "day": str(e.day),
        "routed_to": e.routed_to,
        "rule_matched": e.rule_matched,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _task_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "day": str(t.day),
        "due_date": str(t.due_date) if t.due_date else None,
        "project_id": t.project_id,
    }


def _tx_dict(t: Transaction) -> dict:
    return {
        "id": t.id,
        "amount": str(t.amount),
        "currency": t.currency,
        "tx_type": t.tx_type,
        "category": t.category,
        "description": t.description,
        "day": str(t.day),
    }


def _fact_dict(f: Fact) -> dict:
    return {
        "id": f.id,
        "content": f.content,
        "category": f.category,
        "day": str(f.day),
    }


def _metric_dict(m: MetricDaily) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "value": str(m.value),
        "unit": m.unit,
        "day": str(m.day),
    }


def _project_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "status": p.status,
        "start_date": str(p.start_date) if p.start_date else None,
    }
