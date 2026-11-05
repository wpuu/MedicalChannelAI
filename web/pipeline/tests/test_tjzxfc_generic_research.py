from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unittest

from medical_channel_pipeline.channel_scope import is_medical_channel_relevant_record
from medical_channel_pipeline.public_snapshot import _actionability, build_public_snapshot
from medical_channel_pipeline.tjzxfc_market_research import TjzxfcParseError, parse_tjzxfc_market_research
from medical_channel_pipeline.validation import ValidationError, validate_record

FIXTURES = Path(__file__).parent / 'fixtures'
TITLE = '天津市中心妇产科医院调研公告'
SOURCE_URL = 'https://www.tjzxfc.cn/system/2026/10/28/030364590.shtml'
INDEX_URL = 'https://www.tjzxfc.cn/ywgk/zbgg/index.shtml'
CHEMICALS = '危化品（冰乙酸、次氯酸钠、二甲苯、甲醇、甲醛、无水甲醇、无水乙醇、75%酒精、95%酒精等）'
USE = '检验科、病理科、产前诊断、实验室等使用。'
EVENT_TEXT = '携带资料及样品，现场讲解产品。时间：2026年11月4日9:30'
EVENT_AT = '2026-11-04T09:30:00+08:00'


def parse_generic(html: str | None = None, **overrides):
    args = dict(
        source_url=SOURCE_URL, index_url=INDEX_URL, index_published_at='2026-10-28',
        expected_title=TITLE, observed_at='2026-11-06T01:00:00+00:00',
        opportunity_id='tjzxfc_20261028_030364590',
    )
    args.update(overrides)
    return parse_tjzxfc_market_research(
        html if html is not None else (FIXTURES / 'tjzxfc_hazardous_research_20261028.html').read_text(encoding='utf-8'),
        **args,
    )


