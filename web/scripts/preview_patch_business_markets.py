from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch(path: str, old: str, new: str, expected: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"PATCH_COUNT {path}: expected {expected}, got {count}\n--- OLD ---\n{old}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Static snapshot: preserve explicit market fields, apply the saved business-market scope
# to list/Today surfaces, but keep direct detail/follow-up access intact.
patch(
    "web/src/services/StaticSnapshotTodayActionsService.ts",
    "import { personalizeTrialCards } from './localCustomerProfile'",
    "import { filterCardsByBusinessMarkets } from './businessMarketPreferences'\nimport { personalizeTrialCards } from './localCustomerProfile'",
)
patch(
    "web/src/services/StaticSnapshotTodayActionsService.ts",
    "const COVERAGE_WARNING = '天津 Pilot · 公开事实来自证据流水线快照；当前仍为部分来源覆盖。'",
    "const COVERAGE_WARNING = '已覆盖地区 · 公开事实来自证据流水线快照；当前仍为部分来源覆盖。'",
)
patch(
    "web/src/services/StaticSnapshotTodayActionsService.ts",
    "      region: card.facts.region,\n      lifecycle_stage: card.facts.lifecycle_state,",
    "      region: card.facts.region,\n      market_code: card.facts.market_code,\n      market_name: card.facts.market_name,\n      market_admin_code: card.facts.market_admin_code,\n      lifecycle_stage: card.facts.lifecycle_state,",
)
patch(
    "web/src/services/StaticSnapshotTodayActionsService.ts",
    """  private derivePool(\n    data: TodayActionsResponse,\n    includeInactive = false,\n  ): TodayActionCard[] {\n    const now = Date.now()\n    const publicPool = data.opportunity_pool?.length ? data.opportunity_pool : data.cards\n    const runtimeCards = publicPool\n      .map((card) => applyRuntimeActionability(card, now, includeInactive))\n      .filter((card): card is TodayActionCard => card !== null)\n    const followedCards = hydrateLocalFollowups(rerank(runtimeCards))\n    return personalizeTrialCards(followedCards)\n  }\n\n  private deriveLocalState(\n    data: TodayActionsResponse,\n    includeInactive = false,\n  ): TodayActionsResponse {\n    const now = Date.now()\n    const pool = this.derivePool(data, includeInactive)\n""",
    """  private derivePool(\n    data: TodayActionsResponse,\n    includeInactive = false,\n    applyBusinessMarketFilter = true,\n  ): TodayActionCard[] {\n    const now = Date.now()\n    const publicPool = data.opportunity_pool?.length ? data.opportunity_pool : data.cards\n    const runtimeCards = publicPool\n      .map((card) => applyRuntimeActionability(card, now, includeInactive))\n      .filter((card): card is TodayActionCard => card !== null)\n    const scopedCards = applyBusinessMarketFilter\n      ? filterCardsByBusinessMarkets(runtimeCards)\n      : runtimeCards\n    const followedCards = hydrateLocalFollowups(rerank(scopedCards))\n    return personalizeTrialCards(followedCards)\n  }\n\n  private deriveLocalState(\n    data: TodayActionsResponse,\n    includeInactive = false,\n    applyBusinessMarketFilter = true,\n  ): TodayActionsResponse {\n    const now = Date.now()\n    const pool = this.derivePool(data, includeInactive, applyBusinessMarketFilter)\n""",
)
patch(
    "web/src/services/StaticSnapshotTodayActionsService.ts",
    "const data = this.deriveLocalState(await this.ensureLoaded(), true)",
    "const data = this.deriveLocalState(await this.ensureLoaded(), true, false)",
    expected=2,
)

# Opportunity pool: replace the single-select filter with a persistent multi-market scope.
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'",
    """import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'\nimport {\n  BUSINESS_MARKETS,\n  businessMarketSelectionLabel,\n  cardMatchesBusinessMarkets,\n  isExactBusinessMarketSelection,\n  loadBusinessMarketPreferences,\n  saveBusinessMarketPreferences,\n  toggleBusinessMarket,\n  type BusinessMarketCode,\n} from '@/services/businessMarketPreferences'""",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "  const [marketFilter, setMarketFilter] = useState('ALL')",
    "  const [marketFilters, setMarketFilters] = useState<BusinessMarketCode[]>(() => loadBusinessMarketPreferences())",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "  const [error, setError] = useState(false)\n\n  useEffect(() => {",
    """  const [error, setError] = useState(false)\n\n  const updateMarketFilters = (next: BusinessMarketCode[]) => {\n    setMarketFilters(next)\n    saveBusinessMarketPreferences(next)\n  }\n\n  useEffect(() => {""",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    """  const marketOptions = useMemo(() => {\n    const markets = new Map<string, string>()\n    cards.forEach((card) => {\n      const code = card.facts.market_code?.trim().toUpperCase()\n      const name = card.facts.market_name?.trim()\n      if (code && name) markets.set(code, name)\n    })\n    const preferredOrder = ['TJ', 'BJ', 'HE', 'LN', 'JL', 'HL']\n    return [...markets.entries()]\n      .map(([code, name]) => ({ code, name }))\n      .sort((a, b) => {\n        const ai = preferredOrder.indexOf(a.code)\n        const bi = preferredOrder.indexOf(b.code)\n        if (ai !== -1 || bi !== -1) {\n          if (ai === -1) return 1\n          if (bi === -1) return -1\n          return ai - bi\n        }\n        return a.name.localeCompare(b.name, 'zh-CN')\n      })\n  }, [cards])\n\n""",
    "",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "      if (marketFilter !== 'ALL' && card.facts.market_code !== marketFilter) return false",
    "      if (!cardMatchesBusinessMarkets(card, marketFilters)) return false",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    "  }, [cards, marketFilter, query, windowFilter])",
    "  }, [cards, marketFilters, query, windowFilter])",
)
patch(
    "web/src/pages/OpportunityPoolPage.tsx",
    """          <label className=\"flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 text-[12px] text-slate-500\">\n            <span className=\"whitespace-nowrap\">业务地区</span>\n            <select\n              value={marketFilter}\n              onChange={(event) => setMarketFilter(event.target.value)}\n              className=\"min-w-24 bg-transparent font-medium text-slate-700 outline-none\"\n            >\n              <option value=\"ALL\">全部地区</option>\n              {marketOptions.map((market) => (\n                <option key={market.code} value={market.code}>{market.name}</option>\n              ))}\n            </select>\n          </label>\n""",
    """          <div className=\"flex min-h-10 flex-wrap items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 px-2 py-1 text-[12px] text-slate-500\">\n            <span className=\"whitespace-nowrap px-1\">业务地区：{businessMarketSelectionLabel(marketFilters)}</span>\n            <button\n              type=\"button\"\n              onClick={() => updateMarketFilters([])}\n              className={`rounded-lg px-2 py-1 font-medium ${marketFilters.length === 0 ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'}`}\n            >\n              全部\n            </button>\n            <button\n              type=\"button\"\n              onClick={() => updateMarketFilters(['TJ', 'BJ'])}\n              className={`rounded-lg px-2 py-1 font-medium ${isExactBusinessMarketSelection(marketFilters, ['TJ', 'BJ']) ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'}`}\n            >\n              京津\n            </button>\n            {BUSINESS_MARKETS.map((market) => (\n              <button\n                key={market.code}\n                type=\"button\"\n                onClick={() => updateMarketFilters(toggleBusinessMarket(marketFilters, market.code))}\n                className={`rounded-lg px-2 py-1 font-medium ${marketFilters.includes(market.code) ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'}`}\n              >\n                {market.name}\n              </button>\n            ))}\n          </div>\n""",
)

