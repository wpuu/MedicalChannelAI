from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / 'scripts' / 'sync_tjzxfc_market_research.py'

spec = importlib.util.spec_from_file_location('sync_tjzxfc_market_research', SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError('SYNC_TJZXFC_IMPORT_FAILED')
sync_tjzxfc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_tjzxfc)


class TjzxfcSyncTests(unittest.TestCase):
    def test_publish_gate_blocks_index_failure_or_unresolved_detail(self) -> None:
        self.assertEqual(
            sync_tjzxfc.publish_gate(index_discovery_succeeded=False, unresolved_failure_count=0),
            (False, 'INDEX_DISCOVERY_FAILED'),
        )
        self.assertEqual(
            sync_tjzxfc.publish_gate(index_discovery_succeeded=True, unresolved_failure_count=1),
            (False, 'SUPPORTED_OR_UNKNOWN_DETAILS_INCOMPLETE'),
        )
        self.assertEqual(
            sync_tjzxfc.publish_gate(index_discovery_succeeded=True, unresolved_failure_count=0),
            (True, 'PASS'),
        )

    def test_non_medical_market_research_is_explicitly_unsupported(self) -> None:
        self.assertIn('TJZXFC_NON_MEDICAL_EARLY_SIGNAL', sync_tjzxfc.UNSUPPORTED_DETAIL_CODES)

    def test_only_transient_fetch_errors_retry(self) -> None:
        self.assertTrue(sync_tjzxfc.is_retryable_fetch_error(RuntimeError('TJZXFC_NETWORK_ERROR')))
        self.assertTrue(sync_tjzxfc.is_retryable_fetch_error(RuntimeError('TJZXFC_HTTP_503')))
        self.assertTrue(sync_tjzxfc.is_retryable_fetch_error(RuntimeError('TJZXFC_HTTP_429')))
        self.assertFalse(sync_tjzxfc.is_retryable_fetch_error(RuntimeError('TJZXFC_HTTP_404')))
        self.assertFalse(sync_tjzxfc.is_retryable_fetch_error(ValueError('TJZXFC_TITLE_MISMATCH')))

    def test_transient_fetch_retries_once_then_succeeds(self) -> None:
        with (
            patch.object(
                sync_tjzxfc,
                'fetch_tjzxfc_page',
                side_effect=[RuntimeError('TJZXFC_NETWORK_ERROR'), '<html>ok</html>'],
            ) as fetch,
            patch.object(sync_tjzxfc.time, 'sleep') as sleep,
        ):
            result = sync_tjzxfc.fetch_page_with_retry(
                'https://www.tjzxfc.cn/ywgk/zbgg/index.shtml',
                delay_seconds=3.0,
            )
        self.assertEqual(result, '<html>ok</html>')
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(3.0)

    def test_default_rate_limit_and_time_rules_are_bounded(self) -> None:
        self.assertGreaterEqual(sync_tjzxfc.MIN_DETAIL_DELAY_SECONDS, 3.0)
        with self.assertRaisesRegex(ValueError, 'timezone'):
            sync_tjzxfc.parse_as_of('2026-09-04T12:00:00')

    def test_source_is_not_silently_added_to_intraday_scheduler(self) -> None:
        runtime = (PIPELINE_ROOT.parent / 'collector_incremental.py').read_text(encoding='utf-8')
        self.assertNotIn("'tjzxfc'", runtime)
        self.assertNotIn('"tjzxfc"', runtime)


if __name__ == '__main__':
    unittest.main()
