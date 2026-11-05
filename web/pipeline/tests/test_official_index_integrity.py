from __future__ import annotations

import unittest
import io
from datetime import date
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from medical_channel_pipeline.official_index import decode_official_html
from medical_channel_pipeline import tjzyefy_discovery, tjzxfc_discovery

from medical_channel_pipeline.tjzyefy_discovery import (
    TjzyefyDiscoveryError, parse_tjzyefy_index_html, select_candidates_since,
)
from medical_channel_pipeline.tjzyefy_intent_discovery import (
    TjzyefyIntentDiscoveryError, parse_tjzyefy_intent_index_html,
)
from medical_channel_pipeline.tjzxfc_discovery import TjzxfcDiscoveryError, parse_tjzxfc_index_html


SOURCES = (
    (parse_tjzyefy_index_html, TjzyefyDiscoveryError, '天津中医药大学第二附属医院', '公告通知'),
    (parse_tjzyefy_intent_index_html, TjzyefyIntentDiscoveryError, '天津中医药大学第二附属医院', '公告通知'),
    (parse_tjzxfc_index_html, TjzxfcDiscoveryError, '天津市中心妇产科医院', '招标公告'),
)


class OfficialIndexIntegrityTests(unittest.TestCase):
    def test_frozen_current_gb2312_index_has_ten_real_announcements_and_five_detail_candidates(self):
        # Replay the captured official entry page's actual ten anchor titles
        # offline, preserving its declared GB2312 transport encoding.
        html = (Path(__file__).parent / 'fixtures' / 'tjzxfc_index_20261106_excerpt.html').read_text(encoding='utf-8')
        decoded = decode_official_html(html.encode('gb2312'))
        parser = tjzxfc_discovery._IndexParser()
        parser.feed(decoded)
        self.assertEqual(len(parser.links), 10)
        self.assertIn('天津市中心妇产科医院南开院区样本库改造项目调研公告', [title for _, title in parser.links])
        self.assertNotIn('\ufffd', decoded)
        # Generic research titles require detail verification too. Facility
        # repair candidates remain candidates, never automatically medical facts.
        candidates = parse_tjzxfc_index_html(decoded)
        self.assertEqual(len(candidates), 5)
        self.assertIn('天津市中心妇产科医院调研公告', [row.title for row in candidates])
        self.assertIn('天津市中心妇产科医院南开院区样本库改造项目调研公告', [row.title for row in candidates])
        self.assertTrue(all(not hasattr(row, 'facts') for row in candidates))

    def test_meta_gb2312_without_http_charset_is_decoded_before_discovery(self):
        html = '<meta http-equiv="Content-Type" content="text/html; charset=gb2312"><a href="/system/2026/09/28/030199113.shtml">院内市场调研公告-医疗设备采购项目</a>'
        raw = html.encode('gb2312')
        self.assertEqual(decode_official_html(raw), html)
        for module, fetch, parse in (
            (tjzyefy_discovery, tjzyefy_discovery.fetch_tjzyefy_page, parse_tjzyefy_index_html),
            (tjzxfc_discovery, tjzxfc_discovery.fetch_tjzxfc_page, parse_tjzxfc_index_html),
        ):
            with self.subTest(module=module.__name__):
                response = io.BytesIO(raw)
                response.headers = Message()
                response.headers['Content-Type'] = 'text/html'
                with patch.object(module, 'urlopen', return_value=response):
                    decoded = fetch(module.INDEX_URL)
                self.assertNotIn('\ufffd', decoded)
                self.assertEqual(len(parse(decoded)), 1)

    def test_utf8_header_and_invalid_encoding_do_not_silently_replace_characters(self):
        html = '<p>医疗设备采购公告</p>'
        self.assertEqual(decode_official_html(html.encode('utf-8'), http_charset='utf-8'), html)
        with self.assertRaisesRegex(ValueError, 'OFFICIAL_INDEX_ENCODING_INVALID'):
            decode_official_html(b'\xff\xfe\x81')

    def test_challenge_login_and_arbitrary_html_fail_closed(self):
        invalid_pages = (
            '', '<html></html>', '<html><h1>Welcome</h1><p>Nothing here</p></html>',
            '<title>访问验证</title><body>请开启JavaScript</body>',
            '<title>Just a moment...</title><script>location.reload()</script>',
            '<html><body>请输入验证码后继续访问</body></html>',
            '<form><input type="password"/><button>登录</button></form>',
            '<div id="app"></div><script src="/app.js"></script>',
            '<h1>暂无信息</h1>',
        )
        for parse, error, _, _ in SOURCES:
            for html in invalid_pages:
                with self.subTest(parser=parse.__name__, html=html):
                    with self.assertRaisesRegex(error, 'INDEX_RESPONSE_INVALID'):
                        parse(html)

    def test_challenge_or_password_page_cannot_pass_using_an_embedded_notice_link(self):
        link = '<a href="/system/2026/09/28/030199113.shtml">医疗设备采购调研公告</a>'
        for parse, error, _, _ in SOURCES:
            for html in ('<h1>访问验证</h1>' + link, '<input type="password">' + link,
                         '<title>Login</title>' + link, '<h1>登录</h1>' + link,
                         '<title>Checking your browser</title>' + link,
                         '<title>医院</title><p>请开启JavaScript</p>' + link):
                with self.subTest(parser=parse.__name__, html=html):
                    with self.assertRaisesRegex(error, 'INDEX_RESPONSE_INVALID'):
                        parse(html)

    def test_official_unrelated_announcements_are_valid_zero_relevance_results(self):
        html = '<ul><li><a href="/system/2026/08/04/030195986.shtml">办公桌采购公告</a></li></ul>'
        for parse, _, _, _ in SOURCES:
            with self.subTest(parser=parse.__name__):
                self.assertEqual(parse(html), [])

    def test_out_of_window_results_are_distinct_from_an_invalid_response(self):
        html = '<a href="/system/2026/08/04/030195986.shtml">院内调研公告-医疗设备采购项目</a>'
        rows = parse_tjzyefy_index_html(html)
        self.assertEqual(len(rows), 1)
        self.assertEqual(select_candidates_since(rows, start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30), max_candidates=20), [])

    def test_explicit_official_empty_list_is_valid_without_fabricating_candidates(self):
        for parse, _, hospital, column in SOURCES:
            with self.subTest(parser=parse.__name__):
                html = f'<h1>{hospital}</h1><h2>{column}</h2><ul class="notice-list"><li>暂无公告</li></ul>'
                self.assertEqual(parse(html), [])

    def test_empty_message_needs_hospital_column_and_identifiable_list_container(self):
        for parse, error, hospital, column in SOURCES:
            for html in (
                f'<h1>{hospital}</h1><h2>{column}</h2><p>暂无公告</p>',
                f'<h1>其他医院</h1><h2>{column}</h2><ul class="notice-list">暂无公告</ul>',
                f'<h1>{hospital}</h1><h2>新闻中心</h2><ul class="notice-list">暂无公告</ul>',
                f'<h1>{hospital}</h1><h2>{column}</h2><ul class="notice-list"></ul><footer>暂无公告</footer>',
            ):
                with self.subTest(parser=parse.__name__, html=html):
                    with self.assertRaisesRegex(error, 'INDEX_RESPONSE_INVALID'):
                        parse(html)

    def test_foreign_or_changed_detail_url_shapes_do_not_count_as_list_evidence(self):
        for parse, error, _, _ in SOURCES:
            for href in ('https://evil.example/system/2026/09/28/123.shtml', '/detail?id=123', '/system/2026/99/99/123.shtml'):
                with self.subTest(parser=parse.__name__, href=href):
                    with self.assertRaisesRegex(error, 'INDEX_RESPONSE_INVALID'):
                        parse(f'<a href="{href}">医疗设备采购公告</a>')


if __name__ == '__main__':
    unittest.main()
