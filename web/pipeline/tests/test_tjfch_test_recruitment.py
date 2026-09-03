from __future__ import annotations

import unittest

from medical_channel_pipeline.tjfch_test_recruitment import (
    RELATIVE_WINDOW_FLAG,
    TjfchTestParseError,
    parse_tjfch_test_recruitment,
)

SOURCE_URL = "https://www.tj-fch.com/system/2026/06/09/030192069.shtml"
INDEX_URL = "https://www.tj-fch.com/ywgk/"
TITLE = "天津市第一中心医院共享设备调度系统项目测试企业征集公告"


def page(*, published: str = "2026-06-11 09:12", window: str = "自公告发布之日起7天", overdue: str = "逾期无效") -> str:
    return f'''
    <html><body>
      <h1>{TITLE}</h1>
      <div>{published}</div>
      <p>一、项目基本信息</p>
      <p>1.项目名称：天津市第一中心医院共享设备调度系统项目</p>
      <p>四、测试安排</p>
      <p>1.测试报名阶段 {window}，测试企业发送相关报名材料至sdyzxxxc@tj.gov.cn邮箱，{overdue}。</p>
      <p>五、其他事项</p>
      <p>本次测试调研仅为采购前期需求核实使用，不构成任何采购要约。</p>
      <p>联系电话：022-2362 8330</p>
    </body></html>
    '''


class TjfchTestRecruitmentTests(unittest.TestCase):
    def test_verified_test_recruitment_becomes_pre_market_record_without_fake_deadline(self) -> None:
        record = parse_tjfch_test_recruitment(
            page(),
            source_url=SOURCE_URL,
            index_url=INDEX_URL,
            expected_title=TITLE,
            observed_at="2026-06-11T02:00:00+00:00",
            opportunity_id="tjfch_20260609_030192069",
        )
        facts = record["facts"]
        self.assertEqual(facts["published_at"], "2026-06-11")
        self.assertEqual(facts["lifecycle_state"], "PRE_MARKET_RESEARCH")
        self.assertEqual(facts["notice_type"], "测试企业征集公告")
        self.assertIsNone(facts["registration_deadline"])
        self.assertIsNone(facts["registration_deadline_date"])
        self.assertIsNone(facts["bid_deadline"])
        self.assertEqual(facts["public_contact"]["email"], "sdyzxxxc@tj.gov.cn")
        self.assertEqual(facts["public_contact"]["phone"], "022-23628330")
        self.assertIn(RELATIVE_WINDOW_FLAG, record["quality_flags"])

    def test_detail_publication_date_is_authoritative_not_url_path_date(self) -> None:
        record = parse_tjfch_test_recruitment(
            page(published="2026-06-11 09:12"),
            source_url=SOURCE_URL,
            index_url=INDEX_URL,
            expected_title=TITLE,
            observed_at="2026-06-11T02:00:00+00:00",
            opportunity_id="tjfch_20260609_030192069",
        )
        self.assertEqual(record["facts"]["published_at"], "2026-06-11")
        self.assertNotEqual(record["facts"]["published_at"], "2026-06-09")

    def test_relative_window_is_not_converted_to_official_deadline(self) -> None:
        record = parse_tjfch_test_recruitment(
            page(),
            source_url=SOURCE_URL,
            index_url=INDEX_URL,
            expected_title=TITLE,
            observed_at="2026-06-11T02:00:00+00:00",
            opportunity_id="tjfch_20260609_030192069",
        )
        self.assertNotIn("2026-06-18", str(record["facts"]))

    def test_non_seven_day_or_unbounded_window_is_rejected(self) -> None:
        with self.assertRaisesRegex(TjfchTestParseError, "REGISTRATION_WINDOW_UNSUPPORTED"):
            parse_tjfch_test_recruitment(
                page(window="自公告发布之日起5天"),
                source_url=SOURCE_URL,
                index_url=INDEX_URL,
                expected_title=TITLE,
                observed_at="2026-06-11T02:00:00+00:00",
                opportunity_id="tjfch_20260609_030192069",
            )
        with self.assertRaisesRegex(TjfchTestParseError, "REGISTRATION_WINDOW_UNSUPPORTED"):
            parse_tjfch_test_recruitment(
                page(overdue="请及时报名"),
                source_url=SOURCE_URL,
                index_url=INDEX_URL,
                expected_title=TITLE,
                observed_at="2026-06-11T02:00:00+00:00",
                opportunity_id="tjfch_20260609_030192069",
            )

    def test_non_official_host_and_title_mismatch_fail_closed(self) -> None:
        with self.assertRaisesRegex(TjfchTestParseError, "SOURCE_HOST_REJECTED"):
            parse_tjfch_test_recruitment(
                page(),
                source_url="https://evil.example/system/2026/06/09/030192069.shtml",
                index_url=INDEX_URL,
                expected_title=TITLE,
                observed_at="2026-06-11T02:00:00+00:00",
                opportunity_id="tjfch_20260609_030192069",
            )
        with self.assertRaisesRegex(TjfchTestParseError, "TITLE_MISMATCH"):
            parse_tjfch_test_recruitment(
                page(),
                source_url=SOURCE_URL,
                index_url=INDEX_URL,
                expected_title="天津市第一中心医院另一项目测试企业征集公告",
                observed_at="2026-06-11T02:00:00+00:00",
                opportunity_id="tjfch_20260609_030192069",
            )


if __name__ == "__main__":
    unittest.main()
