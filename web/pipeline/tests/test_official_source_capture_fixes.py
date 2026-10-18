"""Synthetic boundary mutations based on observed templates; no raw capture upload."""
from dataclasses import replace
from datetime import date, datetime, timezone
from email.message import Message
import hashlib
import json
import socket
import time
import unittest
from unittest.mock import Mock, patch

import collector_official_index as index
import collector_official_transport as transport


START, END = date(2026, 9, 18), date(2026, 10, 17)
OBSERVED = datetime(2026, 10, 17, 15, 55, tzinfo=timezone.utc)


def url(stage, day, number):
    host = 'www.tjzxfc.cn' if stage == 'tjzxfc' else 'www.tjzyefy.com'
    return f'https://{host}/system/{day:%Y/%m/%d}/{number}.shtml'


def row(stage, day=START, number='111', title='合成公告'):
    href = url(stage, day, number)
    inner = f'<a href="{href}" target="_blank">{title}</a>'
    if stage == 'tjzxfc':
        return ('<tr><td><li><table width="100%" border="0" cellspacing="0" cellpadding="0"><tr>'
                '<td style="font-size:28px;color:#666; padding-left:20px">'
                f'<a href="{href}" target="_blank">・ {inner}</a></td></tr></table></li></td></tr>')
    return ('<tr><td><table width="98%" height="2" border="0" cellpadding="0" cellspacing="0"">'
            '<tr><td width="3%" valign="top">&middot;</td><td width="80%" valign="bottom"">'
            f'<div align="left"><a href="{href}">{inner}</a></div></td>'
            '<td width="17%" align="right" valign="bottom"></td></tr></table></td></tr>')


def document(stage, *rows, outside=''):
    table = '<table width="100%">' + ''.join(rows) + '</table>'
    if stage == 'tjzxfc':
        container = '<ul id="xwzx-list">' + table + '</ul>'
    else:
        container = ('<td valign="top" bgcolor="#FFFFFF" class="hanggao26 zi14" style="padding:10px 30px">'
                     '<p>' + table + '</p><p align="center"><div id="pagetemple"></div>'
                     '<script src="https://www.tjzyefy.com/system/count/0002002/002000000000/'
                     'count_page_list_0002002002000000000.js"></script></p></td>')
    return '<html><body>' + outside + container + '</body></html>'


