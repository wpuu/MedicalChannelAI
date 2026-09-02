from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class AiDiscoveryRadarContractTests(unittest.TestCase):
    def test_live_radar_scope_is_user_managed_not_fixed_to_three_hospitals(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        self.assertIn('sourceFromBody(body)', endpoint)
        self.assertIn("body?.source", endpoint)
        self.assertNotIn('const SOURCES = {', endpoint)
        self.assertIn('添加渠道', page)
        self.assertIn('修改', page)
        self.assertIn('停用', page)
        self.assertIn('删除', page)
        self.assertIn('STARTER_SOURCES', store)
        self.assertIn("origin: 'STARTER'", store)

    def test_user_managed_source_fetch_has_public_network_guards(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        self.assertIn("parsed.protocol !== 'https:'", endpoint)
        self.assertIn('assertPublicHostname', endpoint)
        self.assertIn('privateIp(', endpoint)
        self.assertIn("redirect: 'manual'", endpoint)
        self.assertIn('SOURCE_REDIRECT_REJECTED', endpoint)
        self.assertIn('MAX_SOURCE_BYTES', endpoint)

    def test_radar_reuses_saved_result_when_official_link_fingerprint_is_unchanged(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        service = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarApi.ts').read_text(encoding='utf-8')
        store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn('anchorFingerprint(anchors)', endpoint)
        self.assertIn('reusablePreviousScan', endpoint)
        self.assertIn("cache_status: aiCalled ? 'FRESH_AI' : 'REUSED_UNCHANGED'", endpoint)
        self.assertIn('ai_called: aiCalled', endpoint)
        self.assertIn('previous_scan', service)
        self.assertIn('medicalchannelai.discovery.workspace.v2', store)
        self.assertIn('saveDiscoveryWorkspace', page)
        self.assertIn('官网未变化 · 复用保存结果', page)

    def test_source_health_metrics_support_channel_optimization(self):
        store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn('consecutive_failure_count', store)
        self.assertIn('consecutive_zero_candidate_count', store)
        self.assertIn("return 'REVIEW'", store)
        self.assertIn("return 'LOW_YIELD'", store)
        self.assertIn('建议检查或停用', page)
        self.assertIn('低价值渠道', page)

    def test_radar_is_shadow_only_and_rejects_ungrounded_model_urls(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        self.assertIn('production_data_mutated: false', endpoint)
        self.assertIn('DISCOVERED_UNVERIFIED', endpoint)
        self.assertIn('const anchor = allowed.get(rawUrl)', endpoint)
        self.assertIn('rejectedUngrounded += 1', endpoint)
        self.assertNotIn('publish_web_snapshot', endpoint)
        self.assertNotIn('private_followups', endpoint)

    def test_radar_has_same_origin_rate_limit_and_cost_guards(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        self.assertIn('sameOriginAllowed(request)', endpoint)
        self.assertIn('rateLimited(request)', endpoint)
        self.assertIn('AI_RADAR_RATE_LIMITED', endpoint)
        self.assertIn('MAX_ANCHORS = 80', endpoint)
        self.assertIn('PROVIDER_TIMEOUT_MS = 12_000', endpoint)

    def test_radar_score_only_uses_gold_visible_to_current_scan(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        script = (WEB_ROOT / 'pipeline' / 'scripts' / 'run_agnes_discovery_benchmark.py').read_text(encoding='utf-8')
        self.assertIn('function currentBenchmarkUrls(verifiedUrls, anchors)', endpoint)
        self.assertIn('analyzedUrlSet.has(url)', endpoint)
        self.assertIn("benchmark_scope: 'CURRENT_ANALYZED_OFFICIAL_LINKS'", endpoint)
        self.assertIn('historical_known_verified_count', endpoint)
        self.assertIn('current_anchor_urls = {item.url for item in anchors}', script)
        self.assertIn('gold_urls = historical_gold_urls & current_anchor_urls', script)
        self.assertIn('CURRENT_FETCHED_OFFICIAL_LINKS_WITH_KNOWN_VERIFIED_GOLD', script)

    def test_verified_ai_hit_can_open_the_independently_verified_opportunity(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        service = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarApi.ts').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn('verifiedOpportunityMapForSource', endpoint)
        self.assertIn('opportunity_id: benchmark.map.get(item.url) || null', endpoint)
        self.assertIn('opportunity_id: string | null', service)
        self.assertIn('打开已核验商机', page)
        self.assertIn('AI发现分', page)

    def test_radar_page_is_reachable_and_explains_verification_boundary(self):
        app = (WEB_ROOT / 'src' / 'App.tsx').read_text(encoding='utf-8')
        layout = (WEB_ROOT / 'src' / 'components' / 'layout' / 'AppLayout.tsx').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn('path="/radar"', app)
        self.assertIn('to="/radar"', layout)
        self.assertIn('用户控制扫描范围', page)
        self.assertIn('新候选仍需独立官方事实核验', page)
        self.assertIn('拒绝内网地址、跨域跳转和模型编造链接', page)


if __name__ == '__main__':
    unittest.main()
