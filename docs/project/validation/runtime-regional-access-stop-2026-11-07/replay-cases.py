"""Record existing unittest helper observations; no new runtime/simulation engine."""
import json
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from tests.test_runtime_source_parity_behavior import RuntimeSourceParityBehaviorTests
rows=[]
configs=[]
for stage in ('regional_he','regional_he_fallback'):
    for code in (401,403,429):
        configs.append((f'{stage}_HTTP_{code}',dict(stage=stage,error=HTTPError(
            'https://www.ccgp.gov.cn/',code,'OFFLINE',None,None))))
configs.extend([
    ('marker',dict(marker=True)),
    ('warmup_marker',dict(warmup_marker=True)),
    ('warmup_403',dict(warmup_error=HTTPError('https://www.ccgp.gov.cn/',403,'OFFLINE',None,None))),
    ('other_host',dict(error=HTTPError('https://www.ccgp.gov.cn/',429,'OFFLINE',None,None),
                       hosts=('www.ccgp.gov.cn','ccgp.gov.cn','www.ccgp.gov.cn'))),
    ('warmup_other_host',dict(warmup_marker=True,hosts=('www.ccgp.gov.cn','ccgp.gov.cn','www.ccgp.gov.cn'))),
    ('ordinary_timeout',dict(error=TimeoutError('OFFLINE'))),
    ('ordinary_network',dict(error=URLError('OFFLINE'))),
    ('ordinary_503',dict(error=HTTPError('https://www.ccgp.gov.cn/',503,'OFFLINE',None,None))),
    ('ordinary_parse',dict(parse_error=True)),
    ('complete',dict()),('complete_empty',dict(empty=True)),
    ('fallback_complete',dict(stage='regional_he_fallback')),
    ('fallback_empty',dict(stage='regional_he_fallback',empty=True)),
    ('unbudgeted_429',dict(use_budget=False,error=HTTPError('https://www.ccgp.gov.cn/',429,'OFFLINE',None,None))),
])
for label,kwargs in configs:
    case=RuntimeSourceParityBehaviorTests('test_regional_detail_explicit_denial_stops_same_host_after_first_request')
    case.setUp()
    try:
        c=case.regional_access_case(**kwargs)
        rows.append({'case':label,'status':c['status'],'stage_status':c['stage']['status'],
                     'detail_requests':len(c['detail_calls']),
                     'detail_hosts':[urlsplit(url).hostname for url in c['detail_calls']],
                     'parser_calls':len(c['parsed_urls']),'search_calls':c['search_calls'],
                     'canonical_unchanged':c['canonical_unchanged'],'pending_ledger_other_source_unchanged':c['other_unchanged'],
                     'last_success_clock_unchanged':c['health']['last_successful_scan_at']==c['prior'],
                     'diagnostics':c['stage'].get('diagnostics'),
                     'budget_total_work_reserve':[c['budget']['total_seconds'],c['budget']['work_seconds'],c['budget']['finalize_reserve_seconds']]})
    finally:case.doCleanups()
print(json.dumps({'mode':'EXISTING_TEST_HELPER_MEMORY_CACHE_FROZEN_HTML_FAKE_CLOCK','cases':rows,
                  'external_network_calls':0,'real_sdk_execution':False,'apply_allowed':False,'migration_usable':False},ensure_ascii=False,indent=2))
