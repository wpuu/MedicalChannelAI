from __future__ import annotations

import unittest
from datetime import date

from medical_channel_pipeline.tjzyefy_discovery import (
    INDEX_URL,
    TjzyefyDiscoveryError,
    parse_tjzyefy_index_html,
    select_candidates_since,
    stable_opportunity_id,
)


class TjzyefyDiscoveryTests(unittest.TestCase):
    def test_discovers_medical_equipment_and_consumables_research_only(self) -> None:
        html = '''
        <a href="/system/2026/07/31/030195805.shtml">医用耗材（试剂）调研公告（2026年13号）-脱脂棉纱布耗材采购项目</a>
        <a href="/system/2026/07/01/030193522.shtml">院内调研公告（2026年14号）-多导睡眠监测系统等医疗设备采购项目</a>
        <a href="/system/2026/06/01/030191557.shtml">天津中医药大学第二附属医院院内调研公告--医院招标代理服务项目</a>
        <a href="/system/2026/08/01/030200001.shtml">采购意向公告（2026年24号）-流式细胞仪等医疗设备采购项目</a>
        '''
        result = parse_tjzyefy_index_html(html)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].published_at, '2026-07-31')
        self.assertIn('脱脂棉纱布', result[0].title)
        self.assertEqual(result[1].published_at, '2026-07-01')
        self.assertIn('多导睡眠监测系统', result[1].title)

    def test_rejects_foreign_detail_host_and_deduplicates(self) -> None:
        html = '''
        <a href="https://evil.example/system/2026/07/31/030195805.shtml">医用耗材（试剂）调研公告-耗材采购项目</a>
        <a href="/system/2026/07/31/030195805.shtml">医用耗材（试剂）调研公告-耗材采购项目</a>
        <a href="/system/2026/07/31/030195805.shtml">医用耗材（试剂）调研公告-耗材采购项目</a>
        '''
        result = parse_tjzyefy_index_html(html)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].detail_url.startswith('https://www.tjzyefy.com/'))

    def test_stable_id_uses_official_url_date_and_item_id(self) -> None:
        self.assertEqual(
            stable_opportunity_id('https://www.tjzyefy.com/system/2026/07/31/030195805.shtml'),
            'tjzyefy_20260731_030195805',
        )

    def test_select_candidates_respects_date_window_and_limit(self) -> None:
        html = ''.join(
            f'<a href="/system/2026/07/{day:02d}/03019{day:04d}.shtml">院内调研公告-测试医疗设备采购项目</a>'
            for day in (1, 2, 3, 4)
        )
        candidates = parse_tjzyefy_index_html(html)
        selected = select_candidates_since(
            candidates,
            start_date=date(2026, 7, 2),
            end_date=date(2026, 7, 4),
            max_candidates=2,
        )
        self.assertEqual([item.published_at for item in selected], ['2026-07-04', '2026-07-03'])

    def test_index_host_is_fail_closed(self) -> None:
        with self.assertRaisesRegex(TjzyefyDiscoveryError, 'TJZYEFY_INDEX_HOST_REJECTED'):
            parse_tjzyefy_index_html('<html></html>', index_url='https://example.com/not-official')

    def test_public_index_constant_is_official_https(self) -> None:
        self.assertEqual(INDEX_URL, 'https://www.tjzyefy.com/xwgg/ggtz/')


if __name__ == '__main__':
    unittest.main()
