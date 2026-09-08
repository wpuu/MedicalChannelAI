from __future__ import annotations

import unittest

from medical_channel_pipeline.ccgp_detail import (
    CcgpDetailParseError,
    parse_ccgp_public_tender_text,
)


NATIONAL_CCGP_FIXTURE = """
公开招标公告
采购项目名称 | 中日友好医院免散瞳眼底照相机系统采购项目
采购单位 | 中日友好医院
行政区域 | 北京市 | 公告时间 | 2026年09月07日 17:30
发布日期：2026年09月07日
一、项目基本情况
项目编号：B0708-CMC26N7819
项目名称：中日友好医院免散瞳眼底照相机系统采购项目
预算金额：180.0万元
三、获取招标文件
时间：2026年09月08日 至 2026年09月14日，每天上午09:00至12:00，下午12:00至16:00（北京时间，法定节假日除外）
地点：线上获取
四、提交投标文件截止时间、开标时间和地点
提交投标文件截止时间：2026年09月29日 09点30分（北京时间）
七、对本次招标提出询问，请按以下方式联系。
1.采购人信息 名称：中日友好医院 地址：北京市朝阳区
"""


class CcgpNationalDetailFormatTests(unittest.TestCase):
    def test_public_tender_accepts_official_to_separator_and_explicit_bid_label(self) -> None:
        record = parse_ccgp_public_tender_text(
            NATIONAL_CCGP_FIXTURE,
            source_url="https://www.ccgp.gov.cn/cggg/zygg/gkzb/202609/t20260907_27282514.htm",
            observed_at="2026-09-08T12:51:45+08:00",
            opportunity_id="ccgp_b0708_cmc26n7819",
        )
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "B0708-CMC26N7819")
        self.assertEqual(facts["project_name"], "中日友好医院免散瞳眼底照相机系统采购项目")
        self.assertEqual(facts["buyer_name"], "中日友好医院")
        self.assertEqual(facts["region"], "北京市")
        self.assertEqual(facts["registration_deadline"], "2026-09-14T16:00:00+08:00")
        self.assertEqual(facts["bid_deadline"], "2026-09-29T09:30:00+08:00")
        self.assertEqual(facts["budget_cny"], 1_800_000)

    def test_national_format_without_explicit_daily_end_time_still_fails_closed(self) -> None:
        text = NATIONAL_CCGP_FIXTURE.replace(
            "下午12:00至16:00",
            "下午时间以采购代理机构通知为准",
        )
        with self.assertRaisesRegex(
            CcgpDetailParseError,
            "CCGP_REGISTRATION_END_TIME_NOT_FOUND",
        ):
            parse_ccgp_public_tender_text(
                text,
                source_url="https://www.ccgp.gov.cn/cggg/zygg/gkzb/202609/t20260907_27282514.htm",
                observed_at="2026-09-08T12:51:45+08:00",
                opportunity_id="ccgp_missing_daily_end_time",
            )


if __name__ == "__main__":
    unittest.main()
