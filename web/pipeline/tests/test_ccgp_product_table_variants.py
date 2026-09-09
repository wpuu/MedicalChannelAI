from __future__ import annotations

import unittest

from medical_channel_pipeline.ccgp_detail import parse_ccgp_public_tender_html


BASE = """
公开招标公告
公告信息：采购单位 | 中国医学科学院北京协和医院 行政区域 | 北京市 | 公告时间 | 2026年09月08日 10:00
发布日期：2026年09月08日
一、项目基本情况
项目编号：B0708-CMC26N7917
项目名称：中国医学科学院北京协和医院放射科乳腺机采购项目
预算金额：430万元
采购需求：见下表
三、获取招标文件
时间：2026年09月09日 至 2026年09月15日，每天上午9:00至12:00，下午12:00至16:00。
地点：北京
四、提交投标文件截止时间、开标时间和地点
提交投标文件截止时间：2026年09月29日 13点30分
七、对本次招标提出询问，请按以下方式联系。
1.采购人信息 名称：中国医学科学院北京协和医院 地址：北京市东城区帅府园1号
3.项目联系方式 项目联系人：张老师 电 话：010-81168235
"""


def page(table: str) -> str:
    return '<html><body><pre>' + BASE + '</pre>' + table + '</body></html>'


class CcgpProductTableVariantTests(unittest.TestCase):
    def parse(self, table: str):
        return parse_ccgp_public_tender_html(
            page(table),
            source_url='https://www.ccgp.gov.cn/cggg/zygg/gkzb/202609/t20260908_27289494.htm',
            observed_at='2026-09-09T03:00:00+00:00',
            opportunity_id='ccgp_bj_product_variant',
        )

    def test_device_name_and_quantity_table_is_grounded(self) -> None:
        record = self.parse("""
        <table>
          <tr><th>设备名称</th><th>数量（套）</th><th>简要技术要求</th><th>备注</th></tr>
          <tr><td>乳腺机</td><td>1</td><td>用于乳腺疾病筛查及诊断</td><td>不允许进口</td></tr>
        </table>
        """)
        self.assertEqual(record['facts']['product_items'], [{
            'raw_name': '乳腺机', 'category': None, 'quantity': '1', 'specification': '用于乳腺疾病筛查及诊断'
        }])

    def test_mark_name_with_separate_unit_is_combined(self) -> None:
        record = self.parse("""
        <table>
          <tr><th>包号</th><th>品目号</th><th>标的名称</th><th>数量</th><th>单位</th><th>备注</th></tr>
          <tr><td>1</td><td>1-1</td><td>双能X射线骨密度仪</td><td>1</td><td>套</td><td>单一产品</td></tr>
        </table>
        """)
        item = record['facts']['product_items'][0]
        self.assertEqual(item['raw_name'], '双能X射线骨密度仪')
        self.assertEqual(item['quantity'], '1套')

    def test_rowspan_is_expanded_without_shifting_later_product_names(self) -> None:
        record = self.parse("""
        <table>
          <tr><th>序号</th><th>货物名称</th><th>数量</th><th>单位</th><th>简要技术需求</th><th>是否接受进口</th></tr>
          <tr><td rowspan="3">1</td><td>离心机</td><td>3</td><td>台</td><td rowspan="3">详见采购需求</td><td>否</td></tr>
          <tr><td>全自动干式生化分析仪</td><td>1</td><td>台</td><td>否</td></tr>
          <tr><td>生物显微镜</td><td>1</td><td>台</td><td>否</td></tr>
        </table>
        """)
        items = record['facts']['product_items']
        self.assertEqual([item['raw_name'] for item in items], ['离心机', '全自动干式生化分析仪', '生物显微镜'])
        self.assertEqual([item['quantity'] for item in items], ['3台', '1台', '1台'])
        self.assertTrue(all(item['specification'] == '详见采购需求' for item in items))

    def test_item_name_can_be_product_name_when_no_distinct_mark_column_exists(self) -> None:
        record = self.parse("""
        <table>
          <tr><th>包号</th><th>品目号</th><th>品目名称</th><th>数量（台/套）</th><th>备注</th></tr>
          <tr><td>1</td><td>1-1</td><td>X射线计算机体层摄影设备（CT）</td><td>1</td><td>单一产品</td></tr>
        </table>
        """)
        item = record['facts']['product_items'][0]
        self.assertEqual(item['raw_name'], 'X射线计算机体层摄影设备（CT）')
        self.assertIsNone(item['category'])
        self.assertEqual(item['quantity'], '1')

    def test_item_name_remains_category_when_distinct_procurement_mark_exists(self) -> None:
        record = self.parse("""
        <table>
          <tr><th>品目名称</th><th>采购标的</th><th>数量（单位）</th><th>技术要求</th></tr>
          <tr><td>医用X线诊断设备</td><td>64排螺旋CT设备</td><td>1(台)</td><td>详见采购文件</td></tr>
        </table>
        """)
        item = record['facts']['product_items'][0]
        self.assertEqual(item['raw_name'], '64排螺旋CT设备')
        self.assertEqual(item['category'], '医用X线诊断设备')

    def test_unrelated_name_quantity_table_is_not_treated_as_procurement_items(self) -> None:
        record = self.parse("""
        <table><tr><th>名称</th><th>数量</th></tr><tr><td>附件</td><td>1</td></tr></table>
        """)
        self.assertEqual(record['facts']['product_items'], [])
        self.assertEqual(record['facts']['product_categories'], [])


if __name__ == '__main__':
    unittest.main()
