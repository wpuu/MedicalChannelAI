"""Strict, fail-closed single-page coverage checks; official shapes unregistered.

The pure checker can be exercised with synthetic shapes. Production access must
go through registered_index_contract(), whose reviewed-fixture registry is empty
until actual official captures and their list structure have been reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from html import escape
from html.parser import HTMLParser
import hashlib
from pathlib import Path
import re
from types import MappingProxyType
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from collector_official_transport import OfficialFetchError, OfficialPage, SOURCE_INDEXES, validate_official_url


class OfficialIndexError(ValueError):
    pass


@dataclass(frozen=True)
class IndexShape:
    stage: str
    index_url: str
    container_tag: str
    container_id: str
    layout: str = "simple-list"


@dataclass(frozen=True)
class CapturedIndexEvidence:
    path: str
    sha256: str
    source_url: str
    observed_at: datetime


@dataclass(frozen=True)
class ReviewedIndexContract:
    shape: IndexShape
    capture: CapturedIndexEvidence


@dataclass(frozen=True)
class ScopedIndexWindow:
    stage: str
    index_url: str
    raw_html_sha256: str
    scoped_html: str
    scoped_html_sha256: str
    start_date: date
    end_date: date
    observed_at: datetime


FIXTURE_ROOT = Path(__file__).resolve().parent / "pipeline/fixtures/official"
_REGISTERED_INDEX_CONTRACTS = MappingProxyType({})
_VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})


def captured_index_shape(stage: str) -> IndexShape:
    """Observed template for offline checks; never registers a source contract."""
    if stage in {"tjzyefy", "tjzyefy_intent"}:
        return IndexShape(stage, SOURCE_INDEXES[stage], "td", "", "tjzyefy-table-v1")
    if stage == "tjzxfc":
        return IndexShape(stage, SOURCE_INDEXES[stage], "ul", "xwzx-list", "tjzxfc-table-v1")
    raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")


@dataclass
class _IndexNode:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)


class _CapturedTree(HTMLParser):
    """Bounded raw-source tree for the two observed CMS templates, no repair."""
    def __init__(self, shape):
        super().__init__(convert_charrefs=True)
        self.shape, self.roots, self.stack = shape, [], []
        self.node_count = 0

    def _matches(self, tag, attrs):
        if self.shape.layout == "tjzyefy-table-v1":
            return tag == "td" and set((attrs.get("class") or "").split()) == {"hanggao26", "zi14"}
        return tag == "ul" and attrs.get("id") == "xwzx-list"

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        matches = self._matches(tag, attributes)
        if not self.stack and not matches:
            return
        if len(attributes) != len(attrs) or (matches and (self.stack or self.roots)):
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        self.node_count += 1
        if self.node_count > 4096 or len(self.stack) >= 48:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        node = _IndexNode(tag, attributes)
        if self.stack:
            self.stack[-1].children.append(node)
        else:
            self.roots.append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if self.stack:
            if self.stack[-1].tag != tag:
                raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
            self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        if tag not in _VOID_TAGS and (self.stack or self._matches(tag, dict(attrs))):
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.stack and data.strip():
            if len(data) > 4096:
                raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
            self.stack[-1].children.append(data)


def _expect(node, tag, attrs=None, *, cms_quote=False):
    if not isinstance(node, _IndexNode) or node.tag != tag:
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    actual = dict(node.attrs)
    # Two exact observed table/td positions have one stray quote attribute.
    if cms_quote and actual.get('"', False) is None:
        actual.pop('"')
    if actual != (attrs or {}):
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    return node


def _elements(node):
    if any(not isinstance(child, _IndexNode) for child in node.children):
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    return node.children


def _only(node):
    children = _elements(node)
    if len(children) != 1:
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    return children[0]


def _inline_text(node):
    parts = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.tag in {"span", "b", "strong", "em", "i", "br"} and not child.attrs:
            parts.append(" " if child.tag == "br" else _inline_text(child))
        else:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _nested_link(node, *, maternity):
    # The CMS repeats an identical href within ONE row. No global deduplication.
    if not isinstance(node, _IndexNode):
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    href = node.attrs.get("href")
    if not isinstance(href, str) or not href:
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    _expect(node, "a", {"href": href, **({"target": "_blank"} if maternity else {})})
    prefix = "".join(child for child in node.children if isinstance(child, str)).strip()
    children = [child for child in node.children if isinstance(child, _IndexNode)]
    if prefix not in ({"", "・"} if maternity else {""}) or len(children) != 1:
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    inner = _expect(children[0], "a", {"href": href, "target": "_blank"})
    title = _inline_text(inner)
    if not title or len(title) > 1024:
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    return href, title


def _captured_rows(shape, html):
    if shape != captured_index_shape(shape.stage):
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    parser = _CapturedTree(shape)
    parser.feed(html)
    parser.close()
    if len(parser.roots) != 1 or parser.stack:
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    root = parser.roots[0]
    maternity = shape.layout == "tjzxfc-table-v1"
    if maternity:
        _expect(root, "ul", {"id": "xwzx-list"})
        table = _expect(_only(root), "table", {"width": "100%"})
    else:
        _expect(root, "td", {"valign": "top", "bgcolor": "#FFFFFF", "class": "hanggao26 zi14",
                             "style": "padding:10px 30px"})
        children = _elements(root)
        if len(children) != 2:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        table = _expect(_only(_expect(children[0], "p")), "table", {"width": "100%"})
        pager = _elements(_expect(children[1], "p", {"align": "center"}))
        if len(pager) != 2:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        _expect(pager[0], "div", {"id": "pagetemple"})
        _expect(pager[1], "script", {"src": "https://www.tjzyefy.com/system/count/0002002/002000000000/count_page_list_0002002002000000000.js"})
        if pager[0].children or pager[1].children:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    rows = []
    for row in _elements(table):
        cell = _expect(_only(_expect(row, "tr")), "td")
        if maternity:
            inner = _expect(_only(_expect(_only(cell), "li")), "table",
                            {"width": "100%", "border": "0", "cellspacing": "0", "cellpadding": "0"})
            text_cell = _expect(_only(_expect(_only(inner), "tr")), "td",
                                {"style": "font-size:28px;color:#666; padding-left:20px"})
            link = _only(text_cell)
        else:
            inner = _expect(_only(cell), "table", {"width": "98%", "height": "2", "border": "0",
                            "cellpadding": "0", "cellspacing": "0"}, cms_quote=True)
            cells = _elements(_expect(_only(inner), "tr"))
            if len(cells) != 3:
                raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
            bullet = _expect(cells[0], "td", {"width": "3%", "valign": "top"})
            if _inline_text(bullet) != "·":
                raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
            text_cell = _expect(cells[1], "td", {"width": "80%", "valign": "bottom"}, cms_quote=True)
            link = _only(_expect(_only(text_cell), "div", {"align": "left"}))
            tail = _expect(cells[2], "td", {"width": "17%", "align": "right", "valign": "bottom"})
            if tail.children:
                raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        rows.append(_nested_link(link, maternity=maternity))
    return rows


class _NoticeList(HTMLParser):
    def __init__(self, shape: IndexShape):
        super().__init__(convert_charrefs=True)
        self.shape = shape
        self.containers = 0
        self.stack = []
        self.item = None
        self.anchor = False
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if (self.stack or (tag == self.shape.container_tag and attributes.get("id") == self.shape.container_id)) and len(attributes) != len(attrs):
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        if tag == self.shape.container_tag and attributes.get("id") == self.shape.container_id:
            self.containers += 1
            if self.stack or self.containers != 1:
                raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
            self.stack = [tag]
            return
        if not self.stack:
            return
        if len(attributes) != len(attrs):
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        if len(self.stack) == 1:
            if tag != "li":
                raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
            self.item = {"href": None, "text": []}
        elif tag == "li":
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        if tag == "a":
            if self.item is None or self.item["href"] is not None or not attributes.get("href"):
                raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
            self.item["href"] = attributes["href"]
            self.anchor = True
        if tag not in _VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            return
        if self.stack[-1] != tag:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        self.stack.pop()
        if tag == "a":
            self.anchor = False
        if tag == "li":
            title = " ".join(self.item["text"]).strip()
            if not self.item["href"] or not title:
                raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
            self.rows.append((self.item["href"], title))
            self.item = None

    def handle_startendtag(self, tag, attrs):
        if self.stack and tag not in _VOID_TAGS:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.stack and self.item is None and data.strip():
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        if self.anchor and data.strip():
            self.item["text"].append(data.strip())


def _extract_rows(shape: IndexShape, html: str) -> list[tuple[str, str, date]]:
    if (SOURCE_INDEXES.get(shape.stage) != shape.index_url or not isinstance(html, str) or not html.strip()
            or len(html.encode("utf-8")) > 4 * 1024 * 1024):
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    if shape.layout == "simple-list":
        if shape.container_tag not in {"ul", "ol"} or not shape.container_id:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        parser = _NoticeList(shape)
        parser.feed(html)
        parser.close()
        if parser.containers != 1 or parser.stack:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        extracted = parser.rows
    else:
        extracted = _captured_rows(shape, html)
    if not extracted:
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    rows, seen = [], set()
    for href, title in extracted:
        url = urljoin(shape.index_url, href)
        try:
            validate_official_url(shape.stage, url)
        except OfficialFetchError as exc:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN") from exc
        match = re.fullmatch(r"/system/(20\d{2})/(\d{2})/(\d{2})/(\d+)\.shtml", urlsplit(url).path)
        identity = match.groups() if match else None
        if not match or identity in seen:
            raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
        published = date(*(int(value) for value in match.groups()[:3]))
        if rows and rows[-1][2] < published:
            raise OfficialIndexError("OFFICIAL_INDEX_ORDER_UNVERIFIED")
        seen.add(identity)
        rows.append((url, title, published))
    return rows


def registered_index_contract(stage: str) -> ReviewedIndexContract:
    contract = _REGISTERED_INDEX_CONTRACTS.get(stage)
    if not isinstance(contract, ReviewedIndexContract) or contract.shape.stage != stage:
        raise OfficialIndexError("OFFICIAL_INDEX_CONTRACT_UNVERIFIED")
    evidence = contract.capture
    path = (FIXTURE_ROOT / evidence.path).resolve()
    if (not path.is_relative_to(FIXTURE_ROOT.resolve()) or path.suffix != ".html"
            or evidence.source_url != contract.shape.index_url
            or not isinstance(evidence.observed_at, datetime) or evidence.observed_at.tzinfo is None
            or evidence.observed_at > datetime.now(timezone.utc)):
        raise OfficialIndexError("OFFICIAL_INDEX_CAPTURE_INVALID")
    try:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != evidence.sha256:
            raise ValueError()
        _extract_rows(contract.shape, data.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise OfficialIndexError("OFFICIAL_INDEX_CAPTURE_INVALID") from exc
    return contract


def verify_single_page_window(
    page: OfficialPage, shape: IndexShape, *, start_date: date, end_date: date,
) -> ScopedIndexWindow:
    """Pure structure/window validation, NOT authentication of an official shape."""
    if (page.stage != shape.stage or page.url != shape.index_url
            or page.html_sha256 != hashlib.sha256(page.html.encode("utf-8")).hexdigest()
            or type(start_date) is not date or type(end_date) is not date or start_date > end_date
            or not isinstance(page.observed_at, datetime) or page.observed_at.tzinfo is None
            or end_date > page.observed_at.astimezone(ZoneInfo("Asia/Shanghai")).date()):
        raise OfficialIndexError("OFFICIAL_INDEX_WINDOW_UNVERIFIED")
    rows = _extract_rows(shape, page.html)
    if any(published > page.observed_at.astimezone(ZoneInfo("Asia/Shanghai")).date() for _, _, published in rows):
        raise OfficialIndexError("OFFICIAL_INDEX_FUTURE_NOTICE")
    # A reviewed reverse-chronological list must reach the lower boundary.
    # No link/no next page is NOT proof of end-of-archive or empty coverage.
    if rows[-1][2] > start_date:
        raise OfficialIndexError("OFFICIAL_INDEX_WINDOW_NOT_COVERED")
    scoped = "".join(f'<a href="{escape(url, quote=True)}">{escape(title)}</a>' for url, title, _ in rows)
    return ScopedIndexWindow(
        shape.stage, shape.index_url, page.html_sha256, scoped,
        hashlib.sha256(scoped.encode("utf-8")).hexdigest(), start_date, end_date, page.observed_at,
    )


def verify_registered_source_window(page: OfficialPage, *, start_date: date, end_date: date) -> ScopedIndexWindow:
    contract = registered_index_contract(page.stage)
    return verify_single_page_window(page, contract.shape, start_date=start_date, end_date=end_date)
