import json
from urllib.parse import urlsplit
from tests.test_runtime_source_parity_behavior import RuntimeSourceParityBehaviorTests
from tests.test_ccgp_events import CcgpEventTests
rows=[]
configs=[]
for stage in ('ccgp','event1','event6'):
 for where in ('search','detail'):
  for code in (401,403,429):configs.append(dict(stage=stage,where=where,code=code))
  for mode in ('wrapped','marker','timeout','network','503','late','error_late'):
   configs.append(dict(stage=stage,where=where,mode=mode))
 for mode in ('parse','success','empty'):configs.append(dict(stage=stage,mode=mode))
 configs.extend([dict(stage=stage,mixed_hosts=True),dict(stage=stage,retry=True),dict(stage=stage,use_budget=False)])
for options in configs:
 c=RuntimeSourceParityBehaviorTests();c.setUp()
 try:
  value=c.ccgp_access_case(**options)
  rows.append({'config':options,'status':value['status'],'action':value['result'].get('action'),
    'calls':[{'kind':kind,'host':urlsplit(url).hostname,'timeout':timeout} for kind,url,timeout in value['calls']],
    'parse_hosts':[urlsplit(url).hostname for url in value['parses']],
    'retry_request_count':len(value['retry_calls']),
    'diagnostics':value['row'].get('diagnostics'),
    'committed_unchanged':value['committed_unchanged'],'staging_unchanged':value['staging_unchanged'],
    'watch_unchanged':value['watch_unchanged'],'pending_unchanged':value['pending_unchanged'],
    'success_clock_unchanged':value['success_clock_unchanged']})
 finally:c.doCleanups()
helpers=[]
for mode in ('search_denied','detail_denied','detail_wrapped','detail_marker','ordinary_parse_error'):
 for guard in (True,False):
  c=CcgpEventTests();value=c.event_budget_scan_case(mode,use_guard=guard)
  helpers.append({'mode':mode,'guard':guard,'events':len(value['events']) if value['events'] is not None else None,
     'error':str(value['error']) if value['error'] else None,'calls':value['calls'],'blocked_hosts':value['blocked_hosts']})
print(json.dumps({'mode':'REPLAY_OF_EXISTING_UNITTEST_HELPERS_LOCAL_SYNTHETIC_TRANSPORT_ONLY','source_cases':rows,'helper_cases':helpers,'apply_allowed':False,'migration_usable':False},ensure_ascii=False,indent=2))
