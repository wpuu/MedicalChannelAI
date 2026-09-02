from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class DiscoveryCoverageRiskUiTests(unittest.TestCase):
    def setUp(self):
        self.page = (WEB_ROOT / 'src' / 'pages' / 'DiscoveryRadarPage.tsx').read_text(encoding='utf-8')

    def test_risk_classifier_is_connected_to_radar_ui(self):
        self.assertIn("from '@/services/discoveryCoverageRisk'", self.page)
        self.assertIn('summarizeDiscoveryCoverageRisks(coverageRows)', self.page)
        self.assertIn('discoveryCoverageRisks(result)', self.page)

    def test_summary_exposes_coverage_gap_retry_and_continuation_counts(self):
        self.assertIn('覆盖缺口来源', self.page)
        self.assertIn('高风险需重试', self.page)
        self.assertIn('需续扫来源', self.page)
        self.assertIn('coverageSummary.affected_source_count', self.page)
        self.assertIn('coverageSummary.high_risk_source_count', self.page)
        self.assertIn('coverageSummary.continuation_candidate_source_count', self.page)

    def test_each_source_shows_chinese_reason_and_recommended_action(self):
        self.assertIn('coverageRiskLabel(risk.code)', self.page)
        self.assertIn('{risk.reason}', self.page)
        self.assertIn('{risk.recommended_action}', self.page)
        self.assertNotIn('>{risk.code}<', self.page)

    def test_coverage_ui_explains_score_separation(self):
        self.assertIn('覆盖完整度与AI发现分分开计算', self.page)
        self.assertIn('AI发现分高，不代表该公开渠道已经扫完整', self.page)


if __name__ == '__main__':
    unittest.main()
