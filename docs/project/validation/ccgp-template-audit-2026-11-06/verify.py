"""Verify immutable evidence and reproduce known gate failures entirely offline."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
load = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = load(HERE / 'manifest.json')
for item in manifest['files']:
    path = HERE / item['path']
    assert path.stat().st_size == item['bytes'], path
    assert sha(path) == item['sha256'], path
corpus_path = ROOT / manifest['corpus']['path']
assert sha(corpus_path) == manifest['corpus']['sha256']
corpus = load(corpus_path)
for case in corpus['cases']:
    path = corpus_path.parent / case['file']
    assert sha(path) == case['sha256']
    assert path.stat().st_size == case['raw_bytes']
    if case['kind'] == 'SYNTHETIC_DERIVED_NEGATIVE':
        base = corpus_path.parent / case['base_official_file']
        assert sha(base) == case['base_official_sha256']
        expected = base.read_bytes().decode('utf-8').replace('</body>', case['inserted_html'] + '</body>', 1)
        assert expected.encode('utf-8') == path.read_bytes()
inventory = load(HERE / 'local-inventory.json')
for item in inventory['baseline_files']:
    assert sha(ROOT / item['path']) == item['sha256'], 'Historical baseline changed; recreate proposal'
validation = load(HERE / 'validation-summary.json')
for item in validation['source_files']:
    assert sha(ROOT / item['path']) == item['sha256'], 'Evaluator changed; create new evidence'
sys.path.insert(0, str(ROOT / 'web/pipeline/scripts'))
from audit_ccgp_product_backfill import audit
baseline = [ROOT / item['path'] for item in inventory['baseline_files']]
replayed = audit(corpus_path, baseline)
assert replayed == load(HERE / 'audit-result.json')
assert (replayed['passed'], replayed['failed']) == (6, 4)
assert replayed['apply_allowed'] is False
assert len(replayed['patch_proposals']) == 1
assert all(p['apply_allowed'] is False for p in replayed['patch_proposals'])
bootstrap = load(HERE / 'bootstrap-gate-proof.json')
assert (bootstrap['passed'], bootstrap['failed'], bootstrap['gate_pass']) == (1, 2, False)
assert bootstrap['network_requests'] == 0
assert bootstrap['runtime_or_database_writes'] is False
assert load(HERE / 'production-boundary.json')['production']['commit'] == '3216fd940dabfa7714383b6436908f9b72ff8a9c'
print('PASS evidence integrity and offline reproduction; template6/10 and bootstrap1/3 gates remain BLOCKED, no backfill applied')
