from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class DiscoveryCoverageRiskTests(unittest.TestCase):
    def setUp(self):
        self.source = (WEB_ROOT / 'src' / 'services' / 'discoveryCoverageRisk.ts').read_text(encoding='utf-8')

    def test_partial_page_is_high_risk_but_not_a_continuation_cursor(self):
        self.assertIn("'OPTIONAL_PAGE_INCOMPLETE'", self.source)
        partial = self.source[self.source.index('if (result.coverage_partial)'):self.source.index('if (result.coverage_page_limit_applied)')]
        self.assertIn("'HIGH'", partial)
        self.assertIn('优先重试当前渠道', partial)
        self.assertIn('false,', partial)

    def test_page_limit_and_anchor_cap_are_explicit_continuation_candidates(self):
        self.assertIn("'DEEP_PAGINATION_REMAINS'", self.source)
        self.assertIn("'ANCHOR_WINDOW_CAPPED'", self.source)
        self.assertGreaterEqual(self.source.count('true,'), 2)
        self.assertIn('不能覆盖根入口的增量快照', self.source)
        self.assertIn('不把截断窗口标记为完整覆盖', self.source)

    def test_coverage_risk_is_not_folded_into_ai_discovery_score(self):
        self.assertIn('Coverage risk is deliberately separate from discovery quality/score.', self.source)
        self.assertNotIn('discovery_score:', self.source)
        self.assertNotIn('known_recall:', self.source)

    def test_summary_deduplicates_sources_and_separates_risk_reasons(self):
        self.assertIn('affectedSourceIds = new Set', self.source)
        self.assertIn('highRiskSourceIds = new Set', self.source)
        self.assertIn('continuationSourceIds = new Set', self.source)
        self.assertIn('partial_source_count:', self.source)
        self.assertIn('deep_pagination_source_count:', self.source)
        self.assertIn('anchor_cap_source_count:', self.source)
        self.assertIn('continuation_candidate_source_count:', self.source)


if __name__ == '__main__':
    unittest.main()
