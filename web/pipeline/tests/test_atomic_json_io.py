from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPT_DIR))
from atomic_json_io import validate_json_output_paths, write_json_atomic, write_json_bundle_atomic


class AtomicJsonIoTests(unittest.TestCase):
    def test_json_bundle_commits_multiple_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, report = root / 'records.json', root / 'report.json'
            write_json_bundle_atomic({records: [{'id': 1}], report: {'publish_allowed': True}})
            self.assertEqual(records.read_text(encoding='utf-8'), '[\n  {\n    "id": 1\n  }\n]\n')
            self.assertIn('true', report.read_text(encoding='utf-8'))

    def test_serialization_failure_preserves_existing_bytes_and_missing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing, missing = root / 'existing.json', root / 'missing.json'
            before = b'{ "preserve": "exact bytes" }\n'
            existing.write_bytes(before)
            with self.assertRaises(TypeError):
                write_json_bundle_atomic({existing: {'ok': True}, missing: object()})
            self.assertEqual(existing.read_bytes(), before)
            self.assertFalse(missing.exists())

    def test_replace_failure_rolls_back_all_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / 'first.json', root / 'second.json'
            before_first, before_second = b'first-before\n', b'second-before\n'
            first.write_bytes(before_first)
            second.write_bytes(before_second)
            actual_replace = __import__('os').replace
            failed = False

            def fail_second_once(source, destination):
                nonlocal failed
                if Path(destination) == second and not failed:
                    failed = True
                    raise OSError('SIMULATED_REPLACE_FAILURE')
                return actual_replace(source, destination)

            with patch('atomic_json_io.os.replace', side_effect=fail_second_once):
                with self.assertRaisesRegex(OSError, 'SIMULATED_REPLACE_FAILURE'):
                    write_json_bundle_atomic({first: {'new': 1}, second: {'new': 2}})
            self.assertEqual(first.read_bytes(), before_first)
            self.assertEqual(second.read_bytes(), before_second)

    def test_output_validation_rejects_report_symlink_and_hardlink_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, records, report = root / 'source.json', root / 'records.json', root / 'report.json'
            source.write_bytes(b'[]\n')
            report.symlink_to(source)
            with self.assertRaisesRegex(ValueError, 'report output'):
                validate_json_output_paths(
                    report_output=report,
                    data_outputs={'records': records},
                    input_paths={'records': [source]},
                )
            report.unlink()
            report.hardlink_to(source)
            with self.assertRaisesRegex(ValueError, 'report output'):
                validate_json_output_paths(
                    report_output=report,
                    data_outputs={'records': records},
                    input_paths={'records': [source]},
                )

    def test_output_validation_allows_same_type_read_merge_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, report = root / 'records.json', root / 'report.json'
            validate_json_output_paths(
                report_output=report,
                data_outputs={'records': records},
                input_paths={'records': [records]},
            )

    def test_output_validation_rejects_records_events_and_cross_input_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, events, report, events_input = (
                root / 'records.json', root / 'events.json', root / 'report.json', root / 'events-input.json'
            )
            events_input.write_bytes(b'[]\n')
            with self.assertRaisesRegex(ValueError, 'outputs must be distinct'):
                validate_json_output_paths(
                    report_output=report,
                    data_outputs={'records': records, 'events': records},
                    input_paths={'records': [], 'events': []},
                )
            with self.assertRaisesRegex(ValueError, 'events input'):
                validate_json_output_paths(
                    report_output=report,
                    data_outputs={'records': events_input, 'events': events},
                    input_paths={'records': [], 'events': [events_input]},
                )

    def test_single_file_atomic_write(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'records.json'
            output.write_bytes(b'old bytes')
            write_json_atomic(output, {'ok': True})
            self.assertEqual(output.read_text(encoding='utf-8'), '{\n  "ok": true\n}\n')


if __name__ == '__main__':
    unittest.main()
