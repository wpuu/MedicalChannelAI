from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.collector_core import Snapshot, build_event_and_facts
from tools.medical_pilot.first_central_adapter import FirstCentralHospitalAdapter


INTERNAL_SELECTION_HTML = """
<html><head><title>天津市第一中心医院手术无影灯采购项目院内比选公告</title></head>
<body>
<h1>天津市第一中心医院手术无影灯采购项目院内比选公告</h1>
<p>2026-05-06 15:43</p>
<p>天津市第一中心医院将以院内比选方式，对手术无影灯采购项目实施采购。</p>
<p>一、项目基本信息</p>
<p>1. 项目名称：天津市第一中心医院手术无影灯采购项目。</p>
<p>2. 项目编号：YNBX-2026-G-6003。</p>
<p>3. 项目预算：19800元。</p>
<p>二、项目内容、数量及预算</p>
<table><tr><td>序号</td><td>项目内容</td><td>数量</td><td>单位</td><td>预算金额（万元）</td></tr>
<tr><td>1</td><td>手术无影灯</td><td>2</td><td>台</td><td>1.98</td></tr></table>
<p>院内比选响应文件递交截止时间：2026年5月13日14:00。</p>
<p>启封比选响应文件现场比选时间：2026年5月14日9:00。</p>
<p>天津市第一中心医院 2026年5月6日</p>
</body></html>
"""

MARKET_RESEARCH_HTML = """
<html><head><title>天津市第一中心医院医疗器械精细化管理系统项目测试企业征集公告</title></head>
<body>
<h1>天津市第一中心医院医疗器械精细化管理系统项目测试企业征集公告</h1>
<p>2026-05-18 14:33</p>
<p>为保障天津市第一中心医院医疗器械精细化管理项目建设进程，面向社会公开征集符合条件的企业参与项目测试。</p>
<p>一、项目基本信息</p>
<p>1.项目名称：天津市第一中心医院医疗器械精细化管理项目</p>
<p>三、测试内容</p>
<p>1.对接国家药监、医保的医疗耗材数据库。</p>
<p>2.对检验试剂的使用进行效益分析。</p>
<p>四、测试安排</p>
<p>测试报名阶段 自公告发布之日起7天。</p>
<p>本次测试调研仅为采购前期需求核实使用，不构成任何采购要约。</p>
</body></html>
"""


def snapshot(url: str, html: str) -> Snapshot:
    body = html.encode("utf-8")
    return Snapshot(
        source_url=url,
        fetched_at="2026-08-28T03:55:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        text=html,
        sha256=hashlib.sha256(body).hexdigest(),
    )


class FirstCentralHospitalAdapterTests(unittest.TestCase):
    def test_internal_selection_extracts_only_explicit_budget_and_deadline(self) -> None:
        snap = snapshot(
            "https://www.tj-fch.com/system/2026/05/06/030189759.shtml",
            INTERNAL_SELECTION_HTML,
        )
        parsed = FirstCentralHospitalAdapter().parse_notice(snap)
        self.assertEqual(parsed.notice_type, "INTERNAL_SELECTION")
        self.assertEqual(parsed.project_name, "天津市第一中心医院手术无影灯采购项目")
        self.assertEqual(parsed.project_number, "YNBX-2026-G-6003")
        self.assertEqual(parsed.budget_cny, "19800.00")
        self.assertEqual(parsed.bid_deadline, "2026-05-13T14:00:00+08:00")
        self.assertEqual(parsed.procurement_method, "HOSPITAL_INTERNAL_SELECTION")
        self.assertTrue(parsed.eligible_for_verified)
        _, facts = build_event_and_facts(parsed, snap)
        facts_by_name = {fact["field_name"]: fact for fact in facts}
        self.assertEqual(facts_by_name["budget_cny"]["field_value"], "19800.00")
        self.assertFalse(facts_by_name["budget_cny"]["model_generated"])

    def test_enterprise_recruitment_is_early_market_research_not_tender(self) -> None:
        snap = snapshot(
            "https://www.tj-fch.com/system/2026/05/18/030190755.shtml",
            MARKET_RESEARCH_HTML,
        )
        parsed = FirstCentralHospitalAdapter().parse_notice(snap)
        self.assertEqual(parsed.notice_type, "MARKET_RESEARCH")
        self.assertEqual(parsed.project_name, "天津市第一中心医院医疗器械精细化管理项目")
        self.assertEqual(parsed.procurement_method, "HOSPITAL_ENTERPRISE_RECRUITMENT")
        self.assertIsNone(parsed.budget_cny)
        self.assertIsNone(parsed.bid_deadline)
        self.assertTrue(parsed.eligible_for_verified)

    def test_hospital_name_must_exist_in_page_before_buyer_fact_is_verified(self) -> None:
        html = INTERNAL_SELECTION_HTML.replace("天津市第一中心医院", "某医院")
        snap = snapshot(
            "https://www.tj-fch.com/system/2026/05/06/030189759.shtml",
            html,
        )
        parsed = FirstCentralHospitalAdapter().parse_notice(snap)
        self.assertFalse(parsed.eligible_for_verified)
        self.assertNotIn("buyer_name", parsed.evidence_fragments)


if __name__ == "__main__":
    unittest.main()
