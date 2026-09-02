from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class DiscoveryContinuationUiTests(unittest.TestCase):
    def setUp(self):
        self.app = (WEB_ROOT / 'src' / 'App.tsx').read_text(encoding='utf-8')
        self.route = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarRoute.tsx').read_text(encoding='utf-8')
        self.radar = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')
        self.panel = (WEB_ROOT / 'src' / 'components' / 'discovery' / 'DiscoveryContinuationDashboard.tsx').read_text(encoding='utf-8')
        self.provider = (WEB_ROOT / 'src' / 'components' / 'discovery' / 'DiscoveryWorkspaceProvider.tsx').read_text(encoding='utf-8')
        self.findings = (WEB_ROOT / 'src' / 'services' / 'discoveryContinuationFindings.ts').read_text(encoding='utf-8')

    def test_radar_route_mounts_shared_workspace_around_both_surfaces(self):
        self.assertIn('DiscoveryRadarRoute', self.app)
        self.assertIn('path="/radar" element={<DiscoveryRadarRoute />}', self.app)
        self.assertIn('<DiscoveryWorkspaceProvider>', self.route)
        self.assertIn('<DiscoveryRadarPage />', self.route)
        self.assertIn('<DiscoveryContinuationDashboard />', self.route)
        self.assertLess(self.route.index('<DiscoveryWorkspaceProvider>'), self.route.index('<DiscoveryRadarPage />'))
        self.assertGreater(self.route.index('</DiscoveryWorkspaceProvider>'), self.route.index('<DiscoveryContinuationDashboard />'))

    def test_root_and_continuation_use_same_workspace_context(self):
        self.assertIn('useDiscoveryWorkspace()', self.radar)
        self.assertIn('useDiscoveryWorkspace()', self.panel)
        self.assertIn('loadDiscoveryWorkspace()', self.provider)
        self.assertNotIn('loadDiscoveryWorkspaceDurable', self.panel)
        self.assertNotIn('WORKSPACE_REFRESH_MS', self.panel)
        self.assertNotIn('setInterval(', self.panel)
        self.assertNotIn('刷新根扫描状态', self.panel)

    def test_dashboard_only_surfaces_real_continuation_eligible_roots(self):
        self.assertIn('continuationEligible(row.root)', self.panel)
        self.assertIn('深分页补扫发现', self.panel)
        self.assertIn('仍有更深分页', self.panel)
        self.assertIn('80条窗口被截断', self.panel)
        self.assertNotIn('coverage_partial === true', self.panel)

    def test_dashboard_runs_bounded_segment_chain_and_displays_progress(self):
        self.assertIn('loadContinuationLedger', self.panel)
        self.assertIn('scanDiscoveryContinuation', self.panel)
        self.assertIn('appendContinuationSegment', self.panel)
        self.assertIn('continuationLedgerSummary', self.panel)
        self.assertIn('安全续扫下一段', self.panel)
        self.assertIn('续扫 {summary?.segment_count ?? 0}/5 段', self.panel)
        self.assertIn('已确认到达末页', self.panel)
        self.assertIn('补扫新链接', self.panel)
        self.assertIn('补扫候选', self.panel)

    def test_continuation_keeps_segment_ledger_but_merges_candidates_into_main_findings(self):
        self.assertIn('独立 IndexedDB segment 账本', self.panel)
        self.assertIn('不覆盖首页增量快照', self.panel)
        self.assertIn('mergeDiscoveryContinuationIntoWorkspace', self.panel)
        self.assertIn('按 source + 官方URL 无损并入', self.panel)
        self.assertIn('findingKey(segment.source_id, candidate.url)', self.findings)
        self.assertIn("existing.last_seen_at === segment.checked_at", self.findings)
        self.assertIn('times_seen: (previous?.times_seen ?? 0) + 1', self.findings)
        self.assertIn('sourceStillExists', self.findings)

    def test_hydrated_segments_are_reconciled_idempotently(self):
        self.assertIn('for (const segment of ledger.segments)', self.panel)
        self.assertIn('mergeDiscoveryContinuationIntoWorkspace(next, segment)', self.panel)
        self.assertIn('if (existing.last_seen_at === segment.checked_at || existingAt > observedAt) continue', self.findings)

    def test_dashboard_keeps_shadow_verification_boundary_visible(self):
        self.assertIn('AI新候选 · 待核验', self.panel)
        self.assertIn('独立核验已命中', self.panel)
        self.assertIn('打开已核验商机', self.panel)


if __name__ == '__main__':
    unittest.main()
