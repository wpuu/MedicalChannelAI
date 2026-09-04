from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class TodayMutationReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = (WEB_ROOT / "src" / "services" / "ApiTodayActionsService.ts").read_text(encoding="utf-8")
        cls.pilot = (WEB_ROOT / "src" / "services" / "index.ts").read_text(encoding="utf-8")

    def test_confirmed_followup_response_is_reused_only_once(self) -> None:
        self.assertIn("private latestToday: TodayActionsResponse | null = null", self.service)
        self.assertIn("private pendingTodayAfterMutation:", self.service)
        self.assertIn("const pending = this.pendingTodayAfterMutation", self.service)
        self.assertIn("this.pendingTodayAfterMutation = null", self.service)
        self.assertIn("return pending.value", self.service)
        self.assertIn("const state = await this.requestJson<ServerFollowupState>", self.service)
        self.assertIn("applyMutationToToday(this.latestToday, state)", self.service)

    def test_detail_mutation_response_reuses_server_confirmed_state_once(self) -> None:
        self.assertIn("private latestOpportunity: TodayActionCard | null = null", self.service)
        self.assertIn("private pendingOpportunityAfterMutation:", self.service)
        self.assertIn("const pending = this.pendingOpportunityAfterMutation", self.service)
        self.assertIn("pending?.opportunityId === id", self.service)
        self.assertIn("this.pendingOpportunityAfterMutation = null", self.service)
        self.assertIn("applyFollowupState(this.latestOpportunity, state)", self.service)
        self.assertIn("opportunityId: id", self.service)

    def test_mutation_reuse_expires_quickly_instead_of_becoming_long_lived_cache(self) -> None:
        self.assertIn("const MUTATION_REUSE_TTL_MS = 5_000", self.service)
        self.assertIn("pending.expiresAt >= Date.now()", self.service)
        self.assertGreaterEqual(
            self.service.count("expiresAt: Date.now() + MUTATION_REUSE_TTL_MS"),
            2,
        )
        self.assertNotIn("CACHE_TTL_MS", self.service)

    def test_local_today_visibility_matches_server_followup_rules(self) -> None:
        self.assertIn("const DONE_FOR_TODAY = new Set<FollowupStatus>", self.service)
        for status in ("CONTACTED", "NOT_FIT", "BID_SUBMITTED", "WON", "LOST", "ARCHIVED"):
            self.assertIn(f"  '{status}',", self.service)
        self.assertIn("DONE_FOR_TODAY.has(card.followup_status)", self.service)
        self.assertIn("remindAt <= Date.now()", self.service)
        self.assertIn("current.cards.map(updateCard).filter(shouldAppearToday)", self.service)
        self.assertIn("opportunity_pool: opportunityPool", self.service)

    def test_formal_window_nudge_forces_only_next_primary_today_read_authoritative(self) -> None:
        self.assertIn("private primaryHasFormalNudge = false", self.pilot)
        self.assertIn("formal_candidates_needing_action ?? 0", self.pilot)
        self.assertIn("if (this.primaryHasFormalNudge)", self.pilot)
        self.assertIn("this.primary = new GroundedApiTodayActionsService(this.normalizedBaseUrl)", self.pilot)
        self.assertIn("this.primaryHasFormalNudge = false", self.pilot)
        self.assertIn("await this.primary.updateFollowup(id, input)", self.pilot)
        self.assertIn("options?.hydrateFollowups === false ? this.fullPool : this.primary", self.pilot)
        self.assertNotIn("this.fullPool = new GroundedApiTodayActionsService(this.normalizedBaseUrl)", self.pilot)


if __name__ == "__main__":
    unittest.main()
