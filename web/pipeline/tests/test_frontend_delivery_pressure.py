from __future__ import annotations

import json
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]

# Keep this suite lightweight; Full Verify measures production bundle output at stage boundaries.


class FrontendDeliveryPressureTests(unittest.TestCase):
    def test_production_build_keeps_hashed_assets_instead_of_single_html(self) -> None:
        vite = (WEB_ROOT / "vite.config.ts").read_text(encoding="utf-8")
        self.assertNotIn("viteSingleFile", vite)
        self.assertNotIn("vite-plugin-singlefile", vite)
        self.assertIn("plugins: [react(), tailwindcss()]", vite)

        config = json.loads((WEB_ROOT / "vercel.json").read_text(encoding="utf-8"))
        asset_headers = next(
            item for item in config.get("headers", []) if item.get("source") == "/assets/(.*)"
        )
        values = {item["key"].lower(): item["value"] for item in asset_headers.get("headers", [])}
        self.assertIn("immutable", values.get("cache-control", "").lower())

    def test_heavy_secondary_routes_and_login_are_lazy_but_today_stays_eager(self) -> None:
        app = (WEB_ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("import { TodayPage } from '@/pages/TodayPage'", app)
        self.assertIn("const LoginPage = lazy(() =>", app)
        self.assertIn("const DiscoveryRadarRoute = lazy(() =>", app)
        self.assertIn("const OpportunityPoolPage = lazy(() =>", app)
        self.assertIn("const OpportunityDetailPage = lazy(() =>", app)
        self.assertIn("const PilotResourcesPage = lazy(() =>", app)
        self.assertIn("const FollowedPage = lazy(() =>", app)
        self.assertIn("<Suspense fallback={<LoadingState />}", app)
        self.assertNotIn("import { LoginPage } from '@/pages/LoginPage'", app)
        self.assertNotIn("import { OpportunityPoolPage } from '@/pages/OpportunityPoolPage'", app)

    def test_pilot_bundle_does_not_eagerly_import_trial_or_local_demo_services(self) -> None:
        services = (WEB_ROOT / "src" / "services" / "index.ts").read_text(encoding="utf-8")
        layout = (WEB_ROOT / "src" / "components" / "layout" / "AppLayout.tsx").read_text(encoding="utf-8")
        self.assertIn("import { GroundedApiTodayActionsService }", services)
        self.assertIn("import('./RuntimeTrialTodayActionsService')", services)
        self.assertIn("import('./StaticSnapshotTodayActionsService')", services)
        self.assertIn("import('./MockTodayActionsService')", services)
        self.assertNotIn("import { MockTodayActionsService }", services)
        self.assertNotIn("import { RuntimeTrialTodayActionsService }", services)
        self.assertNotIn("import { StaticSnapshotTodayActionsService }", services)
        self.assertIn("class DeferredTodayActionsService implements TodayActionsService", services)

        for module in (
            "@/services/MockTodayActionsService",
            "@/services/localFollowupStore",
            "@/services/localCustomerProfile",
        ):
            self.assertIn(f"import('{module}')", layout)
        self.assertNotIn("import { resetMockDemoState } from '@/services/MockTodayActionsService'", layout)
        self.assertNotIn("import { resetLocalFollowups } from '@/services/localFollowupStore'", layout)
        self.assertNotIn("import { clearLocalCustomerProfile } from '@/services/localCustomerProfile'", layout)
        self.assertIn("const [mockModule, followupModule, profileModule] = await Promise.all([", layout)

    def test_today_ai_client_is_loaded_only_for_demo_cache_or_explicit_analysis(self) -> None:
        today = (WEB_ROOT / "src" / "pages" / "TodayPage.tsx").read_text(encoding="utf-8")
        self.assertNotIn("from '@/services/aiDecisionApi'", today)
        self.assertIn(
            "const { hydrateCachedAiDecisions } = await import('@/services/aiDecisionApi')",
            today,
        )
        self.assertIn("aiApi = await import('@/services/aiDecisionApi')", today)
        self.assertIn("const decision = await aiApi.requestAiDecision(card)", today)
        self.assertIn("cause instanceof aiApi.AiDecisionError", today)
        self.assertIn("aiApi.aiDecisionErrorMessage(cause)", today)
        self.assertIn("if (!isApiMode && isVerifiedPublicDemo)", today)

    def test_today_outreach_drawer_is_loaded_only_after_user_opens_it(self) -> None:
        today = (WEB_ROOT / "src" / "pages" / "TodayPage.tsx").read_text(encoding="utf-8")
        self.assertNotIn(
            "import { OutreachDrawer } from '@/components/followup/OutreachDrawer'",
            today,
        )
        self.assertIn("const OutreachDrawer = lazy(() =>", today)
        self.assertIn("import('@/components/followup/OutreachDrawer')", today)
        self.assertIn("{outreachId ? (", today)
        self.assertIn("<Suspense fallback={null}>", today)
        self.assertIn(
            '<OutreachDrawer open opportunityId={outreachId} onClose={() => setOutreachId(null)} />',
            today,
        )
        self.assertIn("if (!automationUnavailableReason) setOutreachId(card.opportunity_id)", today)


if __name__ == "__main__":
    unittest.main()
