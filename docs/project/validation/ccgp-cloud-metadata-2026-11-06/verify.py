"""Offline integrity/scope crosscheck of saved metadata; makes no network calls.

This checks the saved observation, not a provider signature or cache identity.
"""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
read=lambda p:json.loads(p.read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()
encode=lambda obj:json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

for entry in read(HERE/'manifest.json')['files']:
    data=(HERE/entry['path']).read_bytes()
    assert len(data)==entry['bytes'] and sha(data)==entry['sha256'],entry['path']

observation=read(HERE/'deployment-summary.json')
args=observation['args']
assert args['projectId']=='prj_7fk44eKUhdbfTUaXxEBMgIzZiqUM'
assert args['teamId']=='team_jEy8Ex9vRDBdXj1cQPKF8sRd'
assert args['sha']=='82cc43f06c774969eab0fe44f0afc012f37cadac'
assert args['target']=='preview' and args['limit']==1
assert observation['record_count']==1 and observation['exact_deployment_match'] and observation['expected_sha_match']
row=observation['deployments'][0]
assert row['uid']=='dpl_8Jhc4imHEd6ndBUoth5xBVTrAyL1'
assert row['state']=='READY' and row['target'] is None
assert row['meta']['githubCommitSha']==args['sha']
assert row['meta']['githubCommitRef']==args['branch']=='codex/p0-reliability-contracts'
assert args['since']<row['created']<args['until']
attempts=read(HERE/'query-attempts.json')
assert attempts['deployment_summary_queries']==3 and attempts['source_tree_queries']==1
assert len(attempts['attempts'])==2
assert all(attempt['args']==args for attempt in attempts['attempts'])
assert 'record_count' not in attempts['attempts'][0]  # No false empty-result evidence.

directory=read(HERE/'deployment-source-tree.json')
assert directory['args']['id']==row['uid'] and directory['args']['teamId']==args['teamId']
assert directory['is_error'] and directory['error_codes']==[{'code':'not_found'}]
assert not directory['raw_file_contents_requested'] and not directory['source_tree_complete_verified']

summary=read(HERE/'validation-summary.json')
assert summary['cloud_metadata_calls']==4 and summary['real_runtime_integration']=='NO_GO'
for key in ('scope_provenance_verified','installed_sdk_version_verified','execution_channel_verified',
            'project_latest_deployment_verified','apply_allowed','migration_usable','full_suite_rerun'):
    assert summary[key] is False,key
for key in ('runtime_cache_reads','runtime_cache_writes','database_reads','database_writes',
            'business_http_calls','function_queue_model_calls'):
    assert summary[key]==0,key

source=read(HERE/'local-source-crosscheck.json')
pyproject=subprocess.check_output(['git','show',args['sha']+':web/pyproject.toml'],cwd=ROOT)
assert sha(pyproject)==source['pyproject_bytes_sha256']
assert source['selected_paths_in_git_tree']==['web/pyproject.toml']
assert not source['actual_deployment_bundle_bytes_verified']
names=subprocess.check_output(['git','ls-tree','-r','--name-only','1238596','--',
    'web/pipeline/data','web/pipeline/tests/fixtures','docs/project/validation'],cwd=ROOT,text=True).splitlines()
inventory={name:sha((ROOT/name).read_bytes()) for name in names}
proof=read(HERE/'input-integrity.json')
assert len(inventory)==proof['protected_file_count']==314
assert sha(encode(inventory))==proof['protected_inventory_sha256']
subprocess.run(['git','diff','--exit-code','1238596','--','web',*names],cwd=ROOT,check=True,capture_output=True)
assert read(HERE/'completion.json')['within_foreground_deadline'] is True
print('PASS: scoped saved deployment metadata, explicit directory failure,314inputs unchanged; no fresh cloud query or runtime authentication')
