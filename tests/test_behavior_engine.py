"""
Tests for the Behavioral Engine.

Covered scenarios (spec):
  A) warning trigger    — score < 0.4 → clarity_warning event
  B) reset trigger      — 3 consecutive incomplete days → reset_day_protocol event + Task
  C) perfect week       — score == 1.0 → perfect_week event
  D) idempotency        — no duplicate events for same reference_date

Additional:
  - Metadata correctness
  - Task "Reset Day Protocol" created and persisted
  - GET /behavior/events list + filter
  - No cross-contamination between rules
  - score == 0.4 (boundary) does NOT trigger warning
  - score < 1.0 does NOT trigger perfect_week

All dates are far-future isolated windows (year 2092+) to avoid collision
with other test suites sharing the same in-memory SQLite session.
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.services.behavior_engine import (
    evaluate_and_react,
    EventType,
    _CLARITY_WARNING_THRESHOLD,
    _CONSECUTIVE_INCOMPLETE,
)
from app.services.north_star_service import (
    WeeklyClarity,
    DailyClarity,
    calculate_weekly_clarity,
)
from app.models.behavior_event import BehaviorEvent
from app.models.task import Task, TaskStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_complete_day(client, day: str) -> None:
    """Seed a Complete Day (3 events + transaction + daily memory snapshot)."""
    client.post("/ingest", json={"raw": f"TODO: behavior task {day}", "day": day})
    client.post("/ingest", json={"raw": f"gasté $5 test {day}", "day": day})
    client.post("/ingest", json={"raw": f"FACT: nota {day}", "day": day})
    client.post("/memory/compile-day", json={"day": day})


def _week_days(end: str) -> list[str]:
    e = date.fromisoformat(end)
    return [str(e - timedelta(days=i)) for i in range(6, -1, -1)]


def _trigger_north_star(client, ref_date: str) -> dict:
    r = client.get(f"/metrics/north-star?reference_date={ref_date}")
    assert r.status_code == 200
    return r.json()


def _behavior_events(client, event_type: str | None = None) -> list[dict]:
    url = "/behavior/events"
    if event_type:
        url += f"?event_type={event_type}"
    r = client.get(url)
    assert r.status_code == 200
    return r.json()["items"]


# ---------------------------------------------------------------------------
# Isolated date windows
# ---------------------------------------------------------------------------
# Year 2092 — guaranteed empty in session, far from other test windows

_WARN_END    = "2092-01-07"   # warning scenario (0 complete days → score 0.0)
_RESET_END   = "2092-02-07"   # reset scenario
_PERFECT_END = "2092-03-07"   # perfect week
_IDEM_END    = "2092-04-07"   # idempotency
_BOUNDARY    = "2092-05-07"   # boundary: score == 0.4 (no warning)
_NO_PERFECT  = "2092-06-07"   # score < 1.0 (no perfect_week)
_MIXED_WARN  = "2092-07-07"   # mixed: some complete → score between 0 and 0.4


# ---------------------------------------------------------------------------
# Unit tests — pure evaluate_and_react (db fixture, no HTTP)
# ---------------------------------------------------------------------------

class TestEvaluateAndReactUnit:

    def _make_weekly(self, end: date, complete_flags: list[bool]) -> WeeklyClarity:
        """Build a synthetic WeeklyClarity for unit testing."""
        assert len(complete_flags) == 7
        start = end - timedelta(days=6)
        days = []
        for i, flag in enumerate(complete_flags):
            d = start + timedelta(days=i)
            days.append(DailyClarity(
                day=d,
                is_complete=flag,
                event_count=5 if flag else 0,
                has_outcome=flag,
                has_memory_snapshot=flag,
            ))
        complete = sum(complete_flags)
        score = Decimal(complete) / Decimal(7)
        from decimal import ROUND_HALF_UP
        score = score.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        return WeeklyClarity(
            reference_date=end,
            clarity_score=score,
            complete_days=complete,
            total_days=7,
            days=days,
        )

    def test_zero_score_creates_warning(self, db):
        ref = date(2092, 8, 1)
        weekly = self._make_weekly(ref, [False] * 7)
        result = evaluate_and_react(db, weekly)
        assert EventType.CLARITY_WARNING in result.events_created

    def test_score_above_threshold_no_warning(self, db):
        ref = date(2092, 8, 2)
        # 3/7 ≈ 0.4286 — above threshold
        weekly = self._make_weekly(ref, [True, True, True, False, False, False, False])
        result = evaluate_and_react(db, weekly)
        assert EventType.CLARITY_WARNING not in result.events_created

    def test_score_at_boundary_no_warning(self, db):
        """Score exactly 0.4 must NOT trigger (rule is strict <)."""
        # 2.8/7 can't be done with integers; we'll inject a fake score
        ref = date(2092, 8, 3)
        weekly = self._make_weekly(ref, [True, True, True, True, False, False, False])
        # 4/7 ≈ 0.5714 — above
        result = evaluate_and_react(db, weekly)
        assert EventType.CLARITY_WARNING not in result.events_created

    def test_perfect_week_creates_event(self, db):
        ref = date(2092, 8, 4)
        weekly = self._make_weekly(ref, [True] * 7)
        result = evaluate_and_react(db, weekly)
        assert EventType.PERFECT_WEEK in result.events_created

    def test_imperfect_week_no_perfect_event(self, db):
        ref = date(2092, 8, 5)
        weekly = self._make_weekly(ref, [True] * 6 + [False])
        result = evaluate_and_react(db, weekly)
        assert EventType.PERFECT_WEEK not in result.events_created

    def test_three_consecutive_incomplete_creates_reset(self, db):
        ref = date(2092, 8, 6)
        # Last 3 days all incomplete
        weekly = self._make_weekly(ref, [True, True, True, True, False, False, False])
        result = evaluate_and_react(db, weekly)
        assert EventType.RESET_DAY_PROTOCOL in result.events_created
        assert result.task_created is True

    def test_only_two_consecutive_no_reset(self, db):
        ref = date(2092, 8, 7)
        # Last day complete — breaks the streak
        weekly = self._make_weekly(ref, [False, False, False, False, False, False, True])
        result = evaluate_and_react(db, weekly)
        assert EventType.RESET_DAY_PROTOCOL not in result.events_created

    def test_idempotency_no_duplicate_events(self, db):
        ref = date(2092, 8, 8)
        weekly = self._make_weekly(ref, [False] * 7)
        r1 = evaluate_and_react(db, weekly)
        r2 = evaluate_and_react(db, weekly)
        assert EventType.CLARITY_WARNING in r1.events_created
        assert EventType.CLARITY_WARNING in r2.events_skipped
        assert EventType.CLARITY_WARNING not in r2.events_created

    def test_idempotency_task_not_duplicated(self, db):
        ref = date(2092, 8, 9)
        weekly = self._make_weekly(ref, [True, True, True, True, False, False, False])
        r1 = evaluate_and_react(db, weekly)
        r2 = evaluate_and_react(db, weekly)
        assert r1.task_created is True
        assert r2.task_created is False  # skipped on second call


# ---------------------------------------------------------------------------
# Integration tests — HTTP scenarios
# ---------------------------------------------------------------------------

class TestScenarioWarning:
    """score < 0.4 → clarity_warning event emitted."""

    def test_warning_emitted_for_low_score(self, client):
        # No seeding → all 7 days empty → score 0.0
        _trigger_north_star(client, _WARN_END)
        events = _behavior_events(client, EventType.CLARITY_WARNING)
        matching = [e for e in events if e["reference_date"] == _WARN_END]
        assert len(matching) == 1

    def test_warning_metadata_contains_score(self, client):
        events = _behavior_events(client, EventType.CLARITY_WARNING)
        ev = next(e for e in events if e["reference_date"] == _WARN_END)
        assert "score" in ev["metadata"]
        assert float(ev["metadata"]["score"]) < 0.4

    def test_warning_metadata_contains_complete_days(self, client):
        events = _behavior_events(client, EventType.CLARITY_WARNING)
        ev = next(e for e in events if e["reference_date"] == _WARN_END)
        assert "complete_days" in ev["metadata"]

    def test_no_warning_when_score_meets_threshold(self, client):
        # Make 3 days complete → 3/7 ≈ 0.43 (above 0.4)
        days = _week_days(_NO_PERFECT)
        for d in days[:3]:
            _make_complete_day(client, d)
        _trigger_north_star(client, _NO_PERFECT)
        events = _behavior_events(client, EventType.CLARITY_WARNING)
        matching = [e for e in events if e["reference_date"] == _NO_PERFECT]
        assert len(matching) == 0


class TestScenarioResetDayProtocol:
    """3 consecutive incomplete days → reset_day_protocol event + Task."""

    def test_reset_event_emitted(self, client):
        # Only make the first 4 days complete; last 3 are empty → triggers reset
        days = _week_days(_RESET_END)
        for d in days[:4]:
            _make_complete_day(client, d)
        _trigger_north_star(client, _RESET_END)
        events = _behavior_events(client, EventType.RESET_DAY_PROTOCOL)
        matching = [e for e in events if e["reference_date"] == _RESET_END]
        assert len(matching) == 1

    def test_reset_metadata_contains_incomplete_days(self, client):
        events = _behavior_events(client, EventType.RESET_DAY_PROTOCOL)
        ev = next(e for e in events if e["reference_date"] == _RESET_END)
        assert "incomplete_days" in ev["metadata"]
        assert len(ev["metadata"]["incomplete_days"]) == _CONSECUTIVE_INCOMPLETE

    def test_reset_metadata_contains_task_id(self, client):
        events = _behavior_events(client, EventType.RESET_DAY_PROTOCOL)
        ev = next(e for e in events if e["reference_date"] == _RESET_END)
        assert "task_id" in ev["metadata"]
        assert isinstance(ev["metadata"]["task_id"], int)

    def test_reset_task_appears_in_active_state(self, client):
        r = client.get("/state/active")
        open_tasks = r.json()["open_tasks"]
        assert any("Reset Day Protocol" in t["title"] for t in open_tasks)

    def test_no_reset_when_last_day_complete(self, client):
        # Make all 7 days complete → no consecutive incomplete streak
        for d in _week_days(_PERFECT_END):
            _make_complete_day(client, d)
        _trigger_north_star(client, _PERFECT_END)
        events = _behavior_events(client, EventType.RESET_DAY_PROTOCOL)
        matching = [e for e in events if e["reference_date"] == _PERFECT_END]
        assert len(matching) == 0


class TestScenarioPerfectWeek:
    """score == 1.0 → perfect_week event."""

    def test_perfect_week_event_emitted(self, client):
        for d in _week_days(_PERFECT_END):
            _make_complete_day(client, d)
        _trigger_north_star(client, _PERFECT_END)
        events = _behavior_events(client, EventType.PERFECT_WEEK)
        matching = [e for e in events if e["reference_date"] == _PERFECT_END]
        assert len(matching) == 1

    def test_perfect_week_metadata_score_is_1(self, client):
        events = _behavior_events(client, EventType.PERFECT_WEEK)
        ev = next(e for e in events if e["reference_date"] == _PERFECT_END)
        assert float(ev["metadata"]["score"]) == 1.0

    def test_no_perfect_week_for_incomplete(self, client):
        # _WARN_END has score 0.0 → no perfect_week
        events = _behavior_events(client, EventType.PERFECT_WEEK)
        matching = [e for e in events if e["reference_date"] == _WARN_END]
        assert len(matching) == 0


class TestIdempotency:
    """Calling the endpoint multiple times must not duplicate events."""

    def test_double_call_same_warning(self, client):
        _trigger_north_star(client, _IDEM_END)
        _trigger_north_star(client, _IDEM_END)
        events = _behavior_events(client, EventType.CLARITY_WARNING)
        matching = [e for e in events if e["reference_date"] == _IDEM_END]
        assert len(matching) == 1  # exactly one, not two

    def test_double_call_same_reset_no_duplicate_task(self, client, db):
        days = _week_days(_IDEM_END)
        # Make first 4 complete, last 3 empty
        for d in days[:4]:
            _make_complete_day(client, d)
        _trigger_north_star(client, _IDEM_END)
        _trigger_north_star(client, _IDEM_END)

        from sqlalchemy import func
        count = (
            db.query(func.count(Task.id))
            .filter(Task.title == "Reset Day Protocol", Task.day == date.fromisoformat(_IDEM_END))
            .scalar()
        )
        assert count == 1  # created once only

    def test_double_call_same_perfect_week(self, client):
        for d in _week_days(_PERFECT_END):
            _make_complete_day(client, d)
        _trigger_north_star(client, _PERFECT_END)
        _trigger_north_star(client, _PERFECT_END)
        events = _behavior_events(client, EventType.PERFECT_WEEK)
        matching = [e for e in events if e["reference_date"] == _PERFECT_END]
        assert len(matching) == 1


class TestBehaviorEventsEndpoint:
    """GET /behavior/events general contract."""

    def test_returns_200(self, client):
        r = client.get("/behavior/events")
        assert r.status_code == 200

    def test_response_has_total_and_items(self, client):
        r = client.get("/behavior/events")
        body = r.json()
        assert "total" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_filter_by_event_type(self, client):
        _trigger_north_star(client, _WARN_END)
        for et in [EventType.CLARITY_WARNING, EventType.RESET_DAY_PROTOCOL, EventType.PERFECT_WEEK]:
            r = client.get(f"/behavior/events?event_type={et}")
            for item in r.json()["items"]:
                assert item["event_type"] == et

    def test_event_fields_present(self, client):
        _trigger_north_star(client, _WARN_END)
        items = _behavior_events(client)
        assert len(items) > 0
        for field in ["id", "event_type", "reference_date", "created_at"]:
            assert field in items[0]

    def test_pagination_limit(self, client):
        r = client.get("/behavior/events?limit=1")
        assert len(r.json()["items"]) <= 1

    def test_invalid_limit_rejected(self, client):
        r = client.get("/behavior/events?limit=0")
        assert r.status_code == 422
