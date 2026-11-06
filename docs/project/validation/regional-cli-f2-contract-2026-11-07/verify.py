"""Static arithmetic/reference/integrity verification only; no project/SDK imports."""
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
for path, digest in manifest['document_sha256'].items():
    assert sha((ROOT / path).read_bytes()) == digest, path

proof = read('input-integrity.json')
names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', '98f5503', '--',
    'web/pipeline/data', 'web/pipeline/tests/fixtures', 'docs/project/validation'], cwd=ROOT, text=True).splitlines()
assert set(names) == set(proof['files']) and len(names) == proof['protected_file_count'] == 420
for path, digest in proof['files'].items():
    assert sha((ROOT / path).read_bytes()) == digest, path
refs = read('source-references.json')['references']
assert len(refs) == 49
for item in refs:
    # References describe the exact reviewed commit, even after later fixes.
    data = subprocess.check_output(['git', 'show', f"98f5503:{item['path']}"], cwd=ROOT)
    assert sha(data) == item['sha256'], item['path']
    assert data.decode().splitlines()[item['line'] - 1] == item['text']

contract = read('budget-contract.json')
assert contract['status'] == 'PROPOSED_NOT_IMPLEMENTED'
assert (contract['total_seconds'], contract['work_seconds'], contract['finalize_reserve_seconds']) == (900, 840, 60)
assert contract['total_seconds'] == contract['work_seconds'] + contract['finalize_reserve_seconds']
assert contract['request_caps_seconds'] == {'warmup': 30, 'search': 90, 'detail': 30}
assert contract['workflow_job_seconds'] - contract['total_seconds'] == 600
assert 600 - contract['post_prewarm_step_cap_seconds'] == 120
assert not contract['hard_exit_guaranteed'] and not contract['workflow_remaining_time_verified']
assert not contract['full_default_plan_completion_guaranteed'] and not contract['runtime_stage_budget_implemented']
load = read('static-load.json')
plan = json.loads((ROOT / 'web/pipeline/data/multi_region_query_plan.json').read_text())
assert (len(plan['markets']), len(plan['keywords']), len(plan['notice_types']), plan['max_candidates_per_market']) == (5, 5, 2, 10)
assert plan['delay_seconds'] == 4
assert [(r['total_requests'], r['fixed_sleep_seconds'], r['nominal_timeout_plus_sleep_seconds']) for r in load['rows']] == [
    (101, 401, 6431), (131, 561, 9291), (61, 241, 5671)]
for row in load['rows']:
    assert row['total_requests'] == row['scoped_requests'] + row['fallback_requests'] + row['detail_requests'] + 1
    assert row['nominal_timeout_plus_sleep_seconds'] == (row['scoped_requests'] + row['fallback_requests']) * 90 + row['detail_requests'] * 30 + 30 + row['fixed_sleep_seconds']
    assert row['work_budget_after_sleep_seconds'] == 840 - row['fixed_sleep_seconds']
summary = read('validation-summary.json')
assert not summary['tests_rerun'] and not summary['F2_implemented']
assert not summary['application_or_sdk_imported_or_executed'] and summary['simulators_added'] == 0
assert not summary['apply_allowed'] and not summary['migration_usable']
artifact_path = str((HERE / 'manifest.json').relative_to(ROOT))
recorded_commit = subprocess.check_output(['git', 'log', '-1', '--diff-filter=A', '--format=%H', '--', artifact_path], cwd=ROOT, text=True).strip() or 'HEAD'
subprocess.run(['git', 'diff', '--exit-code', '98f5503', recorded_commit, '--', 'web', '.github'], cwd=ROOT, check=True, capture_output=True)
subprocess.run(['git', 'diff', '--exit-code', 'b97bc09', '98f5503', '--', 'web', '.github'], cwd=ROOT, check=True, capture_output=True)
assert read('completion.json')['within_foreground_deadline']
print('PASS:49references,420unchanged inputs,900/840/60static contract;NO application/test execution or F2 implementation')
