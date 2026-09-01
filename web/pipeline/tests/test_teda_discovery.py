from __future__ import annotations

import unittest

from medical_channel_pipeline.teda_discovery import (
    TedaDiscoveryError,
    index_page_url,
    parse_teda_index_html,
    stable_opportunity_id,
)

INDEX_FIXTURE = """
<html><body>
<a href="/article/show/9/901">天津市泰达医院生物安全柜设备需求调研</a>
<a href="https://tedahospital.com.cn/article/show/9/732">天津市泰达医院 高压氧舱介绍论证邀请公告</a>
<a href="/article/show/9/899">天津市泰达医院GCP改造项目招标公告</a>
<a href="/article/show/9/889">防统方系统采购项目中标公告</a>
<a href="https://example.com/article/show/9/999">某设备需求调研</a>
</body></html>
"""


class TedaDiscoveryTests(unittest.TestCase):
    def test_index_keeps_only_official_early_signal_titles(self) -> None:
        candidates = parse_teda_index_html(INDEX_FIXTURE)
        self.assertEqual([item.title for item in candidates], [
            '天津市泰达医院生物安全柜设备需求调研',
            '天津市泰达医院 高压氧舱介绍论证邀请公告',
        ])
        self.assertTrue(all(item.detail_url.startswith('https://') for item in candidates))

    def test_stable_id_uses_official_article_id(self) -> None:
        self.assertEqual(
            stable_opportunity_id('https://www.tedahospital.com.cn/article/show/9/901'),
            'teda_901',
        )

    def test_pagination_contract_is_bounded_and_deterministic(self) -> None:
        self.assertEqual(index_page_url(1), 'https://www.tedahospital.com.cn/article/plist/9')
        self.assertEqual(index_page_url(4), 'https://www.tedahospital.com.cn/article/plist/9/4')
        with self.assertRaisesRegex(ValueError, 'TEDA_PAGE_INVALID'):
            index_page_url(0)

    def test_non_official_index_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(TedaDiscoveryError, 'INDEX_HOST_REJECTED'):
            parse_teda_index_html(INDEX_FIXTURE, index_url='https://example.com/article/plist/9')


if __name__ == '__main__':
    unittest.main()
