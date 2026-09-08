from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))

from collector_namespace import (  # noqa: E402
    ACTIVE_CYCLE_KEY,
    CCGP_EVENTS_KEY,
    CCGP_RECORDS_KEY,
    CCGP_WATCH_KEY,
    INCREMENTAL_ACTIVE_KEY,
    INCREMENTAL_CHAIN_KEY,
    LATEST_RUNTIME_SNAPSHOT_KEY,
    META_KEY,
    QUEUE_TOPIC_NAME,
    TEDA_RECORDS_KEY,
    TJFCH_RECORDS_KEY,
    TJMUGH_RECORDS_KEY,
    TJNOTHOP_RECORDS_KEY,
    active_cycle_id,
    active_incremental_id,
    apply_runtime_namespace,
    cycle_has_running_stage,
    deep_message_lease_disposition,
)


class ExecutionNamespaceTests(unittest.TestCase):
    def test_collector_runtime_keys_are_all_v2(self) -> None:
        keys = [
            META_KEY,
            ACTIVE_CYCLE_KEY,
            INCREMENTAL_ACTIVE_KEY,
            INCREMENTAL_CHAIN_KEY,
            CCGP_RECORDS_KEY,
            CCGP_EVENTS_KEY,
            CCGP_WATCH_KEY,
            TJMUGH_RECORDS_KEY,
            TJNOTHOP_RECORDS_KEY,
            TEDA_RECORDS_KEY,
            TJFCH_RECORDS_KEY,
            LATEST_RUNTIME_SNAPSHOT_KEY,
        ]
        self.assertTrue(all(value.endswith(":v2") for value in keys))
        self.assertEqual(QUEUE_TOPIC_NAME, "medicalchannelai-refresh-v2")

    def test_runtime_namespace_assignment_covers_mutable_collector_keys(self) -> None:
        runtime = SimpleNamespace()
        apply_runtime_namespace(runtime)
        self.assertEqual(runtime.META_KEY, META_KEY)
        self.assertEqual(runtime.CCGP_RECORDS_KEY, CCGP_RECORDS_KEY)
        self.assertEqual(runtime.CCGP_EVENTS_KEY, CCGP_EVENTS_KEY)
        self.assertEqual(runtime.CCGP_WATCH_KEY, CCGP_WATCH_KEY)
        self.assertEqual(runtime.TJMUGH_RECORDS_KEY, TJMUGH_RECORDS_KEY)
        self.assertEqual(runtime.TJNOTHOP_RECORDS_KEY, TJNOTHOP_RECORDS_KEY)
        self.assertEqual(runtime.TEDA_RECORDS_KEY, TEDA_RECORDS_KEY)
        self.assertEqual(runtime.TJFCH_RECORDS_KEY, TJFCH_RECORDS_KEY)
        self.assertEqual(runtime.LATEST_RUNTIME_SNAPSHOT_KEY, LATEST_RUNTIME_SNAPSHOT_KEY)

    def test_active_cycle_helpers_fail_closed(self) -> None:
        self.assertIsNone(active_cycle_id(None))
        self.assertIsNone(active_cycle_id({"cycle_id": ""}))
        self.assertEqual(active_cycle_id({"cycle_id": "prod:2026-09-01"}), "prod:2026-09-01")
        self.assertIsNone(active_incremental_id(None))
        self.assertIsNone(active_incremental_id({"scan_id": ""}))
        self.assertEqual(
            active_incremental_id({"scan_id": "scan:tjmugh:20260904T0100Z:60m:run"}),
            "scan:tjmugh:20260904T0100Z:60m:run",
        )
        self.assertFalse(cycle_has_running_stage({"stages": {"ccgp": {"status": "FAILED"}}}))
        self.assertTrue(cycle_has_running_stage({"stages": {"ccgp": {"status": "RUNNING"}}}))

    def test_deep_message_with_matching_active_lease_may_run(self) -> None:
        disposition = deep_message_lease_disposition(
            {"cycle_id": "prod:2026-09-04"},
            {},
            cycle_id="prod:2026-09-04",
            cycle_local_date="2026-09-04",
            current_local_date="2026-09-04",
        )
        self.assertEqual(disposition, "MATCH")

    def test_completed_cycle_duplicate_is_acknowledged_after_lease_release(self) -> None:
        disposition = deep_message_lease_disposition(
            None,
            {
                "local_date": "2026-09-04",
                "stages": {"publish": {"status": "COMPLETED"}},
            },
            cycle_id="prod:2026-09-04",
            cycle_local_date="2026-09-04",
            current_local_date="2026-09-04",
        )
        self.assertEqual(disposition, "COMPLETED_CYCLE")

    def test_missing_lease_during_unfinished_same_day_cycle_remains_unsafe(self) -> None:
        disposition = deep_message_lease_disposition(
            None,
            {
                "local_date": "2026-09-04",
                "stages": {
                    "ccgp": {"status": "COMPLETED"},
                    "event1": {"status": "RUNNING"},
                },
            },
            cycle_id="prod:2026-09-04",
            cycle_local_date="2026-09-04",
            current_local_date="2026-09-04",
        )
        self.assertEqual(disposition, "MISSING_UNSAFE")

    def test_older_cycle_message_is_acknowledged_after_newer_cycle_supersedes_it(self) -> None:
        disposition = deep_message_lease_disposition(
            None,
            {"local_date": "2026-09-05", "stages": {}},
            cycle_id="prod:2026-09-04",
            cycle_local_date="2026-09-04",
            current_local_date="2026-09-05",
        )
        self.assertIn(disposition, {"EXPIRED_STALE", "SUPERSEDED"})

    def test_different_active_cycle_supersedes_old_queue_message(self) -> None:
        disposition = deep_message_lease_disposition(
            {"cycle_id": "prod:2026-09-05"},
            {"local_date": "2026-09-05", "stages": {}},
            cycle_id="prod:2026-09-04",
            cycle_local_date="2026-09-04",
            current_local_date="2026-09-05",
        )
        self.assertEqual(disposition, "SUPERSEDED")

    def test_worker_checks_active_cycle_before_running_stage(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        first_fence = source.index("if not _active_cycle_matches(cycle_id, cycle_as_of=cycle_as_of):")
        run_stage = source.index("runtime.run_stage(stage, now=cycle_as_of)")
        self.assertLess(first_fence, run_stage)
        self.assertGreaterEqual(
            source.count("if not _active_cycle_matches(cycle_id, cycle_as_of=cycle_as_of):"),
            2,
        )

    def test_queue_consumer_serializes_all_mutating_messages(self) -> None:
        source = (WEB_ROOT / "api" / "collector-queue.py").read_text(encoding="utf-8")
        self.assertIn("max_concurrency=1", source)
        self.assertIn('Topic[dict[str, object]]("medicalchannelai-refresh-v2")', source)

    def test_snapshot_reader_scopes_runtime_cache_to_bundled_data_revision(self) -> None:
        source = (WEB_ROOT / "api" / "_verifiedSnapshot.js").read_text(encoding="utf-8")
        self.assertIn("BUNDLED_SNAPSHOT_REVISION", source)
        self.assertIn("medicalchannelai:verified-snapshot:${BUNDLED_SNAPSHOT_REVISION}:v3", source)
        self.assertNotIn("medicalchannelai:verified-snapshot:latest:v2", source)
        self.assertNotIn("medicalchannelai:verified-snapshot:latest:v1", source)
        self.assertNotIn("persistRuntimeSnapshot(cache, verifiedLegacy)", source)
        self.assertIn("return persistRuntimeSnapshot(cache, bundledVerifiedSnapshot())", source)


if __name__ == "__main__":
    unittest.main()
