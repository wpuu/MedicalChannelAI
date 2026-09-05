from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'web' / 'pipeline' / 'scripts' / 'probe_ceb_official_search.py'
WORKFLOW = ROOT / '.github' / 'workflows' / 'verify.yml'

spec = importlib.util.spec_from_file_location('probe_ceb_official_search', SCRIPT)
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class CebOfficialProbeTests(unittest.TestCase):
    def test_search_contract_is_https_tianjin_and_bounded(self) -> None:
        url = probe.build_search_url(keyword='空气压力治疗仪', search_date='2026-07-23')
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, 'https')
        self.assertEqual(parsed.hostname, 'bulletin.cebpubservice.com')
        self.assertEqual(parsed.path, '/xxfbcmses/search/bulletin.html')
        self.assertEqual(query['word'], ['空气压力治疗仪'])
        self.assertEqual(query['categoryId'], ['88'])
        self.assertEqual(query['area'], ['120000'])
        self.assertEqual(query['showStatus'], ['1'])
        self.assertLessEqual(probe.LOOKBACK_DAYS, 60)
        self.assertLessEqual(probe.MAX_SEARCH_REQUESTS, 4)
        self.assertLessEqual(probe.MAX_DETAIL_REQUESTS, 2)
        self.assertGreaterEqual(probe.MIN_REQUEST_DELAY_SECONDS, 3.0)

    def test_detail_links_fail_closed_to_official_shape(self) -> None:
        base = 'https://bulletin.cebpubservice.com/xxfbcmses/search/bulletin.html'
        good = '/biddingBulletin/2026-08-06/0123456789abcdef0123456789abcdef.html'
        self.assertEqual(
            probe.normalize_detail_url(good, base_url=base),
            'https://bulletin.cebpubservice.com' + good,
        )
        self.assertIsNone(
            probe.normalize_detail_url('https://example.com' + good, base_url=base)
        )
        self.assertIsNone(
            probe.normalize_detail_url('/other/2026-08-06/0123456789abcdef0123456789abcdef.html', base_url=base)
        )

    def test_workflow_probe_is_explicit_and_read_only(self) -> None:
        workflow = WORKFLOW.read_text(encoding='utf-8')
        script = SCRIPT.read_text(encoding='utf-8')
        self.assertIn('"[live-ceb-probe]"', workflow)
        self.assertIn('Run read-only live CEB official-search probe', workflow)
        self.assertIn("if: steps.verify_mode.outputs.live_ceb == 'true'", workflow)
        self.assertIn('probe_ceb_official_search.py', workflow)
        self.assertIn("PRODUCTION_HOST = 'bulletin.cebpubservice.com'", script)
        self.assertIn("TARGET_KEYWORDS = (", script)
        self.assertIn("'空气压力治疗仪'", script)
        self.assertIn("'高分辨液质联用系统维保服务'", script)
        self.assertIn("LIVE_CEB_PROBE=", script)
        self.assertNotIn('git push', workflow[workflow.index('Run read-only live CEB official-search probe'):])
        self.assertNotIn('VERIFIED_SNAPSHOT_PUBLISH', script)
        self.assertNotIn('customer_context', script)
        self.assertNotIn('hospital_relationship', script)


if __name__ == '__main__':
    unittest.main()
