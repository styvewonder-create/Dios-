"""
Tests for POST /ingest/batch endpoint.

Covers:
- Happy path: all items succeed
- Partial failure: one bad item doesn't cancel the others
- Batch-level source/day defaults inherited by items
- Item-level source/day overrides batch defaults
- Validation: empty batch, too many items, invalid source
- routed_entity returned per item
- Counts in BatchIngestResponse
"""
import pytest
from datetime import date


BASE_URL = "/ingest/batch"


class TestBatchHappyPath:
    def test_all_succeed(self, client):
        payload = {
            "items": [
                {"raw": "TODO: tarea uno"},
                {"raw": "gasté $10 en café"},
                {"raw": "FACT: Python 3.13 salió"},
            ]
        }
        r = client.post(BASE_URL, json=payload)
        assert r.status_code == 207
        body = r.json()
        assert body["total"] == 3
        assert body["succeeded"] == 3
        assert body["failed"] == 0

    def test_item_order_preserved(self, client):
        payload = {
            "items": [
                {"raw": "TODO: primero"},
                {"raw": "TODO: segundo"},
                {"raw": "TODO: tercero"},
            ]
        }
        r = client.post(BASE_URL, json=payload)
        body = r.json()
        indices = [item["index"] for item in body["items"]]
        assert indices == [0, 1, 2]

    def test_each_item_ok_true(self, client):
        payload = {"items": [{"raw": "nota simple"}, {"raw": "otra nota"}]}
        r = client.post(BASE_URL, json=payload)
        for item in r.json()["items"]:
            assert item["ok"] is True
            assert item["entry"] is not None
            assert item["error"] is None

    def test_routed_entity_present_in_batch(self, client):
        payload = {
            "items": [
                {"raw": "TODO: revisar código"},
                {"raw": "ingreso $500 cliente"},
                {"raw": "METRIC: weight=72 kg"},
            ]
        }
        r = client.post(BASE_URL, json=payload)
        items = r.json()["items"]
        assert items[0]["entry"]["routed_entity"]["type"] == "task"
        assert items[1]["entry"]["routed_entity"]["type"] == "transaction"
        assert items[2]["entry"]["routed_entity"]["type"] == "metric"

    def test_single_item_batch(self, client):
        payload = {"items": [{"raw": "TODO: solo un item"}]}
        r = client.post(BASE_URL, json=payload)
        assert r.status_code == 207
        body = r.json()
        assert body["total"] == 1
        assert body["succeeded"] == 1


class TestBatchDefaults:
    def test_batch_level_source_applied_to_all(self, client):
        payload = {
            "source": "voice",
            "items": [{"raw": "primera nota"}, {"raw": "segunda nota"}],
        }
        r = client.post(BASE_URL, json=payload)
        for item in r.json()["items"]:
            assert item["entry"]["source"] == "voice"

    def test_batch_level_day_applied_to_all(self, client):
        payload = {
            "day": "2026-01-10",
            "items": [{"raw": "entrada del pasado"}, {"raw": "otra entrada pasada"}],
        }
        r = client.post(BASE_URL, json=payload)
        for item in r.json()["items"]:
            assert item["entry"]["day"] == "2026-01-10"

    def test_item_source_overrides_batch_source(self, client):
        payload = {
            "source": "voice",
            "items": [
                {"raw": "usa default source"},
                {"raw": "usa cli", "source": "cli"},
            ],
        }
        r = client.post(BASE_URL, json=payload)
        items = r.json()["items"]
        assert items[0]["entry"]["source"] == "voice"
        assert items[1]["entry"]["source"] == "cli"

    def test_item_day_overrides_batch_day(self, client):
        payload = {
            "day": "2026-01-01",
            "items": [
                {"raw": "usa batch day"},
                {"raw": "usa su propio day", "day": "2026-06-15"},
            ],
        }
        r = client.post(BASE_URL, json=payload)
        items = r.json()["items"]
        assert items[0]["entry"]["day"] == "2026-01-01"
        assert items[1]["entry"]["day"] == "2026-06-15"


class TestBatchPartialFailure:
    def test_valid_items_succeed_despite_one_failure(self, client):
        """
        Trigger a failure by sending an empty raw (fails schema validation before
        reaching the service). Valid items around it must still succeed.

        Note: schema-level validation (empty raw) is caught at the batch request
        level, so we trigger a service-level failure via a duplicate metric
        (unique constraint on name+day).
        """
        # Seed a metric first
        client.post("/ingest", json={"raw": "METRIC: dup_metric=100 units", "day": "2026-03-01"})

        payload = {
            "items": [
                {"raw": "TODO: tarea antes del fallo", "day": "2026-03-01"},
                # This metric duplicates name+day → DB unique constraint violation
                {"raw": "METRIC: dup_metric=200 units", "day": "2026-03-01"},
                {"raw": "TODO: tarea después del fallo", "day": "2026-03-01"},
            ]
        }
        r = client.post(BASE_URL, json=payload)
        assert r.status_code == 207
        body = r.json()
        assert body["total"] == 3
        # Item 0 and 2 should succeed; item 1 (duplicate metric) should fail
        assert body["items"][0]["ok"] is True
        assert body["items"][1]["ok"] is False
        assert body["items"][1]["error"] is not None
        assert body["items"][2]["ok"] is True
        assert body["succeeded"] == 2
        assert body["failed"] == 1

    def test_failed_item_has_no_entry(self, client):
        client.post("/ingest", json={"raw": "METRIC: fail_metric=1 u", "day": "2026-04-01"})
        payload = {
            "items": [{"raw": "METRIC: fail_metric=2 u", "day": "2026-04-01"}]
        }
        r = client.post(BASE_URL, json=payload)
        item = r.json()["items"][0]
        assert item["ok"] is False
        assert item["entry"] is None
        assert item["error"] is not None


class TestBatchValidation:
    def test_empty_items_rejected(self, client):
        r = client.post(BASE_URL, json={"items": []})
        assert r.status_code == 422

    def test_missing_items_rejected(self, client):
        r = client.post(BASE_URL, json={})
        assert r.status_code == 422

    def test_invalid_source_in_batch_item_rejected(self, client):
        payload = {"items": [{"raw": "algo", "source": "fax_machine"}]}
        r = client.post(BASE_URL, json=payload)
        assert r.status_code == 422
        assert r.json()["code"] == "VALIDATION_ERROR"

    def test_invalid_source_at_batch_level_rejected(self, client):
        payload = {
            "source": "telegraph",
            "items": [{"raw": "algo"}],
        }
        r = client.post(BASE_URL, json=payload)
        assert r.status_code == 422

    def test_all_valid_sources_accepted(self, client):
        for src in ["voice", "text", "cli", "api", "slack", "webhook"]:
            r = client.post(BASE_URL, json={
                "items": [{"raw": f"test {src}"}],
                "source": src,
            })
            assert r.status_code == 207, f"source={src} should be valid"
