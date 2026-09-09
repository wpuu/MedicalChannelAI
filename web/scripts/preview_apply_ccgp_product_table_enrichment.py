#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAIL = ROOT / "pipeline/medical_channel_pipeline/ccgp_detail.py"
TEST = ROOT / "pipeline/tests/test_ccgp_detail.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"PATCH_ANCHOR_NOT_FOUND:{label}")
    if text.count(old) != 1:
        raise SystemExit(f"PATCH_ANCHOR_NOT_UNIQUE:{label}:{text.count(old)}")
    return text.replace(old, new, 1)


detail = DETAIL.read_text(encoding="utf-8")

insert_anchor = '''def _assert_source_url(source_url: str) -> None:\n'''
insert = r'''class _StructuredProductTableParser(HTMLParser):
    """Preserve exact table cell boundaries for official procurement item tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._current_table = []
            return
        if self._table_depth != 1:
            return
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth or self._table_depth != 1 or self._current_cell is None:
            return
        value = data.strip()
        if value:
            self._current_cell.append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if self._table_depth == 1 and tag in {"td", "th"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append(" ".join(self._current_cell).strip())
            self._current_cell = None
            return
        if self._table_depth == 1 and tag == "tr" and self._current_row is not None:
            if self._current_table is not None and any(cell.strip() for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = None
            return
        if tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None
            self._table_depth -= 1


def _normalize_table_header(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("（", "(").replace("）", ")")


def _optional_table_value(row: list[str], index: int | None, *, max_length: int) -> str | None:
    if index is None or index >= len(row):
        return None
    value = _normalize_space(row[index]).strip("，,：:；;。")
    if not value or value in {"-", "—", "/"} or len(value) > max_length:
        return None
    return value


def _extract_standard_product_table_items(html: str) -> list[dict[str, Any]]:
    """Extract only explicit official rows with 品目名称/采购标的/数量（单位） columns."""
    parser = _StructuredProductTableParser()
    parser.feed(html)
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()

    for rows in parser.tables:
        for header_index, header_row in enumerate(rows):
            headers = [_normalize_table_header(cell) for cell in header_row]
            if "品目名称" not in headers or "采购标的" not in headers:
                continue
            quantity_index = next(
                (index for index, header in enumerate(headers) if header in {"数量(单位)", "数量"}),
                None,
            )
            if quantity_index is None:
                continue
            category_index = headers.index("品目名称")
            name_index = headers.index("采购标的")
            specification_index = next(
                (
                    index
                    for index, header in enumerate(headers)
                    if header in {"技术规格、参数及要求", "技术规格参数及要求", "技术要求"}
                ),
                None,
            )
            required_index = max(category_index, name_index, quantity_index)
            for row in rows[header_index + 1 :]:
                if len(row) <= required_index:
                    continue
                raw_name = _optional_table_value(row, name_index, max_length=300)
                if raw_name is None or _normalize_table_header(raw_name) == "采购标的":
                    continue
                category = _optional_table_value(row, category_index, max_length=200)
                quantity = _optional_table_value(row, quantity_index, max_length=80)
                specification = _optional_table_value(row, specification_index, max_length=2000)
                key = (raw_name, category, quantity, specification)
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    {
                        "raw_name": raw_name,
                        "category": category,
                        "quantity": quantity,
                        "specification": specification,
                    }
                )
                if len(items) >= 100:
                    return items
    return items


def _apply_structured_html_products(record: dict[str, Any], html: str) -> dict[str, Any]:
    items = _extract_standard_product_table_items(html)
    if not items:
        return record

    facts = record["facts"]
    facts["product_items"] = items
    categories: list[str] = []
    for item in items:
        category = item.get("category")
        if isinstance(category, str) and category and category not in categories:
            categories.append(category)
    facts["product_categories"] = categories

    evidence = [
        item
        for item in record.get("evidence", [])
        if item.get("field_path") not in {"facts.product_items", "facts.product_categories"}
    ]
    source_url = record["source"]["url"]
    if categories:
        evidence.append(
            {
                "field_path": "facts.product_categories",
                "source_url": source_url,
                "locator": "一、项目基本情况/采购需求/品目表/品目名称",
            }
        )
    evidence.append(
        {
            "field_path": "facts.product_items",
            "source_url": source_url,
            "locator": "一、项目基本情况/采购需求/品目表/采购标的与数量（单位）",
        }
    )
    record["evidence"] = evidence
    return validate_record(record)


'''
detail = replace_once(detail, insert_anchor, insert + insert_anchor, "structured table insertion")

old_public_html = '''def parse_ccgp_public_tender_html(\n    html: str,\n    *,\n    source_url: str,\n    observed_at: str,\n    opportunity_id: str,\n) -> dict[str, Any]:\n    return parse_ccgp_public_tender_text(\n        html_to_text(html),\n        source_url=source_url,\n        observed_at=observed_at,\n        opportunity_id=opportunity_id,\n    )\n'''
new_public_html = '''def parse_ccgp_public_tender_html(\n    html: str,\n    *,\n    source_url: str,\n    observed_at: str,\n    opportunity_id: str,\n) -> dict[str, Any]:\n    record = parse_ccgp_public_tender_text(\n        html_to_text(html),\n        source_url=source_url,\n        observed_at=observed_at,\n        opportunity_id=opportunity_id,\n    )\n    return _apply_structured_html_products(record, html)\n'''
detail = replace_once(detail, old_public_html, new_public_html, "public tender html adapter")

