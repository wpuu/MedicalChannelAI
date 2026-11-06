from copy import deepcopy
from dataclasses import replace
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import collector_readonly_export as core
import collector_readonly_guard as guard
import test_collector_readonly_export as existing
from collector_epoch import epoch_key

SCOPE = dict(core._D_SCOPE)
KEYS = tuple(epoch_key(key,SCOPE['preview_epoch']) for key in core._plan())


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, amount):
        self.now += amount


class LocalTransport:
    input_kind = 'SYNTHETIC_LOCAL_STUB'

    def __init__(self, values=None, hook=None):
        self.target_scope = dict(SCOPE)
        self.values = deepcopy(values or {})
        self.calls = []
        self.hook = hook

    def get(self,key,*,timeout_seconds):
        self.calls.append({'key':key,'timeout_seconds':timeout_seconds})
        if self.hook:
            self.hook(self,key,timeout_seconds)
        return self.values.get(key)


class ReadonlyGuardTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.transport = LocalTransport()

    def facade(self,**kw):
        return guard.SyntheticGetOnlyGuard(self.transport,scope=kw.get('scope',SCOPE),
            expected_scope=kw.get('expected_scope',SCOPE),monotonic=kw.get('monotonic',self.clock))

    def observe(self,**kw):
        return guard.observe_synthetic_d_canonical(self.transport,scope=kw.pop('scope',SCOPE),
            expected_scope=kw.pop('expected_scope',SCOPE),monotonic=self.clock,**kw)

    def test_normal_exact_forwarding_and_unchanged_kernel_envelope(self):
        baseline=existing.ReadOnlyExportTests().normal()
        self.transport=LocalTransport(baseline.values); before=deepcopy(self.transport.values)
        expected=core.observe_d_canonical(baseline,scope=SCOPE,expected_scope=SCOPE)
        actual=self.observe()
        self.assertEqual(actual,expected)
        self.assertEqual(self.transport.values,before)
        self.assertEqual([row['key'] for row in self.transport.calls],list(KEYS)*2)
        self.assertTrue(all(row['timeout_seconds']==2.0 for row in self.transport.calls))
        self.assertEqual(actual['input_kind'],'OFFLINE_READONLY_CACHE_OBSERVATION')
        for field in ('scope_provenance_verified','apply_allowed','migration_usable','atomic_snapshot_guaranteed'):
            self.assertFalse(actual[field])

    def test_uninitialized_and_explicit_empty_never_backfilled(self):
        result=self.observe()
        self.assertTrue(all(row['value'] is None for row in result['shards'].values()))
        self.transport=LocalTransport({KEYS[0]:[]})
        self.assertEqual(self.observe()['shards'][next(iter(core._plan()))]['state'],'PRESENT_EMPTY')
        self.assertTrue(all('snapshot' not in row['key'] for row in self.transport.calls))

    def test_missing_and_cross_scope_reject_before_reads(self):
        for field in SCOPE:
            for value in (None,'production','mcai-p0-20261106-c','other'):
                scope=dict(SCOPE)
                if value is None: scope.pop(field)
                else: scope[field]=value
                for arg in ('scope','expected_scope'):
                    with self.assertRaisesRegex(core.ExportRejected,'EXPORT_SCOPE_REJECTED'):
                        self.observe(**{arg:scope})
                    self.assertEqual(self.transport.calls,[])

    def test_transport_scope_mismatch_rejects_before_reads(self):
        for field in SCOPE:
            self.transport.target_scope=dict(SCOPE); self.transport.target_scope[field]='other'
            with self.assertRaisesRegex(core.ExportRejected,'GUARD_TRANSPORT_SCOPE_REJECTED'):
                self.observe()
            self.assertEqual(self.transport.calls,[])

    def test_requires_explicit_local_marker_not_real_backend_mode(self):
        for value in (None,'REAL_RUNTIME','preview',False):
            self.transport.input_kind=value
            with self.assertRaisesRegex(core.ExportRejected,'GUARD_LOCAL_STUB_REQUIRED'):
                self.observe()
            self.assertEqual(self.transport.calls,[])

    def test_illegal_double_prefix_old_epoch_production_and_snapshot_keys_zero_reads(self):
        for key in ('arbitrary',epoch_key(KEYS[0],SCOPE['preview_epoch']),
                    KEYS[0].replace('20261106-d','20261106-c'),
                    KEYS[0].replace(':preview:',':production:'),
                    'medicalchannelai:collector-ccgp-records:v2',
                    epoch_key('medicalchannelai:verified-snapshot:published:v2',SCOPE['preview_epoch']),None):
            facade=self.facade()
            with self.assertRaisesRegex(core.ExportRejected,'GUARD_KEY_REJECTED'): facade.get(key)
            self.assertEqual(self.transport.calls,[])

    def test_allowed_keys_wrong_order_rejected_before_read(self):
        facade=self.facade()
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_KEY_ORDER_REJECTED'): facade.get(KEYS[1])
        self.assertEqual(self.transport.calls,[])

    def test_117th_call_rejected_and_never_forwarded(self):
        facade=self.facade()
        for key in KEYS*2: facade.get(key)
        self.assertEqual(facade.call_count,116)
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_CALL_LIMIT'): facade.get(KEYS[0])
        self.assertEqual(len(self.transport.calls),116)
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_FAILED'): facade.finish()

    def test_read_or_total_deadline_before_first_get_zero_reads(self):
        for elapsed,code in ((110,'GUARD_READ_DEADLINE'),(120,'GUARD_TOTAL_DEADLINE')):
            self.clock=FakeClock(); facade=self.facade(); self.clock.advance(elapsed)
            with self.assertRaisesRegex(core.ExportRejected,code): facade.get(KEYS[0])
            self.assertEqual(self.transport.calls,[])

    def test_preflight_time_counts_toward_deadline(self):
        values=iter([0.0,110.0])
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_READ_DEADLINE'):
            guard.observe_synthetic_d_canonical(self.transport,scope=SCOPE,expected_scope=SCOPE,
                                                monotonic=lambda:next(values))
        self.assertEqual(self.transport.calls,[])

    def test_remaining_read_window_bounds_transport_timeout(self):
        facade=self.facade(); self.clock.advance(109.25)
        facade.get(KEYS[0])
        self.assertEqual(self.transport.calls[0]['timeout_seconds'],0.75)
        self.clock.advance(0.75)
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_READ_DEADLINE'): facade.get(KEYS[1])
        self.assertEqual(len(self.transport.calls),1)

    def test_per_call_late_return_rejected_whole_run(self):
        self.transport.hook=lambda *a:self.clock.advance(2.0)
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_GET_DEADLINE'): self.observe()
        self.assertEqual(len(self.transport.calls),1)

    def test_return_at_read_deadline_rejected(self):
        facade=self.facade(); self.clock.advance(109.5)
        self.transport.hook=lambda *a:self.clock.advance(0.5)
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_READ_DEADLINE'): facade.get(KEYS[0])
        self.assertEqual(self.transport.calls[0]['timeout_seconds'],0.5)

    def test_total_deadline_after_kernel_processing_rejects_delivery(self):
        original=core._validate_values
        def processing(*args):
            original(*args); self.clock.advance(120.0)
        with patch.object(core,'_validate_values',side_effect=processing):
            with self.assertRaisesRegex(core.ExportRejected,'GUARD_TOTAL_DEADLINE'): self.observe()
        self.assertEqual(len(self.transport.calls),116)

    def test_processing_reserve_can_succeed_after_read_window(self):
        original=core._validate_values
        def processing(*args):
            original(*args); self.clock.advance(119.5)
        with patch.object(core,'_validate_values',side_effect=processing):
            self.assertTrue(self.observe()['read_plan_complete'])

    def test_partial_failure_has_one_attempt_no_retry_and_latches(self):
        def fail(*args): raise OSError('SECRET_DETAILS_MUST_NOT_LEAK')
        self.transport.hook=fail; facade=self.facade()
        with self.assertRaisesRegex(core.ExportRejected,'^GUARD_TRANSPORT_FAILED$'): facade.get(KEYS[0])
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_FAILED'): facade.get(KEYS[0])
        self.assertEqual(len(self.transport.calls),1)

    def test_scope_or_marker_change_during_get_rejects_return(self):
        for field,value in (('input_kind','REAL_RUNTIME'),('target_scope',{'target':'production'})):
            self.transport=LocalTransport(hook=lambda t,k,s:setattr(t,field,value))
            with self.assertRaises(core.ExportRejected): self.observe()
            self.assertEqual(len(self.transport.calls),1)

    def test_scope_change_before_next_get_zero_additional_calls(self):
        facade=self.facade(); facade.get(KEYS[0]); self.transport.target_scope['target']='production'
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_TRANSPORT_SCOPE_REJECTED'): facade.get(KEYS[1])
        self.assertEqual(len(self.transport.calls),1)

    def test_write_capabilities_refused_without_write_or_read_calls(self):
        for method in ('set','delete','expire','expire_tag','expireTag','clear'):
            self.transport=LocalTransport(); setattr(self.transport,method,lambda *a:self.fail('WRITE_FORBIDDEN'))
            with self.assertRaisesRegex(core.ExportRejected,'EXPORT_GET_ONLY_REQUIRED'): self.observe()
            self.assertEqual(self.transport.calls,[])

    def test_failed_key_cannot_be_caught_and_then_completed(self):
        facade=self.facade()
        with self.assertRaises(core.ExportRejected): facade.get('bad')
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_FAILED'): facade.get(KEYS[0])
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_FAILED'): facade.finish()
        self.assertEqual(self.transport.calls,[])

    def test_finish_rejects_partial_plan_and_closes_successful_plan(self):
        facade=self.facade(); facade.get(KEYS[0])
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_INCOMPLETE_READ_PLAN'): facade.finish()
        self.transport=LocalTransport(); facade=self.facade()
        for key in KEYS*2: facade.get(key)
        facade.finish()
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_CLOSED'): facade.get(KEYS[0])

    def test_invalid_and_regressing_clocks_fail_closed(self):
        for value in (None,True,float('nan'),float('inf'),1e308):
            with self.assertRaisesRegex(core.ExportRejected,'GUARD_CLOCK_INVALID'):
                self.facade(monotonic=lambda:value)
        facade=self.facade(); self.clock.now=-1
        with self.assertRaisesRegex(core.ExportRejected,'GUARD_CLOCK_INVALID'): facade.get(KEYS[0])
        self.assertEqual(self.transport.calls,[])

    def test_existing_size_and_owner_rejections_propagate_without_partial_result(self):
        self.transport=LocalTransport({KEYS[0]:[]})
        with self.assertRaisesRegex(core.ExportRejected,'EXPORT_VALUE_SIZE_LIMIT'):
            self.observe(limits=replace(core.ExportLimits(),max_value_bytes=1))
        self.transport=LocalTransport()
        def change(t,key,timeout):
            if len(t.calls)>58:t.values[key]={}
        self.transport.hook=change
        with self.assertRaisesRegex(core.ExportRejected,'EXPORT_VERSION_OR_OWNER_CHANGED'): self.observe()

    def test_import_and_run_without_cache_sdk_network_or_sleep(self):
        with patch('collector_epoch.RuntimeCache',side_effect=AssertionError('CLIENT_FORBIDDEN')), \
             patch('socket.create_connection',side_effect=AssertionError('NETWORK_FORBIDDEN')), \
             patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_FORBIDDEN')), \
             patch('time.sleep',side_effect=AssertionError('SLEEP_FORBIDDEN')):
            importlib.reload(guard)
            self.assertTrue(self.observe()['read_plan_complete'])


if __name__=='__main__':
    unittest.main()
