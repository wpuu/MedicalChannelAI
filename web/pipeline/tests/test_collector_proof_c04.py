from __future__ import annotations

import unittest
import sys
import asyncio
import importlib.util
from unittest.mock import AsyncMock, patch
from pathlib import Path
from datetime import datetime, timedelta, timezone

WEB_ROOT = Path(__file__).resolve().parents[2]
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

from collector_proof import (
    PROOF_TTL_SECONDS,
    audit_cycle,
    event_cache_key,
    read_event,
    record_event,
    recent_cycle_ids,
    snapshot_source_witness,
    source_stage_freshness,
    try_record,
)
from collector_schedule import scheduled_cycle

from collector_namespace import ACTIVE_CYCLE_KEY, META_KEY
from test_collector_native_reliability import runtime, queue

starter_spec = importlib.util.spec_from_file_location("c04_scheduled_start", WEB_ROOT / "api/collector-run.py")
if starter_spec is None or starter_spec.loader is None:
    raise RuntimeError("C04_START_MODULE_UNAVAILABLE")
starter = importlib.util.module_from_spec(starter_spec)
starter_spec.loader.exec_module(starter)

UTC = timezone.utc
ANCHOR = datetime(2026, 10, 30, 0, 35, tzinfo=UTC)
CYCLE, _ = scheduled_cycle(ANCHOR, "morning")


class MemoryCache:
    def __init__(self):
        self.values = {}
        self.options = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, options=None):
        self.values[key] = value
        self.options[key] = options

    def delete(self, key):
        self.values.pop(key, None)


def record(cache, stage, event, *, when=None, **fields):
    return record_event(
        cache, cycle_id=CYCLE, cycle_as_of=ANCHOR, stage=stage,
        event=event, when=when or ANCHOR + timedelta(minutes=1),
        fields=fields,
    )