class TjzxfcGenericResearchTests(unittest.TestCase):
    def test_frozen_official_generic_notice_keeps_raw_object_use_and_event(self):
        record = parse_generic()
        facts = record['facts']
        self.assertTrue(is_medical_channel_relevant_record(record))
        self.assertEqual(facts['project_name'], TITLE)
        self.assertEqual(facts['product_items'], [dict(raw_name=CHEMICALS, category=None, quantity=None, specification=None)])
        self.assertEqual(facts['product_categories'], [])
        self.assertEqual(facts['product_use'], USE)
        self.assertEqual(facts['department'], '检验科、病理科、产前诊断、实验室')
        self.assertEqual(facts['research_event_at'], EVENT_AT)
        self.assertEqual(facts['research_event_text'], EVENT_TEXT)
        for field in ('registration_deadline', 'registration_deadline_date', 'bid_deadline', 'expected_procurement_at', 'budget_cny'):
            self.assertIsNone(facts[field], field)
        evidence = {item['field_path']: item for item in record['evidence']}
        for field in ('product_items', 'product_use', 'department', 'research_event_at', 'research_event_text'):
            self.assertEqual(evidence[f'facts.{field}']['source_url'], SOURCE_URL)
        self.assertIn('不是报名截止', evidence['facts.research_event_at']['locator'])
        self.assertNotIn('facts.registration_deadline', evidence)

    def test_event_is_projected_but_never_a_deadline_or_urgency(self):
        record = parse_generic()
        snapshot = build_public_snapshot([record], datetime.fromisoformat('2026-11-04T09:29:59.999999+08:00'))
        self.assertEqual(snapshot['matched_count'], 1)
        card = snapshot['opportunity_pool'][0]
        self.assertEqual(card['facts']['research_event_at'], EVENT_AT)
        self.assertEqual(card['facts']['research_event_text'], EVENT_TEXT)
        self.assertEqual(card['facts']['product_use'], USE)
        self.assertIsNone(card['facts']['registration_deadline_precision'])
        urgency = next(row for row in card['priority']['components'] if row['code'] == 'DEADLINE_URGENCY')
        self.assertEqual(urgency['points'], 0)
        self.assertNotIn('facts.research_event_at', urgency['opportunity_paths'])
        self.assertEqual(card['recommendation_mode'], 'PUBLIC_OPPORTUNITY')

    def test_event_closes_at_exact_boundary_even_with_later_bid(self):
        record = parse_generic()
        for now in (EVENT_AT, '2026-11-06T01:00:00+00:00'):
            with self.subTest(now=now):
                self.assertEqual(_actionability(record['facts'], datetime.fromisoformat(now)), ('ARCHIVE', 0, 'NOT_ELIGIBLE'))
                snapshot = build_public_snapshot([record], datetime.fromisoformat(now))
                self.assertEqual(snapshot['input_candidate_count'], 1)
                self.assertEqual(snapshot['opportunity_pool'], [])
                self.assertEqual(snapshot['cards'], [])
        facts = {**record['facts'], 'bid_deadline': '2026-11-30T12:00:00+08:00'}
        self.assertEqual(_actionability(facts, datetime.fromisoformat(EVENT_AT))[0], 'ARCHIVE')

    def test_real_samplebank_construction_remains_hard_negative(self):
        html = (FIXTURES / 'tjzxfc_samplebank_construction_20261102.html').read_text(encoding='utf-8')
        with self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_NON_MEDICAL_EARLY_SIGNAL'):
            parse_generic(html, source_url='https://www.tjzxfc.cn/system/2026/11/02/030366728.shtml',
                          index_published_at='2026-11-02', expected_title='天津市中心妇产科医院南开院区样本库改造项目调研公告')

    def test_medical_department_or_qualification_does_not_make_facilities_medical(self):
        template = '''<h1>{title}</h1><p>时间：2026-10-28 来源：总务科</p>
        <p>二、调研内容：{content}</p><p>三、用途：检验科、病理科等使用。</p>
        <p>四、资格要求：医疗器械经营许可证、注册证。</p>
        <p>五、调研方式及日期：携带资料及样品，现场讲解产品。时间：2026年11月4日9:30</p>
        <p>六、调研地点：天津市中心妇产科医院</p>'''
        for content in ('样本库改造', '病理科空调维修', '检验科水泵及管网改造', '病理科通风机维修', '办公桌椅'):
            with self.subTest(content=content), self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_NON_MEDICAL_EARLY_SIGNAL'):
                parse_generic(template.format(title=TITLE, content=content))
        # Hospital identity and boilerplate cannot substitute for medical use.
        html = template.format(title=TITLE, content=CHEMICALS).replace('检验科、病理科等使用。', '办公室等使用。')
        with self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_NON_MEDICAL_EARLY_SIGNAL'):
            parse_generic(html)

    def test_explicit_medical_equipment_maintenance_is_not_a_facility_exclusion(self):
        title = '天津市中心妇产科医院医用磁共振设备维修采购项目市场调研公告'
        html = f'''<h1>{title}</h1><p>时间：2026-10-28 来源：设备科</p>
        <p>调研内容为医用磁共振设备维修。提交截止时间：2026年11月10日17:00。</p>'''
        record = parse_generic(html, expected_title=title)
        self.assertEqual(record['facts']['product_items'][0]['raw_name'], '医用磁共振设备维修')
        self.assertEqual(record['facts']['registration_deadline'], '2026-11-10T17:00:00+08:00')

    def test_title_must_match_full_official_title_not_substring_or_body_reference(self):
        html = (FIXTURES / 'tjzxfc_hazardous_research_20261028.html').read_text(encoding='utf-8')
        for title in ('・' + TITLE, '天津市中心妇产科医院', TITLE + '（补充）'):
            with self.subTest(title=title), self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_TITLE_MISMATCH'):
                parse_generic(html, expected_title=title)
        with self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_PUBLISHED_DATE_MISMATCH'):
            parse_generic(index_published_at='2026-10-29')

    def test_event_time_missing_or_invalid_does_not_turn_into_registration_deadline(self):
        html = (FIXTURES / 'tjzxfc_hazardous_research_20261028.html').read_text(encoding='utf-8')
        for value, code in (('2026年11月4日', 'TIME_NOT_FOUND'), ('2026年11月4日25:30', 'TIME_INVALID')):
            with self.subTest(value=value), self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_RESEARCH_EVENT_' + code):
                parse_generic(html.replace('2026年11月4日9:30', value))
        with self.assertRaisesRegex(TjzxfcParseError, 'TJZXFC_REGISTRATION_DEADLINE_NOT_FOUND'):
            parse_generic(html.replace('现场讲解产品', '另行通知安排'))
        event_only = parse_generic(html.replace('现场讲解产品。时间：', '现场讲解产品。调研时间：'))
        self.assertEqual(event_only['facts']['research_event_at'], EVENT_AT)
        self.assertIsNone(event_only['facts']['registration_deadline'])
        self.assertIsNone(event_only['facts']['registration_deadline_date'])

    def test_event_and_use_have_independent_critical_evidence(self):
        for field in ('product_use', 'research_event_at', 'research_event_text'):
            record = parse_generic()
            record['evidence'] = [item for item in record['evidence'] if item['field_path'] != f'facts.{field}']
            with self.subTest(field=field), self.assertRaisesRegex(ValidationError, f'UNSUPPORTED_CRITICAL_FACT:facts.{field}'):
                validate_record(record)

    def test_event_validation_requires_exact_timezone_and_original_text(self):
        for invalid in ('2026-11-04', '2026-11-04T09:30:00', '2026-11-04T09:30:00+99:00', '2026-02-30T09:30:00+08:00', '2026-11-04T24:00:00+08:00'):
            record = parse_generic()
            record['facts']['research_event_at'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                validate_record(record)
        record = parse_generic()
        record['facts']['research_event_text'] = None
        with self.assertRaisesRegex(ValidationError, 'RESEARCH_EVENT_TEXT_REQUIRED'):
            validate_record(record)


if __name__ == '__main__':
    unittest.main()
