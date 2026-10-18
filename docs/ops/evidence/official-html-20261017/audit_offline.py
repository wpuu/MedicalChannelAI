"""Audit the four separately authorized, local captures; no HTTP or cache writes.

Raw pages remain local, outside Git. Run with --captures pointing at the saved
batch directory; this script has no fetching fallback and requires all hashes.
"""
from argparse import ArgumentParser
from datetime import date, datetime, timedelta
from email.message import Message
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import socket
import sys
import time
from unittest.mock import Mock, patch
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'web'))
sys.path.insert(0, str(REPO / 'web/pipeline'))


def audit(root):
    import collector_official_index as index
    import collector_official_transport as transport
    from medical_channel_pipeline import tjzyefy_discovery as research
    from medical_channel_pipeline import tjzyefy_intent_discovery as intent
    from medical_channel_pipeline import tjzxfc_discovery as maternity
    from medical_channel_pipeline.tjzyefy_market_research import parse_tjzyefy_market_research
    from medical_channel_pipeline.public_snapshot import _actionability

    manifest = json.loads((root / 'batch.json').read_text())
    assert manifest['status'] == 'COMPLETED_FOUR_ATTEMPTS_NO_RETRY'
    assert len(manifest['results']) == 4
    pages, evidence = {}, []
    previous_end = None
    for source in manifest['results']:
        assert source['attempt'] == 1 and source['http_status'] == 200
        assert source['accepted_official_html'] is True and source['redirects_followed'] == 0
        body = (root / source['body_file']).read_bytes()
        assert len(body) < 1048576 and hashlib.sha256(body).hexdigest() == source['body_sha256']
        start = datetime.fromisoformat(source['started_at_utc'])
        end = datetime.fromisoformat(source['finished_at_utc'])
        assert 0 <= (end - start).total_seconds() < 20
        if previous_end is not None:
            assert (start - previous_end).total_seconds() >= 3
        previous_end = end
        # Diagnostic decoding of saved bytes, not a change to the transport.
        match = re.search(r'charset\s*=\s*["\x27]?\s*([\w-]+)',
                          body[:4096].decode('ascii', errors='ignore'), re.I)
        meta_charset = match.group(1).lower() if match else None
        charset = source.get('declared_charset') or meta_charset or 'utf-8'
        text = body.decode(charset, errors='strict')
        name = Path(source['body_file']).stem
        pages[name] = (source, body, text)
        evidence.append({
            'name': name, 'url': source['url'], 'http_status': 200,
            'observed_at_utc': source['finished_at_utc'], 'bytes': len(body),
            'raw_sha256': source['body_sha256'], 'http_charset': source.get('declared_charset'),
            'meta_charset': meta_charset, 'diagnostic_decoding': charset,
            'decoded_utf8_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        })

    index_results = []
    for name, stage in [('tjzyefy-index', 'tjzyefy'), ('tjzxfc-index', 'tjzxfc')]:
        source, _, text = pages[name]
        parser = research._IndexParser()
        parser.feed(text)
        rows = []
        for href, title in parser.links:
            url = urljoin(source['url'], href)
            match = re.fullmatch(r'/system/(20\d{2})/(\d{2})/(\d{2})/(\d+)\.shtml', urlsplit(url).path)
            if match and urlsplit(url).hostname == urlsplit(source['url']).hostname:
                rows.append({'url': url, 'title': title,
                             'date': date(*(int(v) for v in match.groups()[:3])).isoformat()})
        observed = datetime.fromisoformat(source['finished_at_utc'])
        end_date = observed.astimezone(ZoneInfo('Asia/Shanghai')).date()
        start_date = end_date - timedelta(days=29)
        assert rows
        index_results.append({
            'source': stage, 'row_analysis': 'unscoped diagnostic only, not a registered coverage proof',
            'dated_links': len(rows), 'unique_dated_urls': len({r['url'] for r in rows}),
            'newest_date': max(r['date'] for r in rows), 'oldest_date': min(r['date'] for r in rows),
            'requested_start_date': start_date.isoformat(), 'requested_end_date': end_date.isoformat(),
            'single_page_reaches_start': min(r['date'] for r in rows) <= start_date.isoformat(),
            'pagination_scripts_not_fetched': re.findall(
                r'<script\b[^>]*src=["\x27]([^"\x27]*count_page_list_[^"\x27]*)', text, re.I),
        })
    assert all(not r['single_page_reaches_start'] for r in index_results)

    counts = {
        'tjzyefy': len(research.parse_tjzyefy_index_html(pages['tjzyefy-index'][2])),
        'tjzyefy_intent': len(intent.parse_tjzyefy_intent_index_html(pages['tjzyefy-index'][2])),
        'tjzxfc': len(maternity.parse_tjzxfc_index_html(pages['tjzxfc-index'][2])),
    }
    assert counts == {'tjzyefy': 2, 'tjzyefy_intent': 14, 'tjzxfc': 1}

    detail_results = []
    for name in ['tjzyefy-20260928-030199113', 'tjzyefy-20260930-030199248']:
        source, _, text = pages[name]
        title = re.search(r'<title[^>]*>(.*?)</title>', text, re.S | re.I).group(1).strip()
        published = '-'.join(urlsplit(source['url']).path.split('/')[2:5])
        result = {'sample': name, 'expected_title_source': 'saved detail title; historical index pairing NOT verified'}
        try:
            record = parse_tjzyefy_market_research(
                text, source_url=source['url'], index_url=transport.SOURCE_INDEXES['tjzyefy'],
                index_published_at=published, expected_title=title,
                observed_at=source['finished_at_utc'], opportunity_id=research.stable_opportunity_id(source['url']))
        except ValueError as exc:
            result.update(outcome='REJECTED', reason=str(exc))
            assert name.endswith('030199248') and str(exc) == 'TJZYEFY_NOT_MARKET_RESEARCH'
            local_anchor = '<a href="' + source['url'] + '">' + title + '</a>'
            result['constructed_anchor_discovery_count'] = len(research.parse_tjzyefy_index_html(local_anchor))
            result['anchor_is_captured_index'] = False
            assert result['constructed_anchor_discovery_count'] == 0
        else:
            assert name.endswith('030199113')
            assert record['facts']['registration_deadline'] == '2026-10-09T16:00:00+08:00'
            assert len(record['facts']['product_items']) == 17
            current = _actionability(record['facts'], datetime.fromisoformat(source['finished_at_utc']))
            historical = _actionability(record['facts'], datetime(2026, 9, 29, 8, 20, tzinfo=ZoneInfo('Asia/Shanghai')))
            assert current[0] == 'ARCHIVE' and historical[0] == 'PUBLIC_OPPORTUNITY'
            result.update(outcome='PARSER_DIAGNOSTIC_ONLY_NOT_CANONICAL', product_count=17,
                          deadline=record['facts']['registration_deadline'],
                          current_actionability=current, historical_actionability=historical)
        detail_results.append(result)

    source, body, text = pages['tjzxfc-index']
    headers = Message()
    headers['Content-Type'] = source['response_headers']['content-type']
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.status, response.headers = 200, headers
    response.geturl.return_value, response.read.return_value = source['url'], body
    with patch.object(transport, 'build_opener', return_value=Mock(open=Mock(return_value=response))):
        try:
            transport._worker_fetch('tjzxfc', source['url'], time.monotonic() + 10)
        except transport.OfficialFetchError as exc:
            charset_replay = str(exc)
        else:
            raise AssertionError('Expected the current UTF-8 default to reject saved GB2312 bytes')
    assert charset_replay == 'OFFICIAL_PAGE_DECODE_FAILED'
    try:
        index._extract_rows(index.IndexShape('tjzxfc', source['url'], 'ul', 'xwzx-list'), text)
    except index.OfficialIndexError as exc:
        structure_replay = str(exc)
    else:
        raise AssertionError('Expected table-wrapped children and nested anchors to be rejected')
    assert structure_replay == 'OFFICIAL_INDEX_STRUCTURE_UNKNOWN'
    assert not index._REGISTERED_INDEX_CONTRACTS
    return {
        'repository': 'wpuu/MedicalChannelAI', 'product_head': 'c0d0215d99a8f109cfe62a313f0bf6daf9d8a771',
        'capture_root_local_only': str(root), 'raw_html_in_git': False,
        'source_requests_in_this_offline_audit': 0, 'network_connections_blocked': True,
        'captures': evidence, 'indexes': index_results, 'unscoped_discovery_counts': counts,
        'intent_limit': {'configured_max_details': 3, 'observed_first_page_candidates': 14,
                         'full_window_unknown': True, 'stage_was_not_invoked_with_fake_window': True},
        'details': detail_results, 'current_transport_replay': charset_replay,
        'current_index_shape_replay': structure_replay, 'official_contracts_registered': 0,
        'full_verify': 'NOT_RUN', 'independent_review': 'PENDING', 'release': 'BLOCKED',
    }


if __name__ == '__main__':
    args = ArgumentParser()
    args.add_argument('--captures', type=Path, required=True)
    parsed = args.parse_args()
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('OFFLINE_ONLY')), \
         patch.object(socket.socket, 'connect_ex', side_effect=AssertionError('OFFLINE_ONLY')), \
         patch.object(socket, 'create_connection', side_effect=AssertionError('OFFLINE_ONLY')):
        result = audit(parsed.captures.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
