from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from bootstrap_ccgp_backfill import build_date_windows, parse_as_of  # noqa: E402


class BootstrapCcgpBackfillTests(unittest.TestCase):
    def test_thirty_day_backfill_is_split_into_bounded_seven_day_windows(self) -> None:
        windows = build_date_windows(date(2026, 9, 1), lookback_days=30, chunk_days=7)
        self.assertEqual(
            windows,
            [
                (date(2026, 8, 3), date(2026, 8, 9)),
                (date(2026, 8, 10), date(2026, 8, 16)),
                (date(2026, 8, 17), date(2026, 8, 23)),
                (date(2026, 8, 24), date(2026, 8, 30)),
                (date(2026, 8, 31), date(2026, 9, 1)),
            ],
        )

    def test_single_day_window_is_inclusive(self) -> None:
        windows = build_date_windows(date(2026, 9, 1), lookback_days=1, chunk_days=7)
        self.assertEqual(windows, [(date(2026, 9, 1), date(2026, 9, 1))])

    def test_backfill_rejects_unbounded_windows(self) -> None:
        with self.assertRaisesRegex(ValueError, "lookback_days"):
            build_date_windows(date(2026, 9, 1), lookback_days=61, chunk_days=7)
        with self.assertRaisesRegex(ValueError, "chunk_days"):
            build_date_windows(date(2026, 9, 1), lookback_days=30, chunk_days=15)

    def test_as_of_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_as_of("2026-09-01T08:00:00")
        parsed = parse_as_of("2026-09-01T08:00:00+08:00")
        self.assertIsNotNone(parsed.tzinfo)


if __name__ == "__main__":
    unittest.main()
