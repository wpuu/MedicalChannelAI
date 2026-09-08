from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch(path: str, old: str, new: str, expected: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"PATCH_COUNT {path}: expected {expected}, got {count}\n--- OLD ---\n{old}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Preserve explicit market metadata in the static Today mapping.
patch(
    "web/src/services/StaticSnapshotTodayActionsService.ts",
    "      region: card.facts.region,\n      lifecycle_stage: card.facts.lifecycle_state,",
    "      region: card.facts.region,\n      market_code: card.facts.market_code ?? null,\n      market_name: card.facts.market_name ?? null,\n      market_admin_code: card.facts.market_admin_code ?? null,\n      lifecycle_stage: card.facts.lifecycle_state,",
)
patch(
    "web/src/services/StaticSnapshotTodayActionsService.ts",
    "const COVERAGE_WARNING = '天津 Pilot · 公开事实来自证据流水线快照；当前仍为部分来源覆盖。'",
    "const COVERAGE_WARNING = '当前业务地区 · 公开事实来自证据流水线快照；各地区仍为部分来源覆盖。'",
)

# Reuse the existing MarketScoped service for authenticated API mode as well.
patch(
    "web/src/services/index.ts",
    """export const todayActionsService: TodayActionsService = apiBaseUrl\n  ? new PilotApiTodayActionsService(apiBaseUrl)\n  : new DeferredTodayActionsService(""",
    """export const todayActionsService: TodayActionsService = apiBaseUrl\n  ? new MarketScopedTodayActionsService(new PilotApiTodayActionsService(apiBaseUrl))\n  : new DeferredTodayActionsService(""",
)

# Business-market selector is also relevant to authenticated Pilot accounts.
patch(
    "web/src/components/layout/AppLayout.tsx",
    "                {isVerifiedPublicDemo ? (",
    "                {isApiMode || isVerifiedPublicDemo ? (",
)

# Use concise Chinese labels for the existing preset combinations.
patch(
    "web/src/config/marketPreference.ts",
    "  { value: 'JJ', label: '北京 + 天津' },",
    "  { value: 'JJ', label: '京津' },",
)

# Today copy must describe the actual selected business market, not Tianjin-only coverage.
patch(
    "web/src/pages/TodayPage.tsx",
    "import { isVerifiedPublicDemo } from '@/config/demoDataset'",
    "import { isVerifiedPublicDemo } from '@/config/demoDataset'\nimport { marketSelectionLabel } from '@/config/marketPreference'",
)
patch(
    "web/src/pages/TodayPage.tsx",
    """function userCoverageWarning(value: string): string {\n  return value\n    .replace(\n      '天津 Pilot · 公开事实来自证据流水线快照；当前仍为部分来源覆盖。',\n      '天津公开采购 · 商机来自已核验官方公开信息；当前仍为部分来源覆盖。',\n    )\n    .split('天津 Pilot').join('天津公开采购')\n}\n""",
    """function userCoverageWarning(value: string): string {\n  return value\n    .replace(\n      '天津 Pilot · 公开事实来自证据流水线快照；当前仍为部分来源覆盖。',\n      '当前业务地区 · 商机来自已核验官方公开信息；各地区仍为部分来源覆盖。',\n    )\n    .split('天津 Pilot').join('当前业务地区')\n    .split('天津公开采购').join('当前业务地区')\n}\n""",
)
patch(
    "web/src/pages/TodayPage.tsx",
    "<span className=\"rounded-full border border-slate-200 bg-white px-2.5 py-1\">数据范围：天津公开采购</span>",
    "<span className=\"rounded-full border border-slate-200 bg-white px-2.5 py-1\">业务地区：{marketSelectionLabel()}</span>",
)

# Opportunity pool must obey the same global business-market selection instead of
# maintaining a second, page-only business-region selector.
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "import { useToast } from '@/context/ToastContext'",
    "import { marketCodesForSelection, marketSelectionLabel } from '@/config/marketPreference'\nimport { useToast } from '@/context/ToastContext'",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "  const [marketFilter, setMarketFilter] = useState('ALL')\n",
    "",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    """  const marketOptions = useMemo(() => {\n    const markets = new Map<string, string>()\n    cards.forEach((card) => {\n      const code = card.facts.market_code?.trim().toUpperCase()\n      const name = card.facts.market_name?.trim()\n      if (code && name) markets.set(code, name)\n    })\n    const preferredOrder = ['TJ', 'BJ', 'HE', 'LN', 'JL', 'HL']\n    return [...markets.entries()]\n      .map(([code, name]) => ({ code, name }))\n      .sort((a, b) => {\n        const ai = preferredOrder.indexOf(a.code)\n        const bi = preferredOrder.indexOf(b.code)\n        if (ai !== -1 || bi !== -1) {\n          if (ai === -1) return 1\n          if (bi === -1) return -1\n          return ai - bi\n        }\n        return a.name.localeCompare(b.name, 'zh-CN')\n      })\n  }, [cards])\n\n""",
    "  const selectedMarketCodes = useMemo(() => new Set(marketCodesForSelection()), [])\n\n",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "      if (marketFilter !== 'ALL' && card.facts.market_code !== marketFilter) return false",
    "      if (!card.facts.market_code || !selectedMarketCodes.has(card.facts.market_code as never)) return false",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "  }, [cards, marketFilter, query, windowFilter])",
    "  }, [cards, query, selectedMarketCodes, windowFilter])",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    """          <label className=\"flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 text-[12px] text-slate-500\">\n            <span className=\"whitespace-nowrap\">业务地区</span>\n            <select\n              value={marketFilter}\n              onChange={(event) => setMarketFilter(event.target.value)}\n              className=\"min-w-24 bg-transparent font-medium text-slate-700 outline-none\"\n            >\n              <option value=\"ALL\">全部地区</option>\n              {marketOptions.map((market) => (\n                <option key={market.code} value={market.code}>{market.name}</option>\n              ))}\n            </select>\n          </label>\n""",
    """          <div className=\"flex h-10 items-center rounded-xl border border-slate-200 bg-slate-50 px-3 text-[12px] text-slate-500\">\n            <span className=\"whitespace-nowrap\">业务地区：<strong className=\"font-medium text-slate-700\">{marketSelectionLabel()}</strong></span>\n          </div>\n""",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "<EmptyState title=\"没有符合条件的机会\" hint=\"可以清空搜索词、切换业务地区或调整窗口筛选。\" />",
    "<EmptyState title=\"没有符合条件的机会\" hint=\"可以清空搜索词、在顶部切换业务地区或调整窗口筛选。\" />",
)