# Today: generic coverage wording and a truthful business-market scope label.
patch(
    "web/src/pages/TodayPage.tsx",
    "import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'",
    """import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'\nimport { businessMarketSelectionLabel, loadBusinessMarketPreferences } from '@/services/businessMarketPreferences'""",
)
patch(
    "web/src/pages/TodayPage.tsx",
    """function userCoverageWarning(value: string): string {\n  return value\n    .replace(\n      '天津 Pilot · 公开事实来自证据流水线快照；当前仍为部分来源覆盖。',\n      '天津公开采购 · 商机来自已核验官方公开信息；当前仍为部分来源覆盖。',\n    )\n    .split('天津 Pilot').join('天津公开采购')\n}\n""",
    """function userCoverageWarning(value: string): string {\n  return value\n    .replace(\n      '天津 Pilot · 公开事实来自证据流水线快照；当前仍为部分来源覆盖。',\n      '已覆盖地区 · 商机来自已核验官方公开信息；当前仍为部分来源覆盖。',\n    )\n    .split('天津 Pilot').join('已覆盖地区')\n    .split('天津公开采购').join('已覆盖地区')\n}\n""",
)
patch(
    "web/src/pages/TodayPage.tsx",
    "  const [outreachId, setOutreachId] = useState<string | null>(null)\n",
    "  const [outreachId, setOutreachId] = useState<string | null>(null)\n  const [businessMarkets] = useState(() => loadBusinessMarketPreferences())\n",
)
patch(
    "web/src/pages/TodayPage.tsx",
    "<span className=\"rounded-full border border-slate-200 bg-white px-2.5 py-1\">数据范围：天津公开采购</span>",
    "<span className=\"rounded-full border border-slate-200 bg-white px-2.5 py-1\">业务地区：{businessMarketSelectionLabel(businessMarkets)}</span>",
)

