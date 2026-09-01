from __future__ import annotations

import json
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class BackfillQueueExecutionTests(unittest.TestCase):
    def test_runtime_writes_only_isolated_backfill_keys(self) -> None:
        source = (WEB_ROOT / "backfill_runtime.py").read_text(encoding="utf-8")
        self.assertIn("medicalchannelai:backfill:v1:", source)
        self.assertNotIn("medicalchannelai:verified-snapshot:", source)
        self.assertNotIn("_cache_set(cache, CCGP_RECORDS_KEY", source)
        self.assertNotIn("_cache_set(cache, CCGP_EVENTS_KEY", source)

    def test_candidate_report_requires_manual_acceptance_and_never_publishes(self) -> None:
        source = (WEB_ROOT / "backfill_runtime.py").read_text(encoding="utf-8")
        self.assertIn('"publishes_public_snapshot": False', source)
        self.assertIn('"writes_daily_collector_state": False', source)
        self.assertIn('"writes_verified_snapshot_cache": False', source)
        self.assertIn('"manual_acceptance_required_before_any_promotion": True', source)

    def test_queue_batches_are_bounded_for_hobby_function_duration(self) -> None:
        source = (WEB_ROOT / "backfill_runtime.py").read_text(encoding="utf-8")
        self.assertIn("LOOKBACK_DAYS = 30", source)
        self.assertIn("CHUNK_DAYS = 7", source)
        self.assertIn("DETAIL_BATCH_SIZE = 8", source)
        self.assertIn("EVENT_BATCH_SIZE = 4", source)
        self.assertIn("MAX_CANDIDATES = 200", source)

    def test_queue_subscriber_and_vercel_trigger_match(self) -> None:
        subscriber = (WEB_ROOT / "api" / "backfill-queue.py").read_text(encoding="utf-8")
        config = json.loads((WEB_ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertIn('Topic[dict[str, object]]("medicalchannelai-backfill-v1")', subscriber)
        function = config["functions"]["api/backfill-queue.py"]
        trigger = function["experimentalTriggers"][0]
        self.assertEqual(trigger["type"], "queue/v2beta")
        self.assertEqual(trigger["topic"], "medicalchannelai-backfill-v1")
        self.assertEqual(function["maxDuration"], 300)

    def test_backfill_has_no_cron_and_cannot_modify_daily_schedule(self) -> None:
        config = json.loads((WEB_ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(config["crons"], [{"path": "/api/collector-run", "schedule": "20 0 * * *"}])


if __name__ == "__main__":
    unittest.main()
