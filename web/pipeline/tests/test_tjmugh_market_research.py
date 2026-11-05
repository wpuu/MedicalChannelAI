from __future__ import annotations

import json
import re
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline import build_public_snapshot, validate_records
from medical_channel_pipeline.tjmugh_market_research import (
    TjmughParseError,
    parse_tjmugh_market_research,
)


FIXTURE = """
<html><body>
<h3>天津医科大学总医院医疗设备项目市场调研论证邀请函</h3>
<div>2026-08-05 02:35</div>
<p>天津医科大学总医院设备采购科根据本年度采购计划安排，拟开展院内项目市场调研论证，兹邀请符合要求的供应商参加。</p>
<p>一、论证项目名称：</p>
<p>（1）创面洗消设备（2）腹腔镜系统2套（3）高频电刀3台（4）卡式蒸汽灭菌器（5）便携式睡眠仪</p>
<p>二、供应商参加本次论证活动必须提供下列相关材料：</p>
<p>本次报名截止时间为：2026年8月7日下午17：:00点前。</p>
<p>三、联系方式：</p><p>联系电话：60361777张老师</p>
</body></html>
"""

FRAGMENTED_LIVE_FIXTURE = """
<html><body>
<h3>天津医科大学总医院医疗设备项目市场调研论证邀请函</h3>
<div>2026-08-31 09:00</div>
<p>天津医科大学总医院设备采购科拟开展院内项目市场调研论证。</p>
<p>一、论证项目名称：</p>
<p>（1）设备甲（2）设备乙2套</p>
<p>二、供应商参加本次论证活动必须提供下列相关材料：</p>
<p>本次报名为现场报名，报名需携带营业执照，报名截止时间为：2026年9月3日下午17：:0<span>0</span>点前。</p>
<p>三、联系方式：</p>
<p>联系电话：6<span>036</span><span>177</span><span>7张老师</span></p>
</body></html>
"""

NOVEMBER_SOURCE_URL = "https://www.tjmugh.com.cn/system/2026/11/05/030368176.shtml"
NOVEMBER_OBSERVED_AT = "2026-11-06T00:13:33.196744+08:00"
NOVEMBER_FIXTURE = (Path(__file__).parent / "fixtures" / "tjmugh_market_research_20261105.html").read_text(encoding="utf-8")


