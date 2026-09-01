from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_RUN = WEB_ROOT / "api" / "collector-run.py"


class CollectorRunSecurityTests(unittest.TestCase):
    def test_temporary_acceptance_probe_is_removed(self) -> None:
        source = COLLECTOR_RUN.read_text(encoding="utf-8")
        self.assertNotIn("ACCEPTANCE_PROBE", source)
        self.assertNotIn("parse_qs", source)
        self.assertNotIn("urlsplit", source)
        self.assertNotIn('cycle_id = f"accept:', source)

    def test_trigger_is_limited_to_vercel_cron_contract(self) -> None:
        source = COLLECTOR_RUN.read_text(encoding="utf-8")
        self.assertIn('x-vercel-cron-schedule', source)
        self.assertIn('CRON_SECRET', source)
        self.assertIn('return True, "VERCEL_CRON"', source)
        self.assertIn('cycle_id = f"prod:{local_date}"', source)


if __name__ == "__main__":
    unittest.main()
