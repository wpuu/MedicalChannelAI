"""Offline document/source integrity only; never imports project/SDK modules."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
read=lambda p:json.loads(p.read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()
for entry in read(HERE/'manifest.json')['files']:
    data=(HERE/entry['path']).read_bytes()
    assert len(data)==entry['bytes'] and sha(data)==entry['sha256'],entry['path']
refs=read(HERE/'source-references.json')['references']
for item in refs:
    data=(ROOT/item['path']).read_bytes()
    assert sha(data)==item['sha256'] and item['line']<=len(data.decode().splitlines())
findings=read(HERE/'findings.json')['findings']
assert [item['id'] for item in findings]==['F1','F2','F3']
assert all(not item['new_behavior_reproduction'] and not item['online_fault_verified'] for item in findings)
summary=read(HERE/'validation-summary.json')
assert len(refs)==summary['source_reference_count']
assert not summary['test_suite_executed'] and not summary['sdk_or_application_function_executed']
assert summary['network_calls']==0 and not summary['apply_allowed'] and not summary['migration_usable']
names=subprocess.check_output(['git','ls-tree','-r','--name-only','d9882a0','--',
    'web/pipeline/data','web/pipeline/tests/fixtures','docs/project/validation'],cwd=ROOT,text=True).splitlines()
inventory={name:sha((ROOT/name).read_bytes()) for name in names}
proof=read(HERE/'input-integrity.json')
assert len(inventory)==proof['protected_file_count']==387
assert sha(json.dumps(inventory,sort_keys=True,separators=(',',':')).encode())==proof['inventory_sha256']
subprocess.run(['git','diff','--exit-code','d9882a0','--','web','.github',*names],cwd=ROOT,check=True,capture_output=True)
assert read(HERE/'completion.json')['within_foreground_deadline']
print('PASS:3static findings accurately labelled,source references verified,387inputs unchanged; NO behavior/live reproduction')
