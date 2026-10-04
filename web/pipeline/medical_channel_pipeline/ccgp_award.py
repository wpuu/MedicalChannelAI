"""CCGP 中标 / 成交 结果公告 parser (award results).

Award notices close the lifecycle of a procurement and are the only public
source that names the winning supplier together with brand / model / unit
price. They are parsed into *award records* which are deliberately a separate
record type from opportunity records:

* an award is never an actionable "opportunity" (the bidding is over), so it
  must never enter the Today cards / opportunity pool as PUBLIC_OPPORTUNITY;
* it *does* close the matching opportunity (same market + project number),
  and it feeds the brand x model x price evidence ledger.

Everything here is fail-closed: a notice that does not expose a project
number, a project name, a buyer, a publication date and at least one package
result (supplier + amount, or an explicit 废标/终止 reason) raises
``CcgpAwardParseError`` and is reported, never guessed.

Formats verified against live pages on 2026-09-29:

* Tianjin sub-site mirror (天津分网, e.g. XCSD-2026-A-535 / -589,
  0615-2641031970921): per-package ``<table>`` blocks headed
  ``供应商名称 | 供应商地址 | 统一社会信用代码 | 企业办公电话 | 中标金额(万元) | 评审得分``
  and ``类型 | 名称 | 品牌 | 规格型号 | 数量 | 单价(万元)``, preceded by a
  ``第N包 ：`` line;
* national template (e.g. CQS26A01493): text lines ``包号：1`` /
  ``供应商名称：…`` / ``中标（成交）金额： 10,727,000.00元`` (or
  ``废标（终止）原因：…``) and per-package tables
  ``名称 | 品牌 | 规格型号 | 数量 | 单价`` with ``元`` suffixed values.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from .ccgp_detail import _expand_spanning_table_rows, html_to_text
from .channel_scope import is_medical_channel_relevant_record
from .legal_windows import legal_windows_for_facts

CCGP_HOSTS = {"ccgp.gov.cn", "www.ccgp.gov.cn"}
AWARD_RECORD_TYPE = "AWARD_RESULT"
AWARD_LIFECYCLE_STATE = "AWARDED"
RESULT_KINDS = {"AWARD", "DEAL"}
PACKAGE_STATUSES = {"AWARDED", "FAILED"}
AMOUNT_BASES = {"SUMMARY_TOTAL", "PACKAGE_SUM"}
MAX_PACKAGES = 60
MAX_ITEMS = 120
MAX_TEXT = 300

_RESULT_TITLE_MARKERS = (
    "中标（成交）结果公告",
    "中标(成交)结果公告",
    "中标结果公告",
    "成交结果公告",
    "中标公告",
    "成交公告",
)
_DEAL_MARKERS = ("成交公告", "成交结果公告", "成交信息", "成交供应商", "成交金额")


class CcgpAwardParseError(ValueError):
    pass


# --------------------------------------------------------------------------- #
# Sequential document model: text blocks and tables in page order
# --------------------------------------------------------------------------- #
class _TableFrame:
    __slots__ = ("rows", "row", "cell", "rowspan", "colspan", "wrapper")

    def __init__(self) -> None:
        self.rows: list[list[tuple[str, int, int]]] = []
        self.row: list[tuple[str, int, int]] | None = None
        self.cell: list[str] | None = None
        self.rowspan = 1
        self.colspan = 1
        # A table that contains another table is a layout wrapper: its cell
        # text is emitted as ordinary text blocks so package labels such as
        # ``第1包 ：`` keep their position relative to the nested data tables.
        self.wrapper = False


class _AwardDocumentParser(HTMLParser):
    """Emit ``("text", line)`` and ``("table", rows)`` blocks in document order.

    Nested tables are supported because the Tianjin sub-site mirror wraps the
    whole notice body in one outer ``<table>`` cell; the innermost tables are
    materialised as tables, wrapper tables become text flow.
    """

    BLOCK_TAGS = {
        "article", "br", "div", "h1", "h2", "h3", "h4", "h5", "li", "p", "section",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, Any]] = []
        self._text: list[str] = []
        self._ignored_depth = 0
        self._frames: list[_TableFrame] = []

    @staticmethod
    def _span(attrs: list[tuple[str, str | None]], name: str) -> int:
        raw = next((value for key, value in attrs if key.lower() == name), None)
        try:
            value = int(raw or "1")
        except ValueError:
            return 1
        return value if 1 <= value <= 100 else 1

    def _emit_text(self, parts: list[str]) -> None:
        value = re.sub(r"\s+", " ", "".join(parts)).strip()
        if value:
            self.blocks.append(("text", value))

    def _flush_text(self) -> None:
        parts, self._text = self._text, []
        self._emit_text(parts)

    @staticmethod
    def _close_row(frame: _TableFrame) -> None:
        if frame.row is None:
            return
        if not frame.wrapper and frame.row:
            frame.rows.append(frame.row)
        frame.row = None

    def _promote_to_wrapper(self, frame: _TableFrame) -> None:
        if frame.wrapper:
            return
        frame.wrapper = True
        for row in frame.rows:
            for value, _, _ in row:
                self._emit_text([value])
        frame.rows = []
        if frame.row is not None:
            for value, _, _ in frame.row:
                self._emit_text([value])
            frame.row = []
        if frame.cell is not None:
            self._emit_text(frame.cell)
            frame.cell = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "table":
            if self._frames:
                self._promote_to_wrapper(self._frames[-1])
            else:
                self._flush_text()
            self._frames.append(_TableFrame())
            return
        if not self._frames:
            if tag in self.BLOCK_TAGS:
                self._flush_text()
            return
        frame = self._frames[-1]
        if tag == "tr":
            self._close_row(frame)
            frame.row = []
        elif tag in {"td", "th"}:
            if frame.row is None:
                # The national result template emits header <th> cells
                # directly under <table>; browsers synthesise the row.
                frame.row = []
            frame.cell = []
            frame.rowspan = self._span(attrs, "rowspan")
            frame.colspan = self._span(attrs, "colspan")
        elif frame.wrapper and frame.cell is not None and tag in self.BLOCK_TAGS:
            parts, frame.cell = frame.cell, []
            self._emit_text(parts)
        elif tag == "br" and frame.cell is not None:
            frame.cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if not self._frames:
            self._text.append(data)
            return
        frame = self._frames[-1]
        if frame.cell is not None:
            frame.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if not self._frames:
            if tag in self.BLOCK_TAGS:
                self._flush_text()
            return
        frame = self._frames[-1]
        if tag in {"td", "th"} and frame.cell is not None:
            if frame.wrapper:
                parts, frame.cell = frame.cell, None
                self._emit_text(parts)
            else:
                value = re.sub(r"\s+", " ", "".join(frame.cell)).strip()
                if frame.row is not None:
                    frame.row.append((value, frame.rowspan, frame.colspan))
                frame.cell = None
            frame.rowspan = 1
            frame.colspan = 1
            return
        if tag == "tr" and frame.row is not None:
            self._close_row(frame)
            return
        if frame.wrapper and frame.cell is not None and tag in self.BLOCK_TAGS:
            parts, frame.cell = frame.cell, []
            self._emit_text(parts)
            return
        if tag == "table":
            self._close_row(frame)
            self._frames.pop()
            if not frame.wrapper:
                rows = _expand_spanning_table_rows(frame.rows)
                if rows:
                    self.blocks.append(("table", rows))

    def close(self) -> None:  # pragma: no cover - trivial
        super().close()
        self._flush_text()


def _document_blocks(html: str) -> list[tuple[str, Any]]:
    parser = _AwardDocumentParser()
    parser.feed(html.replace("\xa0", " "))
    parser.close()
    return parser.blocks


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean(value: Any, *, max_length: int = MAX_TEXT) -> str | None:
    if value is None:
        return None
    text = _normalize_space(str(value)).strip("，,：:；;。 ")
    if not text or text in {"-", "—", "/", "无"}:
        return None
    return text[:max_length]


def _assert_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in CCGP_HOSTS:
        raise CcgpAwardParseError("CCGP_AWARD_SOURCE_HOST_REJECTED")


def _header_key(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("（", "(").replace("）", ")")


def _find_header_index(headers: list[str], *needles: str, exclude: tuple[str, ...] = ()) -> int | None:
    """First column whose header contains any needle (needles tried in order,
    so specific labels win over generic ones); ``exclude`` drops columns such
    as ``供应商名称`` when the generic needle is just ``名称``."""
    keys = [_header_key(header) for header in headers]
    for needle in needles:
        for index, key in enumerate(keys):
            if needle in key and not any(item in key for item in exclude):
                return index
    return None


_ITEM_NAME_EXCLUDE = ("供应商", "采购人", "代理", "联系人", "项目名称")


def _item_name_index(headers: list[str]) -> int | None:
    # 黑龙江: ``品目号 | 品目名称 | 采购标的 | 品牌 | …`` — the product is 采购标的,
    # 品目名称 is the catalogue category.
    return _find_header_index(
        headers,
        "标的名称", "货物名称", "产品名称", "服务名称", "工程名称", "采购标的", "名称",
        exclude=_ITEM_NAME_EXCLUDE + ("品目名称",),
    )


# Amount text: ``1,395``, ``237.5万元``, ``10,727,000.00元`` or the national
# text template's ``182.0000000（万元）`` (unit in parentheses after the number).
_AMOUNT_RE = re.compile(r"(?:[￥¥]\s*)?((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)\s*(万元|元|（万元）|（元）|\(万元\)|\(元\))?(?:\s*(?:（人民币）|\(人民币\)))?")
AWARD_EVIDENCE_VERSION = "EXPLICIT_CNY_SCOPE_V1"

def _parse_amount_cny(value: str | None, *, header_hint: str | None = None) -> int | None:
    """Parse ``237.5`` (with a 万元 header), ``1,395`` or ``10,727,000.00元``.

    Returns whole CNY (int) or ``None`` when the text is not a plain number.
    A value is only scaled by 10,000 when the unit is explicit, either as a
    suffix on the value itself or as ``(万元)`` in the column header.
    """
    if value is None:
        return None
    text = _normalize_space(str(value))
    match = _AMOUNT_RE.fullmatch(text)
    if match is None:
        # Either no number or several (``46.8万元； 14.8万元； …``): a single
        # monetary fact cannot be attributed, keep the raw text only.
        return None
    number = float(match.group(1).replace(",", ""))
    unit = match.group(2)
    if unit:
        unit = unit.strip("（）()")
    header_unit = None
    if header_hint:
        key = _header_key(header_hint)
        if "%" in key or "％" in key:
            return None
        annotations = re.findall(r"[（(]([^（）()]+)[）)]", str(header_hint))
        money_units = [_normalize_space(label) for label in annotations if "元" in label]
        if money_units:
            if any(label not in {"元", "万元"} for label in money_units) or len(set(money_units)) != 1:
                return None
            header_unit = money_units[0]
        elif "元" in key:
            # Plain suffixes must follow a money-column label. Never interpret
            # 美元/港元/亿元/千元 or another unsupported currency/scale as 元.
            plain = re.fullmatch(r"(?:.*(?:金额|单价|总价|报价))?(万元|元)", key)
            if plain is None:
                return None
            header_unit = plain.group(1)
    if unit and header_unit and unit != header_unit:
        return None
    unit = unit or header_unit
    if unit is None:
        return None
    if unit == "万元":
        number *= 10_000
    if not math.isfinite(number) or number < 0:
        return None
    return int(round(number))


def _package_no_from_text(text: str) -> str | None:
    # 包号：1 (national) / 包组编号：002 (辽宁) / 合同包1(…) (黑龙江)
    match = re.search(r"包(?:组)?(?:编)?号\s*[：:]\s*([A-Za-z0-9\-]+)", text)
    if match:
        return match.group(1)
    match = re.match(r"^合同包\s*([A-Za-z0-9\-]+)", text)
    if match:
        return match.group(1)
    match = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*(?:分)?包", text)
    if match:
        return match.group(1)
    if re.match(r"^(?:标段|标项|分标|子包)\s*[：:]?\s*([A-Za-z0-9\-]+)", text):
        return re.match(r"^(?:标段|标项|分标|子包)\s*[：:]?\s*([A-Za-z0-9\-]+)", text).group(1)
    return None


# --------------------------------------------------------------------------- #
# Field extraction from flattened text
# --------------------------------------------------------------------------- #
_PROJECT_NUMBER_CHARS = r"[^\s，。；;（()）]+"


def _extract_project_number(text: str, title: str | None) -> str:
    # Prefer the numbered body line (一、项目编号：…) over the title, whose
    # ``(项目编号:XCSD-2026-A-535)中标公告`` suffix would otherwise leak into
    # the value. Closing brackets are excluded from the value characters.
    patterns = [
        r"一[、.]\s*项目(?:编号|号)\s*[：:]\s*(" + _PROJECT_NUMBER_CHARS + ")",
        r"采购项目编号\s*[：:]\s*(" + _PROJECT_NUMBER_CHARS + ")",
        r"项目(?:编号|号)\s*[：:]\s*(" + _PROJECT_NUMBER_CHARS + ")",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = re.sub(r"(?:中标|成交|结果)?公告$", "", match.group(1).strip())
            if value:
                return value
    if title:
        match = re.search(r"项目编号\s*[：:]\s*(" + _PROJECT_NUMBER_CHARS + ")", title)
        if match:
            return match.group(1).strip()
    raise CcgpAwardParseError("CCGP_AWARD_PROJECT_NUMBER_NOT_FOUND")


def _extract_project_name(text: str, summary: dict[str, str]) -> str:
    match = re.search(r"二[、.]\s*项目名称\s*[：:]\s*(.+?)(?=\s+三[、.]|\s+采购方式|\s+项目联系人|$)", text, re.S)
    if match:
        name = _clean(match.group(1))
        if name:
            return name
    summary_name = _clean(summary.get("采购项目名称"))
    if summary_name:
        return summary_name
    raise CcgpAwardParseError("CCGP_AWARD_PROJECT_NAME_NOT_FOUND")


def _extract_buyer(text: str, summary: dict[str, str]) -> str:
    summary_buyer = _clean(summary.get("采购单位"))
    if summary_buyer:
        return summary_buyer
    patterns = [
        r"1[.、]\s*采购人信息\s+名\s*称\s*[：:]\s*(.+?)\s+地\s*址\s*[：:]",
        r"采购人\s*[：:]\s*(.+?)\s+(?:采购经办人|采购人电话|采购人地址|地址)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            buyer = _clean(match.group(1))
            if buyer:
                return buyer
    raise CcgpAwardParseError("CCGP_AWARD_BUYER_NOT_FOUND")


def _extract_published_at(text: str, summary: dict[str, str]) -> str:
    patterns = [
        r"发布日期\s*[：:]\s*(20\d{2})年(\d{1,2})月(\d{1,2})日",
        r"公告时间\s*[|：:]?\s*(20\d{2})年(\d{1,2})月(\d{1,2})日",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    summary_time = summary.get("公告时间")
    if summary_time:
        match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", summary_time)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    raise CcgpAwardParseError("CCGP_AWARD_PUBLISHED_DATE_NOT_FOUND")


def _extract_procurement_method(text: str) -> str | None:
    match = re.search(r"采购方式\s*[：:]\s*(公开招标|邀请招标|竞争性磋商|竞争性谈判|询价|单一来源|框架协议)", text)
    return match.group(1) if match else None


def _extract_summary_total(summary: dict[str, str]) -> int | None:
    for key in ("总中标金额", "总成交金额", "中标金额", "成交金额"):
        value = summary.get(key)
        if value:
            amount = _parse_amount_cny(value)
            # ``0`` / ``0.00元`` is a placeholder (per-test service pricing,
            # 废标), never a published award amount.
            if amount is not None and amount > 0:
                return amount
    return None


def _extract_contact(text: str) -> dict[str, str | None] | None:
    match = re.search(
        r"3[.、]\s*项目联系方式\s+项目联系人\s*[：:]\s*(.+?)\s+"
        r"(?:电\s*话|联系电话|项目联系人电话)\s*[：:]\s*([^\s，。；;]+)",
        text,
        re.S,
    )
    if not match:
        return None
    phone = _normalize_space(match.group(2))
    if len(re.findall(r"\d", phone)) < 5:
        phone = None
    return {"name": _clean(match.group(1), max_length=150), "title": "项目联系人", "phone": phone, "email": None}


# --------------------------------------------------------------------------- #
# Summary table (公告概要)
# --------------------------------------------------------------------------- #
def _summary_fields(blocks: list[tuple[str, Any]]) -> dict[str, str]:
    """Flatten the 公告概要 key/value table into a dict (first value wins)."""
    summary: dict[str, str] = {}
    for kind, payload in blocks:
        if kind != "table":
            continue
        rows: list[list[str]] = payload
        flat = [cell for row in rows for cell in row]
        if not any("采购项目名称" in cell or "总中标金额" in cell or "总成交金额" in cell for cell in flat):
            continue
        for row in rows:
            cells = [cell.strip() for cell in row]
            index = 0
            while index + 1 < len(cells):
                key, value = cells[index], cells[index + 1]
                if key and key not in summary and not key.endswith("："):
                    summary[key] = value
                index += 2
        if summary:
            break
    return summary


# --------------------------------------------------------------------------- #
# Package results (三、中标/成交信息)
# --------------------------------------------------------------------------- #
_CATEGORY_ROW_RE = re.compile(r"^(货物|服务|工程)类?$")


def _table_header(rows: list[list[str]], is_header) -> tuple[int, list[str], str | None] | None:
    """Locate the header row within the first three rows.

    河北 pages put a spanning category row (``货物类`` / ``服务类``) above the
    real header; that label is returned as the default item category.
    """
    category: str | None = None
    for index, row in enumerate(rows[:3]):
        if is_header(row):
            return index, row, category
        distinct = {_header_key(cell) for cell in row if _header_key(cell)}
        if len(distinct) == 1 and _CATEGORY_ROW_RE.match(next(iter(distinct))):
            category = next(iter(distinct))
            continue
        break
    return None


def _is_supplier_table(headers: list[str]) -> bool:
    keys = [_header_key(item) for item in headers]
    has_supplier = any("供应商名称" in key or key in {"中标供应商", "成交供应商", "中标人", "成交人"} for key in keys)
    has_amount = any(("金额" in key or "报价" in key) for key in keys)
    # 河北 template: ``供应商名称 | 供应商地址 | 供应商编码`` carries no amount;
    # the money then lives in the 主要标的信息 table (see _package_amounts_from_item_tables).
    has_identity = any(("供应商地址" in key or "供应商编码" in key or "信用代码" in key) for key in keys)
    return has_supplier and (has_amount or has_identity) and not any("排序" in key or "排名" in key for key in keys)


def _is_item_table(headers: list[str]) -> bool:
    keys = [_header_key(item) for item in headers]
    has_name = any(
        key in {"名称", "标的名称", "货物名称", "产品名称", "服务名称", "工程名称", "采购标的"}
        or (key.endswith("名称") and "供应商" not in key)
        for key in keys
    )
    # Goods tables carry 品牌/规格型号; works/services tables (工程类/服务类)
    # only carry a 类型 column. Both are captured so the scope filter can see
    # that an award is construction-only.
    has_detail = any("品牌" in key or "规格" in key or "型号" in key or key in {"类型", "标的类型"} for key in keys)
    # 河北 服务类 tables: 供应商名称 | 服务名称 | 服务范围 | 服务要求 | 服务标准 | 服务时间 | 中标金额 …
    has_service_detail = any(key in {"服务范围", "服务要求", "服务标准", "服务时间"} for key in keys)
    return has_name and (has_detail or has_service_detail)


# ``三、中标（成交）信息`` (national/天津/河北/北京) or ``三、采购结果`` (黑龙江).
_RESULT_SECTION_RE = re.compile(r"(?:三|四)[、.]\s*(?:(?:中标|成交|中标（成交）|中标\(成交\))信息|采购结果|(?:中标|成交|评审)结果)")
_RESULT_SECTION_TEXT_RE = re.compile(
    r"(?:三|四)[、.]\s*(?:(?:中标|成交|中标（成交）|中标\(成交\))信息|采购结果|(?:中标|成交|评审)结果)\s*[：:]?(.+?)"
    r"(?=(?:四|五)[、.]\s*主要标的信息|(?:五|六)[、.]\s*评审专家|$)",
    re.S,
)


def _packages_from_tables(blocks: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []
    current_package: str | None = None
    in_result_section = False
    for kind, payload in blocks:
        if kind == "text":
            text = payload
            if _RESULT_SECTION_RE.search(text):
                in_result_section = True
            elif re.search(r"(?:四|五)[、.]\s*主要标的信息", text) or "评审报价" in text:
                in_result_section = False
            package_no = _package_no_from_text(text)
            if package_no:
                current_package = package_no
            continue
        if not in_result_section:
            continue
        rows: list[list[str]] = payload
        located = _table_header(rows, _is_supplier_table) if len(rows) >= 2 else None
        if located is None:
            continue
        header_row, headers, _ = located
        supplier_index = _find_header_index(headers, "供应商名称", "中标供应商", "成交供应商", "中标人", "成交人")
        address_index = _find_header_index(headers, "供应商地址", "地址")
        amount_index = _find_header_index(headers, "中标金额", "成交金额", "中标(成交)金额", "金额")
        for row in rows[header_row + 1:]:
            supplier = _clean(row[supplier_index]) if supplier_index is not None and supplier_index < len(row) else None
            if not supplier:
                continue
            amount = None
            if amount_index is not None and amount_index < len(row):
                amount = _parse_amount_cny(row[amount_index], header_hint=headers[amount_index])
            packages.append(
                {
                    "package_no": current_package,
                    "status": "AWARDED",
                    "supplier_name": supplier,
                    "supplier_address": _clean(row[address_index]) if address_index is not None and address_index < len(row) else None,
                    "amount_cny": amount,
                    "amount_raw": _clean(row[amount_index], max_length=160) if amount_index is not None and amount_index < len(row) else None,
                    "amount_header": _clean(headers[amount_index], max_length=80) if amount_index is not None else None,
                    "failure_reason": None,
                }
            )
    return packages


def _packages_from_text(text: str) -> list[dict[str, Any]]:
    """National template: ``包号：N`` blocks with 供应商名称 / 金额 or 废标原因 lines."""
    section = _RESULT_SECTION_TEXT_RE.search(text)
    if not section:
        return []
    body = section.group(1)
    packages: list[dict[str, Any]] = []
    chunks = re.split(r"(?=包(?:组)?(?:编)?号\s*[：:])", body)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        package_no = _package_no_from_text(chunk)
        supplier = re.search(r"(?:中标|成交)?供应商名称\s*[：:]\s*(.+?)(?=\s+供应商地址|\s+(?:中标|成交)|\s+统一社会信用代码|$)", chunk, re.S)
        amount_match = re.search(
            r"(?:中标|成交|中标（成交）|中标\(成交\))金额\s*[：:]\s*([￥¥]?\s*[0-9][0-9,]*(?:\.[0-9]+)?\s*[（(]?\s*(?:万元|元)?\s*[）)]?)",
            chunk,
        )
        # ``废标原因：`` (national) or ``结果类型：废标 … 废标情形：`` (辽宁).
        failure = re.search(
            r"(?:废标|流标|终止)(?:（终止）|\(终止\))?(?:原因|情形)\s*[：:]\s*(.+?)(?=\s+包(?:组)?(?:编)?号|$)",
            chunk,
            re.S,
        )
        if supplier:
            packages.append(
                {
                    "package_no": package_no,
                    "status": "AWARDED",
                    "supplier_name": _clean(supplier.group(1)),
                    "supplier_address": _clean((re.search(r"供应商地址\s*[：:]\s*(.+?)(?=\s+(?:中标|成交)|$)", chunk, re.S) or [None, None])[1]),
                    "amount_cny": _parse_amount_cny(amount_match.group(1)) if amount_match else None,
                    "amount_raw": _clean(amount_match.group(1), max_length=160) if amount_match else None,
                    "failure_reason": None,
                }
            )
        elif failure:
            packages.append(
                {
                    "package_no": package_no,
                    "status": "FAILED",
                    "supplier_name": None,
                    "supplier_address": None,
                    "amount_cny": None,
                    "failure_reason": _clean(failure.group(1)),
                }
            )
    return packages


# --------------------------------------------------------------------------- #
# Items (四、主要标的信息)
# --------------------------------------------------------------------------- #
def _items_from_tables(blocks: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    current_package: str | None = None
    in_item_section = False
    for kind, payload in blocks:
        if kind == "text":
            text = payload
            if re.search(r"(?:四|五)[、.]\s*主要标的信息", text):
                in_item_section = True
            elif re.search(r"(?:五|六|七)[、.]\s*(?:评审专家|代理服务收费|中标（成交）候选)", text):
                in_item_section = False
            package_no = _package_no_from_text(text)
            if package_no:
                current_package = package_no
            continue
        if not in_item_section:
            continue
        rows: list[list[str]] = payload
        located = _table_header(rows, _is_item_table) if len(rows) >= 2 else None
        if located is None:
            continue
        header_row, headers, default_category = located
        name_index = _item_name_index(headers)
        brand_index = _find_header_index(headers, "品牌")
        model_index = _find_header_index(headers, "规格型号", "型号", "规格")
        quantity_index = _find_header_index(headers, "数量")
        price_index = _find_header_index(headers, "单价")
        award_amount_index = _find_header_index(headers, "中标金额", "成交金额")
        category_index = _find_header_index(headers, "类型", "标的类型", "品目名称")
        for row in rows[header_row + 1:]:
            name = _clean(row[name_index]) if name_index is not None and name_index < len(row) else None
            if not name:
                continue
            price_text = row[price_index] if price_index is not None and price_index < len(row) else None
            category = _clean(row[category_index], max_length=20) if category_index is not None and category_index < len(row) else None
            items.append(
                {
                    "package_no": current_package,
                    "category": category or default_category,
                    "name": name,
                    "brand": _clean(row[brand_index], max_length=80) if brand_index is not None and brand_index < len(row) else None,
                    "model": _clean(row[model_index], max_length=120) if model_index is not None and model_index < len(row) else None,
                    "quantity": _clean(row[quantity_index], max_length=40) if quantity_index is not None and quantity_index < len(row) else None,
                    "award_amount_raw": _clean(row[award_amount_index], max_length=160) if award_amount_index is not None and award_amount_index < len(row) else None,
                    "award_amount_header": _clean(headers[award_amount_index], max_length=80) if award_amount_index is not None else None,
                    "unit_price_raw": _clean(price_text, max_length=160),
                    "unit_price_header": _clean(headers[price_index], max_length=80) if price_index is not None else None,
                    "unit_price_cny": _parse_amount_cny(price_text, header_hint=headers[price_index]) if price_index is not None else None,
                }
            )
    return items


def _package_amounts_from_item_tables(blocks: list[tuple[str, Any]]) -> dict[str, int]:
    """河北 template: the 主要标的信息 table carries ``供应商名称`` and ``中标金额``
    per row while the 中标（成交）信息 table has no amount. Sum the awarded
    amount per supplier; a supplier with any unparseable row is left out so
    a partial sum is never published."""
    totals: dict[str, int] = {}
    broken: set[str] = set()
    in_item_section = False
    for kind, payload in blocks:
        if kind == "text":
            if re.search(r"(?:四|五)[、.]\s*主要标的信息", payload):
                in_item_section = True
            elif re.search(r"(?:五|六|七)[、.]\s*(?:评审专家|代理服务收费|中标（成交）候选)", payload):
                in_item_section = False
            continue
        if not in_item_section:
            continue
        rows: list[list[str]] = payload
        located = _table_header(rows, _is_item_table) if len(rows) >= 2 else None
        if located is None:
            continue
        header_row, headers, _ = located
        supplier_index = _find_header_index(headers, "供应商名称", "中标供应商", "成交供应商")
        amount_index = _find_header_index(headers, "中标金额", "成交金额", "中标(成交)金额")
        if supplier_index is None or amount_index is None:
            continue
        for row in rows[header_row + 1:]:
            supplier = _clean(row[supplier_index]) if supplier_index < len(row) else None
            if not supplier:
                continue
            amount = _parse_amount_cny(row[amount_index], header_hint=headers[amount_index]) if amount_index < len(row) else None
            if amount is None:
                broken.add(supplier)
                continue
            totals[supplier] = totals.get(supplier, 0) + amount
    return {supplier: amount for supplier, amount in totals.items() if supplier not in broken}


def _backfill_package_amounts(packages: list[dict[str, Any]], blocks: list[tuple[str, Any]]) -> list[dict[str, Any]]:
    if all(package.get("amount_cny") is not None for package in packages if package["status"] == "AWARDED"):
        return packages
    by_supplier = _package_amounts_from_item_tables(blocks)
    if not by_supplier:
        return packages
    # Only unambiguous: one awarded package per supplier name.
    supplier_counts: dict[str, int] = {}
    for package in packages:
        if package["status"] == "AWARDED" and package.get("supplier_name"):
            supplier_counts[package["supplier_name"]] = supplier_counts.get(package["supplier_name"], 0) + 1
    for package in packages:
        if package["status"] != "AWARDED" or package.get("amount_cny") is not None:
            continue
        supplier = package.get("supplier_name")
        if supplier and supplier_counts.get(supplier) == 1 and supplier in by_supplier:
            package["amount_cny"] = by_supplier[supplier]
            package["amount_source"] = "ITEM_TABLE"
    return packages


_QUANTITY_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)")


def _quantity_number(value: str | None) -> float:
    """``1台`` → 1.0, ``3`` → 3.0; unknown or zero quantities count as one unit."""
    match = _QUANTITY_RE.search(str(value or ""))
    if not match:
        return 1.0
    try:
        number = float(match.group(1))
    except ValueError:
        return 1.0
    return number if number > 0 else 1.0


def reconcile_item_prices(
    items: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    total_amount: int | None,
) -> list[dict[str, Any]]:
    """Conflicting prices stay unknown; never infer a replacement unit.

    Raw cells and source evidence are preserved on the item/record.
    """
    amount_by_package = {
        str(package.get("package_no")): package.get("amount_cny")
        for package in packages
        if package.get("package_no") is not None and isinstance(package.get("amount_cny"), int)
    }
    reconciled: list[dict[str, Any]] = []
    for item in items:
        price = item.get("unit_price_cny")
        if not isinstance(price, int) or price <= 0:
            reconciled.append(item)
            continue
        ceiling = amount_by_package.get(str(item.get("package_no")))
        if ceiling is None:
            ceiling = total_amount
        if not isinstance(ceiling, int) or ceiling <= 0:
            reconciled.append(item)
            continue
        quantity = _quantity_number(item.get("quantity"))
        tolerance = ceiling * 1.001 + 1
        if price * quantity <= tolerance:
            reconciled.append(item)
            continue
        reconciled.append({**item, "unit_price_cny": None, "unit_price_issue": "AMOUNT_CONFLICT"})
    return reconciled


# --------------------------------------------------------------------------- #
# Record assembly
# --------------------------------------------------------------------------- #
def _detect_result_kind(title: str | None, text: str) -> tuple[str, str]:
    haystack = f"{title or ''}\n{text[:600]}"
    notice_type = next((marker for marker in _RESULT_TITLE_MARKERS if marker in haystack), None)
    if notice_type is None:
        raise CcgpAwardParseError("CCGP_AWARD_NOTICE_TYPE_NOT_RESULT")
    if notice_type.startswith("中标（成交）") or notice_type.startswith("中标(成交)"):
        kind = "DEAL" if re.search(r"(?:三|四)[、.]\s*成交信息", text) else "AWARD"
    else:
        kind = "DEAL" if any(marker in notice_type for marker in _DEAL_MARKERS) else "AWARD"
    return notice_type, kind


def _page_title(html: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not match:
        return None
    return _normalize_space(re.sub(r"<[^>]+>", " ", match.group(1)))


def parse_ccgp_award_html(
    html: str,
    *,
    source_url: str,
    observed_at: str,
    award_id: str,
    market_code: str | None = None,
) -> dict[str, Any]:
    _assert_source_url(source_url)
    title = _page_title(html)
    blocks = _document_blocks(html)
    text = _normalize_space(html_to_text(html))
    notice_type, result_kind = _detect_result_kind(title, text)
    summary = _summary_fields(blocks)

    project_number = _extract_project_number(text, title)
    project_name = _extract_project_name(text, summary)
    buyer_name = _extract_buyer(text, summary)
    published_at = _extract_published_at(text, summary)
    procurement_method = _extract_procurement_method(text)
    region = _clean(summary.get("行政区域"), max_length=40)

    packages = _packages_from_tables(blocks) or _packages_from_text(text)
    packages = _backfill_package_amounts(packages[:MAX_PACKAGES], blocks)
    if not packages:
        raise CcgpAwardParseError("CCGP_AWARD_SUPPLIER_NOT_FOUND")
    awarded = [item for item in packages if item["status"] == "AWARDED"]
    for item in awarded:
        if not item.get("supplier_name"):
            raise CcgpAwardParseError("CCGP_AWARD_SUPPLIER_NAME_EMPTY")

    items = _items_from_tables(blocks)[:MAX_ITEMS]

    total_amount = _extract_summary_total(summary) if awarded else None
    amount_basis: str | None = "SUMMARY_TOTAL" if total_amount is not None else None
    if total_amount is None and awarded and all(item.get("amount_cny") is not None for item in awarded):
        total_amount = sum(int(item["amount_cny"]) for item in awarded)
        amount_basis = "PACKAGE_SUM"
    items = reconcile_item_prices(items, packages, total_amount)

    facts: dict[str, Any] = {
        "amount_summary_raw": {key: _clean(value, max_length=160) for key, value in summary.items() if "金额" in key},
        "project_number": project_number,
        "project_name": project_name,
        "buyer_name": buyer_name,
        "region": region,
        "notice_type": notice_type,
        "result_kind": result_kind,
        "lifecycle_state": AWARD_LIFECYCLE_STATE,
        "published_at": published_at,
        "procurement_method": procurement_method,
        "total_amount_cny": total_amount,
        "amount_basis": amount_basis,
        "award_status": "ALL_PACKAGES_FAILED" if not awarded else ("PARTIALLY_FAILED" if len(awarded) < len(packages) else "AWARDED"),
        "packages": packages,
        "items": items,
        "public_contact": _extract_contact(text),
    }
    if market_code:
        facts["market_code"] = str(market_code).strip().upper()

    evidence_paths: list[tuple[str, str]] = [
        ("facts.project_number", "一、项目编号"),
        ("facts.project_name", "二、项目名称"),
        ("facts.buyer_name", "公告概要/采购单位 或 采购人信息/名称"),
        ("facts.notice_type", f"公告标题/{notice_type}"),
        ("facts.lifecycle_state", f"公告类型={notice_type}/确定性生命周期映射"),
        ("facts.published_at", "发布日期"),
        ("facts.packages", "三、中标（成交）信息"),
    ]
    if region:
        evidence_paths.append(("facts.region", "公告概要/行政区域"))
    if procurement_method:
        evidence_paths.append(("facts.procurement_method", "一、项目编号/采购方式"))
    if total_amount is not None:
        evidence_paths.append(
            ("facts.total_amount_cny", "公告概要/总中标(成交)金额" if amount_basis == "SUMMARY_TOTAL" else "三、中标（成交）信息/分包金额合计")
        )
    if items:
        evidence_paths.append(("facts.items", "四、主要标的信息"))
    if facts["public_contact"]:
        evidence_paths.append(("facts.public_contact", "项目联系方式"))

    record = {
        "schema_version": "0.1",
        "record_type": AWARD_RECORD_TYPE,
        "award_id": award_id,
        "source": {
            "source_id": f"ccgp-award:{project_number}",
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
    return validate_award_record(record)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _require_text(value: Any, code: str, *, max_length: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CcgpAwardParseError(code)
    if len(value) > max_length:
        raise CcgpAwardParseError(f"{code}_TOO_LONG")
    return value


def _optional_int(value: Any, code: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CcgpAwardParseError(code)
    return value


def validate_award_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict) or record.get("schema_version") != "0.1":
        raise CcgpAwardParseError("AWARD_SCHEMA_VERSION_UNSUPPORTED")
    if record.get("record_type") != AWARD_RECORD_TYPE:
        raise CcgpAwardParseError("AWARD_RECORD_TYPE_INVALID")
    _require_text(record.get("award_id"), "AWARD_ID_REQUIRED", max_length=80)

    source = record.get("source")
    if not isinstance(source, dict):
        raise CcgpAwardParseError("AWARD_SOURCE_REQUIRED")
    _require_text(source.get("source_id"), "AWARD_SOURCE_ID_REQUIRED", max_length=200)
    if source.get("source_type") != "CCGP_NOTICE":
        raise CcgpAwardParseError("AWARD_SOURCE_TYPE_INVALID")
    _assert_source_url(str(source.get("url") or ""))
    _require_text(source.get("observed_at"), "AWARD_OBSERVED_AT_REQUIRED", max_length=64)

    facts = record.get("facts")
    if not isinstance(facts, dict):
        raise CcgpAwardParseError("AWARD_FACTS_REQUIRED")
    _require_text(facts.get("project_number"), "AWARD_PROJECT_NUMBER_REQUIRED", max_length=120)
    _require_text(facts.get("project_name"), "AWARD_PROJECT_NAME_REQUIRED")
    _require_text(facts.get("buyer_name"), "AWARD_BUYER_REQUIRED")
    if facts.get("lifecycle_state") != AWARD_LIFECYCLE_STATE:
        raise CcgpAwardParseError("AWARD_LIFECYCLE_INVALID")
    if facts.get("result_kind") not in RESULT_KINDS:
        raise CcgpAwardParseError("AWARD_RESULT_KIND_INVALID")
    published_at = facts.get("published_at")
    if not isinstance(published_at, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", published_at):
        raise CcgpAwardParseError("AWARD_PUBLISHED_DATE_INVALID")
    _optional_int(facts.get("total_amount_cny"), "AWARD_TOTAL_AMOUNT_INVALID")
    if facts.get("amount_basis") not in AMOUNT_BASES and facts.get("amount_basis") is not None:
        raise CcgpAwardParseError("AWARD_AMOUNT_BASIS_INVALID")
    if facts.get("total_amount_cny") is not None and facts.get("amount_basis") is None:
        raise CcgpAwardParseError("AWARD_AMOUNT_BASIS_REQUIRED")
    market_code = facts.get("market_code")
    if market_code is not None and (not isinstance(market_code, str) or not re.fullmatch(r"[A-Z]{2}", market_code)):
        raise CcgpAwardParseError("AWARD_MARKET_CODE_INVALID")

    packages = facts.get("packages")
    if not isinstance(packages, list) or not packages or len(packages) > MAX_PACKAGES:
        raise CcgpAwardParseError("AWARD_PACKAGES_INVALID")
    for package in packages:
        if not isinstance(package, dict) or package.get("status") not in PACKAGE_STATUSES:
            raise CcgpAwardParseError("AWARD_PACKAGE_STATUS_INVALID")
        if package["status"] == "AWARDED":
            _require_text(package.get("supplier_name"), "AWARD_PACKAGE_SUPPLIER_REQUIRED")
        else:
            _require_text(package.get("failure_reason"), "AWARD_PACKAGE_FAILURE_REASON_REQUIRED")
        _optional_int(package.get("amount_cny"), "AWARD_PACKAGE_AMOUNT_INVALID")

    items = facts.get("items")
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise CcgpAwardParseError("AWARD_ITEMS_INVALID")
    for item in items:
        if not isinstance(item, dict):
            raise CcgpAwardParseError("AWARD_ITEM_INVALID")
        _require_text(item.get("name"), "AWARD_ITEM_NAME_REQUIRED")
        _optional_int(item.get("unit_price_cny"), "AWARD_ITEM_PRICE_INVALID")

    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise CcgpAwardParseError("AWARD_EVIDENCE_REQUIRED")
    covered = {item.get("field_path") for item in evidence if isinstance(item, dict)}
    for required in ("facts.project_number", "facts.project_name", "facts.buyer_name", "facts.published_at", "facts.packages"):
        if required not in covered:
            raise CcgpAwardParseError(f"AWARD_EVIDENCE_MISSING:{required}")
    for item in evidence:
        if not isinstance(item, dict):
            raise CcgpAwardParseError("AWARD_EVIDENCE_ITEM_INVALID")
        _assert_source_url(str(item.get("source_url") or ""))
    return record


def validate_award_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for record in records:
        checked = validate_award_record(record)
        award_id = checked["award_id"]
        if award_id in seen:
            raise CcgpAwardParseError(f"DUPLICATE_AWARD_ID:{award_id}")
        seen.add(award_id)
        validated.append(checked)
    return validated


def merge_award_records(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Newest ``source.observed_at`` per award_id wins (ties favour ``new``).

    Insertion order is stable so the persisted store diff stays readable.
    """
    merged: dict[str, dict[str, Any]] = {}
    for record in validate_award_records(list(existing) if existing else []):
        merged[record["award_id"]] = record
    for record in validate_award_records(list(new) if new else []):
        current = merged.get(record["award_id"])
        if current is not None and str(current["source"].get("observed_at") or "") > str(record["source"].get("observed_at") or ""):
            continue
        merged[record["award_id"]] = record
    return validate_award_records(list(merged.values())) if merged else []


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #
def is_medical_channel_relevant_award(record: dict[str, Any]) -> bool:
    """Apply the shared medical-channel scope to an award record.

    Pure construction-works awards (every 标的 typed 工程类) are excluded even
    when the project name carries a device acronym such as ``CT室改造``.
    """
    facts = record.get("facts") if isinstance(record, dict) else None
    if not isinstance(facts, dict):
        return False
    items = [item for item in facts.get("items") or [] if isinstance(item, dict)]
    categories = {str(item.get("category") or "") for item in items}
    if items and categories and all("工程" in category for category in categories):
        return False
    pseudo_facts = {
        "project_name": facts.get("project_name"),
        "buyer_name": facts.get("buyer_name"),
        "product_items": [
            {
                "raw_name": item.get("name"),
                "category": item.get("category"),
                "specification": " ".join(str(part) for part in (item.get("brand"), item.get("model")) if part),
            }
            for item in items
        ],
    }
    return is_medical_channel_relevant_record({"facts": pseudo_facts})


