from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.ccgp_procurement_demand import (
    build_ccgp_procurement_demand_facts,
    extract_ccgp_procurement_demand,
)
from tools.medical_pilot.collector_core import Snapshot
from tools.medical_pilot.product_classifier import classify_product_facts


DEMAND_HTML = """
<html><body>
<table>
<tr><td>包号</td><td>是否设置最高限价</td><td>预算（万元）</td><td>采购目录</td><td>采购需求</td></tr>
<tr><td>1</td><td>是</td><td>500</td><td>临床检验设备</td><td>基因测序仪、自动化建库仪、宏基因组分析系统</td></tr>
<tr><td>2</td><td>是</td><td>300</td><td>临床检验设备</td><td>微生物质谱检测系统（飞行时间质谱检测系统）、高性能生物计算工业一体机</td></tr>
</table>
<table>
<tr><td>资格要求</td><td>供应商应具有医疗器械经营许可；如涉及基因测序仪产品请按法规提供材料。</td></tr>
</table>
</body></html>
"""


def snapshot(body: str = DEMAND_HTML) -> Snapshot:
    encoded = body.encode("utf-8")
    return Snapshot(
        source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260824_27194426.htm",
        fetched_at="2026-08-31T00:00:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=encoded,
        text=body,
        sha256=hashlib.sha256(encoded).hexdigest(),
    )


class CcgpProcurementDemandTests(unittest.TestCase):
    def test_extracts_only_package_demand_cells(self) -> None:
        items = extract_ccgp_procurement_demand(DEMAND_HTML)
        self.assertEqual(
            items,
            (
                "基因测序仪、自动化建库仪、宏基因组分析系统",
                "微生物质谱检测系统（飞行时间质谱检测系统）、高性能生物计算工业一体机",
            ),
        )
        self.assertTrue(all("供应商" not in item for item in items))

    def test_requires_explicit_package_and_demand_headers(self) -> None:
        html = """
        <table><tr><td>资格要求</td><td>采购需求</td></tr>
        <tr><td>1</td><td>基因测序仪</td></tr></table>
        """
        self.assertEqual(extract_ccgp_procurement_demand(html), ())

    def test_builds_verified_official_product_item_facts(self) -> None:
        snap = snapshot()
        event = {
            "event_id": "evt_11111111-1111-1111-1111-111111111111",
            "canonical_project_id": "mprj_22222222-2222-2222-2222-222222222222",
            "verification_status": "VERIFIED",
        }
        facts = build_ccgp_procurement_demand_facts(
            event=event,
            snapshot=snap,
            source_id="ccgp_local_notices",
            source_url=snap.source_url,
            published_at="2026-08-24T18:50:00+08:00",
            verification_reason=None,
        )
        self.assertEqual(len(facts), 2)
        for fact in facts:
            self.assertEqual(fact["field_name"], "product_item")
            self.assertEqual(fact["fact_type"], "OFFICIAL_PUBLIC_FACT")
            self.assertEqual(fact["verification_status"], "VERIFIED")
            self.assertFalse(fact["model_generated"])
            self.assertEqual(fact["parser_version"], "ccgp-procurement-demand-v0.1")

    def test_grounded_demand_facts_drive_controlled_taxonomy(self) -> None:
        snap = snapshot()
        event = {
            "event_id": "evt_11111111-1111-1111-1111-111111111111",
            "canonical_project_id": "mprj_22222222-2222-2222-2222-222222222222",
            "verification_status": "VERIFIED",
        }
        facts = build_ccgp_procurement_demand_facts(
            event=event,
            snapshot=snap,
            source_id="ccgp_local_notices",
            source_url=snap.source_url,
            published_at="2026-08-24T18:50:00+08:00",
            verification_reason=None,
        )
        result = classify_product_facts(facts)
        self.assertEqual(
            set(result.labels),
            {
                "LAB_NGS_SEQUENCER",
                "LAB_AUTOMATED_LIBRARY_PREP",
                "LAB_METAGENOMICS_ANALYSIS",
                "LAB_MICROBIAL_MASS_SPECTROMETRY",
                "LAB_BIOINFORMATICS_COMPUTE_APPLIANCE",
            },
        )
        self.assertTrue(result.supporting_fact_ids)


if __name__ == "__main__":
    unittest.main()