# Procurement-intent view: apply the same preference even in API mode.
patch(
    "web/src/pages/ProcurementIntentFollowupPage.tsx",
    "import { isAuthRequiredError } from '@/services/apiConfig'",
    "import { isAuthRequiredError } from '@/services/apiConfig'\nimport { filterCardsByBusinessMarkets } from '@/services/businessMarketPreferences'",
)
patch(
    "web/src/pages/ProcurementIntentFollowupPage.tsx",
    "    setCards(data.opportunity_pool ?? data.cards)",
    "    setCards(filterCardsByBusinessMarkets(data.opportunity_pool ?? data.cards))",
)
patch(
    "web/src/pages/ProcurementIntentFollowupPage.tsx",
    "        setCards(data.opportunity_pool ?? data.cards)",
    "        setCards(filterCardsByBusinessMarkets(data.opportunity_pool ?? data.cards))",
)

# Resources page: expose the persistent setting without mixing it into private relationship timestamps.
patch(
    "web/src/pages/ResourcesPage.tsx",
    "import { CAPABILITY_LABEL, RELATIONSHIP_LABEL } from '@/utils/labels'",
    """import {\n  BUSINESS_MARKETS,\n  businessMarketSelectionLabel,\n  isExactBusinessMarketSelection,\n  loadBusinessMarketPreferences,\n  saveBusinessMarketPreferences,\n  toggleBusinessMarket,\n  type BusinessMarketCode,\n} from '@/services/businessMarketPreferences'\nimport { CAPABILITY_LABEL, RELATIONSHIP_LABEL } from '@/utils/labels'""",
)
patch(
    "web/src/pages/ResourcesPage.tsx",
    "  const [profile, setProfile] = useState<LocalCustomerProfile>(() => loadLocalCustomerProfile())\n",
    """  const [profile, setProfile] = useState<LocalCustomerProfile>(() => loadLocalCustomerProfile())\n  const [businessMarkets, setBusinessMarkets] = useState<BusinessMarketCode[]>(() => loadBusinessMarketPreferences())\n""",
)
patch(
    "web/src/pages/ResourcesPage.tsx",
    "    saveLocalCustomerProfile(profile)\n",
    "    saveLocalCustomerProfile(profile)\n    saveBusinessMarketPreferences(businessMarkets)\n",
)
patch(
    "web/src/pages/ResourcesPage.tsx",
    """      <section className=\"rounded-2xl border border-slate-200 bg-white p-4 shadow-sm\">\n        <div className=\"flex flex-wrap items-center justify-between gap-2\">\n          <div>\n            <h3 className=\"text-[15px] font-semibold text-slate-900\">产品 / 服务能力</h3>\n""",
    """      <section className=\"rounded-2xl border border-slate-200 bg-white p-4 shadow-sm\">\n        <div>\n          <h3 className=\"text-[15px] font-semibold text-slate-900\">业务地区</h3>\n          <p className=\"mt-1 text-[12px] leading-5 text-slate-500\">\n            这是你主动选择的销售覆盖范围，不使用 GPS、IP 或设备定位，也不会被当成医院关系加分。空选择表示全部已覆盖地区；可以多选，例如天津+北京即“京津”。\n          </p>\n        </div>\n        <div className=\"mt-3 flex flex-wrap items-center gap-2\">\n          <button\n            type=\"button\"\n            onClick={() => setBusinessMarkets([])}\n            className={`rounded-lg border px-3 py-1.5 text-[12px] font-medium ${businessMarkets.length === 0 ? 'border-teal-200 bg-teal-50 text-teal-800' : 'border-slate-200 bg-white text-slate-600'}`}\n          >\n            全部已覆盖地区\n          </button>\n          <button\n            type=\"button\"\n            onClick={() => setBusinessMarkets(['TJ', 'BJ'])}\n            className={`rounded-lg border px-3 py-1.5 text-[12px] font-medium ${isExactBusinessMarketSelection(businessMarkets, ['TJ', 'BJ']) ? 'border-teal-200 bg-teal-50 text-teal-800' : 'border-slate-200 bg-white text-slate-600'}`}\n          >\n            京津\n          </button>\n          {BUSINESS_MARKETS.map((market) => (\n            <button\n              key={market.code}\n              type=\"button\"\n              onClick={() => setBusinessMarkets(toggleBusinessMarket(businessMarkets, market.code))}\n              className={`rounded-lg border px-3 py-1.5 text-[12px] font-medium ${businessMarkets.includes(market.code) ? 'border-teal-200 bg-teal-50 text-teal-800' : 'border-slate-200 bg-white text-slate-600'}`}\n            >\n              {market.name}\n            </button>\n          ))}\n        </div>\n        <p className=\"mt-2 text-[11px] text-slate-400\">当前：{businessMarketSelectionLabel(businessMarkets)}。保存后首页、商机池和采购意向跟进使用同一范围；历史跟进和直接详情不会被删除。</p>\n      </section>\n\n      <section className=\"rounded-2xl border border-slate-200 bg-white p-4 shadow-sm\">\n        <div className=\"flex flex-wrap items-center justify-between gap-2\">\n          <div>\n            <h3 className=\"text-[15px] font-semibold text-slate-900\">产品 / 服务能力</h3>\n""",
)

