from __future__ import annotations

import unittest
from datetime import datetime

from medical_channel_pipeline.public_snapshot import build_public_snapshot
from medical_channel_pipeline.ccgp_detail import (
    CcgpDetailParseError,
    parse_ccgp_public_tender_html,
)

# OFFLINE_SYNTHETIC_HTML: Constructed using verified Chinese government
# procurement website's readable text, not a captured original HTML file.
# Source: https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27573388.htm
# Observed official body: 2026-10-30. Never use this fixture as evidence that
# the raw official markup or attachments were independently captured.
SOURCE_URL = "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202610/t20261027_27573388.htm"
OBSERVED = "2026-10-30T20:00:00+08:00"

HEADER = """
公开招标公告
公告信息：
采购项目名称 | 天津市第三中心医院（东丽院区）第五批检验科设备采购项目
采购单位 | 天津市第三中心医院
行政区域 | 市辖区 | 公告时间 | 2026年10月27日 23:50
发布日期：2026年10月27日
一、项目基本情况
项目编号：XCSD-2026-A-939
项目名称：天津市第三中心医院（东丽院区）第五批检验科设备采购项目
预算金额：509.19万元
最高限价：428.19万元
采购需求：
"""

TAIL = """
合同履行期限：自签订合同之日起15日内完成安装调试。
本项目不接受联合体参与，本项目不接受进口产品
二、申请人的资格要求：
1.满足《中华人民共和国政府采购法》第二十二条规定。
三、获取招标文件
时间：2026年10月27日到 2026年11月03日，每天上午09:00至11:30，下午13:30至16:00（北京时间，法定节假日除外）
地点：天津市华苑产业园区梓苑路6号C座2幢215室
四、提交投标文件截止时间、开标时间和地点
2026年11月17日 09点30分（北京时间）。
七、对本次招标提出询问，请按以下方式联系。
1.采购人信息 名称：天津市第三中心医院 地址：天津市河东区津塘路83号 联系方式：022-84112227
2.采购代理机构信息 名称：天津信诚盛德工程咨询有限公司 联系方式：022-23717450
3.项目联系方式 项目联系人：高俊 电 话：022-23717450-8011
"""

EXPECTED_ROWS = (
    ("第1包", "248", "227", "采购全自动生殖道分泌物分析仪、血气分析仪等，具体内容详见项目需求书。"),
    ("第2包", "104.99", "59.99", "采购全自动化学发光免疫分析仪、血液分析仪等，具体内容详见项目需求书。"),
    ("第3包", "95", "80", "采购全自动尿液分析流水线、微生物样本前处理系统等，具体内容详见项目需求书。"),
    ("第4包", "61.2", "61.2", "采购生化培养箱、二氧化碳温箱等，具体内容详见项目需求书。"),
)
EXPECTED_NAMES = (
    "全自动生殖道分泌物分析仪",
    "血气分析仪",
    "全自动化学发光免疫分析仪",
    "血液分析仪",
    "全自动尿液分析流水线",
    "微生物样本前处理系统",
    "生化培养箱",
    "二氧化碳温箱",
)


def synthetic_html(
    rows: tuple = EXPECTED_ROWS,
    *,
    nested: bool = False,
    category: str = "临床检验设备",
    header_override: str | None = None,
    footer: str = "",
) -> str:
    header = header_override or (
        "<tr><th>包号</th><th>是否设置最高限价</th>"
        "<th>预算（万元）</th><th>最高限价（万元）</th>"
        "<th>采购目录</th><th>采购需求</th></tr>"
    )
    row_html = "".join(
        f"<tr><td>{ident}</td><td>是</td><td>{budget}</td>"
        f"<td>{ceiling}</td><td>{category}</td><td>{demand}</td></tr>"
        for ident, budget, ceiling, demand in rows
    )
    procurement_table = f"<table>{header}{row_html}</table>"
    # The actual source has a separate surrounding content table. Test both
    # standalone and wrapper-nested table topologies without claiming either
    # topology is a verified copy of the remote DOM.
    if nested:
        procurement_table = f"<table><tr><td>{procurement_table}</td></tr></table>"
    return (
        f"<html><body><pre>{HEADER}</pre>{procurement_table}"
        f"<pre>{TAIL}</pre>{footer}</body></html>"
    )


def parse_fixture(html: str, source_url: str = SOURCE_URL) -> dict:
    return parse_ccgp_public_tender_html(
        html,
        source_url=source_url,
        observed_at=OBSERVED,
        opportunity_id="c02_offline_synthetic_xcsd_2026_a_939",
    )


