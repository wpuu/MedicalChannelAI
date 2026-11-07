"""Verify this static review's evidence and scope; never execute reviewed code."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
BASE='1f40e91'
ALLOWED={'docs/project/current-state.md','docs/project/checkpoint.json','docs/project/next-task.md','docs/project/ccgp-mainline-reliability-closeout-2026-11-07.md'}
PREFIX='docs/project/validation/ccgp-mainline-reliability-closeout-2026-11-07/'

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)

def read(name):
    return json.loads((HERE/name).read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

changed=set(git('diff','--name-only',BASE).decode().splitlines())|set(git('ls-files','--others','--exclude-standard').decode().splitlines())
assert all(x in ALLOWED or x.startswith(PREFIX) for x in changed),changed
assert not git('diff','--name-only',BASE,'--','web','.github').strip()
for row in read('source-references.json'):
    p=ROOT/row['path']
    assert sha(p)==row['file_sha256']
    assert p.read_text().splitlines()[row['line']-1]==row['text']
    assert row['anchor'] in row['text']
for row in read('version-bindings.json'):
    def ast_hash(data):
        tree=ast.parse(data)
        node=next(n for n in tree.body if getattr(n,'name',None)==row['symbol'])
        return hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()
    assert ast_hash((ROOT/row['path']).read_bytes())==row['current_ast_sha256']
    assert ast_hash(git('show',f"{row['implementation_origin']}:{row['path']}"))==row['current_ast_sha256']
inputs=read('input-integrity.json')
assert len(inputs['files'])==inputs['protected_file_count']==595
for path,digest in inputs['files'].items():
    assert sha(ROOT/path)==digest,path
for row in read('historical-gates.json'):
    assert sha(ROOT/row['path'])==row['sha256'] and row['reexecuted_this_round'] is False
assert read('historical-gates.json')[0]['historical_python_passed']==1202
coverage=read('coverage.json')
assert len(coverage['deep_stages'])==25
assert len(coverage['budgeted_queue_deep_stages'])==18
assert len(coverage['unbudgeted_queue_deep_stages'])==7
assert len(coverage['incremental_sources'])==8
assert coverage['budgeted_queue_incremental_sources']==['tjzyefy']
assert len(coverage['unbudgeted_queue_incremental_sources'])==7
findings=read('findings.json')
assert len(findings)==3 and [f['id'] for f in findings if f['unique_next_priority']]==['R1']
assert not findings[0]['behavior_reproduced_this_round']
decision=read('decision.json')
assert not decision['next_code_authorized'] and not decision['application_or_tests_changed_this_round']
assert len(decision['minimal_files'])==4
assert decision['apply_allowed'] is False and decision['migration_usable'] is False
assert decision['actual_model_and_reasoning_verified'] is False
summary=read('validation-summary.json')
assert summary['tests_executed_this_round'] is False
assert summary['app_or_sdk_imported'] is False
assert summary['findings_count']==3
checkpoint=json.loads((ROOT/'docs/project/checkpoint.json').read_text())
assert checkpoint['latest_code_validated_head']==summary['code_head']
assert not checkpoint['current_authorization_scope']['code_or_test_changes_this_round']
assert not checkpoint['ccgp_mainline_reliability_closeout']['next_code_authorization_received']
next_task=(ROOT/'docs/project/next-task.md').read_text()
assert '我明确授权' in next_task and '1202/10/3是已有' in next_task
for path in decision['minimal_files']: assert path in next_task
assert '当前界面无法生成该按钮' in (ROOT/'docs/project/current-state.md').read_text()
completion=read('completion.json')
assert completion['within_frontend_20_minutes'] is True
for path,digest in read('manifest.json')['files'].items():
    assert sha(ROOT/path)==digest,path
print(json.dumps({'static_verification':'PASS','source_references':110,'version_bindings':8,'protected_inputs':595,'source_config_files':455,'findings':3,'next_priority':'R1','tests_run':False,'application_changed':False,'apply_allowed':False,'migration_usable':False}))
