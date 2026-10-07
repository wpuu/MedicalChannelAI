from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class AiBatchCacheV2Tests(unittest.TestCase):
    def test_server_batch_contract_reuses_durable_public_cache(self) -> None:
        core = (WEB_ROOT / "api" / "ai" / "_analyzeCore.js").read_text(encoding="utf-8")
        db = (WEB_ROOT / "api" / "_publicIntelligenceDb.js").read_text(encoding="utf-8")

        self.assertIn("const MODEL_ID = 'agnes-3.0-flash'", core)
        self.assertIn("const MAX_BATCH_OPPORTUNITIES = 10", core)
        self.assertIn("getSharedPublicAiBrief", core)
        self.assertIn("'opportunity_ids'", core)
        self.assertIn("'cache_only'", core)
        self.assertIn("mode: 'BATCH'", core)
        self.assertIn("Promise.all(", core)
        self.assertIn("status: 'MISS'", core)
        self.assertIn("shared-public:", core)
        self.assertIn("snapshot_runtime_origin: batchRuntimeOrigin", core)
        self.assertIn("snapshot_runtime_origin: runtimeOrigin", core)

        self.assertIn("export async function getSharedPublicAiBrief", db)
        self.assertIn("FROM public_ai_briefs", db)
        self.assertIn("opportunity_id = ${opportunityId}", db)
        self.assertIn("fact_hash = ${factHash}", db)
        self.assertIn("window_state = ${windowState}", db)
        self.assertIn("prompt_version = ${promptVersion}", db)

    def test_client_batches_one_http_request_and_cache_only_hydration(self) -> None:
        client = (WEB_ROOT / "src" / "services" / "aiDecisionApi.ts").read_text(encoding="utf-8")
        today = (WEB_ROOT / "src" / "pages" / "TodayPage.tsx").read_text(encoding="utf-8")
        detail = (WEB_ROOT / "src" / "pages" / "OpportunityDetailPage.tsx").read_text(encoding="utf-8")
        pool = (WEB_ROOT / "src" / "pages" / "OpportunityPoolPage.tsx").read_text(encoding="utf-8")

        self.assertIn("export async function requestAiDecisionBatch", client)
        self.assertIn("opportunity_ids: opportunityIds", client)
        self.assertIn("postAiDecisionBatch(safeCards, cacheOnly)", client)
        self.assertIn("cache_only: cacheOnly", client)
        # Transient per-item failures get exactly one automatic follow-up pass.
        self.assertIn("postAiDecisionBatch(safeCards.filter((card) => retryIds.includes(card.opportunity_id)), false)", client)
        self.assertIn("if (cacheOnly) return { ...first, errors: { ...preflightErrors, ...first.errors } }", client)
        self.assertIn("responseMatchesProvenance(record, provenance)", client)
        self.assertIn("const CACHE_KEY = 'medopp.grounded-ai-decisions.v2'", client)
        self.assertIn("sameAiDecisionSnapshotVersion", today)
        self.assertIn("sameAiDecisionSnapshotVersion", detail)
        self.assertIn("sameAiDecisionSnapshotVersion", pool)
        self.assertIn("export async function hydrateSharedAiDecisions", client)
        self.assertIn("requestAiDecisionBatch(cards, { cacheOnly: true })", client)

        self.assertIn("analyzeVisibleOpportunities", today)
        self.assertIn("AI分析未分析项", today)
        self.assertIn("requestAiDecisionBatch(candidates)", today)
        self.assertIn("hydrateSharedAiDecisions(res.cards)", today)

        self.assertIn("if (isApiMode || isVerifiedPublicDemo)", detail)
        self.assertIn("hydrateCachedAiDecisions([res])", detail)

        self.assertIn("hydrateSharedAiDecisions(candidates)", pool)
        self.assertIn(".slice(0, 10)", pool)


if __name__ == "__main__":
    unittest.main()
