"""Verify this code-bound offline acceptance without network or state writes."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
read = lambda path: json.loads(path.read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
manifest = read(HERE / 'manifest.json')
for entry in manifest['files']:
    path = HERE / entry['path']
    assert path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], path
summary = read(HERE / 'validation-summary.json')
for entry in summary['source_files']:
    assert sha(ROOT / entry['path']) == entry['sha256'], 'Evaluator changed: generate new evidence'
corpus = ROOT / manifest['corpus']['path']
assert sha(corpus) == manifest['corpus']['sha256']
for case in read(corpus)['cases']:
    assert sha(corpus.parent / case['file']) == case['sha256']
inventory = read(ROOT / 'docs/project/validation/ccgp-template-audit-2026-11-06/local-inventory.json')
for entry in inventory['baseline_files']:
    assert sha(ROOT / entry['path']) == entry['sha256'], 'Historical input was changed'
sys.path.insert(0, str(ROOT / 'web/pipeline/scripts'))
from audit_ccgp_product_backfill import audit
actual = audit(corpus, [ROOT / entry['path'] for entry in inventory['baseline_files']])
assert actual == read(HERE / 'audit-result.json')
assert (actual['passed'], actual['failed']) == (10, 0)
assert actual['apply_allowed'] is False
assert len(actual['patch_proposals']) == 2
assert all(p['apply_allowed'] is False for p in actual['patch_proposals'])
cli = read(HERE / 'bootstrap-gate-proof.json')
assert (cli['passed'], cli['failed'], cli['gate_pass']) == (3, 0, True)
assert [case['exit_code'] for case in cli['results']] == [0, 2, 2]
assert (read(HERE / 'before-audit-result.json')['passed'], read(HERE / 'before-audit-result.json')['failed']) == (6, 4)
assert (read(HERE / 'before-bootstrap-gate-proof.json')['passed'], read(HERE / 'before-bootstrap-gate-proof.json')['failed']) == (1, 2)
assert 'Ran 945 tests' in (HERE / 'python-tests.log').read_text()
assert (HERE / 'python-tests.log').read_text().strip().endswith('OK')
assert 'Prebuild verification: PASS' in (HERE / 'build.log').read_text()
assert all(summary[key] is False for key in ['preview_deployed', 'queue_triggered', 'backfill_applied', 'new_browser_acceptance'])
assert read(HERE / 'production-boundary.json')['production']['commit'] == '3216fd940dabfa7714383b6436908f9b72ff8a9c'
assert read(HERE / 'completion.json')['within_foreground_deadline'] is True
print('PASS: code/fixture integrity,10/10 templates,3/3 CLI cases,945/build,2unapplied proposals and no deployment/backfill')
