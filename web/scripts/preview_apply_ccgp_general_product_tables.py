from pathlib import Path

parser_path = Path('web/pipeline/medical_channel_pipeline/ccgp_detail.py')
text = parser_path.read_text(encoding='utf-8')
marker = '\n\ndef _apply_structured_html_products(record: dict[str, Any], html: str) -> dict[str, Any]:\n'
if marker not in text:
    raise SystemExit('APPLY_MARKER_NOT_FOUND')
if '_SpanningProductTableParser' in text:
    raise SystemExit('GENERAL_PRODUCT_TABLE_PATCH_ALREADY_PRESENT')

insert = r'''

class _SpanningProductTableParser(HTMLParser):
    """Capture table cells plus rowspan/colspan so official merged rows can be reconstructed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, int, int]]]] = []
        self._table_depth = 0
        self._current_table: list[list[tuple[str, int, int]]] | None = None
        self._current_row: list[tuple[str, int, int]] | None = None
        self._current_cell: list[str] | None = None
        self._current_rowspan = 1
        self._current_colspan = 1
        self._ignored_depth = 0

    @staticmethod
    def _span(attrs: list[tuple[str, str | None]], name: str) -> int:
        raw = next((value for key, value in attrs if key.lower() == name), None)
        try:
            value = int(raw or '1')
        except ValueError:
            return 1
        return value if 1 <= value <= 100 else 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {'script', 'style'}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == 'table':
            self._table_depth += 1
            if self._table_depth == 1:
                self._current_table = []
            return
        if self._table_depth != 1:
            return
        if tag == 'tr':
            self._current_row = []
        elif tag in {'td', 'th'} and self._current_row is not None:
            self._current_cell = []
            self._current_rowspan = self._span(attrs, 'rowspan')
            self._current_colspan = self._span(attrs, 'colspan')

    def handle_data(self, data: str) -> None:
        if self._ignored_depth or self._table_depth != 1 or self._current_cell is None:
            return
        value = data.strip()
        if value:
            self._current_cell.append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {'script', 'style'}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if self._table_depth == 1 and tag in {'td', 'th'} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append(
                    (' '.join(self._current_cell).strip(), self._current_rowspan, self._current_colspan)
                )
            self._current_cell = None
            self._current_rowspan = 1
            self._current_colspan = 1
            return
        if self._table_depth == 1 and tag == 'tr' and self._current_row is not None:
            if self._current_table is not None and self._current_row:
                self._current_table.append(self._current_row)
            self._current_row = None
            return
        if tag == 'table' and self._table_depth:
            if self._table_depth == 1 and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None
            self._table_depth -= 1


def _expand_spanning_table_rows(
    rows: list[list[tuple[str, int, int]]],
) -> list[list[str]]:
    expanded: list[list[str]] = []
    active: dict[int, tuple[int, str]] = {}

    for source_row in rows:
        row: list[str] = []
        future: dict[int, tuple[int, str]] = {}
        column = 0

        def consume_active() -> bool:
            nonlocal column
            span = active.get(column)
            if span is None:
                return False
            remaining, value = span
            row.append(value)
            if remaining > 1:
                future[column] = (remaining - 1, value)
            column += 1
            return True

        for value, rowspan, colspan in source_row:
            while consume_active():
                pass
            placed = 0
            while placed < colspan:
                while consume_active():
                    pass
                row.append(value)
                if rowspan > 1:
                    future[column] = (rowspan - 1, value)
                column += 1
                placed += 1

        max_active = max(active, default=-1)
        while column <= max_active:
            if consume_active():
                continue
            row.append('')
            column += 1

        if any(cell.strip() for cell in row):
            expanded.append(row)
        active = future

    return expanded


def _find_general_product_name_index(headers: list[str]) -> int | None:
    exact_names = {'采购标的', '标的名称', '设备名称', '货物名称', '维保设备名称'}
    for index, header in enumerate(headers):
        if header in exact_names or header.endswith('设备名称') or header.endswith('货物名称'):
            return index
    return headers.index('品目名称') if '品目名称' in headers else None


def _extract_general_product_table_items(html: str) -> list[dict[str, Any]]:
    """Parse explicit procurement rows across official CCGP table-header variants only."""
    parser = _SpanningProductTableParser()
    parser.feed(html)
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()

    for raw_rows in parser.tables:
        rows = _expand_spanning_table_rows(raw_rows)
        for header_index, header_row in enumerate(rows[:6]):
            headers = [_normalize_table_header(cell) for cell in header_row]
            name_index = _find_general_product_name_index(headers)
            quantity_index = next(
                (
                    index
                    for index, header in enumerate(headers)
                    if '数量' in header and '预算' not in header
                ),
                None,
            )
            if name_index is None or quantity_index is None:
                continue

            unit_index = next((index for index, header in enumerate(headers) if header == '单位'), None)
            category_index = None
            if '品目名称' in headers:
                candidate = headers.index('品目名称')
                if candidate != name_index:
                    category_index = candidate
            specification_index = next(
                (
                    index
                    for index, header in enumerate(headers)
                    if (
                        ('简要' in header and ('技术' in header or '服务' in header))
                        or header in {'技术要求', '技术规格参数及要求'}
                    )
                ),
                None,
            )
            required_index = max(name_index, quantity_index)
            for row in rows[header_index + 1 :]:
                if len(row) <= required_index:
                    continue
                raw_name = _optional_table_value(row, name_index, max_length=300)
                if raw_name is None:
                    continue
                normalized_name = _normalize_table_header(raw_name)
                if (
                    normalized_name in {'采购标的', '标的名称', '设备名称', '货物名称', '维保设备名称', '品目名称'}
                    or re.fullmatch(r'\d+(?:[-.]\d+)*', normalized_name)
                    or normalized_name in {'是', '否', '服务', '货物'}
                ):
                    continue

                category = _optional_table_value(row, category_index, max_length=200)
                quantity = _optional_table_value(row, quantity_index, max_length=80)
                unit = _optional_table_value(row, unit_index, max_length=30)
                if quantity and unit and unit not in quantity:
                    quantity = f'{quantity}{unit}'
                specification = _optional_table_value(row, specification_index, max_length=2000)
                key = (raw_name, category, quantity, specification)
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    {
                        'raw_name': raw_name,
                        'category': category,
                        'quantity': quantity,
                        'specification': specification,
                    }
                )
                if len(items) >= 100:
                    return items
            if items:
                return items
    return items
'''

