"""
Integration tests for API endpoints using SQLite in-memory DB.
"""
import pytest
from datetime import date


class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestIngest:
    def test_ingest_basic(self, client):
        r = client.post("/ingest", json={"raw": "TODO: write tests"})
        assert r.status_code == 201
        body = r.json()
        assert body["entry_type"] == "task"
        assert body["routed_to"] == "tasks"
        assert body["id"] > 0

    def test_ingest_income(self, client):
        r = client.post("/ingest", json={"raw": "ingreso $500 proyecto A"})
        assert r.status_code == 201
        body = r.json()
        assert body["entry_type"] == "transaction"
        assert body["routed_to"] == "transactions"

    def test_ingest_expense(self, client):
        r = client.post("/ingest", json={"raw": "gasté $20 en café"})
        assert r.status_code == 201
        body = r.json()
        assert body["routed_to"] == "transactions"

    def test_ingest_fact(self, client):
        r = client.post("/ingest", json={"raw": "FACT: el agua hierve a 100C"})
        assert r.status_code == 201
        body = r.json()
        assert body["entry_type"] == "fact"

    def test_ingest_metric(self, client):
        r = client.post("/ingest", json={"raw": "METRIC: steps=10000 count"})
        assert r.status_code == 201
        body = r.json()
        assert body["entry_type"] == "metric"

    def test_ingest_project(self, client):
        r = client.post("/ingest", json={"raw": "PROJECT: App móvil v2"})
        assert r.status_code == 201
        body = r.json()
        assert body["entry_type"] == "project"

    def test_ingest_default_note(self, client):
        r = client.post("/ingest", json={"raw": "El equipo tuvo una buena reunión hoy"})
        assert r.status_code == 201
        body = r.json()
        assert body["entry_type"] == "note"
        assert body["routed_to"] == "facts"

    def test_ingest_with_source(self, client):
        r = client.post("/ingest", json={"raw": "TODO: revisar PR", "source": "slack"})
        assert r.status_code == 201

    def test_ingest_with_explicit_day(self, client):
        r = client.post("/ingest", json={"raw": "nota del pasado", "day": "2026-01-15"})
        assert r.status_code == 201
        assert r.json()["day"] == "2026-01-15"

    def test_ingest_empty_raw_rejected(self, client):
        r = client.post("/ingest", json={"raw": "   "})
        assert r.status_code == 422

    def test_ingest_missing_raw_rejected(self, client):
        r = client.post("/ingest", json={})
        assert r.status_code == 422


class TestStateToday:
    def test_state_today_returns_structure(self, client):
        r = client.get("/state/today")
        assert r.status_code == 200
        body = r.json()
        assert "day" in body
        assert "totals" in body
        assert "entries" in body
        assert "tasks" in body
        assert "transactions" in body
        assert "facts" in body
        assert "metrics" in body

    def test_state_today_reflects_ingested(self, client):
        today = str(date.today())
        client.post("/ingest", json={"raw": "TASK: state test task"})
        r = client.get("/state/today")
        body = r.json()
        assert body["totals"]["entries"] >= 1

    def test_state_today_custom_day(self, client):
        r = client.get("/state/today?day=2026-01-01")
        assert r.status_code == 200
        assert r.json()["day"] == "2026-01-01"


class TestStateActive:
    def test_state_active_structure(self, client):
        r = client.get("/state/active")
        assert r.status_code == 200
        body = r.json()
        assert "open_tasks" in body
        assert "active_projects" in body
        assert "open_days" in body

    def test_active_tasks_appear(self, client):
        client.post("/ingest", json={"raw": "TODO: active task for test"})
        r = client.get("/state/active")
        open_tasks = r.json()["open_tasks"]
        assert any("active task for test" in t["title"] for t in open_tasks)


class TestCloseDay:
    def test_close_day_today(self, client):
        # Ingest something first
        client.post("/ingest", json={"raw": "Some entry for close-day test"})
        r = client.post("/state/close-day", json={"summary": "Great day!"})
        assert r.status_code == 200
        body = r.json()
        assert body["is_closed"] is True
        assert body["summary"] == "Great day!"
        assert body["total_entries"] >= 1

    def test_close_day_twice_conflicts(self, client):
        # First close
        client.post("/state/close-day", json={})
        # Second close — must 409
        r = client.post("/state/close-day", json={})
        assert r.status_code == 409

    def test_close_specific_past_day(self, client):
        client.post("/ingest", json={"raw": "old note", "day": "2025-12-31"})
        r = client.post("/state/close-day", json={"day": "2025-12-31"})
        assert r.status_code == 200
        body = r.json()
        assert body["day"] == "2025-12-31"
        assert body["is_closed"] is True
