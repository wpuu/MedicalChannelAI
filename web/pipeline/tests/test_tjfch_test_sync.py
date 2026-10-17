from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / "scripts" / "sync_tjfch_test_recruitment.py"

spec = importlib.util.spec_from_file_location("sync_tjfch_test_recruitment", SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("SYNC_TJFCH_TEST_IMPORT_FAILED")
sync_tjfch_test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_tjfch_test)


class TjfchTestSyncTests(unittest.TestCase):
    def test_default_detail_delay_is_not_below_three_seconds(self) -> None:
        self.assertGreaterEqual(sync_tjfch_test.MIN_DETAIL_DELAY_SECONDS, 3.0)

    def test_only_relative_window_format_limitation_is_explicitly_unsupported(self) -> None:
        self.assertEqual(
            sync_tjfch_test.UNSUPPORTED_DETAIL_CODES,
            {"TJFCH_TEST_REGISTRATION_WINDOW_UNSUPPORTED"},
        )

    def test_parse_as_of_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            sync_tjfch_test.parse_as_of("2026-06-11T12:00:00")

    def test_script_keeps_true_failures_fail_closed_before_state_write(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        failure_gate = source.index("publish_allowed = not failures")
        record_write = source.index("write_json_bundle_atomic({args.records_output: merged, args.report_output: report})")
        self.assertLess(failure_gate, record_write)
        self.assertIn("else:\n        write_json(args.report_output, report)", source)
        self.assertNotIn("write_json(args.records_output, merged)", source)
        self.assertIn('"true_fetch_or_parse_failure_blocks_state_update": True', source)
        self.assertIn('"relative_seven_day_window_never_published_as_official_deadline": True', source)


if __name__ == "__main__":
    unittest.main()
