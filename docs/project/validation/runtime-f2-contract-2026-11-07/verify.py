"""Static versioned-source/arithmetic/integrity checks; no app, SDK or test imports."""
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
refs = read('source-references.json')['references']
assert len(refs) == 145
sources = {}
for item in refs:
    if item['path'] not in sources:
        sources[item['path']] = subprocess.check_output(['git', 'show', f"62c039e:{item['path']}"], cwd=ROOT)
    data = sources[item['path']]
    assert sha(data) == item['sha256']
    assert data.decode().splitlines()[item['line'] - 1] == item['text']
proof = read('input-integrity.json')
names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', '62c039e', '--',
    'web/pipeline/data', 'web/pipeline/tests/fixtures', 'docs/project/validation'], cwd=ROOT, text=True).splitlines()
assert len(names) == proof['protected_file_count'] == 450 and set(names) == set(proof['files'])
for path, digest in proof['files'].items():
    assert sha((ROOT / path).read_bytes()) == digest, path
contract = read('budget-contract.json')
assert contract['status'] == 'PROPOSED_NOT_IMPLEMENTED'
assert (contract['total_seconds'], contract['work_seconds'], contract['finalize_reserve_seconds']) == (270, 210, 60)
assert 270 == 210 + 60 and 300 - 270 == contract['nominal_outer_headroom_seconds'] == 30
assert contract['business_max_attempts'] == 2 and contract['provider_max_deliveries'] == 3
assert contract['provider_message_lease_seconds'] == 300 and contract['provider_retry_after_seconds'] == 150
assert contract['deep_owner_liveness_seconds'] == contract['incremental_owner_ttl_seconds'] == 900
assert contract['deep_owner_cache_retention_seconds'] == 172800
assert contract['existing_cli_defaults_must_remain'] == {'total_seconds': 900, 'work_seconds': 840, 'finalize_reserve_seconds': 60}
assert not contract['queue_config_or_lease_change'] and not contract['health_state_contract_change']
assert not contract['incremental_event_publish_in_scope'] and not contract['hard_cancel_guaranteed']
assert not contract['cache_write_outcome_known_guaranteed'] and not contract['default_full_fallback_on_time_guaranteed']
assert len(contract['candidate_files']) == 6
capacity = read('static-capacity.json')
assert [(r['total_requests'], r['fixed_sleep_seconds'], r['nominal_timeout_plus_sleep_seconds'], r['work_remaining_after_fixed_sleep']) for r in capacity['rows']] == [
    (21, 81, 1311, 129), (41, 201, 3231, 9), (11, 41, 971, 169)]
for row in capacity['rows']:
    assert not row['measured'] and not row['hard_wall_clock_bound']
    assert row['nominal_timeout_plus_sleep_seconds'] == row['search_requests'] * 90 + row['detail_requests'] * 30 + 30 + row['fixed_sleep_seconds']
summary = read('validation-summary.json')
assert not summary['tests_executed'] and not summary['application_or_sdk_imported_or_executed']
assert not summary['runtime_budget_implemented'] and summary['simulators_added'] == 0
assert not summary['apply_allowed'] and not summary['migration_usable']
artifact_path = str((HERE / 'manifest.json').relative_to(ROOT))
recorded_commit = subprocess.check_output(['git', 'log', '-1', '--diff-filter=A', '--format=%H', '--', artifact_path], cwd=ROOT, text=True).strip() or 'HEAD'
subprocess.run(['git', 'diff', '--exit-code', '62c039e', recorded_commit, '--', 'web', '.github'], cwd=ROOT, check=True, capture_output=True)
assert read('completion.json')['within_foreground_deadline']
print('PASS:145source refs,450unchanged inputs,270/210/60static contract;NO runtime implementation/test execution')
