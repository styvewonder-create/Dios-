"""
Tests for error handling: structured error responses, HTTP status codes,
and the custom exception classes.
"""
import pytest
from app.core.errors import (
    DayAlreadyClosedError,
    BatchTooLargeError,
    EmptyBatchError,
    EntryIngestionError,
    RouterNoActiveRulesError,
)
from datetime import date


# ---------------------------------------------------------------------------
# Unit tests on exception classes
# ---------------------------------------------------------------------------

class TestExceptionClasses:
    def test_day_already_closed_error(self):
        err = DayAlreadyClosedError(day=date(2026, 2, 20))
        assert err.http_status == 409
        assert err.code == "DAY_ALREADY_CLOSED"
        assert "2026-02-20" in err.message
        d = err.to_dict()
        assert d["code"] == "DAY_ALREADY_CLOSED"
        assert d["details"]["day"] == "2026-02-20"

    def test_batch_too_large_error(self):
        err = BatchTooLargeError(max_items=100, received=150)
        assert err.http_status == 422
        assert err.code == "BATCH_TOO_LARGE"
        assert "100" in err.message
        assert "150" in err.message
        d = err.to_dict()
        assert d["details"]["max_items"] == 100
        assert d["details"]["received"] == 150

    def test_empty_batch_error(self):
        err = EmptyBatchError()
        assert err.http_status == 422
        assert err.code == "EMPTY_BATCH"

    def test_entry_ingestion_error_with_raw(self):
        err = EntryIngestionError(message="oops", raw="bad entry")
        assert err.http_status == 500
        assert err.code == "INGESTION_ERROR"
        assert err.details["raw"] == "bad entry"

    def test_router_no_active_rules_error(self):
        err = RouterNoActiveRulesError()
        assert err.http_status == 500
        assert err.code == "ROUTER_NO_ACTIVE_RULES"

    def test_to_dict_without_details(self):
        err = EmptyBatchError()
        d = err.to_dict()
        assert "code" in d
        assert "message" in d
        # details should not be in dict when empty
        assert "details" not in d


# ---------------------------------------------------------------------------
# Integration tests on HTTP error responses
# ---------------------------------------------------------------------------

class TestValidationErrors:
    def test_empty_raw_returns_validation_error(self, client):
        r = client.post("/ingest", json={"raw": ""})
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "errors" in body["details"]
        assert isinstance(body["details"]["errors"], list)

    def test_whitespace_only_raw_returns_validation_error(self, client):
        r = client.post("/ingest", json={"raw": "   \t\n  "})
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"

    def test_missing_raw_returns_validation_error(self, client):
        r = client.post("/ingest", json={})
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"

    def test_invalid_source_returns_validation_error(self, client):
        r = client.post("/ingest", json={"raw": "test", "source": "invalid_channel"})
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"
        # Should indicate which field failed
        fields = [e["field"] for e in body["details"]["errors"]]
        assert any("source" in f for f in fields)

    def test_invalid_day_format_returns_validation_error(self, client):
        r = client.post("/ingest", json={"raw": "test", "day": "not-a-date"})
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"

    def test_raw_too_long_returns_validation_error(self, client):
        r = client.post("/ingest", json={"raw": "x" * 10_001})
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"


class TestConflictErrors:
    # Use isolated past dates no other test touches
    _DAY_A = "2024-07-04"
    _DAY_B = "2024-07-05"

    def test_close_day_twice_returns_409_with_code(self, client):
        client.post("/ingest", json={"raw": "setup for 409 test", "day": self._DAY_A})
        r1 = client.post("/state/close-day", json={"day": self._DAY_A})
        assert r1.status_code == 200

        r2 = client.post("/state/close-day", json={"day": self._DAY_A})
        assert r2.status_code == 409
        body = r2.json()
        assert body["code"] == "DAY_ALREADY_CLOSED"
        assert "details" in body
        assert "day" in body["details"]

    def test_409_has_machine_readable_code(self, client):
        client.post("/ingest", json={"raw": "code test entry", "day": self._DAY_B})
        client.post("/state/close-day", json={"day": self._DAY_B})
        r = client.post("/state/close-day", json={"day": self._DAY_B})
        assert r.json()["code"] == "DAY_ALREADY_CLOSED"


class TestSourceChannelValidation:
    @pytest.mark.parametrize("source", ["voice", "text", "cli", "api", "slack", "webhook"])
    def test_all_valid_sources_accepted(self, client, source):
        r = client.post("/ingest", json={"raw": "nota de prueba", "source": source})
        assert r.status_code == 201
        assert r.json()["source"] == source

    @pytest.mark.parametrize("source", ["email", "sms", "fax", "pigeon", "", "Voice"])
    def test_invalid_sources_rejected(self, client, source):
        r = client.post("/ingest", json={"raw": "test", "source": source})
        assert r.status_code == 422
        assert r.json()["code"] == "VALIDATION_ERROR"
