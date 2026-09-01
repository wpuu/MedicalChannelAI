from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

INDEX_URL = 'https://www.tedahospital.com.cn/article/plist/9'
ALLOWED_HOSTS = {'tedahospital.com.cn', 'www.tedahospital.com.cn'}
EARLY_SIGNAL_TITLE_MARKERS = ('设备需求调研', '论证邀请公告', '产品介绍论证')
EXCLUDED_TITLE_MARKERS = ('中标', '结果', '终止', '招标公告', '遴选结果')


class TedaDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class TedaCandidate:
    title: str
    detail_url: str
    index_url: str
    published_at: str | None


class _IndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str | None]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self._pending_index: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'a':
            self._href = dict(attrs).get('href')
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == 'a' and self._href:
            title = re.sub(r'\s+', ' ', ''.join(self._text)).strip()
            if title:
                self.links.append(
                    {
                        'href': self._href,
                        'title': title,
                        'published_at': None,
                    }
                )
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
        match = re.search(r'\b(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?\b', text)
        if match:
            year, month, day = (int(value) for value in match.groups())
            try:
                self.links[self._pending_index]['published_at'] = date(year, month, day).isoformat()
            except ValueError:
                pass
            self._pending_index = None


def _assert_url(url: str, *, code: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
        raise TedaDiscoveryError(code)


def index_page_url(page: int) -> str:
    if page < 1:
        raise ValueError('TEDA_PAGE_INVALID')
    return INDEX_URL if page == 1 else f'{INDEX_URL}/{page}'


def _normalize_official_url(index_url: str, href: str) -> str | None:
    detail_url = urljoin(index_url, href)
    parsed = urlparse(detail_url)
    if parsed.hostname not in ALLOWED_HOSTS:
        return None
    if parsed.scheme == 'http':
        detail_url = parsed._replace(scheme='https').geturl()
    elif parsed.scheme != 'https':
        return None
    return detail_url


def _detail_id(url: str) -> str | None:
    match = re.fullmatch(r'/article/show/9/(\d+)', urlparse(url).path.rstrip('/'))
    return match.group(1) if match else None


def stable_opportunity_id(detail_url: str) -> str:
    item_id = _detail_id(detail_url)
    if not item_id:
        raise TedaDiscoveryError('TEDA_DETAIL_URL_ID_NOT_FOUND')
    return f'teda_{item_id}'


def _supported_title(title: str) -> bool:
    normalized = re.sub(r'\s+', '', title)
    if any(marker in normalized for marker in EXCLUDED_TITLE_MARKERS):
        return False
    return any(marker in normalized for marker in EARLY_SIGNAL_TITLE_MARKERS)


def parse_teda_index_html(html: str, *, index_url: str = INDEX_URL) -> list[TedaCandidate]:
    _assert_url(index_url, code='TEDA_INDEX_HOST_REJECTED')
    parser = _IndexParser()
    parser.feed(html)
    result: list[TedaCandidate] = []
    seen: set[str] = set()
    for row in parser.links:
        href = row.get('href')
        title = row.get('title')
        if not href or not title or not _supported_title(title):
            continue
        detail_url = _normalize_official_url(index_url, href)
        if not detail_url or not _detail_id(detail_url) or detail_url in seen:
            continue
        seen.add(detail_url)
        result.append(
            TedaCandidate(
                title=title,
                detail_url=detail_url,
                index_url=index_url,
                published_at=row.get('published_at'),
            )
        )
    return result


def _meta_charset(body: bytes) -> str | None:
    match = re.search(
        br'charset\s*=\s*["\']?\s*([A-Za-z0-9._-]+)',
        body[:8192],
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).decode('ascii', errors='ignore') or None


def decode_teda_html(body: bytes, declared_charset: str | None = None) -> str:
    candidates: list[str] = []
    for value in (declared_charset, _meta_charset(body), 'utf-8', 'gb18030'):
        if not value:
            continue
        normalized = value.strip().lower()
        if normalized in {'gb2312', 'gbk', 'gb_2312-80'}:
            normalized = 'gb18030'
        if normalized not in candidates:
            candidates.append(normalized)
    decoded: list[tuple[int, str]] = []
    for charset in candidates:
        try:
            text = body.decode(charset)
        except (LookupError, UnicodeDecodeError):
            continue
        score = 0
        if '天津市泰达医院' in text:
            score += 100
        if '需求调研' in text:
            score += 40
        if '医疗设备' in text:
            score += 30
        if '/article/show/9/' in text:
            score += 10
        decoded.append((score, text))
    if decoded:
        decoded.sort(key=lambda item: item[0], reverse=True)
        return decoded[0][1]
    return body.decode('utf-8', errors='replace')


def fetch_teda_page(url: str, *, timeout_seconds: int = 30) -> str:
    _assert_url(url, code='TEDA_PAGE_HOST_REJECTED')
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
            declared_charset = response.headers.get_content_charset()
        return decode_teda_html(body, declared_charset)
    except HTTPError as exc:
        raise RuntimeError(f'TEDA_HTTP_{exc.code}') from exc
    except URLError as exc:
        raise RuntimeError('TEDA_NETWORK_ERROR') from exc
