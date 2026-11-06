"""Static workflow/evidence integrity only; does not execute workflow or tests."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import yaml

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
    assert sha((ROOT / path).read_bytes()) == digest
summary = read('validation-summary.json')
path = '.github/workflows/regional-medical-refresh.yml'
before = subprocess.check_output(['git', 'show', f'8b3eba8:{path}'], cwd=ROOT).decode()
after = subprocess.check_output(['git', 'show', f"{summary['workflow_head']}:{path}"], cwd=ROOT).decode()
added_path = "      - 'web/pipeline/tests/test_regional_cli_completeness.py'\n"
added_module = '            tests.test_regional_cli_completeness \\\n'
assert after.count(added_path) == after.count(added_module) == 1
assert after.replace(added_path, '').replace(added_module, '') == before
workflow = yaml.load(after, Loader=yaml.BaseLoader)
run = workflow['jobs']['refresh']['steps'][1]['run']
assert run.startswith('set -euo pipefail\ncd web/pipeline\n')
argv = shlex.split(run.split('\n', 2)[2].replace('\\\n', ' '))
assert argv[:3] == ['python3', '-m', 'unittest']
tests = read('test-results.json')
assert argv[3:] == tests['modules'] and len(tests['modules']) == 8
assert (tests['tests_run'], tests['failures'], tests['errors'], tests['skipped']) == (94, 0, 0, 0)
assert tests['passed'] and not tests['workflow_executed']
assert not tests['full1079_rerun'] and not tests['frozen10_original3_rerun']
assert read('workflow-structure.json')['other_yaml_structure_unchanged']
for path, digest in summary['source_sha256'].items():
    data = subprocess.check_output(['git', 'show', f"{summary['workflow_head']}:{path}"], cwd=ROOT)
    assert sha(data) == digest, path
changes = subprocess.check_output(['git', 'diff', '--name-only', '8b3eba8', summary['workflow_head']], cwd=ROOT, text=True).splitlines()
assert changes == ['.github/workflows/regional-medical-refresh.yml']
subprocess.run(['git', 'diff', '--exit-code', '8b3eba8', summary['workflow_head'], '--', 'web'], cwd=ROOT, check=True, capture_output=True)
proof = read('input-integrity.json')
names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', '8b3eba8', '--',
    'web/pipeline/data', 'web/pipeline/tests/fixtures', 'docs/project/validation'], cwd=ROOT, text=True).splitlines()
assert len(names) == proof['protected_file_count'] == 441 and set(names) == set(proof['files'])
for path, digest in proof['files'].items():
    assert sha((ROOT / path).read_bytes()) == digest, path
log = (HERE / 'selected-tests.log').read_text()
assert 'Ran 94 tests' in log and '\nOK\n' in log
assert not summary['workflow_executed_or_triggered'] and not summary['deployment_or_push']
assert not summary['apply_allowed'] and not summary['migration_usable']
assert read('completion.json')['within_foreground_deadline']
print('PASS:exactly2workflow additions,8modules94local tests,441inputs unchanged;no workflow trigger/full rerun')
