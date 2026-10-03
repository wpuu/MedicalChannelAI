from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class DetailRequestPressureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (WEB_ROOT / "src" / "services" / "ApiTodayActionsService.ts").read_text(encoding="utf-8")

    def test_opportunity_and_followup_reads_are_parallel(self) -> None:
        start = self.source.index("async getOpportunity(id: string)")
        end = self.source.index("async updateFollowup", start)
        block = self.source[start:end]
        self.assertIn("Promise.all([", block)
        self.assertIn("/opportunity/${encodedId}", block)
        self.assertIn("this.getFollowupState(id)", block)
        self.assertIn(
            "applyFollowupState({ ...mapPublicCard(card), snapshot_meta: card.snapshot_meta }, state)",
            block,
        )
        self.assertNotIn("enrichWithServerFollowup", block)


if __name__ == "__main__":
    unittest.main()
