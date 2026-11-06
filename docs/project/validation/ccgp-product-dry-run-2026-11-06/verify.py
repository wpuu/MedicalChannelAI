"""Reproduce the frozen dry-run with network blocked; never applies or exports runtime state."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
read=lambda path:json.loads(path.read_text())
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
for item in read(HERE/'manifest.json')['files']:
    file=HERE/item['path']
    assert file.stat().st_size==item['bytes'] and sha(file)==item['sha256'],file
summary=read(HERE/'validation-summary.json')
for item in summary['source_files']:
    assert sha(ROOT/item['path'])==item['sha256'],'Code changed: generate new evidence'
proof=read(HERE/'replay-proof.json')
for name,digest in proof['input_files'].items():
    assert sha(ROOT/name)==digest,'Frozen input changed'
assert (HERE/'change-set.json').read_bytes()==(HERE/'change-set-replay.json').read_bytes()
sys.path.insert(0,str(ROOT/'web/pipeline/scripts'))
from audit_ccgp_product_backfill import build_dry_run,object_hash
lock=read(HERE/'request-lock.json')
corpus=ROOT/'web/pipeline/tests/fixtures/ccgp_template_audit_20261106/manifest.json'
baselines=[ROOT/'web/pipeline/data/tianjin_live_ccgp_records.json',ROOT/'web/pipeline/data/regional_live_ccgp_records.json']
request=ROOT/'web/pipeline/tests/fixtures/ccgp_product_dry_run_request_20261106.json'
with patch('socket.create_connection',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_FORBIDDEN')):
    actual=build_dry_run(corpus,baselines,request,expected_request_sha256=lock['request_sha256'],expected_scope=lock['target_scope'])
assert actual==read(HERE/'change-set.json')
assert actual['selected_count']==2 and actual['selection_limit']==5
assert not any(actual[key] for key in ['apply_allowed','runtime_canonical_exported','migration_complete','publishes_snapshot','writes_runtime_state','network_requests'])
old_by_id={r['opportunity_id']:r for p in baselines for r in read(p)}
for change in actual['changes']:
    old=old_by_id[change['identity']['opportunity_id']]
    new=change['candidate_record']
    assert object_hash(old)==change['before_record_sha256']
    assert object_hash(new)==change['candidate_record_sha256']
    assert old['source']==new['source']
    for key,value in old['facts'].items():
        if key not in ('product_items','product_categories'):assert new['facts'][key]==value
    assert all(e['source_url']==old['source']['url'] and e['locator'] for e in change['after']['evidence'])
assert (read(HERE/'audit-result.json')['passed'],read(HERE/'audit-result.json')['failed'])==(10,0)
assert (read(HERE/'bootstrap-gate-proof.json')['passed'],read(HERE/'bootstrap-gate-proof.json')['failed'])==(3,0)
assert 'Ran 966 tests' in (HERE/'python-tests.log').read_text()
assert (HERE/'python-tests.log').read_text().strip().endswith('OK')
assert read(HERE/'completion.json')['within_foreground_deadline'] is True
print('PASS:966Python,10/3gates,2deterministic evidence-complete proposals,input integrity and zero network/runtime/apply')
