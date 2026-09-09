from __future__ import annotations

import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .validation import validate_record

CCGP_HOSTS = {"ccgp.gov.cn", "www.ccgp.gov.cn"}


class CcgpDetailParseError(ValueError):
    pass


class _VisibleTextParser(HTMLParser):
    BLOCK_TAGS = {
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "li",
        "p",
        "section",
        "table",
        "tbody",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


class _StructuredProductTableParser(HTMLParser):
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


def _apply_structured_html_products(record: dict[str, Any], html: str) -> dict[str, Any]:
    items = _extract_standard_product_table_items(html)
    if not items:
        items = _extract_general_product_table_items(html)
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
                "locator": "一、项目基本情况/采购需求/结构化采购表/品目名称",
            }
        )
    evidence.append(
        {
            "field_path": "facts.product_items",
            "source_url": source_url,
            "locator": "一、项目基本情况/采购需求/结构化采购表/标的名称与数量",
        }
    )
    record["evidence"] = evidence
    return validate_record(record)


def _assert_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in CCGP_HOSTS:
        raise CcgpDetailParseError("CCGP_DETAIL_SOURCE_HOST_REJECTED")


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _date_from_cn(year: str, month: str, day: str) -> str:
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _datetime_from_cn(
    year: str,
    month: str,
    day: str,
    hour: str,
    minute: str,
) -> str:
    year_i, month_i, day_i = int(year), int(month), int(day)
    hour_i, minute_i = int(hour), int(minute)
    if hour_i == 24:
        if minute_i != 0:
            raise CcgpDetailParseError("CCGP_TIME_INVALID")
        next_day = datetime(year_i, month_i, day_i) + timedelta(days=1)
        return f"{next_day:%Y-%m-%d}T00:00:00+08:00"
    if not 0 <= hour_i <= 23 or not 0 <= minute_i <= 59:
        raise CcgpDetailParseError("CCGP_TIME_INVALID")
    return f"{year_i:04d}-{month_i:02d}-{day_i:02d}T{hour_i:02d}:{minute_i:02d}:00+08:00"


def _required_match(pattern: str, text: str, code: str, flags: int = 0) -> re.Match[str]:
    match = re.search(pattern, text, flags)
    if not match:
        raise CcgpDetailParseError(code)
    return match


def _extract_project_number(text: str) -> str:
    match = _required_match(
        r"项目编号\s*[：:]\s*([^\s，。；;]+)",
        text,
        "CCGP_PROJECT_NUMBER_NOT_FOUND",
    )
    value = match.group(1).strip()
    return re.sub(r"[)）](?:公开招标|竞争性磋商)公告$", "", value).strip()


def _extract_project_name(text: str) -> str:
    match = _required_match(
        r"项目名称\s*[：:]\s*(.+?)\s+"
        r"(?:采购方式\s*[：:]\s*.+?\s+)?"
        r"预算金额(?:（元）|\(元\))?\s*[：:]",
        text,
        "CCGP_PROJECT_NAME_NOT_FOUND",
        re.S,
    )
    return _normalize_space(match.group(1))


