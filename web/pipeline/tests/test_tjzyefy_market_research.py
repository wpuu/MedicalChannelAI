from __future__ import annotations

import unittest

from medical_channel_pipeline.tjzyefy_market_research import (
    TjzyefyParseError,
    parse_tjzyefy_market_research,
)

INDEX_URL = 'https://www.tjzyefy.com/xwgg/ggtz/'
OBSERVED_AT = '2026-09-04T10:00:00+00:00'


def detail_html(title: str, published: str, body: str) -> str:
    return f'''<html><body>
      <h1>{title}</h1>
      <div>{published} 16:34 发布人：资产设备科</div>
      <p>天津中医药大学第二附属医院</p>
      <p>{body}</p>
    </body></html>'''


class TjzyefyMarketResearchTests(unittest.TestCase):
    def test_parses_multi_device_research_with_exact_deadline(self) -> None:
        title = '院内调研公告（2026年14号）-多导睡眠监测系统等医疗设备采购项目'
        html = detail_html(
            title,
            '2026-07-01',
            '我院拟对多导睡眠监测系统、便携式睡眠监测仪、重复经颅磁刺激仪、生物反馈治疗仪、计算机化心理测评系统进行院内调研。'
            '报名方式：国有资产管理科电子邮箱tjzyefygzk2026@126.com。'
            '报名时间：2026年7月1日-2026年7月7日16:00。'
            '联系人：潘老师 联系电话：022-60637522。',
        )
        record = parse_tjzyefy_market_research(
            html,
            source_url='https://www.tjzyefy.com/system/2026/07/01/030193522.shtml',
            index_url=INDEX_URL,
            index_published_at='2026-07-01',
            expected_title=title,
            observed_at=OBSERVED_AT,
            opportunity_id='tjzyefy_20260701_030193522',
        )
        facts = record['facts']
        self.assertEqual(facts['lifecycle_state'], 'MARKET_RESEARCH')
        self.assertEqual(facts['notice_type'], '院内调研公告')
        self.assertEqual(facts['registration_deadline'], '2026-07-07T16:00:00+08:00')
        self.assertIsNone(facts['registration_deadline_date'])
        self.assertEqual(facts['product_categories'], ['医疗设备'])
        self.assertEqual(
            [item['raw_name'] for item in facts['product_items']],
            ['多导睡眠监测系统', '便携式睡眠监测仪', '重复经颅磁刺激仪', '生物反馈治疗仪', '计算机化心理测评系统'],
        )
        self.assertEqual(facts['public_contact']['name'], '潘老师')
        self.assertEqual(facts['public_contact']['phone'], '022-60637522')
        self.assertEqual(facts['public_contact']['email'], 'tjzyefygzk2026@126.com')

    def test_parses_consumable_research(self) -> None:
        title = '医用耗材（试剂）调研公告（2026年13号）-脱脂棉纱布耗材采购项目'
        html = detail_html(
            title,
            '2026-07-31',
            '我院拟对脱脂棉纱布进行院内调研。报名方式：国有资产管理科电子邮箱tjzyefygzk2026@126.com。'
            '报名时间：2026年7月31日-2026年8月4日16:00。联系人：潘老师 联系电话：022-60637522。',
        )
        record = parse_tjzyefy_market_research(
            html,
            source_url='https://www.tjzyefy.com/system/2026/07/31/030195805.shtml',
            index_url=INDEX_URL,
            index_published_at='2026-07-31',
            expected_title=title,
            observed_at=OBSERVED_AT,
            opportunity_id='tjzyefy_20260731_030195805',
        )
        facts = record['facts']
        self.assertEqual(facts['notice_type'], '医用耗材（试剂）调研公告')
        self.assertEqual(facts['product_categories'], ['医用耗材'])
        self.assertEqual([item['raw_name'] for item in facts['product_items']], ['脱脂棉纱布'])
        self.assertEqual(facts['registration_deadline'], '2026-08-04T16:00:00+08:00')

    def test_parses_lc_ms_maintenance_without_inventing_generic_category(self) -> None:
        title = '院内调研公告（2026年17号）-高分辨液质联用系统三年期维保项目'
        html = detail_html(
            title,
            '2026-07-17',
            '我院拟对高分辨液质联用系统三年期维保项目（维保期：三年）进行院内调研。'
            '现有设备包括高分辨质谱仪、超高压液相色谱仪、纳升液相泵。'
            '报名方式：国有资产管理科电子邮箱tjzyefygzk2026@126.com。'
            '报名时间：2026年7月17日-2026年7月22日16:00。'
            '联系人：王老师 联系电话：022-60637812。',
        )
        record = parse_tjzyefy_market_research(
            html,
            source_url='https://www.tjzyefy.com/system/2026/07/17/030194635.shtml',
            index_url=INDEX_URL,
            index_published_at='2026-07-17',
            expected_title=title,
            observed_at=OBSERVED_AT,
            opportunity_id='tjzyefy_20260717_030194635',
        )
        facts = record['facts']
        self.assertEqual(facts['lifecycle_state'], 'MARKET_RESEARCH')
        self.assertEqual(facts['registration_deadline'], '2026-07-22T16:00:00+08:00')
        self.assertEqual(facts['product_categories'], [])
        self.assertTrue(any('高分辨液质联用系统' in item['raw_name'] for item in facts['product_items']))
        self.assertEqual(facts['public_contact']['name'], '王老师')
        self.assertEqual(facts['public_contact']['phone'], '022-60637812')
        self.assertEqual(facts['public_contact']['email'], 'tjzyefygzk2026@126.com')
        self.assertFalse(any(item['field_path'] == 'facts.product_categories' for item in record['evidence']))

    def test_date_only_deadline_does_not_invent_time(self) -> None:
        title = '院内调研公告（2026年12号）-除颤仪医疗设备采购项目'
        html = detail_html(
            title,
            '2026-05-29',
            '我院拟对除颤仪进行院内调研。报名时间：2026年5月29日-2026年6月2日。'
            '联系人：潘老师 联系电话：022-60637522。',
        )
        record = parse_tjzyefy_market_research(
            html,
            source_url='https://www.tjzyefy.com/system/2026/05/29/030191460.shtml',
            index_url=INDEX_URL,
            index_published_at='2026-05-29',
            expected_title=title,
            observed_at=OBSERVED_AT,
            opportunity_id='tjzyefy_20260529_030191460',
        )
        facts = record['facts']
        self.assertIsNone(facts['registration_deadline'])
        self.assertEqual(facts['registration_deadline_date'], '2026-06-02')
        self.assertIn('DEADLINE_TIME_NOT_PUBLISHED', record['quality_flags'])

    def test_procurement_intent_is_not_relabelled_market_research(self) -> None:
        title = '采购意向公告（2026年24号）-流式细胞仪等医疗设备采购项目'
        html = detail_html(
            title,
            '2026-06-03',
            '我院拟对流式细胞仪进行院内调研。报名时间：2026年6月3日-2026年6月8日16:00。',
        )
        with self.assertRaisesRegex(TjzyefyParseError, 'TJZYEFY_PROCUREMENT_INTENT_NOT_SUPPORTED'):
            parse_tjzyefy_market_research(
                html,
                source_url='https://www.tjzyefy.com/system/2026/06/03/030191773.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-06-03',
                expected_title=title,
                observed_at=OBSERVED_AT,
                opportunity_id='tjzyefy_intent_test',
            )

    def test_title_and_publication_date_mismatch_fail_closed(self) -> None:
        title = '院内调研公告（2026年12号）-除颤仪医疗设备采购项目'
        html = detail_html(
            title,
            '2026-05-29',
            '我院拟对除颤仪进行院内调研。报名时间：2026年5月29日-2026年6月2日16:00。',
        )
        with self.assertRaisesRegex(TjzyefyParseError, 'TJZYEFY_TITLE_MISMATCH'):
            parse_tjzyefy_market_research(
                html,
                source_url='https://www.tjzyefy.com/system/2026/05/29/030191460.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-05-29',
                expected_title='院内调研公告-其他医疗设备采购项目',
                observed_at=OBSERVED_AT,
                opportunity_id='tjzyefy_title_mismatch',
            )
        with self.assertRaisesRegex(TjzyefyParseError, 'TJZYEFY_PUBLISHED_DATE_MISMATCH'):
            parse_tjzyefy_market_research(
                html,
                source_url='https://www.tjzyefy.com/system/2026/05/29/030191460.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-05-28',
                expected_title=title,
                observed_at=OBSERVED_AT,
                opportunity_id='tjzyefy_date_mismatch',
            )

    def test_foreign_host_is_rejected(self) -> None:
        title = '院内调研公告-除颤仪医疗设备采购项目'
        html = detail_html(
            title,
            '2026-05-29',
            '我院拟对除颤仪进行院内调研。报名时间：2026年5月29日-2026年6月2日16:00。',
        )
        with self.assertRaisesRegex(TjzyefyParseError, 'TJZYEFY_SOURCE_HOST_REJECTED'):
            parse_tjzyefy_market_research(
                html,
                source_url='https://example.com/system/2026/05/29/1.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-05-29',
                expected_title=title,
                observed_at=OBSERVED_AT,
                opportunity_id='tjzyefy_foreign',
            )


if __name__ == '__main__':
    unittest.main()
