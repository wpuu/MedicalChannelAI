from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = ROOT / "web"
LEGACY_WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"
PACKAGE = WEB_ROOT / "package.json"
PREBUILD = WEB_ROOT / "scripts" / "run-prebuild.mjs"


class GithubCiPressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = json.loads(PACKAGE.read_text(encoding="utf-8"))
        cls.prebuild = PREBUILD.read_text(encoding="utf-8")

    def test_gcp_backed_pr_verify_workflow_is_retired(self) -> None:
        self.assertFalse(
            LEGACY_WORKFLOW.exists(),
            "PR verification must not depend on the MedicalChannelAI GCP self-hosted runner",
        )

    def test_vercel_build_is_the_complete_pr_verification_entrypoint(self) -> None:
        build = self.package.get("scripts", {}).get("build")
        self.assertEqual(
            build,
            "node scripts/run-prebuild.mjs && tsc --noEmit && vite build",
        )

    def test_prebuild_runs_full_python_regression_suite(self) -> None:
        self.assertIn("['-m', 'unittest', 'discover', '-s', 'tests', '-v']", self.prebuild)
        self.assertIn("BUNDLED_SNAPSHOT_REFRESH_FAILED", self.prebuild)
        self.assertIn("PIPELINE_UNITTEST_FAILED", self.prebuild)
        self.assertIn("PYTHON_RUNTIME_NOT_FOUND_FOR_PIPELINE_TESTS", self.prebuild)

    def test_prebuild_keeps_serverless_and_safety_contracts(self) -> None:
        required_checks = [
            "check-serverless-entrypoints.mjs",
            "check-verified-snapshot.mjs",
            "check-medical-channel-scope.mjs",
            "check-ai-decision-contract.mjs",
            "check-runtime-status.mjs",
            "check-source-quality-boundary.mjs",
        ]
        for check in required_checks:
            self.assertIn(check, self.prebuild)
        self.assertIn("Prebuild verification: PASS", self.prebuild)


if __name__ == "__main__":
    unittest.main()
