from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.attachments import BoundedAttachmentFetcher
from tools.medical_pilot.ccgp_lifecycle_adapter import CcgpLifecycleAdapter, build_ccgp_lifecycle_event_and_facts
from tools.medical_pilot.collector_core import FetchError, Snapshot
from tools.medical_pilot.lifecycle import resolve_project_lifecycle
from tools.medical_pilot.registry import adapter_for_source, resolve_source
from tools.medical_pilot.tianjin_government_procurement_adapter import TianjinGovernmentProcurementAdapter


NATIVE_STRUCTURE_HTML = """
<html>
<head><title>天津市胸科医院检验科设备租赁服务项目（项目编号：XCSD-2026-A-641）中标公告</title></head>
<body>
<h1>天津市胸科医院检验科设备租赁服务项目（项目编号：XCSD-2026-A-641）中标公告</h1>
<p>发布日期：2026年09月25日</p>
<p>一、项目编号：XCSD-2026-A-641</p>
<p>二、项目名称：天津市胸科医院检验科设备租赁服务项目</p>
<p>三、中标信息</p>
<table>
<tr><td>第1包</td></tr>
<tr><td>供应商名称</td><td>供应商地址</td><td>中标金额(万元)</td></tr>
<tr><td>天津测试医疗科技有限公司</td><td>天津市</td><td>500.00</td></tr>
</table>
<p>四、主要标的信息</p>
<p>九、凡对本次公告内容提出询问，请按以下方式联系。</p>
<p>1.采购人信息</p>
<p>名称：天津市胸科医院</p>
<p>地址：天津市</p>
</body>
</html>
"""

CCGP_MIRROR_HTML = """
<html><head><title>天津市胸科医院检验科设备租赁服务项目（项目编号：XCSD-2026-A-641）中标公告</title></head>
<body>
<table>
<tr><td>采购项目名称</td><td>天津市胸科医院检验科设备租赁服务项目</td></tr>
<tr><td>采购单位</td><td>天津市胸科医院</td></tr>
<tr><td>公告时间</td><td>2026年09月25日 18:50</td></tr>
</table>
<p>项目编号：XCSD-2026-A-641</p>
<p>三、中标信息</p>
</body></html>
"""

MEDICAL_ATTACHMENT_URL = (
    "https://www.ccgp-tianjin.gov.cn/portal/documentView.do?"
    "id=cehQ4qF6Unc%2A&method=downEnId"
)
MEDICAL_ATTACHMENT_FILENAME = "招标文件（ TGPC-2025-A-0164 ）.docx"


def snapshot(url: str, html: str) -> Snapshot:
    body = html.encode("utf-8")
    return Snapshot(
        source_url=url,
        fetched_at="2026-09-25T12:00:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        text=html,
        sha256=hashlib.sha256(body).hexdigest(),
    )


