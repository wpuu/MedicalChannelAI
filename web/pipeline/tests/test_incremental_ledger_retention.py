from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))

from collector_incremental import (  # noqa: E402
    LEDGER_ENTRY_RETENTION_DAYS,
    empty_ledger,
    plan_detail_verification,
    record_verification_success,
)


NOW = datetime(2026, 9, 4, 1, 15, tzinfo=timezone.utc)


def candidate(url: str, published_at: str) -> dict:
    return {
        "detail_url": url,
        "title": "检验设备采购",
        "published_at": published_at,
        "index_url": "https://hospital.example/procurement",
        "notice_type": "采购公告",
    }


class IncrementalLedgerRetentionTests(unittest.TestCase):
    def test_old_entries_are_pruned_individually_even_while_ledger_key_stays_hot(self) -> None:
        old_seen = NOW - timedelta(days=LEDGER_ENTRY_RETENTION_DAYS + 5)
        recent_seen = NOW - timedelta(days=10)

        old_plan = plan_detail_verification(
            "tjmugh",
            [candidate("https://hospital.example/old", "2026-07-16")],
            empty_ledger(),
            now=old_seen,
        )
        ledger = record_verification_success(
            old_plan.next_ledger,
            old_plan.selected[0].candidate,
            verified_at=old_seen,
        )

        recent_plan = plan_detail_verification(
            "tjmugh",
            [candidate("https://hospital.example/recent", "2026-08-25")],
            ledger,
            now=recent_seen,
        )
        ledger = record_verification_success(
            recent_plan.next_ledger,
            recent_plan.selected[0].candidate,
            verified_at=recent_seen,
        )

        current = plan_detail_verification("tjmugh", [], ledger, now=NOW)
        urls = {
            row["detail_url"]
            for row in current.next_ledger["entries"].values()
        }
        self.assertNotIn("https://hospital.example/old", urls)
        self.assertIn("https://hospital.example/recent", urls)
        self.assertEqual(len(urls), 1)

    def test_candidate_reappearing_after_retention_is_treated_as_new(self) -> None:
        first_seen = NOW - timedelta(days=LEDGER_ENTRY_RETENTION_DAYS + 1)
        row = candidate("https://hospital.example/reappeared", "2026-07-20")
        first = plan_detail_verification("tjmugh", [row], empty_ledger(), now=first_seen)
        ledger = record_verification_success(
            first.next_ledger,
            first.selected[0].candidate,
            verified_at=first_seen,
        )

        again = plan_detail_verification("tjmugh", [row], ledger, now=NOW)
        self.assertEqual(len(again.selected), 1)
        self.assertEqual(again.selected[0].reason, "NEW_CANDIDATE")


if __name__ == "__main__":
    unittest.main()
