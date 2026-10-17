from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / 'scripts' / 'sync_tjzyefy_market_research.py'
REPO_ROOT = Path(__file__).resolve().parents[3]
INCREMENTAL_PATH = REPO_ROOT / 'web' / 'collector_incremental.py'

spec = importlib.util.spec_from_file_location('sync_tjzyefy_market_research', SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError('SYNC_TJZYEFY_IMPORT_FAILED')
sync_tjzyefy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_tjzyefy)


class TjzyefySyncTests(unittest.TestCase):
    def test_publish_gate_blocks_index_failure(self) -> None:
        allowed, reason = sync_tjzyefy.publish_gate(
            index_discovery_succeeded=False,
            selected_candidate_count=0,
            new_verified_record_count=0,
            unresolved_failure_count=0,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, 'INDEX_DISCOVERY_FAILED')

    def test_publish_gate_blocks_unresolved_supported_detail(self) -> None:
        allowed, reason = sync_tjzyefy.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=1,
            new_verified_record_count=1,
            unresolved_failure_count=1,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, 'SUPPORTED_DETAILS_INCOMPLETE')

    def test_publish_gate_allows_complete_or_historically_covered_refresh(self) -> None:
        allowed, reason = sync_tjzyefy.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=0,
            new_verified_record_count=0,
            unresolved_failure_count=0,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, 'PASS')

    def test_publish_gate_blocks_when_all_selected_details_fail_even_if_history_exists(self) -> None:
        allowed, reason = sync_tjzyefy.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=2,
            new_verified_record_count=0,
            unresolved_failure_count=0,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, 'NO_SELECTED_DETAIL_VERIFIED')

    def test_only_transient_fetch_errors_are_retryable(self) -> None:
        self.assertTrue(sync_tjzyefy.is_retryable_fetch_error(RuntimeError('TJZYEFY_NETWORK_ERROR')))
        self.assertTrue(sync_tjzyefy.is_retryable_fetch_error(RuntimeError('TJZYEFY_HTTP_503')))
        self.assertTrue(sync_tjzyefy.is_retryable_fetch_error(RuntimeError('TJZYEFY_HTTP_429')))
        self.assertFalse(sync_tjzyefy.is_retryable_fetch_error(RuntimeError('TJZYEFY_HTTP_404')))
        self.assertFalse(sync_tjzyefy.is_retryable_fetch_error(ValueError('TJZYEFY_TITLE_MISMATCH')))

    def test_transient_fetch_retries_once_then_succeeds(self) -> None:
        with (
            patch.object(
                sync_tjzyefy,
                'fetch_tjzyefy_page',
                side_effect=[RuntimeError('TJZYEFY_NETWORK_ERROR'), '<html>ok</html>'],
            ) as fetch,
            patch.object(sync_tjzyefy.time, 'sleep') as sleep,
        ):
            result = sync_tjzyefy.fetch_page_with_retry(
                'https://www.tjzyefy.com/xwgg/ggtz/',
                delay_seconds=3.0,
            )
        self.assertEqual(result, '<html>ok</html>')
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(3.0)

    def test_minimum_delay_and_procurement_intent_boundary_are_explicit(self) -> None:
        self.assertGreaterEqual(sync_tjzyefy.MIN_DETAIL_DELAY_SECONDS, 3.0)
        self.assertIn('TJZYEFY_PROCUREMENT_INTENT_NOT_SUPPORTED', sync_tjzyefy.UNSUPPORTED_DETAIL_CODES)

    def test_source_is_not_silently_added_to_intraday_scheduler(self) -> None:
        source = INCREMENTAL_PATH.read_text(encoding='utf-8')
        self.assertNotIn("'tjzyefy'", source)
        self.assertNotIn('"tjzyefy"', source)

    def test_parse_as_of_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, 'timezone'):
            sync_tjzyefy.parse_as_of('2026-09-04T12:00:00')


if __name__ == '__main__':
    unittest.main()
