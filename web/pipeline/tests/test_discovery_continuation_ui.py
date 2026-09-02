from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class DiscoveryContinuationUiTests(unittest.TestCase):
    def setUp(self):
        self.app = (WEB_ROOT / 'src' / 'App.tsx').read_text(encoding='utf-8')
        self.route = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarRoute.tsx').read_text(encoding='utf-8')
        self.panel = (WEB_ROOT / 'src' / 'components' / 'discovery' / 'DiscoveryContinuationDashboard.tsx').read_text(encoding='utf-8')

    def test_radar_route_mounts_root_radar_and_continuation_dashboard(self):
        self.assertIn('DiscoveryRadarRoute', self.app)
        self.assertIn('path="/radar" element={<DiscoveryRadarRoute />}', self.app)
        self.assertIn('<DiscoveryRadarPage />', self.route)
        self.assertIn('<DiscoveryContinuationDashboard />', self.route)

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

    def test_dashboard_keeps_continuation_as_independent_local_ledger_until_shared_state(self):
        self.assertIn('独立 IndexedDB segment 账本', self.panel)
        self.assertIn('不覆盖首页增量快照', self.panel)
        self.assertIn('当前刻意不让这个组件直接改写“累计保存的AI发现”主账本', self.panel)
        self.assertNotIn('saveDiscoveryWorkspace(', self.panel)
        self.assertNotIn('mergeDiscoveryFindings', self.panel)

    def test_dashboard_keeps_shadow_verification_boundary_visible(self):
        self.assertIn('AI新候选 · 待核验', self.panel)
        self.assertIn('独立核验已命中', self.panel)
        self.assertIn('打开已核验商机', self.panel)
        self.assertIn('WORKSPACE_REFRESH_MS = 5000', self.panel)


if __name__ == '__main__':
    unittest.main()
