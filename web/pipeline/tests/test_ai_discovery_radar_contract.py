from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class AiDiscoveryRadarContractTests(unittest.TestCase):
    def test_live_radar_scope_is_user_managed_and_starts_empty(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        self.assertIn('sourceFromBody(body)', endpoint)
        self.assertIn("body?.source", endpoint)
        self.assertNotIn('const SOURCES = {', endpoint)
        self.assertIn('sources: []', store)
        self.assertNotIn('STARTER_SOURCES', store)
        self.assertIn('新工作区默认没有医院', page)
        self.assertIn('添加渠道', page)
        self.assertIn('修改', page)
        self.assertIn('停用', page)
        self.assertIn('删除', page)

    def test_bulk_import_is_explicit_user_input_not_hidden_hospital_registry(self):
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn('批量导入', page)
        self.assertIn('医院/机构名称 | https://官方栏目地址', page)
        self.assertIn('范围 | 医院/机构名称 | https://官方栏目地址', page)
        self.assertIn('importBulkSources', page)
        self.assertIn('导入并加入扫描范围', page)
        self.assertNotIn('天津医科大学总医院', page)
        self.assertNotIn('天津泰达医院', page)

    def test_region_scope_groups_many_real_sources_without_claiming_magic_full_web_search(self):
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        self.assertIn('scope: string', store)
        self.assertIn('scanScope', page)
        self.assertIn('区域大范围增量搜索', page)
        self.assertIn('扫描{scope}全部', page)
        self.assertIn('天津市', page)
        self.assertIn('不把“天津市”三个字当成全网无遗漏保证', page)
        self.assertIn('MULTI_SCAN_GAP_MS = 2200', page)

    def test_user_managed_source_fetch_has_public_network_guards(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        self.assertIn("parsed.protocol !== 'https:'", endpoint)
        self.assertIn('assertPublicHostname', endpoint)
        self.assertIn('privateIp(', endpoint)
        self.assertIn("redirect: 'manual'", endpoint)
        self.assertIn('SOURCE_REDIRECT_REJECTED', endpoint)
        self.assertIn('MAX_SOURCE_BYTES', endpoint)

    def test_safe_next_page_coverage_is_bounded_and_same_origin(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        service = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarApi.ts').read_text(encoding='utf-8')
        self.assertIn('MAX_COVERAGE_PAGES = 2', endpoint)
        self.assertIn('NEXT_PAGE_LABELS', endpoint)
        self.assertIn('extractNextPageUrl', endpoint)
        self.assertIn("canonicalOfficialUrl(href, baseUrl, source.hosts)", endpoint)
        self.assertIn('fetchOfficialCoverage(source)', endpoint)
        self.assertIn('if (anchorByUrl.size >= MAX_ANCHORS) break', endpoint)
        self.assertIn('coverage_page_count', endpoint)
        self.assertIn('coverage_page_urls', endpoint)
        self.assertIn('coverage_next_page_detected', endpoint)
        self.assertIn('coverage_page_limit_applied', endpoint)
        self.assertIn('coverage_page_count: number', service)
        self.assertIn('coverage_page_urls: string[]', service)
        self.assertIn('body.coverage_page_count !== body.coverage_page_urls.length', service)

    def test_radar_reuses_saved_result_when_official_link_fingerprint_is_unchanged(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        service = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarApi.ts').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn('anchorFingerprint(anchors)', endpoint)
        self.assertIn('previousScanContext', endpoint)
        self.assertIn("cacheStatus: 'REUSED_UNCHANGED'", endpoint)
        self.assertIn('aiCalled: false', endpoint)
        self.assertIn('previous_scan', service)
        self.assertIn('官网链接未变化 · 未调用AI', page)

    def test_changed_source_only_sends_new_or_changed_anchors_to_ai(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        service = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarApi.ts').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn('anchor_snapshot', service)
        self.assertIn('previousAnchorSnapshot', endpoint)
        self.assertIn('newAnchors', endpoint)
        self.assertIn('changedAnchors', endpoint)
        self.assertIn('removedAnchors', endpoint)
        self.assertIn('deltaAnchors: [...newAnchors, ...changedAnchors]', endpoint)
        self.assertIn('const aiAnchors = previous ? previous.deltaAnchors : anchors', endpoint)
        self.assertIn("cacheStatus: previous ? 'FRESH_DELTA_AI' : 'FRESH_AI'", endpoint)
        self.assertIn('ai_analyzed_anchor_count', endpoint)
        self.assertIn('new_anchor_count', endpoint)
        self.assertIn('changed_anchor_count', endpoint)
        self.assertIn('removed_anchor_count', endpoint)
        self.assertIn('旧链接不会重复交给AI', page)
        self.assertIn('AI仅分析', page)

    def test_anchor_fingerprint_is_order_independent_so_reordering_does_not_waste_ai(self):
        endpoint = (WEB_ROOT / 'api' / 'ai' / 'discover.js').read_text(encoding='utf-8')
        self.assertIn(".sort((a, b) => a[0].localeCompare(b[0])", endpoint)
        self.assertIn("'REUSED_NO_NEW_LINKS'", endpoint)

    def test_saved_findings_survive_new_scans_and_are_deduplicated_by_source_and_url(self):
        store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn('interface DiscoveryFinding', store)
        self.assertIn('mergeDiscoveryFindings', store)
        self.assertIn('first_seen_at', store)
        self.assertIn('last_seen_at', store)
        self.assertIn('times_seen', store)
        self.assertIn('active_in_latest_scan', store)
        self.assertIn('findingKey(result.source_id, candidate.url)', store)
        self.assertIn('累计保存的AI发现', page)
        self.assertIn('新一轮扫描不会覆盖旧发现', page)
        self.assertIn('历史已保存', page)
        self.assertIn('FINDINGS_RENDER_LIMIT = 500', page)

    def test_heavy_local_radar_state_uses_indexeddb_before_cloud(self):
        store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.assertIn("indexedDB.open(DB_NAME, DB_VERSION)", store)
        self.assertIn('loadDiscoveryWorkspaceDurable', store)
        self.assertIn('writeIndexedWorkspace', store)
        self.assertIn('navigator.storage.estimate()', store)
        self.assertIn('navigator.storage.persist()', store)
        self.assertIn("mode: 'INDEXED_DB'", store)
        self.assertIn("'LOCAL_STORAGE_FALLBACK'", store)
        self.assertIn('storageReady', page)
        self.assertIn('本地发现账本', page)
        self.assertIn('IndexedDB', page)
        self.assertIn('localStorage 只保留轻量启动信息', page)

    def test_legacy_live_templates_are_not_migrated_into_new_user_scope(self):
        store = (WEB_ROOT / 'src' / 'services' / 'discoveryRadarStore.ts').read_text(encoding='utf-8')
        self.assertIn('LEGACY_STORAGE_KEY', store)
        self.assertIn("source.origin === 'USER'", store)
        self.assertNotIn("origin: 'STARTER'", store)

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
        self.assertIn('MAX_REQUEST_BODY_BYTES = 262_144', endpoint)

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
        self.assertIn('区域增量搜索', page)
        self.assertIn('独立核验前不发布', page)
        self.assertIn('单个入口当前分析当前页最多80个官方链接', page)


if __name__ == '__main__':
    unittest.main()
