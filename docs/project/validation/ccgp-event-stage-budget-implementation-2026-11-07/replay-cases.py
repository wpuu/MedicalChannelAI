"""Reuse existing unittest fixtures/helpers; no separate simulation engine."""
import json
from tests.test_runtime_source_parity_behavior import RuntimeSourceParityBehaviorTests
from tests.test_ccgp_events import CcgpEventTests
from tests.test_collector_orchestration_behavior import CollectorOrchestrationBehaviorTests
source=[]
configs=[(mode,{'stage':stage}) for stage in ('event1','event6') for mode in (
    'success','write_before','write_after','write_late','local_save_late','stage_error','health_error','scan_late','merge_late','partial')]
configs += [(mode,kwargs) for mode,kwargs in [
    ('admission_late',{}),('watch_late',{}),('staging_late',{}),('slow',{}),('none_late',{}),
    ('save_expired',{'stage':'event6'}),('pending_late',{'stage':'event6'}),('raw_late',{'stage':'event6'}),
    ('pending',{'stage':'event6'}),('raw_missing',{'stage':'event6'}),('raw_corrupt',{'stage':'event6'}),
    ('success',{'count':31}),('success',{'count':0}),('success',{'stage':'event6','count':0}),('replay',{})]]
for mode,kwargs in configs:
    c=RuntimeSourceParityBehaviorTests('test_event_stage_five_fast_projects_and_complete_empty_preserve_pair_boundary');c.setUp()
    try:
        row=c.event_stage_budget_case(mode,**kwargs)
        row['verified_sibling_staging_retained']=(row['staging_unchanged'] if row['receipt']['target']=='COMMITTED_PAIR' else row['sibling_preserved'])
        source.append({'mode':mode,'config':kwargs,**row})
    finally:c.doCleanups()
helper=[]
for mode in ('success','search_late','search_none_late','search_error_late','search_parse_late',
             'detail_late','detail_none_late','detail_error_late','parse_late','parse_none_late',
             'sleep_admission','sleep_late','ordinary_parse_error'):
    c=CcgpEventTests('test_event_budget_zero_request_at_deadline_or_margin')
    row=c.event_budget_scan_case(mode)
    helper.append({'mode':mode,'error_phase':getattr(row['error'],'phase',None),'events':len(row['events']) if row['events'] is not None else None,
                   'calls':row['calls'],'failure_count':len(row['failures']),'sleeps':row['sleeps']})
queue=[]
for mode in ('heartbeat','enqueue','late','replaced'):
    c=CollectorOrchestrationBehaviorTests('test_event_queue_lateness_does_not_skip_original_tail_or_fence');c.setUp()
    try:
        events,error=c.event_tail_case(mode)
        queue.append({'mode':mode,'events':events,'error_type':type(error).__name__ if error else None,'diagnostics':getattr(error,'diagnostics',{})})
    finally:c.doCleanups()
print(json.dumps({'source_cases':source,'helper_cases':helper,'queue_cases':queue,
    'apply_allowed':False,'migration_usable':False,'network_or_real_sdk':False},ensure_ascii=False,indent=2))
