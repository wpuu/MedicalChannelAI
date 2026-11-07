"""Reuse existing unittest fixtures/helpers only; synthetic local cache and HTTP."""
import json
import hashlib
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'web/pipeline'))
def offline(event,args):
    if event=='import' and (args[0]=='vercel' or args[0].startswith('vercel.')):raise ImportError('REAL_SDK_FORBIDDEN')
    if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('NETWORK_FORBIDDEN')
sys.addaudithook(offline)
from tests.test_runtime_source_parity_behavior import RuntimeSourceParityBehaviorTests
from tests.test_collector_publish_environment import CollectorPublishEnvironmentTests
from tests.test_collector_orchestration_behavior import CollectorOrchestrationBehaviorTests

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
source=[]
modes=['success','expired','read_late','merge_late','build_late','health_late','digest_late','latest_set_late','latest_read_late','ack_late_work','ack_late_total','copy_set_late','copy_read_late','copy_error','node_retry','node_unknown','missing','committed_pair','stage_error','failure_state_error']
for mode,budget in [(m,True) for m in modes]+[('bad_ack',False)]:
    case=RuntimeSourceParityBehaviorTests('test_publish_budget_each_work_boundary_refuses_new_put');case.setUp()
    try:
        c=case.publisher_budget_case(mode,use_budget=budget)
        source.append({'mode':mode,'uses_budget':budget,'error':c['error'],'receipt':c['receipt'],'diagnostics':c['diagnostics'],
            'result':c['result'],'requests':len(c['calls']),'read_count':len(c['reads']),'copy_reads':len(c['copy_reads']),
            'latest_written':c['latest'] is not None,'published_written':c['published'] is not None,
            'pending_unchanged':c['pending']==['unresolved-source'],'health_unchanged':c['health'] is None,
            'latest_sha256':digest(c['latest']),'published_sha256':digest(c['published']),
            'wire_matches_latest':json.loads(c['calls'][0][0].data)==c['latest'] if c['calls'] else None})
    finally:case.doCleanups()
(HERE/'publisher-cases.json').write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n')
put=[]
configs=[('success',{}),('success',{'elapsed':210}),('success',{'elapsed':209}),('serialize_late',{}),('late_work',{}),('late_total',{}),('transport_error',{}),('http_error',{}),('bad_json',{}),('missing_commit',{}),('success',{'elapsed':195,'parent_work':180})]
configs += [('success',{'changes':v}) for v in [{'durable_committed':False},{'durable_committed':1},{'ok':1},{'snapshot_as_of':'wrong'},{'opportunity_pool_count':False},{'cache_status':{'invalid':1}}]]
for mode,kwargs in configs:
    case=CollectorPublishEnvironmentTests('test_publish_budget_ack_requires_strict_existing_fields');case.setUp()
    try:
        c=case.budget_put_case(mode,**kwargs)
        put.append({'mode':mode,'case':kwargs,'error':c['error'],'receipt':c['receipt'],'requests':len(c['calls']),
                    'timeouts':[x[1]['timeout'] for x in c['calls']],'parent_work':c['budget'].work_seconds,'parent_origin':c['budget'].started})
    finally:case.doCleanups()
(HERE/'put-cases.json').write_text(json.dumps(put,ensure_ascii=False,indent=2)+'\n')
queue=[]
for mode in ['heartbeat','reconcile','tick','release',None,'replaced']:
    case=CollectorOrchestrationBehaviorTests('test_publish_confirmed_overrun_does_not_add_budget_abort_to_tail');case.setUp()
    try:
        events,error=case.publish_tail_case(None if mode=='replaced' else mode,replaced=mode=='replaced')
        queue.append({'mode':mode or 'overrun_success','events':events,'error_type':type(error).__name__ if error else None,
                      'diagnostics':getattr(error,'diagnostics',{}) if error else {}})
    finally:case.doCleanups()
(HERE/'queue-tail-cases.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'publisher_cases':len(source),'put_cases':len(put),'queue_tail_cases':len(queue),'external_network_calls':0,'real_sdk_execution':False}))
