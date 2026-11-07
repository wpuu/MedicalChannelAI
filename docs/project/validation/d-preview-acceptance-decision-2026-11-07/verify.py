"""Static decision-package verification; never imports reviewed code or SDK."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent

def read(name):return json.loads((HERE/name).read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def literal(path,name):
 tree=ast.parse((ROOT/path).read_bytes())
 n=next(n for n in tree.body if (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)) or (isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id==name))
 return ast.literal_eval(n.value)

s=read('validation-summary.json');release=read('release-source.json');base=s['starting_head']
assert base.startswith('b710804') and s['unchanged_application_code_sha'].startswith('3f88ff7')
assert git('rev-parse',base+':web')==git('rev-parse',release['application_code_sha']+':web')
assert not git('diff','--name-only',base,'--','web','.github').strip()
assert not git('diff','--name-only',release['historical_deployed_source_sha'],release['application_code_sha'],'--','web/pipeline/data','web/public').strip()
assert len(release['changed_web_and_workflow_paths_from_historical_source'])==23
for row in read('source-references.json'):
 path=ROOT/row['path']
 assert sha(path)==row['file_sha256']
 assert path.read_text().splitlines()[row['line']-1]==row['text']
assert len(read('source-references.json'))==101
protected=read('input-integrity.json');assert protected['protected_file_count']==len(protected['files'])==629
for path,digest in protected['files'].items():assert sha(ROOT/path)==digest,path
assert len(read('source-config-git-objects.json')['files'])==455
assert sha(ROOT/release['historical_gate_summary'])==release['historical_gate_summary_sha256']
historical=json.loads((ROOT/release['historical_gate_summary']).read_text())
assert [historical[k] for k in ['python_tests_passed','frozen_template_passed','original_cli_passed']]==[1213,10,3]
assert s['gates_reexecuted'] is False and s['application_sdk_model_tests_or_build_executed'] is False
assert len(literal('web/collector_runtime.py','STAGE_ORDER'))==25
assert literal('web/collector_incremental_ticks.py','MAX_TICKS_PER_DAY')==31
assert literal('web/pipeline/scripts/sync_tjzyefy_market_research.py','FETCH_ATTEMPTS')==2
policy=literal('web/collector_incremental.py','SOURCE_POLICIES')
assert policy['tjzyefy']['max_details_per_scan']==12
plan=json.loads((ROOT/'web/pipeline/data/tianjin_query_plan.json').read_text())
cost=read('scope-and-cost.json')
assert len(plan['keywords'])*len(plan['notice_types'])==cost['ccgp_search_helper_calls_per_execution_upper']==10
assert plan['max_candidates']==cost['ccgp_selected_detail_helper_calls_upper']==12
assert (1+12)*2==cost['tjzyefy_nominal_attempt_slots_per_delivery']==26
assert 26*3==cost['tjzyefy_nominal_attempt_slots_if_three_deliveries']==78
assert 300*3+150*2==cost['nominal_three_deliveries_and_retry_seconds']==1200
assert cost['event_detail_candidate_count_cap'] is None and cost['complete_ccgp_wire_request_upper_verified'] is False
# AST confirms side-effect calls without executing handlers or SDK.
def function(path,name):
 return next(n for n in ast.walk(ast.parse((ROOT/path).read_bytes())) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
def calls(node):return {n.func.id for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
assert 'cache_roundtrip' in calls(function('web/api/pipeline-health.py','do_GET'))
assert 'ensure_intraday_chain' in calls(function('web/api/collector-run.py','_enqueue_start'))
assert '_enqueue_stage' in calls(function('web/collector_queue.py','process_collector_payload'))
assert '_enqueue_incremental_tick' in calls(function('web/collector_queue.py','_process_incremental_tick_payload'))
config=json.loads((ROOT/'web/vercel.json').read_text())
assert config['git']['deploymentEnabled']['codex/p0-reliability-contracts'] is False
assert config['functions']['api/collector-queue.py']['maxDuration']==300
assert config['functions']['api/collector-queue.py']['experimentalTriggers'][0]['maxDeliveries']==3
assert config['functions']['api/collector-queue.py']['experimentalTriggers'][0]['retryAfterSeconds']==150
package=json.loads((ROOT/'web/package.json').read_text())
assert 'run-prebuild' in package['scripts']['build']
d=read('decision.json');gates=read('go-no-go.json')
assert len(gates)==8 and all(g['status'].startswith('NO_GO') for g in gates[1:])
assert not any(d['current_authorized_counts'].values())
assert d['future_caps_enforceable_for_full_ccgp_chain'] is False
assert d['no_auto_followup_rounds'] is True
assert d['sdk_and_strong_guarantee_branches']=='CLOSED_NO_GO'
assert d['apply_allowed'] is False and d['migration_usable'] is False
cp=json.loads((ROOT/'docs/project/checkpoint.json').read_text())
assert cp['latest_code_validated_head']==release['application_code_sha']
assert cp['d_preview_acceptance_decision']['status']=='NO_GO_PAUSED_NO_AUTOMATIC_FOLLOWUP_ROUNDS'
assert not cp['current_authorization_scope']['network_this_round']
assert '无新证据时仅简短说明暂停，不改文件' in (ROOT/'docs/project/next-task.md').read_text()
for path,digest in read('manifest.json')['files'].items():assert sha(ROOT/path)==digest,path
assert read('completion.json')['within_frontend_20_minutes'] is True
changed=set(git('diff','--name-only',base).decode().splitlines())|set(git('ls-files','--others','--exclude-standard').decode().splitlines())
allowed={'docs/project/checkpoint.json','docs/project/current-state.md','docs/project/next-task.md','docs/project/d-preview-acceptance-decision-2026-11-07.md'}
assert all(p in allowed or p.startswith('docs/project/validation/d-preview-acceptance-decision-2026-11-07/') for p in changed)
print(json.dumps({'static_verification':'PASS','source_references':101,'protected_inputs':629,'unchanged_web_workflow_files':455,'historical_source_delta_paths':23,'go_no_go_gates':8,'decision':'NO_GO_PAUSED','tests_or_build_run':False,'cloud_access':False,'apply_allowed':False,'migration_usable':False}))
