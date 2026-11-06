"""Offline static documentation evidence checks, not application tests."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
START = 'd6a9cee'
REPORT = 'docs/project/tjzyefy-incremental-budget-contract-2026-11-07.md'
ALLOWED = {REPORT, 'docs/project/current-state.md', 'docs/project/checkpoint.json', 'docs/project/next-task.md'}
PREFIX = str(HERE.relative_to(ROOT)) + '/'

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

def read(name):
    return json.loads((HERE / name).read_text())

def sha(value):
    return hashlib.sha256(value).hexdigest()

def source(name):
    return (ROOT / name).read_text()

refs = read('source-references.json')['references']
assert len(refs) == 44
for ref in refs:
    data = (ROOT / ref['path']).read_bytes()
    assert sha(data) == ref['source_sha256']
    assert data.decode().splitlines()[ref['line'] - 1] == ref['text']
    assert git('show', f"{START}:{ref['path']}") == data
integrity = read('input-integrity.json')
assert integrity['protected_file_count'] == len(integrity['files']) == 470
names = set(git('ls-tree', '-r', '--name-only', START, '--', 'web/pipeline/data',
                'web/pipeline/tests/fixtures', 'docs/project/validation').decode().splitlines())
assert names == set(integrity['files'])
for name, digest in integrity['files'].items():
    assert sha((ROOT / name).read_bytes()) == digest, name
    assert sha(git('show', f'{START}:{name}')) == digest, name
changed = git('diff', '--name-only', START).decode().splitlines()
untracked = git('ls-files', '--others', '--exclude-standard').decode().splitlines()
assert all(name in ALLOWED or name.startswith(PREFIX) for name in changed + untracked)
assert not git('diff', START, '--', 'web', '.github', 'package.json', 'package-lock.json')
# Parse source AST as data only; never import/execute application modules.
tree = ast.parse(source('web/collector_incremental.py'))
policy = next(ast.literal_eval(n.value) for n in tree.body
              if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == 'SOURCE_POLICIES')
assert policy['tjzyefy'] == {'scan_interval_minutes': 60, 'reverify_after_hours': 24, 'max_details_per_scan': 12}
inc = source('web/collector_incremental_runtime.py')
run = inc[inc.index('def run_incremental_source('):]
assert run.count('_DISCOVERY[source](observed)') == 1
assert run.index('discovered = _DISCOVERY[source](observed)') < run.index('discovered=discovered') < run.index('plan = plan_detail_verification(')
assert run.index('_save_pending_records(cache, source, durable_staging)') < run.index('scan_barrier.discard(') < run.index('ledger = record_verification_success(') < run.index('finally:')
assert run.index('if failures:') < run.index('if pending_barrier:') < run.index('if staged_records:') < run.index('_publish_snapshot_if_ready(cache, observed)') < run.index('_mark_bucket_completed(', run.index('_publish_snapshot_if_ready(cache, observed)'))
assert 'budget' not in inc[inc.index('def _discover_tjzyefy('):inc.index('def _discover_tjzyefy_intent(')]
helper = source('web/pipeline/scripts/sync_tjzyefy_market_research.py')
assert 'FETCH_ATTEMPTS = 2' in helper and 'time.sleep(delay_seconds)' in helper
assert 'timeout_seconds: int = 30' in source('web/pipeline/medical_channel_pipeline/tjzyefy_discovery.py')
assert 'discovered is None' in source('web/collector_incremental_bootstrap.py')
b = read('budget-contract.json')
assert [b['logical_total_seconds'], b['work_seconds'], b['tail_url_save_reserve_seconds'], b['finalization_reserve_seconds']] == [270, 180, 30, 60]
assert b['work_seconds'] + b['tail_url_save_reserve_seconds'] + b['finalization_reserve_seconds'] == b['logical_total_seconds']
assert b['status'] == 'PROPOSED_ONLY_NOT_IMPLEMENTED' and b['stepwise_save_admission']
assert b['publish_minimum_admission_remaining_seconds'] == b['http_original_cap_seconds'] + 1
assert all(b[key] is False for key in ['apply_allowed', 'migration_usable', 'go_real_runtime', 'hard_cancel_guaranteed', 'physical_no_write_after_deadline_guaranteed', 'atomic_commit_guaranteed', 'pending_protocol_changed'])
a = read('capacity-arithmetic.json')
assert a['logical_fetches'] == 1 + 12 and a['maximum_http_attempts'] == 13 * 2
assert a['no_retry_nominal_seconds'] == 13 * 30 + 12 * 3 == 426
assert a['all_retry_nominal_seconds'] == 26 * 30 + 13 * 3 + 12 * 3 == 855
assert a['work_after_detail_sleeps_seconds'] == 180 - 36 == 144
assert a['work_after_all_retry_sleeps_seconds'] == 180 - 36 - 39 == 105
assert read('go-no-go.json')['historical_tests']['rerun_this_round'] is False
checkpoint = json.loads(source('docs/project/checkpoint.json'))
assert checkpoint['latest_code_validated_head'].startswith('bba3716')
assert checkpoint['tjzyefy_incremental_budget_contract']['app_or_test_execution'] is False
assert checkpoint['current_authorization_scope']['F2_code_this_round'] is False
completion = read('completion.json')
assert completion['within_foreground_budget'] and completion['application_or_tests_executed'] is False
for name, digest in read('manifest.json')['sha256'].items():
    assert sha((ROOT / name).read_bytes()) == digest, name
print('PASS: 44 exact source references; 470 protected files; docs-only diff; source order and policy; proposed budget arithmetic; manifest hashes. No application or tests executed.')
