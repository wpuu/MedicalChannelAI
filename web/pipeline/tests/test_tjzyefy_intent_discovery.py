from __future__ import annotations

import unittest
from datetime import date

from medical_channel_pipeline.tjzyefy_intent_discovery import (
    TjzyefyIntentDiscoveryError,
    parse_tjzyefy_intent_index_html,
    select_intent_candidates_since,
    stable_intent_opportunity_id,
)


class TjzyefyIntentDiscoveryTests(unittest.TestCase):
    def test_discovery_is_broad_across_official_procurement_intents(self) -> None:
        html = '''
        <a href="/system/2026/06/19/030192700.shtml">采购意向公告（2026年24号）-流式细胞仪等医疗设备采购项目</a>
        <a href="/system/2026/06/19/030192699.shtml">采购意向公告（2026年23号）-脉动真空灭菌器等设备采购项目</a>
        <a href="/system/2026/06/19/030192701.shtml">采购意向公告（2026年25号）-2026年景区年票采购项目</a>
        <a href="/system/2026/06/19/030192702.shtml">院内调研公告（2026年12号）-除颤仪医疗设备采购项目</a>
        '''
        rows = parse_tjzyefy_intent_index_html(html)
        self.assertEqual(len(rows), 3)
        self.assertTrue(any('景区年票' in row.title for row in rows))
        self.assertFalse(any('院内调研' in row.title for row in rows))

    def test_non_official_index_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(TjzyefyIntentDiscoveryError, 'TJZYEFY_INTENT_INDEX_HOST_REJECTED'):
            parse_tjzyefy_intent_index_html(
                '<a href="/system/2026/06/19/1.shtml">采购意向公告-医疗设备</a>',
                index_url='https://example.com/xwgg/ggtz/',
            )

    def test_date_window_and_candidate_cap_are_bounded(self) -> None:
        html = ''.join(
            f'<a href="/system/2026/06/{day:02d}/{300000 + day}.shtml">采购意向公告（2026年{day}号）-医疗设备采购项目</a>'
            for day in range(1, 11)
        )
        rows = parse_tjzyefy_intent_index_html(html)
        selected = select_intent_candidates_since(
            rows,
            start_date=date(2026, 6, 5),
            end_date=date(2026, 6, 10),
            max_candidates=3,
        )
        self.assertEqual(len(selected), 3)
        self.assertTrue(all(row.published_at >= '2026-06-05' for row in selected))

    def test_stable_id_is_intent_namespaced(self) -> None:
        value = stable_intent_opportunity_id(
            'https://www.tjzyefy.com/system/2026/06/19/030192700.shtml'
        )
        self.assertEqual(value, 'tjzyefy_intent_20260619_030192700')


if __name__ == '__main__':
    unittest.main()
