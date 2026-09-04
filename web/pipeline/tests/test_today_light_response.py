from __future__ import annotations

import json
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_ENTRY = WEB_ROOT / "api" / "private.js"
PRIVATE_CORE = WEB_ROOT / "api" / "_privateCore.js"
SERVICES = WEB_ROOT / "src" / "services" / "index.ts"
POOL_PAGE = WEB_ROOT / "src" / "pages" / "OpportunityPoolPage.tsx"
VERCEL_CONFIG = WEB_ROOT / "vercel.json"


class TodayLightResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entry = PRIVATE_ENTRY.read_text(encoding="utf-8")
        cls.core = PRIVATE_CORE.read_text(encoding="utf-8")
        cls.services = SERVICES.read_text(encoding="utf-8")
        cls.pool_page = POOL_PAGE.read_text(encoding="utf-8")
        cls.vercel = json.loads(VERCEL_CONFIG.read_text(encoding="utf-8"))

    def test_default_today_projects_out_full_pool_and_keeps_only_intent_summary(self) -> None:
        self.assertIn("import privateCoreHandler from './_privateCore.js'", self.entry)
        self.assertIn("import { procurementIntentFollowupSummary } from './_procurementIntentFollowup.js'", self.entry)
        self.assertIn("request.method !== 'GET'", self.entry)
        self.assertIn("firstQuery(request, 'route') !== 'today'", self.entry)
        self.assertIn("firstQuery(request, 'include_pool') !== '1'", self.entry)
        self.assertIn("const { opportunity_pool: fullPool, ...lightPayload } = payload", self.entry)
        self.assertIn("procurement_intent_followup_summary: procurementIntentFollowupSummary(fullPool)", self.entry)
        self.assertIn("return await privateCoreHandler(request, response)", self.entry)
        self.assertNotIn("return {\n    ...lightPayload,\n    opportunity_pool:", self.entry)
        self.assertNotIn("privateDb", self.entry)
        self.assertNotIn("loadVerifiedSnapshot", self.entry)

    def test_internal_core_retains_original_full_pool_business_payload(self) -> None:
        self.assertTrue(PRIVATE_CORE.name.startswith("_"))
        self.assertIn("async function todayRoute(request, response, user)", self.core)
        self.assertIn("opportunity_pool_count: pool.length", self.core)
        self.assertIn("opportunity_pool: decoratedPool", self.core)
        self.assertIn("if (route === 'today') return todayRoute(request, response, user)", self.core)
        self.assertIn("if (route === 'followup') return followupRoute(request, response, user)", self.core)

    def test_full_pool_alias_reuses_same_private_function(self) -> None:
        rewrites = {
            item.get("source"): item.get("destination")
            for item in self.vercel.get("rewrites", [])
            if isinstance(item, dict)
        }
        self.assertEqual(rewrites.get("/api/today"), "/api/private?route=today")
        self.assertEqual(
            rewrites.get("/api/opportunity-pool/today"),
            "/api/private?route=today&include_pool=1",
        )
        self.assertNotIn("/api/opportunity-pool", self.vercel.get("functions", {}))

    def test_real_pilot_uses_isolated_full_pool_delegate_only_for_pool_load_profile(self) -> None:
        self.assertIn("class PilotApiTodayActionsService implements TodayActionsService", self.services)
        self.assertIn(
            "this.fullPool = new GroundedApiTodayActionsService(`${normalized}/opportunity-pool`)",
            self.services,
        )
        self.assertIn(
            "options?.hydrateFollowups === false ? this.fullPool : this.primary",
            self.services,
        )
        self.assertIn("return this.primary.updateFollowup(id, input)", self.services)
        self.assertIn("return this.primary.getOpportunity(id)", self.services)

    def test_opportunity_pool_keeps_explicit_full_pool_load_profile(self) -> None:
        self.assertIn(
            "todayActionsService.getTodayActions({ hydrateFollowups: false })",
            self.pool_page,
        )


if __name__ == "__main__":
    unittest.main()
