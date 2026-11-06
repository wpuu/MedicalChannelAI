"""Static source/document evidence only; never imports application or SDK."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
START = '82c1006'
REPORT = 'docs/project/publish-budget-receipt-contract-2026-11-07.md'
ALLOWED = {REPORT, 'docs/project/current-state.md', 'docs/project/checkpoint.json', 'docs/project/next-task.md'}
PREFIX = str(HERE.relative_to(ROOT)) + '/'

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

def read(name):
    return json.loads((HERE / name).read_text())

def sha(data):
    return hashlib.sha256(data).hexdigest()

def source(name):
    return (ROOT / name).read_text()

refs = read('source-references.json')['references']
assert len(refs) == 46
for ref in refs:
    data = (ROOT / ref['path']).read_bytes()
    assert sha(data) == ref['source_sha256']
    assert data.decode().splitlines()[ref['line'] - 1] == ref['text']
    assert data == git('show', f"{START}:{ref['path']}")
p = read('input-integrity.json')
assert p['protected_file_count'] == len(p['files']) == 492
names = set(git('ls-tree', '-r', '--name-only', START, '--', 'web/pipeline/data',
                'web/pipeline/tests/fixtures', 'docs/project/validation').decode().splitlines())
assert names == set(p['files'])
for name, digest in p['files'].items():
    assert sha((ROOT / name).read_bytes()) == sha(git('show', f'{START}:{name}')) == digest, name
changed = git('diff', '--name-only', START).decode().splitlines()
untracked = git('ls-files', '--others', '--exclude-standard').decode().splitlines()
assert all(name in ALLOWED or name.startswith(PREFIX) for name in changed + untracked)
assert not git('diff', START, '--', 'web', '.github')
# Source facts from AST/text, not executed demonstrations of app behavior.
tree = ast.parse(source('web/collector_runtime.py'))
functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
observations = read('static-observations.json')
assert observations['mode'] == 'SOURCE_AST_AND_TEXT_ONLY_NOT_BEHAVIORAL_REPRODUCTION'
assert len(observations['gaps']) == 3
for row in observations['python_function_observations']:
    assert row['budget_parameter_present'] is False
    node = functions[row['function']]
    assert all(a.arg != 'budget' for a in node.args.args + node.args.kwonlyargs)
    gets = {(n.func.value.id, n.args[0].value) for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'get'
            and isinstance(n.func.value, ast.Name) and n.args and isinstance(n.args[0], ast.Constant)}
    assert gets == {tuple(v) for v in row['named_dict_gets']}
    if row['function'] == '_persist_verified_snapshot_durably':
        assert ('result', 'durable_committed') not in gets
        assert {('result', 'ok'), ('result', 'snapshot_as_of'), ('result', 'opportunity_pool_count')} <= gets
    else:
        assert ('durable_result', 'cache_status') not in gets
assert observations['incremental_helper_publisher_keyword_args'] == []
endpoint = source('web/api/public-snapshot.js')
assert endpoint.index('validateSnapshotPublication(await requestBodyValue(request))') < endpoint.index('await persistSnapshot(snapshot)') < endpoint.index('await publishRuntimeSnapshot(snapshot)')
assert 'durable_committed: true' in endpoint and "cacheStatus = 'RETRY_REQUIRED'" in endpoint
store = source('web/api/_publicIntelligenceDb.js')
body = store[store.index('export async function persistPublicVerifiedSnapshot'):store.index('export async function latestPublicVerifiedSnapshot')]
assert body.index('await ensureSchema()') < body.index('await sql.begin(') < body.index('pg_advisory_xact_lock') < body.index('INSERT INTO public_verified_snapshots') < body.index('const readBack = await tx') < body.index('persisted: true')
assert 'PUBLIC_SNAPSHOT_ROLLBACK_REJECTED' in body and 'PUBLIC_SNAPSHOT_REVISION_CONFLICT' in body
assert "payload->>'snapshot_as_of' AS revision_as_of" in body and '::text::timestamptz' in body
revision = source('web/api/_snapshotRevision.js')
assert r'\d{1,6}' in revision and 'BigInt' in revision
b = read('budget-contract.json')
assert b['deep_publish_work_through_ack_seconds'] + b['post_confirmation_reserve_seconds'] == b['deep_publish_total_seconds'] == 270
assert b['full_http_cap_latest_build_elapsed_seconds'] == 270 - 60 - 30 - 1 == 179
assert b['authority_http_cap_seconds'] == 30 and b['local_http_retries'] == 0
for key in ['incremental_parent_origin_reset', 'node_or_sql_protocol_change', 'queue_lease_health_pending_protocol_change',
            'hard_cancel_guaranteed', 'physical_no_late_write_guaranteed', 'crash_durable_receipt_guaranteed', 'apply_allowed', 'migration_usable']:
    assert b[key] is False, key
assert read('receipt-contract.json')['late_valid_ack_preserves_confirmed']
assert len(read('go-no-go.json')['proposed_implementation_files']) == 7
c = json.loads(source('docs/project/checkpoint.json'))
assert c['latest_code_validated_head'].startswith('b584bcf')
assert c['current_authorization_scope']['F2_code_this_round'] is False
assert c['publish_budget_receipt_contract']['application_sdk_or_tests_executed'] is False
assert read('completion.json')['within_foreground_budget']
assert observations['historical_tests']['rerun_this_round'] is False
for name, digest in read('manifest.json')['sha256'].items():
    assert sha((ROOT / name).read_bytes()) == digest, name
print('PASS: 46 source references; 492 protected files; 3 static gaps; source commit/ACK order; 270/210/60 arithmetic; docs-only scope and manifest. No app/SDK/tests executed.')
