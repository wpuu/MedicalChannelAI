from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

INDEX_URL = "https://www.tjnothop.cn/xwzx/index.shtml"
ALLOWED_HOSTS = {"tjnothop.cn", "www.tjnothop.cn"}
SUPPORTED_TITLE_MARKER = "采购项目调研公告"


class TjnothopDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class TjnothopCandidate:
    title: str
    detail_url: str
    published_at: str | None


class _IndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str | None]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self._pending_index: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            title = re.sub(r"\s+", " ", "".join(self._text)).strip()
            if title:
                self.links.append({"href": self._href, "title": title, "published_at": None})
                self._pending_index = len(self.links) - 1
            self._href = None
            self._text = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._href is not None:
            self._text.append(text)
            return
        if self._pending_index is None:
            return
        match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
        if match:
            self.links[self._pending_index]["published_at"] = match.group(0)
            self._pending_index = None


def _assert_url(url: str, *, code: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise TjnothopDiscoveryError(code)


def _detail_parts(url: str) -> tuple[str, str] | None:
    match = re.search(r"/system/(20\d{2})/(\d{2})/(\d{2})/(\d+)\.shtml$", urlparse(url).path)
    if not match:
        return None
    year, month, day, item_id = match.groups()
    return f"{year}-{month}-{day}", item_id


def stable_opportunity_id(detail_url: str) -> str:
    parsed = _detail_parts(detail_url)
    if not parsed:
        raise TjnothopDiscoveryError("TJNOTHOP_DETAIL_URL_ID_NOT_FOUND")
    url_date, item_id = parsed
    return f"tjnothop_{url_date.replace('-', '')}_{item_id}"


def _supported_title(title: str) -> bool:
    normalized = re.sub(r"\s+", "", title)
    return (
        normalized.startswith("天津市天津医院")
        and SUPPORTED_TITLE_MARKER in normalized
        and "招聘" not in normalized
    )


def parse_tjnothop_index_html(
    html: str,
    *,
    index_url: str = INDEX_URL,
) -> list[TjnothopCandidate]:
    _assert_url(index_url, code="TJNOTHOP_INDEX_HOST_REJECTED")
    parser = _IndexParser()
    parser.feed(html)

    candidates: list[TjnothopCandidate] = []
    seen: set[str] = set()
    for row in parser.links:
        href = row.get("href")
        title = row.get("title")
        if not href or not title or not _supported_title(title):
            continue
        detail_url = urljoin(index_url, href)
        parsed = urlparse(detail_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            continue
        detail_parts = _detail_parts(detail_url)
        if not detail_parts or detail_url in seen:
            continue
        published_at = row.get("published_at")
        if published_at is not None:
            try:
                date.fromisoformat(published_at)
            except ValueError:
                published_at = None
        seen.add(detail_url)
        candidates.append(
            TjnothopCandidate(
                title=re.sub(r"\s+", " ", title).strip(),
                detail_url=detail_url,
                published_at=published_at,
            )
        )

    candidates.sort(key=lambda item: (item.published_at or "", item.detail_url), reverse=True)
    return candidates


def select_candidates_since(
    candidates: list[TjnothopCandidate],
    *,
    start_date: date,
    end_date: date,
    max_candidates: int,
) -> list[TjnothopCandidate]:
    if max_candidates < 1:
        raise ValueError("TJNOTHOP_MAX_CANDIDATES_INVALID")
    selected: list[TjnothopCandidate] = []
    for candidate in candidates:
        if not candidate.published_at:
            continue
        published = date.fromisoformat(candidate.published_at)
        if start_date <= published <= end_date:
            selected.append(candidate)
        if len(selected) >= max_candidates:
            break
    return selected


def fetch_tjnothop_page(url: str, *, timeout_seconds: int = 30) -> str:
    _assert_url(url, code="TJNOTHOP_PAGE_HOST_REJECTED")
    request = Request(
        url,
        headers={
            "User-Agent": "MedicalChannelAI/0.1 (+official hospital evidence collection)",
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
        raise RuntimeError(f"TJNOTHOP_HTTP_{exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("TJNOTHOP_NETWORK_ERROR") from exc
