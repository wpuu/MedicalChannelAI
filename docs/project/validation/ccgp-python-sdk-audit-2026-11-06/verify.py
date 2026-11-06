"""Offline static evidence verification. Never imports or executes downloaded SDK."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
read=lambda p:json.loads(p.read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()

for entry in read(HERE/'manifest.json')['files']:
    data=(HERE/entry['path']).read_bytes()
    assert len(data)==entry['bytes'] and sha(data)==entry['sha256'],entry['path']
for entry in read(HERE/'download-ledger.json'):
    assert sha((HERE/entry['file']).read_bytes())==entry['sha256'],entry['file']
for package in read(HERE/'audit-summary.json')['packages']:
    archive=HERE/package['filename']
    assert sha(archive.read_bytes())==package['sha256']
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            view=HERE/'wheel-source'/name
            if view.is_file(): assert view.read_bytes()==z.read(name),name
provenance=read(HERE/'provenance.json')
assert len(provenance['source_matches'])==5
for entry in provenance['source_matches']:
    official=(HERE/'official-source'/entry['path']).read_bytes()
    assert sha(official)==entry['official_sha256']
    assert entry['wheel_bytes_equal_official_commit'] and official==(HERE/'wheel-source'/entry['path']).read_bytes()

# Parse signatures as data; no compilation/import/runtime evaluation of SDK.
tree=ast.parse((HERE/'wheel-source/vercel/cache/runtime_cache.py').read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RuntimeCache')
get=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='get')
assert [n.arg for n in get.args.args]==['self','key'] and not get.args.kwonlyargs and get.args.kwarg is None
summary=read(HERE/'audit-summary.json')
assert summary['candidate_only'] and not summary['deployed_version_verified']
assert not summary['sdk_installed_or_imported_or_executed']
assert summary['findings']['real_integration']=='NO_GO'
assert not summary['apply_allowed'] and not summary['migration_usable']
names=subprocess.check_output(['git','ls-tree','-r','--name-only','315136a','--',
    'web/pipeline/data','web/pipeline/tests/fixtures','docs/project/validation'],cwd=ROOT,text=True).splitlines()
inventory={name:sha((ROOT/name).read_bytes()) for name in names}
integrity=read(HERE/'input-integrity.json')
assert len(inventory)==integrity['protected_file_count']==324
assert sha(json.dumps(inventory,sort_keys=True,separators=(',',':')).encode())==integrity['inventory_sha256']
subprocess.run(['git','diff','--exit-code','315136a','--','web',*names],cwd=ROOT,check=True,capture_output=True)
assert read(HERE/'completion.json')['within_foreground_deadline']
print('PASS:6wheel hashes,5official source matches,get signature,324unchanged inputs; STATIC ONLY,NO SDK execution')
