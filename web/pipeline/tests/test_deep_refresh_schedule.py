from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tianjin-medical-refresh.yml"


class DeepRefreshScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_legacy_fallback_has_only_one_automatic_deep_run_per_day(self) -> None:
        self.assertEqual(self.workflow.count("- cron:"), 1)
        self.assertIn("- cron: '20 0 * * *'", self.workflow)
        self.assertNotIn("20 8 * * 1-5", self.workflow)

    def test_manual_fallback_remains_available_until_vercel_runtime_acceptance(self) -> None:
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("Legacy GitHub scheduler", self.workflow)
        self.assertIn("until the Vercel-native collector is runtime-accepted", self.workflow)


if __name__ == "__main__":
    unittest.main()
