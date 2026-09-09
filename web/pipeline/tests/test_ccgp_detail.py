from __future__ import annotations

import unittest

from medical_channel_pipeline.ccgp_detail import (
    CcgpDetailParseError,
    parse_ccgp_competitive_consultation_text,
    parse_ccgp_public_tender_html,
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

NUMERIC_PACKAGE_FIXTURE = FIXTURE.replace(
    "第1包 否 190 190 其他医疗设备 具体内容详见项目需求书。第一包：基因测序仪、自动化建库仪、宏基因组分析系统的采购；\n"
    "第2包 否 80 80 其他医疗设备 具体内容详见项目需求书。第二包：微生物质谱检测系统（飞行时间质谱检测系统）、高性能生物计算工业一体机的采购；",
    "第1包：基因测序仪、自动化建库仪、宏基因组分析系统的采购；\n"
    "第2包：微生物质谱检测系统（飞行时间质谱检测系统）、高性能生物计算工业一体机的采购；",
)

ATTACHMENT_ONLY_FIXTURE = FIXTURE.replace(
    "第1包 否 190 190 其他医疗设备 具体内容详见项目需求书。第一包：基因测序仪、自动化建库仪、宏基因组分析系统的采购；\n"
    "第2包 否 80 80 其他医疗设备 具体内容详见项目需求书。第二包：微生物质谱检测系统（飞行时间质谱检测系统）、高性能生物计算工业一体机的采购；",
    "第1包 否 190 190 其他医疗设备 具体内容详见项目需求书。\n"
    "第2包 否 80 80 其他医疗设备 具体内容详见项目需求书。",
)

CONSULTATION_FIXTURE = """
竞争性磋商公告
公告信息：
采购项目名称 | 天津市第一中心医院复康院区提升改造项目基础硬件及附属设施建设项目智能语音采集设备采购项目
采购单位 | 天津市第一中心医院
行政区域 | 市辖区 | 公告时间 | 2026年05月15日 18:50
发布日期：2026年05月15日
一、项目基本情况
项目编号：TGPC-2026-A-0081
项目名称：天津市第一中心医院复康院区提升改造项目基础硬件及附属设施建设项目智能语音采集设备采购项目
采购方式：竞争性磋商
预算金额：100.0万元
最高限价：100.0万元
采购需求：
第1包 否 100 100 其他信息化设备 详见竞争性磋商文件
二、申请人的资格要求：略
三、获取采购文件
时间：2026年05月15日到 2026年05月22日，每天上午09:00至12:00，下午12:00至17:00（北京时间，法定节假日除外）
地点：天津市政府采购中心网
四、响应文件提交
截止时间：2026年05月26日 08点30分（北京时间）
地点：天津市政府采购中心网
五、开启
时间：2026年05月26日 09点30分（北京时间）
地点：天津市政府采购中心网
八、凡对本次采购提出询问，请按以下方式联系。
1.采购人信息 名称：天津市第一中心医院 地址：天津市西青区保山西道2号 联系方式：022-23628323
2.采购代理机构信息 名称：天津市政府采购中心 地址：天津市河东区红星路79号二楼 联系方式：022-24538271
3.项目联系方式 项目联系人：张艳、李楠 电 话：022-24538271
"""


STANDARD_PRODUCT_TABLE_HTML_FIXTURE = (
    "<html><body><pre>"
    + FIXTURE
    + "</pre>"
    + """
    <table>
      <tr><th>品目号</th><th>品目名称</th><th>采购标的</th><th>数量（单位）</th><th>技术规格、参数及要求</th><th>品目预算(元)</th></tr>
      <tr><td>1-1</td><td>医用 X 线诊断设备</td><td>64排螺旋CT设备</td><td>1(台)</td><td>详见采购文件</td><td>5800000</td></tr>
      <tr><td>1-2</td><td>医用内窥镜</td><td>电子消化道内窥镜系统</td><td>1(套)</td><td>4K成像</td><td>1500000</td></tr>
    </table>
    """
    + "</body></html>"
)

NON_PRODUCT_TABLE_HTML_FIXTURE = (
    "<html><body><pre>"
    + ATTACHMENT_ONLY_FIXTURE
    + "</pre><table><tr><th>名称</th><th>数量</th></tr><tr><td>附件</td><td>1</td></tr></table></body></html>"
)


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

    def test_non_phone_contact_value_is_preserved_as_name_but_not_dial_target(self) -> None:
        text = FIXTURE.replace(
            "项目联系人：李宁 电 话：022-23717450-8019",
            "项目联系人：董艳 项目联系电话：董艳",
        )
        record = parse_ccgp_public_tender_text(
            text,
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260907_27278298.htm",
            observed_at="2026-09-09T09:30:00+08:00",
            opportunity_id="ccgp_jl_invalid_phone_fixture",
        )
        contact = record["facts"]["public_contact"]
        self.assertEqual(contact["name"], "董艳")
        self.assertIsNone(contact["phone"])

    def test_official_standard_product_table_is_structured_without_title_guessing(self) -> None:
        record = parse_ccgp_public_tender_html(
            STANDARD_PRODUCT_TABLE_HTML_FIXTURE,
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260908_27291415.htm",
            observed_at="2026-09-09T01:55:00+00:00",
            opportunity_id="standard_product_table",
        )
        facts = record["facts"]
        self.assertEqual(facts["product_categories"], ["医用 X 线诊断设备", "医用内窥镜"])
        self.assertEqual(len(facts["product_items"]), 2)
        self.assertEqual(facts["product_items"][0], {
            "raw_name": "64排螺旋CT设备",
            "category": "医用 X 线诊断设备",
            "quantity": "1(台)",
            "specification": "详见采购文件",
        })
        self.assertEqual(facts["product_items"][1]["raw_name"], "电子消化道内窥镜系统")
        evidence_paths = {item["field_path"] for item in record["evidence"]}
        self.assertIn("facts.product_items", evidence_paths)
        self.assertIn("facts.product_categories", evidence_paths)

    def test_unrelated_html_table_does_not_invent_product_items(self) -> None:
        record = parse_ccgp_public_tender_html(
            NON_PRODUCT_TABLE_HTML_FIXTURE,
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260824_27194426.htm",
            observed_at="2026-09-09T01:55:00+00:00",
            opportunity_id="non_product_table",
        )
        self.assertEqual(record["facts"]["product_items"], [])
        self.assertEqual(record["facts"]["product_categories"], [])

    def test_competitive_consultation_uses_response_submission_deadline_not_opening_time(self) -> None:
        record = parse_ccgp_competitive_consultation_text(
            CONSULTATION_FIXTURE,
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/jzxcs/202605/t20260515_26577430.htm",
            observed_at="2026-08-31T18:15:00+08:00",
            opportunity_id="ccgp_tgpc_2026_a_0081",
        )
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "TGPC-2026-A-0081")
        self.assertEqual(facts["procurement_method"], "竞争性磋商")
        self.assertEqual(facts["notice_type"], "竞争性磋商公告")
        self.assertEqual(facts["registration_deadline"], "2026-05-22T17:00:00+08:00")
        self.assertEqual(facts["bid_deadline"], "2026-05-26T08:30:00+08:00")
        self.assertNotEqual(facts["bid_deadline"], "2026-05-26T09:30:00+08:00")
        self.assertEqual(facts["budget_cny"], 1_000_000)
        self.assertEqual(facts["product_items"], [])
        self.assertEqual(facts["public_contact"]["name"], "张艳、李楠")

    def test_competitive_consultation_missing_exact_response_deadline_fails_closed(self) -> None:
        text = CONSULTATION_FIXTURE.replace(
            "截止时间：2026年05月26日 08点30分（北京时间）",
            "截止时间：具体时间另行通知",
        )
        with self.assertRaisesRegex(CcgpDetailParseError, "CCGP_RESPONSE_DEADLINE_NOT_FOUND"):
            parse_ccgp_competitive_consultation_text(
                text,
                source_url="https://www.ccgp.gov.cn/cggg/dfgg/jzxcs/202605/t20260515_26577430.htm",
                observed_at="2026-08-31T18:15:00+08:00",
                opportunity_id="consultation_missing_deadline",
            )

    def test_numeric_package_labels_are_parsed(self) -> None:
        record = parse_ccgp_public_tender_text(
            NUMERIC_PACKAGE_FIXTURE,
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260824_27194426.htm",
            observed_at="2026-08-31T18:15:00+08:00",
            opportunity_id="numeric_packages",
        )
        products = record["facts"]["product_items"]
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["raw_name"], "基因测序仪、自动化建库仪、宏基因组分析系统")
        self.assertIn("微生物质谱检测系统", products[1]["raw_name"])

    def test_attachment_only_package_text_does_not_invent_products(self) -> None:
        record = parse_ccgp_public_tender_text(
            ATTACHMENT_ONLY_FIXTURE,
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260824_27194426.htm",
            observed_at="2026-08-31T18:15:00+08:00",
            opportunity_id="attachment_only",
        )
        self.assertEqual(record["facts"]["product_items"], [])

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
