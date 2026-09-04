from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .channel_scope import is_medical_channel_relevant_text
from .tjzyefy_discovery import ALLOWED_HOSTS, INDEX_URL, fetch_tjzyefy_page


class TjzyefyIntentDiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class TjzyefyIntentCandidate:
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
        raise TjzyefyIntentDiscoveryError(code)


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


def _is_supported_intent_title(title: str) -> bool:
    compact = re.sub(r'\s+', '', title)
    if '采购意向公告' not in compact:
        return False
    return is_medical_channel_relevant_text(compact)


def stable_intent_opportunity_id(detail_url: str) -> str:
    identity = _detail_identity(detail_url)
    if not identity:
        raise TjzyefyIntentDiscoveryError('TJZYEFY_INTENT_DETAIL_URL_ID_NOT_FOUND')
    published_at, item_id = identity
    return f"tjzyefy_intent_{published_at.replace('-', '')}_{item_id}"


def parse_tjzyefy_intent_index_html(
    html: str,
    *,
    index_url: str = INDEX_URL,
) -> list[TjzyefyIntentCandidate]:
    _assert_official_url(index_url, code='TJZYEFY_INTENT_INDEX_HOST_REJECTED')
    parser = _IndexParser()
    parser.feed(html)
    candidates: list[TjzyefyIntentCandidate] = []
    seen: set[str] = set()
    for href, title in parser.links:
        if not _is_supported_intent_title(title):
            continue
        detail_url = _normalize_detail_url(index_url, href)
        if not detail_url or detail_url in seen:
            continue
        identity = _detail_identity(detail_url)
        if not identity:
            continue
        published_at, _ = identity
        seen.add(detail_url)
        candidates.append(
            TjzyefyIntentCandidate(
                title=title,
                detail_url=detail_url,
                published_at=published_at,
            )
        )
    candidates.sort(key=lambda item: (item.published_at, item.detail_url), reverse=True)
    return candidates


def select_intent_candidates_since(
    candidates: list[TjzyefyIntentCandidate],
    *,
    start_date: date,
    end_date: date,
    max_candidates: int,
) -> list[TjzyefyIntentCandidate]:
    if max_candidates < 1:
        raise ValueError('TJZYEFY_INTENT_MAX_CANDIDATES_INVALID')
    result: list[TjzyefyIntentCandidate] = []
    for candidate in candidates:
        published = date.fromisoformat(candidate.published_at)
        if start_date <= published <= end_date:
            result.append(candidate)
        if len(result) >= max_candidates:
            break
    return result


__all__ = [
    'INDEX_URL',
    'TjzyefyIntentCandidate',
    'TjzyefyIntentDiscoveryError',
    'fetch_tjzyefy_page',
    'parse_tjzyefy_intent_index_html',
    'select_intent_candidates_since',
    'stable_intent_opportunity_id',
]
