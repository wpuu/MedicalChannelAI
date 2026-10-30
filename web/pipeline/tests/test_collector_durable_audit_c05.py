from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

WEB = Path(__file__).resolve().parents[2]
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from collector_durable_audit import ENDPOINT, audit_enabled, try_persist_failure
from collector_schedule import scheduled_cycle
from test_collector_native_reliability import MemoryCache, queue

NOW = datetime(2026, 10, 31, 0, 24, tzinfo=timezone.utc)
CYCLE, _ = scheduled_cycle(NOW, "morning")
ENABLED = {
    "COLLECTOR_AUDIT_ENABLED": "true",
    "COLLECTOR_AUDIT_TOKEN": "dedicated-failure-audit-only-secret-01234567890",
}


class FakeHttpResponse:
    def __init__(self, body=b'{"ok":true,"event_id":"' + b"a" * 64 + b'"}'):
        self.body = body
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


class CollectorDurableFailureAuditTests(unittest.TestCase):
    def test_default_is_disabled_and_never_hits_network(self):
        with patch.dict(os.environ, {}, clear=True), patch("collector_durable_audit.urlopen") as opened:
            self.assertFalse(audit_enabled())
            self.assertFalse(try_persist_failure(
                cycle_id=CYCLE, stage="ccgp",
                event_kind="CRON_QUEUE_FAILED", error_code="COLLECTOR_QUEUE_START_FAILED",
                occurred_at=NOW,
            ))
            opened.assert_not_called()

    def test_only_allowlisted_metadata_sent_to_separate_token_endpoint(self):
        with patch.dict(os.environ, ENABLED, clear=True), patch(
            "collector_durable_audit.urlopen", return_value=FakeHttpResponse(),
        ) as opened:
            ok = try_persist_failure(
                cycle_id=CYCLE, stage="tjmugh",
                event_kind="STAGE_TERMINAL_FAILURE", error_code="COLLECTOR_SOURCE_FAILED",
                occurred_at=NOW,
            )
        self.assertTrue(ok)
        request = opened.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            set(body), {"cycle_id", "stage_id", "event_kind", "error_code", "occurred_at"},
        )
        self.assertEqual(body["stage_id"], "tjmugh")
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertTrue(request.full_url.startswith("https://medicalchannelai.vercel.app/"))
        self.assertEqual(opened.call_args.kwargs["timeout"], 2.0)
        self.assertNotIn("api_key", json.dumps(body))
        self.assertNotIn("contact", json.dumps(body))
        self.assertNotIn("AGNES", json.dumps(body))

    def test_error_text_and_token_cannot_be_sent_as_error_code(self):
        with patch.dict(os.environ, ENABLED, clear=True), patch(
            "collector_durable_audit.urlopen", return_value=FakeHttpResponse(),
        ) as opened:
            ok = try_persist_failure(
                cycle_id=CYCLE, stage="ccgp", event_kind="STAGE_RETRY_ERROR",
                error_code="https://example.com/private?token=abc", occurred_at=NOW,
            )
        self.assertTrue(ok)
        body = json.loads(opened.call_args.args[0].data)
        self.assertEqual(body["error_code"], "ERROR_CODE_UNAVAILABLE")

    def test_transport_error_never_leaks_secret_or_retries(self):
        with patch.dict(os.environ, ENABLED, clear=True), patch(
            "collector_durable_audit.urlopen", side_effect=RuntimeError(
                "PRIVATE TOKEN " + ENABLED["COLLECTOR_AUDIT_TOKEN"]
            ),
        ) as opened:
            self.assertFalse(try_persist_failure(
                cycle_id=CYCLE, stage="ccgp", event_kind="STAGE_RETRY_ERROR",
                error_code="STAGE_ERROR", occurred_at=NOW,
            ))
            opened.assert_called_once()

    def test_invalid_context_ignores_incoming_request_even_when_configured(self):
        with patch.dict(os.environ, ENABLED, clear=True), patch("collector_durable_audit.urlopen") as opened:
            self.assertFalse(try_persist_failure(
                cycle_id="bad", stage="ccgp", event_kind="CRON_QUEUE_FAILED",
                error_code="COLLECTOR_QUEUE_START_FAILED", occurred_at=NOW,
            ))
            self.assertFalse(try_persist_failure(
                cycle_id=CYCLE, stage="ccgp", event_kind="SNAPSHOT_CONFIRMED",
                error_code="COLLECTOR_QUEUE_START_FAILED", occurred_at=NOW,
            ))
            opened.assert_not_called()

    def test_queue_send_failure_keeps_original_error_and_writes_no_success_stamp(self):
        spec = importlib.util.spec_from_file_location("c05_collector_start", WEB / "api/collector-run.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cache = MemoryCache()
        with (
            patch.object(module, "RuntimeCache", return_value=cache),
            patch.object(module, "send", new_callable=AsyncMock, side_effect=RuntimeError("QUEUE_SEND_ORIGINAL")),
            patch.object(module, "try_persist_failure", return_value=False) as audit,
            patch.object(module, "datetime") as clock,
        ):
            clock.now.return_value = NOW
            clock.fromisoformat.side_effect = datetime.fromisoformat
            with self.assertRaisesRegex(RuntimeError, "QUEUE_SEND_ORIGINAL"):
                asyncio.run(module._enqueue_start("VERCEL_CRON", "morning"))
        audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs["event_kind"], "CRON_QUEUE_FAILED")

    def test_terminal_queue_failure_posts_audit_without_generating_success(self):
        from collector_namespace import ACTIVE_CYCLE_KEY, META_KEY
        from collector_proof import read_event

        cache = MemoryCache({
            ACTIVE_CYCLE_KEY: {"cycle_id": CYCLE, "cycle_as_of": NOW.isoformat()},
            META_KEY: {"cycle_id": CYCLE, "cycle_as_of": NOW.isoformat(), "stages": {}},
        })
        payload = {
            "schema_version": "0.1",
            "schedule_version": "twice-daily-v1",
            "stage": "publish",
            "cycle_id": CYCLE,
            "cycle_as_of": NOW.isoformat(),
        }
        with (
            patch.object(queue, "RuntimeCache", return_value=cache),
            patch.object(queue.runtime, "run_stage", return_value=(
                503, {"action": "FAILED", "terminal": True, "error_code": "SOURCE_PARTIAL_FAILURE"}
            )),
            patch.object(queue, "try_persist_failure", return_value=True) as audit,
            patch.object(queue, "datetime") as clock,
        ):
            clock.now.return_value = NOW
            clock.fromisoformat.side_effect = datetime.fromisoformat
            asyncio.run(queue.process_collector_payload(payload))
        audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs["event_kind"], "STAGE_TERMINAL_FAILURE")
        self.assertIsNone(read_event(cache, CYCLE, "publish", "SNAPSHOT_CONFIRMED"))


if __name__ == "__main__":
    unittest.main()
