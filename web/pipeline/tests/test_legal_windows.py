from __future__ import annotations

import json
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from medical_channel_pipeline.legal_windows import (
    CALENDAR_OFFICIAL,
    DOCUMENT_CHALLENGE,
    RESULT_CHALLENGE,
    add_working_days,
    is_working_day,
    legal_windows_for_facts,
    refresh_legal_windows,
    working_calendar_payload,
    working_days_remaining,
)
from medical_channel_pipeline.public_snapshot import build_public_snapshot

TIANJIN = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]


SOURCE_URL = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260916_27340783.htm"


def ccgp_record(**overrides) -> dict:
    facts = {
        "project_number": "TJ-2026-0916-01",
        "project_name": "天津市人民医院复合手术室医疗设备采购项目",
        "buyer_name": "天津市人民医院",
        "hospital_name": "天津市人民医院",
        "department": "手术室",
        "region": "天津市",
        "lifecycle_state": "BIDDING",
        "notice_type": "公开招标公告",
        "published_at": "2026-09-16",
        "registration_deadline": "2026-09-22T16:30:00+08:00",
        "registration_deadline_date": None,
        "bid_deadline": "2026-10-10T09:00:00+08:00",
        "expected_procurement_at": None,
        "expected_procurement_precision": None,
        "budget_cny": 12_000_000,
        "procurement_method": "公开招标",
        "product_categories": ["医疗设备"],
        "product_items": [{"name": "复合手术室设备", "category": "医疗设备"}],
        "public_contact": None,
    }
    facts.update(overrides.pop("facts", {}))
    evidence = [
        {"field_path": f"facts.{key}", "source_url": SOURCE_URL, "locator": "公告正文"}
        for key, value in facts.items()
        if value not in (None, "", [], {})
    ]
    record = {
        "schema_version": "0.1",
        "opportunity_id": "ccgp_legal_window_demo",
        "source": {
            "source_id": "ccgp:202609:t20260916_27340783",
            "source_type": "CCGP_NOTICE",
            "url": SOURCE_URL,
            "observed_at": "2026-09-16T02:00:00Z",
        },
        "facts": facts,
        "evidence": evidence,
        "quality_flags": [],
    }
    record.update(overrides)
    return record


class WorkingCalendarTests(unittest.TestCase):
    def test_state_council_2026_schedule(self) -> None:
        # 国办发明电〔2025〕7号
        self.assertFalse(is_working_day(date(2026, 1, 1)))
        self.assertTrue(is_working_day(date(2026, 1, 4)))     # 周日调休上班
        self.assertFalse(is_working_day(date(2026, 2, 15)))   # 春节首日
        self.assertFalse(is_working_day(date(2026, 2, 23)))   # 春节末日
        self.assertTrue(is_working_day(date(2026, 2, 14)))    # 周六调休上班
        self.assertTrue(is_working_day(date(2026, 2, 28)))
        self.assertFalse(is_working_day(date(2026, 5, 5)))
        self.assertTrue(is_working_day(date(2026, 5, 9)))
        self.assertFalse(is_working_day(date(2026, 9, 25)))   # 中秋
        self.assertTrue(is_working_day(date(2026, 9, 20)))    # 周日调休上班
        self.assertFalse(is_working_day(date(2026, 10, 1)))
        self.assertFalse(is_working_day(date(2026, 10, 7)))
        self.assertTrue(is_working_day(date(2026, 10, 8)))
        self.assertTrue(is_working_day(date(2026, 10, 10)))   # 周六调休上班
        self.assertFalse(is_working_day(date(2026, 10, 11)))  # 普通周日

    def test_add_working_days_skips_start_day_and_holidays(self) -> None:
        # 94号令 §42: 开始之日不计入。2026-09-22(周二) + 7 个工作日:
        # 9/23 9/24 | 9/25-27 中秋 | 9/28 9/29 9/30 | 10/1-7 国庆 | 10/8 10/9
        self.assertEqual(add_working_days(date(2026, 9, 22), 7), date(2026, 10, 9))
        self.assertEqual(add_working_days(date(2026, 9, 22), 0), date(2026, 9, 22))
        # 2026-09-11(周五) + 7 个工作日 = 9/21 (9/14-18 五天, 9/20 周日调休上班, 9/21)
        self.assertEqual(add_working_days(date(2026, 9, 11), 7), date(2026, 9, 21))
        # 跨春节: 2026-02-13(周五) + 1 = 2/14(周六调休上班)
        self.assertEqual(add_working_days(date(2026, 2, 13), 1), date(2026, 2, 14))
        self.assertEqual(add_working_days(date(2026, 2, 14), 1), date(2026, 2, 24))

    def test_working_days_remaining_counts_today_when_working_day(self) -> None:
        self.assertEqual(working_days_remaining(date(2026, 9, 29), date(2026, 10, 9)), 4)  # 9/29 9/30 10/8 10/9
        self.assertEqual(working_days_remaining(date(2026, 10, 9), date(2026, 10, 9)), 1)  # 最后一天
        self.assertEqual(working_days_remaining(date(2026, 10, 10), date(2026, 10, 9)), 0)
        self.assertEqual(working_days_remaining(date(2026, 10, 3), date(2026, 10, 9)), 2)  # 假期中只剩 10/8 10/9

    def test_calendar_payload_is_serializable_and_complete(self) -> None:
        payload = working_calendar_payload()
        json.dumps(payload)
        self.assertEqual(payload["code"], CALENDAR_OFFICIAL)
        self.assertEqual(payload["complaint_working_days"], 15)
        self.assertIn("2026-10-01", payload["holidays"])
        self.assertIn("2026-10-10", payload["adjusted_workdays"])
        self.assertEqual(payload["coverage_from"], "2025-01-01")
        self.assertEqual(payload["coverage_to"], "2026-12-31")
        self.assertEqual(payload["holidays"], sorted(payload["holidays"]))


