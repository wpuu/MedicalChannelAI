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

    def test_worker_checks_active_cycle_before_running_stage(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        first_fence = source.index("if not _active_cycle_matches(cycle_id):")
        run_stage = source.index("runtime.run_stage(stage, now=cycle_as_of)")
        self.assertLess(first_fence, run_stage)
        self.assertGreaterEqual(source.count("if not _active_cycle_matches(cycle_id):"), 2)

    def test_queue_consumer_serializes_all_mutating_messages(self) -> None:
        source = (WEB_ROOT / "api" / "collector-queue.py").read_text(encoding="utf-8")
        self.assertIn("max_concurrency=1", source)
        self.assertIn('Topic[dict[str, object]]("medicalchannelai-refresh-v2")', source)

    def test_snapshot_reader_migrates_v1_only_into_v2(self) -> None:
        source = (WEB_ROOT / "api" / "_verifiedSnapshot.js").read_text(encoding="utf-8")
        self.assertIn("medicalchannelai:verified-snapshot:latest:v2", source)
        self.assertIn("medicalchannelai:verified-snapshot:latest:v1", source)
        self.assertLess(source.index("LATEST_RUNTIME_SNAPSHOT_KEY"), source.index("LEGACY_RUNTIME_SNAPSHOT_KEY"))
        self.assertIn("persistRuntimeSnapshot(cache, verifiedLegacy)", source)


if __name__ == "__main__":
    unittest.main()
