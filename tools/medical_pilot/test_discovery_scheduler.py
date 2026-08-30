from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from .discovery_runtime import DiscoveryRunResult
from .discovery_scheduler import (
    SQLiteDiscoveryScheduleLedger,
    due_discovery_slot,
    run_due_discovery_tick,
)


MONDAY_1003 = datetime(2026, 8, 31, 2, 3, tzinfo=timezone.utc)  # 10:03 Asia/Shanghai
MONDAY_1011 = datetime(2026, 8, 31, 2, 11, tzinfo=timezone.utc)  # 10:11 Asia/Shanghai
SUNDAY_0734 = datetime(2026, 8, 29, 23, 34, tzinfo=timezone.utc)  # 2026-08-30 07:34 local
SUNDAY_0742 = datetime(2026, 8, 29, 23, 42, tzinfo=timezone.utc)  # 2026-08-30 07:42 local


def success_result(source_id: str) -> DiscoveryRunResult:
    return DiscoveryRunResult(
        source_id=source_id,
        listing_url=f"https://example.invalid/{source_id}",
        discovered_count=0,
        due_count=0,
        attempted_count=0,
        persisted_count=0,
        failed_count=0,
        skipped_not_due_count=0,
        errors=(),
    )


class DiscoverySchedulerTests(unittest.TestCase):
    def test_regular_slots_use_existing_source_offsets(self) -> None:
        total = due_discovery_slot("tjmugh_procurement", now=MONDAY_1003)
        first = due_discovery_slot("tj_first_central_hospital_procurement", now=MONDAY_1011)
        self.assertIsNotNone(total)
        self.assertIsNotNone(first)
        assert total is not None
        assert first is not None
        self.assertEqual(total.kind, "REGULAR")
        self.assertEqual(first.kind, "REGULAR")
        self.assertEqual(total.interval_minutes, 15)
        self.assertEqual(first.interval_minutes, 15)
        self.assertIsNone(due_discovery_slot("tjmugh_procurement", now=MONDAY_1011))

    def test_not_ready_source_never_receives_a_slot(self) -> None:
        self.assertIsNone(due_discovery_slot("ccgp_local_notices", now=MONDAY_1003))
        self.assertIsNone(due_discovery_slot("tj_government_procurement", now=MONDAY_1003))

    def test_forced_refresh_uses_stable_source_minute_inside_window(self) -> None:
        total = due_discovery_slot("tjmugh_procurement", now=SUNDAY_0734)
        first = due_discovery_slot("tj_first_central_hospital_procurement", now=SUNDAY_0742)
        self.assertIsNotNone(total)
        self.assertIsNotNone(first)
        assert total is not None
        assert first is not None
        self.assertEqual(total.kind, "FORCED_REFRESH")
        self.assertEqual(first.kind, "FORCED_REFRESH")
        self.assertIn("07:31-07:43", total.slot_id)
        self.assertIn("07:31-07:43", first.slot_id)

    def test_same_slot_is_claimed_only_once_even_after_runtime_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "pilot.sqlite"
            calls: list[str] = []

            def runner(source_id: str, *, db_path: Path, now: datetime) -> DiscoveryRunResult:
                self.assertEqual(db_path, db)
                calls.append(source_id)
                return success_result(source_id)

            first = run_due_discovery_tick(db_path=db, now=MONDAY_1003, run_source=runner)
            second = run_due_discovery_tick(db_path=db, now=MONDAY_1003, run_source=runner)

            self.assertEqual(first.claimed_sources, ("tjmugh_procurement",))
            self.assertEqual(second.duplicate_claim_sources, ("tjmugh_procurement",))
            self.assertEqual(calls, ["tjmugh_procurement"])

            reopened = SQLiteDiscoveryScheduleLedger(db)
            self.assertEqual(reopened.consecutive_failures("tjmugh_procurement"), 0)

    def test_source_failure_widens_regular_cadence_and_success_resets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "pilot.sqlite"
            calls = 0

            def failing(source_id: str, *, db_path: Path, now: datetime) -> DiscoveryRunResult:
                nonlocal calls
                calls += 1
                raise RuntimeError("listing unavailable")

            failed = run_due_discovery_tick(db_path=db, now=MONDAY_1003, run_source=failing)
            self.assertEqual(failed.failed_sources[0]["source_id"], "tjmugh_procurement")
            ledger = SQLiteDiscoveryScheduleLedger(db)
            self.assertEqual(ledger.consecutive_failures("tjmugh_procurement"), 1)

            # One source-level failure changes the 15-minute EARLY_SIGNAL cadence to 30.
            self.assertIsNone(
                due_discovery_slot(
                    "tjmugh_procurement",
                    now=MONDAY_1003 + timedelta(minutes=15),
                    consecutive_failures=1,
                )
            )
            self.assertIsNotNone(
                due_discovery_slot(
                    "tjmugh_procurement",
                    now=MONDAY_1003 + timedelta(minutes=30),
                    consecutive_failures=1,
                )
            )

            def succeeding(source_id: str, *, db_path: Path, now: datetime) -> DiscoveryRunResult:
                return success_result(source_id)

            recovered = run_due_discovery_tick(
                db_path=db,
                now=MONDAY_1003 + timedelta(minutes=30),
                run_source=succeeding,
            )
            self.assertEqual(recovered.succeeded_sources, ("tjmugh_procurement",))
            self.assertEqual(ledger.consecutive_failures("tjmugh_procurement"), 0)
            self.assertEqual(calls, 1)

    def test_tick_does_not_call_other_ready_source_when_its_minute_is_not_due(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "pilot.sqlite"
            calls: list[str] = []

            def runner(source_id: str, *, db_path: Path, now: datetime) -> DiscoveryRunResult:
                calls.append(source_id)
                return success_result(source_id)

            result = run_due_discovery_tick(db_path=db, now=MONDAY_1011, run_source=runner)
            self.assertEqual(result.due_sources, ("tj_first_central_hospital_procurement",))
            self.assertEqual(calls, ["tj_first_central_hospital_procurement"])


if __name__ == "__main__":
    unittest.main()
