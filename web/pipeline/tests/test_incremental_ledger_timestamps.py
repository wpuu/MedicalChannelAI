from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))

from collector_incremental import (  # noqa: E402
    candidate_observation,
    empty_ledger,
    plan_detail_verification,
    record_verification_failure,
    record_verification_success,
)


NOW = datetime(2026, 9, 4, 1, 15, tzinfo=timezone.utc)
ROW = {
    "detail_url": "https://hospital.example/a",
    "title": "检验设备采购",
    "published_at": "2026-09-04",
    "index_url": "https://hospital.example/procurement",
    "notice_type": "采购公告",
}


class IncrementalLedgerTimestampTests(unittest.TestCase):
    def _discovered_ledger(self) -> tuple[dict, object]:
        plan = plan_detail_verification("tjmugh", [ROW], empty_ledger(), now=NOW)
        return plan.next_ledger, candidate_observation("tjmugh", ROW)

    def test_detail_failure_does_not_claim_candidate_was_seen_again_in_index(self) -> None:
        ledger, observation = self._discovered_ledger()
        failed = record_verification_failure(
            ledger,
            observation,
            "temporary detail fetch failure",
            failed_at=NOW + timedelta(hours=10),
        )
        entry = next(iter(failed["entries"].values()))
        self.assertEqual(entry["last_seen_at"], NOW.isoformat())
        self.assertEqual(entry["verification_status"], "FAILED")

    def test_detail_success_updates_verified_time_but_not_discovery_time(self) -> None:
        ledger, observation = self._discovered_ledger()
        verified_at = NOW + timedelta(hours=10)
        verified = record_verification_success(
            ledger,
            observation,
            verified_at=verified_at,
        )
        entry = next(iter(verified["entries"].values()))
        self.assertEqual(entry["last_seen_at"], NOW.isoformat())
        self.assertEqual(entry["last_verified_at"], verified_at.isoformat())
        self.assertEqual(entry["verification_status"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
