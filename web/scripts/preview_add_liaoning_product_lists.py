from pathlib import Path

PARSER = Path('web/pipeline/medical_channel_pipeline/ccgp_detail.py')
TEST = Path('web/pipeline/tests/test_ccgp_liaoning_product_lists.py')

source = PARSER.read_text(encoding='utf-8')

marker = '\ndef _apply_structured_html_products(record: dict[str, Any], html: str) -> dict[str, Any]:\n'
if marker not in source:
    raise SystemExit('PARSER_INSERT_MARKER_NOT_FOUND')
if '_extract_grounded_text_product_items' in source:
    raise SystemExit('LIAONING_TEXT_PRODUCT_PARSER_ALREADY_PRESENT')

helper = r'''

def _procurement_text_scope(text: str) -> str:
    anchor = text.find('采购需求')
    return text[anchor:] if anchor >= 0 else ''


def _text_product_item(raw_name: str, quantity: str) -> dict[str, Any]:
    return {
        'raw_name': _normalize_space(raw_name).strip('，,：:；;。'),
        'category': None,
        'quantity': _normalize_space(quantity),
        'specification': None,
    }


def _dedupe_text_product_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        raw_name = str(item.get('raw_name') or '').strip()
        quantity = str(item.get('quantity') or '').strip()
        if not raw_name or not _is_explicit_product_quantity(quantity):
            continue
        if _is_explicit_product_quantity(raw_name) or len(raw_name) > 180:
            continue
        key = (raw_name, quantity)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= 100:
            break
    return deduped


def _extract_top_level_numbered_quantity_items(text: str) -> list[dict[str, Any]]:
    scope = _procurement_text_scope(text)
    if not scope:
        return []
    unit_pattern = '|'.join(sorted((re.escape(unit) for unit in _PRODUCT_UNIT_WORDS), key=len, reverse=True))
    pattern = re.compile(
        rf'(?<![\d.])(?P<index>\d{{1,3}})[.、](?!\d)\s*'
        rf'(?P<name>[^：:\n]{{1,120}}?)\s+'
        rf'(?P<quantity>\d+(?:\.\d+)?\s*(?:{unit_pattern}))\s*'
        rf'(?=[：:★▲]|\d{{1,3}}\.\d|\d{{1,3}}[.、](?!\d)|$)'
    )
    items = [
        _text_product_item(match.group('name'), match.group('quantity'))
        for match in pattern.finditer(scope)
    ]
    return _dedupe_text_product_items(items)


def _normalized_text_lines(text: str) -> list[str]:
    return [_normalize_space(line) for line in text.splitlines() if _normalize_space(line)]


def _find_header_cluster(lines: list[str], required: tuple[str, ...], *, window: int = 8) -> int | None:
    for start, line in enumerate(lines):
        if line != required[0]:
            continue
        cluster = lines[start : start + window]
        if all(value in cluster for value in required[1:]):
            return start + max(cluster.index(value) for value in required)
    return None


def _extract_product_name_quantity_lines(text: str) -> list[dict[str, Any]]:
    scope = _procurement_text_scope(text)
    lines = _normalized_text_lines(scope)
    header_end = _find_header_cluster(lines, ('序号', '产品名称', '数量'), window=7)
    if header_end is None:
        return []

    items: list[dict[str, Any]] = []
    index = header_end + 1
    while index + 2 < len(lines):
        line = lines[index]
        if line.startswith(('合同履行期限', '二、供应商', '三、政府采购供应商', '四、获取')):
            break
        if re.fullmatch(r'\d{1,3}', line):
            raw_name = lines[index + 1]
            quantity = lines[index + 2]
            if (
                1 <= len(raw_name) <= 180
                and not _is_explicit_product_quantity(raw_name)
                and _is_explicit_product_quantity(quantity)
                and re.search(r'\D', quantity)
            ):
                items.append(_text_product_item(raw_name, quantity))
                index += 3
                continue
        index += 1
    return _dedupe_text_product_items(items)


def _extract_item_name_quantity_unit_lines(text: str) -> list[dict[str, Any]]:
    scope = _procurement_text_scope(text)
    lines = _normalized_text_lines(scope)
    header_end = _find_header_cluster(lines, ('品目号', '品目名称', '数量', '计量单位'), window=9)
    if header_end is None:
        return []

    items: list[dict[str, Any]] = []
    index = header_end + 1
    while index + 3 < len(lines):
        line = lines[index]
        if line.startswith(('投标人须以包为单位', '合同履行期限', '★二、交货', '二、供应商', '三、政府采购供应商')):
            break
        if re.fullmatch(r'\d{3}包', line):
            index += 1
            continue
        if re.fullmatch(r'\d{1,3}', line):
            raw_name = lines[index + 1]
            amount = lines[index + 2]
            unit = lines[index + 3]
            if (
                1 <= len(raw_name) <= 180
                and re.fullmatch(r'\d+(?:\.\d+)?', amount)
                and unit in _PRODUCT_UNIT_WORDS
                and not _is_explicit_product_quantity(raw_name)
            ):
                items.append(_text_product_item(raw_name, f'{amount}{unit}'))
                index += 4
                continue
        index += 1
    return _dedupe_text_product_items(items)


def _extract_grounded_text_product_items(text: str) -> list[dict[str, Any]]:
    extractors = (
        _extract_item_name_quantity_unit_lines,
        _extract_product_name_quantity_lines,
        _extract_top_level_numbered_quantity_items,
    )
    for extractor in extractors:
        items = extractor(text)
        if items:
            return items
    return []


def _apply_grounded_text_products(record: dict[str, Any], text: str) -> dict[str, Any]:
    if record['facts'].get('product_items'):
        return record
    items = _extract_grounded_text_product_items(text)
    if not items:
        return record

    record['facts']['product_items'] = items
    record['facts']['product_categories'] = []
    evidence = [
        item for item in record.get('evidence', [])
        if item.get('field_path') not in {'facts.product_items', 'facts.product_categories'}
    ]
    evidence.append(
        {
            'field_path': 'facts.product_items',
            'source_url': record['source']['url'],
            'locator': '采购需求/正文结构化名称与数量清单',
        }
    )
    record['evidence'] = evidence
    return validate_record(record)
'''

