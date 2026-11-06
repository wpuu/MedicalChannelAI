"""Validate frozen offline evidence; never imports project or SDK modules."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
read = lambda name: json.loads((HERE / name).read_text())
sha = lambda value: hashlib.sha256(value).hexdigest()

manifest = read('manifest.json')
assert not manifest['apply_allowed'] and not manifest['migration_usable']
for item in manifest['files']:
    data = (HERE / item['path']).read_bytes()
    assert len(data) == item['bytes'] and sha(data) == item['sha256'], item['path']
for path, digest in manifest['document_sha256'].items():
    assert sha((ROOT / path).read_bytes()) == digest
proof = read('input-integrity.json')
names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', '2826b30', '--',
    'web/pipeline/data', 'web/pipeline/tests/fixtures', 'docs/project/validation'], cwd=ROOT, text=True).splitlines()
assert set(names) == set(proof['files']) and len(names) == proof['protected_file_count'] == 429
for path, digest in proof['files'].items():
    assert sha((ROOT / path).read_bytes()) == digest, path
summary = read('validation-summary.json')
assert (summary['python_tests_passed'], summary['new_behavior_tests'], summary['cli_behavior_tests']) == (1079, 20, 48)
for path, digest in summary['source_sha256'].items():
    data = subprocess.check_output(['git', 'show', f"{summary['code_head']}:{path}"], cwd=ROOT)
    assert sha(data) == digest, path
changes = subprocess.check_output(['git', 'diff', '--name-only', '2826b30', summary['code_head']], cwd=ROOT, text=True).splitlines()
assert set(changes) == set(summary['only_modified_code_files'])
rows = read('cli-cases.json')
assert len(rows) == 20
by_name = {r['scenario']: r for r in rows}
for row in rows:
    assert row['temporary_files_remaining'] == 0
    assert (row['budget']['total_seconds'], row['budget']['work_seconds'], row['budget']['finalize_reserve_seconds']) == (900, 840, 60)
    assert not row['budget']['hard_exit_guaranteed']
    if row['exit_code'] == 2:
        assert row['commit_state'] == 'NOT_COMMITTED' and row['records_written'] is False
        assert row['records_bytes_unchanged'] and row['inputs_unchanged']
        assert row['before_sha256'] == row['after_sha256']
    elif row['exit_code'] == 0:
        assert row['commit_state'] == 'COMMITTED' and row['records_written'] is True
        assert row['acceptance_ready'] and not row['post_commit_overrun']
    else:
        assert row['exit_code'] == 3 and not row['acceptance_ready']
        assert row['commit_state'] in {'COMMITTED', 'COMMIT_UNKNOWN', 'COMMITTED_REPORTING_INCOMPLETE'}
        assert row['records_written'] is None if row['commit_state'] == 'COMMIT_UNKNOWN' else row['records_written'] is True
for name in ('input_expired', 'margin_expired'):
    row = by_name[name]
    assert (row['client_calls'], row['search_calls'], row['detail_calls']) == (0, 0, 0)
assert by_name['detail_timeout']['detail_timeouts'] == [6, 2]
for name in ('detail_late', 'parse_late'):
    assert by_name[name]['detail_calls'] == 1 and by_name[name]['exit_code'] == 2
assert by_name['replace_error_before']['records_bytes_unchanged']
assert not by_name['replace_then_error']['records_bytes_unchanged']
assert by_name['replace_late']['post_commit_overrun'] and by_name['report_late']['post_commit_overrun']
assert by_name['report_error']['commit_state'] == 'COMMITTED_REPORTING_INCOMPLETE'
assert not by_name['report_error']['report_present']
assert by_name['symlink_success']['output_is_symlink']
log = (HERE / 'regression.log').read_text()
assert 'Ran 1079 tests' in log and '\nOK\n' in log
assert read('frozen-template-audit.json')['passed'] == 10 and read('frozen-template-audit.json')['failed'] == 0
assert read('original-cli-gate.json')['passed'] == 3 and read('original-cli-gate.json')['failed'] == 0
assert not summary['hard_exit_guaranteed'] and not summary['runtime_budget_implemented']
assert not summary['apply_allowed'] and not summary['migration_usable']
assert read('completion.json')['within_foreground_deadline']
print('PASS:CLI cooperative budget20cases,1079+10/3,429inputs unchanged,commit outcomes accurately distinguished')
