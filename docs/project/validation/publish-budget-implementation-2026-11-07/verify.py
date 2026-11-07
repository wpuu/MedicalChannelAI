"""Static hashes and recorded acceptance only; no app/SDK/test execution."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def read(name):return json.loads((HERE/name).read_text())
def sha(data):return hashlib.sha256(data).hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
s=read('validation-summary.json');code=s['code_head']
expected={'web/collector_runtime.py','web/collector_queue.py','web/collector_incremental_runtime.py','web/pipeline/tests/test_collector_publish_environment.py','web/pipeline/tests/test_runtime_source_parity_behavior.py','web/pipeline/tests/test_collector_orchestration_behavior.py','web/pipeline/tests/test_collector_deferred_budget.py'}
assert set(git('diff','--name-only',s['starting_head'],code).decode().splitlines())==expected
for name,digest in s['source_sha256'].items():assert sha((ROOT/name).read_bytes())==sha(git('show',f'{code}:{name}'))==digest,name
added=0
for name in expected:
 if '/tests/' not in name:continue
 def names(t):return {n.name for n in ast.walk(t) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
 before=names(ast.parse(git('show',f"{s['starting_head']}:{name}").decode()));after=names(ast.parse((ROOT/name).read_text()));assert before<=after;added+=len(after-before)
assert added==s['new_behavior_tests']==24
p=read('input-integrity.json');assert len(p['files'])==p['protected_file_count']==503
base=set(git('ls-tree','-r','--name-only',s['starting_head'],'--','web/pipeline/data','web/pipeline/tests/fixtures','docs/project/validation').decode().splitlines());assert base==set(p['files'])
for name,digest in p['files'].items():assert sha((ROOT/name).read_bytes())==sha(git('show',f"{s['starting_head']}:{name}"))==digest,name
for name,digest in read('unchanged-boundaries.json').items():assert sha((ROOT/name).read_bytes())==sha(git('show',f"{s['starting_head']}:{name}"))==digest,name
for r in read('source-references.json'):
 data=(ROOT/r['path']).read_bytes();assert sha(data)==r['sha256'] and data.decode().splitlines()[r['line']-1]==r['text']
rows=read('publisher-cases.json');assert len(rows)==21
assert all(c['pending_unchanged'] and c['health_unchanged'] for c in rows)
for c in rows:
 mode,receipt=c['mode'],c['receipt']
 if mode in {'expired','read_late','merge_late','build_late','health_late','digest_late','latest_set_late','latest_read_late','missing'}:
  assert c['requests']==0 and receipt['publication_outcome']=='NOT_ATTEMPTED' and not c['published_written'],mode
 if mode in {'ack_late_work','ack_late_total','copy_set_late','copy_read_late','copy_error','node_retry','node_unknown','stage_error'}:assert receipt['publication_outcome']=='CONFIRMED',mode
 if mode=='ack_late_total':assert receipt['python_cache_status']=='SKIPPED_BUDGET'
 if mode=='bad_ack':assert receipt['latest_candidate_mutation_possible'] and receipt['publication_outcome']=='UNKNOWN'
 if c['requests']:assert c['wire_matches_latest'],mode
put=read('put-cases.json');assert len(put)==17
assert all(c['requests']<=1 for c in put)
assert any(c['parent_work']==180 and c['timeouts']==[14] and c['parent_origin']==0 for c in put)
queue=read('queue-tail-cases.json');assert len(queue)==6
for c in queue:
 if c['error_type']:assert c['diagnostics']['publish_receipt']['publication_outcome']=='CONFIRMED'
assert next(c for c in queue if c['mode']=='overrun_success')['events']==['heartbeat','reconcile','tick','release']
assert next(c for c in queue if c['mode']=='replaced')['events']==['heartbeat']
assert read('frozen-template-audit.json')['passed']==10 and read('original-cli-gate.json')['passed']==3
log=(HERE/'regression.log').read_text();assert 'Ran 1145 tests' in log and log.rstrip().endswith('OK')
assert s['deep_total_work_reserve']==[270,210,60] and s['parent_source_unchanged']==[270,180,30,60]
for name in ['node_sql_version_cli_budget_or_js_gate_changed','hard_cancellation_guaranteed','atomic_commit_guaranteed','durable_crash_receipt_guaranteed','real_persistence_verified','apply_allowed','migration_usable']:assert s[name] is False,name
assert read('completion.json')['within_foreground_budget']
for name,digest in read('manifest.json')['sha256'].items():assert sha((ROOT/name).read_bytes())==digest,name
print('PASS: 7 authorized files; 24 new tests; 1145/10/3; 21 publisher/17 PUT/6 tail cases; 503 protected inputs; unchanged Node/SQL/JS/CliBudget; manifest; offline scope')
