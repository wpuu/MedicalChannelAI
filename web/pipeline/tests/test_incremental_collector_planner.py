from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WEB_ROOT))

from collector_incremental import (  # noqa: E402
    SOURCE_POLICIES,
    candidate_observation,
    empty_ledger,
    plan_detail_verification,
    record_verification_failure,
    record_verification_success,
    scan_bucket_id,
)


NOW = datetime(2026, 9, 4, 1, 15, tzinfo=timezone.utc)


def candidate(url: str, *, title: str = "检验设备采购", published_at: str = "2026-09-04") -> dict:
    return {
        "detail_url": url,
        "title": title,
        "published_at": published_at,
        "index_url": "https://hospital.example/procurement",
        "notice_type": "采购公告",
    }


class IncrementalCollectorPlannerTests(unittest.TestCase):
    def test_new_candidate_requires_detail_verification(self) -> None:
        plan = plan_detail_verification(
            "tjmugh",
            [candidate("https://hospital.example/a")],
            empty_ledger(),
            now=NOW,
        )
        self.assertEqual(len(plan.selected), 1)
        self.assertEqual(plan.selected[0].reason, "NEW_CANDIDATE")
        self.assertEqual(len(plan.skipped_unchanged), 0)

    def test_verified_unchanged_candidate_is_skipped_until_reverify_due(self) -> None:
        row = candidate("https://hospital.example/a")
        observation = candidate_observation("tjmugh", row)
        ledger = record_verification_success(empty_ledger(), observation, verified_at=NOW)
        plan = plan_detail_verification(
            "tjmugh",
            [row],
            ledger,
            now=NOW + timedelta(hours=1),
        )
        self.assertEqual(plan.selected, ())
        self.assertEqual(len(plan.skipped_unchanged), 1)

    def test_metadata_change_forces_reverification_but_does_not_become_verified_fact(self) -> None:
        original = candidate("https://hospital.example/a", title="设备采购公告")
        observation = candidate_observation("tjmugh", original)
        ledger = record_verification_success(empty_ledger(), observation, verified_at=NOW)
        changed = candidate("https://hospital.example/a", title="设备采购公告（更新）")
        plan = plan_detail_verification(
            "tjmugh",
            [changed],
            ledger,
            now=NOW + timedelta(hours=1),
        )
        self.assertEqual(plan.selected[0].reason, "DISCOVERY_METADATA_CHANGED")
        entry = next(iter(plan.next_ledger["entries"].values()))
        self.assertEqual(entry["verification_status"], "VERIFIED")
        self.assertNotEqual(entry["fingerprint"], entry["last_verification_fingerprint"])

    def test_periodic_reverify_catches_same_url_detail_changes_hidden_from_index(self) -> None:
        row = candidate("https://hospital.example/a")
        observation = candidate_observation("tjmugh", row)
        ledger = record_verification_success(empty_ledger(), observation, verified_at=NOW)
        plan = plan_detail_verification(
            "tjmugh",
            [row],
            ledger,
            now=NOW + timedelta(hours=25),
        )
        self.assertEqual(plan.selected[0].reason, "PERIODIC_REVERIFY_DUE")

    def test_new_and_changed_candidates_win_detail_budget_before_periodic_rechecks(self) -> None:
        stale = candidate("https://hospital.example/stale", title="旧项目")
        changed_old = candidate("https://hospital.example/changed", title="原标题")
        ledger = empty_ledger()
        ledger = record_verification_success(
            ledger,
            candidate_observation("tjmugh", stale),
            verified_at=NOW - timedelta(hours=30),
        )
        ledger = record_verification_success(
            ledger,
            candidate_observation("tjmugh", changed_old),
            verified_at=NOW - timedelta(hours=2),
        )
        plan = plan_detail_verification(
            "tjmugh",
            [
                stale,
                candidate("https://hospital.example/changed", title="新标题"),
                candidate("https://hospital.example/new", title="全新项目"),
            ],
            ledger,
            now=NOW,
            max_details=2,
        )
        self.assertEqual(
            [item.reason for item in plan.selected],
            ["NEW_CANDIDATE", "DISCOVERY_METADATA_CHANGED"],
        )
        self.assertEqual([item.reason for item in plan.deferred], ["PERIODIC_REVERIFY_DUE"])

    def test_detail_budget_prioritizes_newest_candidate_within_same_priority(self) -> None:
        plan = plan_detail_verification(
            "tjmugh",
            [
                candidate("https://hospital.example/old", published_at="2026-09-02"),
                candidate("https://hospital.example/newest", published_at="2026-09-04"),
                candidate("https://hospital.example/middle", published_at="2026-09-03"),
            ],
            empty_ledger(),
            now=NOW,
            max_details=2,
        )
        self.assertEqual(
            [item.candidate.detail_url for item in plan.selected],
            ["https://hospital.example/newest", "https://hospital.example/middle"],
        )
        self.assertEqual(
            [item.candidate.detail_url for item in plan.deferred],
            ["https://hospital.example/old"],
        )

    def test_failure_is_retried_even_when_index_metadata_is_unchanged(self) -> None:
        row = candidate("https://hospital.example/a")
        observation = candidate_observation("tjmugh", row)
        ledger = record_verification_failure(
            empty_ledger(),
            observation,
            "temporary fetch failure",
            failed_at=NOW,
        )
        plan = plan_detail_verification(
            "tjmugh",
            [row],
            ledger,
            now=NOW + timedelta(hours=1),
        )
        self.assertEqual(plan.selected[0].reason, "NOT_CURRENTLY_VERIFIED")

    def test_duplicate_candidate_url_is_verified_once_per_scan(self) -> None:
        row = candidate("https://hospital.example/a")
        plan = plan_detail_verification("tjmugh", [row, row], empty_ledger(), now=NOW)
        self.assertEqual(len(plan.selected), 1)

    def test_bucket_id_is_idempotent_inside_same_scan_interval(self) -> None:
        first = scan_bucket_id("tjmugh", now=NOW, interval_minutes=60)
        second = scan_bucket_id(
            "tjmugh",
            now=NOW + timedelta(minutes=40),
            interval_minutes=60,
        )
        third = scan_bucket_id(
            "tjmugh",
            now=NOW + timedelta(minutes=50),
            interval_minutes=60,
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_current_planning_policy_does_not_enable_hourly_full_detail_scrapes(self) -> None:
        self.assertEqual(SOURCE_POLICIES["tjmugh"]["scan_interval_minutes"], 60)
        self.assertEqual(SOURCE_POLICIES["tjmugh"]["reverify_after_hours"], 24)
        self.assertEqual(SOURCE_POLICIES["ccgp"]["scan_interval_minutes"], 180)
        self.assertGreaterEqual(SOURCE_POLICIES["ccgp"]["reverify_after_hours"], 24)


if __name__ == "__main__":
    unittest.main()
