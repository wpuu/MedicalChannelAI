"""Replay LOCAL/SYNTHETIC cache wrappers; never instantiate a runtime client."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT/'web'))
import collector_readonly_export as core
from collector_epoch import epoch_key

read = lambda path: json.loads(path.read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


class LocalGetOnly:
    def __init__(self, values):
        self.values = deepcopy(values)
        self.reads = []

    def get(self, key):
        self.reads.append(key)
        return self.values.get(key)


def build_reader(recipe):
    values = {}
    physical = lambda key: epoch_key(key, recipe['scope']['preview_epoch'])
    for key, spec in core._plan().items():
        values[physical(key)] = [] if spec['kind'] in recipe['present_empty_kinds'] else None
    records = read(ROOT/recipe['record_source'])
    for identity in recipe['record_ids']:
        record = next(row for row in records if row['opportunity_id']==identity)
        values[physical('medicalchannelai:collector-regional-records:v3:'+record['facts']['market_code'])] = [record]
    for key, value in recipe['synthetic_auxiliary_values'].items():
        values[physical(key)] = value
    return LocalGetOnly(values)


def summarize(result):
    return {key:value for key,value in result.items() if key!='shards'} | {
        'shards':{key:{field:value for field,value in shard.items() if field!='value'}
                  for key,shard in result['shards'].items()}}


def protected_digest():
    names = subprocess.check_output(['git','ls-tree','-r','--name-only','246c139', '--',
        'web/pipeline/data','web/pipeline/tests/fixtures','docs/project/validation'],cwd=ROOT,text=True).splitlines()
    inventory = {name:sha((ROOT/name).read_bytes()) for name in names}
    # All pre-existing frozen trees must match the actual starting commit too.
    subprocess.run(['git','diff','--exit-code','246c139','--',*names],cwd=ROOT,check=True,capture_output=True)
    return {'file_count':len(inventory),'inventory_sha256':sha(encode(inventory))}


def replay():
    recipe=read(HERE/'cache-recipe.json')
    reader=build_reader(recipe); original=deepcopy(reader.values)
    with patch('collector_epoch.RuntimeCache',side_effect=AssertionError('CLIENT_FORBIDDEN')), \
         patch('socket.create_connection',side_effect=AssertionError('NETWORK_FORBIDDEN')), \
         patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_FORBIDDEN')):
        normal=core.observe_d_canonical(reader,scope=recipe['scope'],expected_scope=recipe['scope'])
        repeated=core.observe_d_canonical(build_reader(recipe),scope=recipe['scope'],expected_scope=recipe['scope'])
        empty_reader=LocalGetOnly({})
        empty=core.observe_d_canonical(empty_reader,scope=recipe['scope'],expected_scope=recipe['scope'])
    assert normal==repeated and reader.values==original
    assert reader.reads==[epoch_key(key,recipe['scope']['preview_epoch']) for key in core._plan()]*2
    assert all('verified-snapshot' not in key for key in reader.reads+empty_reader.reads)
    assert not normal['migration_usable'] and not normal['apply_allowed'] and not normal['coverage']['complete']
    assert all(shard['value'] is None for shard in empty['shards'].values())
    return normal,empty,reader.reads


if __name__=='__main__':
    for entry in read(HERE/'manifest.json')['files']:
        data=(HERE/entry['path']).read_bytes()
        assert len(data)==entry['bytes'] and sha(data)==entry['sha256'],entry['path']
    summary=read(HERE/'validation-summary.json')
    for entry in summary['source_files']:
        assert sha((ROOT/entry['path']).read_bytes())==entry['sha256'],entry['path']
    assert protected_digest()==read(HERE/'invariants-proof.json')['protected_inputs']
    normal,empty,trace=replay()
    assert summarize(normal)==read(HERE/'normal-observation.json')
    assert summarize(empty)==read(HERE/'uninitialized-observation.json')
    assert trace==read(HERE/'read-trace.json')
    assert sha(encode(normal))==summary['normal_envelope_sha256']
    assert sha(encode(empty))==summary['empty_envelope_sha256']
    assert (read(HERE/'audit-result.json')['passed'],read(HERE/'audit-result.json')['failed'])==(10,0)
    assert (read(HERE/'bootstrap-gate-proof.json')['passed'],read(HERE/'bootstrap-gate-proof.json')['failed'])==(3,0)
    assert 'Ran 1007 tests' in (HERE/'python-tests.log').read_text()
    assert (HERE/'python-tests.log').read_text().strip().endswith('OK')
    assert read(HERE/'completion.json')['within_foreground_deadline'] is True
    print('PASS:1007Python,10/3gates,58keys/116get-only reads,d-only,no fallback,inputs unchanged; OFFLINE CORE ONLY')
