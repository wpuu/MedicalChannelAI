from __future__ import annotations

import unittest
from datetime import date

from medical_channel_pipeline.tjfch_discovery import (
    INDEX_URL,
    TjfchDiscoveryError,
    parse_tjfch_index_html,
    select_candidates_since,
    stable_opportunity_id,
)


class TjfchDiscoveryTests(unittest.TestCase):
    def test_official_procurement_announcements_are_discovered_and_result_notices_are_excluded(self) -> None:
        html = '''
        <html><body>
          <a href="/system/2026/05/06/030189759.shtml">天津市第一中心医院手术无影灯采购项目院内比选公告</a>
          <a href="/system/2026/05/20/030190001.shtml">天津市第一中心医院手术无影灯采购项目成交公告</a>
          <a href="/system/2026/06/18/030192813.shtml">天津市第一中心医院26-27年度SSL域名证书安全运维项目院内比选公告</a>
          <a href="https://evil.example/system/2026/06/19/123.shtml">院内比选采购公告</a>
        </body></html>
        '''
        candidates = parse_tjfch_index_html(html)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].published_at, '2026-06-18')
        self.assertEqual(candidates[1].published_at, '2026-05-06')
        self.assertEqual(
            stable_opportunity_id(candidates[1].detail_url),
            'tjfch_20260506_030189759',
        )

    def test_candidate_window_is_bounded_by_official_url_date(self) -> None:
        html = '''
        <a href="/system/2026/05/06/030189759.shtml">手术无影灯采购项目院内比选公告</a>
        <a href="/system/2026/06/18/030192813.shtml">SSL域名证书安全运维项目院内比选公告</a>
        '''
        candidates = parse_tjfch_index_html(html)
        selected = select_candidates_since(
            candidates,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
            max_candidates=10,
        )
        self.assertEqual([item.published_at for item in selected], ['2026-06-18'])

    def test_stable_id_rejects_non_official_detail_shape(self) -> None:
        with self.assertRaisesRegex(TjfchDiscoveryError, 'TJFCH_DETAIL_URL_ID_NOT_FOUND'):
            stable_opportunity_id('https://www.tjfch.com.cn/ywgk/ynbx/index.shtml')

    def test_index_url_is_the_current_official_procurement_column(self) -> None:
        self.assertEqual(INDEX_URL, 'https://www.tjfch.com.cn/ywgk/ynbx/index.shtml')

    def test_legacy_broken_tls_domain_is_not_accepted_as_official_index(self) -> None:
        with self.assertRaisesRegex(TjfchDiscoveryError, 'TJFCH_INDEX_HOST_REJECTED'):
            parse_tjfch_index_html(
                '<a href="/system/2026/08/31/030197542.shtml">天津市第一中心医院科教处工服采购项目院内比选公告</a>',
                index_url='https://www.tj-fch.com/ywgk/ynbx/index.shtml',
            )


if __name__ == '__main__':
    unittest.main()
