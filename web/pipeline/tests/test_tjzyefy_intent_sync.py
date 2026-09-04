from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / 'scripts' / 'sync_tjzyefy_procurement_intent.py'
REPO_ROOT = Path(__file__).resolve().parents[3]
INCREMENTAL_PATH = REPO_ROOT / 'web' / 'collector_incremental.py'

spec = importlib.util.spec_from_file_location('sync_tjzyefy_procurement_intent', SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError('SYNC_TJZYEFY_INTENT_IMPORT_FAILED')
sync_intent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_intent)


class TjzyefyIntentSyncTests(unittest.TestCase):
    def test_publish_gate_blocks_index_or_unresolved_detail_failure(self) -> None:
        self.assertEqual(
            sync_intent.publish_gate(index_discovery_succeeded=False, unresolved_failure_count=0),
            (False, 'INDEX_DISCOVERY_FAILED'),
        )
        self.assertEqual(
            sync_intent.publish_gate(index_discovery_succeeded=True, unresolved_failure_count=1),
            (False, 'SUPPORTED_OR_UNKNOWN_DETAILS_INCOMPLETE'),
        )
        self.assertEqual(
            sync_intent.publish_gate(index_discovery_succeeded=True, unresolved_failure_count=0),
            (True, 'PASS'),
        )

    def test_nonmedical_intent_is_explicitly_unsupported(self) -> None:
        self.assertEqual(sync_intent.UNSUPPORTED_DETAIL_CODES, {'TJZYEFY_INTENT_NON_MEDICAL'})

    def test_only_transient_fetch_errors_retry(self) -> None:
        self.assertTrue(sync_intent.is_retryable_fetch_error(RuntimeError('TJZYEFY_NETWORK_ERROR')))
        self.assertTrue(sync_intent.is_retryable_fetch_error(RuntimeError('TJZYEFY_HTTP_503')))
        self.assertFalse(sync_intent.is_retryable_fetch_error(RuntimeError('TJZYEFY_HTTP_404')))
        self.assertFalse(sync_intent.is_retryable_fetch_error(ValueError('TJZYEFY_INTENT_TITLE_MISMATCH')))

    def test_transient_fetch_retries_once_then_succeeds(self) -> None:
        with (
            patch.object(
                sync_intent,
                'fetch_tjzyefy_page',
                side_effect=[RuntimeError('TJZYEFY_NETWORK_ERROR'), '<html>ok</html>'],
            ) as fetch,
            patch.object(sync_intent.time, 'sleep') as sleep,
        ):
            result = sync_intent.fetch_page_with_retry(
                'https://www.tjzyefy.com/xwgg/ggtz/',
                delay_seconds=3.0,
            )
        self.assertEqual(result, '<html>ok</html>')
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(3.0)

    def test_rate_limit_and_time_rules_are_bounded(self) -> None:
        self.assertGreaterEqual(sync_intent.MIN_DETAIL_DELAY_SECONDS, 3.0)
        with self.assertRaisesRegex(ValueError, 'timezone'):
            sync_intent.parse_as_of('2026-09-04T12:00:00')

    def test_intent_source_is_not_silently_added_to_intraday_scheduler(self) -> None:
        source = INCREMENTAL_PATH.read_text(encoding='utf-8')
        self.assertNotIn("'tjzyefy_intent'", source)
        self.assertNotIn('"tjzyefy_intent"', source)


if __name__ == '__main__':
    unittest.main()
