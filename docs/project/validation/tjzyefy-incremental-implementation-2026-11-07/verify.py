"""Static artifact verification; no application/SDK/test imports or execution."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

def read(name):
    return json.loads((HERE / name).read_text())

def sha(data):
    return hashlib.sha256(data).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

s = read('validation-summary.json')
code = s['code_head']
expected = {'web/collector_queue.py', 'web/collector_incremental_runtime.py',
            'web/pipeline/scripts/sync_tjzyefy_market_research.py',
            'web/pipeline/tests/test_collector_deferred_budget.py',
            'web/pipeline/tests/test_collector_orchestration_behavior.py',
            'web/pipeline/tests/test_tjzyefy_sync.py'}
assert set(git('diff', '--name-only', s['starting_head'], code).decode().splitlines()) == expected
assert set(s['source_sha256']) == expected
for name, digest in s['source_sha256'].items():
    assert sha((ROOT / name).read_bytes()) == sha(git('show', f'{code}:{name}')) == digest, name
added = 0
for name in expected:
    if '/tests/' not in name:
        continue
    before = ast.parse(git('show', f"{s['starting_head']}:{name}").decode())
    after = ast.parse((ROOT / name).read_text())
    def methods(tree):
        return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')}
    assert methods(before) <= methods(after)
    added += len(methods(after) - methods(before))
assert added == s['new_behavior_tests'] == 23
protected = read('input-integrity.json')
assert protected['protected_file_count'] == len(protected['files']) == 480
names = set(git('ls-tree', '-r', '--name-only', s['starting_head'], '--', 'web/pipeline/data',
                'web/pipeline/tests/fixtures', 'docs/project/validation').decode().splitlines())
assert names == set(protected['files'])
for name, digest in protected['files'].items():
    assert sha((ROOT / name).read_bytes()) == sha(git('show', f"{s['starting_head']}:{name}")) == digest, name
cases = read('source-cases.json')
assert len(cases) == 40 and len(read('queue-cases.json')) == 6
assert all(c['other_source_pending_unchanged'] for c in cases)
for c in cases:
    mode, result = c['mode'], c['result']
    if mode in {'expired', 'index_late', 'sleep_admission', 'sleep_late', 'detail_late', 'nonfact_late',
                'staging_late', 'barrier_late', 'ledger_late', 'admit_URL_STAGING', 'admit_URL_BARRIER',
                'admit_URL_LEDGER', 'pre_canonical_late', 'finalize_late', 'periodic_defer', 'staging_recovery_error'}:
        assert c['status'] == 503 and c['canonical_unchanged'] and c['publish_calls'] == 0 and not c['bucket_written'], mode
    if mode in {'detail_late', 'nonfact_late', 'staging_late', 'barrier_late', 'ledger_late', 'periodic_defer'}:
        assert 'VERIFIED' not in c['ledger_statuses'] and c['barrier_count'] == 2, mode
    if mode in {'publish_late', 'bucket_late'}:
        assert c['status'] == 200 and result['budget_finalization_overrun'] and result['publication_outcome'] == 'CONFIRMED'
    if mode == 'bucket_error_after':
        assert c['status'] == 503 and result['snapshot_refreshed'] and result['bucket_mutation_possible']
    if mode in {'staging_error_then_deadline', 'staging_recovery_error'}:
        assert result['recovery_confirmed'] is False
    if mode == 'staging_error_then_deadline':
        assert result['error_type'] == 'OSError' and result['failure_ledger_error_type'] == 'CliBudgetExceeded'
assert all(c['assertions_passed'] for c in read('queue-cases.json'))
assert read('frozen-template-audit.json')['passed'] == 10
assert read('original-cli-gate.json')['passed'] == 3
log = (HERE / 'regression.log').read_text()
assert 'Ran 1121 tests' in log and log.rstrip().endswith('OK')
assert s['total_work_url_tail_finalize'] == [270, 180, 30, 60]
for name in ['hard_cancel_guaranteed', 'atomic_commit_guaranteed', 'real_persistence_verified',
             'physical_no_inflight_late_mutation_guaranteed', 'full_internal_publish_budget_added',
             'queue_lease_health_pending_protocol_changed', 'apply_allowed', 'migration_usable']:
    assert s[name] is False, name
for ref in read('source-references.json')['references']:
    data = (ROOT / ref['path']).read_bytes()
    assert sha(data) == ref['sha256'] and data.decode().splitlines()[ref['line'] - 1] == ref['text']
assert read('completion.json')['within_foreground_budget']
for name, digest in read('manifest.json')['sha256'].items():
    assert sha((ROOT / name).read_bytes()) == digest, name
print('PASS: 6 authorized code files; 23 new tests; 1121/10/3; 40 source + 6 Queue cases; 480 protected files; source references; manifest; offline scope')
