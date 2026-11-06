from copy import deepcopy
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import collector_readonly_export as export
import collector_namespace as ns
from collector_epoch import epoch_key

SCOPE = dict(export._D_SCOPE)
physical = lambda key: epoch_key(key, SCOPE['preview_epoch'])


class GetOnly:
    def __init__(self, values=None, hook=None):
        self.values = deepcopy(values or {})
        self.reads = []
        self.hook = hook

    def get(self, key):
        self.reads.append(key)
        if self.hook:
            self.hook(self, key)
        return self.values.get(key)


class ReadOnlyExportTests(unittest.TestCase):
    def observe(self, reader=None, **kw):
        return export.observe_d_canonical(reader or GetOnly(), scope=kw.pop('scope', SCOPE),
                                          expected_scope=kw.pop('expected_scope', SCOPE), **kw)

    def normal(self):
        rows = json.loads((ROOT/'pipeline/data/regional_live_ccgp_records.json').read_text())
        selected = [next(row for row in rows if row['opportunity_id'] == name) for name in (
            'ccgp_he_2a9ca892bf9d0b6a', 'ccgp_jl_806743d8af167ea4')]
        values = {}
        for key, spec in export._plan().items():
            values[physical(key)] = [] if spec['kind'] in ('canonical','events','pending','watch') else None
        for row in selected:
            values[physical('medicalchannelai:collector-regional-records:v3:'+row['facts']['market_code'])] = [row]
        values[physical(ns.SOURCE_HEALTH_KEY)] = {'schema_version':'0.1','sources':{
            'regional_he':{'last_attempt_at':'2026-11-06T10:00:00Z',
                           'last_successful_scan_at':'2026-11-06T09:00:00Z'}}}
        values[physical(ns.ACTIVE_CYCLE_KEY)] = {'cycle_id':'local-test-owner','activated_at':'2026-11-06T09:00:00Z'}
        values[physical(ns.META_KEY)] = {'schema_version':'0.1','updated_at':'2026-11-06T09:00:00Z'}
        return GetOnly(values)

    def test_normal_preserves_values_clocks_hashes_and_input(self):
        reader = self.normal(); before = deepcopy(reader.values)
        result = self.observe(reader)
        self.assertEqual(result['status'], 'OBSERVED_STABLE')
        self.assertTrue(result['read_plan_complete'])
        self.assertEqual(result['missing_canonical_or_event_keys'], [])
        self.assertEqual(reader.values, before)
        self.assertEqual(result['shards'][ns.SOURCE_HEALTH_KEY]['value'], before[physical(ns.SOURCE_HEALTH_KEY)])
        self.assertEqual(result, self.observe(GetOnly(before)))
        self.assertFalse(result['apply_allowed'])
        self.assertFalse(result['migration_usable'])
        self.assertFalse(result['coverage']['complete'])
        self.assertFalse(result['atomic_snapshot_guaranteed'])

    def test_empty_cache_retains_missing_and_no_fallback(self):
        result = self.observe()
        self.assertEqual(len(result['missing_canonical_or_event_keys']), 14)
        self.assertTrue(all(s['value'] is None for s in result['shards'].values()))
        self.assertTrue(all(s['state']=='UNINITIALIZED_OR_UNAVAILABLE' for s in result['shards'].values()))

    def test_present_empty_differs_from_uninitialized(self):
        result = self.observe(GetOnly({physical(ns.CCGP_RECORDS_KEY):[]}))
        self.assertEqual(result['shards'][ns.CCGP_RECORDS_KEY]['state'], 'PRESENT_EMPTY')
        self.assertNotIn(ns.CCGP_RECORDS_KEY, result['missing_canonical_or_event_keys'])

    def test_missing_identity_rejected_before_read(self):
        for name in SCOPE:
            scope = dict(SCOPE); scope.pop(name); reader = GetOnly()
            with self.assertRaisesRegex(export.ExportRejected, 'EXPORT_SCOPE_REJECTED'):
                self.observe(reader, scope=scope)
            self.assertEqual(reader.reads, [])

    def test_cross_epoch_production_project_database_rejected_before_read(self):
        for field,value in [('preview_epoch','mcai-p0-20261106-c'),('target','production'),
                            ('database','other'),('project_id','other')]:
            for arg in ('scope','expected_scope'):
                scope = dict(SCOPE); scope[field]=value; reader = GetOnly()
                with self.assertRaisesRegex(export.ExportRejected, 'EXPORT_SCOPE_REJECTED'):
                    self.observe(reader, **{arg:scope})
                self.assertEqual(reader.reads, [])

    def test_read_trace_only_fixed_d_namespace_no_snapshot(self):
        reader = GetOnly(); self.observe(reader)
        self.assertEqual(reader.reads, [physical(k) for k in export._plan()]*2)
        self.assertTrue(all(k.startswith('medicalchannelai:preview:mcai-p0-20261106-d:') for k in reader.reads))
        self.assertTrue(all('snapshot' not in k and '20261106-c' not in k for k in reader.reads))

    def test_write_capability_reader_rejected_with_zero_calls(self):
        for method in ('set','delete','expire','expire_tag','expireTag','clear'):
            reader = GetOnly(); setattr(reader, method, lambda *a: self.fail('write called'))
            with self.assertRaisesRegex(export.ExportRejected, 'EXPORT_GET_ONLY_REQUIRED'):
                self.observe(reader)
            self.assertEqual(reader.reads, [])

    def test_owner_version_canonical_health_pending_changes_reject_entire_export(self):
        for key in (ns.ACTIVE_CYCLE_KEY,ns.META_KEY,ns.CCGP_RECORDS_KEY,ns.SOURCE_HEALTH_KEY,
                    'medicalchannelai:collector-incremental-pending-barrier:tjmugh:v2'):
            target = physical(key)
            def change(reader, actual):
                if len(reader.reads)>len(export._plan()) and actual == target:
                    reader.values[target] = {'changed':'new-version'}
            with self.assertRaisesRegex(export.ExportRejected, 'EXPORT_VERSION_OR_OWNER_CHANGED'):
                self.observe(GetOnly(hook=change))

    def test_mutable_reader_references_do_not_hide_concurrency(self):
        reader = self.normal()
        def change(r, key):
            if len(r.reads)==len(export._plan()):
                r.values[physical(ns.ACTIVE_CYCLE_KEY)]['cycle_id']='new-owner'
        reader.hook=change
        with self.assertRaisesRegex(export.ExportRejected,'EXPORT_VERSION_OR_OWNER_CHANGED'):
            self.observe(reader)

    def test_partial_failure_in_either_pass_returns_no_result(self):
        for nth in (3,len(export._plan())+3):
            def fail(reader,key):
                if len(reader.reads)==nth: raise OSError('sensitive failure details')
            with self.assertRaisesRegex(export.ExportRejected,'^EXPORT_READ_FAILED$'):
                self.observe(GetOnly(hook=fail))

    def test_value_and_total_byte_limits_fail_closed(self):
        with self.assertRaisesRegex(export.ExportRejected,'EXPORT_VALUE_SIZE_LIMIT'):
            self.observe(GetOnly({physical(ns.META_KEY):{'x':'z'*100}}),limits=replace(export.ExportLimits(),max_value_bytes=30))
        with self.assertRaisesRegex(export.ExportRejected,'EXPORT_TOTAL_SIZE_LIMIT'):
            self.observe(limits=replace(export.ExportLimits(),max_total_bytes=10))

    def test_record_limit_not_silent_truncation(self):
        with self.assertRaisesRegex(export.ExportRejected,'EXPORT_RECORD_COUNT_LIMIT'):
            self.observe(self.normal(),limits=replace(export.ExportLimits(),max_records=1))

    def test_limits_cannot_expand_hard_ceiling_and_reject_before_reads(self):
        for value in (0,-1,True,4_000_001):
            reader = GetOnly()
            with self.assertRaisesRegex(export.ExportRejected,'EXPORT_LIMITS_INVALID'):
                self.observe(reader,limits=replace(export.ExportLimits(),max_value_bytes=value))
            self.assertEqual(reader.reads,[])

    def test_non_json_nan_and_depth_rejected(self):
        for value in ({'x':float('nan')},{'x':object()},{1:'bad'}, {'a':{'b':{'c':1}}}):
            with self.assertRaises(export.ExportRejected):
                self.observe(GetOnly({physical(ns.META_KEY):value}),limits=replace(export.ExportLimits(),max_depth=2))

    def test_invalid_canonical_or_events_or_metadata_rejected(self):
        for key,value in ((ns.CCGP_RECORDS_KEY,{}),(ns.CCGP_RECORDS_KEY,[{}]),
                          (ns.CCGP_EVENTS_KEY,[{}]),(ns.META_KEY,[])):
            with self.assertRaisesRegex(export.ExportRejected,'EXPORT_STATE_INVALID'):
                self.observe(GetOnly({physical(key):value}))

    def test_unknown_metadata_preserved_opaque_never_coverage_success(self):
        result = self.observe(GetOnly({physical(ns.META_KEY):{'future_version':{'unknown':1}}}))
        self.assertEqual(result['shards'][ns.META_KEY]['semantic_coverage'],'OPAQUE_NOT_SEMANTICALLY_COVERED')
        self.assertFalse(result['coverage']['complete'])

    def test_actual_pending_barrier_string_list_and_watch_shapes(self):
        key='medicalchannelai:collector-incremental-pending-barrier:tjmugh:v2'
        values={physical(key):['https://example.org/pending'],physical(ns.CCGP_WATCH_KEY):['project-1']}
        result=self.observe(GetOnly(values))
        self.assertEqual(result['shards'][key]['value'],values[physical(key)])
        self.assertEqual(result['shards'][key]['uncovered_paths'],['/**'])
        with self.assertRaisesRegex(export.ExportRejected,'EXPORT_STATE_INVALID'):
            self.observe(GetOnly({physical(key):{}}))

    def test_unknown_canonical_extensions_are_explicitly_uncovered(self):
        reader=self.normal(); key='medicalchannelai:collector-regional-records:v3:HE'
        reader.values[physical(key)][0]['future_metadata']={'x':1}
        reader.values[physical(key)][0]['facts']['future_fact']='unknown'
        result=self.observe(reader)
        paths=result['shards'][key]['uncovered_paths']
        self.assertIn('/0/future_metadata',paths)
        self.assertIn('/0/facts/future_fact',paths)
        self.assertFalse(result['migration_usable'])

    def test_structural_node_limit_rejected(self):
        with self.assertRaisesRegex(export.ExportRejected,'EXPORT_STRUCTURE_LIMIT'):
            self.observe(GetOnly({physical(ns.META_KEY):{'a':[1,2,3]}}),
                         limits=replace(export.ExportLimits(),max_nodes=3))

    def test_wrong_market_and_cross_shard_duplicates_rejected(self):
        reader=self.normal()
        source=physical('medicalchannelai:collector-regional-records:v3:HE')
        reader.values[physical('medicalchannelai:collector-regional-records:v3:JL')]=reader.values[source]
        with self.assertRaisesRegex(export.ExportRejected,'EXPORT_STATE_INVALID'):
            self.observe(reader)
        reader=self.normal(); reader.values[physical(ns.CCGP_RECORDS_KEY)]=reader.values[source]
        with self.assertRaisesRegex(export.ExportRejected,'EXPORT_STATE_INVALID'):
            self.observe(reader)

    def test_committed_state_precedence_matches_publish_without_erasing_raw_shard(self):
        reader=self.normal(); committed='medicalchannelai:collector-ccgp-committed:v2'
        reader.values[physical(committed)]={'cycle_as_of':'2026-11-06T09:00:00Z','records':[],'events':[]}
        result=self.observe(reader)
        self.assertEqual(result['effective_ccgp_key'],committed)
        self.assertIn(ns.CCGP_RECORDS_KEY,result['shards'])

    def test_existing_key_functions_and_namespace_parity(self):
        import collector_runtime as runtime
        import collector_incremental_runtime as incremental
        plan=export._plan()
        for market in runtime.REGIONAL_STAGE_MARKET_CODES.values():
            self.assertIn(runtime._regional_records_key(market),plan)
        for source in export.SOURCE_POLICIES:
            for name in ('ledger','bucket','pending','pending_barrier'):
                self.assertIn(getattr(incremental,'_'+name+'_cache_key')(source),plan)
        for name in ('CCGP_COMMITTED_STATE_KEY','CCGP_CYCLE_STAGING_KEY'):
            self.assertIn(getattr(runtime,name),plan)
        self.assertEqual(plan[ns.TJFCH_RECORDS_KEY]['sources'],['tjfch','tjfch_test'])

    def test_import_and_execution_do_not_construct_cache_or_access_network(self):
        with patch('collector_epoch.RuntimeCache',side_effect=AssertionError('CLIENT_FORBIDDEN')), \
             patch('socket.create_connection',side_effect=AssertionError('NETWORK_FORBIDDEN')), \
             patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_FORBIDDEN')):
            module=importlib.reload(export)
            result=module.observe_d_canonical(GetOnly(),scope=SCOPE,expected_scope=SCOPE)
            self.assertTrue(result['read_plan_complete'])


if __name__=='__main__':
    unittest.main()
