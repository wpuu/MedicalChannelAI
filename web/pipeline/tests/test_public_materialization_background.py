from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class PublicMaterializationBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (WEB_ROOT / "api" / "_pilotOpportunity.js").read_text(encoding="utf-8")

    def test_vercel_schedules_side_store_after_response_path(self) -> None:
        self.assertIn("import { waitUntil } from '@vercel/functions'", self.source)
        start = self.source.index("async function materializePublicSnapshotBestEffort")
        end = self.source.index("function publicCustomerContext", start)
        block = self.source[start:end]
        self.assertIn("if (process.env.VERCEL)", block)
        self.assertIn("waitUntil(task)", block)
        self.assertIn("await task", block)
        self.assertLess(block.index("waitUntil(task)"), block.index("await task"))

    def test_duplicate_materialization_is_suppressed_per_warm_instance(self) -> None:
        self.assertIn("const materializingSnapshotKeys = new Set()", self.source)
        self.assertIn("materializingSnapshotKeys.has(key)", self.source)
        self.assertIn("materializingSnapshotKeys.add(key)", self.source)
        self.assertIn("materializingSnapshotKeys.delete(key)", self.source)
        self.assertIn("materializedSnapshotKeys.has(key)", self.source)


if __name__ == "__main__":
    unittest.main()
