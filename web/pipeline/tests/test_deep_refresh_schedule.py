from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TIANJIN_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tianjin-medical-refresh.yml"
REGIONAL_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "regional-medical-refresh.yml"


class DeepRefreshScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tianjin_workflow = TIANJIN_WORKFLOW.read_text(encoding="utf-8")
        cls.regional_workflow = REGIONAL_WORKFLOW.read_text(encoding="utf-8")

    def test_legacy_fallback_has_only_one_automatic_deep_run_per_day(self) -> None:
        self.assertEqual(self.tianjin_workflow.count("- cron:"), 1)
        self.assertIn("- cron: '20 0 * * *'", self.tianjin_workflow)
        self.assertNotIn("20 8 * * 1-5", self.tianjin_workflow)

    def test_manual_fallback_remains_available_until_vercel_runtime_acceptance(self) -> None:
        self.assertIn("workflow_dispatch:", self.tianjin_workflow)
        self.assertIn("Legacy GitHub scheduler", self.tianjin_workflow)
        self.assertIn(
            "until the Vercel-native collector is runtime-accepted",
            self.tianjin_workflow,
        )

    def test_tianjin_and_regional_deep_refreshes_share_one_serialization_group(self) -> None:
        shared_group = "group: medicalchannel-deep-refresh-${{ github.ref_name }}"
        for workflow in (self.tianjin_workflow, self.regional_workflow):
            with self.subTest(workflow=workflow[:40]):
                self.assertIn(shared_group, workflow)
                self.assertIn("cancel-in-progress: false", workflow)

        self.assertNotIn("group: tianjin-medical-refresh", self.tianjin_workflow)
        self.assertNotIn("group: regional-medical-refresh-", self.regional_workflow)
        self.assertNotIn("cancel-in-progress: true", self.regional_workflow)

    def test_regional_push_trigger_is_main_only_after_preview_acceptance(self) -> None:
        self.assertIn("branches: [main]", self.regional_workflow)
        self.assertNotIn("release/production-gate-prep", self.regional_workflow)


if __name__ == "__main__":
    unittest.main()
