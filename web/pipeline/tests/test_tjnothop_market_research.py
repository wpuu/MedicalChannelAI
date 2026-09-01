from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from medical_channel_pipeline.public_snapshot import build_public_snapshot
from medical_channel_pipeline.tjnothop_market_research import (
    TjnothopParseError,
    parse_tjnothop_market_research,
)
from medical_channel_pipeline.validation import ValidationError, validate_record


DETAIL_URL = "https://www.tjnothop.cn/system/2026/07/03/030101007.shtml"
INDEX_URL = "https://www.tjnothop.cn/xwzx/index.shtml"
TITLE = "天津市天津医院 血液透析机采购项目调研公告"
DETAIL_HTML = """
<html><head><title>天津市天津医院 血液透析机采购项目调研公告</title></head><body>
<h1>天津市天津医院 血液透析机采购项目调研公告</h1>
<p>通知公告</p>
<p>为进一步落实《政府采购需求管理办法》，明确采购需求和采购预算，拟对血液透析机采购项目开展需求调查工作，现欢迎具备资质的供应商参与调研。</p>
<p>一、产品要求：</p>
<p>1、产品名称：血液透析机 2、采购数量：6台 3、预算金额：120万元 4、产品用途：用于尿毒症患者的维持性透析治疗</p>
<p>三、提交报名资料方式：胶装报名资料现场提交至设备物资科（住院部B区三楼）</p>
<p>四、报名及资质提交时间：2026年7月2日至2026年7月10日（逾期不予参加论证）</p>
<p>五、论证时间：另行通知</p>
<p>六、联系电话：022-60910433</p>
</body></html>
"""


def parsed_record() -> dict:
    return parse_tjnothop_market_research(
        DETAIL_HTML,
        source_url=DETAIL_URL,
        index_url=INDEX_URL,
        index_published_at="2026-07-03",
        expected_title=TITLE,
        observed_at="2026-08-31T20:00:00+08:00",
        opportunity_id="tjnothop_20260703_030101007",
    )


class TjnothopMarketResearchTests(unittest.TestCase):
    def test_official_equipment_research_becomes_verified_date_only_record(self) -> None:
        record = parsed_record()
        facts = record["facts"]
        self.assertEqual(facts["project_name"], TITLE)
        self.assertEqual(facts["buyer_name"], "天津市天津医院")
        self.assertEqual(facts["lifecycle_state"], "MARKET_RESEARCH")
        self.assertEqual(facts["published_at"], "2026-07-03")
        self.assertIsNone(facts["registration_deadline"])
        self.assertEqual(facts["registration_deadline_date"], "2026-07-10")
        self.assertEqual(facts["budget_cny"], 1_200_000)
        self.assertEqual(facts["product_items"][0]["raw_name"], "血液透析机")
        self.assertEqual(facts["product_items"][0]["quantity"], "6台")
        self.assertEqual(facts["public_contact"]["phone"], "022-60910433")
        self.assertIn("DEADLINE_TIME_NOT_PUBLISHED", record["quality_flags"])
        published_evidence = next(
            item for item in record["evidence"] if item["field_path"] == "facts.published_at"
        )
        self.assertEqual(published_evidence["source_url"], INDEX_URL)

    def test_date_only_deadline_is_actionable_on_same_tianjin_calendar_day(self) -> None:
        record = parsed_record()
        snapshot = build_public_snapshot(
            [record],
            datetime(2026, 7, 10, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        self.assertEqual(snapshot["matched_count"], 1)
        card = snapshot["cards"][0]
        self.assertEqual(card["recommendation_mode"], "PUBLIC_OPPORTUNITY")
        self.assertIsNone(card["facts"]["registration_deadline"])
        self.assertEqual(card["facts"]["registration_deadline_date"], "2026-07-10")
        self.assertEqual(card["facts"]["registration_deadline_precision"], "DAY")
        self.assertIn("DEADLINE_TIME_NOT_PUBLISHED", card["priority"]["warnings"])
        self.assertEqual(card["evidence_source_urls"], [DETAIL_URL, INDEX_URL])

    def test_date_only_deadline_is_archived_after_calendar_date_passes(self) -> None:
        snapshot = build_public_snapshot(
            [parsed_record()],
            datetime(2026, 7, 11, 0, 1, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        self.assertEqual(snapshot["matched_count"], 0)
        self.assertEqual(snapshot["cards"], [])

    def test_precise_and_date_only_deadline_cannot_both_be_claimed(self) -> None:
        record = parsed_record()
        bad = deepcopy(record)
        bad["facts"]["registration_deadline"] = "2026-07-10T17:00:00+08:00"
        bad["evidence"].append(
            {
                "field_path": "facts.registration_deadline",
                "source_url": DETAIL_URL,
                "locator": "invented for regression test only",
            }
        )
        with self.assertRaisesRegex(ValidationError, "REGISTRATION_DEADLINE_PRECISION_CONFLICT"):
            validate_record(bad)

    def test_title_mismatch_between_index_and_detail_fails_closed(self) -> None:
        with self.assertRaisesRegex(TjnothopParseError, "TJNOTHOP_TITLE_MISMATCH"):
            parse_tjnothop_market_research(
                DETAIL_HTML,
                source_url=DETAIL_URL,
                index_url=INDEX_URL,
                index_published_at="2026-07-03",
                expected_title="天津市天津医院 另一设备采购项目调研公告",
                observed_at="2026-08-31T20:00:00+08:00",
                opportunity_id="bad-title",
            )

    def test_cross_host_index_evidence_is_rejected(self) -> None:
        with self.assertRaisesRegex(TjnothopParseError, "TJNOTHOP_INDEX_HOST_REJECTED"):
            parse_tjnothop_market_research(
                DETAIL_HTML,
                source_url=DETAIL_URL,
                index_url="https://example.com/index.shtml",
                index_published_at="2026-07-03",
                expected_title=TITLE,
                observed_at="2026-08-31T20:00:00+08:00",
                opportunity_id="bad-index",
            )


if __name__ == "__main__":
    unittest.main()
