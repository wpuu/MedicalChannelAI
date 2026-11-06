"""Offline integrity and recorded behavior verification; no project/SDK imports."""
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
proof = read('input-integrity.json')
names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', '1352739', '--',
    'web/pipeline/data', 'web/pipeline/tests/fixtures', 'docs/project/validation'], cwd=ROOT, text=True).splitlines()
assert set(names) == set(proof['files']) and len(names) == proof['protected_file_count'] == 408
for path, digest in proof['files'].items():
    assert sha((ROOT / path).read_bytes()) == digest, path
summary = read('validation-summary.json')
assert (summary['python_tests_passed'], summary['regional_cli_behavior_tests'], summary['new_behavior_tests']) == (1059, 28, 13)
for path, digest in summary['source_sha256'].items():
    data = subprocess.check_output(['git', 'show', f"{summary['code_head']}:{path}"], cwd=ROOT)
    assert sha(data) == digest, path
changes = subprocess.check_output(['git', 'diff', '--name-only', '1352739', summary['code_head']], cwd=ROOT, text=True).splitlines()
assert set(changes) == {'web/pipeline/scripts/sync_regional_ccgp.py', 'web/pipeline/tests/test_regional_cli_completeness.py'}
before, after = read('before.json'), read('after.json')
assert [(r['search_calls'], r['detail_calls']) for r in before] == [(4, 2), (7, 2), (4, 2), (4, 2)]
assert [(r['search_calls'], r['detail_calls']) for r in after[:4]] == [(2, 1), (5, 1), (4, 1), (4, 1)]
assert (after[4]['search_calls'], after[4]['detail_calls']) == (1, 0)
assert after[10]['detail_calls'] == 2 and set(after[10]['blocked_hosts']) == {'www.ccgp.gov.cn'}
assert (after[11]['search_calls'], after[11]['detail_calls']) == (4, 0)
assert after[13]['exit_code'] == 0 and not after[13]['blocked_hosts']
assert [r['search_calls'] for r in after[14:]] == [3, 9]
for row in after:
    assert row['exit_code'] in (0, 2)
    assert row['acceptance_ready'] == row['records_written'] == (row['exit_code'] == 0)
    if row['exit_code'] == 2:
        assert row['inputs_unchanged'] and row['records_unchanged']
        assert row['before_sha256'] == row['after_sha256']
assert read('frozen-template-audit.json')['passed'] == 10 and read('frozen-template-audit.json')['failed'] == 0
assert read('original-cli-gate.json')['passed'] == 3 and read('original-cli-gate.json')['failed'] == 0
log = (HERE / 'regression.log').read_text()
assert 'Ran 1059 tests' in log and '\nOK\n' in log
assert not summary['F1_whole_project_complete'] and not summary['F2_implemented']
assert not summary['apply_allowed'] and not summary['migration_usable']
assert read('completion.json')['within_foreground_deadline']
print('PASS:F1 CLI stop before/after,1059+10/3,408 unchanged inputs,pinned sources,scope boundaries')
