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
import tjmugh_failure_diagnostics


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
        self.assertEqual(logged['message'], report['failures'][0]['message'])
        self.assertNotIn('title', logged)
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

    def test_atomic_json_failures_preserve_target_and_clean_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'records.json'
            target.write_text('original\n', encoding='utf-8')
            for method in ('replace', 'fsync'):
                with self.subTest(stage=method), patch.object(
                    tjmugh_failure_diagnostics.os, method, side_effect=OSError('write failed')
                ), self.assertRaises(OSError):
                    sync_tjmugh.write_json(target, [{'id': 'new'}])
                self.assertEqual(target.read_text(encoding='utf-8'), 'original\n')
                self.assertEqual(list(Path(directory).glob('.records.json.*.tmp')), [])

            real_named_temporary = tjmugh_failure_diagnostics.tempfile.NamedTemporaryFile

            class FailingWriter:
                def __init__(self, wrapped):
                    self.wrapped = wrapped
                    self.name = wrapped.name

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    self.wrapped.close()

                def write(self, content):
                    self.wrapped.write(content[:1])
                    raise OSError('write failed')

                def flush(self):
                    self.wrapped.flush()

                def fileno(self):
                    return self.wrapped.fileno()

            with (
                patch.object(
                    tjmugh_failure_diagnostics.tempfile, 'NamedTemporaryFile',
                    side_effect=lambda *args, **kwargs: FailingWriter(real_named_temporary(*args, **kwargs)),
                ),
                self.assertRaisesRegex(OSError, 'write failed'),
            ):
                sync_tjmugh.write_json(target, [{'id': 'new'}])
            self.assertEqual(target.read_text(encoding='utf-8'), 'original\n')
            self.assertEqual(list(Path(directory).glob('.records.json.*.tmp')), [])
            with self.assertRaises(TypeError):
                sync_tjmugh.write_json(target, {'bad': object()})
            self.assertEqual(target.read_text(encoding='utf-8'), 'original\n')
            self.assertEqual(list(Path(directory).glob('.records.json.*.tmp')), [])

    def test_report_write_failure_preserves_records(self):
        with tempfile.TemporaryDirectory() as directory:
            records = Path(directory) / 'records.json'
            report = Path(directory) / 'report.json'
            before = json.dumps([self.verified_record()], ensure_ascii=False) + '\n'
            records.write_text(before, encoding='utf-8')
            argv = [str(SCRIPT_PATH), '--as-of', '2026-08-05T08:00:00Z',
                    '--records-output', str(records), '--existing-records-input', str(records),
                    '--report-output', str(report)]
            with (
                patch.object(sync_tjmugh.sys, 'argv', argv),
                patch.object(sync_tjmugh, 'fetch_tjmugh_page', return_value='index'),
                patch.object(sync_tjmugh, 'parse_tjmugh_index_html', return_value=[]),
                patch.object(sync_tjmugh, 'write_json', side_effect=OSError('report write')),
                self.assertRaisesRegex(OSError, 'report write'),
            ):
                sync_tjmugh.main()
            self.assertEqual(records.read_text(encoding='utf-8'), before)

    def test_report_aliases_rejected_before_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = root / 'records-output.json'
            seed = root / 'seed.json'
            records_before, seed_before = 'existing records output\n', '[]\n'
            records.write_text(records_before, encoding='utf-8')
            for alias_kind in ('records_output', 'direct_input', 'symlink_input', 'hardlink_input'):
                seed.write_text(seed_before, encoding='utf-8')
                if alias_kind == 'records_output':
                    report_path = records
                    input_path = None
                elif alias_kind == 'direct_input':
                    report_path, input_path = seed, seed
                elif alias_kind == 'symlink_input':
                    report_path = root / 'report-link.json'
                    report_path.unlink(missing_ok=True)
                    report_path.symlink_to(seed)
                    input_path = seed
                else:
                    report_path = root / 'report-hardlink.json'
                    report_path.unlink(missing_ok=True)
                    report_path.hardlink_to(seed)
                    input_path = seed
                argv = [str(SCRIPT_PATH), '--records-output', str(records),
                        '--report-output', str(report_path)]
                if input_path:
                    argv.extend(['--existing-records-input', str(input_path)])
                with (
                    patch.object(sync_tjmugh.sys, 'argv', argv),
                    patch.object(sync_tjmugh, 'fetch_tjmugh_page') as fetch,
                    self.assertRaisesRegex(ValueError, 'report output must not alias'),
                ):
                    sync_tjmugh.main()
                fetch.assert_not_called()
                self.assertEqual(records.read_text(encoding='utf-8'), records_before)
                self.assertEqual(seed.read_text(encoding='utf-8'), seed_before)

    def test_failure_log_redacts_untrusted_fields_and_rejects_unexpected_url(self):
        failure = {
            'stage': 'verified_detail', 'category': 'PARSER_REJECTED', 'error': 'ValueError',
            'message': 'TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND:SECRET_AUTH_TOKEN_ABC',
            'title': 'private title SECRET_AUTH_TOKEN_ABC',
            'url': 'https://user:password@www.tjmugh.com.cn/system/2026/08/05/12.shtml?token=SECRET#x',
        }
        stream = io.StringIO()
        with redirect_stderr(stream):
            sync_tjmugh.emit_failure(failure)
        rendered = stream.getvalue()
        self.assertIn('TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND', rendered)
        self.assertNotIn('SECRET_AUTH_TOKEN_ABC', rendered)
        self.assertNotIn('private title', rendered)
        self.assertNotIn('password', rendered)
        self.assertNotIn('token=', rendered)
        self.assertNotIn('url', json.loads(rendered.split('=', 1)[1]))
        self.assertEqual(tjmugh_failure_diagnostics.safe_error_code('SECRET_AUTH_TOKEN_ABC'),
                         'ERROR_CODE_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
