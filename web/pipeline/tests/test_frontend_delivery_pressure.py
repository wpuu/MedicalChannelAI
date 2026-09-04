from __future__ import annotations

import json
import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


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

    def test_heavy_secondary_routes_are_lazy_but_today_stays_eager(self) -> None:
        app = (WEB_ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("import { TodayPage } from '@/pages/TodayPage'", app)
        self.assertIn("const DiscoveryRadarRoute = lazy(() =>", app)
        self.assertIn("const OpportunityPoolPage = lazy(() =>", app)
        self.assertIn("const OpportunityDetailPage = lazy(() =>", app)
        self.assertIn("const PilotResourcesPage = lazy(() =>", app)
        self.assertIn("const FollowedPage = lazy(() =>", app)
        self.assertIn("<Suspense fallback={<LoadingState />}", app)
        self.assertNotIn("import { OpportunityPoolPage } from '@/pages/OpportunityPoolPage'", app)


if __name__ == "__main__":
    unittest.main()
