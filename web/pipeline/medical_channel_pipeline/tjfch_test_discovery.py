from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .tjfch_discovery import ALLOWED_HOSTS, fetch_tjfch_page, stable_opportunity_id

INDEX_URL = "https://www.tjfch.com.cn/ywgk/"


class TjfchTestDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class TjfchTestCandidate:
    title: str
    detail_url: str


class _IndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            title = re.sub(r"\s+", " ", "".join(self._text)).strip()
            if title:
                self.links.append((self._href, title))
            self._href = None
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None and data.strip():
            self._text.append(data.strip())


def _assert_index_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise TjfchTestDiscoveryError("TJFCH_TEST_INDEX_HOST_REJECTED")


def _supported_title(title: str) -> bool:
    normalized = re.sub(r"\s+", "", title)
    if "测试企业征集公告" not in normalized and "意向测试企业征集公告" not in normalized:
        return False
    if any(marker in normalized for marker in ("评分细则", "测试结果", "征集结果", "成交公告", "中标公告")):
        return False
    return True


def parse_tjfch_test_index_html(
    html: str,
    *,
    index_url: str = INDEX_URL,
    max_candidates: int = 30,
) -> list[TjfchTestCandidate]:
    _assert_index_url(index_url)
    if not 1 <= max_candidates <= 100:
        raise ValueError("TJFCH_TEST_MAX_CANDIDATES_INVALID")

    parser = _IndexParser()
    parser.feed(html)
    candidates: list[TjfchTestCandidate] = []
    seen: set[str] = set()

    for href, title in parser.links:
        if not _supported_title(title):
            continue
        detail_url = urljoin(index_url, href)
        parsed = urlparse(detail_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            continue
        try:
            stable_opportunity_id(detail_url)
        except ValueError:
            continue
        if detail_url in seen:
            continue
        seen.add(detail_url)
        candidates.append(
            TjfchTestCandidate(
                title=re.sub(r"\s+", " ", title).strip(),
                detail_url=detail_url,
            )
        )
        if len(candidates) >= max_candidates:
            break

    return candidates


__all__ = [
    "INDEX_URL",
    "TjfchTestCandidate",
    "TjfchTestDiscoveryError",
    "fetch_tjfch_page",
    "parse_tjfch_test_index_html",
    "stable_opportunity_id",
]
