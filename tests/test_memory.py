"""
Tests for the Memory Engine layer.

Covers:
- POST /memory/compile-day  — happy path, empty day, idempotence, all fields present
- POST /memory/compile-week — happy path, auto-compiles missing dailies, idempotence
- GET  /memory/snapshots    — list, filter by type, pagination
- GET  /memory/snapshots/{id} — single fetch, 404 on missing
- Heuristics — emotional state, key_events, decisions, lessons, tags
- Unit tests on pure compiler functions
"""
import json
import pytest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace as NS

from app.services.memory import (
    _build_day_fields,
    _infer_emotional_state,
    _extract_key_events,
    _extract_decisions,
    _extract_lessons,
    _jdump,
    _jload,
)
from app.models.task import TaskStatus
from app.models.transaction import TransactionType
from app.models.entry import EntryType


# ---------------------------------------------------------------------------
# Unit tests on pure functions
# ---------------------------------------------------------------------------

class TestEmotionalState:
    def test_no_entries_is_quiet(self):
        state = _infer_emotional_state(0, 0, Decimal("0"), 0, 0)
        assert state == "quiet"

    def test_all_tasks_done_is_productive(self):
        state = _infer_emotional_state(5, 5, Decimal("0"), 5, 0)
        assert "productive" in state

    def test_partial_tasks_is_progressing(self):
        state = _infer_emotional_state(2, 5, Decimal("0"), 5, 0)
        assert "progressing" in state

    def test_few_tasks_done_is_backlogged(self):
        state = _infer_emotional_state(0, 5, Decimal("0"), 5, 0)
        assert "backlogged" in state

    def test_positive_net_adds_financially_positive(self):
        state = _infer_emotional_state(0, 0, Decimal("100"), 5, 0)
        assert "financially_positive" in state

    def test_negative_net_adds_financially_cautious(self):
        state = _infer_emotional_state(0, 0, Decimal("-50"), 5, 0)
        assert "financially_cautious" in state

    def test_many_facts_adds_knowledge_rich(self):
        state = _infer_emotional_state(0, 0, Decimal("0"), 10, 5)
        assert "knowledge_rich" in state

    def test_compound_state_joined_with_plus(self):
        state = _infer_emotional_state(3, 3, Decimal("200"), 10, 0)
        assert "+" in state  # productive + financially_positive at minimum

    def test_fallback_neutral(self):
        state = _infer_emotional_state(0, 0, Decimal("0"), 5, 0)
        assert state == "neutral"


class TestJsonHelpers:
    def test_jdump_jload_roundtrip(self):
        items = ["one", "dos", "três"]
        assert _jload(_jdump(items)) == items

    def test_jload_empty_string(self):
        assert _jload("") == []

    def test_jload_none(self):
        assert _jload(None) == []

    def test_jload_invalid_json(self):
        assert _jload("not-json") == []


class TestExtractDecisions:
    def _entry(self, raw: str) -> NS:
        return NS(raw=raw, entry_type=EntryType.note)

    def _task(self, title: str) -> NS:
        return NS(title=title, status=TaskStatus.pending)

    def test_decision_keyword_in_entry(self):
        e = self._entry("Decidí usar FastAPI en lugar de Flask")
        decisions = _extract_decisions([e], [])
        assert len(decisions) == 1
        assert "FastAPI" in decisions[0]

    def test_decision_keyword_in_task(self):
        t = self._task("Elegí el proveedor cloud")
        decisions = _extract_decisions([], [t])
        assert any("cloud" in d for d in decisions)

    def test_no_match_returns_empty(self):
        e = self._entry("reunión de equipo")
        decisions = _extract_decisions([e], [])
        assert decisions == []

    def test_deduplication(self):
        e1 = self._entry("decidí pausar el proyecto")
        e2 = self._entry("decidí pausar el proyecto")
        decisions = _extract_decisions([e1, e2], [])
        assert len(decisions) == 1


