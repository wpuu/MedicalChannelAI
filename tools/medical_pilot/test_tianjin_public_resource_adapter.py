from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.ccgp_lifecycle_adapter import (
    CcgpLifecycleAdapter,
    build_ccgp_lifecycle_event_and_facts,
)
from tools.medical_pilot.collector_core import Snapshot
from tools.medical_pilot.lifecycle import resolve_project_lifecycle
from tools.medical_pilot.registry import adapter_for_source, resolve_source
from tools.medical_pilot.tianjin_public_resource_adapter import TianjinPublicResourceAdapter


PUBLIC_RESOURCE_HTML = """
<html><head><title>天津市疾病预防控制中心 天津市疾病预防控制中心性病艾滋病检测试剂、耗材招标采购项目 (项目编号:GY-2025-058)中标公告</title></head>
<body>
<div>2025.06.05 信息来源:天津市财政局 浏览次数：</div>
<h1>天津市疾病预防控制中心 天津市疾病预防控制中心性病艾滋病检测试剂、耗材招标采购项目 (项目编号:GY-2025-058)中标公告</h1>
<p>发布日期：2025年06月05日 发布来源：天津市疾病预防控制中心</p>
<p>一、项目编号：GY-2025-058</p>
<p>二、项目名称：天津市疾病预防控制中心性病艾滋病检测试剂、耗材招标采购项目</p>
<p>三、中标信息</p>
<table>
<tr><td>第3包</td></tr>
<tr><td>供应商名称</td><td>供应商地址</td><td>中标金额(万元)</td></tr>
<tr><td>天津市卫防科技有限公司</td><td>天津市南开区</td><td>1.65</td></tr>
</table>
<p>四、主要标的信息</p>
<table>
<tr><td>第3包</td></tr>
<tr><td>类型</td><td>名称</td><td>品牌</td><td>规格型号</td><td>数量</td><td>单价(万元)</td></tr>
<tr><td>货物类</td><td>采血管</td><td>瑞埼</td><td>EDTA-K2</td><td>10000</td><td>0.000125</td></tr>
</table>
<p>五、评审专家名单</p>
<p>九、凡对本次公告内容提出询问，请按以下方式联系。</p>
<p>1.采购人信息 名称：天津市疾病预防控制中心 地址：天津市河东区华越道6号 联系方式：022-24333451</p>
</body></html>
"""

CCGP_MIRROR_HTML = """
<html><head><title>天津市疾病预防控制中心性病艾滋病检测试剂、耗材招标采购项目 (项目编号:GY-2025-058)中标公告</title></head>
<body>
<table>
<tr><td>采购项目名称</td><td>天津市疾病预防控制中心性病艾滋病检测试剂、耗材招标采购项目</td></tr>
<tr><td>采购单位</td><td>天津市疾病预防控制中心</td></tr>
<tr><td>公告时间</td><td>2025年06月05日 12:30</td></tr>
</table>
<p>项目编号：GY-2025-058</p>
<p>三、中标信息</p>
</body></html>
"""


def snapshot(url: str, html: str) -> Snapshot:
    body = html.encode("utf-8")
    return Snapshot(
        source_url=url,
        fetched_at="2026-08-28T04:40:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        text=html,
        sha256=hashlib.sha256(body).hexdigest(),
    )


class TianjinPublicResourceAdapterTests(unittest.TestCase):
    def test_verified_award_preserves_day_only_publication_precision(self) -> None:
        snap = snapshot(
            "https://ggzy.zwfwb.tj.gov.cn/jyxxcgjg/I0BgS5K5kAp2ToTVxelNlQ.jhtml",
            PUBLIC_RESOURCE_HTML,
        )
        parsed = TianjinPublicResourceAdapter().parse_notice(snap)
        self.assertEqual(parsed.source_id, "tj_public_resource_exchange")
        self.assertEqual(parsed.notice_type, "AWARD")
        self.assertEqual(parsed.project_number, "GY-2025-058")
        self.assertEqual(
            parsed.project_name,
            "天津市疾病预防控制中心性病艾滋病检测试剂、耗材招标采购项目",
        )
        self.assertEqual(parsed.buyer_name, "天津市疾病预防控制中心")
        self.assertEqual(parsed.published_at, "2025-06-05T00:00:00+08:00")
        self.assertEqual(parsed.published_at_precision, "DAY")
        self.assertTrue(parsed.eligible_for_verified)
        self.assertEqual(len(parsed.award_packages), 1)
        self.assertEqual(parsed.award_packages[0].supplier_name, "天津市卫防科技有限公司")
        self.assertEqual(parsed.award_packages[0].award_amount_cny, "16500.00")

        event, facts = build_ccgp_lifecycle_event_and_facts(parsed, snap)
        self.assertEqual(event["published_at_precision"], "DAY")
        self.assertEqual(event["verification_status"], "VERIFIED")
        self.assertTrue(all(fact["model_generated"] is False for fact in facts))

    def test_registry_accepts_only_verified_result_detail_path_for_this_partial_source(self) -> None:
        url = "https://ggzy.zwfwb.tj.gov.cn/jyxxcgjg/I0BgS5K5kAp2ToTVxelNlQ.jhtml"
        source = resolve_source(url)
        self.assertEqual(source.source_id, "tj_public_resource_exchange")
        self.assertEqual(source.raw.get("provenance_role"), "OFFICIAL_MIRROR")
        self.assertEqual(adapter_for_source(source).source_id, source.source_id)

        with self.assertRaises(ValueError):
            resolve_source("https://ggzy.zwfwb.tj.gov.cn/jyxxcgzb/example.jhtml")

    def test_ccgp_and_official_mirror_share_one_canonical_project_by_exact_project_number(self) -> None:
        public_snap = snapshot(
            "https://ggzy.zwfwb.tj.gov.cn/jyxxcgjg/I0BgS5K5kAp2ToTVxelNlQ.jhtml",
            PUBLIC_RESOURCE_HTML,
        )
        ccgp_snap = snapshot(
            "https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202506/t-mirror-fixture.htm",
            CCGP_MIRROR_HTML,
        )
        public_event, _ = build_ccgp_lifecycle_event_and_facts(
            TianjinPublicResourceAdapter().parse_notice(public_snap), public_snap
        )
        ccgp_event, _ = build_ccgp_lifecycle_event_and_facts(
            CcgpLifecycleAdapter().parse_notice(ccgp_snap), ccgp_snap
        )
        self.assertEqual(public_event["canonical_project_id"], ccgp_event["canonical_project_id"])
        self.assertNotEqual(public_event["event_id"], ccgp_event["event_id"])

        aggregate = resolve_project_lifecycle([public_event, ccgp_event])
        self.assertEqual(aggregate.lifecycle_state, "AWARDED")
        self.assertEqual(len(aggregate.source_event_ids), 2)
        self.assertEqual(aggregate.verification_status, "VERIFIED")


if __name__ == "__main__":
    unittest.main()
