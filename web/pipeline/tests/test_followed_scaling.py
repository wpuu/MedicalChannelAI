import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class FollowedScalingTests(unittest.TestCase):
    def test_followed_route_supports_bounded_pagination_and_compact_status_index(self):
        backend = (WEB_ROOT / "api" / "_privateCore.js").read_text(encoding="utf-8")
        start = backend.index("async function followedRoute")
        end = backend.index("function reminderPublicFacts", start)
        followed = backend[start:end]
        self.assertIn("view !== 'status-index'", followed)
        self.assertIn("LIMIT 5001", followed)
        self.assertIn("mode: 'FOLLOWED_STATUS_INDEX'", followed)
        self.assertIn("LIMIT 101 OFFSET ${offset}", followed)
        self.assertIn("has_more: hasMore", followed)
        self.assertIn("organization_id = ${user.organization_id}", followed)

    def test_opportunity_pool_reuses_followup_summary_already_batched_into_today(self):
        page = (WEB_ROOT / "src" / "pages" / "OpportunityPoolPage.tsx").read_text(encoding="utf-8")
        service = (WEB_ROOT / "src" / "services" / "ApiTodayActionsService.ts").read_text(encoding="utf-8")
        backend = (WEB_ROOT / "api" / "_privateCore.js").read_text(encoding="utf-8")

        self.assertIn("todayActionsService.getTodayActions({ hydrateFollowups: false })", page)
        self.assertNotIn("getFollowedStatusIndex", page)
        self.assertNotIn("getFollowedOpportunities", page)
        self.assertNotIn("'/followed?view=status-index'", service)
        self.assertIn("normalizeFollowupStatus(card.followup_status)", service)
        self.assertIn("decorateCardWithFollowup", backend)
        self.assertIn("opportunity_pool: decoratedPool", backend)

    def test_followed_page_can_load_older_records_and_recover_focused_item_exactly(self):
        page = (WEB_ROOT / "src" / "pages" / "FollowedPage.tsx").read_text(encoding="utf-8")
        self.assertIn("getFollowedOpportunityPage", page)
        self.assertIn("getFollowedStatusIndex", page)
        self.assertIn("getFollowedOpportunityById(focusedId)", page)
        self.assertIn("加载更早跟进", page)
        self.assertIn("statusIndex.length", page)
        self.assertIn("setNextOffset(page.offset + 100)", page)
        self.assertIn("搜索与行动排序仅覆盖已加载详情", page)


if __name__ == "__main__":
    unittest.main()