class CollectorExecutionProofTests(unittest.TestCase):
    def setUp(self):
        self.cache = MemoryCache()

    def test_trigger_success_is_separate_from_enqueue_and_delivery(self):
        record(self.cache, "ccgp", "TRIGGER_ACCEPTED")
        self.assertIsNotNone(read_event(self.cache, CYCLE, "ccgp", "TRIGGER_ACCEPTED"))
        self.assertIsNone(read_event(self.cache, CYCLE, "ccgp", "STAGE_DELIVERED"))
        self.assertIsNone(read_event(self.cache, CYCLE, "ccgp", "STAGE_COMPLETED"))

    def test_retry_same_event_does_not_replace_original_timestamp(self):
        first = record(self.cache, "ccgp", "TRIGGER_ACCEPTED")
        repeated = record(self.cache, "ccgp", "TRIGGER_ACCEPTED", when=ANCHOR + timedelta(minutes=29))
        self.assertEqual(repeated, first)

    def test_separate_events_have_disjoint_hashed_keys(self):
        self.assertNotEqual(event_cache_key(CYCLE, "ccgp", "STAGE_DELIVERED"),
                            event_cache_key(CYCLE, "ccgp", "STAGE_COMPLETED"))
        self.assertNotIn("prod:2026", event_cache_key(CYCLE, "ccgp", "STAGE_DELIVERED"))
        record(self.cache, "ccgp", "STAGE_DELIVERED")
        key = event_cache_key(CYCLE, "ccgp", "STAGE_DELIVERED")
        self.assertEqual(self.cache.options[key]["ttl"], PROOF_TTL_SECONDS)

    def test_foreign_cycle_and_stage_event_rejected(self):
        with self.assertRaisesRegex(ValueError, "PROOF_CYCLE_INVALID"):
            record_event(
                self.cache, cycle_id="attacker", cycle_as_of=ANCHOR,
                stage="ccgp", event="STAGE_COMPLETED", when=ANCHOR,
            )
        with self.assertRaisesRegex(ValueError, "PROOF_STAGE_INVALID"):
            record(self.cache, "ccgp/../../foo", "STAGE_COMPLETED")
        with self.assertRaisesRegex(ValueError, "PROOF_TRIGGER_NOT_INITIAL_STAGE"):
            record(self.cache, "teda", "TRIGGER_ACCEPTED")
        with self.assertRaisesRegex(ValueError, "PROOF_SNAPSHOT_NOT_PUBLISH"):
            record(self.cache, "ccgp", "SNAPSHOT_CONFIRMED")

    def test_error_code_does_not_reveal_transport_strings_or_secrets(self):
        event = record(self.cache, "ccgp", "STAGE_TERMINAL_FAILURE",
                       error_code="http://example.com?token=sensitive")
        self.assertEqual(event["error_code"], "ERROR_CODE_UNAVAILABLE")
        self.assertNotIn("sensitive", str(self.cache.values))

    def test_snapshot_receipt_needs_proven_sha_and_persisted_flag(self):
        digest = "a" * 64
        with self.assertRaisesRegex(ValueError, "PROOF_DURABLE_RECEIPT_REQUIRED"):
            record(self.cache, "publish", "SNAPSHOT_CONFIRMED",
                   snapshot_sha256=digest, snapshot_as_of=ANCHOR.isoformat())
        with self.assertRaisesRegex(ValueError, "PROOF_SNAPSHOT_HASH_INVALID"):
            record(self.cache, "publish", "SNAPSHOT_CONFIRMED",
                   snapshot_sha256="bad", durable_snapshot_persisted=True,
                   snapshot_as_of=ANCHOR.isoformat())
        stamp = record(self.cache, "publish", "SNAPSHOT_CONFIRMED",
                       snapshot_sha256=digest, snapshot_as_of=ANCHOR.isoformat(),
                       durable_snapshot_persisted=True)
        self.assertEqual(stamp["snapshot_sha256"], digest)
        self.assertNotIn("durable_snapshot_persisted", stamp)

    def test_cache_failure_is_never_success_or_publish_gate(self):
        class BrokenCache:
            def get(self, key):
                return None
            def set(self, key, value, opts):
                return None

        self.assertFalse(try_record(
            BrokenCache(), cycle_id=CYCLE, cycle_as_of=ANCHOR,
            stage="ccgp", event="TRIGGER_ACCEPTED", when=ANCHOR,
        ))
        result = audit_cycle(BrokenCache(), CYCLE, ("ccgp", "publish"), period="morning", anchor=ANCHOR)
        self.assertEqual(result["state"], "INCOMPLETE_OR_EXPIRED")
        self.assertFalse(result["trigger_recorded"])

    def test_cycle_acceptance_requires_trigger_delivery_and_all_stages(self):
        record(self.cache, "ccgp", "TRIGGER_ACCEPTED")
        record(self.cache, "ccgp", "STAGE_DELIVERED")
        record(self.cache, "ccgp", "STAGE_COMPLETED", failure_count=0, verified_count=4)
        result = audit_cycle(self.cache, CYCLE, ("ccgp", "publish"), period="morning", anchor=ANCHOR)
        self.assertEqual(result["state"], "INCOMPLETE_OR_EXPIRED")
        record(self.cache, "publish", "STAGE_DELIVERED")
        record(self.cache, "publish", "STAGE_COMPLETED")
        record(self.cache, "publish", "SNAPSHOT_CONFIRMED",
               snapshot_sha256="b"*64, snapshot_as_of=ANCHOR.isoformat(),
               durable_snapshot_persisted=True)
        result = audit_cycle(self.cache, CYCLE, ("ccgp", "publish"), period="morning", anchor=ANCHOR)
        self.assertEqual(result["state"], "PROOF_AVAILABLE")
        self.assertTrue(result["snapshot_readback_recorded"])

    def test_terminal_failure_does_not_overwrite_completion_but_vetoes_success(self):
        record(self.cache, "ccgp", "TRIGGER_ACCEPTED")
        record(self.cache, "ccgp", "STAGE_DELIVERED")
        record(self.cache, "ccgp", "STAGE_COMPLETED", failure_count=0)
        record(self.cache, "ccgp", "STAGE_TERMINAL_FAILURE", error_code="COLLECTOR_TEST_FAILED")
        out = audit_cycle(self.cache, CYCLE, ("ccgp", "publish"), period="morning", anchor=ANCHOR)
        self.assertEqual(out["state"], "RECORDED_FAILURE")
        self.assertEqual(out["failed_stages"], ["ccgp"])

    def test_witness_requires_every_prepublication_stage_and_never_raises_public_claims(self):
        record(self.cache, "ccgp", "TRIGGER_ACCEPTED")
        record(self.cache, "ccgp", "STAGE_DELIVERED")
        self.assertIsNone(snapshot_source_witness(
            self.cache, cycle_id=CYCLE, cycle_as_of=ANCHOR, completed_stages=["ccgp"],
        ))
        record(self.cache, "ccgp", "STAGE_COMPLETED", failure_count=0)
        witness = snapshot_source_witness(
            self.cache, cycle_id=CYCLE, cycle_as_of=ANCHOR, completed_stages=["ccgp"],
        )
        self.assertEqual(witness["witnessed_stage_count"], 1)
        self.assertEqual(witness["source_quality"], "NO_STAGE_FAILURES_REPORTED")
        self.assertEqual(len(witness["witness_sha256"]), 64)
        self.assertNotIn("official_source_covered", witness)

    def test_partial_source_completion_downgrades_witness(self):
        record(self.cache, "ccgp", "TRIGGER_ACCEPTED")
        record(self.cache, "ccgp", "STAGE_DELIVERED")
        record(self.cache, "ccgp", "STAGE_COMPLETED", failure_count=2)
        witness = snapshot_source_witness(
            self.cache, cycle_id=CYCLE, cycle_as_of=ANCHOR, completed_stages=["ccgp"],
        )
        self.assertEqual(witness["source_quality"], "PARTIAL_OR_UNREPORTED")

    def test_source_freshness_requires_snapshot_receipt_and_succeeds_only_when_clean(self):
        record(self.cache, "ccgp", "TRIGGER_ACCEPTED")
        record(self.cache, "tjmugh", "STAGE_DELIVERED")
        record(self.cache, "tjmugh", "STAGE_COMPLETED",
               when=ANCHOR+timedelta(minutes=9), failure_count=0)
        before = source_stage_freshness(
            self.cache, now=ANCHOR+timedelta(hours=4), source_stages=["tjmugh"],lookback_days=2,
        )
        self.assertEqual(before["tjmugh"]["status"], "UNKNOWN_NO_END_TO_END_PROOF")
        record(self.cache, "publish", "SNAPSHOT_CONFIRMED",
               snapshot_sha256="d"*64, snapshot_as_of=ANCHOR.isoformat(),
               durable_snapshot_persisted=True)
        after = source_stage_freshness(
            self.cache, now=ANCHOR+timedelta(hours=4), source_stages=["tjmugh"],lookback_days=2,
        )
        self.assertEqual(after["tjmugh"]["status"], "RECENT_STAGE_WITH_SNAPSHOT_RECEIPT")
        stale = source_stage_freshness(
            self.cache, now=ANCHOR+timedelta(hours=40), source_stages=["tjmugh"],lookback_days=3,
        )
        self.assertEqual(stale["tjmugh"]["status"], "STALE")

    def test_last7days_expected_cycles_does_not_invent_future_cycle(self):
        recent = recent_cycle_ids(ANCHOR, lookback_days=7)
        self.assertEqual(len(recent), 13)
        self.assertEqual(recent[0][0], CYCLE)
        self.assertEqual(recent[0][1], "morning")
        self.assertTrue(all(x[1] in {"morning", "noon"} for x in recent))

    def test_evidence_without_trigger_is_not_a_proven_cycle(self):
        record(self.cache, "ccgp", "STAGE_DELIVERED")
        record(self.cache, "ccgp", "STAGE_COMPLETED", failure_count=0)
        out = audit_cycle(self.cache, CYCLE, ("ccgp",), period="morning", anchor=ANCHOR)
        self.assertEqual(out["state"], "INCOMPLETE_OR_EXPIRED")
        self.assertFalse(out["trigger_recorded"])


