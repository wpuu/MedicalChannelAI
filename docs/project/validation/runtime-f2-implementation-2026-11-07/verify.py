"""Static evidence/hash verification only; never imports application or SDK."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

def read(name):
    return json.loads((HERE / name).read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

summary = read('validation-summary.json')
code = summary['code_head']
expected = set(summary['only_modified_code_files'])
assert set(git('diff', '--name-only', summary['starting_head'], code).decode().splitlines()) == expected
for name, digest in summary['source_sha256'].items():
    assert sha(ROOT / name) == digest, name
    assert hashlib.sha256(git('show', f'{code}:{name}')).hexdigest() == digest, name
integrity = read('input-integrity.json')
assert integrity['protected_file_count'] == len(integrity['files']) == 460
baseline = set(git('ls-tree', '-r', '--name-only', summary['starting_head'], '--',
                   'web/pipeline/data', 'web/pipeline/tests/fixtures', 'docs/project/validation').decode().splitlines())
assert baseline == set(integrity['files'])
for name, digest in integrity['files'].items():
    assert sha(ROOT / name) == digest, name
    assert hashlib.sha256(git('show', f"{summary['starting_head']}:{name}")).hexdigest() == digest, name
regional = read('regional-cases.json')
queue = read('queue-cases.json')
assert len(regional) == 21 and len(queue) == 6
assert all(c['pending_preserved'] and c['ledger_unchanged'] for c in regional)
for c in regional:
    if c['mode'] in {'expired', 'margin', 'search_late', 'sleep_admission', 'sleep_overrun', 'detail_late', 'parse_late', 'precommit_late'}:
        assert c['status'] == 503 and c['canonical_unchanged'] and c['last_success_unchanged'], c['mode']
    if c['mode'] in {'expired', 'margin'}:
        assert c['search_calls'] == c['detail_calls'] == c['session_calls'] == 0
    if c['mode'] in {'success', 'empty', 'commit_late', 'health_late', 'timeout_near'}:
        assert c['status'] == 200 and c['stage_status'] == 'COMPLETED'
    if c['mode'] in {'commit_late', 'health_late'}:
        assert c['result']['budget_finalization_overrun'] is True
    if c['mode'] == 'write_then_error':
        assert not c['canonical_unchanged'] and c['status'] == 503
assert all(c['assertions_passed'] for c in queue)
assert read('frozen-template-audit.json')['passed'] == 10
assert read('original-cli-gate.json')['passed'] == 3
log = (HERE / 'regression.log').read_text()
assert 'Ran 1098 tests' in log and log.rstrip().endswith('OK')
assert summary['new_behavior_tests'] == 19
assert summary['runtime_total_work_reserve'] == [270, 210, 60]
assert summary['cli_default_total_work_reserve'] == [900, 840, 60]
for key in ['apply_allowed', 'migration_usable', 'hard_cancel_guaranteed', 'real_persistence_verified',
            'atomic_owner_or_time_commit_guaranteed', 'incremental_event_publish_budget_added',
            'queue_lease_or_health_contract_changed', 'cloud_runtime_access']:
    assert summary[key] is False, key
completion = read('completion.json')
assert completion['within_foreground_budget'] and completion['apply_allowed'] is False
for name, digest in read('manifest.json')['sha256'].items():
    assert sha(ROOT / name) == digest, name
print('PASS: 6 authorized code files; 460 protected inputs; 1098/10/3; 21 regional + 6 Queue cases; manifest hashes; offline scope')
