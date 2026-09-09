#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from textwrap import dedent


def main() -> int:
    parser_path = Path('web/pipeline/medical_channel_pipeline/ccgp_detail.py')
    text = parser_path.read_text(encoding='utf-8')
    if '_extract_zcy_primary_subject_items' in text:
        raise RuntimeError('JILIN_ZCY_PATCH_ALREADY_PRESENT')

    marker = "\n\ndef _extract_top_level_numbered_quantity_items(text: str) -> list[dict[str, Any]]:\n"
    if marker not in text:
        raise RuntimeError('INSERT_MARKER_NOT_FOUND')

    insertion = dedent(r'''

    _ZCY_SPECIFIC_PRODUCT_TERMS = (
        '分析仪', '试剂', '试剂盒', '流水线', '质谱', '超声', '内窥镜', '内镜', '离心机',
        '显微镜', '监护仪', '呼吸机', '透析机', '血透机', 'X射线机', 'X光机', 'C形臂', 'C型臂',
        'CT', 'DR', 'MRI', '磁共振', 'PCR', '测序仪', '病理', '眼压计',
    )
    _ZCY_GENERIC_PRODUCT_NAMES = {
        '数量', '采购数量', '设备', '设备一批', '医疗设备', '医疗设备一批', '检验设备', '检测设备',
        '试剂耗材', '耗材', '货物', '产品', '标的', '合同包',
    }


    def _bounded_procurement_demand_scope(text: str) -> str:
        anchor_match = re.search(r'采购需求\s*[：:]\s*', text)
        if not anchor_match:
            return ''
        scope = text[anchor_match.end():]
        end_positions = [
            position
            for marker in (
                '合同履行期限', '合同履约期限', '本项目不接受', '本项目接受',
                '二、申请人的资格要求', '二、申请人',
            )
            if (position := scope.find(marker)) >= 0
        ]
        if end_positions:
            scope = scope[: min(end_positions)]
        scope = _normalize_space(scope)
        return scope if scope and len(scope) <= 4000 else ''


    def _optional_text_product_item(raw_name: str, quantity: str | None) -> dict[str, Any]:
        return {
            'raw_name': _normalize_space(raw_name).strip('，,：:；;。'),
            'category': None,
            'quantity': _normalize_space(quantity) if quantity else None,
            'specification': None,
        }


    def _looks_specific_zcy_product_name(raw_name: str) -> bool:
        name = _normalize_space(raw_name).strip('，,：:；;。')
        if not name or len(name) < 2 or len(name) > 180:
            return False
        if name in _ZCY_GENERIC_PRODUCT_NAMES:
            return False
        if any(token in name for token in ('详见', '采购需求', '预算金额', '最高限价', '项目基本概况', '配置及参数一览表')):
            return False
        if name.endswith(('设备一批', '医疗设备一批', '检测设备', '检验检测设备')):
            return False
        return any(term in name for term in _ZCY_SPECIFIC_PRODUCT_TERMS)


    def _dedupe_optional_product_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str | None]] = set()
        for item in items:
            name = str(item.get('raw_name') or '').strip()
            quantity = item.get('quantity')
            normalized_quantity = str(quantity).strip() if quantity is not None else None
            if not _looks_specific_zcy_product_name(name):
                continue
            if normalized_quantity is not None and not _is_explicit_product_quantity(normalized_quantity):
                continue
            key = (name, normalized_quantity)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
            if len(result) >= 100:
                break
        return result


    def _extract_zcy_primary_subject_items(text: str) -> list[dict[str, Any]]:
        """Parse explicit 政采云正文 pairs: 主要标的名称：X；数量：N单位。"""
        scope = _bounded_procurement_demand_scope(text)
        if not scope:
            return []
        unit_pattern = '|'.join(
            sorted(
                (re.escape(unit) for unit in _PRODUCT_UNIT_WORDS if unit not in {'年', '月', '人', '人次', '家', '所', '间'}),
                key=len,
                reverse=True,
            )
        )
        quantity_pattern = rf'(?:\d+(?:\.\d+)?|[一二三四五六七八九十百]+)\s*(?:{unit_pattern})'
        pattern = re.compile(
            rf'主要标的名称\s*[：:]\s*(?P<name>[^；;]{{2,180}}?)\s*[；;]\s*'
            rf'数量\s*[：:]\s*(?P<quantity>{quantity_pattern})(?=\s*[；;，,。]|$)'
        )
        items = [
            _optional_text_product_item(match.group('name'), match.group('quantity'))
            for match in pattern.finditer(scope)
        ]
        return _dedupe_optional_product_items(items)


    def _extract_zcy_brief_description_items(text: str) -> list[dict[str, Any]]:
        """Parse only product-like facts from bounded 政采云“简要规格描述” blocks."""
        scope = _bounded_procurement_demand_scope(text)
        if not scope:
            return []
        bodies = [
            _normalize_space(match.group('body')).strip('，,：:；;。')
            for match in re.finditer(
                r'简要规格描述或项目基本概况介绍、用途\s*[：:]\s*'
                r'(?P<body>.*?)(?=\s+备注\s*[：:]|\s+标项(?:一|二|三|四|五|六|七|八|九|十|名称)\b|$)',
                scope,
            )
        ]
        if not bodies:
            return []

        unit_pattern = '|'.join(
            sorted(
                (re.escape(unit) for unit in _PRODUCT_UNIT_WORDS if unit not in {'年', '月', '人', '人次', '家', '所', '间'}),
                key=len,
                reverse=True,
            )
        )
        explicit_pattern = re.compile(
            rf'(?P<name>[A-Za-z0-9\u4e00-\u9fff（）()·+\-/]{{2,120}}?)'
            rf'(?P<quantity>\d+(?:\.\d+)?\s*(?:{unit_pattern}))(?=\s*(?:及|和|与|，|,|；|;|。|$))'
        )
        items: list[dict[str, Any]] = []
        for body in bodies:
            if not body or len(body) > 1200 or re.match(r'^\d+[.、]', body):
                continue
            explicit = []
            for match in explicit_pattern.finditer(body[:500]):
                name = match.group('name').strip()
                if _looks_specific_zcy_product_name(name):
                    explicit.append(_optional_text_product_item(name, match.group('quantity')))
            if explicit:
                items.extend(explicit)
                continue

            name = None
            if body.startswith(('采购', '拟采购', '购买')):
                candidate = re.sub(r'^(?:拟采购|采购|购买)', '', body, count=1).strip()
                candidate = re.split(r'[，,](?:\s*详见|\s*具体)', candidate, maxsplit=1)[0].strip()
                name = candidate
            else:
                purchase = re.match(r'(?P<name>.+?)采购(?:[，,]|$)', body)
                if purchase:
                    name = purchase.group('name').strip()
                    name = re.sub(r'^(?:一|二|三|四|五|六|七|八|九|十)标段\s*[：:]\s*', '', name)
            if name and _looks_specific_zcy_product_name(name):
                items.append(_optional_text_product_item(name, None))

        return _dedupe_optional_product_items(items)
    ''')
    text = text.replace(marker, insertion + marker, 1)

    old_scope = dedent('''
    def _extract_bounded_procurement_demand_items(text: str) -> list[dict[str, Any]]:
        """Extract only explicit name+quantity facts from the bounded official 采购需求 paragraph."""
        anchor_match = re.search(r"采购需求\\s*[：:]\\s*", text)
        if not anchor_match:
            return []
        scope = text[anchor_match.end():]
        end_positions = [
            position
            for marker in ("合同履行期限", "本项目不接受", "本项目接受", "二、申请人的资格要求", "二、申请人")
            if (position := scope.find(marker)) >= 0
        ]
        if end_positions:
            scope = scope[: min(end_positions)]
        scope = _normalize_space(scope)
        if not scope or len(scope) > 4000:
            return []
    ''').lstrip('\n')
    new_scope = dedent('''
    def _extract_bounded_procurement_demand_items(text: str) -> list[dict[str, Any]]:
        """Extract only explicit name+quantity facts from the bounded official 采购需求 paragraph."""
        scope = _bounded_procurement_demand_scope(text)
        if not scope:
            return []
    ''').lstrip('\n')
    if old_scope not in text:
        raise RuntimeError('BOUNDED_SCOPE_BLOCK_NOT_FOUND')
    text = text.replace(old_scope, new_scope, 1)

    old_guard = "        if any(token in name for token in ('预算金额', '最高限价', '合同履行', '详见', '具体内容', '采购需求')):\n            return\n"
    new_guard = "        if name in _ZCY_GENERIC_PRODUCT_NAMES or name.startswith(('数量：', '数量:')):\n            return\n        if any(token in name for token in ('预算金额', '最高限价', '合同履行', '合同履约', '详见', '具体内容', '采购需求')):\n            return\n"
    if old_guard not in text:
        raise RuntimeError('ADD_GUARD_NOT_FOUND')
    text = text.replace(old_guard, new_guard, 1)

    old_extractors = dedent('''
        extractors = (
            _extract_bounded_procurement_demand_items,
            _extract_item_name_quantity_unit_lines,
            _extract_product_name_quantity_lines,
            _extract_top_level_numbered_quantity_items,
        )
    ''').lstrip('\n')
    new_extractors = dedent('''
        extractors = (
            _extract_zcy_primary_subject_items,
            _extract_zcy_brief_description_items,
            _extract_bounded_procurement_demand_items,
            _extract_item_name_quantity_unit_lines,
            _extract_product_name_quantity_lines,
            _extract_top_level_numbered_quantity_items,
        )
    ''').lstrip('\n')
    if old_extractors not in text:
        raise RuntimeError('EXTRACTOR_TUPLE_NOT_FOUND')
    text = text.replace(old_extractors, new_extractors, 1)
    text = text.replace("'locator': '采购需求/正文结构化名称与数量清单',", "'locator': '采购需求/正文结构化产品明细',", 1)
    parser_path.write_text(text, encoding='utf-8')

    test_path = Path('web/pipeline/tests/test_ccgp_jilin_zcy_products.py')
    test_path.write_text(dedent(r'''
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

        def pairs(self, items):
            return [(item['raw_name'], item['quantity']) for item in items]

        def test_primary_subject_name_and_quantity_are_grounded(self):
            text = self.wrap(
                '标项名称: 合同包1 数量: 预算金额（元）：5108800 '
                '简要规格描述或项目基本概况介绍、用途： '
                '主要标的名称：血液透析机（单泵）；数量：10台；简要技术需求：用于血液透析； '
                '主要标的名称：三维移动式C形臂X射线机等；数量：1套；简要技术需求：用于骨科手术。 备注：'
            )
            self.assertEqual(
                self.pairs(_extract_zcy_primary_subject_items(text)),
                [('血液透析机（单泵）', '10台'), ('三维移动式C形臂X射线机等', '1套')],
            )
            self.assertEqual(self.pairs(_extract_grounded_text_product_items(text)), self.pairs(_extract_zcy_primary_subject_items(text)))

        def test_quantity_label_is_never_a_product_name(self):
            text = self.wrap('标项名称: 合同包1 数量: 预算金额（元）：5108800 简要规格描述或项目基本概况介绍、用途： 主要标的名称：血液透析机；数量：10台；备注：')
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

        def test_specific_brief_product_without_quantity_keeps_quantity_null(self):
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
                '简要规格描述或项目基本概况介绍、用途： 采购埃可病毒30型核酸检测试剂盒（荧光法）等四大症候群监测相关试剂耗材，详见采购文件 备注：'
            )
            self.assertEqual(
                self.pairs(_extract_zcy_brief_description_items(text)),
                [('埃可病毒30型核酸检测试剂盒（荧光法）等四大症候群监测相关试剂耗材', None)],
            )

        def test_generic_or_technical_brief_remains_empty(self):
            samples = [
                '标项名称: 传染病实验室监测质量提升采购项目 数量: 预算金额（元）：3850000 简要规格描述或项目基本概况介绍、用途： 通化市疾病预防控制中心采购设备一批，详见招标文件第五章采购需求 备注：',
                '标项名称: 检验检测设备 数量: 预算金额（元）：4460400 简要规格描述或项目基本概况介绍、用途： 一标段：四平市产品质量检验院食品、工业产品检验检测设备采购，详见配置及参数一览表； 备注：',
                '标项名称: 小动物超声系统等设备 数量: 预算金额（元）：465000 简要规格描述或项目基本概况介绍、用途： 1.系统需支持云部署及本地部署两种部署方式，用户无需安装桌面端软件可直接登录网址进行实验；等 备注：',
            ]
            for sample in samples:
                with self.subTest(sample=sample):
                    self.assertEqual(_extract_zcy_brief_description_items(self.wrap(sample)), [])


    if __name__ == '__main__':
        unittest.main()
    ''').lstrip('\n'), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
