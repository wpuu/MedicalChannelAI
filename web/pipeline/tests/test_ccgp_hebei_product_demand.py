from __future__ import annotations

import unittest

from medical_channel_pipeline.ccgp_detail import _extract_bounded_procurement_demand_items


class HebeiProcurementDemandProductTests(unittest.TestCase):
    def items(self, demand: str):
        text = f"一、项目基本情况 项目名称：测试 采购需求：{demand} 合同履行期限：30日 二、申请人的资格要求"
        return [(item['raw_name'], item['quantity']) for item in _extract_bounded_procurement_demand_items(text)]

    def test_single_device_quantity_is_grounded(self):
        self.assertEqual(self.items('拟采购病理数字化切片扫描仪4套，具体内容详见第四部分采购需求'), [('病理数字化切片扫描仪', '4套')])
        self.assertEqual(self.items('移动床旁DR机采购2台'), [('移动床旁DR机', '2台')])
        self.assertEqual(self.items('血液透析机3台，详见招标文件'), [('血液透析机', '3台')])

    def test_semicolon_multi_device_list_is_grounded(self):
        self.assertEqual(
            self.items('脊柱内镜系统1套；内热针灸治疗仪3台；动态心电记录仪8台。'),
            [('脊柱内镜系统', '1套'), ('内热针灸治疗仪', '3台'), ('动态心电记录仪', '8台')],
        )

    def test_package_budget_and_quantity_format_is_grounded(self):
        self.assertEqual(
            self.items('其中包1:数字胃肠X射线系统：预算金额：130万元、数量：1套，包2:医用C型臂X光机：预算金额：70万元、数量：1台，详见第四部分采购需求。'),
            [('数字胃肠X射线系统', '1套'), ('医用C型臂X光机', '1台')],
        )

    def test_no_quantity_or_attachment_only_does_not_invent_items(self):
        self.assertEqual(self.items('详见附件。'), [])
        self.assertEqual(self.items('一标段：广谱病原体靶向高通量检测；二标段：中性粒细胞载脂蛋白检测。'), [])
        self.assertEqual(self.items('A包：购买血液质量生化分析系统；B包：购买大容量低温离心机及离心配平仪。'), [])

    def test_text_after_bounded_demand_is_never_scanned(self):
        text = '采购需求：详见附件。合同履行期限：30日。资格要求：医疗设备制造商须有3台设备。'
        self.assertEqual(_extract_bounded_procurement_demand_items(text), [])


if __name__ == '__main__':
    unittest.main()
