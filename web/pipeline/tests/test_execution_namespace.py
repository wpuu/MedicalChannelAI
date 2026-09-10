from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


WEB_ROOT = Path(__file__).resolve().parents[2]
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

import collector_queue
import collector_runtime


class ExecutionNamespaceTests(unittest.TestCase):
    def test_runtime_namespace_assignment_covers_mutable_collector_keys(self) -> None:
        self.assertEqual(collector_runtime.LATEST_RUNTIME_SNAPSHOT_KEY, "medicalchannelai:verified-snapshot:latest:v1")
        self.assertEqual(collector_runtime.SNAPSHOT_HISTORY_KEY, "medicalchannelai:verified-snapshot:history:v2")
        self.assertEqual(collector_runtime.CANONICAL_RECORDS_KEY, "medicalchannelai:canonical-records:v2")
        self.assertEqual(collector_runtime.SOURCE_LEDGER_KEY, "medicalchannelai:source-ledger:v2")
        self.assertEqual(collector_runtime.INCREMENTAL_STAGING_KEY, "medicalchannelai:incremental-staging:v2")
        self.assertEqual(collector_runtime.INCREMENTAL_STATUS_KEY, "medicalchannelai:incremental-status:v2")
        self.assertEqual(collector_runtime.ACTIVE_CYCLE_KEY, "medicalchannelai:active-cycle:v2")
        self.assertEqual(collector_runtime.COMPLETED_CYCLE_KEY, "medicalchannelai:completed-cycle:v2")

    def test_collector_runtime_keys_are_all_v2(self) -> None:
        runtime_source = (WEB_ROOT / "collector_runtime.py").read_text(encoding="utf-8")
        queue_source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        for legacy_key in [
            "medicalchannelai:canonical-records:v1",
            "medicalchannelai:source-ledger:v1",
            "medicalchannelai:incremental-staging:v1",
            "medicalchannelai:incremental-status:v1",
            "medicalchannelai:active-cycle:v1",
            "medicalchannelai:completed-cycle:v1",
        ]:
            self.assertNotIn(legacy_key, runtime_source)
            self.assertNotIn(legacy_key, queue_source)

    def test_active_cycle_helpers_fail_closed(self) -> None:
        self.assertFalse(collector_queue._active_cycle_matches("", cycle_as_of=None))
        self.assertFalse(collector_queue._active_cycle_matches("cycle", cycle_as_of=None))
        self.assertFalse(collector_queue._active_cycle_matches("", cycle_as_of=datetime.now(timezone.utc)))

    def test_deep_message_with_matching_active_lease_may_run(self) -> None:
        cycle_id = "prod:2026-09-04"
        cycle_as_of = datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)
        with patch.object(
            collector_queue.runtime,
            "_cache_get_json",
            return_value={"cycle_id": cycle_id, "cycle_as_of": cycle_as_of.isoformat()},
        ):
            self.assertTrue(collector_queue._active_cycle_matches(cycle_id, cycle_as_of=cycle_as_of))

    def test_completed_cycle_duplicate_is_acknowledged_after_lease_release(self) -> None:
        cycle_id = "prod:2026-09-04"
        with patch.object(collector_queue.runtime, "_cache_get_json", return_value=None), patch.object(
            collector_queue.runtime,
            "_cache_get_text",
            return_value=cycle_id,
        ):
            self.assertEqual(
                collector_queue._deep_cycle_disposition(cycle_id, cycle_local_date="2026-09-04"),
                "COMPLETED_DUPLICATE",
            )

    def test_missing_lease_during_unfinished_same_day_cycle_remains_unsafe(self) -> None:
        cycle_id = "prod:2026-09-04"
        with patch.object(collector_queue.runtime, "_cache_get_json", return_value=None), patch.object(
            collector_queue.runtime,
            "_cache_get_text",
            return_value=None,
        ):
            self.assertEqual(
                collector_queue._deep_cycle_disposition(cycle_id, cycle_local_date="2026-09-04"),
                "UNSAFE_MISSING_LEASE",
            )

    def test_different_active_cycle_supersedes_old_queue_message(self) -> None:
        cycle_as_of = datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)
        with patch.object(
            collector_queue.runtime,
            "_cache_get_json",
            return_value={"cycle_id": "prod:2026-09-05", "cycle_as_of": cycle_as_of.isoformat()},
        ), patch.object(collector_queue.runtime, "_cache_get_text", return_value=None):
            self.assertEqual(
                collector_queue._deep_cycle_disposition("prod:2026-09-04", cycle_local_date="2026-09-04"),
                "SUPERSEDED",
            )

    def test_older_cycle_message_is_acknowledged_after_newer_cycle_supersedes_it(self) -> None:
        disposition = collector_queue._cycle_date_disposition(
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
        self.assertIn("return persistBundledRuntimeSnapshot(cache, bundledVerifiedSnapshot())", source)


if __name__ == "__main__":
    unittest.main()
