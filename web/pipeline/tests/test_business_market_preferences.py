from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BusinessMarketPreferenceTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_static_today_preserves_explicit_market_metadata(self):
        source = self.read("src/services/StaticSnapshotTodayActionsService.ts")
        self.assertIn("market_code: card.facts.market_code ?? null", source)
        self.assertIn("market_name: card.facts.market_name ?? null", source)
        self.assertIn("market_admin_code: card.facts.market_admin_code ?? null", source)

    def test_one_market_preference_source_drives_public_and_api_services(self):
        source = self.read("src/services/index.ts")
        self.assertIn("marketCodesForSelection", source)
        self.assertIn("new MarketScopedTodayActionsService(new PilotApiTodayActionsService(apiBaseUrl))", source)
        self.assertIn("return this.delegate.getOpportunity(id)", source)
        self.assertFalse((ROOT / "src/services/businessMarketPreferences.ts").exists())

    def test_selector_is_explicit_business_scope_without_geolocation(self):
        config = self.read("src/config/marketPreference.ts")
        layout = self.read("src/components/layout/AppLayout.tsx")
        self.assertIn("{ value: 'JJ', label: '京津' }", config)
        self.assertIn("{ value: 'JJJ', label: '京津冀' }", config)
        self.assertIn("{ value: 'NE3', label: '东北三省' }", config)
        self.assertIn("{ value: 'ALL', label: '全部已开通' }", config)
        self.assertIn("isApiMode || isVerifiedPublicDemo", layout)
        for forbidden in ("geolocation", "navigator.geolocation", "ipLocation", "GPS"):
            self.assertNotIn(forbidden, config)

    def test_today_and_pool_show_same_global_business_scope(self):
        today = self.read("src/pages/TodayPage.tsx")
        pool = self.read("src/pages/OpportunityPoolPage.tsx")
        self.assertIn("业务地区：{marketSelectionLabel()}", today)
        self.assertNotIn("数据范围：天津公开采购", today)
        self.assertIn("selectedMarketCodes", pool)
        self.assertIn("业务地区：", pool)
        self.assertNotIn("setMarketFilter", pool)


if __name__ == "__main__":
    unittest.main()
