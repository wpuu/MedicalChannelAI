from __future__ import annotations

import unittest
from datetime import date

from medical_channel_pipeline.tjzxfc_discovery import (
    INDEX_URL,
    TjzxfcDiscoveryError,
    parse_tjzxfc_index_html,
    select_candidates_since,
    stable_opportunity_id,
)


class TjzxfcDiscoveryTests(unittest.TestCase):
    def test_official_index_discovers_market_research_without_guessing_medical_scope(self) -> None:
        html = '''
        <ul>
          <li><a href="/system/2026/08/20/030333150.shtml">设备科发布医用设备市场调研（2026-08-20）</a></li>
          <li><a href="/system/2026/08/17/030331860.shtml">天津市中心妇产科医院报告厅提升改造项目市场调研邀请公告</a></li>
          <li><a href="/system/2026/08/27/030336273.shtml">天津市中心妇产科医院设备维修询价公告</a></li>
          <li><a href="https://evil.example/system/2026/08/21/999.shtml">市场调研公告</a></li>
        </ul>
        '''
        rows = parse_tjzxfc_index_html(html)
        self.assertEqual([row.published_at for row in rows], ['2026-08-20', '2026-08-17'])
        self.assertEqual(rows[0].detail_url, 'https://www.tjzxfc.cn/system/2026/08/20/030333150.shtml')
        self.assertNotIn('询价公告', ' '.join(row.title for row in rows))

    def test_date_window_and_candidate_cap_are_bounded(self) -> None:
        html = ''.join(
            f'<a href="/system/2026/08/{day:02d}/{30000000 + day}.shtml">设备项目市场调研公告 {day}</a>'
            for day in range(10, 21)
        )
        rows = parse_tjzxfc_index_html(html)
        selected = select_candidates_since(
            rows,
            start_date=date(2026, 8, 15),
            end_date=date(2026, 8, 20),
            max_candidates=3,
        )
        self.assertEqual([row.published_at for row in selected], ['2026-08-20', '2026-08-19', '2026-08-18'])

    def test_stable_id_uses_official_detail_path_identity(self) -> None:
        self.assertEqual(
            stable_opportunity_id('https://www.tjzxfc.cn/system/2026/03/31/030269964.shtml'),
            'tjzxfc_20260331_030269964',
        )
        with self.assertRaises(TjzxfcDiscoveryError):
            stable_opportunity_id('https://www.tjzxfc.cn/ywgk/zbgg/index.shtml')

    def test_non_official_index_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(TjzxfcDiscoveryError, 'TJZXFC_INDEX_HOST_REJECTED'):
            parse_tjzxfc_index_html('<a href="/system/2026/08/20/1.shtml">市场调研公告</a>', index_url='https://example.com/index.shtml')

    def test_current_index_contract_is_the_official_tender_notice_column(self) -> None:
        self.assertEqual(INDEX_URL, 'https://www.tjzxfc.cn/ywgk/zbgg/index.shtml')


if __name__ == '__main__':
    unittest.main()