class LegalWindowDerivationTests(unittest.TestCase):
    def test_registration_dates_never_prove_a_legal_anchor(self) -> None:
        for deadline in ('2026-09-22T16:30:00+08:00', '2026-09-22T08:30:00Z', '2027-03-01', 'invalid'):
            facts = ccgp_record(facts={'registration_deadline': deadline})['facts']
            for now in (datetime(2026, 9, 29, tzinfo=TIANJIN), datetime(2026, 10, 12, tzinfo=TIANJIN)):
                with self.subTest(deadline=deadline, now=now):
                    item = legal_windows_for_facts(facts, now)[0]
                    self.assertEqual(item['code'], DOCUMENT_CHALLENGE)
                    self.assertEqual(item['status'], 'UNKNOWN')
                    self.assertIsNone(item['anchor_date'])
                    self.assertIsNone(item['deadline_date'])
                    self.assertEqual(item['remaining_working_days'], 0)

    def test_date_only_registration_stays_unknown(self) -> None:
        facts = ccgp_record(facts={'registration_deadline': None, 'registration_deadline_date': '2026-09-11'})['facts']
        self.assertEqual(legal_windows_for_facts(facts, datetime(2026, 9, 21, tzinfo=TIANJIN))[0]['status'], 'UNKNOWN')

    def test_result_date_without_legal_regime_and_period_end_stays_unknown(self) -> None:
        facts = ccgp_record(facts={'lifecycle_state': 'AWARDED', 'published_at': '2026-09-24'})['facts']
        item = legal_windows_for_facts(facts, datetime(2026, 9, 29, tzinfo=TIANJIN))[0]
        self.assertEqual(item['code'], RESULT_CHALLENGE)
        self.assertEqual(item['status'], 'UNKNOWN')
        self.assertIsNone(item['deadline_date'])
        self.assertNotIn('clock_start_date', item)

    def test_procurement_intent_has_no_window(self) -> None:
        facts = ccgp_record(facts={'lifecycle_state': 'PROCUREMENT_INTENT', 'registration_deadline': None, 'registration_deadline_date': None})['facts']
        self.assertIsNone(legal_windows_for_facts(facts, datetime(2026, 9, 29, tzinfo=TIANJIN)))

    def test_refresh_invalidates_unsupported_legacy_countdown_without_mutation(self) -> None:
        built = [{'code': DOCUMENT_CHALLENGE, 'anchor_date': '2026-09-22', 'deadline_date': '2026-10-09', 'status': 'OPEN', 'remaining_working_days': 7}]
        before = json.loads(json.dumps(built))
        refreshed = refresh_legal_windows(built, datetime(2026, 10, 9, tzinfo=TIANJIN))
        self.assertEqual(refreshed[0]['status'], 'UNKNOWN')
        self.assertIsNone(refreshed[0]['deadline_date'])
        self.assertEqual(built, before)
        self.assertIsNone(refresh_legal_windows(None, datetime(2026, 10, 9, tzinfo=TIANJIN)))


class SnapshotIntegrationTests(unittest.TestCase):
    def test_snapshot_carries_calendar_and_card_windows_outside_facts(self) -> None:
        payload = build_public_snapshot([ccgp_record()], datetime(2026, 9, 29, 10, 0, tzinfo=TIANJIN))
        self.assertEqual(payload["working_calendar"]["code"], CALENDAR_OFFICIAL)
        self.assertEqual(payload["working_calendar"]["legal_basis"], "UNVERIFIED")
        self.assertEqual(payload["working_calendar"]["challenge_working_days"], 7)
        card = payload["opportunity_pool"][0]
        self.assertEqual(card["recommendation_mode"], "LATE_WINDOW")
        self.assertNotIn("legal_windows", card["facts"])
        self.assertIsNone(card["legal_windows"][0]["deadline_date"])
        self.assertEqual(card["legal_windows"][0]["status"], "UNKNOWN")

    def test_bundled_snapshot_contract_is_unchanged_for_scoring(self) -> None:
        payload = build_public_snapshot([ccgp_record()], datetime(2026, 9, 29, 10, 0, tzinfo=TIANJIN))
        card = payload["opportunity_pool"][0]
        stage = next(item for item in card["priority"]["components"] if item["code"] == "INTERVENTION_STAGE")
        self.assertEqual(stage["points"], 8)  # legal windows are display-only; scoring contract untouched


if __name__ == "__main__":
    unittest.main()
