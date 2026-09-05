from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

PRODUCTION_HOST = 'bulletin.cebpubservice.com'
SEARCH_PATH = '/xxfbcmses/search/bulletin.html'
DETAIL_PATH_RE = re.compile(r'^/biddingBulletin/20\d{2}-\d{2}-\d{2}/[0-9a-fA-F]{32}\.html$')
TIANJIN_AREA_CODE = '120000'
TENDER_CATEGORY_ID = '88'
LOOKBACK_DAYS = 45
MAX_SEARCH_REQUESTS = 4
MAX_DETAIL_REQUESTS = 2
MIN_REQUEST_DELAY_SECONDS = 3.0
TARGET_KEYWORDS = (
    '空气压力治疗仪',
    '高分辨液质联用系统维保服务',
)


def _normalize(value: str) -> str:
    return re.sub(r'\s+', '', value or '')


def build_search_url(*, keyword: str, search_date: str, area: str = TIANJIN_AREA_CODE) -> str:
    params = {
        'searchDate': search_date,
        'dates': '300',
        'word': keyword,
        'categoryId': TENDER_CATEGORY_ID,
        'industryName': '',
        'area': area,
        'status': '',
        'publishMedia': '',
        'sourceInfo': '',
        'showStatus': '1',
        'page': '1',
    }
    return f'https://{PRODUCTION_HOST}{SEARCH_PATH}?{urlencode(params)}'


def normalize_detail_url(href: str, *, base_url: str) -> str | None:
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    if parsed.hostname != PRODUCTION_HOST:
        return None
    if parsed.scheme not in {'http', 'https'}:
        return None
    if not DETAIL_PATH_RE.fullmatch(parsed.path):
        return None
    return urlunparse(('https', PRODUCTION_HOST, parsed.path, '', '', ''))


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != 'a' or self._href is not None:
            return
        href = dict(attrs).get('href')
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None and data.strip():
            self._text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == 'a' and self._href is not None:
            self.links.append((self._href, ' '.join(self._text)))
            self._href = None
            self._text = []


def extract_matching_detail_links(html: str, *, base_url: str, keyword: str) -> list[dict[str, str]]:
    parser = _AnchorParser()
    parser.feed(html)
    needle = _normalize(keyword)
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, title in parser.links:
        if needle not in _normalize(title):
            continue
        detail_url = normalize_detail_url(href, base_url=base_url)
        if not detail_url or detail_url in seen:
            continue
        seen.add(detail_url)
        result.append({'title': title, 'url': detail_url})
    return result


def _fetch(url: str) -> tuple[int, str, str]:
    request = Request(url, method='GET')
    request.add_header('User-Agent', 'Mozilla/5.0 (compatible; MedicalChannelAI-ReadOnly-Probe/1.0)')
    request.add_header('Accept', 'text/html,application/xhtml+xml')
    request.add_header('Accept-Language', 'zh-CN,zh;q=0.9')
    request.add_header('Referer', f'https://{PRODUCTION_HOST}/')
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode('utf-8', errors='replace')
            return int(response.status), response.geturl(), body
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        return int(exc.code), exc.geturl(), body
    except URLError as exc:
        return 0, url, f'{type(exc.reason).__name__}: {exc.reason}'


def _probe() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    search_date = (now - timedelta(days=LOOKBACK_DAYS)).date().isoformat()
    search_request_count = 0
    detail_request_count = 0
    targets: list[dict[str, object]] = []

    for target_index, keyword in enumerate(TARGET_KEYWORDS):
        attempts: list[dict[str, object]] = []
        matches: list[dict[str, str]] = []
        for area in (TIANJIN_AREA_CODE, ''):
            if search_request_count >= MAX_SEARCH_REQUESTS:
                break
            if search_request_count:
                time.sleep(MIN_REQUEST_DELAY_SECONDS)
            url = build_search_url(keyword=keyword, search_date=search_date, area=area)
            status, final_url, body = _fetch(url)
            search_request_count += 1
            parsed_final = urlparse(final_url)
            same_official_host = parsed_final.hostname == PRODUCTION_HOST
            if status == 200 and same_official_host:
                matches = extract_matching_detail_links(body, base_url=final_url, keyword=keyword)
            attempts.append({
                'area': area or 'ALL',
                'status': status,
                'same_official_host': same_official_host,
                'response_bytes': len(body.encode('utf-8')),
                'matching_detail_count': len(matches),
            })
            if matches:
                break

        detail: dict[str, object] | None = None
        if matches and detail_request_count < MAX_DETAIL_REQUESTS:
            if search_request_count or detail_request_count:
                time.sleep(MIN_REQUEST_DELAY_SECONDS)
            detail_url = matches[0]['url']
            status, final_url, body = _fetch(detail_url)
            detail_request_count += 1
            parsed_final = urlparse(final_url)
            detail = {
                'status': status,
                'same_official_host': parsed_final.hostname == PRODUCTION_HOST,
                'expected_detail_shape': normalize_detail_url(final_url, base_url=detail_url) is not None,
                'keyword_visible': _normalize(keyword) in _normalize(body),
                'url': detail_url,
                'title': matches[0]['title'],
            }

        targets.append({
            'keyword': keyword,
            'search_attempts': attempts,
            'matching_details': matches[:3],
            'detail_probe': detail,
        })

    usable_targets = sum(
        1
        for target in targets
        if target['matching_details']
        and isinstance(target.get('detail_probe'), dict)
        and target['detail_probe'].get('status') == 200
        and target['detail_probe'].get('same_official_host') is True
        and target['detail_probe'].get('expected_detail_shape') is True
    )
    return {
        'observed_at': now.isoformat(),
        'official_host': PRODUCTION_HOST,
        'search_path': SEARCH_PATH,
        'search_date': search_date,
        'lookback_days': LOOKBACK_DAYS,
        'max_search_requests': MAX_SEARCH_REQUESTS,
        'max_detail_requests': MAX_DETAIL_REQUESTS,
        'search_request_count': search_request_count,
        'detail_request_count': detail_request_count,
        'usable_target_count': usable_targets,
        'target_count': len(TARGET_KEYWORDS),
        'targets': targets,
    }


def main() -> int:
    result = _probe()
    print('LIVE_CEB_PROBE=' + json.dumps(result, ensure_ascii=False, sort_keys=True))
    # This probe is intentionally diagnostic. A production site may reject an
    # automated GET even when the public browser page exists; that is evidence
    # about the adapter contract, not permission to fall back to third parties.
    return 0


if __name__ == '__main__':
    sys.exit(main())
