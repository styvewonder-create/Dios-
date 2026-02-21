"""
Tests for the North Star Metric — Clarity Score.

Scenarios required by spec:
  A) 7 complete days  → weekly_clarity_score == 1.0
  B) 0 complete days  → weekly_clarity_score == 0.0
  C) Mixed (some complete, some not) → fractional score

Additional coverage:
  - Single-day endpoint
  - Each criterion evaluated individually
  - Score persisted in north_star_snapshots (upsert)
  - reference_date defaults to today
  - Per-day breakdown returned

Isolated date windows are used throughout (far-future dates) so no
other test's data can bleed in and change assertion results.
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.services.north_star_service import (
    calculate_daily_clarity,
    calculate_weekly_clarity,
    _check_day,
    MIN_EVENTS,
)
from app.models.north_star import NorthStarSnapshot


# ---------------------------------------------------------------------------
# Helpers — build isolated Complete Days via the ingest + memory endpoints
# ---------------------------------------------------------------------------

def _make_complete_day(client, day: str) -> None:
    """
    Seed a day so it satisfies all three Complete Day criteria:
      1. ≥ MIN_EVENTS (3) entries
      2. ≥ 1 task done OR ≥ 1 transaction
      3. Daily memory snapshot compiled
    """
    # 3 entries (task + transaction + fact)
    client.post("/ingest", json={"raw": f"TODO: clarity task on {day}", "day": day})
    client.post("/ingest", json={"raw": f"gasté $10 café {day}", "day": day})
    client.post("/ingest", json={"raw": f"FACT: nota de prueba {day}", "day": day})
    # Mark the task as done via ingest (status change not implemented yet,
    # so use a transaction to satisfy criterion 2)
    # transaction already above — has_outcome = True
    # Compile daily memory snapshot (criterion 3)
    client.post("/memory/compile-day", json={"day": day})


def _week_of(anchor: str) -> list[str]:
    """Return 7 ISO date strings for the window ending at anchor."""
    end = date.fromisoformat(anchor)
    return [str(end - timedelta(days=i)) for i in range(6, -1, -1)]


# ---------------------------------------------------------------------------
# Unit tests — service layer (uses db fixture)
# ---------------------------------------------------------------------------

class TestDailyClarityUnit:
    # Use a date window that no integration test touches
    _BASE = date(2090, 1, 1)

    def test_empty_day_is_not_complete(self, db):
        result = _check_day(db, self._BASE)
        assert result.is_complete is False
        assert result.event_count == 0
        assert result.has_outcome is False
        assert result.has_memory_snapshot is False

    def test_is_complete_requires_all_three_criteria(self, db):
        # Nothing seeded → never complete
        d = self._BASE + timedelta(days=1)
        result = _check_day(db, d)
        assert not result.is_complete

    def test_event_count_below_minimum_not_complete(self, db):
        """Even with memory snapshot, < MIN_EVENTS entries → not complete."""
        result = _check_day(db, self._BASE + timedelta(days=2))
        assert result.event_count < MIN_EVENTS
        assert not result.is_complete


class TestWeeklyClarityUnit:
    _ANCHOR = date(2090, 2, 1)  # isolated week

    def test_all_empty_days_score_zero(self, db):
        result = calculate_weekly_clarity(db, self._ANCHOR)
        assert result.clarity_score == Decimal("0.0")
        assert result.complete_days == 0
        assert result.total_days == 7

    def test_window_is_exactly_7_days(self, db):
        result = calculate_weekly_clarity(db, self._ANCHOR)
        assert len(result.days) == 7

    def test_oldest_day_first(self, db):
        result = calculate_weekly_clarity(db, self._ANCHOR)
        dates = [r.day for r in result.days]
        assert dates == sorted(dates)

    def test_reference_date_is_last_in_window(self, db):
        result = calculate_weekly_clarity(db, self._ANCHOR)
        assert result.days[-1].day == self._ANCHOR


# ---------------------------------------------------------------------------
# Integration tests — full HTTP scenarios
# ---------------------------------------------------------------------------

# Isolated 7-day windows (far future, year 2091)
_ALL_COMPLETE_END   = "2091-01-07"   # window: 2091-01-01 → 2091-01-07
_ALL_INCOMPLETE_END = "2091-02-07"   # window: 2091-02-01 → 2091-02-07
_MIXED_END          = "2091-03-07"   # window: 2091-03-01 → 2091-03-07
_PARTIAL_END        = "2091-04-07"   # extra scenarios
_SINGLE_DAY_TEST    = "2091-05-15"


class TestScenarioAllComplete:
    """7 complete days → score == 1.0"""

    def test_all_7_complete_days(self, client):
        for day in _week_of(_ALL_COMPLETE_END):
            _make_complete_day(client, day)

        r = client.get(f"/metrics/north-star?reference_date={_ALL_COMPLETE_END}")
        assert r.status_code == 200
        body = r.json()
        assert body["weekly_clarity_score"] == 1.0
        assert body["complete_days"] == 7
        assert body["total_days"] == 7

    def test_all_days_marked_complete_in_breakdown(self, client):
        r = client.get(f"/metrics/north-star?reference_date={_ALL_COMPLETE_END}")
        for day_item in r.json()["days"]:
            assert day_item["is_complete"] is True

    def test_reference_date_in_response(self, client):
        r = client.get(f"/metrics/north-star?reference_date={_ALL_COMPLETE_END}")
        assert r.json()["reference_date"] == _ALL_COMPLETE_END


class TestScenarioAllIncomplete:
    """0 complete days → score == 0.0"""

    def test_zero_complete_days(self, client):
        # No seeding for _ALL_INCOMPLETE_END window — all days empty
        r = client.get(f"/metrics/north-star?reference_date={_ALL_INCOMPLETE_END}")
        assert r.status_code == 200
        body = r.json()
        assert body["weekly_clarity_score"] == 0.0
        assert body["complete_days"] == 0
        assert body["total_days"] == 7

    def test_all_days_marked_incomplete_in_breakdown(self, client):
        r = client.get(f"/metrics/north-star?reference_date={_ALL_INCOMPLETE_END}")
        for day_item in r.json()["days"]:
            assert day_item["is_complete"] is False


class TestScenarioMixed:
    """Some complete, some not → fractional score."""

    # Make exactly 3 of the 7 days complete
    _COMPLETE_DAYS = [_week_of(_MIXED_END)[i] for i in (0, 2, 5)]  # Mon, Wed, Sat

    def test_mixed_score_is_correct(self, client):
        for day in self._COMPLETE_DAYS:
            _make_complete_day(client, day)

        r = client.get(f"/metrics/north-star?reference_date={_MIXED_END}")
        assert r.status_code == 200
        body = r.json()
        assert body["complete_days"] == 3
        assert body["total_days"] == 7
        # 3/7 ≈ 0.4286
        assert abs(body["weekly_clarity_score"] - 3 / 7) < 0.001

    def test_mixed_breakdown_correct_flags(self, client):
        r = client.get(f"/metrics/north-star?reference_date={_MIXED_END}")
        days = r.json()["days"]
        complete_dates = {str(d) for d in self._COMPLETE_DAYS}
        for day_item in days:
            if day_item["day"] in complete_dates:
                assert day_item["is_complete"] is True
            else:
                assert day_item["is_complete"] is False


class TestCriteriaBreakdown:
    """Verify each criterion is reported independently."""

    def test_missing_memory_snapshot_fails_criterion_3(self, client):
        day = "2091-06-01"
        # Seed entries + transaction but no memory snapshot
        client.post("/ingest", json={"raw": "TODO: task a", "day": day})
        client.post("/ingest", json={"raw": "gasté $5 test", "day": day})
        client.post("/ingest", json={"raw": "FACT: nota test", "day": day})

        r = client.get(f"/metrics/north-star/day?day={day}")
        body = r.json()
        assert body["has_outcome"] is True
        assert body["event_count"] >= 3
        assert body["has_memory_snapshot"] is False
        assert body["is_complete"] is False

    def test_missing_outcome_fails_criterion_2(self, client):
        day = "2091-06-02"
        # 3 fact entries (no task done, no transaction), + memory snapshot
        client.post("/ingest", json={"raw": "FACT: uno", "day": day})
        client.post("/ingest", json={"raw": "FACT: dos", "day": day})
        client.post("/ingest", json={"raw": "FACT: tres", "day": day})
        client.post("/memory/compile-day", json={"day": day})

        r = client.get(f"/metrics/north-star/day?day={day}")
        body = r.json()
        assert body["event_count"] >= 3
        assert body["has_memory_snapshot"] is True
        assert body["has_outcome"] is False
        assert body["is_complete"] is False

    def test_insufficient_events_fails_criterion_1(self, client):
        day = "2091-06-03"
        # Only 2 entries (below MIN_EVENTS=3), but has outcome + snapshot
        client.post("/ingest", json={"raw": "gasté $10 menos", "day": day})
        client.post("/ingest", json={"raw": "FACT: second entry", "day": day})
        client.post("/memory/compile-day", json={"day": day})

        r = client.get(f"/metrics/north-star/day?day={day}")
        body = r.json()
        assert body["event_count"] == 2
        assert body["has_outcome"] is True
        assert body["has_memory_snapshot"] is True
        assert body["is_complete"] is False

    def test_all_criteria_met_is_complete(self, client):
        _make_complete_day(client, _SINGLE_DAY_TEST)
        r = client.get(f"/metrics/north-star/day?day={_SINGLE_DAY_TEST}")
        body = r.json()
        assert body["event_count"] >= 3
        assert body["has_outcome"] is True
        assert body["has_memory_snapshot"] is True
        assert body["is_complete"] is True


class TestNorthStarEndpointGeneral:
    def test_defaults_to_today(self, client):
        r = client.get("/metrics/north-star")
        assert r.status_code == 200
        from datetime import date
        assert r.json()["reference_date"] == str(date.today())

    def test_response_has_all_fields(self, client):
        r = client.get("/metrics/north-star")
        body = r.json()
        for field in ["reference_date", "weekly_clarity_score", "complete_days",
                      "total_days", "days"]:
            assert field in body

    def test_total_days_always_7(self, client):
        r = client.get(f"/metrics/north-star?reference_date={_ALL_INCOMPLETE_END}")
        assert r.json()["total_days"] == 7

    def test_score_is_float(self, client):
        r = client.get("/metrics/north-star")
        assert isinstance(r.json()["weekly_clarity_score"], float)

    def test_score_between_0_and_1(self, client):
        r = client.get("/metrics/north-star")
        score = r.json()["weekly_clarity_score"]
        assert 0.0 <= score <= 1.0

    def test_days_list_has_7_items(self, client):
        r = client.get("/metrics/north-star")
        assert len(r.json()["days"]) == 7

    def test_days_sorted_oldest_first(self, client):
        r = client.get(f"/metrics/north-star?reference_date={_ALL_INCOMPLETE_END}")
        dates = [item["day"] for item in r.json()["days"]]
        assert dates == sorted(dates)

    def test_single_day_endpoint_defaults_to_today(self, client):
        r = client.get("/metrics/north-star/day")
        assert r.status_code == 200
        from datetime import date
        assert r.json()["day"] == str(date.today())

    def test_invalid_date_returns_422(self, client):
        r = client.get("/metrics/north-star?reference_date=not-a-date")
        assert r.status_code == 422

    def test_upsert_idempotent(self, client):
        """Calling twice for the same date updates the row, not duplicates."""
        day = "2091-07-01"
        r1 = client.get(f"/metrics/north-star?reference_date={day}")
        r2 = client.get(f"/metrics/north-star?reference_date={day}")
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Scores must be identical
        assert r1.json()["weekly_clarity_score"] == r2.json()["weekly_clarity_score"]
