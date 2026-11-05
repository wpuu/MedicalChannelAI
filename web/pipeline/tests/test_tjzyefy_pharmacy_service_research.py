from __future__ import annotations

import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot
from medical_channel_pipeline.tjzyefy_market_research import TjzyefyParseError, parse_tjzyefy_market_research


INDEX_URL = 'https://www.tjzyefy.com/xwgg/ggtz/'
OBSERVED_AT = '2026-11-05T17:22:00+00:00'
FIXTURES = Path(__file__).parent / 'fixtures'
CASES = (
    {
        'id': 'tjzyefy_20261020_030201209', 'date': '2026-10-20',
        'title': '天津中医药大学第二附属医院制剂室内包材检验服务项目调研公告',
        'url': 'https://www.tjzyefy.com/system/2026/10/20/030201209.shtml',
        'service': '制剂室内包材检验服务', 'deadline': '2026-10-29T17:00:00+08:00',
        'evidence': '药品包装用铝箔和聚氯乙烯固体药用硬片',
    },
    {
        'id': 'tjzyefy_20261013_030200135', 'date': '2026-10-13',
        'title': '天津中医药大学第二附属医院制剂室净化区综合性能检验服务项目调研公告',
        'url': 'https://www.tjzyefy.com/system/2026/10/13/030200135.shtml',
        'service': '制剂室净化区综合性能检验服务', 'deadline': '2026-10-15T17:00:00+08:00',
        'evidence': '制剂车间综合性能检测',
    },
)


class TjzyefyPharmacyServiceResearchTests(unittest.TestCase):
    def page(self, case):
        return (FIXTURES / (case['id'] + '_service_excerpt.html')).read_text(encoding='utf-8')

    def parse(self, case, html=None, **changes):
        arguments = dict(source_url=case['url'], index_url=INDEX_URL, index_published_at=case['date'],
                         expected_title=case['title'], observed_at=OBSERVED_AT, opportunity_id=case['id'])
        arguments.update(changes)
        return parse_tjzyefy_market_research(html if html is not None else self.page(case), **arguments)

    def test_two_real_official_service_templates_preserve_pharmacy_objects_and_deadlines(self):
        for case in CASES:
            with self.subTest(opportunity_id=case['id']):
                record = self.parse(case)
                facts = record['facts']
                self.assertEqual(facts['lifecycle_state'], 'MARKET_RESEARCH')
                self.assertEqual(facts['project_name'], case['title'])
                self.assertEqual(facts['registration_deadline'], case['deadline'])
                self.assertIsNone(facts['registration_deadline_date'])
                self.assertEqual(facts['product_categories'], [])
                self.assertEqual(len(facts['product_items']), 1)
                item = facts['product_items'][0]
                self.assertEqual(item['raw_name'], case['service'])
                self.assertIsNone(item['category'])
                self.assertIsNone(item['quantity'])
                self.assertIn(case['evidence'], item['specification'])
                locator = next(row['locator'] for row in record['evidence'] if row['field_path'] == 'facts.product_items')
                self.assertIn('项目名称', locator)
                self.assertIn('服务内容', locator)
                self.assertNotIn('我院拟对', locator)

    def test_real_expired_services_do_not_become_current_public_opportunities(self):
        records = [self.parse(case) for case in CASES]
        snapshot = build_public_snapshot(records, datetime(2026, 11, 5, 17, 22, tzinfo=timezone.utc))
        self.assertEqual(snapshot['opportunity_pool'], [])

    def test_project_title_in_service_body_must_match_the_verified_index_title(self):
        case = CASES[0]
        html = self.page(case).replace('1.项目名称：' + case['title'], '1.项目名称：另一个制剂室检验服务项目调研公告')
        self.assertNotEqual(html, self.page(case))
        with self.assertRaisesRegex(TjzyefyParseError, 'SERVICE_PROJECT_TITLE_MISMATCH'):
            self.parse(case, html)

    def test_hospital_or_pharmacy_title_without_pharmacy_service_content_is_insufficient(self):
        case = CASES[0]
        html = re.sub(r'(<p>[^<]*2.服务内容：).*?(</p>)', r'\1办公楼配电箱检测与安防系统检查\2', self.page(case), flags=re.S)
        self.assertNotEqual(html, self.page(case))
        with self.assertRaisesRegex(TjzyefyParseError, 'PRODUCT_ITEMS_NOT_FOUND'):
            self.parse(case, html)

    def test_office_security_and_generic_inspection_services_do_not_gain_medical_facts(self):
        for service in ('办公室配电箱检测服务', '安防系统检测服务', '消防设施检验服务',
                        '制剂室办公室配电箱检测服务', '制剂室安防系统检测服务'):
            case = CASES[0]
            title = '天津中医药大学第二附属医院' + service + '项目调研公告'
            html = self.page(case).replace(case['title'], title)
            html = re.sub(r'(<p>[^<]*2.服务内容：).*?(</p>)', r'\1制剂车间' + service + r'\2', html, flags=re.S)
            with self.subTest(service=service):
                with self.assertRaises(TjzyefyParseError):
                    self.parse(case, html, expected_title=title)

    def test_registration_precision_and_invalid_times_remain_fail_closed(self):
        case = CASES[0]
        record = self.parse(case, self.page(case).replace('2026年10月29日17:00', '2026年10月29日'))
        self.assertIsNone(record['facts']['registration_deadline'])
        self.assertEqual(record['facts']['registration_deadline_date'], '2026-10-29')
        self.assertIn('DEADLINE_TIME_NOT_PUBLISHED', record['quality_flags'])
        with self.assertRaisesRegex(TjzyefyParseError, 'REGISTRATION_TIME_INVALID'):
            self.parse(case, self.page(case).replace('2026年10月29日17:00', '2026年10月29日25:00'))
        with self.assertRaisesRegex(TjzyefyParseError, 'REGISTRATION_WINDOW_NOT_FOUND'):
            self.parse(case, self.page(case).replace('报名时间：即日起至2026年10月29日17:00', '报名要求：请联系工作人员'))

    def test_existing_official_identity_and_publication_guards_remain(self):
        for case in CASES:
            with self.subTest(opportunity_id=case['id']):
                with self.assertRaisesRegex(TjzyefyParseError, 'SOURCE_HOST_REJECTED'):
                    self.parse(case, source_url='https://evil.example/system/2026/10/20/030201209.shtml')
                with self.assertRaisesRegex(TjzyefyParseError, 'PUBLISHED_DATE_MISMATCH'):
                    self.parse(case, index_published_at='2026-10-01')


if __name__ == '__main__':
    unittest.main()