def _extract_buyer(text: str) -> str:
    patterns = [
        r"采购人信息\s+名称\s*[：:]\s*(.+?)\s+地址\s*[：:]",
        r"采购单位\s*[|：:]?\s*(.+?)\s+(?:采购单位地址|行政区域|公告时间)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            return _normalize_space(match.group(1))
    raise CcgpDetailParseError("CCGP_BUYER_NOT_FOUND")


def _extract_region(text: str) -> str | None:
    match = re.search(r"行政区域\s*[|：:]?\s*(.+?)\s+(?:\||公告时间)", text, re.S)
    return _normalize_space(match.group(1)) if match else None


def _extract_publish_date(text: str) -> str:
    patterns = [
        r"发布日期\s*[：:]\s*(20\d{2})年(\d{1,2})月(\d{1,2})日",
        r"公告时间\s*[|：:]?\s*(20\d{2})年(\d{1,2})月(\d{1,2})日",
        r"\b(20\d{2})年(\d{1,2})月(\d{1,2})日\s+\d{1,2}:\d{2}\s+来源",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _date_from_cn(*match.groups())
    raise CcgpDetailParseError("CCGP_PUBLISHED_DATE_NOT_FOUND")


def _extract_registration_deadline(text: str) -> str:
    # Liaoning's official procurement template commonly numbers this as
    # section four and publishes exact start/end datetimes instead of a
    # daily business-hours schedule. Prefer that exact official end time.
    direct_patterns = [
        r"(?:三|四)[、.]\s*获取(?:招标|采购)文件\s+时间\s*[：:]\s*"
        r"20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}\s*(?:时|点)\s*\d{1,2}\s*分?\s*(?:到|至)\s*"
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})\s*(?:时|点)\s*(\d{1,2})\s*分?",
        r"(?:三|四)[、.]\s*获取(?:招标|采购)文件\s+时间\s*[：:]\s*"
        r"20\d{2}年\d{1,2}月\d{1,2}日\s*\d{1,2}\s*[：:]\s*\d{2}\s*(?:到|至)\s*"
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})\s*[：:]\s*(\d{2})",
    ]
    for pattern in direct_patterns:
        direct = re.search(pattern, text, re.S)
        if direct:
            return _datetime_from_cn(*direct.groups())

    patterns = [
        r"(?:三|四)[、.]\s*获取(?:招标|采购)文件\s+时间\s*[：:]\s*"
        r"20\d{2}年\d{1,2}月\d{1,2}日\s*(?:到|至)\s*"
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日"
        r"(.+?)(?:地点\s*[：:]|(?:四|五)[、.])",
        r"(?:三|四)[、.]\s*获取(?:招标|采购)文件\s+时间\s*[：:]\s*"
        r"20\d{2}-\d{1,2}-\d{1,2}\s*(?:到|至)\s*"
        r"(20\d{2})-(\d{1,2})-(\d{1,2})"
        r"(.+?)(?:地点\s*[：:]|(?:四|五)[、.])",
    ]
    section = None
    for pattern in patterns:
        section = re.search(pattern, text, re.S)
        if section:
            break
    if not section:
        raise CcgpDetailParseError("CCGP_REGISTRATION_SECTION_NOT_FOUND")
    year, month, day, schedule = section.groups()

    if "下午" in schedule:
        afternoon_schedule = schedule.rsplit("下午", 1)[1]
        afternoon_times = re.findall(r"至\s*(\d{1,2})\s*[：:]\s*(\d{2})", afternoon_schedule)
        if not afternoon_times:
            raise CcgpDetailParseError("CCGP_REGISTRATION_END_TIME_NOT_FOUND")
        hour, minute = afternoon_times[-1]
    else:
        times = re.findall(r"至\s*(\d{1,2})\s*[：:]\s*(\d{2})", schedule)
        if not times:
            raise CcgpDetailParseError("CCGP_REGISTRATION_END_TIME_NOT_FOUND")
        hour, minute = times[-1]
    return _datetime_from_cn(year, month, day, hour, minute)

