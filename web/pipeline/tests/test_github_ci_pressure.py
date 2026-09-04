from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"


class GithubCiPressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_normal_pr_verify_skips_heavy_npm_build(self) -> None:
        self.assertIn("Select verification depth", self.workflow)
        self.assertIn('"[full-verify]"', self.workflow)
        self.assertIn("Fast Verify selected", self.workflow)
        self.assertIn("Run fast contract verification", self.workflow)
        self.assertIn("python3 -m unittest discover -s tests -v", self.workflow)
        self.assertIn("node scripts/check-serverless-entrypoints.mjs", self.workflow)
        self.assertIn("if: steps.verify_mode.outputs.full == 'true'", self.workflow)

    def test_full_verify_remains_available_at_stage_boundaries(self) -> None:
        self.assertIn("workflow_dispatch", self.workflow)
        self.assertIn("Full Verify requested by workflow_dispatch", self.workflow)
        self.assertIn("npm ci --no-audit --no-fund", self.workflow)
        self.assertIn("npm run build", self.workflow)
        self.assertIn("Print verified ranking summary", self.workflow)

    def test_runner_cleanup_and_docs_skip_remain_enabled(self) -> None:
        self.assertIn("cancel-in-progress: true", self.workflow)
        self.assertIn("'docs/**'", self.workflow)
        self.assertIn("'**/*.md'", self.workflow)
        self.assertIn("rm -rf web/node_modules web/dist", self.workflow)


if __name__ == "__main__":
    unittest.main()
