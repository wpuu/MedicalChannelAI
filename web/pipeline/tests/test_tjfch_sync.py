from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / "scripts" / "sync_tjfch_procurement.py"

spec = importlib.util.spec_from_file_location("sync_tjfch_procurement", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("SYNC_TJFCH_IMPORT_FAILED")
sync_tjfch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_tjfch)


class TjfchSyncTests(unittest.TestCase):
    def test_publish_gate_blocks_index_discovery_failure(self) -> None:
        allowed, reason = sync_tjfch.publish_gate(
            index_discovery_succeeded=False,
            selected_candidate_count=0,
            new_verified_record_count=0,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "INDEX_DISCOVERY_FAILED")

    def test_publish_gate_allows_successful_empty_window(self) -> None:
        allowed, reason = sync_tjfch.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=0,
            new_verified_record_count=0,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "PASS")

    def test_publish_gate_blocks_when_all_selected_details_fail(self) -> None:
        allowed, reason = sync_tjfch.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=2,
            new_verified_record_count=0,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "ALL_SELECTED_DETAILS_FAILED_VERIFICATION")

    def test_publish_gate_allows_partial_verified_details(self) -> None:
        allowed, reason = sync_tjfch.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=3,
            new_verified_record_count=1,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "PASS")

    def test_default_detail_delay_is_not_below_three_seconds(self) -> None:
        self.assertGreaterEqual(sync_tjfch.MIN_DETAIL_DELAY_SECONDS, 3.0)

    def test_parse_as_of_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            sync_tjfch.parse_as_of("2026-09-03T09:00:00")


if __name__ == "__main__":
    unittest.main()