class TestExtractLessons:
    def _fact(self, content: str) -> NS:
        return NS(content=content)

    def _entry(self, raw: str) -> NS:
        return NS(raw=raw, entry_type=EntryType.fact)

    def test_fact_prefix_extracted(self):
        f = self._fact("FACT: Python es interpretado")
        lessons = _extract_lessons([f], [])
        assert len(lessons) == 1

    def test_dato_prefix_extracted(self):
        f = self._fact("DATO: el café tiene cafeína")
        lessons = _extract_lessons([f], [])
        assert len(lessons) == 1

    def test_non_lesson_fact_excluded(self):
        f = self._fact("Tenía reunión con el cliente")
        lessons = _extract_lessons([f], [])
        assert lessons == []

    def test_entry_with_fact_prefix(self):
        e = self._entry("FACT: aprendí que los índices aceleran las consultas")
        lessons = _extract_lessons([], [e])
        assert len(lessons) == 1

    def test_no_duplicates(self):
        f = self._fact("FACT: el agua hierve a 100C")
        e = self._entry("FACT: el agua hierve a 100C")
        lessons = _extract_lessons([f], [e])
        assert len(lessons) == 1


# ---------------------------------------------------------------------------
# Integration tests — endpoints
# ---------------------------------------------------------------------------

_D1 = "2026-03-10"  # isolated dates for memory tests
_D2 = "2026-03-11"
_D3 = "2026-03-12"
_WEEK_START = "2026-03-09"   # Mon of the week containing D1-D3


class TestCompileDay:
    # A date guaranteed to be empty in the test session (far future, no test ingests here)
    _EMPTY_DAY = "2099-12-31"

    def test_compile_empty_day(self, client):
        r = client.post("/memory/compile-day", json={"day": self._EMPTY_DAY})
        assert r.status_code == 201
        body = r.json()
        assert body["date"] == self._EMPTY_DAY
        assert body["snapshot_type"] == "daily"
        assert "No entries recorded" in body["summary"]
        assert body["emotional_state"] == "quiet"
        assert body["key_events"] == []
        assert body["tags"] == []

    def test_compile_day_with_task(self, client):
        client.post("/ingest", json={"raw": "TODO: escribir tests de memoria", "day": _D1})
        r = client.post("/memory/compile-day", json={"day": _D1})
        assert r.status_code == 201
        body = r.json()
        assert "task" in body["tags"]
        assert "Tasks:" in body["summary"]

    def test_compile_day_with_transaction(self, client):
        client.post("/ingest", json={"raw": "gasté $75 en suscripciones", "day": _D1})
        r = client.post("/memory/compile-day", json={"day": _D1})
        body = r.json()
        assert "Net cashflow" in body["summary"]
        assert "transaction" in body["tags"]
        assert any("Transaction" in ev for ev in body["key_events"])

    def test_compile_day_with_fact_lesson(self, client):
        client.post("/ingest", json={"raw": "FACT: el índice BRIN es mejor para series temporales", "day": _D1})
        r = client.post("/memory/compile-day", json={"day": _D1})
        body = r.json()
        assert any("BRIN" in l for l in body["lessons"])

    def test_compile_day_with_metric(self, client):
        client.post("/ingest", json={"raw": "METRIC: pasos=8000 count", "day": _D2})
        r = client.post("/memory/compile-day", json={"day": _D2})
        body = r.json()
        assert "metric" in body["tags"] or "metrics" in body["tags"]
        assert any("pasos" in ev or "Metric" in ev for ev in body["key_events"])

    def test_compile_day_defaults_to_today(self, client):
        r = client.post("/memory/compile-day", json={})
        assert r.status_code == 201
        from datetime import date
        assert r.json()["date"] == str(date.today())

    def test_compile_day_is_idempotent(self, client):
        client.post("/ingest", json={"raw": "TODO: tarea de idempotencia", "day": _D3})
        r1 = client.post("/memory/compile-day", json={"day": _D3})
        r2 = client.post("/memory/compile-day", json={"day": _D3})
        assert r1.status_code == 201
        assert r2.status_code == 201
        # Same ID → same row was updated
        assert r1.json()["id"] == r2.json()["id"]

    def test_response_has_all_required_fields(self, client):
        r = client.post("/memory/compile-day", json={"day": "2026-02-01"})
        body = r.json()
        for field in ["id", "date", "snapshot_type", "summary", "key_events",
                      "emotional_state", "decisions_made", "lessons", "tags", "created_at"]:
            assert field in body, f"Missing field: {field}"

    def test_key_events_is_list(self, client):
        r = client.post("/memory/compile-day", json={"day": "2026-02-02"})
        assert isinstance(r.json()["key_events"], list)

    def test_decisions_made_is_list(self, client):
        r = client.post("/memory/compile-day", json={"day": "2026-02-02"})
        assert isinstance(r.json()["decisions_made"], list)

    def test_decision_detected_from_entry(self, client):
        client.post("/ingest", json={"raw": "Decidí migrar a PostgreSQL 16", "day": "2026-05-01"})
        r = client.post("/memory/compile-day", json={"day": "2026-05-01"})
        body = r.json()
        assert any("PostgreSQL" in d for d in body["decisions_made"])


