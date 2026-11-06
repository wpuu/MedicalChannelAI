"""Replay existing unittest helpers/assertions only; synthetic local transports."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'web/pipeline'))
def offline(event, args):
    if event == 'import' and (args[0] == 'vercel' or args[0].startswith('vercel.')):
        raise ImportError('REAL_SDK_FORBIDDEN')
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise RuntimeError('NETWORK_FORBIDDEN')
sys.addaudithook(offline)
from tests.test_collector_deferred_budget import CollectorDeferredBudgetTests
from tests.test_collector_orchestration_behavior import CollectorOrchestrationBehaviorTests

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

modes = ['expired', 'index_late', 'sleep_admission', 'sleep_late', 'detail_late', 'nonfact_late',
         'staging_late', 'barrier_late', 'ledger_late', 'admit_URL_STAGING', 'admit_URL_BARRIER',
         'admit_URL_LEDGER', 'staging_error_before', 'staging_error_after', 'barrier_error_after',
         'ledger_error_after', 'failure_ledger_error', 'success', 'empty', 'nonfact', 'ordinary_error',
         'finalize_late', 'pre_canonical_late', 'canonical_error_before', 'canonical_error_after',
         'canonical_late', 'health_late', 'publish_admission', 'publish_late', 'publish_error',
         'bucket_late', 'bucket_error_after', 'health_error_before', 'hard_stop', 'periodic_defer',
         'old_pending_empty', 'staging_error_then_deadline', 'staging_recovery_error']
rows = []
for mode, count in [(m, 2) for m in modes] + [('success', 12), ('success', 13)]:
    case = CollectorDeferredBudgetTests('test_incremental_budget_rejects_before_or_after_discovery')
    case.setUp()
    try:
        c = case.incremental_budget_case(mode, count=count)
        rows.append({'mode': mode, 'candidate_count': count, 'status': c['status'], 'exception': c['exception'],
            'canonical_before_sha256': digest(c['baseline']), 'canonical_after_sha256': digest(c['canonical']),
            'canonical_unchanged': c['baseline'] == c['canonical'], 'staged_record_count': len(c['staged']),
            'barrier_count': len(c['barrier']), 'ledger_statuses': sorted(r['verification_status'] for r in c['ledger']['entries'].values()),
            'bucket_written': c['bucket'] is not None, 'last_success_unchanged': c['health']['last_successful_scan_at'] == c['prior'],
            'other_source_pending_unchanged': c['other_pending'] == ['unresolved-other-source'],
            'detail_calls': sum(x not in {'index', 'publish'} for x in c['called']),
            'index_calls': c['called'].count('index'), 'publish_calls': c['called'].count('publish'),
            'elapsed_seconds': c['tick'], 'result': c['result']})
    finally:
        case.doCleanups()
(HERE / 'source-cases.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
queue = []
for method in ['test_tjzyefy_budget_keeps_entry_origin_through_lease_and_ignores_payload_deadline',
               'test_tjzyefy_guards_and_owner_denial_never_enter_runner',
               'test_other_incremental_sources_keep_original_dispatch_without_budget',
               'test_tjzyefy_lease_release_failure_preserves_known_scan_result',
               'test_tjzyefy_lease_acquire_io_error_is_unknown_and_never_runs_source',
               'test_incremental_dispatch_does_not_get_regional_budget']:
    case = CollectorOrchestrationBehaviorTests(method)
    case.setUp()
    try:
        getattr(case, method)()
        queue.append({'method': method, 'assertions_passed': True})
    finally:
        case.doCleanups()
(HERE / 'queue-cases.json').write_text(json.dumps(queue, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'synthetic_source_cases': len(rows), 'existing_queue_assertion_cases': len(queue),
                  'external_network_calls': 0, 'real_sdk_execution': False}))