source = source.replace(marker, helper + marker, 1)

old_public = '''def parse_ccgp_public_tender_html(\n    html: str,\n    *,\n    source_url: str,\n    observed_at: str,\n    opportunity_id: str,\n) -> dict[str, Any]:\n    record = parse_ccgp_public_tender_text(\n        html_to_text(html),\n        source_url=source_url,\n        observed_at=observed_at,\n        opportunity_id=opportunity_id,\n    )\n    return _apply_structured_html_products(record, html)\n'''
new_public = '''def parse_ccgp_public_tender_html(\n    html: str,\n    *,\n    source_url: str,\n    observed_at: str,\n    opportunity_id: str,\n) -> dict[str, Any]:\n    text = html_to_text(html)\n    record = parse_ccgp_public_tender_text(\n        text,\n        source_url=source_url,\n        observed_at=observed_at,\n        opportunity_id=opportunity_id,\n    )\n    record = _apply_structured_html_products(record, html)\n    return _apply_grounded_text_products(record, text)\n'''
if old_public not in source:
    raise SystemExit('PUBLIC_HTML_BLOCK_NOT_FOUND')
source = source.replace(old_public, new_public, 1)

old_consult = '''def parse_ccgp_competitive_consultation_html(\n    html: str,\n    *,\n    source_url: str,\n    observed_at: str,\n    opportunity_id: str,\n) -> dict[str, Any]:\n    record = parse_ccgp_competitive_consultation_text(\n        html_to_text(html),\n        source_url=source_url,\n        observed_at=observed_at,\n        opportunity_id=opportunity_id,\n    )\n    return _apply_structured_html_products(record, html)\n'''
new_consult = '''def parse_ccgp_competitive_consultation_html(\n    html: str,\n    *,\n    source_url: str,\n    observed_at: str,\n    opportunity_id: str,\n) -> dict[str, Any]:\n    text = html_to_text(html)\n    record = parse_ccgp_competitive_consultation_text(\n        text,\n        source_url=source_url,\n        observed_at=observed_at,\n        opportunity_id=opportunity_id,\n    )\n    record = _apply_structured_html_products(record, html)\n    return _apply_grounded_text_products(record, text)\n'''
if old_consult not in source:
    raise SystemExit('CONSULT_HTML_BLOCK_NOT_FOUND')
source = source.replace(old_consult, new_consult, 1)
PARSER.write_text(source, encoding='utf-8')

TEST.write_text(r'''import unittest

from medical_channel_pipeline.ccgp_detail import _extract_grounded_text_product_items


class LiaoningGroundedProductListTests(unittest.TestCase):
    def test_top_level_numbered_products_ignore_decimal_subparameters(self):
        text = '''采购需求：查看
技术参数要求：1.超声主机 1台：1.1≥18英寸高分辨率显示器 1.2≥11英寸触摸屏 2.超声电子上消化道内窥镜（扇扫） 1条▲2.1视野方向≥45° 2.2视野角≥140° 3.超声电子上消化道内窥镜（环扫） 1条3.1景深≥3-100mm 4.高清电子内窥镜系统 1套4.1、图像处理器4.1.1高清视频输出
★1 交货时间：签订合同后30个工作日。'''
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
        text = '''采购需求：查看
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
合同履行期限：30日'''
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
        text = '''采购需求：查看
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
投标人须以包为单位对包中全部内容进行投标，不得拆分。'''
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
''', encoding='utf-8')

print('LIAONING_PRODUCT_LIST_PATCH_APPLIED')