class TestCompileWeek:
    def test_compile_week_happy_path(self, client):
        # Seed data in week
        client.post("/ingest", json={"raw": "TODO: weekly task uno", "day": _WEEK_START})
        client.post("/ingest", json={"raw": "gasté $100 en hosting", "day": _WEEK_START})
        r = client.post("/memory/compile-week", json={"week_start": _WEEK_START})
        assert r.status_code == 201
        body = r.json()
        assert body["snapshot_type"] == "weekly"
        assert body["date"] == _WEEK_START
        assert "Week" in body["summary"]
        assert "/7 active days" in body["summary"]

    def test_compile_week_creates_missing_daily_snapshots(self, client):
        week = "2026-04-07"  # isolated week
        r = client.post("/memory/compile-week", json={"week_start": week})
        assert r.status_code == 201
        # Now all 7 daily snapshots should exist
        r_list = client.get("/memory/snapshots?snapshot_type=daily&limit=100")
        dates = {item["date"] for item in r_list.json()["items"]}
        from datetime import date
        for i in range(7):
            d = str(date.fromisoformat(week) + timedelta(days=i))
            assert d in dates

    def test_compile_week_is_idempotent(self, client):
        week = "2026-04-14"
        r1 = client.post("/memory/compile-week", json={"week_start": week})
        r2 = client.post("/memory/compile-week", json={"week_start": week})
        assert r1.json()["id"] == r2.json()["id"]

    def test_compile_week_aggregates_key_events(self, client):
        week = "2026-04-21"
        client.post("/ingest", json={"raw": "TODO: tarea semana", "day": week})
        client.post("/ingest", json={"raw": "ingreso $500 cliente", "day": week})
        r = client.post("/memory/compile-week", json={"week_start": week})
        body = r.json()
        # At least some key events should appear from seeded data
        assert isinstance(body["key_events"], list)

    def test_compile_week_emotional_state_not_empty(self, client):
        week = "2026-04-28"
        r = client.post("/memory/compile-week", json={"week_start": week})
        assert r.json()["emotional_state"] is not None
        assert len(r.json()["emotional_state"]) > 0


class TestSnapshotsList:
    def test_list_all_snapshots(self, client):
        client.post("/memory/compile-day", json={"day": "2026-06-01"})
        r = client.get("/memory/snapshots")
        assert r.status_code == 200
        body = r.json()
        assert "total" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_filter_by_daily(self, client):
        r = client.get("/memory/snapshots?snapshot_type=daily")
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["snapshot_type"] == "daily"

    def test_filter_by_weekly(self, client):
        client.post("/memory/compile-week", json={"week_start": "2026-06-08"})
        r = client.get("/memory/snapshots?snapshot_type=weekly")
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["snapshot_type"] == "weekly"

    def test_pagination_limit(self, client):
        r = client.get("/memory/snapshots?limit=2")
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 2

    def test_pagination_offset(self, client):
        r_all = client.get("/memory/snapshots?limit=100")
        r_off = client.get("/memory/snapshots?limit=100&offset=1")
        all_ids = [i["id"] for i in r_all.json()["items"]]
        off_ids = [i["id"] for i in r_off.json()["items"]]
        if len(all_ids) > 1:
            assert off_ids == all_ids[1:]

    def test_sorted_newest_first(self, client):
        client.post("/memory/compile-day", json={"day": "2026-06-20"})
        client.post("/memory/compile-day", json={"day": "2026-06-21"})
        r = client.get("/memory/snapshots?snapshot_type=daily&limit=10")
        dates = [i["date"] for i in r.json()["items"]]
        assert dates == sorted(dates, reverse=True)


class TestSnapshotById:
    def test_get_existing_snapshot(self, client):
        created = client.post("/memory/compile-day", json={"day": "2026-07-01"}).json()
        r = client.get(f"/memory/snapshots/{created['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_get_nonexistent_returns_404(self, client):
        r = client.get("/memory/snapshots/999999")
        assert r.status_code == 404
        body = r.json()
        assert body["code"] == "NARRATIVE_NOT_FOUND"
