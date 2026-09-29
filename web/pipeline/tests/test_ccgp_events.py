from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot
from medical_channel_pipeline.ccgp_events import package_refs, parse_ccgp_event_html, parse_ccgp_event_text, validate_notice_events

ROOT = Path(__file__).resolve().parents[1]

CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：XCSD-2026-C-181
原公告的采购项目名称：病原微生物能力提升相关设备购置
首次公告日期：2026-08-24
二、更正信息
更正事项：采购文件
更正内容：原公告的投标文件提交截止时间：2026-09-14 09:30:00，更正为：2026-09-18 09:30:00。
原公告的开标时间：2026-09-14 09:30:00，更正为：2026-09-18 09:30:00。
其他内容不变
更正日期：2026-09-01
三、其他补充事宜 无
"""

RESPONSE_CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：TGPC-2026-A-0081
原公告的采购项目名称：天津市第一中心医院复康院区提升改造项目基础硬件及附属设施建设项目智能语音采集设备采购项目
首次公告日期：2026-05-15
二、更正信息
更正事项：采购公告
更正内容：原公告的响应文件提交截止时间：2026-05-26 08:30:00，更正为：2026-05-29 08:30:00。
原公告的开启时间：2026-05-26 09:30:00，更正为：2026-05-29 09:30:00。
其他内容不变
更正日期：2026-05-20
三、其他补充事宜 无
"""

MATERIAL_RESPONSE_CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：TGPC-2026-A-0081
原公告的采购项目名称：天津市第一中心医院复康院区提升改造项目基础硬件及附属设施建设项目智能语音采集设备采购项目
首次公告日期：2026-05-15
二、更正信息
更正事项：采购文件
更正内容：原公告的响应文件提交截止时间：2026-05-26 08:30:00，更正为：2026-05-29 08:30:00。
同时调整采购需求中的技术参数，具体详见更正后的竞争性磋商文件。
更正日期：2026-05-20
三、其他补充事宜 无
"""

INCOMPLETE_CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：XCSD-2026-C-181
原公告的采购项目名称：病原微生物能力提升相关设备购置
首次公告日期：2026-08-24
二、更正信息
更正事项：采购公告
更正内容：原公告的获取招标文件结束日期：2026-08-31，更正为：2026-09-04。
原公告的投标文件提交截止时间：2026-09-14 09:30:00，更正为：2026-09-20 09:30:00。
其他内容不变
更正日期：2026-09-01
三、其他补充事宜 无
"""

MATERIAL_CORRECTION_FIXTURE = """
更正公告
一、项目基本情况
原公告的采购项目编号：XCSD-2026-C-181
原公告的采购项目名称：病原微生物能力提升相关设备购置
首次公告日期：2026-08-24
二、更正信息
更正事项：采购文件和采购公告
更正内容：原公告的投标文件提交截止时间：2026-09-14 09:30:00，更正为：2026-09-18 09:30:00。
同时调整采购需求中的技术参数，具体详见更正后的招标文件。
更正日期：2026-09-01
三、其他补充事宜 无
"""

TERMINATION_FIXTURE = """
终止公告
发布日期：2026年08月25日
一、项目基本情况：
采购项目编号：XCSD-2026-C-181
采购项目名称：病原微生物能力提升相关设备购置
二、项目终止的原因：截至规定时间，无供应商投标
三、其他补充事宜：无
"""

PACKAGE_TERMINATION_FIXTURE = """
终止公告
发布日期：2026年08月25日
一、项目基本情况：
采购项目编号：XCSD-2026-C-181
采购项目名称：病原微生物能力提升相关设备购置
二、项目终止的原因：第2包：通过符合性审查的投标人不足3家，本包废标。
三、其他补充事宜：无
"""

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
CORRECTION_URL = 'https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260901_99999999.htm'
RESPONSE_CORRECTION_URL = 'https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202605/t20260520_99999997.htm'


class CcgpEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = json.loads((ROOT / 'data' / 'tianjin_verified_seed.json').read_text(encoding='utf-8'))

    def test_exact_deadline_correction_becomes_resolved_override(self) -> None:
        event = parse_ccgp_event_text(
            CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='correction_xcsd_2026_c_181',
        )
        self.assertEqual(event['event_type'], 'CORRECTION')
        self.assertEqual(event['project_number'], 'XCSD-2026-C-181')
        self.assertFalse(event['requires_reconciliation'])
        self.assertEqual(event['changed_fact_paths'], ['facts.bid_deadline'])
        self.assertEqual(
            event['fact_overrides']['facts.bid_deadline'],
            '2026-09-18T09:30:00+08:00',
        )
        self.assertEqual(event['unresolved_fact_paths'], [])
        self.assertFalse(event['terminal'])

    def test_exact_response_submission_correction_maps_to_canonical_bid_deadline(self) -> None:
        event = parse_ccgp_event_text(
            RESPONSE_CORRECTION_FIXTURE,
            source_url=RESPONSE_CORRECTION_URL,
            observed_at='2026-05-20T12:00:00+08:00',
            event_id='correction_tgpc_2026_a_0081',
        )
        self.assertFalse(event['requires_reconciliation'])
        self.assertEqual(event['changed_fact_paths'], ['facts.bid_deadline'])
        self.assertEqual(
            event['fact_overrides']['facts.bid_deadline'],
            '2026-05-29T08:30:00+08:00',
        )

    def test_material_response_correction_stays_suppressed_despite_exact_deadline(self) -> None:
        event = parse_ccgp_event_text(
            MATERIAL_RESPONSE_CORRECTION_FIXTURE,
            source_url=RESPONSE_CORRECTION_URL,
            observed_at='2026-05-20T12:00:00+08:00',
            event_id='material_correction_tgpc_2026_a_0081',
        )
        self.assertEqual(
            event['fact_overrides']['facts.bid_deadline'],
            '2026-05-29T08:30:00+08:00',
        )
        self.assertTrue(event['requires_reconciliation'])
        self.assertIn('__material_correction__', event['unresolved_fact_paths'])

    def test_exact_correction_rebuilds_today_card_and_adds_event_evidence(self) -> None:
        event = parse_ccgp_event_text(
            CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='correction_xcsd_2026_c_181',
        )
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat('2026-09-01T12:00:00+08:00'),
            [event],
        )
        card = next(
            card
            for card in payload['cards']
            if card['opportunity_id'] == 'verified_bhcdc_2026_c_181'
        )
        self.assertEqual(card['facts']['bid_deadline'], '2026-09-18T09:30:00+08:00')
        self.assertIn(CORRECTION_URL, card['evidence_source_urls'])
        self.assertIn('OFFICIAL_CORRECTION_APPLIED', card['priority']['warnings'])

    def test_correction_matches_project_number_typed_with_full_width_characters(self) -> None:
        # Clerks type the same number with full-width brackets/dashes or stray
        # spaces; matching must use the shared normalisation, not raw text.
        event = parse_ccgp_event_text(
            CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='correction_xcsd_2026_c_181_fullwidth',
        )
        raw_number = event['project_number']
        event['project_number'] = raw_number.replace('-', '－').replace('(', '（').replace(')', '）') + '\u3000'
        self.assertNotEqual(event['project_number'].strip().lower(), raw_number.strip().lower())
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat('2026-09-01T12:00:00+08:00'),
            [event],
        )
        card = next(
            card
            for card in payload['cards']
            if card['opportunity_id'] == 'verified_bhcdc_2026_c_181'
        )
        self.assertEqual(card['facts']['bid_deadline'], '2026-09-18T09:30:00+08:00')
        self.assertIn('OFFICIAL_CORRECTION_APPLIED', card['priority']['warnings'])

    def test_date_only_registration_change_remains_suppressed(self) -> None:
        event = parse_ccgp_event_text(
            INCOMPLETE_CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='incomplete_correction_xcsd_2026_c_181',
        )
        self.assertTrue(event['requires_reconciliation'])
        self.assertIn('facts.registration_deadline', event['unresolved_fact_paths'])
        self.assertEqual(
            event['fact_overrides']['facts.bid_deadline'],
            '2026-09-20T09:30:00+08:00',
        )
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat('2026-09-01T12:00:00+08:00'),
            [event],
        )
        self.assertNotIn(
            'verified_bhcdc_2026_c_181',
            {card['opportunity_id'] for card in payload['cards']},
        )

    def test_material_correction_remains_suppressed_even_when_deadline_is_exact(self) -> None:
        event = parse_ccgp_event_text(
            MATERIAL_CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='material_correction_xcsd_2026_c_181',
        )
        self.assertTrue(event['requires_reconciliation'])
        self.assertIn('__material_correction__', event['unresolved_fact_paths'])
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat('2026-09-01T12:00:00+08:00'),
            [event],
        )
        self.assertNotIn(
            'verified_bhcdc_2026_c_181',
            {card['opportunity_id'] for card in payload['cards']},
        )

    def test_termination_event_is_terminal(self) -> None:
        event = parse_ccgp_event_text(
            TERMINATION_FIXTURE,
            source_url='https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202608/t20260825_99999998.htm',
            observed_at='2026-08-25T19:00:00+08:00',
            event_id='termination_xcsd_2026_c_181',
        )
        self.assertEqual(event['event_type'], 'TERMINATION')
        self.assertEqual(event['published_at'], '2026-08-25')
        self.assertTrue(event['terminal'])

    def test_package_refs_are_normalised_and_project_names_with_packages_do_not_count(self) -> None:
        self.assertEqual(package_refs('市属医院2026年医用设备集中带量采购放射组第14包、第16包废标公告'), ['第14包', '第16包'])
        self.assertEqual(package_refs('公改示范项目（第一批）-西城区骨健康特色诊疗中心项目（丰盛医院）06包更正公告'), ['第6包'])
        self.assertEqual(package_refs('某项目第十二包、第二十包废标公告'), ['第12包', '第20包'])
        self.assertEqual(package_refs('2026年第二批设备采购终止公告'), [])
        self.assertEqual(package_refs('天津市第一中心医院CT室、DR室改造项目成交公告'), [])

    def test_real_beijing_package_failed_bid_notice_is_package_scoped_not_terminal(self) -> None:
        event = parse_ccgp_event_html(
            (FIXTURES / 'ccgp_event_beijing_package_failed_bid.html').read_text(encoding='utf-8'),
            source_url='https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202609/t20260924_27401689.htm',
            observed_at='2026-09-29T12:00:00+00:00',
            event_id='termination_bj_202601_p14_16',
        )
        self.assertEqual(event['event_type'], 'TERMINATION')
        self.assertEqual(event['project_number'], '202601')
        self.assertEqual(event['notice_title'], '市属医院2026年医用设备集中带量采购放射组第14包、第16包废标公告')
        self.assertEqual((event['scope'], event['packages']), ('PACKAGE', ['第14包', '第16包']))
        self.assertFalse(event['terminal'])
        self.assertIn('本包废标', event['summary'])
        # Round-trips through the store validator with the new optional fields.
        event['market_code'] = 'BJ'
        self.assertEqual(validate_notice_events([event])[0]['scope'], 'PACKAGE')

    def test_real_beijing_package_correction_and_heilongjiang_project_correction(self) -> None:
        package = parse_ccgp_event_html(
            (FIXTURES / 'ccgp_event_beijing_package_correction.html').read_text(encoding='utf-8'),
            source_url='https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260924_27397249.htm',
            observed_at='2026-09-29T12:00:00+00:00',
            event_id='correction_bj_fengsheng_p06',
        )
        self.assertEqual(package['project_number'], '11010226210200025327-XM001')
        self.assertEqual((package['scope'], package['packages']), ('PACKAGE', ['第6包']))
        self.assertTrue(package['requires_reconciliation'])  # parameter change, unparsed
        project = parse_ccgp_event_html(
            (FIXTURES / 'ccgp_event_heilongjiang_project_correction.html').read_text(encoding='utf-8'),
            source_url='https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260928_27407474.htm',
            observed_at='2026-09-29T12:00:00+00:00',
            event_id='correction_hl_gannan',
        )
        self.assertEqual(project['project_number'], '[230225]CQXMGL[GK]20260003-1')
        self.assertEqual((project['scope'], project['packages']), ('PROJECT', []))
        self.assertIn('本项目暂停', project['summary'])

    def test_package_scoped_termination_keeps_card_and_surfaces_official_notice(self) -> None:
        event = parse_ccgp_event_text(
            PACKAGE_TERMINATION_FIXTURE,
            source_url='https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202608/t20260825_99999996.htm',
            observed_at='2026-08-25T19:00:00+08:00',
            event_id='termination_xcsd_2026_c_181_p2',
        )
        # Text fixtures have no page headline: package scope comes from the 终止原因 lines.
        self.assertEqual((event['scope'], event['packages']), ('PACKAGE', ['第2包']))
        self.assertFalse(event['terminal'])
        as_of = datetime.fromisoformat('2026-08-31T15:00:00+08:00')
        baseline = build_public_snapshot(copy.deepcopy(self.records), as_of, [])
        payload = build_public_snapshot(copy.deepcopy(self.records), as_of, [event])
        self.assertEqual(payload['opportunity_pool_count'], baseline['opportunity_pool_count'])
        card = next(card for card in payload['opportunity_pool'] if card['opportunity_id'] == 'verified_bhcdc_2026_c_181')
        self.assertEqual(card['facts']['bid_deadline'], next(
            item for item in baseline['opportunity_pool'] if item['opportunity_id'] == 'verified_bhcdc_2026_c_181'
        )['facts']['bid_deadline'])
        self.assertIn('OFFICIAL_PACKAGE_NOTICE_REPORTED', card['facts']['quality_flags'])
        self.assertEqual(card['official_notices'], [
            {
                'event_type': 'TERMINATION',
                'scope': 'PACKAGE',
                'packages': ['第2包'],
                'published_at': '2026-08-25',
                'source_url': 'https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202608/t20260825_99999996.htm',
                'summary': '第2包：通过符合性审查的投标人不足3家，本包废标。',
            }
        ])
        self.assertIn(event['source_url'], card['evidence_source_urls'])
        other = next(card for card in payload['opportunity_pool'] if card['opportunity_id'] != 'verified_bhcdc_2026_c_181')
        self.assertIsNone(other['official_notices'])

    def test_events_with_market_code_only_reach_records_of_that_market(self) -> None:
        event = parse_ccgp_event_text(
            TERMINATION_FIXTURE,
            source_url='https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202608/t20260825_99999998.htm',
            observed_at='2026-08-25T19:00:00+08:00',
            event_id='termination_xcsd_2026_c_181_bj',
        )
        as_of = datetime.fromisoformat('2026-08-31T15:00:00+08:00')
        baseline = build_public_snapshot(copy.deepcopy(self.records), as_of, [])
        self.assertTrue(any(card['opportunity_id'] == 'verified_bhcdc_2026_c_181' for card in baseline['opportunity_pool']))
        # Same number, foreign market: the Tianjin record is untouched.
        foreign = dict(event, market_code='BJ')
        payload = build_public_snapshot(copy.deepcopy(self.records), as_of, [foreign])
        self.assertTrue(any(card['opportunity_id'] == 'verified_bhcdc_2026_c_181' for card in payload['opportunity_pool']))
        # Explicit Tianjin identity and the legacy market-less form both apply.
        for applied in (dict(event, market_code='TJ'), event):
            payload = build_public_snapshot(copy.deepcopy(self.records), as_of, [applied])
            self.assertFalse(any(card['opportunity_id'] == 'verified_bhcdc_2026_c_181' for card in payload['opportunity_pool']))
        with self.assertRaisesRegex(ValueError, 'EVENT_MARKET_CODE_INVALID'):
            validate_notice_events([dict(event, market_code='SH')])
        with self.assertRaisesRegex(ValueError, 'EVENT_PACKAGE_SCOPE_REQUIRES_PACKAGES'):
            validate_notice_events([dict(event, scope='PACKAGE', packages=[])])

    def test_future_correction_does_not_apply_before_publication(self) -> None:
        event = parse_ccgp_event_text(
            CORRECTION_FIXTURE,
            source_url=CORRECTION_URL,
            observed_at='2026-09-01T10:00:00+08:00',
            event_id='correction_xcsd_2026_c_181',
        )
        payload = build_public_snapshot(
            copy.deepcopy(self.records),
            datetime.fromisoformat('2026-08-31T15:00:00+08:00'),
            [event],
        )
        card = next(
            card
            for card in payload['cards']
            if card['opportunity_id'] == 'verified_bhcdc_2026_c_181'
        )
        self.assertEqual(card['facts']['bid_deadline'], '2026-09-14T09:30:00+08:00')
        self.assertNotIn(CORRECTION_URL, card['evidence_source_urls'])


if __name__ == '__main__':
    unittest.main()
