from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / 'web' / 'src' / 'pages' / 'ProcurementIntentFollowupPage.tsx'
NOTICE = ROOT / 'web' / 'src' / 'components' / 'followup' / 'OfficialFollowupSourceNotice.tsx'


class ProcurementIntentFollowupSourceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = PAGE.read_text(encoding='utf-8')
        cls.notice = NOTICE.read_text(encoding='utf-8')

    def test_notice_only_uses_verified_quality_flag_contract(self) -> None:
        self.assertIn("OFFICIAL_FOLLOWUP_SOURCE_PREFIX = 'OFFICIAL_FOLLOWUP_SOURCE='", self.notice)
        self.assertIn("const TIANJIN_GPC = 'TIANJIN_GPC'", self.notice)
        self.assertIn("const CEB_PUBLIC_SERVICE = 'CEB_PUBLIC_SERVICE'", self.notice)
        self.assertIn('qualityFlags={intent.facts.quality_flags}', self.page)
        self.assertNotIn('customer_context', self.notice)
        self.assertNotIn('hospital_relationship', self.notice)

    def test_tianjin_and_ceb_have_distinct_operational_copy(self) -> None:
        self.assertIn('已纳入定向自动补搜', self.notice)
        self.assertIn('当前需人工核验', self.notice)
        self.assertIn('自动未发现不代表没有正式公告', self.notice)
        self.assertIn('https://tjgpc.zwfwb.tj.gov.cn/', self.notice)
        self.assertIn('https://ctbpsp.com/#/', self.notice)

    def test_manual_platform_link_never_mutates_business_state(self) -> None:
        self.assertIn('不会自动标记为已联系、已跟进', self.notice)
        self.assertNotIn('updateFollowup', self.notice)
        self.assertNotIn('fetch(', self.notice)
        self.assertNotIn('/api/', self.notice)
        self.assertNotIn('cutominfoapi', self.notice)

    def test_page_surfaces_search_term_without_inventing_formal_facts(self) -> None:
        self.assertIn('productNames={(intent.facts.products ?? []).map((item) => item.name)}', self.page)
        self.assertIn('建议核查关键词：', self.notice)
        self.assertNotIn('项目编号', self.notice)
        self.assertNotIn('投标截止', self.notice)
        self.assertNotIn('中标人', self.notice)


if __name__ == '__main__':
    unittest.main()