class TianjinGovernmentProcurementAdapterTests(unittest.TestCase):
    def test_native_detail_route_parses_buyer_and_day_precision_without_model_help(self) -> None:
        url = "https://tjgp.cz.tj.gov.cn/portal/documentView.do?method=view&id=999999999&ver=2"
        parsed = TianjinGovernmentProcurementAdapter().parse_notice(snapshot(url, NATIVE_STRUCTURE_HTML))
        self.assertEqual(parsed.source_id, "tj_government_procurement")
        self.assertEqual(parsed.notice_type, "AWARD")
        self.assertEqual(parsed.project_number, "XCSD-2026-A-641")
        self.assertEqual(parsed.project_name, "天津市胸科医院检验科设备租赁服务项目")
        self.assertEqual(parsed.buyer_name, "天津市胸科医院")
        self.assertEqual(parsed.published_at, "2026-09-25T00:00:00+08:00")
        self.assertEqual(parsed.published_at_precision, "DAY")
        self.assertTrue(parsed.eligible_for_verified)
        self.assertEqual(len(parsed.award_packages), 1)
        self.assertEqual(parsed.award_packages[0].supplier_name, "天津测试医疗科技有限公司")

    def test_registry_accepts_native_detail_route_and_rejects_spoofed_host(self) -> None:
        url = "http://tjgp.cz.tj.gov.cn/portal/documentView.do?method=view&id=611515456&ver=2"
        source = resolve_source(url)
        self.assertEqual(source.source_id, "tj_government_procurement")
        self.assertEqual(source.provenance_role, "PRIMARY_SOURCE")
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

        with self.assertRaises(ValueError):
            resolve_source(
                "https://tjgp.cz.tj.gov.cn.attacker.example/portal/documentView.do?method=view&id=611515456&ver=2"
            )

    def test_ccgp_tianjin_alias_and_reordered_query_parse_through_same_adapter(self) -> None:
        url = "https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=999999999&ver=2&method=view"
        source = resolve_source(url)
        self.assertEqual(source.source_id, "tj_government_procurement")
        parsed = adapter_for_source(source).parse_notice(snapshot(url, NATIVE_STRUCTURE_HTML))
        self.assertEqual(parsed.source_id, "tj_government_procurement")
        self.assertEqual(parsed.project_number, "XCSD-2026-A-641")
        self.assertTrue(parsed.eligible_for_verified)

    def test_known_medical_downenid_attachment_is_discovered_but_not_download_authorized(self) -> None:
        adapter = TianjinGovernmentProcurementAdapter()
        self.assertTrue(adapter.is_verified_attachment_url(MEDICAL_ATTACHMENT_URL))
        html = (
            '<a href="https://www.ccgp-tianjin.gov.cn/portal/documentView.do?'
            'id=cehQ4qF6Unc%2A&amp;method=downEnId">'
            + MEDICAL_ATTACHMENT_FILENAME
            + "</a>"
        )
        candidates = adapter.discover_attachment_candidates(
            html,
            "https://ggzyfw.beijing.gov.cn/xtggtjcggg/20250702/5173111.html",
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.filename, MEDICAL_ATTACHMENT_FILENAME)
        self.assertEqual(candidate.extension, ".docx")
        self.assertFalse(candidate.download_authorized)
        self.assertEqual(
            candidate.handling_policy,
            "DISCOVER_ONLY_TIANJIN_OFFICIAL_DOWNENID_PENDING_BYTES_VALIDATION",
        )
        with self.assertRaises(FetchError) as context:
            BoundedAttachmentFetcher({"www.ccgp-tianjin.gov.cn"}).fetch(candidate)
        self.assertEqual(context.exception.code, "ATTACHMENT_DOWNLOAD_NOT_AUTHORIZED")

    def test_downenid_attachment_route_rejects_spoofed_or_unsafe_variants(self) -> None:
        adapter = TianjinGovernmentProcurementAdapter()
        invalid = (
            "https://evil.example/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId",
            "https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=../secret&method=downEnId",
            "https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=delete",
            "https://www.ccgp-tianjin.gov.cn/portal/documentView.do?id=cehQ4qF6Unc%2A&method=downEnId&x=1",
            "https://www.ccgp-tianjin.gov.cn/portal/other.do?id=cehQ4qF6Unc%2A&method=downEnId",
        )
        for url in invalid:
            with self.subTest(url=url):
                self.assertFalse(adapter.is_verified_attachment_url(url))

    def test_attachment_route_is_not_treated_as_notice_detail_route(self) -> None:
        adapter = TianjinGovernmentProcurementAdapter()
        self.assertTrue(adapter.is_verified_attachment_url(MEDICAL_ATTACHMENT_URL))
        self.assertFalse(adapter.is_verified_detail_url(MEDICAL_ATTACHMENT_URL))
        with self.assertRaises(ValueError):
            resolve_source(MEDICAL_ATTACHMENT_URL)

    def test_primary_and_ccgp_mirror_share_one_project_and_primary_wins_same_day_evidence(self) -> None:
        native_url = "https://tjgp.cz.tj.gov.cn/portal/documentView.do?method=view&id=999999999&ver=2"
        ccgp_url = "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202609/t-mirror-fixture.htm"
        native_snap = snapshot(native_url, NATIVE_STRUCTURE_HTML)
        mirror_snap = snapshot(ccgp_url, CCGP_MIRROR_HTML)

        native_event, _ = build_ccgp_lifecycle_event_and_facts(
            TianjinGovernmentProcurementAdapter().parse_notice(native_snap), native_snap
        )
        mirror_event, _ = build_ccgp_lifecycle_event_and_facts(
            CcgpLifecycleAdapter().parse_notice(mirror_snap), mirror_snap
        )
        self.assertEqual(native_event["canonical_project_id"], mirror_event["canonical_project_id"])
        self.assertNotEqual(native_event["event_id"], mirror_event["event_id"])

        aggregate = resolve_project_lifecycle([native_event, mirror_event])
        self.assertEqual(aggregate.lifecycle_state, "AWARDED")
        self.assertEqual(aggregate.verification_status, "VERIFIED")
        self.assertEqual(aggregate.current_event_id, native_event["event_id"])
        self.assertEqual(aggregate.latest_effective_at, native_event["effective_at"])
        self.assertEqual(len(aggregate.source_event_ids), 2)

    def test_missing_purchaser_name_does_not_drift_into_agent_name(self) -> None:
        url = "https://tjgp.cz.tj.gov.cn/portal/documentView.do?method=view&id=999999998&ver=2"
        html = NATIVE_STRUCTURE_HTML.replace(
            "<p>名称：天津市胸科医院</p>\n<p>地址：天津市</p>",
            "<p>地址：天津市</p><p>2.采购代理机构信息</p><p>名称：天津某采购代理有限公司</p>",
        )
        parsed = TianjinGovernmentProcurementAdapter().parse_notice(snapshot(url, html))
        self.assertEqual(parsed.buyer_name, "")
        self.assertNotIn("buyer_name", parsed.evidence_fragments)
        self.assertFalse(parsed.eligible_for_verified)
        self.assertIn("buyer_name", parsed.verification_reason or "")

    def test_unverified_route_variants_fail_closed(self) -> None:
        adapter = TianjinGovernmentProcurementAdapter()
        self.assertFalse(adapter.is_verified_detail_url("https://tjgp.cz.tj.gov.cn/portal/other.do?id=1"))
        self.assertFalse(
            adapter.is_verified_detail_url(
                "https://tjgp.cz.tj.gov.cn/portal/documentView.do?method=view&id=abc&ver=2"
            )
        )
        self.assertFalse(
            adapter.is_verified_detail_url(
                "https://ccgp-tianjin.gov.cn/portal/documentView.do?method=view&id=1&ver=2&extra=1"
            )
        )
        with self.assertRaises(ValueError):
            adapter.parse_notice(
                snapshot("https://tjgp.cz.tj.gov.cn/portal/other.do?id=1", NATIVE_STRUCTURE_HTML)
            )


if __name__ == "__main__":
    unittest.main()
