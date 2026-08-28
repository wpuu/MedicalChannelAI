from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.ccgp_lifecycle_adapter import (
    CcgpLifecycleAdapter,
    build_ccgp_lifecycle_event_and_facts,
)
from tools.medical_pilot.collector_core import Snapshot
from tools.medical_pilot.lifecycle import resolve_project_lifecycle


TENDER_HTML = """
<html><head><title>天津市天津医院 天津医院单光子发射及X射线计算机断层成像系统（SPECT/CT）采购项目 (项目编号:PYGP-2026-A-0157)公开招标公告</title></head>
<body>
<table>
<tr><td>采购项目名称</td><td>天津医院单光子发射及X射线计算机断层成像系统（SPECT/CT）采购项目</td></tr>
<tr><td>采购单位</td><td>天津市天津医院</td></tr>
<tr><td>公告时间</td><td>2026年07月20日 18:50</td></tr>
<tr><td>开标时间</td><td>2026年08月10日 09:30</td></tr>
<tr><td>预算金额</td><td>￥1200.000000万元（人民币）</td></tr>
</table>
<p>项目编号：PYGP-2026-A-0157</p>
<p>公开招标</p>
</body></html>
"""

TERMINATION_HTML = """
<html><head><title>天津市天津医院 天津医院单光子发射及X射线计算机断层成像系统（SPECT/CT）采购项目 (项目编号:PYGP-2026-A-0157 )终止公告</title></head>
<body>
<table>
<tr><td>采购项目名称</td><td>天津医院单光子发射及X射线计算机断层成像系统（SPECT/CT）采购项目</td></tr>
<tr><td>采购单位</td><td>天津市天津医院</td></tr>
<tr><td>公告时间</td><td>2026年08月24日 18:50</td></tr>
</table>
<p>一、项目基本情况：</p>
<p>采购项目编号： PYGP-2026-A-0157</p>
<p>采购项目名称：天津医院单光子发射及X射线计算机断层成像系统（SPECT/CT）采购项目</p>
<p>二、项目终止的原因：</p>
<p>本项目项目需求发生重大变更</p>
<p>三、其他补充事宜：</p>
</body></html>
"""

AWARD_HTML = """
<html><head><title>天津医科大学 天津医科大学细胞药物GMP实验室生产核心系统设备采购项目 (项目编号:TJBD-2026-A-123)中标公告</title></head>
<body>
<table>
<tr><td>采购项目名称</td><td>天津医科大学细胞药物GMP实验室生产核心系统设备采购项目</td></tr>
<tr><td>采购单位</td><td>天津医科大学</td></tr>
<tr><td>公告时间</td><td>2026年08月03日 18:50</td></tr>
<tr><td>总中标金额</td><td>￥873.270000 万元（人民币）</td></tr>
</table>
<p>一、项目编号：TJBD-2026-A-123</p>
<p>二、项目名称：天津医科大学细胞药物GMP实验室生产核心系统设备采购项目</p>
<p>三、中标信息</p>
<table>
<tr><td>第1包</td></tr>
<tr><td>供应商名称</td><td>供应商地址</td><td>统一社会信用代码</td><td>企业办公电话</td><td>中标金额(万元)</td><td>评审得分</td></tr>
<tr><td>天津启物科技有限责任公司</td><td>天津市南开区科研西路天津科技广场6-1-1004</td><td>91120104MACXFAQR4L</td><td>15822130304</td><td>873.27</td><td>98.80</td></tr>
</table>
</body></html>
"""

AMENDMENT_HTML = """
<html><head><title>天津市消防救援总队第二批灭火救援装备采购项目（项目编号：TGPC-2026-A-0161）更正公告</title></head>
<body>
<table>
<tr><td>采购项目名称</td><td>天津市消防救援总队第二批灭火救援装备采购项目（项目编号：TGPC-2026-A-0161）</td></tr>
<tr><td>采购单位</td><td>天津市消防救援总队</td></tr>
<tr><td>公告时间</td><td>2026年07月10日 15:23</td></tr>
<tr><td>更正事项</td><td>采购文件</td></tr>
</table>
<p>一、项目基本情况</p>
<p>原公告的采购项目编号：TGPC-2026-A-0161</p>
<p>二、更正信息</p>
<p>更正事项：采购文件</p>
<p>更正内容：</p>
<p>招标文件部分评分因素变更，本项目其它内容不变。</p>
<p>更正日期：2026年07月10日</p>
<p>三、其他补充事宜</p>
</body></html>
"""


def snapshot(url: str, html: str) -> Snapshot:
    body = html.encode("utf-8")
    return Snapshot(
        source_url=url,
        fetched_at="2026-08-28T03:20:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        text=html,
        sha256=hashlib.sha256(body).hexdigest(),
    )