text = text.replace(marker, insert + marker, 1)
old = '    items = _extract_standard_product_table_items(html)\n    if not items:\n        return record\n'
new = '    items = _extract_standard_product_table_items(html)\n    if not items:\n        items = _extract_general_product_table_items(html)\n    if not items:\n        return record\n'
if old not in text:
    raise SystemExit('APPLY_BODY_NOT_FOUND')
text = text.replace(old, new, 1)
text = text.replace('一、项目基本情况/采购需求/品目表/品目名称', '一、项目基本情况/采购需求/结构化采购表/品目名称')
text = text.replace('一、项目基本情况/采购需求/品目表/采购标的与数量（单位）', '一、项目基本情况/采购需求/结构化采购表/标的名称与数量')
parser_path.write_text(text, encoding='utf-8')


test_path = Path('web/pipeline/tests/test_ccgp_product_table_variants.py')
test_path.write_text(r'''from __future__ import annotations

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
        record = self.parse('''
        <table>
          <tr><th>设备名称</th><th>数量（套）</th><th>简要技术要求</th><th>备注</th></tr>
          <tr><td>乳腺机</td><td>1</td><td>用于乳腺疾病筛查及诊断</td><td>不允许进口</td></tr>
        </table>
        ''')
        self.assertEqual(record['facts']['product_items'], [{
            'raw_name': '乳腺机', 'category': None, 'quantity': '1', 'specification': '用于乳腺疾病筛查及诊断'
        }])

    def test_mark_name_with_separate_unit_is_combined(self) -> None:
        record = self.parse('''
        <table>
          <tr><th>包号</th><th>品目号</th><th>标的名称</th><th>数量</th><th>单位</th><th>备注</th></tr>
          <tr><td>1</td><td>1-1</td><td>双能X射线骨密度仪</td><td>1</td><td>套</td><td>单一产品</td></tr>
        </table>
        ''')
        item = record['facts']['product_items'][0]
        self.assertEqual(item['raw_name'], '双能X射线骨密度仪')
        self.assertEqual(item['quantity'], '1套')

    def test_rowspan_is_expanded_without_shifting_later_product_names(self) -> None:
        record = self.parse('''
        <table>
          <tr><th>序号</th><th>货物名称</th><th>数量</th><th>单位</th><th>简要技术需求</th><th>是否接受进口</th></tr>
          <tr><td rowspan="3">1</td><td>离心机</td><td>3</td><td>台</td><td rowspan="3">详见采购需求</td><td>否</td></tr>
          <tr><td>全自动干式生化分析仪</td><td>1</td><td>台</td><td>否</td></tr>
          <tr><td>生物显微镜</td><td>1</td><td>台</td><td>否</td></tr>
        </table>
        ''')
        items = record['facts']['product_items']
        self.assertEqual([item['raw_name'] for item in items], ['离心机', '全自动干式生化分析仪', '生物显微镜'])
        self.assertEqual([item['quantity'] for item in items], ['3台', '1台', '1台'])
        self.assertTrue(all(item['specification'] == '详见采购需求' for item in items))

    def test_item_name_can_be_product_name_when_no_distinct_mark_column_exists(self) -> None:
        record = self.parse('''
        <table>
          <tr><th>包号</th><th>品目号</th><th>品目名称</th><th>数量（台/套）</th><th>备注</th></tr>
          <tr><td>1</td><td>1-1</td><td>X射线计算机体层摄影设备（CT）</td><td>1</td><td>单一产品</td></tr>
        </table>
        ''')
        item = record['facts']['product_items'][0]
        self.assertEqual(item['raw_name'], 'X射线计算机体层摄影设备（CT）')
        self.assertIsNone(item['category'])
        self.assertEqual(item['quantity'], '1')

    def test_item_name_remains_category_when_distinct_procurement_mark_exists(self) -> None:
        record = self.parse('''
        <table>
          <tr><th>品目名称</th><th>采购标的</th><th>数量（单位）</th><th>技术要求</th></tr>
          <tr><td>医用X线诊断设备</td><td>64排螺旋CT设备</td><td>1(台)</td><td>详见采购文件</td></tr>
        </table>
        ''')
        item = record['facts']['product_items'][0]
        self.assertEqual(item['raw_name'], '64排螺旋CT设备')
        self.assertEqual(item['category'], '医用X线诊断设备')

    def test_unrelated_name_quantity_table_is_not_treated_as_procurement_items(self) -> None:
        record = self.parse('''
        <table><tr><th>名称</th><th>数量</th></tr><tr><td>附件</td><td>1</td></tr></table>
        ''')
        self.assertEqual(record['facts']['product_items'], [])
        self.assertEqual(record['facts']['product_categories'], [])


if __name__ == '__main__':
    unittest.main()
''', encoding='utf-8')

print('general CCGP product-table parser patch staged')
