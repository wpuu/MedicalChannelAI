"""Strict, fail-closed single-page coverage checks; official shapes unregistered.

The pure checker can be exercised with synthetic shapes. Production access must
go through registered_index_contract(), whose reviewed-fixture registry is empty
until actual official captures and their list structure have been reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    if (SOURCE_INDEXES.get(shape.stage) != shape.index_url or shape.container_tag not in {"ul", "ol"}
            or not shape.container_id or not isinstance(html, str) or not html.strip()
            or len(html.encode("utf-8")) > 4 * 1024 * 1024):
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    parser = _NoticeList(shape)
    parser.feed(html)
    parser.close()
    if parser.containers != 1 or parser.stack or not parser.rows:
        raise OfficialIndexError("OFFICIAL_INDEX_STRUCTURE_UNKNOWN")
    rows, seen = [], set()
    for href, title in parser.rows:
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
