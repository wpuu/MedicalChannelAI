from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

INDEX_URL = 'https://www.tjmugh.com.cn/cgxxtzgg/index.shtml'
ALLOWED_HOSTS = {'tjmugh.com.cn', 'www.tjmugh.com.cn'}
SUPPORTED_TITLE_MARKERS = ('医疗设备', '市场调研')


class TjmughDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class TjmughCandidate:
    title: str
    detail_url: str
    published_at: str | None


class _IndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []
        self.visible_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'a':
            self._href = dict(attrs).get('href')
            self._text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == 'a' and self._href:
            title = re.sub(r'\s+', ' ', ''.join(self._text)).strip()
            if title:
                self.links.append((self._href, title))
            self._href = None
            self._text = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        self.visible_text.append(text)
        if self._href is not None:
            self._text.append(text)


def _assert_index_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
        raise TjmughDiscoveryError('TJMUGH_INDEX_HOST_REJECTED')


def _detail_id_from_url(url: str) -> tuple[str, str] | None:
    match = re.search(r'/system/(20\d{2})/(\d{2})/(\d{2})/(\d+)\.shtml$', urlparse(url).path)
    if not match:
        return None
    year, month, day, item_id = match.groups()
    return f'{year}-{month}-{day}', item_id


def stable_opportunity_id(detail_url: str) -> str:
    parsed = _detail_id_from_url(detail_url)
    if not parsed:
        raise TjmughDiscoveryError('TJMUGH_DETAIL_URL_ID_NOT_FOUND')
    published_at, item_id = parsed
    return f"tjmugh_{published_at.replace('-', '')}_{item_id}"


def parse_tjmugh_index_html(html: str, *, index_url: str = INDEX_URL) -> list[TjmughCandidate]:
    _assert_index_url(index_url)
    parser = _IndexParser()
    parser.feed(html)

    # The North China site uses stable /system/YYYY/MM/DD/id.shtml links. The URL date
    # is used only as discovery metadata; the detail parser independently verifies the
    # publication date from page content before a record can become VERIFIED.
    candidates: list[TjmughCandidate] = []
    seen: set[str] = set()
    for href, title in parser.links:
        detail_url = urljoin(index_url, href)
        parsed = urlparse(detail_url)
        if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
            continue
        date_and_id = _detail_id_from_url(detail_url)
        if not date_and_id or detail_url in seen:
            continue
        if not all(marker in title for marker in SUPPORTED_TITLE_MARKERS):
            continue
        seen.add(detail_url)
        published_at, _ = date_and_id
        candidates.append(
            TjmughCandidate(
                title=title,
                detail_url=detail_url,
                published_at=published_at,
            )
        )

    candidates.sort(key=lambda item: (item.published_at or '', item.detail_url), reverse=True)
    return candidates


def select_candidates_since(
    candidates: list[TjmughCandidate],
    *,
    start_date: date,
    end_date: date,
    max_candidates: int,
) -> list[TjmughCandidate]:
    if max_candidates < 1:
        raise ValueError('TJMUGH_MAX_CANDIDATES_INVALID')
    selected = []
    for candidate in candidates:
        if not candidate.published_at:
            continue
        published = date.fromisoformat(candidate.published_at)
        if start_date <= published <= end_date:
            selected.append(candidate)
        if len(selected) >= max_candidates:
            break
    return selected


def fetch_tjmugh_page(url: str, *, timeout_seconds: int = 30) -> str:
    _assert_index_url(url)
    request = Request(
        url,
        headers={
            'User-Agent': 'MedicalChannelAI/0.1 (+official hospital evidence collection)',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or 'utf-8'
        return body.decode(charset, errors='replace')
    except HTTPError as exc:
        raise RuntimeError(f'TJMUGH_HTTP_{exc.code}') from exc
    except URLError as exc:
        raise RuntimeError('TJMUGH_NETWORK_ERROR') from exc
