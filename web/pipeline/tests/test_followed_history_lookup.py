import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class FollowedHistoryLookupTests(unittest.TestCase):
    def test_historical_detail_uses_exact_server_lookup_not_bounded_recent_list(self):
        frontend = (WEB_ROOT / "src" / "services" / "followedApi.ts").read_text(encoding="utf-8")
        start = frontend.index("export async function getHistoricalFollowedOpportunityCard")
        historical = frontend[start:]
        self.assertIn("getFollowedOpportunityById(opportunityId)", historical)
        self.assertNotIn("await getFollowedOpportunities()", historical)
        self.assertIn("/followed?id=${encodeURIComponent(opportunityId)}", frontend)

    def test_exact_lookup_is_user_and_organization_scoped(self):
        backend = (WEB_ROOT / "api" / "private.js").read_text(encoding="utf-8")
        start = backend.index("async function followedRoute")
        end = backend.index("function reminderPublicFacts", start)
        followed = backend[start:end]
        self.assertIn("f.opportunity_id = ${requestedId}", followed)
        self.assertIn("f.user_id = ${user.id}", followed)
        self.assertIn("f.organization_id = ${user.organization_id}", followed)
        self.assertIn("mode: 'FOLLOWED_OPPORTUNITY'", followed)
        self.assertIn("LIMIT 100", followed)


if __name__ == "__main__":
    unittest.main()
