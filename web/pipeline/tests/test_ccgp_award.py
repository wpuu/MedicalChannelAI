from __future__ import annotations

import copy
import unittest
from pathlib import Path

from medical_channel_pipeline.ccgp_award import (
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

    def test_amount_parsing_never_guesses_a_scale(self) -> None:
        self.assertIsNone(_parse_amount_cny("237.5"))
        self.assertEqual(_parse_amount_cny("237.5", header_hint="中标金额(万元)"), 2_375_000)
        self.assertEqual(_parse_amount_cny("1,395", header_hint="中标金额(万元)"), 13_950_000)
        self.assertEqual(_parse_amount_cny("10,727,000.00元"), 10_727_000)
        self.assertEqual(_parse_amount_cny("￥932.000000 万元（人民币）"), 9_320_000)
        self.assertEqual(_parse_amount_cny("225,000.00元", header_hint="单价"), 225_000)
        self.assertIsNone(_parse_amount_cny("详见附件", header_hint="单价(万元)"))


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
