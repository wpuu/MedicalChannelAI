from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RegionalIncrementalRadarTests(unittest.TestCase):
    def test_incremental_sync_skips_existing_verified_detail_urls(self) -> None:
        source = (ROOT / "pipeline" / "scripts" / "sync_regional_ccgp.py").read_text(encoding="utf-8")
        self.assertIn("'--incremental-only'", source)
        self.assertIn("'--lookback-days'", source)
        self.assertIn("if args.incremental_only", source)
        self.assertIn("not in existing_source_urls", source)
        self.assertIn("'incremental_existing_verified_urls_are_not_refetched': args.incremental_only", source)

    def test_incremental_workflow_is_change_driven(self) -> None:
        workflow = (ROOT.parent / ".github" / "workflows" / "regional-medical-incremental.yml").read_text(encoding="utf-8")
        self.assertIn("0,30 0-10 * * 1-5", workflow)
        self.assertIn("--lookback-days 1", workflow)
        self.assertIn("--incremental-only", workflow)
        self.assertIn("new_verified_record_count", workflow)
        self.assertIn("if: steps.changes.outputs.publish == 'true'", workflow)
        self.assertIn("No new verified opportunity; snapshot, AI and Git publication are skipped.", workflow)


if __name__ == "__main__":
    unittest.main()
