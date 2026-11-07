"""Static evidence verification only; never imports application or SDK."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent

def read(name):
    return json.loads((HERE / name).read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

summary = read('validation-summary.json')
base, code = summary['starting_head'], summary['code_head']
assert set(git('diff', '--name-only', base, code).decode().splitlines()) == set(summary['authorized_files'])
for name, digest in summary['source_sha256'].items():
    assert sha(ROOT / name) == digest
    assert hashlib.sha256(git('show', f'{code}:{name}')).hexdigest() == digest
for record in read('source-references.json'):
    assert (ROOT / record['path']).read_text().splitlines()[record['line'] - 1] == record['text']
for name, allowed in {
    'web/collector_runtime.py': {'_run_ccgp', 'run_stage'},
    'web/collector_queue.py': {'process_collector_payload'},
    'web/pipeline/scripts/sync_ccgp_query.py': {'discover_candidates'},
}.items():
    old = ast.parse(git('show', f'{base}:{name}'))
    new = ast.parse((ROOT / name).read_text())
    def preserved(tree):
        return [ast.dump(n, include_attributes=False) for n in tree.body if getattr(n, 'name', None) not in allowed]
    assert preserved(old) == preserved(new), name
added = []
for name in summary['authorized_files']:
    if '/tests/' not in name:
        continue
    def methods(source):
        return {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_')}
    old, new = methods(git('show', f'{base}:{name}')), methods((ROOT / name).read_text())
    assert old <= new
    added.extend(f'{name}:{n}' for n in new - old)
assert sorted(added) == sorted(summary['new_test_methods']) and len(added) == 21
protected = read('input-integrity.json')
assert len(protected['files']) == protected['protected_file_count'] == 581
for name, digest in protected['files'].items():
    assert sha(ROOT / name) == digest, name
# Compare repository object identities for other files, without reading environment values.
other = read('unchanged-boundaries.json')
assert len(other) == 450
assert not git('diff', '--name-only', base, '--', *other).strip()
for filename, count in [('regression.log', 1202), ('directed.log', 145)]:
    log = (HERE / filename).read_text()
    assert f'Ran {count} tests' in log and '\nOK\n' in log
for filename, count in [('frozen-template-audit.json', 10), ('original-cli-gate.json', 3)]:
    evidence = read(filename)
    assert evidence['passed'] == count and evidence['failed'] == 0
cases = read('cases.json')
assert len(cases['source_cases']) == 44 and len(cases['helper_cases']) == 10 and len(cases['queue_cases']) == 4
for row in cases['source_cases']:
    assert row['committed_unchanged'] and row['pending_unchanged'] and row['success_clock_unchanged']
    assert not row['data_has_receipt']
    receipt = row.get('receipt')
    if receipt:
        assert receipt['source_transaction_committed'] is False
for name, digest in read('manifest.json')['files'].items():
    assert sha(ROOT / name) == digest, name
assert read('completion.json')['within_frontend_20_minutes'] is True
print(json.dumps({'static_verification': 'PASS', 'code_head': code, 'new_behavior_tests': 21, 'python': 1202, 'directed': 145, 'templates': 10, 'original_cli': 3, 'protected_inputs': 581, 'other_files': 450, 'apply_allowed': False, 'migration_usable': False}))
