"""Replay the guard using the existing frozen recipe and synthetic clock only."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'web'))
import collector_readonly_export as core
import collector_readonly_guard as guard

prior_folder=HERE.parent/'ccgp-readonly-export-2026-11-06'
spec=importlib.util.spec_from_file_location('frozen_export_fixture',prior_folder/'verify.py')
prior=importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
read=lambda p:json.loads(p.read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()
encode=lambda value:json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


class Clock:
    def __init__(self): self.now=0.0
    def __call__(self): return self.now


class Transport:
    input_kind='SYNTHETIC_LOCAL_STUB'
    def __init__(self,scope,values):
        self.target_scope=deepcopy(scope)
        self.values=deepcopy(values)
        self.calls=[]
    def get(self,key,*,timeout_seconds):
        self.calls.append({'key':key,'timeout_seconds':timeout_seconds})
        return self.values.get(key)


def replay():
    recipe=read(prior_folder/'cache-recipe.json')
    scope=recipe['scope']; values=prior.build_reader(recipe).values
    transport=Transport(scope,values); empty_transport=Transport(scope,{})
    original=deepcopy(transport.values)
    with patch('collector_epoch.RuntimeCache',side_effect=AssertionError('CLIENT_FORBIDDEN')), \
         patch('socket.create_connection',side_effect=AssertionError('NETWORK_FORBIDDEN')), \
         patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_FORBIDDEN')), \
         patch('time.sleep',side_effect=AssertionError('SLEEP_FORBIDDEN')):
        normal=guard.observe_synthetic_d_canonical(transport,scope=scope,expected_scope=scope,monotonic=Clock())
        repeated=guard.observe_synthetic_d_canonical(Transport(scope,values),scope=scope,expected_scope=scope,monotonic=Clock())
        empty=guard.observe_synthetic_d_canonical(empty_transport,scope=scope,expected_scope=scope,monotonic=Clock())
        rejected=Transport(scope,{})
        facade=guard.SyntheticGetOnlyGuard(rejected,scope=scope,expected_scope=scope,monotonic=Clock())
        try: facade.get('medicalchannelai:verified-snapshot:published:v2')
        except core.ExportRejected as exc: key_error=str(exc)
        else: raise AssertionError('Invalid key accepted')
        deadline=Clock(); expired=Transport(scope,{})
        facade=guard.SyntheticGetOnlyGuard(expired,scope=scope,expected_scope=scope,monotonic=deadline)
        deadline.now=110.0
        try: facade.get(transport.calls[0]['key'])
        except core.ExportRejected as exc: deadline_error=str(exc)
        else: raise AssertionError('Expired read accepted')
    assert normal==repeated and transport.values==original
    assert prior.summarize(normal)==read(prior_folder/'normal-observation.json')
    assert prior.summarize(empty)==read(prior_folder/'uninitialized-observation.json')
    assert [call['key'] for call in transport.calls]==read(prior_folder/'read-trace.json')
    assert len(transport.calls)==116 and all(call['timeout_seconds']==2.0 for call in transport.calls)
    assert rejected.calls==expired.calls==[]
    assert not normal['apply_allowed'] and not normal['migration_usable'] and not normal['scope_provenance_verified']
    return {'normal_envelope_sha256':sha(encode(normal)),
        'empty_envelope_sha256':sha(encode(empty)),
        'normal_summary':prior.summarize(normal), 'read_trace':transport.calls,
        'rejections':{'invalid_key':{'code':key_error,'transport_calls':0},
                      'expired_before_read':{'code':deadline_error,'transport_calls':0}},
        'repeat_envelope_equal':True,'input_values_unchanged':True,
        'kernel_envelopes_equal_prior_frozen_outputs':True,
        'hard_cancellation_implemented':False,'real_backend_authenticated':False,
        'cloud_access_performed':False,'apply_allowed':False,'migration_usable':False}


if __name__=='__main__':
    for entry in read(HERE/'manifest.json')['files']:
        data=(HERE/entry['path']).read_bytes()
        assert len(data)==entry['bytes'] and sha(data)==entry['sha256'],entry['path']
    summary=read(HERE/'validation-summary.json')
    for entry in summary['source_files']:
        assert sha((ROOT/entry['path']).read_bytes())==entry['sha256'],entry['path']
    proof=read(HERE/'invariants-proof.json')
    names=subprocess.check_output(['git','ls-tree','-r','--name-only','78bb17b','--',
        'web/pipeline/data','web/pipeline/tests/fixtures','docs/project/validation'],cwd=ROOT,text=True).splitlines()
    inventory={name:sha((ROOT/name).read_bytes()) for name in names}
    assert len(inventory)==proof['protected_file_count'] and sha(encode(inventory))==proof['protected_inventory_sha256']
    subprocess.run(['git','diff','--exit-code','78bb17b','--',*names],cwd=ROOT,check=True,capture_output=True)
    assert replay()==read(HERE/'guard-proof.json')
    assert 'Ran 1031 tests' in (HERE/'python-tests.log').read_text()
    assert (HERE/'python-tests.log').read_text().strip().endswith('OK')
    assert (read(HERE/'audit-result.json')['passed'],read(HERE/'audit-result.json')['failed'])==(10,0)
    assert (read(HERE/'bootstrap-gate-proof.json')['passed'],read(HERE/'bootstrap-gate-proof.json')['failed'])==(3,0)
    assert read(HERE/'completion.json')['within_foreground_deadline'] is True
    print('PASS:1031Python,10/3gates,116bounded get-only calls,identical frozen envelopes,inputs unchanged; SYNTHETIC ONLY')
