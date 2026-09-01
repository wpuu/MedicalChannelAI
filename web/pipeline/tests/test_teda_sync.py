from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / 'scripts' / 'sync_teda_market_research.py'

spec = importlib.util.spec_from_file_location('sync_teda_market_research', SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError('SYNC_TEDA_IMPORT_FAILED')
sync_teda = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_teda)


class TedaSyncTests(unittest.TestCase):
    def test_only_transient_fetch_errors_are_retryable(self) -> None:
        self.assertTrue(sync_teda.is_retryable_fetch_error(RuntimeError('TEDA_NETWORK_ERROR')))
        self.assertTrue(sync_teda.is_retryable_fetch_error(RuntimeError('TEDA_HTTP_503')))
        self.assertTrue(sync_teda.is_retryable_fetch_error(RuntimeError('TEDA_HTTP_429')))
        self.assertFalse(sync_teda.is_retryable_fetch_error(RuntimeError('TEDA_HTTP_404')))
        self.assertFalse(sync_teda.is_retryable_fetch_error(ValueError('TEDA_PRODUCT_SECTION_NOT_FOUND')))

    def test_transient_fetch_retries_once_then_succeeds(self) -> None:
        with (
            patch.object(
                sync_teda,
                'fetch_teda_page',
                side_effect=[RuntimeError('TEDA_NETWORK_ERROR'), '<html>ok</html>'],
            ) as fetch,
            patch.object(sync_teda.time, 'sleep') as sleep,
        ):
            result = sync_teda.fetch_page_with_retry(
                'https://www.tedahospital.com.cn/article/plist/9',
                delay_seconds=3.0,
            )
        self.assertEqual(result, '<html>ok</html>')
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(3.0)

    def test_non_retryable_fetch_fails_without_sleep(self) -> None:
        with (
            patch.object(
                sync_teda,
                'fetch_teda_page',
                side_effect=RuntimeError('TEDA_HTTP_404'),
            ) as fetch,
            patch.object(sync_teda.time, 'sleep') as sleep,
            self.assertRaisesRegex(RuntimeError, 'TEDA_HTTP_404'),
        ):
            sync_teda.fetch_page_with_retry(
                'https://www.tedahospital.com.cn/article/plist/9',
                delay_seconds=3.0,
            )
        self.assertEqual(fetch.call_count, 1)
        sleep.assert_not_called()

    def test_discovery_deduplicates_same_article_across_pages(self) -> None:
        page = '''
        <html><body>
          <a href="/article/show/9/901">天津市泰达医院生物安全柜设备需求调研</a>
        </body></html>
        '''
        with (
            patch.object(sync_teda, 'fetch_page_with_retry', return_value=page),
            patch.object(sync_teda.time, 'sleep'),
        ):
            candidates = sync_teda.discover_candidates(index_pages=2, delay_seconds=3.0)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(sync_teda.stable_opportunity_id(candidates[0].detail_url), 'teda_901')

    def test_parse_as_of_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, 'timezone'):
            sync_teda.parse_as_of('2026-09-02T03:00:00')

    def test_minimum_request_delay_is_three_seconds(self) -> None:
        self.assertGreaterEqual(sync_teda.MIN_REQUEST_DELAY_SECONDS, 3.0)


if __name__ == '__main__':
    unittest.main()
