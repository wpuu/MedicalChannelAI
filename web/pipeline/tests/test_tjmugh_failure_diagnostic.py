from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PIPELINE_ROOT / 'scripts' / 'export_tjmugh_failure_diagnostic.py'
spec = importlib.util.spec_from_file_location('export_tjmugh_failure_diagnostic', SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError('EXPORT_TJMUGH_DIAGNOSTIC_IMPORT_FAILED')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class TjmughFailureDiagnosticTests(unittest.TestCase):
    expected = '2026-08-05T08:00:00+00:00'

    def current_report(self):
        return {
            'schema_version': '0.1', 'source': 'TJMUGH_PROCUREMENT_INDEX',
            'observed_at': '2026-08-05T16:00:00+08:00',
            'selected_candidate_count': 2, 'new_verified_record_count': 1,
            'publish_gate_reason': 'SELECTED_DETAILS_INCOMPLETE',
            'refresh_outcome': 'BLOCKED', 'publish_allowed': False,
            'failures': [{
                'stage': 'verified_detail', 'category': 'PARSER_REJECTED', 'error': 'TjmughParseError',
                'message': 'TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND:secret data',
                'title': 'private title and contact',
                'url': 'https://www.tjmugh.com.cn/system/2026/08/05/123.shtml?secret=x',
            }],
        }

    def write_report(self, path, payload):
        path.write_text(json.dumps(payload), encoding='utf-8')

    def test_missing_malformed_and_stale_reports_emit_only_safe_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            for expected_status, payload in (
                ('REPORT_MISSING', None), ('REPORT_INVALID', '{broken'),
                ('REPORT_NOT_CURRENT', json.dumps({**self.current_report(), 'observed_at': '2026-08-04T08:00:00Z'})),
            ):
                if payload is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(payload, encoding='utf-8')
                result = exporter.build_diagnostic(path, self.expected)
                self.assertEqual(result['status'], expected_status)
                self.assertEqual(result['workflow_result'], 'failure')
                self.assertNotIn('publish_allowed', result)
                self.assertNotIn('observed_at', result)
                self.assertIn('original authorized runner report and HTML', result['guidance'])

    def test_current_report_is_equivalent_datetime_and_allowlist_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            self.write_report(path, self.current_report())
            result = exporter.build_diagnostic(path, self.expected, 'a' * 40, '1234')
            rendered = json.dumps(result)
            self.assertEqual(result['status'], 'REPORT_CURRENT')
            self.assertEqual(result['workflow_result'], 'failure')
            self.assertEqual(result['reported_publish_allowed'], False)
            self.assertEqual(result['reported_publish_gate_reason'], 'SELECTED_DETAILS_INCOMPLETE')
            self.assertEqual(result['counts']['selected_candidate_count'], 2)
            self.assertEqual(result['failures'][0]['message'], 'TJMUGH_REGISTRATION_DEADLINE_NOT_FOUND')
            self.assertEqual(result['failures'][0]['url'], 'https://www.tjmugh.com.cn/system/2026/08/05/123.shtml')
            for secret in ('private title', 'contact', 'secret data', '?secret', 'report.json'):
                self.assertNotIn(secret, rendered)
            self.assertLessEqual(len(rendered.encode()), exporter.MAX_OUTPUT_BYTES)

    def test_pathological_report_sizes_counts_and_failures_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_bytes(b' ' * (exporter.MAX_REPORT_BYTES + 1))
            self.assertEqual(exporter.build_diagnostic(path, self.expected)['status'], 'REPORT_INVALID')
            report = self.current_report()
            report['selected_candidate_count'] = 1_000_001
            report['failure_count'] = 10**9
            report['failures'] = [{'message': 'SAFE_TOKEN'}] * 60
            self.write_report(path, report)
            result = exporter.build_diagnostic(path, self.expected)
            self.assertNotIn('selected_candidate_count', result['counts'])
            self.assertNotIn('failure_count', result['counts'])
            self.assertEqual(len(result['failures']), 50)
            self.assertEqual(result['failures'][0]['message'], 'ERROR_CODE_UNAVAILABLE')

    def test_invalid_expected_timestamp_and_unknown_source_are_not_current(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            self.write_report(path, self.current_report())
            with self.assertRaisesRegex(ValueError, 'timezone'):
                exporter.build_diagnostic(path, '2026-08-05T08:00:00')
            report = self.current_report()
            report['source'] = 'OTHER'
            self.write_report(path, report)
            self.assertEqual(exporter.build_diagnostic(path, self.expected)['status'], 'REPORT_INVALID')

    def test_adversarial_json_errors_urls_error_types_and_expected_timestamp_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_text('[' * 1500 + '0' + ']' * 1500, encoding='utf-8')
            self.assertEqual(exporter.build_diagnostic(path, self.expected)['status'], 'REPORT_INVALID')

            report = self.current_report()
            bad_urls = [
                'https://outside.example/system/2026/08/05/123.shtml',
                'https://user:secret@www.tjmugh.com.cn/system/2026/08/05/123.shtml',
                'https://www.tjmugh.com.cn/system/2026/08/05/123.shtml?secret=1#private',
                'https://www.tjmugh.com.cn/system/2026/08/05/' + '9' * 100 + '.shtml',
            ]
            report['failures'] = [{
                'stage': 'verified_detail', 'category': 'UNEXPECTED_ERROR',
                'error': 'SECRET_AUTH_TOKEN_ABC', 'message': 'SECRET_AUTH_TOKEN_ABC',
                'url': url,
            } for url in bad_urls]
            self.write_report(path, report)
            result = exporter.build_diagnostic(path, self.expected)
            rendered = json.dumps(result)
            self.assertNotIn('SECRET_AUTH_TOKEN_ABC', rendered)
            self.assertNotIn('outside.example', rendered)
            self.assertNotIn('user:secret@', rendered)
            self.assertNotIn('?secret=', rendered)
            self.assertNotIn('#private', rendered)
            for index, failure in enumerate(result['failures']):
                self.assertEqual(failure['error'], 'Error')
                if index == 2:
                    self.assertEqual(failure['url'], 'https://www.tjmugh.com.cn/system/2026/08/05/123.shtml')
                else:
                    self.assertNotIn('url', failure)
            long_expected = '2026-08-05T08:00:00.' + '1' * 20_000 + '+00:00'
            missing = exporter.build_diagnostic(Path(directory) / 'missing.json', long_expected)
            self.assertLess(len(missing['expected_as_of']), 64)
            self.assertEqual(missing['status'], 'REPORT_MISSING')


if __name__ == '__main__':
    unittest.main()
