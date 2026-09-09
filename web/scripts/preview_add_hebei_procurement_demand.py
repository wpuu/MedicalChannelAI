from pathlib import Path

source_path = Path('web/pipeline/medical_channel_pipeline/ccgp_detail.py')
text = source_path.read_text(encoding='utf-8')
anchor = "def _extract_grounded_text_product_items(text: str) -> list[dict[str, Any]]:\n"
if anchor not in text:
    raise SystemExit('HEBEI_INSERT_ANCHOR_NOT_FOUND')
if 'def _extract_bounded_procurement_demand_items' in text:
    raise SystemExit('HEBEI_PARSER_ALREADY_PRESENT')

helper = r'''def _extract_bounded_procurement_demand_items(text: str) -> list[dict[str, Any]]:
    """Extract only explicit name+quantity facts from the bounded official 采购需求 paragraph."""
    anchor_match = re.search(r"采购需求\s*[：:]\s*", text)
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

    unit_pattern = '|'.join(
        sorted(
            (re.escape(unit) for unit in _PRODUCT_UNIT_WORDS if unit not in {'年', '月', '人', '人次', '家', '所', '间'}),
            key=len,
            reverse=True,
        )
    )
    quantity_pattern = rf"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百]+)\s*(?:{unit_pattern})"
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(raw_name: str, quantity: str) -> None:
        name = _normalize_space(raw_name).strip('，,：:；;。')
        name = re.sub(r"^(?:其中)?(?:[A-HＡ-Ｈ]包|包\s*[A-HＡ-Ｈ一二三四五六七八九十0-9]+)\s*[：:]\s*", "", name)
        name = re.sub(r"^(?:拟采购|采购|购买)", "", name).strip()
        name = re.sub(r"采购$", "", name).strip()
        name = re.sub(r"^(?:其中|包括|包含)\s*", "", name).strip()
        if not name or len(name) < 2 or len(name) > 160:
            return
        if any(token in name for token in ('预算金额', '最高限价', '合同履行', '详见', '具体内容', '采购需求')):
            return
        normalized_quantity = _normalize_space(quantity)
        if not _is_explicit_product_quantity(normalized_quantity):
            return
        key = (name, normalized_quantity)
        if key in seen:
            return
        seen.add(key)
        items.append(_text_product_item(name, normalized_quantity))

    # Multi-package wording such as 包1:设备A：预算金额：...、数量：1套，包2:设备B：...、数量：1台。
    package_re = re.compile(
        rf"(?:^|[，,；;])\s*(?:其中)?(?:[A-HＡ-Ｈ]包|包\s*[A-HＡ-Ｈ一二三四五六七八九十0-9]+)\s*[：:]\s*"
        rf"(?P<name>[^；;，,]{{2,180}}?)"
        rf"(?:[：:]\s*预算金额\s*[：:]\s*[^，,；;]{{1,100}})?"
        rf"[、，,]\s*数量\s*[：:]\s*(?P<quantity>{quantity_pattern})"
    )
    consumed: list[tuple[int, int]] = []
    for match in package_re.finditer(scope):
        add(match.group('name'), match.group('quantity'))
        consumed.append(match.span())

    if consumed:
        chars = list(scope)
        for start, end in consumed:
            chars[start:end] = ' ' * (end - start)
        scope = ''.join(chars)

    # Direct bounded statements such as 病理数字化切片扫描仪4套 / 移动床旁DR机采购2台.
    for segment in re.split(r"[；;。]", scope):
        segment = _normalize_space(segment).strip('，,：:；;。')
        if not segment or segment.startswith(('详见', '具体内容')):
            continue
        # Ignore explicit service/package descriptions without a quantity in this first strict variant.
        direct = re.search(rf"(?P<name>.+?)(?P<quantity>{quantity_pattern})(?=$|[，,、])", segment)
        if direct:
            raw_name = direct.group('name')
            # If unrelated prose precedes the product after a comma, use only the final bounded clause.
            raw_name = re.split(r"[，,]", raw_name)[-1]
            add(raw_name, direct.group('quantity'))

    return items[:100]


'''
text = text.replace(anchor, helper + anchor, 1)
old_tuple = "    extractors = (\n        _extract_item_name_quantity_unit_lines,\n"
new_tuple = "    extractors = (\n        _extract_bounded_procurement_demand_items,\n        _extract_item_name_quantity_unit_lines,\n"
if old_tuple not in text:
    raise SystemExit('HEBEI_EXTRACTOR_TUPLE_ANCHOR_NOT_FOUND')
text = text.replace(old_tuple, new_tuple, 1)
source_path.write_text(text, encoding='utf-8')


test_path = Path('web/pipeline/tests/test_ccgp_hebei_product_demand.py')
test_path.write_text(r'''from __future__ import annotations

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
''', encoding='utf-8')
print('staged Hebei bounded procurement-demand parser and tests')
