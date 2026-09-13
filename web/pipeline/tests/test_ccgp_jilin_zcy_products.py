from __future__ import annotations

import unittest

from medical_channel_pipeline.ccgp_detail import (
    _extract_bounded_procurement_demand_items,
    _extract_grounded_text_product_items,
    _extract_zcy_brief_description_items,
    _extract_zcy_primary_subject_items,
)


class JilinZcyProductTests(unittest.TestCase):
    def wrap(self, demand: str) -> str:
        return f'一、项目基本情况 采购需求： {demand} 合同履约期限：30天 二、申请人的资格要求'

    @staticmethod
    def pairs(items):
        return [(item['raw_name'], item['quantity']) for item in items]

    def test_primary_subject_name_and_quantity_are_grounded(self):
        text = self.wrap(
            '标项名称: 合同包1 数量: 预算金额（元）：5108800 '
            '简要规格描述或项目基本概况介绍、用途： '
            '主要标的名称：血液透析机（单泵）；数量：10台；简要技术需求：用于血液透析； '
            '主要标的名称：三维移动式C形臂X射线机等；数量：1套；简要技术需求：用于骨科手术。 备注：'
        )
        expected = [('血液透析机（单泵）', '10台'), ('三维移动式C形臂X射线机等', '1套')]
        self.assertEqual(self.pairs(_extract_zcy_primary_subject_items(text)), expected)
        self.assertEqual(self.pairs(_extract_grounded_text_product_items(text)), expected)

    def test_quantity_label_is_never_a_product_name(self):
        text = self.wrap(
            '标项名称: 合同包1 数量: 预算金额（元）：5108800 '
            '简要规格描述或项目基本概况介绍、用途： 主要标的名称：血液透析机；数量：10台；备注：'
        )
        items = _extract_bounded_procurement_demand_items(text)
        self.assertFalse(any(item['raw_name'] == '数量' for item in items))

    def test_brief_description_explicit_product_quantity(self):
        text = self.wrap(
            '标项一 标项名称: 血管内超声（三次） 数量: 1 预算金额（元）：170000 '
            '简要规格描述或项目基本概况介绍、用途： 血管内超声1套及配套耗材,具体内容详见第五章采购需求及技术要求 备注： '
            '标项二 标项名称: 非接触眼压计（四次） 数量: 1 预算金额（元）：110000 '
            '简要规格描述或项目基本概况介绍、用途： 非接触眼压计1套，具体内容详见第五章采购需求及技术要求 备注：'
        )
        self.assertEqual(
            self.pairs(_extract_zcy_brief_description_items(text)),
            [('血管内超声', '1套'), ('非接触眼压计', '1套')],
        )

    def test_specific_brief_products_without_quantity_keep_null(self):
        text = self.wrap(
            '标项一 标项名称: 检验设备（一标段） 数量: 预算金额（元）：1800000 '
            '简要规格描述或项目基本概况介绍、用途： 五分类血球分析仪、糖化分析仪、超敏C反应分析仪一体化自动检测流水线采购 备注： '
            '标项二 标项名称: 检验设备（二标段） 数量: 预算金额（元）：1700000 '
            '简要规格描述或项目基本概况介绍、用途： 全自动尿液分析仪(干化学+尿沉渣)采购 备注： '
            '标项三 标项名称: 检验设备（三标段） 数量: 预算金额（元）：750000 '
            '简要规格描述或项目基本概况介绍、用途： 质谱分析仪采购 备注： '
            '标项四 标项名称: 检验设备（四标段） 数量: 预算金额（元）：480000 '
            '简要规格描述或项目基本概况介绍、用途： 微生物药敏分析仪采购 备注：'
        )
        self.assertEqual(
            self.pairs(_extract_zcy_brief_description_items(text)),
            [
                ('五分类血球分析仪、糖化分析仪、超敏C反应分析仪一体化自动检测流水线', None),
                ('全自动尿液分析仪(干化学+尿沉渣)', None),
                ('质谱分析仪', None),
                ('微生物药敏分析仪', None),
            ],
        )

    def test_specific_reagent_phrase_without_quantity_is_grounded(self):
        text = self.wrap(
            '标项名称: 病毒检验 数量: 预算金额（元）：1514375 '
            '简要规格描述或项目基本概况介绍、用途： '
            '采购埃可病毒30型核酸检测试剂盒（荧光法）等四大症候群监测相关试剂耗材，详见采购文件 备注：'
        )
        self.assertEqual(
            self.pairs(_extract_zcy_brief_description_items(text)),
            [('埃可病毒30型核酸检测试剂盒（荧光法）等四大症候群监测相关试剂耗材', None)],
        )

    def test_generic_or_technical_briefs_remain_empty(self):
        samples = [
            '标项名称: 传染病实验室监测质量提升采购项目 数量: 预算金额（元）：3850000 '
            '简要规格描述或项目基本概况介绍、用途： 通化市疾病预防控制中心采购设备一批，详见招标文件第五章采购需求 备注：',
            '标项名称: 检验检测设备 数量: 预算金额（元）：4460400 '
            '简要规格描述或项目基本概况介绍、用途： 一标段：四平市产品质量检验院食品、工业产品检验检测设备采购，详见配置及参数一览表； 备注：',
            '标项名称: 小动物超声系统等设备 数量: 预算金额（元）：465000 '
            '简要规格描述或项目基本概况介绍、用途： 1.系统需支持云部署及本地部署两种部署方式，用户无需安装桌面端软件可直接登录网址进行实验；等 备注：',
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(_extract_zcy_brief_description_items(self.wrap(sample)), [])


if __name__ == '__main__':
    unittest.main()
