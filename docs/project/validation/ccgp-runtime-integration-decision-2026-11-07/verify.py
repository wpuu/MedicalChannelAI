"""Offline checks of the closed decision and its frozen evidence. No SDK imports."""
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
decision=read(HERE/'decision.json')
assert decision['decision']=='NO_GO_PAUSE_AND_CLOSE_CURRENT_SDK_INTEGRATION_BRANCH'
for key in ('application_files_to_change_now','approved_dependency_versions_for_deployment',
            'new_routes','new_configuration_changes','new_permissions_requested_now','branches_to_retry_or_simulate'):
    assert decision[key]==[],key
assert decision['execution_carrier_selected'] is None
assert not decision['apply_allowed'] and not decision['migration_usable']
refs=read(HERE/'evidence-index.json')['references']
assert len(refs)==19
for item in refs:
    data=(ROOT/item['path']).read_bytes()
    assert sha(data)==item['sha256'] and item['line']<=len(data.decode().splitlines())
names=subprocess.check_output(['git','ls-tree','-r','--name-only','75c02dc','--',
    'web/pipeline/data','web/pipeline/tests/fixtures','docs/project/validation'],cwd=ROOT,text=True).splitlines()
inventory={name:sha((ROOT/name).read_bytes()) for name in names}
proof=read(HERE/'input-integrity.json')
assert len(inventory)==proof['protected_file_count']==380
assert sha(json.dumps(inventory,sort_keys=True,separators=(',',':')).encode())==proof['inventory_sha256']
subprocess.run(['git','diff','--exit-code','75c02dc','--','web',*names],cwd=ROOT,check=True,capture_output=True)
assert read(HERE/'completion.json')['within_foreground_deadline']
print('PASS:NO-GO workflow closed,19source references,380inputs unchanged,no app/lock/test changes; DOCUMENTATION ONLY')
