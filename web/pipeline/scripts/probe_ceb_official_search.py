from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener
from zoneinfo import ZoneInfo

PRODUCTION_HOST = 'bulletin.cebpubservice.com'
VIEWER_HOST = 'ctbpsp.com'
HOMEPAGE_URL = f'https://{PRODUCTION_HOST}/'
SEARCH_PATH = '/xxfbcmses/search/bulletin.html'
TENDER_CATEGORY_ID = '88'
TIANJIN_AREA = '天津'
LOOKBACK_DAYS = 45
MAX_NETWORK_REQUESTS = 4
MAX_SEARCH_REQUESTS = 3
MIN_REQUEST_DELAY_SECONDS = 3.0
SHANGHAI = ZoneInfo('Asia/Shanghai')
TARGET_KEYWORDS = (
    '空气压力治疗仪',
    '高分辨液质联用系统维保服务',
)
UUID_RE = re.compile(
    r'^(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$'
)
URL_OPEN_RE = re.compile(r"urlOpen\(['\"]([^'\"]+)['\"]\)")


def _normalize(value: str) -> str:
    return re.sub(r'\s+', '', value or '')


def build_baseline_url() -> str:
    params = {
        'dates': '7',
        'categoryId': TENDER_CATEGORY_ID,
        'page': '1',
        'showStatus': '1',
    }
    return f'https://{PRODUCTION_HOST}{SEARCH_PATH}?{urlencode(params)}'


def build_search_url(
    *,
    keyword: str,
    start_date: str,
    end_date: str,
    area: str = TIANJIN_AREA,
    page: int = 1,
) -> str:
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    if end < start:
        raise ValueError('CEB_SEARCH_DATE_RANGE_INVALID')
    if not 1 <= page <= 500:
        raise ValueError('CEB_SEARCH_PAGE_OUT_OF_RANGE')
    dates = max(1, min(300, (end - start).days + 1))
    # The public list page's own script double-URI-encodes the keyword. quote()
    # performs the inner encoding; urlencode() below performs the outer layer.
    encoded_keyword = quote(keyword, safe='')
    params = {
        'searchDate': start.isoformat(),
        'dates': str(dates),
        'word': encoded_keyword,
        'categoryId': TENDER_CATEGORY_ID,
        'industryName': '',
        'area': area,
        'status': '',
        'publishMedia': '',
        'sourceInfo': '',
        'showStatus': '1',
        'startcheckDate': start.isoformat(),
        'endcheckDate': f'{end.isoformat()} 23:59:59',
        'page': str(page),
    }
    return f'https://{PRODUCTION_HOST}{SEARCH_PATH}?{urlencode(params)}'


def build_viewer_url(bulletin_id: str, *, keyword: str = '') -> str | None:
    bulletin_id = bulletin_id.strip()
    if not UUID_RE.fullmatch(bulletin_id):
        return None
    params = urlencode(
        {
            'uuid': bulletin_id,
            'inpvalue': keyword,
            'dataSource': '0',
            'tenderAgency': '',
        }
    )
    return f'https://{VIEWER_HOST}/#/bulletinDetail?{params}'


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, str | None]]] = []
        self._row: list[dict[str, str | None]] | None = None
        self._cell_text: list[str] | None = None
        self._cell_uuid: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered == 'tr':
            self._row = []
            return
        if lowered == 'td' and self._row is not None:
            self._cell_text = []
            self._cell_uuid = None
            return
        if lowered == 'a' and self._cell_text is not None:
            values = dict(attrs)
            candidate = values.get('href') or values.get('onclick') or ''
            match = URL_OPEN_RE.search(candidate)
            if match:
                self._cell_uuid = match.group(1).strip()

    def handle_data(self, data: str) -> None:
        if self._cell_text is not None and data.strip():
            self._cell_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == 'td' and self._row is not None and self._cell_text is not None:
            self._row.append(
                {
                    'text': ' '.join(self._cell_text).strip(),
                    'uuid': self._cell_uuid,
                }
            )
            self._cell_text = None
            self._cell_uuid = None
            return
        if lowered == 'tr' and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def parse_list_rows(html: str) -> list[dict[str, str]]:
    parser = _TableParser()
    parser.feed(html)
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for cells in parser.rows:
        if len(cells) < 5:
            continue
        bulletin_id = str(cells[0].get('uuid') or '').strip()
        title = str(cells[0].get('text') or '').strip()
        viewer_url = build_viewer_url(bulletin_id)
        if not viewer_url or not title or bulletin_id in seen:
            continue
        seen.add(bulletin_id)
        result.append(
            {
                'bulletin_id': bulletin_id,
                'title': title,
                'industry': str(cells[1].get('text') or '').strip(),
                'region': str(cells[2].get('text') or '').strip().strip('【】[]'),
                'publisher': str(cells[3].get('text') or '').strip(),
                'published_at': str(cells[4].get('text') or '').strip(),
                'viewer_url': viewer_url,
            }
        )
    return result


def matching_rows(rows: list[dict[str, str]], keyword: str) -> list[dict[str, str]]:
    needle = _normalize(keyword)
    return [row for row in rows if needle and needle in _normalize(row.get('title', ''))]


def looks_like_challenge(body: str) -> bool:
    lowered = body.lower()
    markers = ('vaptcha', 'verificationcode', '验证码', '人机验证')
    return any(marker in lowered for marker in markers)