class TjmughMarketResearchTests(unittest.TestCase):
    def test_frozen_november_official_numbered_list_becomes_verified_without_invented_facts(self) -> None:
        record = parse_tjmugh_market_research(
            NOVEMBER_FIXTURE, source_url=NOVEMBER_SOURCE_URL,
            observed_at=NOVEMBER_OBSERVED_AT, opportunity_id="tjmugh_20261105_030368176",
        )
        self.assertEqual(len(validate_records([record])), 1)
        facts = record["facts"]
        self.assertEqual(facts["published_at"], "2026-11-05")
        self.assertEqual(facts["registration_deadline"], "2026-11-09T17:00:00+08:00")
        self.assertEqual([item["raw_name"] for item in facts["product_items"]], [
            "中毒通信指挥系统（ 安全智能头盔 、 移动视频采集终端（工作记录仪） 、 单兵距离采集终端（相对测距搜救终端） ）",
            "胚胎激光破膜仪",
            "PCR仪、水平电泳仪、凝胶成像系统、化学发光成像系统、离心机、电动移液器、电动移液枪、套组移液枪、分光光度计、生物信息分析工作站、生物样本库管理系统、甲壁微循环、全自动化学发光免疫分析仪、肺功能检测仪、射频皮肤治疗仪 、 气象色谱检测器、凝胶成像系统、蛋白质免疫印记制胶系统设备",
        ])
        for item in facts["product_items"]:
            self.assertIsNone(item["category"])
            self.assertIsNone(item["quantity"])
            self.assertIsNone(item["specification"])
        self.assertEqual({item["source_url"] for item in record["evidence"]}, {NOVEMBER_SOURCE_URL})
        snapshot = build_public_snapshot([record], datetime.fromisoformat(NOVEMBER_OBSERVED_AT))
        self.assertEqual(snapshot["opportunity_pool"][0]["facts"]["verification_status"], "VERIFIED")
        self.assertEqual(snapshot["opportunity_pool"][0]["facts"]["product_items"], facts["product_items"])

    def test_numbered_list_keeps_model_numbers_and_internal_delimiters_inside_product_name(self) -> None:
        original_items = "（1）创面洗消设备（2）腹腔镜系统2套（3）高频电刀3台（4）卡式蒸汽灭菌器（5）便携式睡眠仪"
        html = FIXTURE.replace(original_items, "1、型号A1、B系列PCR仪 2、3.0T磁共振设备")
        record = parse_tjmugh_market_research(
            html, source_url="https://www.tjmugh.com.cn/system/2026/08/05/030326488.shtml",
            observed_at="2026-08-06T08:42:00Z", opportunity_id="numbered_models",
        )
        self.assertEqual([item["raw_name"] for item in record["facts"]["product_items"]], [
            "型号A1、B系列PCR仪", "3.0T磁共振设备",
        ])

    def test_ordinary_numbers_and_supplier_section_cannot_become_numbered_products(self) -> None:
        original_items = "（1）创面洗消设备（2）腹腔镜系统2套（3）高频电刀3台（4）卡式蒸汽灭菌器（5）便携式睡眠仪"
        for raw_items in ("设备2026、型号3套", "设备数量1台，说明 1、检查材料 2、操作说明", "设备数量1台"):
            with self.subTest(raw_items=raw_items):
                html = FIXTURE.replace(original_items, raw_items).replace(
                    "二、供应商参加本次论证活动必须提供下列相关材料：",
                    "二、供应商参加本次论证活动必须提供下列相关材料：1、营业执照 2、资质证明",
                )
                with self.assertRaisesRegex(TjmughParseError, "TJMUGH_PROJECT_ITEMS_NOT_FOUND"):
                    parse_tjmugh_market_research(
                        html, source_url="https://www.tjmugh.com.cn/system/2026/08/05/030326488.shtml",
                        observed_at="2026-08-06T08:42:00Z", opportunity_id="ordinary_numbers",
                    )

    def test_incomplete_or_repeated_new_numbering_fails_closed(self) -> None:
        original_items = "（1）创面洗消设备（2）腹腔镜系统2套（3）高频电刀3台（4）卡式蒸汽灭菌器（5）便携式睡眠仪"
        for raw_items in ("1、PCR仪 3、胚胎激光破膜仪", "1、PCR仪 1、胚胎激光破膜仪"):
            with self.subTest(raw_items=raw_items):
                with self.assertRaisesRegex(TjmughParseError, "TJMUGH_PROJECT_ITEM_SEQUENCE_INVALID"):
                    parse_tjmugh_market_research(
                        FIXTURE.replace(original_items, raw_items),
                        source_url="https://www.tjmugh.com.cn/system/2026/08/05/030326488.shtml",
                        observed_at="2026-08-06T08:42:00Z", opportunity_id="invalid_numbering",
                    )

    def test_existing_ascii_parenthesized_numbering_remains_supported(self) -> None:
        html = re.sub(r"（([1-5])）", r"(\1)", FIXTURE)
        record = parse_tjmugh_market_research(
            html, source_url="https://www.tjmugh.com.cn/system/2026/08/05/030326488.shtml",
            observed_at="2026-08-06T08:42:00Z", opportunity_id="ascii_parentheses",
        )
        self.assertEqual(len(record["facts"]["product_items"]), 5)

    def test_official_market_research_page_becomes_verified_record(self) -> None:
        record = parse_tjmugh_market_research(
            FIXTURE,
            source_url="https://www.tjmugh.com.cn/system/2026/08/05/030326488.shtml",
            observed_at="2026-08-31T08:42:00Z",
            opportunity_id="tjmugh_20260805_030326488",
        )
        self.assertEqual(record["source"]["source_type"], "OFFICIAL_INSTITUTION_NOTICE")
        self.assertEqual(record["facts"]["lifecycle_state"], "MARKET_RESEARCH")
        self.assertEqual(record["facts"]["registration_deadline"], "2026-08-07T17:00:00+08:00")
        self.assertEqual(len(record["facts"]["product_items"]), 5)
        self.assertEqual(record["facts"]["public_contact"]["phone"], "60361777")

    def test_live_numeric_node_fragmentation_does_not_destroy_verified_facts(self) -> None:
        record = parse_tjmugh_market_research(
            FRAGMENTED_LIVE_FIXTURE,
            source_url="https://www.tjmugh.com.cn/system/2026/08/31/030337994.shtml",
            observed_at="2026-09-01T18:43:00Z",
            opportunity_id="tjmugh_20260831_030337994",
        )
        self.assertEqual(record["facts"]["registration_deadline"], "2026-09-03T17:00:00+08:00")
        self.assertEqual(record["facts"]["public_contact"]["phone"], "60361777")
        self.assertEqual(record["facts"]["public_contact"]["name"], "张老师")
        self.assertEqual([item["raw_name"] for item in record["facts"]["product_items"]], ["设备甲", "设备乙2套"])

    def test_closed_market_research_is_kept_in_fact_layer_but_not_today_feed(self) -> None:
        seed = Path(__file__).resolve().parents[1] / "data" / "tianjin_official_institution_seed.json"
        records = json.loads(seed.read_text(encoding="utf-8"))
        self.assertEqual(len(validate_records(records)), 1)
        payload = build_public_snapshot(records, datetime.fromisoformat("2026-08-31T16:42:00+08:00"))
        self.assertEqual(payload["input_candidate_count"], 1)
        self.assertEqual(payload["matched_count"], 0)
        self.assertEqual(payload["card_count"], 0)
        self.assertEqual(payload["cards"], [])

    def test_unapproved_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(TjmughParseError, "TJMUGH_SOURCE_HOST_REJECTED"):
            parse_tjmugh_market_research(
                FIXTURE,
                source_url="https://example.com/fake",
                observed_at="2026-08-31T08:42:00Z",
                opportunity_id="bad",
            )

    def test_missing_deadline_fails_closed(self) -> None:
        html = FIXTURE.replace("本次报名截止时间为：2026年8月7日下午17：:00点前。", "报名时间另行通知")
        with self.assertRaisesRegex(TjmughParseError, "TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND"):
            parse_tjmugh_market_research(
                html,
                source_url="https://www.tjmugh.com.cn/system/2026/08/05/030326488.shtml",
                observed_at="2026-08-31T08:42:00Z",
                opportunity_id="tjmugh_20260805_030326488",
            )


if __name__ == "__main__":
    unittest.main()
