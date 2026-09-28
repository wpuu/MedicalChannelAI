from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class AiBatchCacheV2Tests(unittest.TestCase):
    def test_server_batch_returns_rule_decisions_and_page_brief_uses_durable_cache(self) -> None:
        core = (WEB_ROOT / "api" / "ai" / "_analyzeCore.js").read_text(encoding="utf-8")
        db = (WEB_ROOT / "api" / "_publicIntelligenceDb.js").read_text(encoding="utf-8")

        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", core)
        self.assertIn("const MAX_BATCH_OPPORTUNITIES = 10", core)
        self.assertIn("'opportunity_ids'", core)
        self.assertIn("'cache_only'", core)
        self.assertIn("'page_brief'", core)
        self.assertIn("mode: 'BATCH'", core)
        self.assertIn("ruleDecisionItem({ snapshot: batchSnapshot, opportunityId, nowMs })", core)
        self.assertIn("mode: 'PAGE_BRIEF'", core)
        self.assertIn("getSharedPublicAiBrief(cacheKeys)", core)
        self.assertIn("PAGE_BRIEF_FIELDS_EXCLUSIVE", core)

        self.assertIn("export async function getSharedPublicAiBrief", db)
        self.assertIn("FROM public_ai_briefs", db)
        self.assertIn("opportunity_id = ${opportunityId}", db)
        self.assertIn("fact_hash = ${factHash}", db)
        self.assertIn("window_state = ${windowState}", db)
        self.assertIn("prompt_version = ${promptVersion}", db)

    def test_client_hydrates_visible_cards_and_offers_one_whole_page_ai_call(self) -> None:
        client = (WEB_ROOT / "src" / "services" / "aiDecisionApi.ts").read_text(encoding="utf-8")
        today = (WEB_ROOT / "src" / "pages" / "TodayPage.tsx").read_text(encoding="utf-8")
        detail = (WEB_ROOT / "src" / "pages" / "OpportunityDetailPage.tsx").read_text(encoding="utf-8")
        pool = (WEB_ROOT / "src" / "pages" / "OpportunityPoolPage.tsx").read_text(encoding="utf-8")
        panel = (WEB_ROOT / "src" / "components" / "today" / "PageBriefPanel.tsx").read_text(encoding="utf-8")

        self.assertIn("export async function requestAiDecisionBatch", client)
        self.assertIn("postJson({ opportunity_ids: opportunityIds })", client)
        self.assertIn("export async function hydrateSharedAiDecisions", client)
        self.assertIn("export async function requestPageBrief(", client)
        self.assertIn("postJson({ page_brief: { markets }, cache_only: cacheOnly })", client)
        # Only the page brief may call the model, so only it takes the AI gate.
        self.assertIn("if (!beginAiRequest()) throw new AiDecisionError('AI_CLIENT_BUSY', 429)", client)
        self.assertEqual(client.count("beginAiRequest()"), 1)

        self.assertNotIn("analyzeVisibleOpportunities", today)
        self.assertNotIn("AI分析未分析项", today)
        self.assertIn("const cards = await hydrateCachedAiDecisions(selected)", today)
        self.assertIn("hydrateSharedAiDecisions(res.cards)", today)
        self.assertIn("<PageBriefPanel", today)
        self.assertIn("AI整页研判", panel)

        self.assertIn("if (isApiMode || isVerifiedPublicDemo)", detail)
        self.assertIn("hydrateCachedAiDecisions([res])", detail)

        self.assertIn("hydrateSharedAiDecisions(candidates)", pool)
        self.assertIn(".slice(0, 30)", pool)


if __name__ == "__main__":
    unittest.main()