def _page_signature(body: str) -> dict[str, object]:
    title_match = re.search(r'<title[^>]*>(.*?)</title>', body, flags=re.I | re.S)
    title = re.sub(r'\s+', ' ', title_match.group(1)).strip() if title_match else None
    return {
        'title': title,
        'has_table': '<table' in body.lower(),
        'has_url_open': bool(URL_OPEN_RE.search(body)),
        'challenge_detected': looks_like_challenge(body),
        'response_bytes': len(body.encode('utf-8')),
    }


def _make_session() -> tuple[object, CookieJar]:
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    return opener, jar


def _fetch(opener: object, url: str, *, referer: str | None = None) -> tuple[int, str, str, str | None]:
    request = Request(url, method='GET')
    request.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36')
    request.add_header('Accept', 'text/html,application/xhtml+xml')
    request.add_header('Accept-Language', 'zh-CN,zh;q=0.9')
    if referer:
        request.add_header('Referer', referer)
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read().decode('utf-8', errors='replace')
            return int(response.status), response.geturl(), body, response.headers.get('Content-Type')
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        return int(exc.code), exc.geturl(), body, exc.headers.get('Content-Type')
    except URLError as exc:
        return 0, url, f'{type(exc.reason).__name__}: {exc.reason}', None


def _official_list_response(status: int, final_url: str, body: str) -> bool:
    parsed = urlparse(final_url)
    signature = _page_signature(body)
    return bool(
        status == 200
        and parsed.hostname == PRODUCTION_HOST
        and signature['has_table'] is True
        and signature['challenge_detected'] is False
    )


def _probe() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    local_end = now.astimezone(SHANGHAI).date()
    local_start = local_end - timedelta(days=LOOKBACK_DAYS - 1)
    opener, jar = _make_session()
    network_request_count = 0

    homepage_status, homepage_final, homepage_body, homepage_type = _fetch(opener, HOMEPAGE_URL)
    network_request_count += 1
    homepage = {
        'status': homepage_status,
        'same_official_host': urlparse(homepage_final).hostname == PRODUCTION_HOST,
        'content_type': homepage_type,
        'cookie_names': sorted({cookie.name for cookie in jar}),
        **_page_signature(homepage_body),
    }

    time.sleep(MIN_REQUEST_DELAY_SECONDS)
    baseline_url = build_baseline_url()
    baseline_status, baseline_final, baseline_body, baseline_type = _fetch(
        opener,
        baseline_url,
        referer=HOMEPAGE_URL,
    )
    network_request_count += 1
    baseline_rows = (
        parse_list_rows(baseline_body)
        if _official_list_response(baseline_status, baseline_final, baseline_body)
        else []
    )
    baseline = {
        'status': baseline_status,
        'same_official_host': urlparse(baseline_final).hostname == PRODUCTION_HOST,
        'content_type': baseline_type,
        'row_count': len(baseline_rows),
        **_page_signature(baseline_body),
    }

    targets: list[dict[str, object]] = []
    for keyword in TARGET_KEYWORDS:
        if network_request_count >= MAX_NETWORK_REQUESTS:
            break
        time.sleep(MIN_REQUEST_DELAY_SECONDS)
        search_url = build_search_url(
            keyword=keyword,
            start_date=local_start.isoformat(),
            end_date=local_end.isoformat(),
        )
        status, final_url, body, content_type = _fetch(
            opener,
            search_url,
            referer=HOMEPAGE_URL,
        )
        network_request_count += 1
        usable = _official_list_response(status, final_url, body)
        rows = parse_list_rows(body) if usable else []
        matches = matching_rows(rows, keyword)
        targets.append(
            {
                'keyword': keyword,
                'status': status,
                'same_official_host': urlparse(final_url).hostname == PRODUCTION_HOST,
                'content_type': content_type,
                'row_count': len(rows),
                'matching_row_count': len(matches),
                'matches': matches[:3],
                **_page_signature(body),
            }
        )

    usable_target_count = sum(1 for target in targets if target['matching_row_count'])
    public_list_contract_usable = bool(
        baseline['status'] == 200
        and baseline['same_official_host'] is True
        and baseline['has_table'] is True
        and baseline['challenge_detected'] is False
    )
    return {
        'observed_at': now.isoformat(),
        'official_host': PRODUCTION_HOST,
        'viewer_host': VIEWER_HOST,
        'search_path': SEARCH_PATH,
        'lookback_days': LOOKBACK_DAYS,
        'search_start_date': local_start.isoformat(),
        'search_end_date': local_end.isoformat(),
        'max_network_requests': MAX_NETWORK_REQUESTS,
        'max_search_requests': MAX_SEARCH_REQUESTS,
        'network_request_count': network_request_count,
        'homepage': homepage,
        'baseline_list': baseline,
        'target_count': len(TARGET_KEYWORDS),
        'usable_target_count': usable_target_count,
        'public_list_contract_usable': public_list_contract_usable,
        'detail_contract_verified': False,
        'adapter_promotion_allowed': False,
        'targets': targets,
        'policy': {
            'normal_same_origin_cookie_session_only': True,
            'cookie_values_never_logged': True,
            'captcha_or_challenge_never_bypassed': True,
            'ctbpsp_internal_detail_api_never_called': True,
            'list_rows_are_discovery_evidence_only': True,
            'no_canonical_write': True,
            'no_lineage_write': True,
            'no_crm_write': True,
        },
    }


def main() -> int:
    result = _probe()
    print('LIVE_CEB_PROBE=' + json.dumps(result, ensure_ascii=False, sort_keys=True))
    # Diagnostic only. Even a usable public list is not enough to promote CEB
    # into the verified fact adapter because the detail contract remains unverified.
    return 0


if __name__ == '__main__':
    sys.exit(main())
