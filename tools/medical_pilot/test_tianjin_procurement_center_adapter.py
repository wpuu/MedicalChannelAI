from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.collector_core import Snapshot
from tools.medical_pilot.registry import adapter_for_source, resolve_source
from tools.medical_pilot.tianjin_procurement_center_adapter import TianjinProcurementCenterAdapter


# Structure regression only. Field wording and route shape are based on indexed official
# tjgpc.zwfwb.tj.gov.cn pages. This local HTML is not represented as a live captured page.
CENTER_STRUCTURE_HTML = """
<html>
<head><title>天津市南开区教育综合服务中心新建校家具项目 (项目编号:TJNK-2026-A-0002)公开招标公告</title></head>
<body>
<h1>天津市南开区教育综合服务中心新建校家具项目 (项目编号:TJNK-2026-A-0002)公开招标公告</h1>
<p>您的当前位置：首页&gt;&gt;项目信息&gt;&gt;采购信息&gt;&gt;公开招标</p>
<p>〖信息时间：2026-3-17〗</p>
<p>受天津市南开区教育综合服务中心委托，天津市南开区财政服务中心将以公开招标方式，对天津市南开区教育综合服务中心新建校家具项目实施政府采购。</p>
<p>一、项目名称和编号</p>
<p>（一）项目名称：天津市南开区教育综合服务中心新建校家具项目</p>
<p>（二）项目编号：TJNK-2026-A-0002</p>
<p>三、项目预算</p>
<p>总预算：6029947元；第一包：2766650元；第二包：3263297元。</p>
<p>八、投标截止时间及方式</p>
<p>（一）投标截止时间：2026年4月8日8:30。</p>
</body>
</html>
"""


def snapshot(url: str, html: str = CENTER_STRUCTURE_HTML) -> Snapshot:
    body = html.encode("utf-8")
    return Snapshot(
        source_url=url,
        fetched_at="2026-03-17T02:00:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        text=html,
        sha256=hashlib.sha256(body).hexdigest(),
    )


class TianjinProcurementCenterAdapterTests(unittest.TestCase):
    def test_official_public_tender_detail_parses_core_fields_deterministically(self) -> None:
        url = "https://tjgpc.zwfwb.tj.gov.cn/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=2E1138AD-0900-4EC0-B863-6E4A41525FB8"
        parsed = TianjinProcurementCenterAdapter().parse_notice(snapshot(url))
        self.assertEqual(parsed.source_id, "tj_government_procurement_center")
        self.assertEqual(parsed.notice_type, "TENDER")
        self.assertEqual(parsed.project_number, "TJNK-2026-A-0002")
        self.assertEqual(parsed.project_name, "天津市南开区教育综合服务中心新建校家具项目")
        self.assertEqual(parsed.buyer_name, "天津市南开区教育综合服务中心")
        self.assertEqual(parsed.published_at, "2026-03-17T00:00:00+08:00")
        self.assertEqual(parsed.published_at_precision, "DAY")
        self.assertEqual(parsed.budget_cny, "6029947.00")
        self.assertEqual(parsed.bid_deadline, "2026-04-08T08:30:00+08:00")
        self.assertEqual(parsed.procurement_method, "PUBLIC_TENDER")
        self.assertTrue(parsed.eligible_for_verified)

    def test_registry_resolves_exact_official_detail_route(self) -> None:
        url = "https://tjgpc.zwfwb.tj.gov.cn/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=F8DE1A68-9A7A-4093-A427-027031E9CE17"
        source = resolve_source(url)
        self.assertEqual(source.source_id, "tj_government_procurement_center")
        self.assertEqual(source.provenance_role, "PRIMARY_SOURCE")
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

    def test_route_rejects_spoofed_host_wrong_path_extra_query_and_non_uuid(self) -> None:
        adapter = TianjinProcurementCenterAdapter()
        invalid = (
            "https://tjgpc.zwfwb.tj.gov.cn.attacker.example/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=2E1138AD-0900-4EC0-B863-6E4A41525FB8",
            "https://tjgpc.zwfwb.tj.gov.cn/webInfo/other.do?pkWebInfoId=2E1138AD-0900-4EC0-B863-6E4A41525FB8",
            "https://tjgpc.zwfwb.tj.gov.cn/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=2E1138AD-0900-4EC0-B863-6E4A41525FB8&x=1",
            "https://tjgpc.zwfwb.tj.gov.cn/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=not-a-uuid",
        )
        for url in invalid:
            with self.subTest(url=url):
                self.assertFalse(adapter.is_verified_detail_url(url))
                with self.assertRaises(ValueError):
                    resolve_source(url)

    def test_missing_buyer_keeps_notice_unverified_instead_of_guessing_agent(self) -> None:
        url = "https://tjgpc.zwfwb.tj.gov.cn/webInfo/getWebInfoByPkWebInfoId1.do?pkWebInfoId=526595EA-EC53-4938-8CE2-2DD3CC476AC5"
        html = CENTER_STRUCTURE_HTML.replace(
            "受天津市南开区教育综合服务中心委托，天津市南开区财政服务中心将以公开招标方式，",
            "天津市南开区财政服务中心将以公开招标方式，",
        )
        parsed = TianjinProcurementCenterAdapter().parse_notice(snapshot(url, html))
        self.assertEqual(parsed.buyer_name, "")
        self.assertFalse(parsed.eligible_for_verified)
        self.assertIn("buyer_name", parsed.verification_reason or "")


if __name__ == "__main__":
    unittest.main()
