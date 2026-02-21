"""
Memory compiler service.

Rules (CLAUDE.md):
- Zero LLM: all logic is deterministic regex + arithmetic.
- No HTTP / external SDK calls.
- Reads from: entries, tasks, transactions, facts, metrics_daily, narrative_memory.
- Writes to: narrative_memory only (upsert by date+snapshot_type).
- db.commit() only at the root function.

Public API
----------
compile_day_memory(db, day)                     -> NarrativeMemory  (upsert)
compile_week_memory(db, week_start)             -> NarrativeMemory  (upsert)
get_snapshots(db, snapshot_type, limit, offset) -> tuple[int, list[NarrativeMemory]]
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entry import Entry
from app.models.task import Task
from app.models.transaction import Transaction
from app.models.fact import Fact
from app.models.metric import MetricDaily
from app.models.narrative_memory import NarrativeMemory


# ---------------------------------------------------------------------------
# Tiny utilities
# ---------------------------------------------------------------------------

def _today() -> date:
    return datetime.now(tz=timezone.utc).date()


def _ev(v) -> str:
    """Return bare string value from a str-enum or plain str."""
    return v.value if hasattr(v, "value") else str(v)


def _jdump(items: list[str]) -> str:
    return json.dumps(items, ensure_ascii=False)


def _jload(text: Optional[str]) -> list[str]:
    if not text:
        return []
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except (ValueError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Pattern constants
# ---------------------------------------------------------------------------

_DECISION_RE = re.compile(
    r"(decid[íi]|decided|chose|elegí|eleg[íi]|opt[oó]|opted|resolv)",
    re.IGNORECASE,
)
_LESSON_RE = re.compile(
    r"^(FACT|DATO|aprendí|learned|lesson|aprendizaje|nota|note)\s*:",
    re.IGNORECASE,
)
_PROJECT_PREFIX_RE = re.compile(
    r"^(PROJECT|PROYECTO)\s*[:\-]?\s*", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

def _infer_emotional_state(
    tasks_done: int,
    tasks_total: int,
    net_cashflow: Decimal,
    total_entries: int,
    facts_count: int,
) -> str:
    """
    Deterministic emotional-state labels derived from day metrics.
    Returns one or more labels joined by '+', never empty (fallback: 'neutral').
    """
    labels: list[str] = []

    if total_entries == 0:
        return "quiet"

    # Productivity
    if tasks_total > 0:
        ratio = tasks_done / tasks_total
        if ratio >= 0.7:
            labels.append("productive")
        elif ratio >= 0.3:
            labels.append("progressing")
        else:
            labels.append("backlogged")

    # Cashflow
    if net_cashflow > Decimal("0"):
        labels.append("financially_positive")
    elif net_cashflow < Decimal("0"):
        labels.append("financially_cautious")

    # Knowledge capture
    if facts_count >= 3:
        labels.append("knowledge_rich")

    # Volume
    if total_entries >= 15:
        labels.append("data_rich")

    return "+".join(labels) if labels else "neutral"


def _extract_key_events(
    tasks: list[Task],
    transactions: list[Transaction],
    project_entries: list[Entry],
    metrics: list[MetricDaily],
) -> list[str]:
    """
    Extract the most notable events from a day, capped at 10 items.
    project_entries: entries with routed_to == 'projects'.
    """
    events: list[str] = []

    # Completed tasks (up to 3)
    for t in [t for t in tasks if _ev(t.status) == "done"][:3]:
        events.append(f"Task completed: {t.title}")

    # New projects (up to 2, extract name from raw entry)
    for e in project_entries[:2]:
        proj_name = _PROJECT_PREFIX_RE.sub("", e.raw).strip()
        events.append(f"Project created: {proj_name or e.raw}")

    # Largest transactions by abs(amount), up to 3
    for tx in sorted(transactions, key=lambda t: abs(t.amount), reverse=True)[:3]:
        kind = _ev(tx.tx_type)
        desc = tx.description or "—"
        events.append(f"Transaction ({kind}): {tx.currency} {tx.amount} — {desc}")

    # Metrics (up to 2)
    for m in metrics[:2]:
        unit = f" {m.unit}" if m.unit else ""
        events.append(f"Metric: {m.name} = {m.value}{unit}")

    return events[:10]


def _extract_decisions(entries: list[Entry], tasks: list[Task]) -> list[str]:
    """
    Identify entries and tasks that signal a decision via keyword matching.
    """
    decisions: list[str] = []
    for e in entries:
        if _DECISION_RE.search(e.raw):
            decisions.append(e.raw[:200])
    for t in tasks:
        if _DECISION_RE.search(t.title):
            decisions.append(f"Task: {t.title[:200]}")
    return list(dict.fromkeys(decisions))[:10]


def _extract_lessons(facts: list[Fact], entries: list[Entry]) -> list[str]:
    """
    Extract fact entries that look like lessons or knowledge captures.
    Checks both the Fact.content and the raw Entry text.
    """
    seen: set[str] = set()
    lessons: list[str] = []

    for f in facts:
        if _LESSON_RE.match(f.content):
            key = f.content[:300]
            if key not in seen:
                seen.add(key)
                lessons.append(key)

    for e in entries:
        if _ev(e.entry_type) == "fact" and _LESSON_RE.match(e.raw):
            key = e.raw[:300]
            if key not in seen:
                seen.add(key)
                lessons.append(key)

    return lessons[:10]


def _infer_tags(
    entry_types: set[str],
    has_income: bool,
    has_expense: bool,
    has_projects: bool,
    has_metrics: bool,
) -> list[str]:
    """Build sorted inferred tags from entry types and financial activity."""
    tags = set(entry_types)
    if has_income:
        tags.add("income")
    if has_expense:
        tags.add("expense")
    if has_projects:
        tags.add("projects")
    if has_metrics:
        tags.add("metrics")
    return sorted(tags)


# ---------------------------------------------------------------------------
# Core day narrative builder (pure function — no DB writes)
# ---------------------------------------------------------------------------

def _build_day_fields(
    day: date,
    entries: list[Entry],
    tasks: list[Task],
    transactions: list[Transaction],
    facts: list[Fact],
    metrics: list[MetricDaily],
) -> dict:
    """
    Compile the narrative dict from loaded domain objects.
    Returns a dict with keys matching NarrativeMemory text columns.
    """
    total_entries = len(entries)

    tasks_done = sum(1 for t in tasks if _ev(t.status) == "done")
    tasks_total = len(tasks)

    income = sum(
        (t.amount for t in transactions if _ev(t.tx_type) == "income"),
        Decimal("0"),
    )
    expense = sum(
        (t.amount for t in transactions if _ev(t.tx_type) == "expense"),
        Decimal("0"),
    )
    net = income - expense

    project_entries = [e for e in entries if e.routed_to == "projects"]

    # Summary
    parts: list[str] = [f"Day {day}:"]
    if total_entries == 0:
        parts.append("No entries recorded.")
    else:
        parts.append(f"{total_entries} entries captured.")
    if tasks_total:
        parts.append(f"Tasks: {tasks_done}/{tasks_total} completed.")
    if transactions:
        sign = "+" if net >= 0 else ""
        parts.append(f"Net cashflow: {sign}{net:.2f} USD.")
    if metrics:
        parts.append(f"{len(metrics)} metric(s) tracked.")
    if project_entries:
        names = ", ".join(
            _PROJECT_PREFIX_RE.sub("", e.raw).strip() or e.raw
            for e in project_entries[:3]
        )
        parts.append(f"Projects: {names}.")
    summary = " ".join(parts)

    key_events = _extract_key_events(tasks, transactions, project_entries, metrics)
    decisions = _extract_decisions(entries, tasks)
    lessons = _extract_lessons(facts, entries)

    entry_types = {_ev(e.entry_type) for e in entries}
    tags = _infer_tags(
        entry_types=entry_types,
        has_income=income > Decimal("0"),
        has_expense=expense > Decimal("0"),
        has_projects=bool(project_entries),
        has_metrics=bool(metrics),
    )

    emotional_state = _infer_emotional_state(
        tasks_done=tasks_done,
        tasks_total=tasks_total,
        net_cashflow=net,
        total_entries=total_entries,
        facts_count=len(facts),
    )

    return {
        "summary": summary,
        "key_events": _jdump(key_events),
        "emotional_state": emotional_state,
        "decisions_made": _jdump(decisions),
        "lessons": _jdump(lessons),
        "tags": ",".join(tags),
    }


def _upsert_snapshot(
    db: Session,
    target_date: date,
    snapshot_type: str,
    fields: dict,
) -> NarrativeMemory:
    """Insert or update a NarrativeMemory row for (date, snapshot_type)."""
    existing = (
        db.query(NarrativeMemory)
        .filter(
            NarrativeMemory.date == target_date,
            NarrativeMemory.snapshot_type == snapshot_type,
        )
        .first()
    )
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        db.flush()
        db.commit()
        db.refresh(existing)
        return existing

    snapshot = NarrativeMemory(
        date=target_date,
        snapshot_type=snapshot_type,
        **fields,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Public — compile single day
# ---------------------------------------------------------------------------

def compile_day_memory(
    db: Session,
    day: Optional[date] = None,
) -> NarrativeMemory:
    """
    Compile a deterministic narrative snapshot for a single calendar day.
    Upserts: re-compiling the same day updates the existing snapshot.

    Event store (entries) is the source of truth — all data is read from it.
    """
    target = day or _today()

    entries = db.query(Entry).filter(Entry.day == target).all()
    tasks = db.query(Task).filter(Task.day == target).all()
    transactions = db.query(Transaction).filter(Transaction.day == target).all()
    facts = db.query(Fact).filter(Fact.day == target).all()
    metrics = db.query(MetricDaily).filter(MetricDaily.day == target).all()

    fields = _build_day_fields(
        day=target,
        entries=entries,
        tasks=tasks,
        transactions=transactions,
        facts=facts,
        metrics=metrics,
    )
    return _upsert_snapshot(db, target, "daily", fields)


# ---------------------------------------------------------------------------
# Public — compile week
# ---------------------------------------------------------------------------

def compile_week_memory(
    db: Session,
    week_start: date,
) -> NarrativeMemory:
    """
    Compile a weekly narrative aggregating 7 consecutive daily snapshots.
    Days in scope: [week_start, week_start + 6].
    If a daily snapshot for a day doesn't exist, it is compiled on-demand.
    """
    days = [week_start + timedelta(days=i) for i in range(7)]

    # Guarantee all daily snapshots exist
    daily_snapshots: list[NarrativeMemory] = []
    for d in days:
        snap = (
            db.query(NarrativeMemory)
            .filter(
                NarrativeMemory.date == d,
                NarrativeMemory.snapshot_type == "daily",
            )
            .first()
        )
        if snap is None:
            snap = compile_day_memory(db, d)
        daily_snapshots.append(snap)

    # Aggregate across days
    all_key_events: list[str] = []
    all_decisions: list[str] = []
    all_lessons: list[str] = []
    all_tags: set[str] = set()
    all_state_labels: list[str] = []
    active_days = 0

    for snap in daily_snapshots:
        all_key_events.extend(_jload(snap.key_events))
        all_decisions.extend(_jload(snap.decisions_made))
        all_lessons.extend(_jload(snap.lessons))
        if snap.tags:
            all_tags.update(t.strip() for t in snap.tags.split(",") if t.strip())
        if snap.emotional_state:
            all_state_labels.extend(snap.emotional_state.split("+"))
        if "No entries recorded" not in snap.summary:
            active_days += 1

    # Deduplicate, cap
    key_events = list(dict.fromkeys(all_key_events))[:15]
    decisions = list(dict.fromkeys(all_decisions))[:10]
    lessons = list(dict.fromkeys(all_lessons))[:10]
    tags = sorted(all_tags)

    # Dominant state labels for the week
    if all_state_labels:
        top_labels = [label for label, _ in Counter(all_state_labels).most_common(2)]
        weekly_state = "+".join(top_labels)
    else:
        weekly_state = "neutral"

    week_end = week_start + timedelta(days=6)
    summary_parts = [
        f"Week {week_start} → {week_end}:",
        f"{active_days}/7 active days.",
    ]
    if key_events:
        summary_parts.append(f"{len(key_events)} notable event(s) across the week.")
    if decisions:
        summary_parts.append(f"{len(decisions)} decision(s) recorded.")
    if lessons:
        summary_parts.append(f"{len(lessons)} lesson(s) captured.")
    summary_parts.append(f"Dominant state: {weekly_state}.")

    fields = {
        "summary": " ".join(summary_parts),
        "key_events": _jdump(key_events),
        "emotional_state": weekly_state,
        "decisions_made": _jdump(decisions),
        "lessons": _jdump(lessons),
        "tags": ",".join(tags),
    }
    return _upsert_snapshot(db, week_start, "weekly", fields)


# ---------------------------------------------------------------------------
# Public — list snapshots
# ---------------------------------------------------------------------------

def get_snapshots(
    db: Session,
    snapshot_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[NarrativeMemory]]:
    """Return (total_count, page) ordered by date descending."""
    q = db.query(NarrativeMemory)
    if snapshot_type:
        q = q.filter(NarrativeMemory.snapshot_type == snapshot_type)
    total = q.count()
    items = q.order_by(NarrativeMemory.date.desc()).offset(offset).limit(limit).all()
    return total, items
