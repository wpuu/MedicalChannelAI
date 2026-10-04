from __future__ import annotations

import copy
import unittest
from pathlib import Path

from medical_channel_pipeline.ccgp_award import (
    normalize_project_number,
    reconcile_item_prices,
    CcgpAwardParseError,
    _parse_amount_cny,
    is_medical_channel_relevant_award,
    merge_award_records,
    parse_ccgp_award_html,
    validate_award_records,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OBSERVED_AT = "2026-09-29T01:00:00+00:00"

TJ_MULTI_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27412443.htm"
TJ_SINGLE_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27412423.htm"
TJ_WORKS_URL = "https://www.ccgp.gov.cn/cggg/dfgg/cjgg/202609/t20260928_27411167.htm"
NATIONAL_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202608/t20260804_27071574.htm"
TJ_MISDECLARED_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27411227.htm"
HE_GOODS_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27409767.htm"
HE_SERVICE_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27410652.htm"
BJ_TEXT_URL = "https://www.ccgp.gov.cn/cggg/zygg/zbgg/202609/t20260929_27412753.htm"
HL_CONTRACT_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260929_27414653.htm"
LN_FAILED_URL = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260929_27413417.htm"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _parse(name: str, url: str, **kwargs):
    return parse_ccgp_award_html(
        _fixture(name),
        source_url=url,
        observed_at=OBSERVED_AT,
        award_id=f"ccgpaward_{Path(name).stem}",
        **kwargs,
    )


class CcgpAwardParserTests(unittest.TestCase):
    def test_tianjin_multi_package_notice_yields_supplier_brand_model_and_prices(self) -> None:
        record = _parse("ccgp_award_tianjin_multi_package.html", TJ_MULTI_URL, market_code="TJ")
        facts = record["facts"]
        self.assertEqual(record["record_type"], "AWARD_RESULT")
        self.assertEqual(facts["project_number"], "XCSD-2026-A-535")
        self.assertEqual(facts["project_name"], "天津市第三中心医院彩色多普勒超声诊断仪采购项目")
        self.assertEqual(facts["buyer_name"], "天津市第三中心医院")
        self.assertEqual(facts["notice_type"], "中标公告")
        self.assertEqual(facts["result_kind"], "AWARD")
        self.assertEqual(facts["lifecycle_state"], "AWARDED")
        self.assertEqual(facts["published_at"], "2026-09-28")
        self.assertEqual(facts["market_code"], "TJ")
        self.assertEqual(facts["region"], "市辖区")
        # 公告概要 总中标金额 ￥932.000000 万元 -> whole CNY
        self.assertEqual(facts["total_amount_cny"], 9_320_000)
        self.assertEqual(facts["amount_basis"], "SUMMARY_TOTAL")
        self.assertEqual(facts["award_status"], "AWARDED")

        packages = facts["packages"]
        self.assertEqual([item["package_no"] for item in packages], ["1", "2", "3", "4"])
        self.assertEqual(packages[0]["supplier_name"], "华润天津医药有限公司")
        # 中标金额(万元) column: 237.5 -> 2,375,000
        self.assertEqual(packages[0]["amount_cny"], 2_375_000)
        self.assertEqual(packages[3]["supplier_name"], "北京合众汇美国际贸易有限公司")
        self.assertEqual(packages[3]["amount_cny"], 1_865_000)
        self.assertTrue(all(item["status"] == "AWARDED" for item in packages))

        items = facts["items"]
        self.assertEqual(
            [(item["package_no"], item["brand"], item["model"], item["unit_price_cny"]) for item in items],
            [
                ("1", "飞利浦", "EPIQ CVx", 2_375_000),
                ("2", "GE", "Voluson Expert 22 Premium", 2_570_000),
                ("3", "佳能", "Aplio i900 TUS-AI900", 2_510_000),
                ("4", "富士", "ARIETTA 650", 1_865_000),
            ],
        )
        self.assertEqual(items[0]["name"], "彩色多普勒超声诊断仪")
        self.assertEqual(items[0]["category"], "货物类")
        self.assertEqual(items[0]["quantity"], "1套")
        self.assertEqual(facts["public_contact"]["phone"], "022-23717450-8002")
        self.assertTrue(is_medical_channel_relevant_award(record))

        covered = {item["field_path"] for item in record["evidence"]}
        for path in ("facts.project_number", "facts.buyer_name", "facts.published_at", "facts.packages", "facts.items", "facts.total_amount_cny"):
            self.assertIn(path, covered)
        self.assertTrue(all(item["source_url"] == TJ_MULTI_URL for item in record["evidence"]))

    def test_tianjin_single_package_dsa_award(self) -> None:
        record = _parse("ccgp_award_tianjin_single_package.html", TJ_SINGLE_URL, market_code="TJ")
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "XCSD-2026-A-589")
        self.assertEqual(facts["total_amount_cny"], 13_950_000)
        self.assertEqual(facts["packages"][0]["supplier_name"], "天津市联大医用设备有限公司")
        # "1,395" under 中标金额(万元)
        self.assertEqual(facts["packages"][0]["amount_cny"], 13_950_000)
        self.assertEqual(facts["items"][0]["name"], "医用血管造影X射线机")
        self.assertEqual(facts["items"][0]["brand"], "联影")
        self.assertEqual(facts["items"][0]["model"], "uAngio960")
        self.assertEqual(facts["items"][0]["quantity"], "1台")
        self.assertTrue(is_medical_channel_relevant_award(record))

    def test_deal_notice_for_construction_works_is_parsed_but_out_of_channel_scope(self) -> None:
        record = _parse("ccgp_deal_tianjin_works_only.html", TJ_WORKS_URL, market_code="TJ")
        facts = record["facts"]
        self.assertEqual(facts["notice_type"], "成交公告")
        self.assertEqual(facts["result_kind"], "DEAL")
        self.assertEqual(facts["project_number"], "0615-2641031970921")
        self.assertEqual(facts["total_amount_cny"], 1_080_000)
        self.assertEqual(facts["packages"][0]["supplier_name"], "天津华惠安信建设工程有限公司")
        self.assertEqual(facts["items"][0]["category"], "工程类")
        self.assertIsNone(facts["items"][0]["brand"])
        # CT室/DR室 in the name would be a device acronym hit; works-only awards stay out.
        self.assertFalse(is_medical_channel_relevant_award(record))

    def test_national_template_text_packages_failed_packages_and_th_only_tables(self) -> None:
        record = _parse("ccgp_award_national_template_failed_packages.html", NATIONAL_URL)
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "CQS26A01493")
        self.assertEqual(facts["notice_type"], "中标（成交）结果公告")
        self.assertEqual(facts["result_kind"], "AWARD")
        self.assertEqual(facts["procurement_method"], "公开招标")
        self.assertEqual(facts["published_at"], "2026-08-04")
        self.assertEqual(facts["total_amount_cny"], 6_673_500)
        self.assertEqual(facts["award_status"], "PARTIALLY_FAILED")
        self.assertNotIn("market_code", facts)

        awarded = [item for item in facts["packages"] if item["status"] == "AWARDED"]
        failed = [item for item in facts["packages"] if item["status"] == "FAILED"]
        self.assertEqual(len(awarded), 5)
        self.assertEqual(awarded[0]["package_no"], "1")
        self.assertEqual(awarded[0]["supplier_name"], "广东汇康联医疗供应链管理有限公司")
        # "10,727,000.00元" keeps whole CNY
        self.assertEqual(awarded[0]["amount_cny"], 10_727_000)
        self.assertEqual([item["package_no"] for item in failed], ["6", "5", "3"])
        self.assertEqual(failed[0]["failure_reason"], "无投标人参与投标")

        items = facts["items"]
        self.assertEqual(len(items), 5)
        self.assertEqual((items[0]["name"], items[0]["brand"], items[0]["model"], items[0]["quantity"], items[0]["unit_price_cny"]), ("麻醉机1", "迈瑞", "A4C", "26套", 225_000))
        self.assertEqual(items[-1]["brand"], "凯迪泰")
        self.assertTrue(is_medical_channel_relevant_award(record))

    def test_non_result_notice_is_rejected(self) -> None:
        html = """
        <html><head><title>天津市胸科医院检验科设备采购项目公开招标公告</title></head><body>
        <div>一、项目基本情况 项目编号：TJ-2026-001 项目名称：检验科设备采购项目 预算金额：100万元</div>
        <div>发布日期：2026年09月20日</div></body></html>
        """
        with self.assertRaisesRegex(CcgpAwardParseError, "CCGP_AWARD_NOTICE_TYPE_NOT_RESULT"):
            parse_ccgp_award_html(html, source_url=TJ_MULTI_URL, observed_at=OBSERVED_AT, award_id="x")

    def test_result_notice_without_any_package_result_fails_closed(self) -> None:
        html = """
        <html><head><title>天津市某医院设备采购项目中标公告</title></head><body>
        <div>发布日期：2026年09月20日</div>
        <div>一、项目编号：TJ-2026-002</div><div>二、项目名称：设备采购项目</div>
        <div>三、中标信息</div><div>详见附件。</div>
        <div>1.采购人信息 名称：天津市某医院 地址：天津市</div></body></html>
        """
        with self.assertRaisesRegex(CcgpAwardParseError, "CCGP_AWARD_SUPPLIER_NOT_FOUND"):
            parse_ccgp_award_html(html, source_url=TJ_MULTI_URL, observed_at=OBSERVED_AT, award_id="x")

    def test_non_ccgp_or_plain_http_source_is_rejected(self) -> None:
        html = _fixture("ccgp_award_tianjin_single_package.html")
        for url in ("http://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t20260928_27412423.htm", "https://example.invalid/award.htm"):
            with self.assertRaisesRegex(CcgpAwardParseError, "CCGP_AWARD_SOURCE_HOST_REJECTED"):
                parse_ccgp_award_html(html, source_url=url, observed_at=OBSERVED_AT, award_id="x")

    def test_unit_price_under_misdeclared_wan_header_stays_unknown(self) -> None:
        # Real 2026-09-28 notice: column headed 单价(万元) but filled with 元
        # (312000 for a ¥312,000 package). Literal reading = ¥3.12 billion.
        record = _parse("ccgp_award_tianjin_unit_price_misdeclared.html", TJ_MISDECLARED_URL, market_code="TJ")
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "BJFHGJ-2026-038")
        self.assertEqual(facts["total_amount_cny"], 312_000)
        self.assertEqual(facts["packages"][0]["amount_cny"], 312_000)
        self.assertEqual(facts["items"][0]["brand"], "辉锦创兴")
        self.assertEqual(facts["items"][0]["model"], "AutoPlex-12")
        self.assertIsNone(facts["items"][0]["unit_price_cny"])
        validate_award_records([record])

    def test_reconcile_item_prices_drops_prices_that_cannot_fit_the_award(self) -> None:
        packages = [{"package_no": "1", "status": "AWARDED", "supplier_name": "甲", "amount_cny": 312_000}]
        items = [
            {"package_no": "1", "name": "a", "quantity": "1", "unit_price_cny": 3_120_000_000},
            {"package_no": "1", "name": "b", "quantity": "2", "unit_price_cny": 150_000},
            {"package_no": "1", "name": "c", "quantity": "1台", "unit_price_cny": 5_000_000_000},
            {"package_no": "9", "name": "d", "quantity": None, "unit_price_cny": 99_999_999_999},
            {"package_no": None, "name": "e", "quantity": None, "unit_price_cny": None},
        ]
        result = reconcile_item_prices(items, packages, 312_000)
        self.assertEqual([item["unit_price_cny"] for item in result], [None, 150_000, None, None, None])
        # Plausible prices are never touched, and unknown ceilings never drop data.
        self.assertEqual(reconcile_item_prices(items[1:2], packages, None)[0]["unit_price_cny"], 150_000)
        self.assertEqual(reconcile_item_prices(items[:1], [], None)[0]["unit_price_cny"], 3_120_000_000)

    def test_project_number_normalisation_bridges_clerical_variants(self) -> None:
        self.assertEqual(normalize_project_number("HBHX（Z）-2026-019"), "hbhx(z)-2026-019")
        self.assertEqual(normalize_project_number(" hbhx(z)-2026-019 "), "hbhx(z)-2026-019")
        self.assertEqual(normalize_project_number("ＸＣＳＤ－2026－A－589"), "xcsd-2026-a-589")
        self.assertEqual(normalize_project_number("XCSD-2026 -A-589"), "xcsd-2026-a-589")
        self.assertEqual(normalize_project_number(None), "")

    def test_hebei_goods_table_supplier_without_amount_column_is_backfilled_from_item_table(self) -> None:
        # 河北 template (observed 2026-09-28): 中标（成交）信息 is ``供应商名称 | 供应商地址 |
        # 供应商编码`` with no amount; a spanning ``货物类`` row precedes the 主要标的信息
        # header, whose unit-less ``中标金额`` column carries the money.
        record = _parse("ccgp_award_hebei_goods_table.html", HE_GOODS_URL, market_code="HE")
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "ZHZB2026404")
        self.assertEqual(facts["buyer_name"], "沧州市中心医院")
        self.assertEqual(facts["market_code"], "HE")
        self.assertEqual(facts["total_amount_cny"], 2_569_303)
        self.assertEqual(len(facts["packages"]), 1)
        package = facts["packages"][0]
        self.assertEqual(package["supplier_name"], "吉荣家具有限公司")
        self.assertIsNone(package["amount_cny"])
        self.assertNotIn("amount_source", package)
        self.assertEqual(
            [(item["category"], item["name"], item["brand"], item["quantity"]) for item in facts["items"]],
            [("货物类", "病房护理设备设施", "吉荣", "一批")],
        )
        validate_award_records([record])
        # Furniture-only award: parsed, stored, but not a medical-channel award.
        self.assertFalse(is_medical_channel_relevant_award(record))

    def test_hebei_service_table_is_captured_as_service_item(self) -> None:
        record = _parse("ccgp_award_hebei_service_table.html", HE_SERVICE_URL, market_code="HE")
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "RHP-C192668292816-1")
        self.assertEqual(facts["buyer_name"], "河北医科大学第三医院")
        self.assertEqual(facts["total_amount_cny"], 5_733_000)
        self.assertEqual(facts["packages"][0]["supplier_name"], "河北瑞鹤医疗器械有限公司")
        self.assertIsNone(facts["packages"][0]["amount_cny"])
        self.assertEqual(
            [(item["category"], item["name"], item["model"], item["unit_price_cny"]) for item in facts["items"]],
            [("服务类", "河北医科大学第三医院CT、MRI维保项目（三年）（二次）", None, None)],
        )
        self.assertTrue(is_medical_channel_relevant_award(record))

    def test_national_text_template_reads_parenthesised_unit_and_item_name_column(self) -> None:
        # 北京 (central) template: ``中标（成交）金额：182.0000000（万元）`` in text and an
        # item table whose first 名称 column is the supplier, not the 标的.
        record = _parse("ccgp_award_beijing_text_template.html", BJ_TEXT_URL, market_code="BJ")
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "0701-264106070107")
        self.assertEqual(facts["buyer_name"], "中国医学科学院北京协和医院")
        self.assertEqual(facts["total_amount_cny"], 1_820_000)
        self.assertEqual(facts["packages"][0]["supplier_name"], "北京若华医疗器械有限公司")
        self.assertEqual(facts["packages"][0]["amount_cny"], 1_820_000)
        item = facts["items"][0]
        self.assertEqual(item["name"], "自动血液微生物培养系统; 全自动蛋白分析仪")
        self.assertEqual(item["brand"], "美国BD; 西门子")
        self.assertEqual(item["model"], "BD BACTEC FX; BN Ⅱ System")
        self.assertIsNone(item["unit_price_cny"])  # multi-valued cell, not attributable
        self.assertTrue(is_medical_channel_relevant_award(record))

    def test_heilongjiang_contract_package_template_yields_catalogue_category_and_unit_prices(self) -> None:
        # 黑龙江 template: ``三、采购结果`` + ``合同包1(…)：`` + item table
        # ``品目号 | 品目名称 | 采购标的 | 品牌 | 规格型号 | 数量（单位） | 单价(元) | 总价(元)``.
        record = _parse("ccgp_award_heilongjiang_contract_package.html", HL_CONTRACT_URL, market_code="HL")
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "[231025]FAGC[GK]20260002")
        self.assertEqual(facts["buyer_name"], "林口县中医院")
        self.assertEqual(facts["total_amount_cny"], 1_430_000)
        self.assertEqual(facts["award_status"], "AWARDED")
        self.assertEqual(
            [(p["package_no"], p["supplier_name"], p["amount_cny"]) for p in facts["packages"]],
            [("1", "国药集团黑龙江医疗器械有限公司", 1_430_000)],
        )
        first = facts["items"][0]
        self.assertEqual(first["package_no"], "1")
        self.assertEqual(first["category"], "物理治疗、康复及体育治疗仪器设备")
        self.assertEqual(first["name"], "智能言语训练机")
        self.assertEqual(first["brand"], "好博医疗")
        self.assertEqual(first["unit_price_cny"], 410_000)
        self.assertIn(("多参数监护仪", "理邦仪器", "iX15", 39_000), [(i["name"], i["brand"], i["model"], i["unit_price_cny"]) for i in facts["items"]])
        validate_award_records([record])
        self.assertTrue(is_medical_channel_relevant_award(record))

    def test_liaoning_all_packages_failed_notice_has_no_amount(self) -> None:
        # 辽宁 template: ``包组编号：002 … 结果类型：废标 … 废标情形：…`` and no 标的 table.
        record = _parse("ccgp_award_liaoning_all_packages_failed.html", LN_FAILED_URL, market_code="LN")
        facts = record["facts"]
        self.assertEqual(facts["project_number"], "JH26-210323-00239")
        self.assertEqual(facts["award_status"], "ALL_PACKAGES_FAILED")
        self.assertIsNone(facts["total_amount_cny"])
        self.assertIsNone(facts["amount_basis"])
        self.assertEqual(facts["packages"][0]["package_no"], "002")
        self.assertEqual(facts["packages"][0]["status"], "FAILED")
        self.assertIn("通过符合性检查的供应商不足3家", facts["packages"][0]["failure_reason"])
        self.assertEqual(facts["items"], [])
        validate_award_records([record])

    def test_amount_parsing_never_guesses_a_scale(self) -> None:
        self.assertIsNone(_parse_amount_cny("237.5"))
        # Unit-less cells remain unknown regardless of magnitude.
        self.assertIsNone(_parse_amount_cny("12000"))
        self.assertIsNone(_parse_amount_cny("99999.99"))
        self.assertIsNone(_parse_amount_cny("5733000"))
        self.assertIsNone(_parse_amount_cny("2569303.17"))
        self.assertEqual(_parse_amount_cny("182.0000000（万元）"), 1_820_000)
        self.assertEqual(_parse_amount_cny("1820000(元)"), 1_820_000)

    def test_zero_summary_total_is_treated_as_unpublished(self) -> None:
        from medical_channel_pipeline.ccgp_award import _extract_summary_total

        self.assertIsNone(_extract_summary_total({"中标金额": "0元"}))
        self.assertIsNone(_extract_summary_total({"成交金额": "0.00 万元"}))
        self.assertEqual(_extract_summary_total({"中标金额": "52.39万元"}), 523_900)
        self.assertEqual(_parse_amount_cny("237.5", header_hint="中标金额(万元)"), 2_375_000)
        self.assertEqual(_parse_amount_cny("1,395", header_hint="中标金额(万元)"), 13_950_000)
        self.assertEqual(_parse_amount_cny("10,727,000.00元"), 10_727_000)
        self.assertEqual(_parse_amount_cny("￥932.000000 万元（人民币）"), 9_320_000)
        self.assertEqual(_parse_amount_cny("225,000.00元", header_hint="单价"), 225_000)
        self.assertIsNone(_parse_amount_cny("详见附件", header_hint="单价(万元)"))
        # Multi-item cells (泰达 腔镜 template) cannot be attributed to one 标的.
        self.assertIsNone(_parse_amount_cny("46.8万元； 14.8万元； 10.8万元； 其他详见附件。", header_hint="单价(万元)"))
        self.assertIsNone(_parse_amount_cny("141万元； 其他详见附件。", header_hint="单价(万元)"))


class AwardRecordValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = _parse("ccgp_award_tianjin_single_package.html", TJ_SINGLE_URL, market_code="TJ")

    def test_validate_rejects_negative_amounts_and_missing_supplier(self) -> None:
        broken = copy.deepcopy(self.record)
        broken["facts"]["packages"][0]["amount_cny"] = -1
        with self.assertRaisesRegex(CcgpAwardParseError, "AWARD_PACKAGE_AMOUNT_INVALID"):
            validate_award_records([broken])
        broken = copy.deepcopy(self.record)
        broken["facts"]["packages"][0]["supplier_name"] = ""
        with self.assertRaisesRegex(CcgpAwardParseError, "AWARD_PACKAGE_SUPPLIER_REQUIRED"):
            validate_award_records([broken])
        broken = copy.deepcopy(self.record)
        broken["facts"]["lifecycle_state"] = "BIDDING"
        with self.assertRaisesRegex(CcgpAwardParseError, "AWARD_LIFECYCLE_INVALID"):
            validate_award_records([broken])

    def test_validate_rejects_duplicate_award_ids(self) -> None:
        with self.assertRaisesRegex(CcgpAwardParseError, "DUPLICATE_AWARD_ID"):
            validate_award_records([self.record, copy.deepcopy(self.record)])

    def test_merge_keeps_newest_observation_per_award_id(self) -> None:
        older = copy.deepcopy(self.record)
        older["source"]["observed_at"] = "2026-09-28T01:00:00+00:00"
        other = _parse("ccgp_award_tianjin_multi_package.html", TJ_MULTI_URL, market_code="TJ")
        merged = merge_award_records([older, other], [self.record])
        self.assertEqual([item["award_id"] for item in merged], [self.record["award_id"], other["award_id"]])
        self.assertEqual(merged[0]["source"]["observed_at"], OBSERVED_AT)
        # A stale re-observation never regresses the store.
        stale = merge_award_records(merged, [older])
        self.assertEqual(stale[0]["source"]["observed_at"], OBSERVED_AT)


if __name__ == "__main__":
    unittest.main()