# Remove the duplicate preference store introduced during this turn. The existing
# config/marketPreference.ts remains the single source of truth.
duplicate = ROOT / "web/src/services/businessMarketPreferences.ts"
if duplicate.exists():
    duplicate.unlink()

# Replace the superseded one-shot test with a regression for the unified path.
test_path = ROOT / "web/pipeline/tests/test_business_market_preferences.py"
test_path.write_text(
    '''from pathlib import Path\nimport unittest\n\nROOT = Path(__file__).resolve().parents[2]\n\n\nclass BusinessMarketPreferenceTests(unittest.TestCase):\n    def read(self, relative: str) -> str:\n        return (ROOT / relative).read_text(encoding="utf-8")\n\n    def test_static_today_preserves_explicit_market_metadata(self):\n        source = self.read("src/services/StaticSnapshotTodayActionsService.ts")\n        self.assertIn("market_code: card.facts.market_code ?? null", source)\n        self.assertIn("market_name: card.facts.market_name ?? null", source)\n        self.assertIn("market_admin_code: card.facts.market_admin_code ?? null", source)\n\n    def test_one_market_preference_source_drives_public_and_api_services(self):\n        source = self.read("src/services/index.ts")\n        self.assertIn("marketCodesForSelection", source)\n        self.assertIn("new MarketScopedTodayActionsService(new PilotApiTodayActionsService(apiBaseUrl))", source)\n        self.assertIn("return this.delegate.getOpportunity(id)", source)\n        self.assertFalse((ROOT / "src/services/businessMarketPreferences.ts").exists())\n\n    def test_selector_is_explicit_business_scope_without_geolocation(self):\n        config = self.read("src/config/marketPreference.ts")\n        layout = self.read("src/components/layout/AppLayout.tsx")\n        self.assertIn("{ value: 'JJ', label: '京津' }", config)\n        self.assertIn("{ value: 'JJJ', label: '京津冀' }", config)\n        self.assertIn("{ value: 'NE3', label: '东北三省' }", config)\n        self.assertIn("{ value: 'ALL', label: '全部已开通' }", config)\n        self.assertIn("isApiMode || isVerifiedPublicDemo", layout)\n        for forbidden in ("geolocation", "navigator.geolocation", "ipLocation", "GPS"):\n            self.assertNotIn(forbidden, config)\n\n    def test_today_and_pool_show_same_global_business_scope(self):\n        today = self.read("src/pages/TodayPage.tsx")\n        pool = self.read("src/pages/OpportunityPoolPage.tsx")\n        self.assertIn("业务地区：{marketSelectionLabel()}", today)\n        self.assertNotIn("数据范围：天津公开采购", today)\n        self.assertIn("selectedMarketCodes", pool)\n        self.assertIn("业务地区：", pool)\n        self.assertNotIn("setMarketFilter", pool)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

print("unified market preference patch applied")
