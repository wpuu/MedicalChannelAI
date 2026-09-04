from __future__ import annotations

import unittest

from medical_channel_pipeline.tjzyefy_procurement_intent import (
    EXPECTED_PROCUREMENT_WINDOW_UNSTRUCTURED,
    TjzyefyIntentParseError,
    parse_tjzyefy_procurement_intent,
)

INDEX_URL = 'https://www.tjzyefy.com/xwgg/ggtz/'
OBSERVED_AT = '2026-06-19T09:00:00+00:00'


def page(title: str, body: str, *, published: str = '2026-06-19') -> str:
    return f'''
    <html><body>
      <h1>{title}</h1>
      <div>{published} 10:05 发布人：采购办公室</div>
      <p>天津中医药大学第二附属医院</p>
      <p>{body}</p>
    </body></html>
    '''


class TjzyefyProcurementIntentTests(unittest.TestCase):
    def test_medical_equipment_intent_becomes_verified_pre_market_record(self) -> None:
        title = '采购意向公告（2026年24号）-流式细胞仪等医疗设备采购项目'
        html = page(
            title,
            '我院将于近期对天津中医药大学第二附属医院流式细胞仪等医疗设备采购项目进行采购，'
            '欢迎各位有资质的供应商咨询。预计采购时间2026年7-8月。'
            '联系电话：022-60637953、022-60372615 联系人：孙老师、赵老师。'
            '本项目具体招标信息请于近期关注天津市政采网。',
        )
        record = parse_tjzyefy_procurement_intent(
            html,
            source_url='https://www.tjzyefy.com/system/2026/06/19/030192700.shtml',
            index_url=INDEX_URL,
            index_published_at='2026-06-19',
            expected_title=title,
            observed_at=OBSERVED_AT,
            opportunity_id='tjzyefy_intent_20260619_030192700',
        )
        facts = record['facts']
        self.assertEqual(facts['lifecycle_state'], 'PROCUREMENT_INTENT')
        self.assertEqual(facts['notice_type'], '采购意向公告')
        self.assertEqual(facts['product_categories'], ['医疗设备'])
        self.assertEqual(facts['product_items'][0]['raw_name'], '流式细胞仪')
        self.assertIsNone(facts['registration_deadline'])
        self.assertIsNone(facts['registration_deadline_date'])
        self.assertIsNone(facts['expected_procurement_at'])
        self.assertIn(EXPECTED_PROCUREMENT_WINDOW_UNSTRUCTURED, record['quality_flags'])
        self.assertEqual(facts['public_contact']['phone'], '022-60637953')
        self.assertEqual(facts['public_contact']['name'], '孙老师')

    def test_sterilizer_title_is_medical_without_generic_medical_equipment_words(self) -> None:
        title = '采购意向公告（2026年23号）-脉动真空灭菌器等设备采购项目'
        html = page(
            title,
            '我院将于近期对天津中医药大学第二附属医院脉动真空灭菌器等设备采购项目进行采购，'
            '欢迎各位有资质的供应商咨询。预计采购时间2026年7月。'
            '联系电话：022-60637522 联系人：潘老师。',
        )
        record = parse_tjzyefy_procurement_intent(
            html,
            source_url='https://www.tjzyefy.com/system/2026/06/19/030192699.shtml',
            index_url=INDEX_URL,
            index_published_at='2026-06-19',
            expected_title=title,
            observed_at=OBSERVED_AT,
            opportunity_id='tjzyefy_intent_20260619_030192699',
        )
        self.assertEqual(record['facts']['product_items'][0]['raw_name'], '脉动真空灭菌器')
        self.assertEqual(record['facts']['product_categories'], [])

    def test_nonmedical_intent_is_rejected_after_broad_discovery(self) -> None:
        title = '采购意向公告（2026年25号）-2026年景区年票采购项目'
        html = page(
            title,
            '我院将于近期对天津中医药大学第二附属医院2026年景区年票采购项目进行采购，'
            '欢迎各位有资质的供应商咨询。预计采购时间2026年7月。'
            '联系电话：022-60637803 联系人：孙老师。',
        )
        with self.assertRaisesRegex(TjzyefyIntentParseError, 'TJZYEFY_INTENT_NON_MEDICAL'):
            parse_tjzyefy_procurement_intent(
                html,
                source_url='https://www.tjzyefy.com/system/2026/06/19/030192701.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-06-19',
                expected_title=title,
                observed_at=OBSERVED_AT,
                opportunity_id='tjzyefy_intent_20260619_030192701',
            )

    def test_title_and_official_publication_date_must_match(self) -> None:
        title = '采购意向公告（2026年24号）-流式细胞仪等医疗设备采购项目'
        html = page(
            title,
            '我院将于近期对天津中医药大学第二附属医院流式细胞仪等医疗设备采购项目进行采购，'
            '欢迎各位有资质的供应商咨询。预计采购时间2026年7月。',
            published='2026-06-18',
        )
        with self.assertRaisesRegex(TjzyefyIntentParseError, 'TJZYEFY_INTENT_PUBLISHED_DATE_MISMATCH'):
            parse_tjzyefy_procurement_intent(
                html,
                source_url='https://www.tjzyefy.com/system/2026/06/19/030192700.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-06-19',
                expected_title=title,
                observed_at=OBSERVED_AT,
                opportunity_id='tjzyefy_intent_20260619_030192700',
            )

    def test_non_official_detail_host_is_rejected(self) -> None:
        title = '采购意向公告（2026年24号）-流式细胞仪等医疗设备采购项目'
        with self.assertRaisesRegex(TjzyefyIntentParseError, 'TJZYEFY_INTENT_SOURCE_HOST_REJECTED'):
            parse_tjzyefy_procurement_intent(
                page(title, '欢迎供应商咨询'),
                source_url='https://example.com/system/2026/06/19/1.shtml',
                index_url=INDEX_URL,
                index_published_at='2026-06-19',
                expected_title=title,
                observed_at=OBSERVED_AT,
                opportunity_id='bad',
            )


if __name__ == '__main__':
    unittest.main()