old_consult_html = '''def parse_ccgp_competitive_consultation_html(\n    html: str,\n    *,\n    source_url: str,\n    observed_at: str,\n    opportunity_id: str,\n) -> dict[str, Any]:\n    return parse_ccgp_competitive_consultation_text(\n        html_to_text(html),\n        source_url=source_url,\n        observed_at=observed_at,\n        opportunity_id=opportunity_id,\n    )\n'''
new_consult_html = '''def parse_ccgp_competitive_consultation_html(\n    html: str,\n    *,\n    source_url: str,\n    observed_at: str,\n    opportunity_id: str,\n) -> dict[str, Any]:\n    record = parse_ccgp_competitive_consultation_text(\n        html_to_text(html),\n        source_url=source_url,\n        observed_at=observed_at,\n        opportunity_id=opportunity_id,\n    )\n    return _apply_structured_html_products(record, html)\n'''
detail = replace_once(detail, old_consult_html, new_consult_html, "consultation html adapter")
DETAIL.write_text(detail, encoding="utf-8")


test = TEST.read_text(encoding="utf-8")
old_import = '''from medical_channel_pipeline.ccgp_detail import (\n    CcgpDetailParseError,\n    parse_ccgp_competitive_consultation_text,\n    parse_ccgp_public_tender_text,\n)\n'''
new_import = '''from medical_channel_pipeline.ccgp_detail import (\n    CcgpDetailParseError,\n    parse_ccgp_competitive_consultation_text,\n    parse_ccgp_public_tender_html,\n    parse_ccgp_public_tender_text,\n)\n'''
test = replace_once(test, old_import, new_import, "test import")

class_anchor = '''class CcgpDetailTests(unittest.TestCase):\n'''
fixture = '''STANDARD_PRODUCT_TABLE_HTML_FIXTURE = (\n    "<html><body><pre>"\n    + FIXTURE\n    + "</pre>"\n    + """\n    <table>\n      <tr><th>品目号</th><th>品目名称</th><th>采购标的</th><th>数量（单位）</th><th>技术规格、参数及要求</th><th>品目预算(元)</th></tr>\n      <tr><td>1-1</td><td>医用 X 线诊断设备</td><td>64排螺旋CT设备</td><td>1(台)</td><td>详见采购文件</td><td>5800000</td></tr>\n      <tr><td>1-2</td><td>医用内窥镜</td><td>电子消化道内窥镜系统</td><td>1(套)</td><td>4K成像</td><td>1500000</td></tr>\n    </table>\n    """\n    + "</body></html>"\n)\n\nNON_PRODUCT_TABLE_HTML_FIXTURE = (\n    "<html><body><pre>"\n    + ATTACHMENT_ONLY_FIXTURE\n    + "</pre><table><tr><th>名称</th><th>数量</th></tr><tr><td>附件</td><td>1</td></tr></table></body></html>"\n)\n\n\n'''
test = replace_once(test, class_anchor, fixture + class_anchor, "test fixture insertion")

test_anchor = '''    def test_competitive_consultation_uses_response_submission_deadline_not_opening_time(self) -> None:\n'''
new_tests = '''    def test_official_standard_product_table_is_structured_without_title_guessing(self) -> None:\n        record = parse_ccgp_public_tender_html(\n            STANDARD_PRODUCT_TABLE_HTML_FIXTURE,\n            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260908_27291415.htm",\n            observed_at="2026-09-09T01:55:00+00:00",\n            opportunity_id="standard_product_table",\n        )\n        facts = record["facts"]\n        self.assertEqual(facts["product_categories"], ["医用 X 线诊断设备", "医用内窥镜"])\n        self.assertEqual(len(facts["product_items"]), 2)\n        self.assertEqual(facts["product_items"][0], {\n            "raw_name": "64排螺旋CT设备",\n            "category": "医用 X 线诊断设备",\n            "quantity": "1(台)",\n            "specification": "详见采购文件",\n        })\n        self.assertEqual(facts["product_items"][1]["raw_name"], "电子消化道内窥镜系统")\n        evidence_paths = {item["field_path"] for item in record["evidence"]}\n        self.assertIn("facts.product_items", evidence_paths)\n        self.assertIn("facts.product_categories", evidence_paths)\n\n    def test_unrelated_html_table_does_not_invent_product_items(self) -> None:\n        record = parse_ccgp_public_tender_html(\n            NON_PRODUCT_TABLE_HTML_FIXTURE,\n            source_url="https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/t20260824_27194426.htm",\n            observed_at="2026-09-09T01:55:00+00:00",\n            opportunity_id="non_product_table",\n        )\n        self.assertEqual(record["facts"]["product_items"], [])\n        self.assertEqual(record["facts"]["product_categories"], [])\n\n'''
test = replace_once(test, test_anchor, new_tests + test_anchor, "test insertion")
TEST.write_text(test, encoding="utf-8")

print("CCGP standard product-table parser patch applied")
