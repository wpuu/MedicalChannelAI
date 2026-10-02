from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from medical_channel_pipeline.tjmugh_discovery import TjmughCandidate
from medical_channel_pipeline.tjmugh_market_research import TjmughParseError, parse_tjmugh_market_research
from medical_channel_pipeline.validation import ValidationError
from test_tjmugh_market_research import FIXTURE

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / 'scripts' / 'sync_tjmugh_market_research.py'

spec = importlib.util.spec_from_file_location('sync_tjmugh_market_research', SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError('SYNC_TJMUGH_IMPORT_FAILED')
sync_tjmugh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_tjmugh)


class TjmughSyncTests(unittest.TestCase):
    def run_sync(self, candidates, responses, *, existing=None, output_exists=True):
        with tempfile.TemporaryDirectory() as directory:
            records_path = Path(directory) / 'records.json'
            report_path = Path(directory) / 'report.json'
            before = json.dumps(existing or [], ensure_ascii=False) + '\n'
            if output_exists:
                records_path.write_text(before, encoding='utf-8')
            argv = [
                str(SCRIPT_PATH), '--as-of', '2026-08-05T08:00:00Z',
                '--records-output', str(records_path), '--report-output', str(report_path),
            ]
            if output_exists:
                argv.extend(['--existing-records-input', str(records_path)])
            stderr = io.StringIO()
            with (
                patch.object(sync_tjmugh.sys, 'argv', argv),
                patch.object(sync_tjmugh, 'fetch_tjmugh_page', side_effect=responses) as fetch,
                patch.object(sync_tjmugh, 'parse_tjmugh_index_html', return_value=candidates),
                patch.object(sync_tjmugh.time, 'sleep'),
                redirect_stdout(io.StringIO()), redirect_stderr(stderr),
            ):
                result = sync_tjmugh.main()
            output = records_path.read_text(encoding='utf-8') if records_path.exists() else None
            report = json.loads(report_path.read_text(encoding='utf-8'))
            return result, output, report, stderr.getvalue(), before, fetch.call_count

    def candidate(self, item_id='030326488'):
        return TjmughCandidate(
            '天津医科大学总医院医疗设备项目市场调研论证邀请函',
            f'https://www.tjmugh.com.cn/system/2026/08/05/{item_id}.shtml',
            '2026-08-05',
        )

    def verified_record(self):
        return parse_tjmugh_market_research(
            FIXTURE, source_url=self.candidate().detail_url,
            observed_at='2026-08-05T08:00:00+00:00', opportunity_id='tjmugh_20260805_030326488',
        )

    def test_rejected_detail_reproduces_block_and_keeps_records_unchanged(self):
        html = FIXTURE.replace('本次报名截止时间为：2026年8月7日下午17：:00点前。', '报名时间另行通知')
        result, output, report, stderr, before, _ = self.run_sync(
            [self.candidate('030326489')], ['index', html], existing=[self.verified_record()],
        )
        self.assertEqual(result, 2)
        self.assertEqual(output, before)
        self.assertEqual(report['publish_gate_reason'], 'ALL_SELECTED_DETAILS_FAILED_VERIFICATION')
        self.assertEqual(report['missing_selected_count'], 1)
        self.assertEqual(report['refresh_outcome'], 'BLOCKED')
        logged = json.loads(stderr.split('TJMUGH_FAILURE=', 1)[1].splitlines()[0])
        self.assertEqual(logged, report['failures'][0])
        self.assertEqual(logged['message'], 'TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND')
        self.assertEqual(logged['category'], 'PARSER_REJECTED')
        self.assertEqual(logged['url'], self.candidate('030326489').detail_url)

    def test_partial_failure_does_not_write_new_records(self):
        result, output, report, _, before, _ = self.run_sync(
            [self.candidate(), self.candidate('030326489')],
            ['index', FIXTURE, RuntimeError('TJMUGH_HTTP_403')],
        )
        self.assertEqual(result, 2)
        self.assertEqual(output, before)
        self.assertEqual(report['new_verified_record_count'], 1)
        self.assertEqual(report['publish_gate_reason'], 'SELECTED_DETAILS_INCOMPLETE')
        self.assertEqual(report['failures'][0]['category'], 'ACCESS_DENIED')

    def test_blocked_refresh_does_not_create_records_file(self):
        result, output, report, _, _, calls = self.run_sync(
            [self.candidate()], ['index', RuntimeError('TJMUGH_HTTP_403')], output_exists=False,
        )
        self.assertEqual(result, 2)
        self.assertIsNone(output)
        self.assertFalse(report['publish_allowed'])
        self.assertEqual(calls, 2)  # Access rejection is never retried.

    def test_index_transient_failure_reports_and_preserves_output(self):
        result, output, report, stderr, before, calls = self.run_sync(
            [], [RuntimeError('TJMUGH_NETWORK_ERROR')] * 2,
        )
        self.assertEqual(result, 2)
        self.assertEqual(output, before)
        self.assertEqual(calls, 2)
        self.assertEqual(report['publish_gate_reason'], 'INDEX_DISCOVERY_FAILED')
        self.assertEqual(report['failures'][0]['category'], 'TRANSIENT_FETCH_ERROR')
        self.assertIn('TJMUGH_FAILURE=', stderr)

    def test_empty_window_is_distinct_from_failure(self):
        result, _, report, stderr, _, calls = self.run_sync([], ['index'])
        self.assertEqual(result, 0)
        self.assertEqual(calls, 1)
        self.assertEqual(report['refresh_outcome'], 'NO_CANDIDATES_IN_WINDOW')
        self.assertEqual(report['failure_count'], 0)
        self.assertEqual(stderr, '')

    def test_verified_refresh_writes_valid_records(self):
        result, output, report, _, _, _ = self.run_sync([self.candidate()], ['index', FIXTURE])
        self.assertEqual(result, 0)
        self.assertEqual(report['refresh_outcome'], 'VERIFIED')
        self.assertEqual(json.loads(output), [self.verified_record()])

    def test_existing_coverage_does_not_hide_current_fetch_failure(self):
        result, output, report, stderr, _, _ = self.run_sync(
            [self.candidate()], ['index', RuntimeError('TJMUGH_HTTP_404')],
            existing=[self.verified_record()],
        )
        self.assertEqual(result, 0)  # Existing publish-gate contract.
        self.assertEqual(json.loads(output), [self.verified_record()])
        self.assertEqual(report['refresh_outcome'], 'EXISTING_VERIFIED_COVERAGE_WITH_FAILURES')
        self.assertEqual(report['failure_count'], 1)
        self.assertIn('PERMANENT_HTTP_ERROR', stderr)

    def test_failure_categories_keep_evidence_rejection_separate(self):
        self.assertEqual(sync_tjmugh.failure_category(ValidationError('EVIDENCE_LIST_REQUIRED')),
                         'EVIDENCE_VALIDATION_FAILED')
        self.assertEqual(sync_tjmugh.failure_category(TjmughParseError('TJMUGH_TITLE_NOT_FOUND')),
                         'PARSER_REJECTED')
        self.assertEqual(sync_tjmugh.failure_category(RuntimeError('unknown')), 'UNEXPECTED_ERROR')

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
