from __future__ import annotations

import unittest

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


class TjmughMarketResearchTests(unittest.TestCase):
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
