"""Archive observations from existing unittest helpers only; no new simulator."""
import json
from tests.test_runtime_source_parity_behavior import RuntimeSourceParityBehaviorTests
from tests.test_collector_orchestration_behavior import CollectorOrchestrationBehaviorTests
source=[]
configs=[(m,{}) for m in ('success','admission_late','query_late','query_none_late','query_error_late','partial',
 'detail_late','detail_none_late','detail_error_late','parse_late','merge_late','watch_late','digest_late',
 'cold','cold_late','cold_error','prepare_expired','s_put_before','s_put_after','s_put_late','w_put_before',
 'w_put_after','w_put_late','s_get_error','w_get_error','s_get_late','w_get_late','s_none','w_none',
 's_wrong_cycle','w_old','read_digest_late','stage_error','health_error','failure_save_error','tail_late','replay','watch_capacity')]
configs += [('success',{'count':0}),('success',{'count':12}),('success',{'count':13}),('success',{'use_budget':False}),
 ('committed_precedence',{'count':0}),('corrupt_committed',{'count':0})]
for mode,kwargs in configs:
 c=RuntimeSourceParityBehaviorTests('test_ccgp_budget_complete_empty_twelve_candidates_and_no_budget_keep_boundaries');c.setUp()
 try:source.append({'mode':mode,'config':kwargs,**c.ccgp_stage_budget_case(mode,**kwargs)})
 finally:c.doCleanups()
helper=[]
for mode in ('success','late','none_late','error_late','parse_late','parse_none_late','sort_late','sleep_late','sleep_admission','ordinary_error'):
 c=RuntimeSourceParityBehaviorTests('test_ccgp_discovery_budget_margin_and_timeout_parameters');c.setUp()
 try:helper.append({'mode':mode,**c.ccgp_discovery_budget_case(mode)})
 finally:c.doCleanups()
queue=[]
for mode in ('heartbeat','enqueue','late','replaced'):
 c=CollectorOrchestrationBehaviorTests('test_ccgp_late_tail_runs_original_order_and_replacement_still_fences');c.setUp()
 try:
  events,error=c.ccgp_tail_case(mode)
  queue.append({'mode':mode,'events':events,'error_type':type(error).__name__ if error else None,'diagnostics':getattr(error,'diagnostics',{})})
 finally:c.doCleanups()
print(json.dumps({'source_cases':source,'helper_cases':helper,'queue_cases':queue,'apply_allowed':False,'migration_usable':False},ensure_ascii=False,indent=2))
