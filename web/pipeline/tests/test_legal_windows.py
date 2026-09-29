from __future__ import annotations

import json
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from medical_channel_pipeline.legal_windows import (
    CALENDAR_OFFICIAL,
    CALENDAR_WEEKENDS_ONLY,
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
    def test_document_challenge_window_from_acquisition_cutoff(self) -> None:
        facts = ccgp_record()["facts"]
        windows = legal_windows_for_facts(facts, datetime(2026, 9, 29, 10, 0, tzinfo=TIANJIN))
        self.assertIsNotNone(windows)
        assert windows is not None
        (item,) = windows
        self.assertEqual(item["code"], DOCUMENT_CHALLENGE)
        self.assertEqual(item["anchor_kind"], "DOCUMENT_ACQUISITION_END")
        self.assertEqual(item["anchor_date"], "2026-09-22")
        self.assertNotIn("clock_start_date", item)  # equal to anchor → omitted for compactness
        self.assertEqual(item["deadline_date"], "2026-10-09")
        self.assertEqual(item["remaining_working_days"], 4)
        self.assertEqual(item["status"], "OPEN")
        self.assertNotIn("calendar", item)  # official calendar covers the dates

    def test_document_challenge_window_closes_after_deadline(self) -> None:
        facts = ccgp_record()["facts"]
        windows = legal_windows_for_facts(facts, datetime(2026, 10, 12, 9, 0, tzinfo=TIANJIN))
        assert windows is not None
        self.assertEqual(windows[0]["status"], "CLOSED")
        self.assertEqual(windows[0]["remaining_working_days"], 0)

    def test_date_only_registration_deadline_is_supported(self) -> None:
        facts = ccgp_record(facts={"registration_deadline": None, "registration_deadline_date": "2026-09-11"})["facts"]
        windows = legal_windows_for_facts(facts, datetime(2026, 9, 21, 9, 0, tzinfo=TIANJIN))
        assert windows is not None
        item = windows[0]
        self.assertEqual(item["deadline_date"], "2026-09-21")
        self.assertEqual(item["remaining_working_days"], 1)  # 今天 9/21 是最后一天

    def test_registration_deadline_converted_to_tianjin_date(self) -> None:
        # 2026-09-22T16:30+08:00 stored as UTC is still 9/22 in Tianjin.
        facts = ccgp_record(facts={"registration_deadline": "2026-09-22T08:30:00+00:00"})["facts"]
        windows = legal_windows_for_facts(facts, datetime(2026, 9, 23, 9, 0, tzinfo=TIANJIN))
        assert windows is not None
        self.assertEqual(windows[0]["anchor_date"], "2026-09-22")

    def test_result_challenge_window_for_award_notice(self) -> None:
        facts = ccgp_record(
            facts={
                "lifecycle_state": "AWARDED",
                "notice_type": "中标公告",
                "published_at": "2026-09-24",  # 周四; 公告期限 1 个工作日 → 9/28(周一) 届满
                "registration_deadline": None,
                "bid_deadline": None,
            }
        )["facts"]
        windows = legal_windows_for_facts(facts, datetime(2026, 9, 29, 9, 0, tzinfo=TIANJIN))
        assert windows is not None
        (item,) = windows
        self.assertEqual(item["code"], RESULT_CHALLENGE)
        self.assertEqual(item["anchor_kind"], "AWARD_NOTICE_PERIOD_END")
        self.assertEqual(item["anchor_date"], "2026-09-24")
        self.assertEqual(item["clock_start_date"], "2026-09-28")
        # 9/29 9/30 10/8 10/9 10/10(调休) 10/12 10/13
        self.assertEqual(item["deadline_date"], "2026-10-13")
        self.assertEqual(item["remaining_working_days"], 7)
        self.assertEqual(item["status"], "OPEN")

    def test_procurement_intent_has_no_window(self) -> None:
        facts = ccgp_record(
            facts={
                "lifecycle_state": "PROCUREMENT_INTENT",
                "notice_type": "采购意向公告",
                "registration_deadline": None,
                "registration_deadline_date": None,
                "bid_deadline": None,
            }
        )["facts"]
        self.assertIsNone(legal_windows_for_facts(facts, datetime(2026, 9, 29, tzinfo=TIANJIN)))

    def test_outside_calendar_coverage_is_labelled_as_estimate(self) -> None:
        facts = ccgp_record(facts={"registration_deadline": "2027-03-01T17:00:00+08:00"})["facts"]
        windows = legal_windows_for_facts(facts, datetime(2027, 3, 2, tzinfo=TIANJIN))
        assert windows is not None
        self.assertEqual(windows[0]["calendar"], CALENDAR_WEEKENDS_ONLY)

    def test_refresh_only_touches_remaining_and_status(self) -> None:
        facts = ccgp_record()["facts"]
        built = legal_windows_for_facts(facts, datetime(2026, 9, 23, tzinfo=TIANJIN))
        assert built is not None
        self.assertEqual(built[0]["remaining_working_days"], 7)  # 9/23 9/24 9/28 9/29 9/30 10/8 10/9
        refreshed = refresh_legal_windows(built, datetime(2026, 10, 9, 18, 0, tzinfo=TIANJIN))
        assert refreshed is not None
        self.assertEqual(refreshed[0]["remaining_working_days"], 1)
        self.assertEqual(refreshed[0]["status"], "OPEN")
        self.assertEqual(refreshed[0]["deadline_date"], built[0]["deadline_date"])
        self.assertEqual(built[0]["remaining_working_days"], 7)  # input not mutated
        self.assertIsNone(refresh_legal_windows(None, datetime(2026, 10, 9, tzinfo=TIANJIN)))


class SnapshotIntegrationTests(unittest.TestCase):
    def test_snapshot_carries_calendar_and_card_windows_outside_facts(self) -> None:
        payload = build_public_snapshot([ccgp_record()], datetime(2026, 9, 29, 10, 0, tzinfo=TIANJIN))
        self.assertEqual(payload["working_calendar"]["code"], CALENDAR_OFFICIAL)
        self.assertEqual(payload["working_calendar"]["legal_basis"], "MOF_ORDER_94")
        self.assertEqual(payload["working_calendar"]["challenge_working_days"], 7)
        card = payload["opportunity_pool"][0]
        self.assertEqual(card["recommendation_mode"], "LATE_WINDOW")
        self.assertNotIn("legal_windows", card["facts"])
        self.assertEqual(card["legal_windows"][0]["deadline_date"], "2026-10-09")
        self.assertEqual(card["legal_windows"][0]["remaining_working_days"], 4)

    def test_bundled_snapshot_contract_is_unchanged_for_scoring(self) -> None:
        payload = build_public_snapshot([ccgp_record()], datetime(2026, 9, 29, 10, 0, tzinfo=TIANJIN))
        card = payload["opportunity_pool"][0]
        stage = next(item for item in card["priority"]["components"] if item["code"] == "INTERVENTION_STAGE")
        self.assertEqual(stage["points"], 8)  # legal windows are display-only; scoring contract untouched


if __name__ == "__main__":
    unittest.main()
