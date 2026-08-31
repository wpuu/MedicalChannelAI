from __future__ import annotations

import unittest

from medical_channel_pipeline.ccgp_detail import (
    CcgpDetailParseError,
    parse_ccgp_public_tender_text,
)


FIXTURE = """
公开招标公告
公告信息： 采购项目名称 | 病原微生物能力提升相关设备购置
采购单位 | 天津市滨海新区疾病预防控制中心（天津市滨海新区卫生监督所）
行政区域 | 滨海新区 | 公告时间 | 2026年08月24日 18:50
发布日期：2026年08月24日
一、项目基本情况
项目编号：XCSD-2026-C-181
项目名称：病原微生物能力提升相关设备购置
预算金额：270.0万元
最高限价：270.0万元
采购需求：
第1包 否 190 190 其他医疗设备 具体内容详见项目需求书。第一包：基因测序仪、自动化建库仪、宏基因组分析系统的采购；
第2包 否 80 80 其他医疗设备 具体内容详见项目需求书。第二包：微生物质谱检测系统（飞行时间质谱检测系统）、高性能生物计算工业一体机的采购；
二、申请人的资格要求：略
三、获取招标文件
时间：2026年08月24日到 2026年08月31日，每天上午09:00至11:30，下午13:30至16:00（北京时间，法定节假日除外）
地点：天津信诚盛德工程咨询有限公司
四、提交投标文件截止时间、开标时间和地点
2026年09月14日 09点30分（北京时间）。
七、对本次招标提出询问，请按以下方式联系。
1.采购人信息 名称：天津市滨海新区疾病预防控制中心（天津市滨海新区卫生监督所） 地址：天津市滨海新区北塘街嘉顺路575号
2.采购代理机构信息 名称：天津信诚盛德工程咨询有限公司
3.项目联系方式 项目联系人：李宁 电 话：022-23717450-8019
"""


class CcgpDetailTests(unittest.TestCase):
    def test_public_tender_detail_becomes_verified_canonical_record(self) -> None:
        record = parse_ccgp_public_tender_text(
            FIXTURE,
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260824_27194426.htm",
            observed_at="2026-08-31T18:15:00+08:00",
            opportunity_id="ccgp_xcsd_2026_c_181",
        )
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "XCSD-2026-C-181")
        self.assertEqual(facts["project_name"], "病原微生物能力提升相关设备购置")
        self.assertEqual(
            facts["buyer_name"],
            "天津市滨海新区疾病预防控制中心（天津市滨海新区卫生监督所）",
        )
        self.assertEqual(facts["region"], "滨海新区")
        self.assertEqual(facts["published_at"], "2026-08-24")
        self.assertEqual(facts["registration_deadline"], "2026-08-31T16:00:00+08:00")
        self.assertEqual(facts["bid_deadline"], "2026-09-14T09:30:00+08:00")
        self.assertEqual(facts["budget_cny"], 2_700_000)
        self.assertEqual(len(facts["product_items"]), 2)
        self.assertIn("基因测序仪", facts["product_items"][0]["raw_name"])
        self.assertEqual(facts["public_contact"]["name"], "李宁")
        self.assertEqual(facts["public_contact"]["phone"], "022-23717450-8019")

    def test_missing_exact_registration_end_time_fails_closed(self) -> None:
        text = FIXTURE.replace("下午13:30至16:00", "下午时间以代理机构通知为准")
        with self.assertRaisesRegex(
            CcgpDetailParseError,
            "CCGP_REGISTRATION_END_TIME_NOT_FOUND",
        ):
            parse_ccgp_public_tender_text(
                text,
                source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260824_27194426.htm",
                observed_at="2026-08-31T18:15:00+08:00",
                opportunity_id="bad_deadline",
            )

    def test_non_ccgp_detail_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            CcgpDetailParseError,
            "CCGP_DETAIL_SOURCE_HOST_REJECTED",
        ):
            parse_ccgp_public_tender_text(
                FIXTURE,
                source_url="https://example.com/fake",
                observed_at="2026-08-31T18:15:00+08:00",
                opportunity_id="bad_host",
            )


if __name__ == "__main__":
    unittest.main()
