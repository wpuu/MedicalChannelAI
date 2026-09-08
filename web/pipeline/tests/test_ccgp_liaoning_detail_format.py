from __future__ import annotations

import unittest

from medical_channel_pipeline.ccgp_detail import parse_ccgp_public_tender_text


LIAONING_FIXTURE = """
公开招标公告
采购项目名称 | 医疗设备采购项目
采购单位 | 沈阳市辽中区卫生健康局
行政区域 | 辽中区 | 公告时间 | 2026年01月22日 18:30
一、项目基本情况
项目编号：JH26-210122-00009
项目名称：医疗设备采购项目
预算金额（元）：19570000
四、获取招标文件
时间：2026年01月22日18时30分至2026年01月30日00时00分（北京时间，法定节假日除外）
地点：线上获取
五、提交投标文件截止时间、开标时间和地点
2026年02月12日 09时40分（北京时间）
地点：辽中区公共资源交易中心五楼开标室
七、对本次招标提出询问，请按以下方式联系。
1.采购人信息 名称：沈阳市辽中区卫生健康局 地址：蒲东街道丽水路1号
3.项目联系方式 项目联系人：黄金凤 电话：13079212119
"""


class CcgpLiaoningDetailFormatTests(unittest.TestCase):
    def test_liaoning_section_four_exact_registration_window_is_verified(self) -> None:
        record = parse_ccgp_public_tender_text(
            LIAONING_FIXTURE,
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202601/t20260122_26106594.htm",
            observed_at="2026-01-22T11:00:00+00:00",
            opportunity_id="ccgp_ln_template_test",
        )
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "JH26-210122-00009")
        self.assertEqual(facts["registration_deadline"], "2026-01-30T00:00:00+08:00")
        self.assertEqual(facts["bid_deadline"], "2026-02-12T09:40:00+08:00")
        self.assertEqual(facts["budget_cny"], 19_570_000)
        registration_evidence = next(
            item for item in record["evidence"]
            if item["field_path"] == "facts.registration_deadline"
        )
        self.assertEqual(registration_evidence["locator"], "获取招标文件/时间")

    def test_liaoning_24_hour_registration_end_rolls_to_next_day(self) -> None:
        fixture = LIAONING_FIXTURE.replace(
            "2026年01月30日00时00分",
            "2026年01月29日24时00分",
        )
        record = parse_ccgp_public_tender_text(
            fixture,
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202601/t20260122_26106594.htm",
            observed_at="2026-01-22T11:00:00+00:00",
            opportunity_id="ccgp_ln_24h_template_test",
        )
        self.assertEqual(
            record["facts"]["registration_deadline"],
            "2026-01-30T00:00:00+08:00",
        )


if __name__ == "__main__":
    unittest.main()
