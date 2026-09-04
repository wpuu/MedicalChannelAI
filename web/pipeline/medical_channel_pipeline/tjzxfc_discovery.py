from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

INDEX_URL = 'https://www.tjzxfc.cn/ywgk/zbgg/index.shtml'
ALLOWED_HOSTS = {'tjzxfc.cn', 'www.tjzxfc.cn'}
EARLY_SIGNAL_MARKERS = ('市场调研', '采购前调研', '调研邀请公告')


class TjzxfcDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class TjzxfcCandidate:
    title: str
    detail_url: str
    published_at: str


class _IndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'a':
            self._href = dict(attrs).get('href')
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == 'a' and self._href:
            title = re.sub(r'\s+', ' ', ''.join(self._text)).strip(' ·')
            if title:
                self.links.append((self._href, title))
            self._href = None
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None and data.strip():
            self._text.append(data.strip())


def _assert_official_url(url: str, *, code: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
        raise TjzxfcDiscoveryError(code)


def _detail_identity(url: str) -> tuple[str, str] | None:
    match = re.fullmatch(r'/system/(20\d{2})/(\d{2})/(\d{2})/(\d+)\.shtml', urlparse(url).path)
    if not match:
        return None
    year, month, day, item_id = match.groups()
    try:
        published = date(int(year), int(month), int(day))
    except ValueError:
        return None
    return published.isoformat(), item_id


def _normalize_detail_url(index_url: str, href: str) -> str | None:
    detail_url = urljoin(index_url, href)
    parsed = urlparse(detail_url)
    if parsed.hostname not in ALLOWED_HOSTS:
        return None
    if parsed.scheme == 'http':
        detail_url = parsed._replace(scheme='https').geturl()
    elif parsed.scheme != 'https':
        return None
    return detail_url if _detail_identity(detail_url) else None


def _is_early_signal_title(title: str) -> bool:
    compact = re.sub(r'\s+', '', title)
    return '调研' in compact and any(marker in compact for marker in EARLY_SIGNAL_MARKERS)


def stable_opportunity_id(detail_url: str) -> str:
    identity = _detail_identity(detail_url)
    if not identity:
        raise TjzxfcDiscoveryError('TJZXFC_DETAIL_URL_ID_NOT_FOUND')
    published_at, item_id = identity
    return f"tjzxfc_{published_at.replace('-', '')}_{item_id}"


def parse_tjzxfc_index_html(html: str, *, index_url: str = INDEX_URL) -> list[TjzxfcCandidate]:
    _assert_official_url(index_url, code='TJZXFC_INDEX_HOST_REJECTED')
    parser = _IndexParser()
    parser.feed(html)
    candidates: list[TjzxfcCandidate] = []
    seen: set[str] = set()
    for href, title in parser.links:
        if not _is_early_signal_title(title):
            continue
        detail_url = _normalize_detail_url(index_url, href)
        if not detail_url or detail_url in seen:
            continue
        identity = _detail_identity(detail_url)
        if not identity:
            continue
        seen.add(detail_url)
        published_at, _ = identity
        candidates.append(TjzxfcCandidate(title=title, detail_url=detail_url, published_at=published_at))
    candidates.sort(key=lambda item: (item.published_at, item.detail_url), reverse=True)
    return candidates


def select_candidates_since(
    candidates: list[TjzxfcCandidate],
    *,
    start_date: date,
    end_date: date,
    max_candidates: int,
) -> list[TjzxfcCandidate]:
    if max_candidates < 1:
        raise ValueError('TJZXFC_MAX_CANDIDATES_INVALID')
    result: list[TjzxfcCandidate] = []
    for candidate in candidates:
        published = date.fromisoformat(candidate.published_at)
        if start_date <= published <= end_date:
            result.append(candidate)
        if len(result) >= max_candidates:
            break
    return result


def fetch_tjzxfc_page(url: str, *, timeout_seconds: int = 30) -> str:
    _assert_official_url(url, code='TJZXFC_FETCH_HOST_REJECTED')
    request = Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (compatible; MedicalChannelAI/0.1; official-public-evidence)',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or 'utf-8'
        try:
            return body.decode(charset)
        except (LookupError, UnicodeDecodeError):
            return body.decode('utf-8', errors='replace')
    except HTTPError as exc:
        raise RuntimeError(f'TJZXFC_HTTP_{exc.code}') from exc
    except URLError as exc:
        raise RuntimeError('TJZXFC_NETWORK_ERROR') from exc
