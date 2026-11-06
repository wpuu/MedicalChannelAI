"""Verify frozen local evidence; never imports project/SDK or accesses a service."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
read = lambda name: json.loads((HERE / name).read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()

manifest = read('manifest.json')
assert not manifest['apply_allowed'] and not manifest['migration_usable']
for item in manifest['files']:
    data = (HERE / item['path']).read_bytes()
    assert len(data) == item['bytes'] and sha(data) == item['sha256'], item['path']

proof = read('input-integrity.json')
assert len(proof['files']) == proof['protected_file_count'] == 395
for path, digest in proof['files'].items():
    assert sha((ROOT / path).read_bytes()) == digest, path

summary = read('validation-summary.json')
assert summary['python_tests_passed'] == 1046 and summary['new_behavior_tests'] == 15
assert not summary['apply_allowed'] and not summary['migration_usable']
for path, digest in summary['source_files'].items():
    # Bind historical evidence to its exact commit, also after future code changes.
    data = subprocess.check_output(['git', 'show', f"{summary['code_head']}:{path}"], cwd=ROOT)
    assert sha(data) == digest, path

before = {r['scenario']: r for r in read('before.json')}
after = {r['scenario']: r for r in read('after.json')}
for scenario in ('one_discovery_failed', 'one_detail_failed', 'rate_limited', 'partial_fallback'):
    assert before[scenario]['code'] == 0 and before[scenario]['records_changed']
for scenario, row in after.items():
    assert row['input_bytes_unchanged']
    success = scenario in ('all_success', 'empty_success', 'fallback_success')
    assert row['exit_code'] == (0 if success else 2)
    assert row['acceptance_ready'] == row['records_written'] == success
    if not success:
        assert row['records_bytes_unchanged'] and row['before_sha256'] == row['after_sha256']
        assert row['acceptance_blockers']
assert read('frozen-template-audit.json')['passed'] == 10
assert read('frozen-template-audit.json')['failed'] == 0
assert read('original-cli-gate.json')['passed'] == 3
assert read('original-cli-gate.json')['failed'] == 0
log = (HERE / 'regression.log').read_text()
assert 'Ran 1046 tests' in log and '\nOK\n' in log
assert read('completion.json')['within_foreground_deadline']
print('PASS:F3 before/after,1046+10/3,395 protected inputs,pinned source and evidence hashes')