class CcgpTianjinPackageTableRegressionTests(unittest.TestCase):
    def test_four_packages_eight_explicit_products_with_correct_package_ids(self) -> None:
        record = parse_fixture(synthetic_html())
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "XCSD-2026-A-939")
        self.assertEqual(facts["budget_cny"], 5091900)
        self.assertEqual([x["raw_name"] for x in facts["product_items"]], list(EXPECTED_NAMES))
        self.assertEqual(
            [x["package_id"] for x in facts["product_items"]],
            ["第1包"] * 2 + ["第2包"] * 2 + ["第3包"] * 2 + ["第4包"] * 2,
        )
        self.assertEqual(facts["product_categories"], ["临床检验设备"])

        packages = facts["procurement_packages"]
        self.assertEqual([x["package_id"] for x in packages], ["第1包", "第2包", "第3包", "第4包"])
        self.assertEqual([x["budget_cny"] for x in packages], [2480000, 1049900, 950000, 612000])
        self.assertEqual([x["ceiling_cny"] for x in packages], [2270000, 599900, 800000, 612000])
        self.assertEqual(sum(x["budget_cny"] for x in packages), 5091900)
        self.assertEqual(sum(x["ceiling_cny"] for x in packages), 4281900)

        fields = {row["field_path"] for row in record["evidence"]}
        self.assertTrue({"facts.product_items", "facts.product_categories", "facts.procurement_packages"} <= fields)

    def test_verified_package_ids_amounts_and_partial_state_reach_public_snapshot(self) -> None:
        record = parse_fixture(synthetic_html(nested=True))
        snapshot = build_public_snapshot([record], datetime.fromisoformat(OBSERVED))
        card = snapshot["opportunity_pool"][0]
        public = card["facts"]
        self.assertEqual(public["coverage_status"], "PARTIAL")
        self.assertEqual(len(public["product_items"]), 8)
        self.assertEqual(len(public["procurement_packages"]), 4)
        self.assertEqual(public["procurement_packages"][0]["budget_cny"], 2480000)
        self.assertEqual(public["procurement_packages"][0]["ceiling_cny"], 2270000)
        self.assertTrue(public["procurement_packages"][0]["non_exhaustive"])
        self.assertIn(SOURCE_URL, card["evidence_source_urls"])

    def test_nested_wrapper_table_and_unpublished_quantities(self) -> None:
        record = parse_fixture(synthetic_html(nested=True))
        self.assertEqual(len(record["facts"]["product_items"]), 8)
        self.assertTrue(all(x["quantity"] is None for x in record["facts"]["product_items"]))
        self.assertTrue(all(x["non_exhaustive"] for x in record["facts"]["procurement_packages"]))

    def test_wrong_table_header_fails_closed(self) -> None:
        wrong_header = (
            "<tr><th>序号</th><th>名称</th><th>预算</th>"
            "<th>金额</th><th>采购目录</th><th>采购需求</th></tr>"
        )
        record = parse_fixture(synthetic_html(header_override=wrong_header))
        self.assertEqual(record["facts"]["product_items"], [])
        self.assertFalse(record["facts"].get("procurement_packages"))

    def test_nonmedical_category_never_gets_clinical_lab_package_facts(self) -> None:
        record = parse_fixture(synthetic_html(category="安防设备"))
        self.assertEqual(record["facts"]["product_items"], [])
        self.assertFalse(record["facts"].get("procurement_packages"))

    def test_incomplete_package_budget_does_not_publish_partial_facts(self) -> None:
        rows = list(EXPECTED_ROWS)
        ident, _, ceiling, demand = rows[0]
        rows[0] = (ident, "249", ceiling, demand)
        record = parse_fixture(synthetic_html(tuple(rows)))
        self.assertEqual(record["facts"]["product_items"], [])
        self.assertFalse(record["facts"].get("procurement_packages"))

    def test_omitted_package_row_does_not_publish_partial_facts(self) -> None:
        record = parse_fixture(synthetic_html(EXPECTED_ROWS[:3]))
        self.assertEqual(record["facts"]["product_items"], [])
        self.assertFalse(record["facts"].get("procurement_packages"))

    def test_generic_attachment_only_demand_does_not_create_product(self) -> None:
        rows = (
            ("第1包", "248", "227", "具体内容详见项目需求书。"),
            *EXPECTED_ROWS[1:],
        )
        record = parse_fixture(synthetic_html(rows))
        self.assertEqual(record["facts"]["product_items"], [])
        self.assertFalse(record["facts"].get("procurement_packages"))

    def test_untrusted_other_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(CcgpDetailParseError, "CCGP_DETAIL_SOURCE_HOST_REJECTED"):
            parse_fixture(synthetic_html(), "https://example.com/notice.html")

    def test_secondary_footer_deadline_does_not_override_official_deadline(self) -> None:
        html = synthetic_html(
            footer="<footer>第三方信息提示：截止日期2026年11月11日。</footer>"
        )
        record = parse_fixture(html)
        self.assertEqual(record["facts"]["bid_deadline"], "2026-11-17T09:30:00+08:00")


if __name__ == "__main__":
    unittest.main()
