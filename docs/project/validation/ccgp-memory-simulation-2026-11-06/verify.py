"""Rebuild the frozen memory envelope and verify the four stages with network blocked."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for entry in read(HERE/'manifest.json')['files']:
    path=HERE/entry['path'];assert path.stat().st_size==entry['bytes'] and sha(path)==entry['sha256'],path
for entry in read(HERE/'validation-summary.json')['source_files']:
    assert sha(ROOT/entry['path'])==entry['sha256'],'Code changed: generate new evidence'
proof=read(HERE/'invariants-proof.json')
for name,digest in proof['input_files'].items():assert sha(ROOT/name)==digest,'Frozen input changed'
sys.path.insert(0,str(ROOT/'web/pipeline/scripts'))
from simulate_ccgp_product_corrections import simulate_overlay,simulate_rollback
from audit_ccgp_product_backfill import object_hash
prior=ROOT/'docs/project/validation/ccgp-product-dry-run-2026-11-06'
change=read(prior/'change-set.json');recipe=read(HERE/'state-recipe.json')
state={k:deepcopy(recipe[k]) for k in ('schema_version','input_kind','target_scope','events','pending')}
state['records']=[row for path in recipe['record_sources'] for row in read(ROOT/path)]
assert object_hash(state)==recipe['expected_state_sha256']
original=deepcopy(state)
verification={'manifest_path':ROOT/'web/pipeline/tests/fixtures/ccgp_template_audit_20261106/manifest.json',
    'baseline_paths':[ROOT/path for path in recipe['record_sources']],
    'request_path':ROOT/'web/pipeline/tests/fixtures/ccgp_product_dry_run_request_20261106.json',
    'expected_request_sha256':change['reviewed_request_sha256'],'expected_scope':recipe['target_scope']}
with patch('socket.create_connection',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_FORBIDDEN')):
    after,applied=simulate_overlay(change,state,expected_state_sha256=object_hash(state),**verification)
    repeated,replay=simulate_overlay(change,after,expected_state_sha256=object_hash(after),**verification)
    restored,rollback=simulate_rollback(change,after,applied['receipt'],expected_receipt_sha256=object_hash(applied['receipt']),**verification)
    again,rollback_replay=simulate_rollback(change,restored,applied['receipt'],expected_receipt_sha256=object_hash(applied['receipt']),**verification)
assert state==original and restored==original and again==original and repeated==after
reports=read(HERE/'roundtrip.json')
assert [applied,replay,rollback,rollback_replay]==[reports[k] for k in ('overlay','overlay_replay','rollback','rollback_replay')]
assert (HERE/'roundtrip.json').read_bytes()==(HERE/'roundtrip-replay.json').read_bytes()
assert [r['changed_record_count'] for r in (applied,replay,rollback,rollback_replay)]==[2,0,2,0]
assert all(r['apply_allowed'] is False and r['runtime_cas_implemented'] is False for r in (applied,replay,rollback,rollback_replay))
assert object_hash(restored)==proof['before_state_sha256']
assert (read(HERE/'audit-result.json')['passed'],read(HERE/'audit-result.json')['failed'])==(10,0)
assert (read(HERE/'bootstrap-gate-proof.json')['passed'],read(HERE/'bootstrap-gate-proof.json')['failed'])==(3,0)
assert 'Ran 984 tests' in (HERE/'python-tests.log').read_text()
assert (HERE/'python-tests.log').read_text().strip().endswith('OK')
assert read(HERE/'completion.json')['within_foreground_deadline'] is True
print('PASS:984Python,10/3gates,892record restoration,2/0/2/0idempotence,input integrity,no runtime CAS/apply')
