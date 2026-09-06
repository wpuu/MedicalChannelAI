from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / 'scripts' / 'sync_tjmugh_market_research.py'

spec = importlib.util.spec_from_file_location('sync_tjmugh_market_research', SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError('SYNC_TJMUGH_IMPORT_FAILED')
sync_tjmugh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_tjmugh)


class TjmughSyncTests(unittest.TestCase):
    def test_publish_gate_blocks_index_discovery_failure(self) -> None:
        allowed, reason = sync_tjmugh.publish_gate(
            index_discovery_succeeded=False,
            selected_candidate_count=0,
            new_verified_record_count=0,
            missing_selected_count=0,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, 'INDEX_DISCOVERY_FAILED')

    def test_publish_gate_allows_successful_empty_index_window(self) -> None:
        allowed, reason = sync_tjmugh.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=0,
            new_verified_record_count=0,
            missing_selected_count=0,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, 'PASS')

    def test_publish_gate_blocks_when_all_selected_details_fail(self) -> None:
        allowed, reason = sync_tjmugh.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=3,
            new_verified_record_count=0,
            missing_selected_count=3,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, 'ALL_SELECTED_DETAILS_FAILED_VERIFICATION')

    def test_publish_gate_blocks_partial_refresh_when_selected_record_is_missing(self) -> None:
        allowed, reason = sync_tjmugh.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=3,
            new_verified_record_count=1,
            missing_selected_count=2,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, 'SELECTED_DETAILS_INCOMPLETE')

    def test_publish_gate_allows_partial_current_fetch_when_historical_verified_state_covers_rest(self) -> None:
        allowed, reason = sync_tjmugh.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=3,
            new_verified_record_count=1,
            missing_selected_count=0,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, 'PASS')

    def test_publish_gate_allows_complete_current_refresh(self) -> None:
        allowed, reason = sync_tjmugh.publish_gate(
            index_discovery_succeeded=True,
            selected_candidate_count=3,
            new_verified_record_count=3,
            missing_selected_count=0,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, 'PASS')

    def test_only_transient_fetch_errors_are_retryable(self) -> None:
        self.assertTrue(sync_tjmugh.is_retryable_fetch_error(RuntimeError('TJMUGH_NETWORK_ERROR')))
        self.assertTrue(sync_tjmugh.is_retryable_fetch_error(RuntimeError('TJMUGH_HTTP_503')))
        self.assertTrue(sync_tjmugh.is_retryable_fetch_error(RuntimeError('TJMUGH_HTTP_429')))
        self.assertFalse(sync_tjmugh.is_retryable_fetch_error(RuntimeError('TJMUGH_HTTP_404')))
        self.assertFalse(sync_tjmugh.is_retryable_fetch_error(ValueError('TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND')))

    def test_transient_fetch_retries_once_then_succeeds(self) -> None:
        with (
            patch.object(
                sync_tjmugh,
                'fetch_tjmugh_page',
                side_effect=[RuntimeError('TJMUGH_NETWORK_ERROR'), '<html>ok</html>'],
            ) as fetch,
            patch.object(sync_tjmugh.time, 'sleep') as sleep,
        ):
            result = sync_tjmugh.fetch_page_with_retry(
                'https://www.tjmugh.com.cn/cgxxtzgg/index.shtml',
                delay_seconds=3.0,
            )
        self.assertEqual(result, '<html>ok</html>')
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(3.0)

    def test_non_retryable_fetch_fails_immediately(self) -> None:
        with (
            patch.object(
                sync_tjmugh,
                'fetch_tjmugh_page',
                side_effect=RuntimeError('TJMUGH_HTTP_404'),
            ) as fetch,
            patch.object(sync_tjmugh.time, 'sleep') as sleep,
            self.assertRaisesRegex(RuntimeError, 'TJMUGH_HTTP_404'),
        ):
            sync_tjmugh.fetch_page_with_retry(
                'https://www.tjmugh.com.cn/cgxxtzgg/index.shtml',
                delay_seconds=3.0,
            )
        self.assertEqual(fetch.call_count, 1)
        sleep.assert_not_called()

    def test_default_detail_delay_is_not_below_three_seconds(self) -> None:
        self.assertGreaterEqual(sync_tjmugh.MIN_DETAIL_DELAY_SECONDS, 3.0)

    def test_parse_as_of_requires_timezone(self) -> None:
        with self.assertRaisesRegex(ValueError, 'timezone'):
            sync_tjmugh.parse_as_of('2026-08-31T12:00:00')


if __name__ == '__main__':
    unittest.main()