# --------------------------------------------------------------------------- #
# Public snapshot projection (compact, bounded award ledger)
# --------------------------------------------------------------------------- #
MAX_LEDGER_ENTRIES = 40
MAX_LEDGER_PACKAGES = 8
MAX_LEDGER_ITEMS = 8
_LEDGER_TEXT_LIMITS = {
    "project_name": 80,
    "buyer_name": 48,
    "supplier_name": 48,
    "category": 24,
    "name": 48,
    "brand": 24,
    "model": 48,
    "quantity": 16,
    "failure_reason": 60,
}


def _ledger_text(value: Any, key: str) -> str | None:
    if value is None:
        return None
    text = _normalize_space(str(value))
    if not text:
        return None
    limit = _LEDGER_TEXT_LIMITS[key]
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _award_is_effective(record: dict[str, Any], as_of: datetime) -> bool:
    try:
        published = date.fromisoformat(str(record["facts"]["published_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    return published <= as_of.date()


def effective_award_records(award_records: list[dict[str, Any]] | None, as_of: datetime) -> list[dict[str, Any]]:
    """Validated awards whose notice is already published at ``as_of``, newest first."""
    if not award_records:
        return []
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    effective = [record for record in validate_award_records(list(award_records)) if _award_is_effective(record, as_of)]
    effective.sort(key=lambda record: (record["facts"]["published_at"], record["award_id"]), reverse=True)
    return effective


_FULLWIDTH_ASCII = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}
_FULLWIDTH_ASCII[0x3000] = 0x20


def normalize_project_number(value: Any) -> str:
    """Matching key for project numbers across notices.

    Tender and result notices for the same project are typed by different
    clerks: full-width brackets/dashes (``HBHX（Z）-2026-019`` vs
    ``HBHX(Z)-2026-019``), stray spaces and letter case all occur. Keys are
    half-width, whitespace-free and lower-cased; the displayed value is never
    changed.
    """
    text = str(value or "").translate(_FULLWIDTH_ASCII)
    return re.sub(r"\s+", "", text).lower()


def awarded_project_numbers(award_records: list[dict[str, Any]] | None, as_of: datetime) -> set[str]:
    """Normalised project numbers that already have a published award/deal result."""
    return {
        normalize_project_number(record["facts"]["project_number"])
        for record in effective_award_records(award_records, as_of)
    }


def _project_completion_proven(record: dict[str, Any]) -> bool:
    """A package result alone never proves that the whole project is closed.

    Existing adapters do not establish this fact. Future verified input must
    carry an explicit whole-project assertion and its official evidence.
    """
    facts = record["facts"]
    return (
        facts.get("award_status") == "AWARDED"
        and facts.get("project_completion_confirmed") is True
        and any(
            isinstance(item, dict)
            and item.get("field_path") == "facts.project_completion_confirmed"
            and item.get("source_url") == record["source"]["url"]
            and str(item.get("locator") or "").strip()
            for item in record.get("evidence", [])
        )
    )


def awarded_project_keys(award_records: list[dict[str, Any]] | None, as_of: datetime) -> set[tuple[str, str]]:
    """Only explicitly proven complete projects in a known market can retire."""
    keys: set[tuple[str, str]] = set()
    for record in effective_award_records(award_records, as_of):
        market = str(record["facts"].get("market_code") or "").strip().upper()
        if market and _project_completion_proven(record):
            keys.add((market, normalize_project_number(record["facts"]["project_number"])))
    return keys


def is_awarded_project(
    awarded_keys: set[tuple[str | None, str]],
    project_number: Any,
    market_code: str | None,
) -> bool:
    key = normalize_project_number(project_number)
    market = str(market_code or "").strip().upper()
    return bool(key and market and (market, key) in awarded_keys)


def exclude_awarded_projects(
    project_numbers: list[str],
    award_records: list[dict[str, Any]] | None,
    as_of: datetime,
) -> tuple[list[str], list[str]]:
    """Result publication never licenses stopping later correction monitoring."""
    return list(project_numbers), []


def evidenced_unit_price(item: dict[str, Any], facts: dict[str, Any]) -> int | None:
    """Recheck raw units and bounds, including canonical records parsed earlier."""
    parsed = _parse_amount_cny(item.get("unit_price_raw"), header_hint=item.get("unit_price_header"))
    price = item.get("unit_price_cny")
    if not isinstance(price, int) or isinstance(price, bool) or price <= 0 or parsed != price:
        return None
    verified_packages = []
    for package in facts.get("packages") or []:
        if package.get("package_no") != item.get("package_no"):
            continue
        amount = evidenced_package_amount(package)
        # A conflicting raw bound invalidates this price; never trust the larger
        # stale canonical ceiling or correct either value by guessing its scale.
        if package.get("amount_raw") and amount is None:
            return None
        if amount is not None:
            verified_packages.append({**package, "amount_cny": amount})
    total = evidenced_total_amount(facts)
    if facts.get("amount_summary_raw") and facts.get("amount_basis") == "SUMMARY_TOTAL" and total is None:
        return None
    return reconcile_item_prices([item], verified_packages, total)[0].get("unit_price_cny")


def evidenced_package_amount(package: dict[str, Any]) -> int | None:
    amount = package.get("amount_cny")
    parsed = _parse_amount_cny(package.get("amount_raw"), header_hint=package.get("amount_header"))
    return amount if isinstance(amount, int) and not isinstance(amount, bool) and parsed == amount else None


def evidenced_total_amount(facts: dict[str, Any]) -> int | None:
    total = facts.get("total_amount_cny")
    if not isinstance(total, int) or isinstance(total, bool):
        return None
    if facts.get("amount_basis") == "SUMMARY_TOTAL":
        raw = facts.get("amount_summary_raw") or {}
        return total if isinstance(raw, dict) and any(_parse_amount_cny(value) == total for value in raw.values()) else None
    packages = [p for p in facts.get("packages") or [] if p.get("status") == "AWARDED"]
    amounts = [evidenced_package_amount(p) for p in packages]
    return total if packages and all(amount is not None for amount in amounts) and sum(amounts) == total else None


def public_award_ledger_entry(record: dict[str, Any], as_of: datetime) -> dict[str, Any]:
    """Project one award record onto the compact public ledger shape.

    Only public facts are carried (supplier, package amounts, brand/model/unit
    price, statutory challenge window); addresses, phone numbers and the full
    evidence list stay in the canonical store. ``source_url`` is the official
    notice so every number remains verifiable.
    """
    facts = record["facts"]
    packages = [
        {
            "package_no": package.get("package_no"),
            "status": package.get("status"),
            "supplier_name": _ledger_text(package.get("supplier_name"), "supplier_name"),
            "amount_cny": evidenced_package_amount(package),
            "amount_basis": "EXPLICIT_CNY" if evidenced_package_amount(package) is not None else "UNKNOWN",
            "failure_reason": _ledger_text(package.get("failure_reason"), "failure_reason"),
        }
        for package in list(facts.get("packages") or [])[:MAX_LEDGER_PACKAGES]
    ]
    items = [
        {
            "package_no": item.get("package_no"),
            "category": _ledger_text(item.get("category"), "category"),
            "name": _ledger_text(item.get("name"), "name"),
            "brand": _ledger_text(item.get("brand"), "brand"),
            "model": _ledger_text(item.get("model"), "model"),
            "quantity": _ledger_text(item.get("quantity"), "quantity"),
            "unit_price_cny": evidenced_unit_price(item, facts),
            "unit_price_basis": "EXPLICIT_UNIT" if evidenced_unit_price(item, facts) is not None else "UNKNOWN",
        }
        for item in list(facts.get("items") or [])[:MAX_LEDGER_ITEMS]
    ]
    entry: dict[str, Any] = {
        "award_id": record["award_id"],
        "projection_version": AWARD_EVIDENCE_VERSION,
        "project_number": facts["project_number"],
        "project_name": _ledger_text(facts.get("project_name"), "project_name"),
        "buyer_name": _ledger_text(facts.get("buyer_name"), "buyer_name"),
        "region": facts.get("region"),
        "notice_type": facts.get("notice_type"),
        "result_kind": facts.get("result_kind"),
        "lifecycle_state": facts.get("lifecycle_state"),
        "published_at": facts.get("published_at"),
        "procurement_method": facts.get("procurement_method"),
        "total_amount_cny": evidenced_total_amount(facts),
        "total_amount_basis": ("VERIFIED_SUMMARY_TOTAL" if facts.get("amount_basis") == "SUMMARY_TOTAL" else "VERIFIED_PACKAGE_SUM") if evidenced_total_amount(facts) is not None else "UNKNOWN",
        "amount_basis": facts.get("amount_basis"),
        "award_status": facts.get("award_status"),
        "package_count": len(facts.get("packages") or []),
        "item_count": len(facts.get("items") or []),
        "packages": packages,
        "items": items,
        "source_url": record["source"]["url"],
        "legal_windows": legal_windows_for_facts(facts, as_of),
    }
    if facts.get("market_code"):
        entry["market_code"] = facts["market_code"]
    return entry


def build_public_award_ledger(
    award_records: list[dict[str, Any]] | None,
    as_of: datetime,
    *,
    max_entries: int = MAX_LEDGER_ENTRIES,
) -> list[dict[str, Any]]:
    """Newest-first, bounded ledger of published awards for the public snapshot."""
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return [
        public_award_ledger_entry(record, as_of)
        for record in effective_award_records(award_records, as_of)[: max(0, int(max_entries))]
    ]