# Contract regression: keep the business-region selection explicit, shared, and independent from relationship data.
test_path = ROOT / "web/pipeline/tests/test_business_market_preferences.py"
test_path.write_text(
    '''from pathlib import Path\nimport unittest\n\nROOT = Path(__file__).resolve().parents[2]\n\n\nclass BusinessMarketPreferenceTests(unittest.TestCase):\n    def read(self, relative: str) -> str:\n        return (ROOT / relative).read_text(encoding="utf-8")\n\n    def test_static_snapshot_preserves_market_fields_and_filters_lists(self):\n        source = self.read("src/services/StaticSnapshotTodayActionsService.ts")\n        self.assertIn("market_code: card.facts.market_code", source)\n        self.assertIn("market_name: card.facts.market_name", source)\n        self.assertIn("market_admin_code: card.facts.market_admin_code", source)\n        self.assertIn("filterCardsByBusinessMarkets(runtimeCards)", source)\n        self.assertIn("deriveLocalState(await this.ensureLoaded(), true, false)", source)\n\n    def test_region_preference_is_separate_from_customer_relationship_profile(self):\n        preference = self.read("src/services/businessMarketPreferences.ts")\n        profile = self.read("src/services/localCustomerProfile.ts")\n        self.assertIn("medopp.business-markets.v1", preference)\n        self.assertNotIn("business_market_codes", profile)\n        self.assertIn("if (codes.length === 0) return true", preference)\n\n    def test_ui_supports_multi_market_and_jingjin_without_geolocation(self):\n        pool = self.read("src/pages/OpportunityPoolPage.tsx")\n        resources = self.read("src/pages/ResourcesPage.tsx")\n        today = self.read("src/pages/TodayPage.tsx")\n        self.assertIn("toggleBusinessMarket", pool)\n        self.assertIn("updateMarketFilters(['TJ', 'BJ'])", pool)\n        self.assertIn("业务地区", resources)\n        self.assertIn("不使用 GPS、IP 或设备定位", resources)\n        self.assertIn("businessMarketSelectionLabel(businessMarkets)", today)\n        self.assertNotIn("数据范围：天津公开采购", today)\n\n    def test_procurement_intent_uses_same_business_scope(self):\n        source = self.read("src/pages/ProcurementIntentFollowupPage.tsx")\n        self.assertGreaterEqual(source.count("filterCardsByBusinessMarkets"), 3)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

print("business-market patch applied")