class CaptureFixTests(unittest.TestCase):
    def setUp(self):
        for name in ('connect', 'connect_ex'):
            guard = patch.object(socket.socket, name, side_effect=AssertionError('OFFLINE_ONLY'))
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch.object(socket, 'create_connection', side_effect=AssertionError('OFFLINE_ONLY'))
        guard.start()
        self.addCleanup(guard.stop)

    def decode(self, body, content_type='text/html'):
        headers = Message()
        headers['Content-Type'] = content_type
        return transport._decode_official_html(body, headers)

    def verify(self, stage, html, start=START):
        page = transport.OfficialPage(stage, transport.SOURCE_INDEXES[stage], html,
                                      hashlib.sha256(html.encode()).hexdigest(), OBSERVED)
        return index.verify_single_page_window(page, index.captured_index_shape(stage),
                                              start_date=start, end_date=END)

    def test_meta_gb2312_decodes_without_header_charset(self):
        html = '<html><head><meta http-equiv="Content-Type" content="text/html; charset=gb2312"></head><body>合成公告</body></html>'
        self.assertEqual(self.decode(html.encode('gb2312')), html)

    def test_header_only_and_modern_meta_allow_explicit_supported_charsets(self):
        for codec in ('utf-8', 'gb2312', 'gbk', 'gb18030'):
            with self.subTest(codec=codec):
                self.assertEqual(self.decode('公告'.encode(codec), 'text/html; charset='+codec), '公告')
                html = f'<head><META CHARSET="{codec}"></head><body>公告</body>'
                self.assertEqual(self.decode(html.encode(codec)), html)

    def test_missing_all_declarations_defaults_strict_utf8(self):
        self.assertEqual(self.decode('公告'.encode()), '公告')
        with self.assertRaisesRegex(transport.OfficialFetchError, 'PAGE_DECODE_FAILED'):
            self.decode(b'\xff')

    def test_aliases_and_utf8_bom_are_consistent(self):
        html = '<head><meta charset="utf8"></head><body>公告</body>'
        self.assertEqual(self.decode(b'\xef\xbb\xbf'+html.encode(), 'text/html; charset=UTF-8'), html)
        self.assertEqual(self.decode('<meta charset="gb_2312-80">公告'.encode('gb2312')), '<meta charset="gb_2312-80">公告')

    def test_header_meta_bom_or_multiple_meta_conflict_is_rejected(self):
        cases = [
            (b'<meta charset="gbk">', 'text/html; charset=utf-8'),
            (b'\xef\xbb\xbf<meta charset="gb2312">', 'text/html'),
            (b'<meta charset="gbk"><meta charset="utf-8">', 'text/html'),
        ]
        for body, header in cases:
            with self.subTest(body=body), self.assertRaisesRegex(transport.OfficialFetchError, 'CHARSET_CONFLICT'):
                self.decode(body, header)

    def test_unknown_empty_duplicate_or_ambiguous_declarations_are_rejected(self):
        cases = [(b'<meta charset="utf-7">', 'text/html'), (b'<meta charset>', 'text/html'),
                 (b'<meta charset="utf-8" charset="utf-8">', 'text/html'),
                 (b'x', 'text/html; charset=utf-8; charset=utf-8'),
                 (b'x', 'text/html; charset=unknown')]
        for body, header in cases:
            with self.subTest(body=body, header=header), self.assertRaisesRegex(transport.OfficialFetchError, 'CHARSET_REJECTED'):
                self.decode(body, header)
        headers = Message()
        headers['Content-Type'] = 'text/html'
        headers['Content-Type'] = 'text/html'
        with self.assertRaisesRegex(transport.OfficialFetchError, 'CHARSET_REJECTED'):
            transport._decode_official_html(b'x', headers)

    def test_comments_script_and_body_meta_do_not_choose_encoding(self):
        html = ('<head><!--<meta charset="gbk">--><script>var x="<meta charset=gbk>";</script>'
                '<meta charset="UTF-8"></head><body><meta charset="gbk">公告</body>')
        self.assertEqual(self.decode(html.encode()), html)

    def test_meta_scan_is_bounded_without_decode_replacement(self):
        body = b'<head>'+b' '*transport.CHARSET_SCAN_BYTES+b'<meta charset="gb2312"></head>'+ '公告'.encode('gb2312')
        with self.assertRaisesRegex(transport.OfficialFetchError, 'PAGE_DECODE_FAILED'):
            self.decode(body)

    def test_child_charset_conflict_is_preserved_as_nonretryable(self):
        result = json.dumps({'ok': False, 'error': 'OFFICIAL_CHARSET_CONFLICT', 'retryable': False}).encode()
        with patch.object(transport, '_run_bounded_worker', return_value=result):
            with self.assertRaisesRegex(transport.OfficialFetchError, 'CHARSET_CONFLICT') as caught:
                transport.fetch_official_page('tjzxfc', transport.SOURCE_INDEXES['tjzxfc'], deadline=time.monotonic()+10)
        self.assertFalse(caught.exception.retryable)

    def test_observed_templates_scope_both_hospitals_and_intent(self):
        for stage in transport.SOURCE_INDEXES:
            with self.subTest(stage=stage):
                window = self.verify(stage, document(stage, row(stage)))
                self.assertEqual(window.scoped_html.count('<a '), 1)
                self.assertIn('合成公告', window.scoped_html)

    def test_sidebar_links_do_not_prove_coverage_or_enter_scoped_html(self):
        for stage in transport.SOURCE_INDEXES:
            outside = f'<a href="{url(stage, date(2020,1,1),"999")}">侧栏旧记录</a>'
            with self.subTest(stage=stage), self.assertRaisesRegex(index.OfficialIndexError, 'WINDOW_NOT_COVERED'):
                self.verify(stage, document(stage, row(stage, END), outside=outside))
            self.assertNotIn('侧栏', self.verify(stage, document(stage, row(stage), outside=outside)).scoped_html)

    def test_duplicate_rows_and_host_alias_identity_are_rejected(self):
        for stage in transport.SOURCE_INDEXES:
            html = document(stage, row(stage), row(stage))
            alias = row(stage).replace('https://www.', 'https://')
            for raw in (html, document(stage, row(stage), alias)):
                with self.subTest(stage=stage), self.assertRaisesRegex(index.OfficialIndexError, 'STRUCTURE_UNKNOWN'):
                    self.verify(stage, raw)

    def test_nested_href_mismatch_extra_anchor_and_foreign_link_are_rejected(self):
        for stage in transport.SOURCE_INDEXES:
            raw = document(stage, row(stage))
            href = url(stage, START, '111')
            changes = [raw.replace(f'<a href="{href}" target="_blank">合成', '<a href="https://evil.example/" target="_blank">合成'),
                       raw.replace('合成公告</a>', '合成公告<a href="'+href+'">额外</a></a>'),
                       raw.replace(href, 'https://evil.example/system/2026/09/18/111.shtml')]
            for html in changes:
                with self.subTest(stage=stage), self.assertRaises(index.OfficialIndexError):
                    self.verify(stage, html)

    def test_unknown_missing_duplicate_unclosed_and_empty_containers_are_rejected(self):
        for stage in transport.SOURCE_INDEXES:
            raw = document(stage, row(stage))
            marker = 'xwzx-list' if stage == 'tjzxfc' else 'hanggao26 zi14'
            changes = [document(stage), raw.replace(marker, 'other'), raw+raw,
                       raw[:raw.rfind('</ul>')] if stage == 'tjzxfc' else raw[:raw.rfind('</td>')],
                       raw.replace('width="100%"', 'width="90%"', 1)]
            for html in changes:
                with self.subTest(stage=stage), self.assertRaises(index.OfficialIndexError):
                    self.verify(stage, html)

    def test_out_of_order_future_and_invalid_dates_do_not_create_coverage(self):
        for stage in transport.SOURCE_INDEXES:
            changes = [document(stage, row(stage), row(stage, END, '222')),
                       document(stage, row(stage, date(2026,10,18)), row(stage, START, '222')),
                       document(stage, row(stage)).replace('/2026/09/18/', '/2026/09/31/')]
            for html in changes:
                with self.subTest(stage=stage), self.assertRaises(index.OfficialIndexError):
                    self.verify(stage, html)

    def test_duplicate_attributes_and_unexpected_content_are_rejected(self):
        for stage in transport.SOURCE_INDEXES:
            raw = document(stage, row(stage))
            changes = [raw.replace('<table width="100%">', '<table width="100%" width="100%">', 1),
                       raw.replace('合成公告', '<script>fake()</script>'),
                       raw.replace('<tr><td>', '<tr>未知<td>', 1)]
            for html in changes:
                with self.subTest(stage=stage), self.assertRaises(index.OfficialIndexError):
                    self.verify(stage, html)

    def test_cms_quote_exception_is_limited_to_observed_positions(self):
        stage = 'tjzyefy'
        self.verify(stage, document(stage, row(stage)).replace('cellspacing="0""', 'cellspacing="0"').replace('valign="bottom""', 'valign="bottom"'))
        with self.assertRaises(index.OfficialIndexError):
            self.verify(stage, document(stage, row(stage)).replace('<div align="left">', '<div align="left"">'))

    def test_pagination_script_is_never_executed_or_used_as_end_proof(self):
        stage = 'tjzyefy'
        raw = document(stage, row(stage, END))
        with self.assertRaisesRegex(index.OfficialIndexError, 'WINDOW_NOT_COVERED'):
            self.verify(stage, raw)
        for html in (raw.replace('count_page_list_0002002002000000000.js', 'unknown.js'),
                     raw.replace('</script>', 'fake()</script>')):
            with self.assertRaisesRegex(index.OfficialIndexError, 'STRUCTURE_UNKNOWN'):
                self.verify(stage, html)

    def test_tree_depth_and_node_count_are_bounded(self):
        stage = 'tjzxfc'
        for label, html in [('depth', document(stage, row(stage, title='<span>'*50+'公告'+'</span>'*50))),
                            ('nodes', document(stage, *(row(stage, number=str(n)) for n in range(600))))]:
            with self.subTest(limit=label), self.assertRaisesRegex(index.OfficialIndexError, 'STRUCTURE_UNKNOWN'):
                self.verify(stage, html)

    def test_shapes_cannot_register_or_change_source_identity(self):
        for stage in transport.SOURCE_INDEXES:
            self.assertEqual(len(index._REGISTERED_INDEX_CONTRACTS), 0)
            with self.assertRaisesRegex(index.OfficialIndexError, 'CONTRACT_UNVERIFIED'):
                index.registered_index_contract(stage)
            shape = replace(index.captured_index_shape(stage), container_id='changed')
            with self.assertRaises(index.OfficialIndexError):
                index._extract_rows(shape, document(stage, row(stage)))
