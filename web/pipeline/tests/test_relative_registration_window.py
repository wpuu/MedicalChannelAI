from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from medical_channel_pipeline.public_snapshot import build_public_snapshot
from medical_channel_pipeline.tjfch_test_recruitment import parse_tjfch_test_recruitment

TIANJIN = ZoneInfo("Asia/Shanghai")
TITLE = "天津市第一中心医院共享设备调度系统项目测试企业征集公告"
URL = "https://www.tj-fch.com/system/2026/06/09/030192069.shtml"
INDEX = "https://www.tj-fch.com/ywgk/"


def record() -> dict:
    html = f'''
    <h1>{TITLE}</h1>
    <div>2026-06-11 09:12</div>
    <p>1.项目名称：共享设备调度系统项目</p>
    <p>自公告发布之日起7天，测试企业发送相关报名材料至sdyzxxxc@tj.gov.cn邮箱，逾期无效。</p>
    <p>本次测试调研仅为采购前期需求核实使用，不构成任何采购要约。</p>
    <p>联系电话：022-23628330</p>
    '''
    return parse_tjfch_test_recruitment(
        html,
        source_url=URL,
        index_url=INDEX,
        expected_title=TITLE,
        observed_at="2026-06-11T02:00:00+00:00",
        opportunity_id="tjfch_20260609_030192069",
    )


class RelativeRegistrationWindowTests(unittest.TestCase):
    def test_relative_window_is_actionable_without_fake_official_deadline(self) -> None:
        payload = build_public_snapshot(
            [record()],
            datetime(2026, 6, 12, 10, 0, tzinfo=TIANJIN),
        )
        self.assertEqual(payload["opportunity_pool_count"], 1)
        card = payload["opportunity_pool"][0]
        self.assertEqual(card["recommendation_mode"], "PUBLIC_OPPORTUNITY")
        self.assertIsNone(card["facts"]["registration_deadline"])
        self.assertIsNone(card["facts"]["registration_deadline_date"])
        self.assertIsNone(card["facts"]["bid_deadline"])
        self.assertIn("RELATIVE_REGISTRATION_WINDOW_7_DAYS", card["facts"]["quality_flags"])
        urgency = next(item for item in card["priority"]["components"] if item["code"] == "DEADLINE_URGENCY")
        self.assertGreater(urgency["points"], 0)

    def test_relative_window_expires_operationally_after_bounded_period(self) -> None:
        payload = build_public_snapshot(
            [record()],
            datetime(2026, 6, 20, 10, 0, tzinfo=TIANJIN),
        )
        self.assertEqual(payload["opportunity_pool_count"], 0)


if __name__ == "__main__":
    unittest.main()
