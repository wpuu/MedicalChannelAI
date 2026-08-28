from __future__ import annotations

import hashlib
import unittest

from tools.medical_pilot.award_items import (
    build_award_items_fact,
    extract_official_award_items,
)
from tools.medical_pilot.ccgp_lifecycle_adapter import (
    CcgpLifecycleAdapter,
    build_ccgp_lifecycle_event_and_facts,
)
from tools.medical_pilot.collector_core import Snapshot


AWARD_WITH_ITEMS_HTML = """
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
<tr><td>供应商名称</td><td>供应商地址</td><td>中标金额(万元)</td></tr>
<tr><td>天津启物科技有限责任公司</td><td>天津市南开区</td><td>873.27</td></tr>
</table>
<p>四、主要标的信息</p>
<table>
<tr><td>第1包</td></tr>
<tr><td>类型</td><td>名称</td><td>品牌</td><td>规格型号</td><td>数量</td><td>单价(万元)</td></tr>
<tr><td>货物类</td><td>蜂巢培养系统</td><td>东富龙</td><td>TY-CF606</td><td>3台</td><td>108.80</td></tr>
<tr><td>货物类</td><td>波浪式生物反应器</td><td>东富龙</td><td>SUR-25L</td><td>6台</td><td>49.87</td></tr>
<tr><td>货物类</td><td>细胞制备全站</td><td>东富龙</td><td>TY-CZ01</td><td>1台</td><td>247.65</td></tr>
</table>
<p>五、评审专家名单：张昊等</p>
</body></html>
"""


def snapshot() -> Snapshot:
    body = AWARD_WITH_ITEMS_HTML.encode("utf-8")
    return Snapshot(
        source_url="https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202608/t20260803_27061943.htm",
        fetched_at="2026-08-28T03:40:00Z",
        status_code=200,
        content_type="text/html; charset=utf-8",
        body=body,
        text=AWARD_WITH_ITEMS_HTML,
        sha256=hashlib.sha256(body).hexdigest(),
    )


class AwardItemsTests(unittest.TestCase):
    def test_extracts_only_officially_stated_product_fields(self) -> None:
        items = extract_official_award_items(AWARD_WITH_ITEMS_HTML)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].package_name, "第1包")
        self.assertEqual(items[0].raw_name, "蜂巢培养系统")
        self.assertEqual(items[0].brand, "东富龙")
        self.assertEqual(items[0].model, "TY-CF606")
        self.assertEqual(items[0].quantity, "3台")
        self.assertEqual(items[0].unit_price_cny, "1088000.00")
        self.assertEqual(items[1].raw_name, "波浪式生物反应器")
        self.assertEqual(items[1].unit_price_cny, "498700.00")
        self.assertEqual(items[2].model, "TY-CZ01")
        self.assertEqual(items[2].unit_price_cny, "2476500.00")

    def test_award_items_fact_is_bound_to_original_main_information_section(self) -> None:
        snap = snapshot()
        parsed = CcgpLifecycleAdapter().parse_notice(snap)
        event, _ = build_ccgp_lifecycle_event_and_facts(parsed, snap)
        items = extract_official_award_items(snap.text)
        fact = build_award_items_fact(
            event=event,
            snapshot=snap,
            source_id=parsed.source_id,
            source_url=parsed.source_url,
            published_at=parsed.published_at,
            items=items,
        )
        self.assertIsNotNone(fact)
        assert fact is not None
        self.assertEqual(fact["field_name"], "award_items")
        self.assertEqual(fact["fact_type"], "OFFICIAL_PUBLIC_FACT")
        self.assertFalse(fact["model_generated"])
        self.assertEqual(fact["verification_status"], "VERIFIED")
        self.assertEqual(fact["field_value"][0]["brand"], "东富龙")
        self.assertEqual(fact["field_value"][0]["model"], "TY-CF606")
        self.assertIsNotNone(fact["evidence_locator"]["text_hash"])

    def test_missing_official_main_information_section_prevents_fact_promotion(self) -> None:
        html = AWARD_WITH_ITEMS_HTML.replace("四、主要标的信息", "产品表").replace("五、评审专家名单", "结束")
        body = html.encode("utf-8")
        snap = Snapshot(
            source_url="https://www.ccgp.gov.cn/cggg/dfgg/zbgg/202608/t20260803_27061943.htm",
            fetched_at="2026-08-28T03:40:00Z",
            status_code=200,
            content_type="text/html; charset=utf-8",
            body=body,
            text=html,
            sha256=hashlib.sha256(body).hexdigest(),
        )
        parsed = CcgpLifecycleAdapter().parse_notice(snap)
        event, _ = build_ccgp_lifecycle_event_and_facts(parsed, snap)
        items = extract_official_award_items(snap.text)
        fact = build_award_items_fact(
            event=event,
            snapshot=snap,
            source_id=parsed.source_id,
            source_url=parsed.source_url,
            published_at=parsed.published_at,
            items=items,
        )
        self.assertIsNone(fact)


if __name__ == "__main__":
    unittest.main()
