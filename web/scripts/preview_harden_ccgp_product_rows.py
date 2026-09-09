from pathlib import Path

parser_path = Path('web/pipeline/medical_channel_pipeline/ccgp_detail.py')
text = parser_path.read_text(encoding='utf-8')
anchor = "\ndef _extract_general_product_table_items(html: str) -> list[dict[str, Any]]:\n"
if anchor not in text:
    raise SystemExit('GENERAL_EXTRACTOR_ANCHOR_NOT_FOUND')
if '_is_explicit_product_quantity' in text:
    raise SystemExit('PRODUCT_ROW_HARDENING_ALREADY_PRESENT')

helper = r'''

_PRODUCT_UNIT_WORDS = {
    '台', '套', '项', '个', '条', '批', '组', '件', '盒', '瓶', '包', '支', '份', '张', '辆',
    '本', '册', '人', '人次', '系统', '服务', '年', '月', '次', '家', '所', '间', '种', '片',
    '枚', '把', '部', '床', '位', '台/套', '套/年', '项服务',
}
_PRODUCT_TABLE_FOOTER_PREFIXES = (
    '备注', '注解', '注：', '注:', '合同履行期限', '项目用途', '项目现场', '保险期限', '服务期限',
)


def _is_explicit_product_quantity(value: str | None) -> bool:
    if value is None:
        return False
    normalized = re.sub(r'\s+', '', value).replace('（', '(').replace('）', ')')
    unit_pattern = '|'.join(sorted((re.escape(unit) for unit in _PRODUCT_UNIT_WORDS), key=len, reverse=True))
    return bool(
        re.fullmatch(
            rf'(?:\d+(?:\.\d+)?|[一二三四五六七八九十百]+)(?:\([^()\d]{{1,8}}\)|(?:{unit_pattern}))?',
            normalized,
        )
    )


def _is_product_table_footer_row(row: list[str]) -> bool:
    first = next((_normalize_space(cell) for cell in row if _normalize_space(cell)), '')
    return first.startswith(_PRODUCT_TABLE_FOOTER_PREFIXES)
'''
text = text.replace(anchor, helper + anchor, 1)

old = r'''            required_index = max(name_index, quantity_index)
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
'''
new = r'''            required_index = max(name_index, quantity_index)
            for row in rows[header_index + 1 :]:
                if _is_product_table_footer_row(row):
                    break
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
                    or _is_explicit_product_quantity(raw_name)
                ):
                    continue

                category = _optional_table_value(row, category_index, max_length=200)
                quantity = _optional_table_value(row, quantity_index, max_length=80)
                if not _is_explicit_product_quantity(quantity):
                    continue
                unit = _optional_table_value(row, unit_index, max_length=30)
                if unit_index is not None and unit is not None and _normalize_space(unit) not in _PRODUCT_UNIT_WORDS:
                    continue
                if quantity and unit and unit not in quantity:
                    quantity = f'{quantity}{unit}'
'''
if old not in text:
    raise SystemExit('GENERAL_PRODUCT_ROW_BLOCK_NOT_FOUND')
text = text.replace(old, new, 1)
parser_path.write_text(text, encoding='utf-8')


test_path = Path('web/pipeline/tests/test_ccgp_product_table_variants.py')
test = test_path.read_text(encoding='utf-8')
marker = "\n    def test_unrelated_name_quantity_table_is_not_treated_as_procurement_items(self) -> None:\n"
if marker not in test:
    raise SystemExit('TEST_INSERTION_ANCHOR_NOT_FOUND')
extra = r'''

    def test_colspan_footer_rows_do_not_become_products(self) -> None:
        record = self.parse("""
        <table>
          <tr><th>包号</th><th>品目号</th><th>标的名称</th><th>数量</th><th>单位</th><th>备注</th></tr>
          <tr><td>1</td><td>1-1</td><td>双能X射线骨密度仪</td><td>1</td><td>套</td><td>单一产品</td></tr>
          <tr><td colspan="6">备注：本项目采购标的对应行业为工业</td></tr>
        </table>
        """)
        self.assertEqual([item['raw_name'] for item in record['facts']['product_items']], ['双能X射线骨密度仪'])

    def test_non_quantity_metadata_rows_after_product_rows_are_ignored(self) -> None:
        record = self.parse("""
        <table>
          <tr><th>包号</th><th>品目号</th><th>品目名称</th><th>数量</th><th>预算</th></tr>
          <tr><td>1</td><td>1-1</td><td>医责险采购</td><td>1项</td><td>120</td></tr>
          <tr><td>2</td><td>2-1</td><td>医师险采购</td><td>1项</td><td>110</td></tr>
          <tr><td colspan="2">项目用途</td><td colspan="3">医院服务</td></tr>
          <tr><td colspan="2">项目现场</td><td colspan="3">指定地点</td></tr>
          <tr><td colspan="2">保险期限</td><td colspan="3">1年</td></tr>
        </table>
        """)
        self.assertEqual(
            [item['raw_name'] for item in record['facts']['product_items']],
            ['医责险采购', '医师险采购'],
        )

    def test_quantity_like_value_cannot_be_product_name(self) -> None:
        record = self.parse("""
        <table>
          <tr><th>标的名称</th><th>数量</th><th>简要服务要求</th></tr>
          <tr><td>医疗设备维保服务</td><td>1项服务</td><td>详见采购需求</td></tr>
          <tr><td>1年</td><td>1年</td><td>错误移位的期限行</td></tr>
        </table>
        """)
        self.assertEqual([item['raw_name'] for item in record['facts']['product_items']], ['医疗设备维保服务'])
'''
test = test.replace(marker, extra + marker, 1)
test_path.write_text(test, encoding='utf-8')
print('CCGP product-row hardening staged')
