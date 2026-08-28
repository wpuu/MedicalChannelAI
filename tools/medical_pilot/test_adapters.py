from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.adapters import CcgpAdapter, TjmughAdapter
from tools.medical_pilot.collector_core import FetchError, HostBoundFetcher, Snapshot, build_event_and_facts


CCGP_CHEST_HOSPITAL_HTML = """
<html><head><title>天津市胸科医院检验科设备租赁服务项目公开招标公告</title></head>
<body>
<div>2026年08月27日 18:50 来源：</div>
<table>
<tr><td>采购项目名称</td><td>天津市胸科医院检验科设备租赁服务项目</td></tr>
<tr><td>采购单位</td><td>天津市胸科医院</td></tr>
<tr><td>公告时间</td><td>2026年08月27日 18:50</td></tr>
<tr><td>开标时间</td><td>2026年09月17日 09:30</td></tr>
<tr><td>预算金额</td><td>￥573.000000万元（人民币）</td></tr>
</table>
<p>项目编号：XCSD-2026-A-641</p>
<p>项目名称：天津市胸科医院检验科设备租赁服务项目</p>
<p>预算金额：573.0万元</p>
<p>提交投标文件截止时间、开标时间和地点 2026年09月17日 09点30分（北京时间）。</p>
<p>公开招标</p>
</body></html>
"""


TJMUGH_RESEARCH_HTML = """
<html><head><title>天津医科大学总医院天津医科大学总医院医疗设备项目市场调研论证邀请函-天津医科大学总医院-北方网企业建站</title></head>
<body>
<h3>天津医科大学总医院天津医科大学总医院医疗设备项目市场调研论证邀请函</h3>
<div>2026-05-29 05:10</div>
<p>天津医科大学总医院设备采购科根据本年度采购计划安排，拟开展院内项目市场调研论证。</p>
<p>一、论证项目名称：</p>
<p>（1）精密空调（2）泌尿科探针（3）经颅聚焦超声刺激仪（4）脑电图</p>
<p>二、供应商参加本次论证活动必须提供下列相关材料：</p>
<p>本次报名截止时间为：2026年6月2日下午17:00点前。</p>
</body></html>
"""


def snapshot(url: str, body: str) -> Snapshot:
    encoded = body.encode("utf-8")
    return Snapshot(
        source_url=url,
        fetched_at="2026-08-28T02:30:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=encoded,
        text=body,
        sha256=hashlib.sha256(encoded).hexdigest(),
    )


class CcgpAdapterTests(unittest.TestCase):
    def test_parses_chest_hospital_notice_without_model(self) -> None:
        adapter = CcgpAdapter()
        parsed = adapter.parse_notice(
            snapshot(
                "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260827_27219613.htm",
                CCGP_CHEST_HOSPITAL_HTML,
            )
        )
        self.assertEqual(parsed.project_number, "XCSD-2026-A-641")
        self.assertEqual(parsed.project_name, "天津市胸科医院检验科设备租赁服务项目")
        self.assertEqual(parsed.buyer_name, "天津市胸科医院")
        self.assertEqual(parsed.budget_cny, "5730000.00")
        self.assertEqual(parsed.bid_deadline, "2026-09-17T09:30:00+08:00")
        self.assertEqual(parsed.notice_type, "TENDER")
        self.assertEqual(parsed.procurement_method, "PUBLIC_TENDER")
        self.assertTrue(parsed.eligible_for_verified)

    def test_builds_only_evidence_backed_official_facts(self) -> None:
        snap = snapshot(
            "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260827_27219613.htm",
            CCGP_CHEST_HOSPITAL_HTML,
        )
        parsed = CcgpAdapter().parse_notice(snap)
        event, facts = build_event_and_facts(parsed, snap)
        self.assertEqual(event["verification_status"], "VERIFIED")
        fields = {fact["field_name"] for fact in facts}
        self.assertIn("budget_cny", fields)
        self.assertIn("project_number", fields)
        self.assertIn("bid_deadline", fields)
        for fact in facts:
            self.assertEqual(fact["fact_type"], "OFFICIAL_PUBLIC_FACT")
            self.assertFalse(fact["model_generated"])
            self.assertEqual(fact["verification_status"], "VERIFIED")

    def test_discovers_only_medical_ccgp_detail_links(self) -> None:
        listing = """
        <a href='/cggg/dfgg/gkzb/202608/t1.htm'>天津市胸科医院检验科设备租赁服务项目</a>
        <a href='/cggg/dfgg/gkzb/202608/t2.htm'>某学校食堂服务项目</a>
        <a href='https://example.com/cggg/dfgg/gkzb/x.htm'>某医院项目</a>
        """
        links = CcgpAdapter().discover(listing, "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/index.htm")
        self.assertEqual(len(links), 1)
        self.assertIn("胸科医院", links[0].title)


class TjmughAdapterTests(unittest.TestCase):
    def test_parses_market_research_and_product_list(self) -> None:
        parsed = TjmughAdapter().parse_notice(
            snapshot(
                "https://www.tjmugh.com.cn/system/2026/05/29/030295720.shtml",
                TJMUGH_RESEARCH_HTML,
            )
        )
        self.assertEqual(parsed.notice_type, "MARKET_RESEARCH")
        self.assertEqual(parsed.buyer_name, "天津医科大学总医院")
        self.assertEqual(parsed.published_at, "2026-05-29T05:10:00+08:00")
        self.assertEqual(parsed.registration_deadline, "2026-06-02T17:00:00+08:00")
        self.assertIn("泌尿科探针", parsed.product_items)
        self.assertIn("经颅聚焦超声刺激仪", parsed.product_items)
        self.assertTrue(parsed.eligible_for_verified)

    def test_discovers_only_registered_hospital_notice_paths(self) -> None:
        listing = """
        <a href='/system/2026/08/20/030330000.shtml'>天津医科大学总医院医疗设备项目市场调研论证邀请函</a>
        <a href='/news/other.shtml'>医院新闻</a>
        <a href='https://example.com/system/2026/08/20/1.shtml'>医疗设备项目市场调研</a>
        """
        links = TjmughAdapter().discover(listing, "https://www.tjmugh.com.cn/cgxxtzgg/index.shtml")
        self.assertEqual(len(links), 1)
        self.assertIn("医疗设备", links[0].title)


class FetchBoundaryTests(unittest.TestCase):
    def test_unregistered_host_is_rejected_before_network(self) -> None:
        fetcher = HostBoundFetcher({"www.ccgp.gov.cn"})
        with self.assertRaises(FetchError) as context:
            fetcher.fetch("https://example.com/not-allowed")
        self.assertEqual(context.exception.code, "HOST_NOT_ALLOWED")


if __name__ == "__main__":
    unittest.main()
