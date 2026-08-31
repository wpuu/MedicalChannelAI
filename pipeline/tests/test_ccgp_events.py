from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot
from medical_channel_pipeline.ccgp_events import parse_ccgp_event_text

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

CORRECTION_URL = 'https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260901_99999999.htm'


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
