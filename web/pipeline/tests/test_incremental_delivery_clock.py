from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))

from collector_incremental_ticks import first_tick_after_deep, next_tick_after  # noqa: E402


class IncrementalDeliveryClockTests(unittest.TestCase):
    def test_source_payload_clock_is_only_bucket_identity_not_verification_clock(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        start = source.index("def _process_incremental_payload")
        end = source.index("async def _process_incremental_tick_payload", start)
        block = source[start:end]

        self.assertIn("delivered_at = datetime.now(timezone.utc)", block)
        self.assertIn("same_china_business_date(observed_at, delivered_at)", block)
        self.assertIn("scan_bucket_id(source_id, now=observed_at)", block)
        self.assertIn("bootstrap_incremental_ledger_from_canonical(\n            source_id,\n            now=delivered_at,", block)
        self.assertIn("run_incremental_source(\n            source_id,\n            now=delivered_at,", block)
        self.assertNotIn("run_incremental_source(\n            source_id,\n            now=observed_at,", block)

    def test_cross_day_guard_runs_before_any_incremental_lease_or_official_fetch_path(self) -> None:
        source = (WEB_ROOT / "collector_queue.py").read_text(encoding="utf-8")
        start = source.index("def _process_incremental_payload")
        end = source.index("async def _process_incremental_tick_payload", start)
        block = source[start:end]

        guard = block.index("if not same_china_business_date(observed_at, delivered_at):")
        lease = block.index("_acquire_incremental_lease(")
        bootstrap = block.index("bootstrap_incremental_ledger_from_canonical(")
        runtime = block.index("incremental_runtime.run_incremental_source(")
        self.assertLess(guard, lease)
        self.assertLess(lease, bootstrap)
        self.assertLess(bootstrap, runtime)

    def test_materially_late_tick_on_aligned_boundary_schedules_strictly_after_delivery(self) -> None:
        first = first_tick_after_deep(datetime(2026, 9, 4, 3, 5, tzinfo=timezone.utc))
        self.assertIsNotNone(first)
        # The 11:30 China tick arrives very late at 12:10. With the 15-minute
        # cadence, the next aligned slot strictly after delivery is 12:15.
        delivered = datetime(2026, 9, 4, 4, 10, tzinfo=timezone.utc)
        nxt = next_tick_after(first, delivered_at=delivered)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.scheduled_for, "2026-09-04T04:15:00+00:00")


if __name__ == "__main__":
    unittest.main()
