"""Replay existing local captures; no download, registration, or publication."""
from argparse import ArgumentParser
from datetime import date, datetime, timedelta
from email.message import Message
import hashlib
from html import escape
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[4]
for path in ('web', 'web/pipeline'):
    sys.path.insert(0, str(ROOT / path))


def replay(captures):
    import collector_official_index as index
    import collector_official_transport as transport
    from medical_channel_pipeline import tjzyefy_discovery as research
    from medical_channel_pipeline import tjzyefy_intent_discovery as intent
    from medical_channel_pipeline import tjzxfc_discovery as maternity

    previous = json.loads((ROOT / 'docs/ops/evidence/official-html-20261017/audit-result.json').read_text())
    prior_hash = {entry['name']: entry['decoded_utf8_sha256'] for entry in previous['captures']}
    batch = json.loads((captures / 'batch.json').read_text())
    assert len(batch['results']) == 4
    decoded, pages = {}, []
    for result in batch['results']:
        body = (captures / result['body_file']).read_bytes()
        assert result['http_status'] == 200 and hashlib.sha256(body).hexdigest() == result['body_sha256']
        headers = Message()
        for key, value in result['response_headers'].items():
            headers[key] = value
        text = transport._decode_official_html(body, headers)
        name = Path(result['body_file']).stem
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        assert digest == prior_hash[name]
        decoded[name] = (text, result)
        pages.append({'name': name, 'raw_sha256': result['body_sha256'],
                      'decoded_utf8_sha256': digest, 'matches_previous_strict_diagnostic_decode': True})

    windows, counts = [], {}
    for stage in transport.SOURCE_INDEXES:
        name = 'tjzxfc-index' if stage == 'tjzxfc' else 'tjzyefy-index'
        text, result = decoded[name]
        shape = index.captured_index_shape(stage)
        rows = index._extract_rows(shape, text)
        observed = datetime.fromisoformat(result['finished_at_utc'])
        end = observed.astimezone(ZoneInfo('Asia/Shanghai')).date()
        start = end - timedelta(days=29)
        page = transport.OfficialPage(stage, result['url'], text,
                                      hashlib.sha256(text.encode()).hexdigest(), observed)
        try:
            index.verify_single_page_window(page, shape, start_date=start, end_date=end)
        except index.OfficialIndexError as exc:
            reason = str(exc)
        else:
            raise AssertionError('A short saved page must not prove a full window')
        assert reason == 'OFFICIAL_INDEX_WINDOW_NOT_COVERED'
        try:
            index.verify_registered_source_window(page, start_date=start, end_date=end)
        except index.OfficialIndexError as exc:
            registered_reason = str(exc)
        else:
            raise AssertionError('No official source is registered')
        assert registered_reason == 'OFFICIAL_INDEX_CONTRACT_UNVERIFIED'
        # Diagnostic row projection only: no window capability or stage invocation.
        scoped = ''.join(f'<a href="{escape(url, quote=True)}">{escape(title)}</a>' for url, title, _ in rows)
        discover = {'tjzyefy': research.parse_tjzyefy_index_html,
                    'tjzyefy_intent': intent.parse_tjzyefy_intent_index_html,
                    'tjzxfc': maternity.parse_tjzxfc_index_html}[stage]
        counts[stage] = len(discover(scoped, index_url=shape.index_url))
        windows.append({'stage': stage, 'logical_rows': len(rows), 'oldest_date': rows[-1][2].isoformat(),
                        'requested_start_date': start.isoformat(), 'window_result': reason,
                        'registered_result': registered_reason})
    assert counts == {'tjzyefy': 2, 'tjzyefy_intent': 14, 'tjzxfc': 1}
    assert not index._REGISTERED_INDEX_CONTRACTS
    return {'raw_capture_root_local_only': str(captures), 'source_requests': 0,
            'raw_html_in_git': False, 'capture_decode': pages, 'row_and_window_checks': windows,
            'scoped_diagnostic_discovery_counts': counts, 'official_contracts_registered': 0,
            'intent_limit_remains': 3, 'intent_14_requires_continuation': True,
            'stage_invocations': 0, 'model_calls': 0, 'release': 'BLOCKED'}


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--captures', type=Path, required=True)
    args = parser.parse_args()
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('OFFLINE_ONLY')), \
         patch.object(socket.socket, 'connect_ex', side_effect=AssertionError('OFFLINE_ONLY')), \
         patch.object(socket, 'create_connection', side_effect=AssertionError('OFFLINE_ONLY')):
        result = replay(args.captures.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
