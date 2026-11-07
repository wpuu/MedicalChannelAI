"""Offline source/AST/hash audit only; no app, SDK, model or tests are executed."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = '1f40e91'
CODE = 'fea6fc70350b17366f20a86eac9ec02396a36fa9'

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def write(name, data):
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def tree(path, ref=None):
    return ast.parse(git('show', f'{ref}:{path}') if ref else (ROOT / path).read_bytes())

def function(path, name, ref=None):
    return next(n for n in tree(path, ref).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)

def literal(path, name):
    node = next(n for n in tree(path).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return ast.literal_eval(node.value)

runtime, queue, query = 'web/collector_runtime.py', 'web/collector_queue.py', 'web/pipeline/scripts/sync_ccgp_query.py'
regional = 'web/pipeline/scripts/sync_regional_ccgp.py'
inc = 'web/collector_incremental_runtime.py'
anchors = {
 runtime: ['STAGE_ORDER = (','def _assert_pending_canonical_commit','def _cached_list','def _prepare_stage','def _mark_failed','def _run_ccgp','def prepare(target','observed_digest = _digest(observed)','committed = cache.get(CCGP_COMMITTED_STATE_KEY)','for keyword_index, keyword','for notice_type, candidate in selected:',"check('CCGP_DETAIL_ERROR_RETURN')",'diagnostic = ";".join','if failures:',"if budget and len(discovered) > plan['max_candidates']:","watch_cap = min(","prepare_deadline = min(budget.clock() + 60",'def _run_event_batch','for project_number in projects:', 'if len(project_search_failures) >= 2:', 'CCGP_SOURCE_TRANSACTION_INCOMPLETE','raw_records = cache.get(CCGP_RECORDS_KEY)','receipt.update(write_attempted=True','def _run_regional_market','blocked_hosts: dict[str, str] = {}','detail_host = urlsplit(candidate.detail_url).hostname','reason = access_block_reason','def _publish_work_deadline','def _persist_verified_snapshot_durably','if result.get("durable_committed") is not True:', 'receipt.update(publication_outcome="CONFIRMED"','def _run_publish','missing_canonical = [','LATEST_RUNTIME_SNAPSHOT_KEY,','if receipt["node_cache_status"] != "UPDATED":','def run_stage','if previous is not None:','if not ccgp_budget and not event_budget','CCGP_FAILURE_STATE_RESULT_UNKNOWN','CCGP_FINALIZATION_RESULT_UNKNOWN','EVENT_VERIFICATION_PENDING','if all((latest_stages.get(required)'],
 queue: ['def _process_incremental_payload','async def process_collector_payload','entered_at = clock()','if not accepts_payload(payload):','if str(payload.get("source_id")','if ccgp_stage:','work_seconds=150','work_seconds=180','work_seconds=210','COLLECTOR_DEPENDENCY_DEGRADED','if not _heartbeat_deep_cycle(cycle_id','reconcile_incremental_pending_from_canonical','runtime.mark_stage_degraded(stage','if ccgp_stage:',"'ccgp_prepare_receipt':",'if event_stage:'],
 query: ['def scan_events','from sync_regional_ccgp import CliBudgetExceeded','for notice_type, event_type','except Exception as exc:  # explicit report','if candidate.published_at:','def discover_candidates','for index, notice_type','except Exception as exc:',"check('CCGP_SEARCH_ERROR_RETURN')"],
 regional: ['class CliBudget:','def access_block_reason','def finish_cli_outputs','def main(*, monotonic','on_access_blocked=blocked_hosts.setdefault','if detail_host in blocked_hosts:','acceptance_ready = not acceptance_blockers'],
 inc: ['SUPPORTED_INCREMENTAL_SOURCES = (','def _publish_snapshot_if_ready','def run_incremental_source','if str(source_id or','save_deadline = min(budget.clock() + 30','_save_pending_records(cache, source, durable_staging)','scan_barrier.discard','if pending_barrier:', 'return 200, {"action": "COMPLETED", **result}', 'if budget.started + budget.total_seconds - budget.clock() < 31:'],
 'web/pipeline/medical_channel_pipeline/ccgp_discovery.py': ['def parse_search_html','if any(marker in html for marker in RATE_LIMIT_MARKERS):','def fetch_search_page'],
 'web/pipeline/medical_channel_pipeline/ccgp_detail.py': ['def fetch_ccgp_detail_html','raise RuntimeError(f"CCGP_DETAIL_HTTP_'],
 'web/collector_diagnostics.py': ['def failure_row','def reported_event_failure_row','def failure_summary'],
 'web/api/public-snapshot.js': ['const committed = await persistSnapshot(snapshot)',"cacheStatus = 'RETRY_REQUIRED'",'durable_committed: true'],
 'web/api/_snapshotRevision.js': ['export function snapshotRevisionMicros'],
 '.github/workflows/regional-medical-refresh.yml': ["- 'web/pipeline/tests/test_regional_cli_completeness.py'",'set -euo pipefail','tests.test_regional_cli_completeness'],
 'web/pipeline/tests/test_runtime_source_parity_behavior.py': ['def test_ccgp_budget_missing_or_mismatched_readback_never_advances','def test_ccgp_budget_each_key_write_before_after_or_late_preserves_truth','def test_ccgp_budget_committed_priority_and_corrupt_bundle_do_not_use_raw_fallback','def test_ccgp_event_failure_cannot_be_masked_by_later_batch_success','def test_nonempty_event_failure_persists_only_safe_diagnostics_and_keeps_committed_bundle'],
 'web/pipeline/tests/test_collector_orchestration_behavior.py': ['def test_ccgp_budget_failure_retries_then_degrades_and_never_scans_third_time','def test_event_budget_first_retry_final_degrade_and_redelivery_keep_attempt_limit','def test_expired_ownerless_running_is_degraded_and_new_identity_fences_old_messages'],
 'web/pipeline/tests/test_ccgp_events.py': ['def test_event_budget_late_detail_parse_or_none_never_falls_back','def test_event_budget_and_default_ordinary_fallback_remain_compatible','def test_event_budget_does_not_break_query_regional_import_orders'],
}
refs=[]
for path, needles in anchors.items():
    data=(ROOT/path).read_bytes(); lines=data.decode().splitlines()
    for needle in needles:
        matches=[i+1 for i,line in enumerate(lines) if needle in line]
        assert matches, (path,needle)
        refs.append({'path':path,'line':matches[0],'text':lines[matches[0]-1], 'anchor':needle,'file_sha256':sha(data),'reviewed_head':BASE,'code_head':CODE})
write('source-references.json',refs)

origins=[(runtime,'_run_ccgp','fea6fc7'),(runtime,'_run_event_batch','5d2fe85'),(runtime,'_run_regional_market','4916d69'),(runtime,'_run_publish','a352b7a'),(runtime,'_persist_verified_snapshot_durably','a352b7a'),(regional,'main','58e7e6b'),(regional,'CliBudget','bba3716'),(inc,'_run_incremental_source','a352b7a')]
versions=[]
for path,name,origin in origins:
    def node(ref=None):
        return next(n for n in tree(path,ref).body if getattr(n,'name',None)==name)
    old,new=ast.dump(node(origin),include_attributes=False),ast.dump(node(),include_attributes=False)
    assert old==new,(name,origin)
    assert subprocess.run(['git','merge-base','--is-ancestor',origin,BASE],cwd=ROOT).returncode==0
    versions.append({'path':path,'symbol':name,'implementation_origin':origin,'current_ast_sha256':sha(new.encode()),'ast_unchanged_from_origin':True})
write('version-bindings.json',versions)

stages=literal(runtime,'STAGE_ORDER')
regions=set(literal(runtime,'REGIONAL_STAGE_MARKET_CODES'))|set(literal(runtime,'REGIONAL_FALLBACK_STAGE_MARKET_CODES'))
budgeted={'ccgp','publish',*[f'event{i}' for i in range(1,7)]}|regions
incremental=literal(inc,'SUPPORTED_INCREMENTAL_SOURCES')
coverage={'deep_stages':list(stages),'budgeted_queue_deep_stages':[s for s in stages if s in budgeted],'unbudgeted_queue_deep_stages':[s for s in stages if s not in budgeted],'incremental_sources':list(incremental),'budgeted_queue_incremental_sources':['tjzyefy'],'unbudgeted_queue_incremental_sources':[s for s in incremental if s!='tjzyefy'],'cli':[900,840,60],'queue_ccgp':[270,150,60,60],'queue_event':[270,180,30,60],'queue_regional':[270,210,60],'queue_tjzyefy':[270,180,30,60],'publish_work_deadline_parent_offset':210,'all_budgets_cooperative_only':True,'cross_process_cooldown_implemented':False,'retry_after_scheduler_implemented':False,'real_runtime_verification':'UNVERIFIED'}
assert len(stages)==25 and len(budgeted)==18 and len(coverage['unbudgeted_queue_deep_stages'])==7 and len(incremental)==8
write('coverage.json',coverage)

# Prove only source control-flow properties, never claim behavioral reproduction.
checks=[]
for path,name,phase in [(query,'discover_candidates','CCGP_SEARCH_ERROR_RETURN'),(query,'scan_events','EVENT_SEARCH_ERROR_RETURN'),(runtime,'_run_ccgp','CCGP_DETAIL_ERROR_RETURN')]:
    fn=function(path,name)
    handler=next(n for n in ast.walk(fn) if isinstance(n,ast.ExceptHandler) and n.type is not None and isinstance(n.type,ast.Name) and n.type.id=='Exception' and any(isinstance(c,ast.Constant) and c.value==phase for c in ast.walk(n)))
    calls={n.func.id for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    assert not {'access_block_reason','failure_row'} & calls
    if phase!='EVENT_SEARCH_ERROR_RETURN':
        assert not any(isinstance(n,(ast.Raise,ast.Break,ast.Return)) for n in ast.walk(handler))
    else:
        assert isinstance(handler.body[-1],ast.Continue)
    checks.append({'path':path,'symbol':name,'handler_line':handler.lineno,'property':'generic timely exception records failure then permits next iteration','access_block_classifier_called':False,'behavior_reproduced_this_round':False})
write('static-control-flow.json',checks)

history=[]
for phase in ['ccgp-discovery-stage-budget-implementation-2026-11-07','ccgp-event-stage-budget-implementation-2026-11-07','runtime-regional-access-stop-2026-11-07','publish-budget-implementation-2026-11-07','tjzyefy-incremental-implementation-2026-11-07','runtime-f2-implementation-2026-11-07']:
    p=ROOT/'docs/project/validation'/phase/'validation-summary.json';d=json.loads(p.read_text())
    history.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p.read_bytes()),'code_head':d['code_head'],'historical_python_passed':d['python_tests_passed'],'templates':d['frozen_template_passed'],'original_cli':d['original_cli_passed'],'reexecuted_this_round':False})
latest=json.loads((ROOT/history[0]['path']).read_text())
assert latest['python_tests_passed']==1202 and latest['frozen_template_passed']==10 and latest['original_cli_passed']==3
for path,digest in latest['source_sha256'].items(): assert sha((ROOT/path).read_bytes())==digest
write('historical-gates.json',history)

# Record names/object identities without opening env files, credentials or runtime logs.
entries=git('ls-tree','-r',BASE,'--','web','.github').decode().splitlines()
protected_tree={line.split('\t',1)[1]:line.split()[2] for line in entries}
write('source-config-git-objects.json',{'baseline_head':BASE,'files':protected_tree,'environment_values_opened':False})
protected={}
for line in git('ls-tree','-r','--name-only',BASE,'--','web/pipeline/data','web/pipeline/tests/fixtures','docs/project/validation').decode().splitlines():
    p=ROOT/line
    if p.is_file():
        digest=sha(p.read_bytes())
        assert digest==sha(git('show',f'{BASE}:{line}')),line
        protected[line]=digest
write('input-integrity.json',{'baseline_head':BASE,'protected_file_count':len(protected),'files':protected,'log_artifact_content_parsed':False})
write('validation-summary.json',{'starting_head':git('rev-parse',BASE).decode().strip(),'code_head':CODE,'source_references':len(refs),'version_bindings':len(versions),'protected_files':len(protected),'protected_source_config_files':len(protected_tree),'deep_budgeted_total':[18,25],'incremental_budgeted_total':[1,8],'historical_gates':[1202,10,3],'tests_executed_this_round':False,'app_or_sdk_imported':False,'new_simulation_engine':False,'external_network_or_cloud_access':False,'actual_environment_values_or_runtime_logs_read':False,'deployment_push_workflow_trigger':False,'findings_count':3,'unique_next_priority':'R1_CCGP_SINGLE_STAGE_EXPLICIT_DENIAL_STOP_AND_SAFE_DIAGNOSTICS','apply_allowed':False,'migration_usable':False})
print(json.dumps({'static_audit':'PASS','source_references':len(refs),'version_bindings':len(versions),'protected_files':len(protected),'protected_source_config_files':len(protected_tree),'deep_budgeted_total':[18,25],'incremental_budgeted_total':[1,8],'tests_run':False}))