def _extract_bid_deadline(text: str) -> str:
    prefix = (
        r"(?:四|五)[、.]\s*提交投标文件截止时间、开标时间和地点\s*"
        r"(?:(?:提交投标文件截止时间|截止时间)\s*[：:]\s*)?"
    )
    patterns = [
        prefix
        + r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*"
        + r"(\d{1,2})\s*(?:点|时)\s*(\d{1,2})\s*分(?:\s*\d{1,2}\s*秒)?",
        prefix
        + r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*"
        + r"(\d{1,2})\s*[：:]\s*(\d{2})(?:\s*[：:]\s*\d{2})?",
        prefix
        + r"(20\d{2})-(\d{1,2})-(\d{1,2})\s+"
        + r"(\d{1,2})\s*[：:]\s*(\d{2})(?:\s*[：:]\s*\d{2})?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            return _datetime_from_cn(*match.groups())
    raise CcgpDetailParseError("CCGP_BID_DEADLINE_NOT_FOUND")


def _extract_response_deadline(text: str) -> str:
    prefix = r"四[、.]\s*响应文件提交\s+截止时间\s*[：:]\s*"
    patterns = [
        prefix
        + r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*"
        + r"(\d{1,2})\s*(?:点|时)\s*(\d{1,2})\s*分(?:\s*\d{1,2}\s*秒)?",
        prefix
        + r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*"
        + r"(\d{1,2})\s*[：:]\s*(\d{2})(?:\s*[：:]\s*\d{2})?",
        prefix
        + r"(20\d{2})-(\d{1,2})-(\d{1,2})\s+"
        + r"(\d{1,2})\s*[：:]\s*(\d{2})(?:\s*[：:]\s*\d{2})?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            return _datetime_from_cn(*match.groups())
    raise CcgpDetailParseError("CCGP_RESPONSE_DEADLINE_NOT_FOUND")


def _extract_budget_cny(text: str) -> int | None:
    match = re.search(
        r"预算金额\s*[|：:]?\s*[￥¥]?\s*([0-9,]+(?:\.[0-9]+)?)\s*万元",
        text,
    )
    if match:
        return int(round(float(match.group(1).replace(",", "")) * 10_000))
    match = re.search(
        r"预算金额(?:（元）|\(元\))?\s*[|：:]\s*[￥¥]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:元)?",
        text,
    )
    if match:
        return int(round(float(match.group(1).replace(",", ""))))
    return None


def _normalize_public_phone(value: str) -> str | None:
    normalized = _normalize_space(value)
    # Contact facts must fail closed. A non-empty label value that has no
    # plausible telephone digit content (for example a repeated contact name)
    # is not a phone number and must never become a dial target.
    if len(re.findall(r"\d", normalized)) < 5:
        return None
    return normalized


def _extract_contact(text: str) -> dict[str, str | None] | None:
    match = re.search(
        r"3[.、]\s*项目联系方式\s+项目联系人\s*[：:]\s*(.+?)\s+"
        r"(?:电\s*话|联系电话)\s*[：:]\s*([^\s，。；;]+)",
        text,
        re.S,
    )
    if not match:
        match = re.search(
            r"项目联系人\s*[|：:]?\s*(.+?)\s+(?:项目联系电话|联系电话)\s*[|：:]?\s*([^\s，。；;]+)",
            text,
            re.S,
        )
    if not match:
        return None
    return {
        "name": _normalize_space(match.group(1)),
        "title": "项目联系人",
        "phone": _normalize_public_phone(match.group(2)),
        "email": None,
    }


def _extract_package_products(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in re.finditer(
        r"第(?:[一二三四五六七八九十]+|\d+)包\s*[：:]\s*(.+?)(?:的采购|；|;|。)",
        text,
        re.S,
    ):
        name = _normalize_space(match.group(1)).strip("，,：:；;。")
        if not name or len(name) > 500 or name in seen:
            continue
        seen.add(name)
        items.append(
            {
                "raw_name": name,
                "category": None,
                "quantity": None,
                "specification": None,
            }
        )
    return items


def _build_verified_record(
    *,
    source_url: str,
    observed_at: str,
    opportunity_id: str,
    project_number: str,
    project_name: str,
    buyer_name: str,
    region: str | None,
    published_at: str,
    registration_deadline: str,
    bid_deadline: str,
    budget_cny: int | None,
    product_items: list[dict[str, Any]],
    public_contact: dict[str, str | None] | None,
    notice_type: str,
    procurement_method: str,
    deadline_locator: str,
) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "project_number": project_number,
        "project_name": project_name,
        "buyer_name": buyer_name,
        "hospital_name": None,
        "department": None,
        "region": region,
        "lifecycle_state": "BIDDING",
        "notice_type": notice_type,
        "published_at": published_at,
        "registration_deadline": registration_deadline,
        "bid_deadline": bid_deadline,
        "expected_procurement_at": None,
        "expected_procurement_precision": None,
        "budget_cny": budget_cny,
        "procurement_method": procurement_method,
        "product_categories": [],
        "product_items": product_items,
        "public_contact": public_contact,
    }

    evidence_paths: list[tuple[str, str]] = [
        ("facts.project_number", "一、项目基本情况/项目编号"),
        ("facts.project_name", "一、项目基本情况/项目名称"),
        ("facts.buyer_name", "采购人信息/名称"),
        ("facts.lifecycle_state", f"公告类型={notice_type}/确定性生命周期映射"),
        ("facts.notice_type", f"公告类型/{notice_type}"),
        ("facts.published_at", "公告发布日期"),
        ("facts.registration_deadline", "获取采购文件/时间" if procurement_method != "公开招标" else "获取招标文件/时间"),
        ("facts.bid_deadline", deadline_locator),
        ("facts.procurement_method", f"公告类型={notice_type}/确定性采购方式映射"),
    ]
    if region:
        evidence_paths.append(("facts.region", "公告概要/行政区域"))
    if budget_cny is not None:
        evidence_paths.append(("facts.budget_cny", "一、项目基本情况/预算金额"))
    if product_items:
        evidence_paths.append(("facts.product_items", "一、项目基本情况/采购需求/分包设备清单"))
    if public_contact:
        evidence_paths.append(("facts.public_contact", "项目联系方式"))

    record = {
        "schema_version": "0.1",
        "opportunity_id": opportunity_id,
        "source": {
            "source_id": f"ccgp:{project_number}",
            "source_type": "CCGP_NOTICE",
            "url": source_url,
            "observed_at": observed_at,
        },
        "facts": facts,
        "evidence": [
            {"field_path": path, "source_url": source_url, "locator": locator}
            for path, locator in evidence_paths
        ],
    }
    return validate_record(record)


def parse_ccgp_public_tender_text(
    text: str,
    *,
    source_url: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_source_url(source_url)
    normalized = _normalize_space(text.replace("\xa0", " "))
    if "公开招标公告" not in normalized:
        raise CcgpDetailParseError("CCGP_NOTICE_TYPE_NOT_PUBLIC_TENDER")

    return _build_verified_record(
        source_url=source_url,
        observed_at=observed_at,
        opportunity_id=opportunity_id,
        project_number=_extract_project_number(normalized),
        project_name=_extract_project_name(normalized),
        buyer_name=_extract_buyer(normalized),
        region=_extract_region(normalized),
        published_at=_extract_publish_date(normalized),
        registration_deadline=_extract_registration_deadline(normalized),
        bid_deadline=_extract_bid_deadline(normalized),
        budget_cny=_extract_budget_cny(normalized),
        product_items=_extract_package_products(normalized),
        public_contact=_extract_contact(normalized),
        notice_type="公开招标公告",
        procurement_method="公开招标",
        deadline_locator="提交投标文件截止时间、开标时间和地点",
    )


def parse_ccgp_competitive_consultation_text(
    text: str,
    *,
    source_url: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    _assert_source_url(source_url)
    normalized = _normalize_space(text.replace("\xa0", " "))
    if "竞争性磋商公告" not in normalized:
        raise CcgpDetailParseError("CCGP_NOTICE_TYPE_NOT_COMPETITIVE_CONSULTATION")
    method_match = re.search(r"采购方式\s*[：:]\s*竞争性磋商", normalized)
    if not method_match:
        raise CcgpDetailParseError("CCGP_COMPETITIVE_CONSULTATION_METHOD_NOT_FOUND")

    return _build_verified_record(
        source_url=source_url,
        observed_at=observed_at,
        opportunity_id=opportunity_id,
        project_number=_extract_project_number(normalized),
        project_name=_extract_project_name(normalized),
        buyer_name=_extract_buyer(normalized),
        region=_extract_region(normalized),
        published_at=_extract_publish_date(normalized),
        registration_deadline=_extract_registration_deadline(normalized),
        bid_deadline=_extract_response_deadline(normalized),
        budget_cny=_extract_budget_cny(normalized),
        product_items=_extract_package_products(normalized),
        public_contact=_extract_contact(normalized),
        notice_type="竞争性磋商公告",
        procurement_method="竞争性磋商",
        deadline_locator="四、响应文件提交/截止时间",
    )


def parse_ccgp_public_tender_html(
    html: str,
    *,
    source_url: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    record = parse_ccgp_public_tender_text(
        html_to_text(html),
        source_url=source_url,
        observed_at=observed_at,
        opportunity_id=opportunity_id,
    )
    return _apply_structured_html_products(record, html)


def parse_ccgp_competitive_consultation_html(
    html: str,
    *,
    source_url: str,
    observed_at: str,
    opportunity_id: str,
) -> dict[str, Any]:
    record = parse_ccgp_competitive_consultation_text(
        html_to_text(html),
        source_url=source_url,
        observed_at=observed_at,
        opportunity_id=opportunity_id,
    )
    return _apply_structured_html_products(record, html)


def fetch_ccgp_detail_html(source_url: str, *, timeout_seconds: int = 30) -> str:
    _assert_source_url(source_url)
    request = Request(
        source_url,
        headers={
            "User-Agent": "MedicalChannelAI/0.1 (+evidence-first public procurement verification)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"CCGP_DETAIL_HTTP_{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("CCGP_DETAIL_NETWORK_ERROR") from exc


def parse_observed_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
