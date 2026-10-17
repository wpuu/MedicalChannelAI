from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime as RealDateTime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


WEB_ROOT = Path(__file__).resolve().parents[2]
HEALTH_PATH = WEB_ROOT / "api" / "pipeline-health.py"
NOW = RealDateTime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


class FixedDateTime(RealDateTime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


class FakeCache:
    values: dict[str, object] = {}

    def __init__(self, *_args, **_kwargs):
        pass

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, *_args, **_kwargs):
        self.values[key] = value


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _load_health_module():
    vercel = types.ModuleType("vercel")
    functions = types.ModuleType("vercel.functions")
    functions.RuntimeCache = FakeCache
    vercel.functions = functions
    with patch.dict(sys.modules, {"vercel": vercel, "vercel.functions": functions}):
        spec = importlib.util.spec_from_file_location("offline_pipeline_health", HEALTH_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
    return module


health = _load_health_module()


def _coverage(revision: str, *, complete=True, anchor: str | None = None, failures=None):
    return {
        "complete": complete,
        "last_complete_as_of": revision if anchor is None else anchor,
        "updated_source_ids": [],
        "failed_source_ids": [] if failures is None else failures,
    }


def _snapshot(revision: str, *, complete=True, anchor: str | None = None, failures=None):
    return {
        "snapshot_as_of": revision,
        "collection_coverage": _coverage(revision, complete=complete, anchor=anchor, failures=failures),
    }


def _database_status(snapshot, *, degraded=False, outcome="COMPLETED", ready=True):
    return {
        "ready": ready,
        "degraded": degraded,
        "collection": {"available": True, "outcome": outcome, "failures": []},
        "snapshot": {
            "available": True,
            "source_mode": "DATABASE",
            "freshness": "FRESH",
            "degraded": False,
            **snapshot,
        },
    }


def _run_health(*, database_status=None, database_http_status=-1, runtime_snapshot=None,
                runtime_state=None, bundled=None, cache_class=FakeCache):
    FakeCache.values = {}
    if runtime_snapshot is not None:
        FakeCache.values[health.LATEST_RUNTIME_SNAPSHOT_KEY] = runtime_snapshot
    if runtime_state is not None:
        FakeCache.values[health.META_KEY] = runtime_state
    captured = {}

    def send_json(_self, status, payload):
        captured.update(status=status, payload=payload)

    database_configured = database_status is not None or database_http_status != -1
    env = {
        "VERCEL_ENV": "production",
        "CRON_SECRET": "offline-configured",
        "VERCEL_PROJECT_PRODUCTION_URL": "offline.invalid",
        "DATABASE_URL": "offline-db-configured" if database_configured else "",
        "POSTGRES_URL": "",
    }
    response_status = 200 if database_http_status == -1 else database_http_status
    response = FakeResponse(database_status or {}, response_status)
    with patch.dict(health.os.environ, env, clear=False), \
         patch.object(health, "datetime", FixedDateTime), \
         patch.object(health, "RuntimeCache", cache_class), \
         patch.object(health, "_CACHE_IMPORT_OK", True), \
         patch.object(health, "_IMPORT_OK", True), \
         patch.object(health, "_DATA_OK", True), \
         patch.object(health, "cache_roundtrip", return_value=True), \
         patch.object(health, "urlopen", return_value=response if database_configured else None) as opener, \
         patch.object(health, "_bundled_snapshot", return_value=bundled), \
         patch.object(health.handler, "_send_json", new=send_json):
        if not database_configured:
            opener.side_effect = AssertionError("network access is disabled in this test")
        health.handler.do_GET(object.__new__(health.handler))
    return captured


class PipelineHealthSnapshotFreshnessTests(unittest.TestCase):
    def test_snapshot_coverage_requires_boolean_complete_and_consistent_anchors(self):
        recent = (NOW - timedelta(minutes=1)).isoformat()
        valid = _snapshot(recent)
        self.assertEqual(health._snapshot_time(valid), RealDateTime.fromisoformat(recent))
        self.assertEqual(
            health._snapshot_time(_snapshot(recent, complete=False, anchor=(NOW - timedelta(hours=2)).isoformat())),
            NOW - timedelta(hours=2),
        )

        invalid_values = [
            {"snapshot_as_of": recent, "collection_coverage": {}},
            _snapshot(recent, complete="true"),
            _snapshot(recent, anchor=(NOW - timedelta(hours=1)).isoformat()),
            _snapshot(recent, failures=["tjmugh"]),
            {**_snapshot(recent), "collection_coverage": {**_coverage(recent), "updated_source_ids": ["bad id"]}},
            {**_snapshot(recent), "collection_coverage": {**_coverage(recent), "updated_source_ids": ["tjmugh"] * 21}},
            _snapshot(recent, complete=False, anchor=(NOW + timedelta(minutes=1)).isoformat()),
            {"snapshot_as_of": recent, "collection_coverage": {"complete": True, "last_complete_as_of": recent}},
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertIsNone(health._snapshot_time(value))

    def test_future_skew_and_age_limits_are_enforced(self):
        at_limit = (NOW + timedelta(minutes=15)).isoformat()
        outside = (NOW + timedelta(minutes=15, seconds=1)).isoformat()
        self.assertEqual(health._snapshot_freshness(_snapshot(at_limit), NOW), (True, 0, None))
        self.assertEqual(health._snapshot_freshness(_snapshot(outside), NOW), (False, None, "SNAPSHOT_FUTURE"))
        stale = _snapshot((NOW - timedelta(hours=30, seconds=1)).isoformat())
        fresh, age, reason = health._snapshot_freshness(stale, NOW)
        self.assertFalse(fresh)
        self.assertGreater(age, health.MAX_VERIFIED_SNAPSHOT_AGE_SECONDS)
        self.assertEqual(reason, "SNAPSHOT_STALE")
        partial_future_revision = _snapshot(
            (NOW + timedelta(hours=1)).isoformat(),
            complete=False,
            anchor=(NOW - timedelta(hours=1)).isoformat(),
        )
        self.assertEqual(health._snapshot_freshness(partial_future_revision, NOW), (False, None, "SNAPSHOT_FUTURE"))

    def test_durable_status_is_authoritative_and_degraded_status_cannot_fall_back(self):
        revision = (NOW - timedelta(minutes=1)).isoformat()
        degraded = _database_status(_snapshot(revision), degraded=True, outcome="FAILED")
        result = _run_health(
            database_status=degraded,
            runtime_snapshot=_snapshot(revision),
            runtime_state={"stages": {"publish": {"status": "COMPLETED", "terminal": True}}},
            bundled=_snapshot(revision),
        )
        self.assertEqual(result["status"], 503)
        runtime = result["payload"]["pipeline_runtime"]
        self.assertFalse(runtime["verified_snapshot_fresh"])
        self.assertEqual(runtime["verified_snapshot_source"], "DATABASE_STATUS")
        self.assertEqual(runtime["verified_snapshot_health_reason"], "DATABASE_STATUS_DEGRADED")

    def test_database_http_failure_cannot_fall_back_to_old_runtime_or_bundle(self):
        revision = (NOW - timedelta(minutes=1)).isoformat()
        result = _run_health(
            database_http_status=503,
            runtime_snapshot=_snapshot(revision),
            runtime_state={"stages": {"publish": {"status": "COMPLETED", "terminal": True}}},
            bundled=_snapshot(revision),
        )
        self.assertEqual(result["status"], 503)
        self.assertFalse(result["payload"]["pipeline_runtime"]["verified_snapshot_fresh"])
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_health_reason"], "DATABASE_STATUS_UNAVAILABLE")

    def test_completed_durable_full_snapshot_remains_healthy(self):
        revision = (NOW - timedelta(minutes=10)).isoformat()
        result = _run_health(database_status=_database_status(_snapshot(revision)))
        self.assertEqual(result["status"], 200)
        runtime = result["payload"]["pipeline_runtime"]
        self.assertTrue(runtime["verified_snapshot_fresh"])
        self.assertEqual(runtime["verified_snapshot_source"], "DATABASE_STATUS")
        self.assertEqual(runtime["verified_snapshot_age_seconds"], 600)
        self.assertIsNone(runtime["verified_snapshot_health_reason"])

    def test_partial_durable_coverage_is_not_full_health(self):
        revision = (NOW - timedelta(minutes=1)).isoformat()
        partial = _snapshot(revision, complete=False, anchor=(NOW - timedelta(hours=2)).isoformat())
        result = _run_health(database_status=_database_status(partial))
        self.assertEqual(result["status"], 503)
        runtime = result["payload"]["pipeline_runtime"]
        self.assertFalse(runtime["verified_snapshot_fresh"])
        self.assertEqual(runtime["verified_snapshot_health_reason"], "COLLECTION_COVERAGE_PARTIAL")
        self.assertEqual(runtime["verified_snapshot_age_seconds"], 7200)

    def test_runtime_failure_or_future_snapshot_cannot_be_rescued_by_bundle(self):
        revision = (NOW - timedelta(minutes=1)).isoformat()
        failed_state = {"stages": {"publish": {"status": "FAILED", "terminal": True}}}
        result = _run_health(
            runtime_snapshot=_snapshot(revision), runtime_state=failed_state, bundled=_snapshot(revision),
        )
        self.assertEqual(result["status"], 503)
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_health_reason"], "COLLECTION_STATE_DEGRADED")

        future = (NOW + timedelta(hours=1)).isoformat()
        completed_state = {"stages": {"publish": {"status": "COMPLETED", "terminal": True}}}
        result = _run_health(
            runtime_snapshot=_snapshot(future), runtime_state=completed_state, bundled=_snapshot(revision),
        )
        self.assertEqual(result["status"], 503)
        self.assertFalse(result["payload"]["pipeline_runtime"]["verified_snapshot_fresh"])
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_health_reason"], "SNAPSHOT_FUTURE")

    def test_missing_or_malformed_runtime_collection_state_is_unknown(self):
        revision = (NOW - timedelta(minutes=1)).isoformat()
        bundle = _snapshot(revision)
        result = _run_health(runtime_snapshot=None, runtime_state=None, bundled=bundle)
        self.assertEqual(result["status"], 503)
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_health_reason"], "COLLECTION_STATE_UNKNOWN")
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_source"], "BUNDLED_SNAPSHOT")
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_age_seconds"], 60)

        malformed_state = {"stages": {"publish": {"status": ["COMPLETED"], "terminal": True}}}
        result = _run_health(runtime_snapshot=_snapshot(revision), runtime_state=malformed_state, bundled=bundle)
        self.assertEqual(result["status"], 503)
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_health_reason"], "COLLECTION_STATE_UNKNOWN")

        class FailingCache(FakeCache):
            def get(self, _key):
                raise RuntimeError("offline cache failure")

        result = _run_health(runtime_snapshot=_snapshot(revision), runtime_state=None, bundled=bundle, cache_class=FailingCache)
        self.assertEqual(result["status"], 503)
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_health_reason"], "RUNTIME_CACHE_UNAVAILABLE")

    def test_malformed_durable_health_fields_and_snapshot_availability_are_rejected(self):
        revision = (NOW - timedelta(minutes=1)).isoformat()
        malformed_degraded = _database_status(_snapshot(revision))
        malformed_degraded.pop("degraded")
        result = _run_health(database_status=malformed_degraded)
        self.assertEqual(result["status"], 503)
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_health_reason"], "DATABASE_STATUS_INVALID")

        unavailable_snapshot = _database_status(_snapshot(revision))
        unavailable_snapshot["snapshot"]["available"] = False
        result = _run_health(database_status=unavailable_snapshot)
        self.assertEqual(result["status"], 503)
        self.assertEqual(result["payload"]["pipeline_runtime"]["verified_snapshot_health_reason"], "DATABASE_STATUS_NOT_READY")

    def test_partial_without_last_complete_anchor_is_partial_not_malformed(self):
        revision = (NOW - timedelta(minutes=1)).isoformat()
        value = {
            "snapshot_as_of": revision,
            "collection_coverage": {
                "complete": False,
                "last_complete_as_of": None,
                "updated_source_ids": [],
                "failed_source_ids": [],
            },
        }
        self.assertIsNone(health._snapshot_time(value))
        self.assertEqual(health._snapshot_freshness(value, NOW), (False, None, "COLLECTION_COVERAGE_PARTIAL"))

    def test_timestamp_normalization_overflow_is_invalid(self):
        value = {
            "snapshot_as_of": "0001-01-01T00:00:00+01:00",
            "collection_coverage": {
                "complete": True,
                "last_complete_as_of": "0001-01-01T00:00:00+01:00",
                "updated_source_ids": [],
                "failed_source_ids": [],
            },
        }
        self.assertIsNone(health._snapshot_time(value))

    def test_runtime_full_snapshot_and_terminal_success_state_are_healthy(self):
        revision = (NOW - timedelta(minutes=1)).isoformat()
        completed_state = {"stages": {"publish": {"status": "COMPLETED", "terminal": True}}}
        result = _run_health(runtime_snapshot=_snapshot(revision), runtime_state=completed_state)
        self.assertEqual(result["status"], 200)
        self.assertTrue(result["payload"]["pipeline_runtime"]["verified_snapshot_fresh"])


if __name__ == "__main__":
    unittest.main()
