#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medical_channel_pipeline.ccgp_discovery import (  # noqa: E402
    _SearchListParser,
    build_search_url,
    fetch_search_page,
    parse_search_html,
)

SHANGHAI = ZoneInfo('Asia/Shanghai')


def main() -> int:
    parser = argparse.ArgumentParser(description='Low-volume diagnostic for the current CCGP search HTML shape.')
    parser.add_argument('--as-of', required=True)
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of.replace('Z', '+00:00')).astimezone(SHANGHAI)
    end_date = as_of.date()
    start_date = end_date - timedelta(days=2)
    url = build_search_url(
        keyword='医院',
        notice_type='公开招标',
        page_index=1,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        region='北京',
    )
    try:
        html = fetch_search_page(url)
    except Exception as exc:
        print(json.dumps({
            'diagnostic': 'CCGP_SEARCH_FETCH_FAILED',
            'error': type(exc).__name__,
            'message': str(exc)[:240],
        }, ensure_ascii=False))
        return 0

    parsed = parse_search_html(html, keyword='医院')
    raw_parser = _SearchListParser()
    raw_parser.feed(html)
    cggg_links = re.findall(r'href=["\']([^"\']*/cggg/[^"\']+)["\']', html, flags=re.I)
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, flags=re.I | re.S)
    title = re.sub(r'\s+', ' ', title_match.group(1)).strip()[:160] if title_match else None
    print(json.dumps({
        'diagnostic': 'CCGP_SEARCH_HTML_SHAPE',
        'html_bytes': len(html.encode('utf-8')),
        'page_title': title,
        'legacy_result_marker': 'vT-srch-result-list-bid' in html,
        'legacy_result_marker_count': html.count('vT-srch-result-list-bid'),
        'cggg_link_count': len(cggg_links),
        'parser_candidate_count': len(parsed),
        'sample_cggg_paths': cggg_links[:3],
        'sample_candidates': [
            {
                'title': item.title[:100],
                'region': item.region,
                'buyer_name': item.buyer_name,
                'notice_type': item.notice_type,
            }
            for item in parsed[:5]
        ],
        'sample_row_meta': [
            {'title': row_title[:100], 'meta': row_meta[:300]}
            for row_title, _href, row_meta in raw_parser.rows[:5]
        ],
        'contains_no_result_text': any(token in html for token in ('没有相关记录', '暂无相关', '未搜索到')),
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
