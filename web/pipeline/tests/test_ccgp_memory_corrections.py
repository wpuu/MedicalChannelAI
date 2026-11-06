from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import simulate_ccgp_product_corrections as sim
from audit_ccgp_product_backfill import object_hash

EVIDENCE=ROOT.parents[1]/'docs/project/validation/ccgp-product-dry-run-2026-11-06'


class MemoryCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.change_set=json.loads((EVIDENCE/'change-set.json').read_text())
        cls.scope=cls.change_set['target_scope']
        cls.baselines=[ROOT/'data/tianjin_live_ccgp_records.json',ROOT/'data/regional_live_ccgp_records.json']
        cls.originals=[record for path in cls.baselines for record in json.loads(path.read_text())]
        cls.verification={'manifest_path':ROOT/'tests/fixtures/ccgp_template_audit_20261106/manifest.json',
            'baseline_paths':cls.baselines,'request_path':ROOT/'tests/fixtures/ccgp_product_dry_run_request_20261106.json',
            'expected_request_sha256':cls.change_set['reviewed_request_sha256'],'expected_scope':cls.scope}

    def setUp(self):
        self.changes=deepcopy(self.change_set)
        self.state={'schema_version':'0.1','input_kind':'FROZEN_MEMORY_STATE','target_scope':deepcopy(self.scope),
            'records':deepcopy(self.originals),'events':[],'pending':[]}
        self.version=object_hash(self.state)

    def overlay(self, state=None, changes=None, version=None):
        return sim.simulate_overlay(changes if changes is not None else self.changes,
            state if state is not None else self.state, expected_state_sha256=version or self.version,**self.verification)

    def rollback(self, state, receipt, **overrides):
        return sim.simulate_rollback(self.changes,state,receipt,
            expected_receipt_sha256=overrides.get('lock',object_hash(receipt)),**self.verification)

    def test_whole_batch_overlay_and_rollback_restore_all892_records_exactly(self):
        before=deepcopy(self.state)
        after,report=self.overlay()
        self.assertEqual(self.state,before)
        self.assertEqual(report['status'],'SIMULATED_APPLIED')
        self.assertEqual(report['changed_record_count'],2)
        selected={c['identity']['opportunity_id'] for c in self.changes['changes']}
        old={r['opportunity_id']:r for r in self.state['records']}
        for row in after['records']:
            if row['opportunity_id'] not in selected:self.assertEqual(row,old[row['opportunity_id']])
        after_copy=deepcopy(after)
        restored,rollback=self.rollback(after,report['receipt'])
        self.assertEqual(restored,before)
        self.assertEqual(object_hash(restored),self.version)
        self.assertEqual(after,after_copy)
        self.assertEqual(rollback['status'],'SIMULATED_RESTORED')
        self.assertFalse(report['apply_allowed'])
        self.assertFalse(rollback['runtime_cas_implemented'])

    def test_overlay_and_rollback_replays_are_whole_batch_noops(self):
        after,applied=self.overlay()
        repeated,r=self.overlay(after,version=object_hash(after))
        self.assertEqual(repeated,after)
        self.assertEqual(r['status'],'ALREADY_SIMULATED')
        self.assertEqual(r['changed_record_count'],0)
        restored,_=self.rollback(after,applied['receipt'])
        again,r=self.rollback(restored,applied['receipt'])
        self.assertEqual(again,restored)
        self.assertEqual(r['status'],'ALREADY_RESTORED')
        self.assertEqual(r['changed_record_count'],0)

    def test_second_bad_hash_rejects_entire_batch_without_touching_first(self):
        before=deepcopy(self.state)
        self.changes['changes'][1]['candidate_record_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'CHANGE_SET_CONTENT_MISMATCH'):self.overlay()
        self.assertEqual(self.state,before)

    def test_before_hash_change_is_rejected(self):
        self.changes['changes'][0]['before_record_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'CHANGE_SET_CONTENT_MISMATCH'):self.overlay()

    def test_rehashed_non_whitelist_candidate_cannot_bypass_trusted_generation(self):
        change=self.changes['changes'][0]
        change['candidate_record']['facts']['published_at']='2026-11-06'
        change['candidate_record_sha256']=object_hash(change['candidate_record'])
        with self.assertRaisesRegex(ValueError,'CHANGE_SET_CONTENT_MISMATCH'):self.overlay()

    def test_forged_product_evidence_is_rejected(self):
        c=self.changes['changes'][0]
        c['candidate_record']['evidence'][-1]['locator']='UNVERIFIED'
        c['after']['evidence'][-1]['locator']='UNVERIFIED'
        c['candidate_record_sha256']=object_hash(c['candidate_record'])
        fields=('target_scope','identity','before_record_sha256','candidate_record_sha256','official_html_sha256','parser_sha256','generator_sha256')
        c['change_id']=object_hash({key:c[key] for key in fields})
        self.changes['change_set_id']=object_hash({'request_sha256':self.changes['reviewed_request_sha256'],
            'target_scope':self.scope,'change_ids':[change['change_id'] for change in self.changes['changes']]})
        with self.assertRaisesRegex(ValueError,'CHANGE_SET_CONTENT_MISMATCH'):self.overlay()

    def test_cross_environment_state_and_artifact_are_rejected(self):
        self.state['target_scope']['preview_epoch']='mcai-p0-other'
        with self.assertRaisesRegex(ValueError,'STATE_SCOPE_OR_KIND_MISMATCH'):
            self.overlay(version=object_hash(self.state))
        self.changes['target_scope']['database']='other'
        with self.assertRaisesRegex(ValueError,'CHANGE_SET_CONTENT_MISMATCH'):self.overlay()

    def test_stale_snapshot_version_rejects_even_unselected_changes(self):
        self.state['events'].append({'event_id':'SYNTHETIC_CONCURRENT_EVENT'})
        before=deepcopy(self.state)
        with self.assertRaisesRegex(ValueError,'STATE_VERSION_CONFLICT'):self.overlay()
        self.assertEqual(self.state,before)

    def test_concurrent_selected_fact_rejected_even_with_refreshed_snapshot_hash(self):
        key=self.changes['changes'][1]['identity']['opportunity_id']
        row=next(r for r in self.state['records'] if r['opportunity_id']==key)
        row['source']['observed_at']='2026-11-06T12:26:01+00:00'
        before=deepcopy(self.state)
        with self.assertRaisesRegex(ValueError,'SELECTED_RECORD_VERSION_CONFLICT'):
            self.overlay(version=object_hash(self.state))
        self.assertEqual(self.state,before)

    def test_mixed_before_after_is_not_silently_completed(self):
        change=self.changes['changes'][0]
        key=change['identity']['opportunity_id']
        self.state['records']=[deepcopy(change['candidate_record']) if r['opportunity_id']==key else r for r in self.state['records']]
        before=deepcopy(self.state)
        with self.assertRaisesRegex(ValueError,'MIXED_BATCH_STATE'):
            self.overlay(version=object_hash(self.state))
        self.assertEqual(self.state,before)

    def test_missing_selected_record_is_rejected(self):
        key=self.changes['changes'][0]['identity']['opportunity_id']
        self.state['records']=[r for r in self.state['records'] if r['opportunity_id']!=key]
        with self.assertRaisesRegex(ValueError,'SELECTED_RECORD_VERSION_CONFLICT'):
            self.overlay(version=object_hash(self.state))

    def test_post_preflight_concurrent_event_is_not_overwritten(self):
        original=sim._positions
        def mutate(changes,current):
            positions=original(changes,current)
            self.state['events'].append({'event_id':'SYNTHETIC_AFTER_PREFLIGHT'})
            return positions
        with patch.object(sim,'_positions',side_effect=mutate):
            with self.assertRaisesRegex(ValueError,'STATE_CHANGED_AFTER_PREFLIGHT'):self.overlay()
        self.assertEqual(self.state['records'],self.originals)
        self.assertEqual(len(self.state['events']),1)

    def test_rollback_rejects_new_facts_and_new_events_preserving_both(self):
        after,applied=self.overlay()
        for kind in ('fact','selected_fact','event','unselected'):
            with self.subTest(kind=kind):
                current=deepcopy(after)
                if kind=='event':current['events'].append({'event_id':'SYNTHETIC_LATER_TERMINATION'})
                elif kind=='fact':current['records'][0]['facts']['project_name']+='-NEW'
                elif kind=='selected_fact':
                    key=self.changes['changes'][0]['identity']['opportunity_id']
                    next(r for r in current['records'] if r['opportunity_id']==key)['facts']['product_items'][0]['quantity']='99台'
                else:current['pending'].append({'url':'SYNTHETIC_NEW_PENDING'})
                before=deepcopy(current)
                with self.assertRaisesRegex(ValueError,'ROLLBACK_STATE_VERSION_CONFLICT'):
                    self.rollback(current,applied['receipt'])
                self.assertEqual(current,before)

    def test_receipt_version_and_batch_binding_are_independently_checked(self):
        after,applied=self.overlay();receipt=deepcopy(applied['receipt']);lock=object_hash(receipt)
        receipt['before_state_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'RECEIPT_VERSION_MISMATCH'):
            self.rollback(after,receipt,lock=lock)
        receipt=deepcopy(applied['receipt']);receipt['change_set_id']='other'
        receipt['receipt_id']=object_hash({k:v for k,v in receipt.items() if k!='receipt_id'})
        with self.assertRaisesRegex(ValueError,'RECEIPT_BINDING_MISMATCH'):
            self.rollback(after,receipt)

    def test_duplicate_replay_preserves_unselected_events_when_explicitly_rebased(self):
        after,_=self.overlay();after['events'].append({'event_id':'SYNTHETIC_UNRELATED_EVENT'})
        repeated,report=self.overlay(after,version=object_hash(after))
        self.assertEqual(repeated,after)
        self.assertEqual(report['status'],'ALREADY_SIMULATED')

    def test_no_network_and_all_original_inputs_remain_unchanged(self):
        paths=[*self.baselines,self.verification['manifest_path'],self.verification['request_path'],EVIDENCE/'change-set.json']
        before={str(p):p.read_bytes() for p in paths}
        with patch('socket.create_connection',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_FORBIDDEN')):
            after,report=self.overlay()
            restored,_=self.rollback(after,report['receipt'])
        self.assertEqual(restored,self.state)
        self.assertEqual(before,{str(p):p.read_bytes() for p in paths})

    def test_cli_writes_only_summary_and_never_overwrites_state(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);state_path=folder/'state.json';state_path.write_text(json.dumps(self.state))
            output=folder/'report.json';before=state_path.read_bytes()
            args=['sim','--manifest',str(self.verification['manifest_path']),'--request',str(self.verification['request_path']),
                '--change-set',str(EVIDENCE/'change-set.json'),'--state',str(state_path),'--output',str(output),
                '--expected-request-sha256',self.verification['expected_request_sha256'],'--expected-state-sha256',self.version,
                '--expected-project-id',self.scope['project_id'],'--expected-preview-epoch',self.scope['preview_epoch'],'--expected-database',self.scope['database']]
            for path in self.baselines:args+=['--baseline',str(path)]
            with patch.object(sys,'argv',args),redirect_stdout(StringIO()):self.assertEqual(sim.main(),0)
            report=json.loads(output.read_text())
            self.assertTrue(report['whole_state_restored']);self.assertFalse(report['apply_allowed'])
            self.assertNotIn('records',report)
            self.assertEqual(state_path.read_bytes(),before)
            bad=args.copy();bad[bad.index('--output')+1]=str(state_path)
            with patch.object(sys,'argv',bad):
                with self.assertRaisesRegex(ValueError,'OUTPUT_OVERWRITES_PROTECTED_INPUT'):sim.main()
            self.assertEqual(state_path.read_bytes(),before)
            fake_root=folder/'project/web/pipeline'
            snapshot=folder/'project/web/public/snapshot.json'
            snapshot.parent.mkdir(parents=True);snapshot.write_text('KEEP')
            outside=args.copy();outside[outside.index('--output')+1]=str(snapshot)
            with patch.object(sim,'ROOT',fake_root),patch.object(sys,'argv',outside):
                with self.assertRaisesRegex(ValueError,'OUTSIDE_NEW_ARTIFACT_AREA'):sim.main()
            self.assertEqual(snapshot.read_text(),'KEEP')

    def test_cli_failed_batch_does_not_replace_existing_report(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);bad=folder/'change-set.json';self.changes['changes'][1]['before_record_sha256']='0'*64;bad.write_text(json.dumps(self.changes))
            state=folder/'state.json';state.write_text(json.dumps(self.state));output=folder/'report.json';output.write_text('KEEP')
            args=['sim','--manifest',str(self.verification['manifest_path']),'--request',str(self.verification['request_path']),
                '--change-set',str(bad),'--state',str(state),'--output',str(output),'--expected-request-sha256',self.verification['expected_request_sha256'],
                '--expected-state-sha256',self.version,'--expected-project-id',self.scope['project_id'],'--expected-preview-epoch',self.scope['preview_epoch'],'--expected-database',self.scope['database']]
            for path in self.baselines:args+=['--baseline',str(path)]
            with patch.object(sys,'argv',args):
                with self.assertRaisesRegex(ValueError,'CHANGE_SET_CONTENT_MISMATCH'):sim.main()
            self.assertEqual(output.read_text(),'KEEP')
