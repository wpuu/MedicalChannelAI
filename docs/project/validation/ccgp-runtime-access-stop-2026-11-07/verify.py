"""Static verification of frozen offline R1 evidence; no application or SDK imports."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent

def read(name):return json.loads((HERE/name).read_text())
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
s=read('validation-summary.json');base,code=s['starting_head'],s['code_head']
assert set(git('diff','--name-only',base,code).decode().splitlines())==set(s['authorized_files'])
for path,digest in s['source_sha256'].items():
 assert sha(ROOT/path)==digest
 assert hashlib.sha256(git('show',f'{code}:{path}')).hexdigest()==digest
added=[]
for path in s['authorized_files']:
 old=ast.parse(git('show',f'{base}:{path}'));new=ast.parse((ROOT/path).read_bytes())
 if '/tests/' in path:
  def methods(t):return {n.name for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')}
  a,b=methods(old),methods(new);assert a<=b
  added.extend(f'{path}:{n}' for n in b-a)
 else:
  allowed={'_run_ccgp','_run_event_batch'} if path=='web/collector_runtime.py' else {'scan_events','discover_candidates'}
  def other(t):return {n.name:ast.dump(n,include_attributes=False) for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name not in allowed}
  assert other(old)==other(new)
  # Preserve original prepare and data commit tail AST in both runtime functions.
  if path=='web/collector_runtime.py':
   for name,marker in [('_run_ccgp','CCGP_MERGE'),('_run_event_batch','EVENT_MERGE')]:
    def tail(tree):
     fn=next(n for n in tree.body if getattr(n,'name',None)==name)
     body=next(n for n in fn.body if isinstance(n,ast.Try)).body
     start=next(i for i,n in enumerate(body) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and any(isinstance(a,ast.Constant) and a.value==marker for a in n.value.args))
     return [ast.dump(n,include_attributes=False) for n in body[start:]]
    assert tail(old)==tail(new),name
assert sorted(added)==sorted(s['new_test_methods']) and len(added)==11
for row in read('source-references.json'):
 assert sha(ROOT/row['path'])==row['sha256']
 assert (ROOT/row['path']).read_text().splitlines()[row['line']-1]==row['text']
p=read('input-integrity.json');assert p['protected_file_count']==len(p['files'])==612
for path,digest in p['files'].items():assert sha(ROOT/path)==digest,path
other=read('unchanged-boundaries.json');assert len(other['git_blob_ids'])==other['other_file_count']==451
assert not git('diff','--name-only',base,'--',*other['git_blob_ids']).strip()
log=(HERE/'regression.log').read_text();assert 'Ran 1213 tests' in log and '\nOK\n' in log
assert 'FAILED (failures=9)' in (HERE/'before.log').read_text()
for filename,count in [('frozen-template-audit.json',10),('original-cli-gate.json',3)]:
 g=read(filename);assert g['passed']==count and g['failed']==0
cases=read('cases.json');assert len(cases['source_cases'])==78 and len(cases['helper_cases'])==10
for row in cases['source_cases']:
 cfg=row['config'];stage=cfg['stage'];mode=cfg.get('mode','http')
 assert row['pending_unchanged']
 if row['status']==503:assert row['committed_unchanged'] and row['success_clock_unchanged']
 if mode in ('http','wrapped','marker') and not cfg.get('retry') and cfg.get('use_budget',True):
  where=cfg.get('where','detail')
  if not cfg.get('mixed_hosts'):
   assert sum(call['kind']==where for call in row['calls'])==1
  assert 'secret' not in json.dumps(row['diagnostics'])
 if cfg.get('mixed_hosts'):
  hosts=[call['host'] for call in row['calls'] if call['kind']=='detail']
  assert hosts.count('www.ccgp.gov.cn')==1 and hosts.count('ccgp.gov.cn')>0
 if cfg.get('retry'):assert row['retry_request_count']>0
for path,digest in read('manifest.json')['files'].items():assert sha(ROOT/path)==digest,path
assert read('completion.json')['within_frontend_20_minutes'] is True
cp=json.loads((ROOT/'docs/project/checkpoint.json').read_text())
assert cp['latest_code_validated_head']==code and cp['ccgp_runtime_r1_access_stop']['status'].endswith('VERIFIED_OFFLINE')
assert cp['current_authorization_scope']['network_this_round'] is False
changed=set(git('diff','--name-only',code).decode().splitlines())|set(git('ls-files','--others','--exclude-standard').decode().splitlines())
assert all(p in {'docs/project/current-state.md','docs/project/checkpoint.json','docs/project/next-task.md','docs/project/ccgp-runtime-access-stop-2026-11-07.md'} or p.startswith('docs/project/validation/ccgp-runtime-access-stop-2026-11-07/') for p in changed)
print(json.dumps({'static_verification':'PASS','code_head':code,'python':1213,'new_behavior_tests':11,'templates':10,'original_cli':3,'protected_inputs':612,'other_files':451,'source_cases':78,'helper_cases':10,'apply_allowed':False,'migration_usable':False}))
