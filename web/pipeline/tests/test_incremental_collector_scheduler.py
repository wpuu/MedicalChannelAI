from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))

from collector_incremental import scan_bucket_id  # noqa: E402
from collector_incremental_scheduler import (  # noqa: E402
    SCHEDULED_INCREMENTAL_SOURCES,
    choose_due_incremental_source,
)


NOW = datetime(2026, 9, 4, 6, 20, tzinfo=timezone.utc)


class FakeCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value: object, options: object | None = None) -> None:
        self.values[key] = value

    def set_completed(self, source_id: str, when: datetime) -> None:
        self.values[f"medicalchannelai:collector-incremental-bucket:{source_id}:v2"] = {
            "schema_version": "0.1",
            "source_id": source_id,
            "bucket_id": scan_bucket_id(source_id, now=when),
            "completed_at": when.isoformat(),
            "result": {},
        }


class IncrementalCollectorSchedulerTests(unittest.TestCase):
    def test_scheduler_never_includes_ccgp_until_event_semantics_are_ready(self) -> None:
        self.assertNotIn("ccgp", SCHEDULED_INCREMENTAL_SOURCES)
        self.assertEqual(
            SCHEDULED_INCREMENTAL_SOURCES,
            ("tjmugh", "tjnothop", "tjfch", "tjfch_test", "teda"),
        )

    def test_first_activation_releases_only_one_never_scanned_source(self) -> None:
        cache = FakeCache()
        decision = choose_due_incremental_source(cache, now=NOW)
        self.assertEqual(decision.source_id, "tjmugh")
        self.assertEqual(decision.reason, "SOURCE_DUE")
        self.assertEqual(len(decision.due_sources), len(SCHEDULED_INCREMENTAL_SOURCES))

    def test_never_scanned_sources_are_bootstrapped_fairly_across_ticks(self) -> None:
        cache = FakeCache()
        first = choose_due_incremental_source(cache, now=NOW)
        second = choose_due_incremental_source(cache, now=NOW + timedelta(minutes=10))
        third = choose_due_incremental_source(cache, now=NOW + timedelta(minutes=20))
        self.assertEqual(first.source_id, "tjmugh")
        self.assertEqual(second.source_id, "tjnothop")
        self.assertEqual(third.source_id, "tjfch")

    def test_failed_never_completed_source_backs_off_instead_of_starving_others(self) -> None:
        cache = FakeCache()
        first = choose_due_incremental_source(cache, now=NOW)
        self.assertEqual(first.source_id, "tjmugh")
        # Simulate a discovery/detail failure: no completed bucket is written.
        # The next scheduler tick must still advance to another source.
        second = choose_due_incremental_source(cache, now=NOW + timedelta(minutes=10))
        self.assertEqual(second.source_id, "tjnothop")
        self.assertNotIn("tjmugh", second.due_sources)

    def test_no_source_is_queued_before_its_interval_is_due(self) -> None:
        cache = FakeCache()
        for source in SCHEDULED_INCREMENTAL_SOURCES:
            cache.set_completed(source, NOW)
        decision = choose_due_incremental_source(cache, now=NOW + timedelta(minutes=30))
        self.assertIsNone(decision.source_id)
        self.assertEqual(decision.reason, "NO_SOURCE_DUE")
        self.assertIsNotNone(decision.next_due_at)

    def test_most_overdue_source_wins_but_only_one_is_selected(self) -> None:
        cache = FakeCache()
        for source in SCHEDULED_INCREMENTAL_SOURCES:
            cache.set_completed(source, NOW)
        decision = choose_due_incremental_source(cache, now=NOW + timedelta(minutes=181))
        self.assertEqual(decision.source_id, "tjmugh")
        self.assertGreater(len(decision.due_sources), 1)

    def test_recent_failed_attempt_on_completed_source_does_not_repeat_every_tick(self) -> None:
        cache = FakeCache()
        for source in SCHEDULED_INCREMENTAL_SOURCES:
            cache.set_completed(source, NOW)
        first = choose_due_incremental_source(cache, now=NOW + timedelta(minutes=181))
        self.assertEqual(first.source_id, "tjmugh")
        # No new completion is recorded for tjmugh, representing a failed scan.
        second = choose_due_incremental_source(cache, now=NOW + timedelta(minutes=191))
        self.assertNotEqual(second.source_id, "tjmugh")

    def test_current_bucket_is_not_requeued_even_if_completed_at_is_malformed_old(self) -> None:
        cache = FakeCache()
        cache.set_completed("tjmugh", NOW)
        key = "medicalchannelai:collector-incremental-bucket:tjmugh:v2"
        row = dict(cache.values[key])
        row["completed_at"] = (NOW - timedelta(days=1)).isoformat()
        cache.values[key] = row
        # Same 60-minute bucket: bucket idempotency wins over an inconsistent old
        # completion timestamp, avoiding duplicate queue work in the same bucket.
        decision = choose_due_incremental_source(cache, now=NOW + timedelta(minutes=20))
        self.assertNotEqual(decision.source_id, "tjmugh")

    def test_trigger_supports_auto_selection_without_activating_cron(self) -> None:
        source = (WEB_ROOT / "api" / "collector-run.py").read_text(encoding="utf-8")
        self.assertIn("choose_due_incremental_source(RuntimeCache())", source)
        self.assertIn('requested_source == "auto"', source)
        self.assertIn('"action": "NO_SOURCE_DUE"', source)
        self.assertIn('"mode": "INCREMENTAL_AUTO"', source)


if __name__ == "__main__":
    unittest.main()
