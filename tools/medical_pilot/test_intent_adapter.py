from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.collector_core import Snapshot
from tools.medical_pilot.intent_adapter import CcgpIntentAdapter, build_intent_event_and_facts
from tools.medical_pilot.registry import adapter_for_source, resolve_source


INTENT_HTML = """
<html><head><title>政府采购意向公开 - 中国政府采购网</title></head>
<body>
<h2>天津中医药大学第一附属医院政府采购意向公告-光电同步脑活动检测仪 详细情况</h2>
<div>2026年03月10日 23:51 来源：天津市政府采购网</div>
<table>
<tr><td>项目所在采购意向：</td><td>天津中医药大学第一附属医院政府采购意向公告</td></tr>
<tr><td>采购单位：</td><td>天津中医药大学第一附属医院</td></tr>
<tr><td>采购项目名称：</td><td>光电同步脑活动检测仪</td></tr>
<tr><td>预算金额：</td><td>390.000000万元(人民币)</td></tr>
<tr><td>采购品目：</td><td></td></tr>
<tr><td>采购需求概况 ：</td><td>为实现神经血管耦合中神经电活动与血液动力学响应的同步观测，拟采购光电同步脑活动成像仪。</td></tr>
<tr><td>预计采购时间：</td><td>2026-05</td></tr>
<tr><td>备注：</td><td></td></tr>
</table>
<p>本次公开的采购意向是本单位政府采购工作的初步安排，具体采购项目情况以相关采购公告和采购文件为准。</p>
</body></html>
"""


def snapshot(body: str) -> Snapshot:
    encoded = body.encode("utf-8")
    return Snapshot(
        source_url="https://cgyx.ccgp.gov.cn/cgyx/pub/proJ/details?projId=d9c9cde4-27c9-4d1f-a0f6-77994bf1ce25",
        fetched_at="2026-08-28T03:00:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=encoded,
        text=body,
        sha256=hashlib.sha256(encoded).hexdigest(),
    )


class CcgpIntentAdapterTests(unittest.TestCase):
    def test_preserves_month_precision_and_budget(self) -> None:
        parsed = CcgpIntentAdapter().parse_notice(snapshot(INTENT_HTML))
        self.assertEqual(parsed.notice_type, "PROCUREMENT_INTENT")
        self.assertEqual(parsed.buyer_name, "天津中医药大学第一附属医院")
        self.assertEqual(parsed.project_name, "光电同步脑活动检测仪")
        self.assertEqual(parsed.budget_cny, "3900000.00")
        self.assertEqual(parsed.expected_procurement_at, "2026-05")
        self.assertIsNone(parsed.bid_deadline)
        self.assertTrue(parsed.eligible_for_verified)
        self.assertIn("光电同步脑活动成像仪", parsed.procurement_need or "")

    def test_emits_expected_month_as_evidence_fact_without_fake_day(self) -> None:
        snap = snapshot(INTENT_HTML)
        parsed = CcgpIntentAdapter().parse_notice(snap)
        event, facts = build_intent_event_and_facts(parsed, snap)
        self.assertEqual(event["event_type"], "PROCUREMENT_INTENT")
        self.assertEqual(event["verification_status"], "VERIFIED")
        fact_by_name = {fact["field_name"]: fact for fact in facts}
        self.assertEqual(fact_by_name["expected_procurement_at"]["field_value"], "2026-05")
        self.assertNotEqual(fact_by_name["expected_procurement_at"]["field_value"], "2026-05-01")
        self.assertFalse(fact_by_name["expected_procurement_at"]["model_generated"])

    def test_registry_resolves_intent_source(self) -> None:
        url = "https://cgyx.ccgp.gov.cn/cgyx/pub/proJ/details?projId=d9c9cde4-27c9-4d1f-a0f6-77994bf1ce25"
        source = resolve_source(url)
        self.assertEqual(source.source_id, "ccgp_procurement_intent")
        self.assertEqual(adapter_for_source(source).source_id, "ccgp_procurement_intent")


if __name__ == "__main__":
    unittest.main()
