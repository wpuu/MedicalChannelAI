from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

INDEX_URL = 'https://www.tjzyefy.com/xwgg/ggtz/'
ALLOWED_HOSTS = {'tjzyefy.com', 'www.tjzyefy.com'}
MEDICAL_TITLE_MARKERS = ('医疗设备', '医疗器械', '医用耗材', '耗材', '试剂')


class TjzyefyDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class TjzyefyCandidate:
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
        raise TjzyefyDiscoveryError(code)


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


def _is_supported_research_title(title: str) -> bool:
    compact = re.sub(r'\s+', '', title)
    if '调研' not in compact or '采购意向' in compact:
        return False
    return any(marker in compact for marker in MEDICAL_TITLE_MARKERS)


def stable_opportunity_id(detail_url: str) -> str:
    identity = _detail_identity(detail_url)
    if not identity:
        raise TjzyefyDiscoveryError('TJZYEFY_DETAIL_URL_ID_NOT_FOUND')
    published_at, item_id = identity
    return f"tjzyefy_{published_at.replace('-', '')}_{item_id}"


def parse_tjzyefy_index_html(html: str, *, index_url: str = INDEX_URL) -> list[TjzyefyCandidate]:
    _assert_official_url(index_url, code='TJZYEFY_INDEX_HOST_REJECTED')
    parser = _IndexParser()
    parser.feed(html)
    candidates: list[TjzyefyCandidate] = []
    seen: set[str] = set()
    for href, title in parser.links:
        if not _is_supported_research_title(title):
            continue
        detail_url = _normalize_detail_url(index_url, href)
        if not detail_url or detail_url in seen:
            continue
        identity = _detail_identity(detail_url)
        if not identity:
            continue
        seen.add(detail_url)
        published_at, _ = identity
        candidates.append(TjzyefyCandidate(title=title, detail_url=detail_url, published_at=published_at))
    candidates.sort(key=lambda item: (item.published_at, item.detail_url), reverse=True)
    return candidates


def select_candidates_since(
    candidates: list[TjzyefyCandidate],
    *,
    start_date: date,
    end_date: date,
    max_candidates: int,
) -> list[TjzyefyCandidate]:
    if max_candidates < 1:
        raise ValueError('TJZYEFY_MAX_CANDIDATES_INVALID')
    result: list[TjzyefyCandidate] = []
    for candidate in candidates:
        published = date.fromisoformat(candidate.published_at)
        if start_date <= published <= end_date:
            result.append(candidate)
        if len(result) >= max_candidates:
            break
    return result


def fetch_tjzyefy_page(url: str, *, timeout_seconds: int = 30) -> str:
    _assert_official_url(url, code='TJZYEFY_FETCH_HOST_REJECTED')
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
        raise RuntimeError(f'TJZYEFY_HTTP_{exc.code}') from exc
    except URLError as exc:
        raise RuntimeError('TJZYEFY_NETWORK_ERROR') from exc
