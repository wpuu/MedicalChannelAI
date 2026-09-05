from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'web' / 'pipeline' / 'scripts' / 'probe_ceb_official_search.py'
WORKFLOW = ROOT / '.github' / 'workflows' / 'verify.yml'

spec = importlib.util.spec_from_file_location('probe_ceb_official_search', SCRIPT)
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class CebOfficialProbeTests(unittest.TestCase):
    def test_baseline_contract_matches_public_list_shape(self) -> None:
        parsed = urlparse(probe.build_baseline_url())
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.hostname, 'bulletin.cebpubservice.com')
        self.assertEqual(parsed.path, '/xxfbcmses/search/bulletin.html')
        self.assertEqual(query['dates'], ['7'])
        self.assertEqual(query['categoryId'], ['88'])
        self.assertEqual(query['page'], ['1'])
        self.assertEqual(query['showStatus'], ['1'])

    def test_directed_search_reproduces_page_query_contract_and_is_bounded(self) -> None:
        url = probe.build_search_url(
            keyword='空气压力治疗仪',
            start_date='2026-07-23',
            end_date='2026-09-05',
        )
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.hostname, 'bulletin.cebpubservice.com')
        self.assertEqual(parsed.path, '/xxfbcmses/search/bulletin.html')
        self.assertEqual(query['word'], [quote('空气压力治疗仪', safe='')])
        self.assertEqual(query['categoryId'], ['88'])
        self.assertEqual(query['area'], ['天津'])
        self.assertEqual(query['showStatus'], ['1'])
        self.assertEqual(query['startcheckDate'], ['2026-07-23'])
        self.assertEqual(query['endcheckDate'], ['2026-09-05 23:59:59'])
        self.assertEqual(query['dates'], ['45'])
        self.assertLessEqual(probe.LOOKBACK_DAYS, 60)
        self.assertLessEqual(probe.MAX_NETWORK_REQUESTS, 4)
        self.assertLessEqual(probe.MAX_SEARCH_REQUESTS, 3)
        self.assertGreaterEqual(probe.MIN_REQUEST_DELAY_SECONDS, 3.0)

    def test_list_parser_keeps_uuid_title_region_and_viewer_link_only(self) -> None:
        bulletin_id = '01234567-89ab-cdef-0123-456789abcdef'
        html = f'''\
        <table>
          <tr><th>名称</th><th>行业</th><th>地区</th><th>来源</th><th>发布时间</th></tr>
          <tr>
            <td><a href="javascript:urlOpen('{bulletin_id}')">天津中医药大学第二附属医院空气压力治疗仪招标公告</a></td>
            <td>机械设备</td><td>【天津】</td><td>发布工具</td><td>2026-08-06</td>
          </tr>
        </table>
        '''
        rows = probe.parse_list_rows(html)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['bulletin_id'], bulletin_id)
        self.assertEqual(row['region'], '天津')
        self.assertEqual(row['published_at'], '2026-08-06')
        self.assertIn('空气压力治疗仪', row['title'])
        self.assertEqual(
            row['viewer_url'],
            'https://ctbpsp.com/#/bulletinDetail?uuid=01234567-89ab-cdef-0123-456789abcdef&inpvalue=&dataSource=0&tenderAgency=',
        )
        self.assertEqual(len(probe.matching_rows(rows, '空气压力治疗仪')), 1)

    def test_viewer_id_and_challenge_detection_fail_closed(self) -> None:
        self.assertIsNotNone(probe.build_viewer_url('0123456789abcdef0123456789abcdef'))
        self.assertIsNotNone(probe.build_viewer_url('01234567-89ab-cdef-0123-456789abcdef'))
        self.assertIsNone(probe.build_viewer_url('../bad'))
        self.assertIsNone(probe.build_viewer_url('not-a-real-uuid'))
        self.assertTrue(probe.looks_like_challenge('<html>VAPTCHA 人机验证</html>'))
        self.assertFalse(probe.looks_like_challenge('<table><tr><td>正常公告</td></tr></table>'))

    def test_workflow_probe_is_explicit_read_only_and_never_promotes_detail(self) -> None:
        workflow = WORKFLOW.read_text(encoding='utf-8')
        script = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('"[live-ceb-probe]"', workflow)
        self.assertIn('Run read-only live CEB official-search probe', workflow)
        self.assertIn("if: steps.verify_mode.outputs.live_ceb == 'true'", workflow)
        self.assertIn('probe_ceb_official_search.py', workflow)
        self.assertIn("PRODUCTION_HOST = 'bulletin.cebpubservice.com'", script)
        self.assertIn("VIEWER_HOST = 'ctbpsp.com'", script)
        self.assertIn("TIANJIN_AREA = '天津'", script)
        self.assertIn("TARGET_KEYWORDS = (", script)
        self.assertIn("'空气压力治疗仪'", script)
        self.assertIn("'高分辨液质联用系统维保服务'", script)
        self.assertIn("'adapter_promotion_allowed': False", script)
        self.assertIn("'ctbpsp_internal_detail_api_never_called': True", script)
        self.assertIn("'cookie_values_never_logged': True", script)
        self.assertIn("LIVE_CEB_PROBE=", script)
        self.assertNotIn('git push', workflow[workflow.index('Run read-only live CEB official-search probe'):])
        self.assertNotIn('VERIFIED_SNAPSHOT_PUBLISH', script)
        self.assertNotIn('customer_context', script)
        self.assertNotIn('hospital_relationship', script)


if __name__ == '__main__':
    unittest.main()
