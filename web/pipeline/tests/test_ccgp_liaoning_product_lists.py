import unittest

from medical_channel_pipeline.ccgp_detail import _extract_grounded_text_product_items


class LiaoningGroundedProductListTests(unittest.TestCase):
    def test_top_level_numbered_products_ignore_decimal_subparameters(self):
        text = """采购需求：查看
技术参数要求：1.超声主机 1台：1.1≥18英寸高分辨率显示器 1.2≥11英寸触摸屏 2.超声电子上消化道内窥镜（扇扫） 1条▲2.1视野方向≥45° 2.2视野角≥140° 3.超声电子上消化道内窥镜（环扫） 1条3.1景深≥3-100mm 4.高清电子内窥镜系统 1套4.1、图像处理器4.1.1高清视频输出
★1 交货时间：签订合同后30个工作日。"""
        items = _extract_grounded_text_product_items(text)
        self.assertEqual(
            [(item['raw_name'], item['quantity']) for item in items],
            [
                ('超声主机', '1台'),
                ('超声电子上消化道内窥镜（扇扫）', '1条'),
                ('超声电子上消化道内窥镜（环扫）', '1条'),
                ('高清电子内窥镜系统', '1套'),
            ],
        )

    def test_product_name_quantity_plaintext_table(self):
        text = """采购需求：查看
1、货物采购技术参数：
序号
产品名称
数量
详细技术参数 重要提示
1
结核分枝杆菌耐药基因检测多通道分析仪
1台
★1.检测通量可同时检测4个样本
2
高压蒸汽灭菌器
1台
技术要求
3
生物安全柜
1个
技术要求
合同履行期限：30日"""
        items = _extract_grounded_text_product_items(text)
        self.assertEqual(
            [(item['raw_name'], item['quantity']) for item in items],
            [
                ('结核分枝杆菌耐药基因检测多通道分析仪', '1台'),
                ('高压蒸汽灭菌器', '1台'),
                ('生物安全柜', '1个'),
            ],
        )

    def test_item_name_quantity_unit_plaintext_table(self):
        text = """采购需求：查看
一、设备名称及数量
包号
品目号
品目名称
数量
计量单位
是否为核心产品
001包
01
负极板回路垫
2
套
否
02
电动综合手术床
4
张
否
03
高频电刀
4
台
否
投标人须以包为单位对包中全部内容进行投标，不得拆分。"""
        items = _extract_grounded_text_product_items(text)
        self.assertEqual(
            [(item['raw_name'], item['quantity']) for item in items],
            [
                ('负极板回路垫', '2套'),
                ('电动综合手术床', '4张'),
                ('高频电刀', '4台'),
            ],
        )

    def test_attachment_only_does_not_invent_products(self):
        text = '采购需求：查看\n详见葫芦岛市第四人民医院综合设备采购项目招标文件第三章货物需求。\n合同履行期限：60日'
        self.assertEqual(_extract_grounded_text_product_items(text), [])

    def test_numbered_technical_requirements_without_quantity_are_not_products(self):
        text = '采购需求：查看\n一、主要技术参数\n1.尺寸不低于1200mm\n2.材质304不锈钢\n3.支持消防联动\n合同履行期限：一年'
        self.assertEqual(_extract_grounded_text_product_items(text), [])


if __name__ == '__main__':
    unittest.main()