class CcgpLifecycleAdapterTests(unittest.TestCase):
    def test_termination_type_comes_from_notice_title_not_project_name(self) -> None:
        snap = snapshot(
            "https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202608/t20260824_27194479.htm",
            TERMINATION_HTML,
        )
        parsed = CcgpLifecycleAdapter().parse_notice(snap)
        self.assertEqual(parsed.notice_type, "TERMINATION")
        self.assertEqual(parsed.project_number, "PYGP-2026-A-0157")
        self.assertEqual(parsed.termination_reason, "本项目项目需求发生重大变更")
        self.assertTrue(parsed.eligible_for_verified)
        _, facts = build_ccgp_lifecycle_event_and_facts(parsed, snap)
        facts_by_name = {fact["field_name"]: fact for fact in facts}
        self.assertEqual(facts_by_name["termination_reason"]["field_value"], "本项目项目需求发生重大变更")
        self.assertFalse(facts_by_name["termination_reason"]["model_generated"])

    def test_award_total_and_winner_are_evidence_backed(self) -> None:
        snap = snapshot(
            "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202608/t20260803_27061943.htm",
            AWARD_HTML,
        )
        parsed = CcgpLifecycleAdapter().parse_notice(snap)
        self.assertEqual(parsed.notice_type, "AWARD")
        self.assertEqual(parsed.award_total_cny, "8732700.00")
        self.assertEqual(len(parsed.award_packages), 1)
        self.assertEqual(parsed.award_packages[0].supplier_name, "天津启物科技有限责任公司")
        self.assertEqual(parsed.award_packages[0].award_amount_cny, "8732700.00")
        _, facts = build_ccgp_lifecycle_event_and_facts(parsed, snap)
        fact_names = {fact["field_name"] for fact in facts}
        self.assertIn("award_total_cny", fact_names)
        self.assertIn("award_packages", fact_names)

    def test_amendment_is_not_treated_as_new_tender(self) -> None:
        snap = snapshot(
            "https://www.ccgp.gov.cn/cggg/zygg/gzgg/202607/t20260710_26910747.htm",
            AMENDMENT_HTML,
        )
        parsed = CcgpLifecycleAdapter().parse_notice(snap)
        self.assertEqual(parsed.notice_type, "AMENDMENT")
        self.assertEqual(parsed.project_number, "TGPC-2026-A-0161")
        self.assertEqual(parsed.amendment_subject, "采购文件")
        self.assertIn("评分因素变更", parsed.amendment_summary or "")


class LifecycleLinkerTests(unittest.TestCase):
    def test_verified_termination_overrides_older_tender_for_same_project_number(self) -> None:
        adapter = CcgpLifecycleAdapter()
        tender_snap = snapshot(
            "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202607/tender.htm",
            TENDER_HTML,
        )
        termination_snap = snapshot(
            "https://www.ccgp.gov.cn/cggg/dfgg/fblbgg/202608/t20260824_27194479.htm",
            TERMINATION_HTML,
        )
        tender_event, _ = build_ccgp_lifecycle_event_and_facts(adapter.parse_notice(tender_snap), tender_snap)
        termination_event, _ = build_ccgp_lifecycle_event_and_facts(adapter.parse_notice(termination_snap), termination_snap)
        self.assertEqual(tender_event["canonical_project_id"], termination_event["canonical_project_id"])
        aggregate = resolve_project_lifecycle([tender_event, termination_event])
        self.assertEqual(aggregate.lifecycle_state, "TERMINATED")
        self.assertEqual(aggregate.current_event_id, termination_event["event_id"])
        self.assertEqual(aggregate.verification_status, "VERIFIED")

    def test_unverified_newer_event_does_not_override_verified_state(self) -> None:
        adapter = CcgpLifecycleAdapter()
        tender_snap = snapshot(
            "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202607/tender.htm",
            TENDER_HTML,
        )
        event, _ = build_ccgp_lifecycle_event_and_facts(adapter.parse_notice(tender_snap), tender_snap)
        unverified = dict(event)
        unverified["event_id"] = "evt_00000000-0000-0000-0000-000000000999"
        unverified["event_type"] = "TERMINATION"
        unverified["effective_at"] = "2026-09-01T00:00:00+08:00"
        unverified["published_at"] = "2026-09-01T00:00:00+08:00"
        unverified["verification_status"] = "UNVERIFIED"
        aggregate = resolve_project_lifecycle([event, unverified])
        self.assertEqual(aggregate.lifecycle_state, "TENDERING")
        self.assertIn(unverified["event_id"], aggregate.ignored_unverified_event_ids)

    def test_different_projects_cannot_be_force_linked(self) -> None:
        event_a = {
            "event_id": "evt_00000000-0000-0000-0000-000000000001",
            "canonical_project_id": "mprj_00000000-0000-0000-0000-000000000001",
            "event_type": "TENDER",
            "verification_status": "VERIFIED",
            "published_at": "2026-08-01T00:00:00+08:00",
        }
        event_b = {
            "event_id": "evt_00000000-0000-0000-0000-000000000002",
            "canonical_project_id": "mprj_00000000-0000-0000-0000-000000000002",
            "event_type": "TERMINATION",
            "verification_status": "VERIFIED",
            "published_at": "2026-08-02T00:00:00+08:00",
        }
        with self.assertRaises(ValueError):
            resolve_project_lifecycle([event_a, event_b])


if __name__ == "__main__":
    unittest.main()