class CollectorExecutionProofWiringTests(unittest.TestCase):
    def setUp(self):
        self.cache = MemoryCache()
        self.mid, self.as_of = scheduled_cycle(ANCHOR, "morning")

    def lease(self):
        self.cache.set(
            ACTIVE_CYCLE_KEY,
            {"cycle_id": self.mid, "cycle_as_of": self.as_of.isoformat()},
        )
        self.cache.set(
            META_KEY,
            {"cycle_id": self.mid, "cycle_as_of": self.as_of.isoformat(), "stages": {}},
        )

    def run_queue(self, *, status, result, stage="publish", lease=True):
        if lease:
            self.lease()
        payload = {
            "schema_version": "0.1",
            "schedule_version": "twice-daily-v1",
            "stage": stage,
            "cycle_id": self.mid,
            "cycle_as_of": self.as_of.isoformat(),
        }
        with (
            patch.object(queue, "RuntimeCache", return_value=self.cache),
            patch.object(queue.runtime, "run_stage", return_value=(status, result)),
            patch.object(queue.incremental_runtime, "clear_incremental_pending"),
            patch.object(queue, "datetime") as fake_clock,
        ):
            fake_clock.now.return_value = ANCHOR + timedelta(minutes=15)
            fake_clock.fromisoformat.side_effect = datetime.fromisoformat
            return asyncio.run(queue.process_collector_payload(payload))

    def test_real_queue_send_adds_trigger_proof_only_after_acceptance(self):
        with (
            patch.object(starter, "RuntimeCache", return_value=self.cache),
            patch.object(starter, "send", new_callable=AsyncMock, return_value="queue-accepted"),
            patch.object(starter, "datetime") as fake_clock,
        ):
            fake_clock.now.return_value = ANCHOR
            fake_clock.fromisoformat.side_effect = datetime.fromisoformat
            result = asyncio.run(starter._enqueue_start("VERCEL_CRON", "morning"))
        self.assertEqual(result[0], "queue-accepted")
        self.assertIsNotNone(read_event(self.cache, self.mid, "ccgp", "TRIGGER_ACCEPTED"))
        self.assertIsNotNone(read_event(self.cache, self.mid, "ccgp", "STAGE_ENQUEUED"))

    def test_failed_queue_send_does_not_claim_trigger_success(self):
        with (
            patch.object(starter, "RuntimeCache", return_value=self.cache),
            patch.object(starter, "send", new_callable=AsyncMock, side_effect=RuntimeError("QUEUE_DOWN")),
            patch.object(starter, "datetime") as fake_clock,
        ):
            fake_clock.now.return_value = ANCHOR
            fake_clock.fromisoformat.side_effect = datetime.fromisoformat
            with self.assertRaisesRegex(RuntimeError, "QUEUE_DOWN"):
                asyncio.run(starter._enqueue_start("VERCEL_CRON", "morning"))
        self.assertIsNone(read_event(self.cache, self.mid, "ccgp", "TRIGGER_ACCEPTED"))

    def test_unowned_queue_message_does_not_create_delivery_evidence(self):
        self.run_queue(
            status=200,
            result={"action": "COMPLETED"},
            stage="publish",
            lease=False,
        )
        self.assertIsNone(read_event(self.cache, self.mid, "publish", "STAGE_DELIVERED"))

    def test_terminal_failure_never_creates_successful_publish_receipt(self):
        self.run_queue(
            status=503,
            result={"action": "FAILED", "terminal": True, "error_code": "SOURCE_PARTIAL_FAILURE"},
        )
        self.assertIsNotNone(read_event(self.cache, self.mid, "publish", "STAGE_DELIVERED"))
        self.assertIsNotNone(read_event(self.cache, self.mid, "publish", "STAGE_TERMINAL_FAILURE"))
        self.assertIsNone(read_event(self.cache, self.mid, "publish", "SNAPSHOT_CONFIRMED"))

    def test_publish_completion_with_durable_receipt_records_confirmed_snapshot(self):
        self.run_queue(
            status=200,
            result={
                "action": "COMPLETED",
                "result": {
                    "durable_snapshot_persisted": True,
                    "sha256": "b" * 64,
                    "snapshot_as_of": ANCHOR.isoformat(),
                },
            },
        )
        self.assertIsNotNone(read_event(self.cache, self.mid, "publish", "STAGE_COMPLETED"))
        proof = read_event(self.cache, self.mid, "publish", "SNAPSHOT_CONFIRMED")
        self.assertEqual(proof["snapshot_sha256"], "b" * 64)

    def test_publish_completed_without_durable_receipt_is_not_confirmed(self):
        self.run_queue(
            status=200,
            result={"action": "COMPLETED", "result": {"snapshot_as_of": ANCHOR.isoformat()}},
        )
        self.assertIsNone(read_event(self.cache, self.mid, "publish", "SNAPSHOT_CONFIRMED"))


if __name__ == "__main__":
    unittest.main()
