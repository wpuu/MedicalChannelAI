from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit_ccgp_product_backfill as target

REQUEST = ROOT / 'tests/fixtures/ccgp_product_dry_run_request_20261106.json'
CORPUS = ROOT / 'tests/fixtures/ccgp_template_audit_20261106'


class ProductDryRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.corpus = self.folder / 'corpus'
        shutil.copytree(CORPUS, self.corpus)
        self.manifest = self.corpus / 'manifest.json'
        self.baselines = []
        for name in ('tianjin_live_ccgp_records.json', 'regional_live_ccgp_records.json'):
            path = self.folder / name
            shutil.copyfile(ROOT / 'data' / name, path)
            self.baselines.append(path)
        self.request = self.folder / 'request.json'
        shutil.copyfile(REQUEST, self.request)
        self.scope = deepcopy(json.loads(self.request.read_text())['target_scope'])
        self.lock = target.digest(self.request.read_bytes())

    def revise_request(self, edit):
        data = json.loads(self.request.read_text())
        edit(data)
        self.request.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        self.lock = target.digest(self.request.read_bytes())

    def run_dry(self):
        return target.build_dry_run(self.manifest, self.baselines, self.request,
            expected_request_sha256=self.lock, expected_scope=self.scope)

    def cli_args(self, output):
        return ['audit', '--manifest',str(self.manifest), '--baseline',str(self.baselines[0]),
            '--baseline',str(self.baselines[1]), '--output',str(output), '--dry-run-request',str(self.request),
            '--expected-request-sha256',self.lock,'--expected-project-id',self.scope['project_id'],
            '--expected-preview-epoch',self.scope['preview_epoch'],'--expected-database',self.scope['database']]

    def test_two_official_candidates_have_evidence_and_repeat_identically_without_input_writes(self):
        files = [self.request,self.manifest,*self.baselines,*self.corpus.glob('*.html')]
        before = {str(p):p.read_bytes() for p in files}
        first = self.run_dry()
        self.assertEqual(first,self.run_dry())
        self.assertEqual(first['selected_count'],2)
        self.assertFalse(first['apply_allowed'])
        self.assertFalse(first['runtime_canonical_exported'])
        self.assertFalse(first['migration_complete'])
        self.assertEqual(first['network_requests'],0)
        self.assertEqual(first['fixture_gate'],{'passed':10,'failed':0})
        old_by_id = {r['opportunity_id']:r for p in self.baselines for r in json.loads(p.read_text())}
        for change in first['changes']:
            old = old_by_id[change['identity']['opportunity_id']]
            new = change['candidate_record']
            self.assertEqual(new['source'],old['source'])
            self.assertEqual(new['opportunity_id'],old['opportunity_id'])
            for key,value in old['facts'].items():
                if key not in ('product_items','product_categories'):
                    self.assertEqual(new['facts'][key],value,key)
            self.assertEqual([e for e in new['evidence'] if e['field_path'] not in target.PRODUCT_EVIDENCE_PATHS],
                [e for e in old['evidence'] if e['field_path'] not in target.PRODUCT_EVIDENCE_PATHS])
            self.assertTrue(change['after']['evidence'])
            self.assertTrue(all(e['source_url']==old['source']['url'] and e['locator'] for e in change['after']['evidence']))
            self.assertEqual(target.object_hash(new),change['candidate_record_sha256'])
            self.assertFalse(change['apply_allowed'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in files})

    def test_explicit_single_selection_does_not_fill_batch(self):
        self.revise_request(lambda r:r.update(selected_records=r['selected_records'][:1]))
        self.assertEqual(self.run_dry()['selected_count'],1)

    def test_stale_product_evidence_is_replaced_without_touching_other_evidence(self):
        rows=json.loads(self.baselines[1].read_text())
        record=next(r for r in rows if r['opportunity_id']=='ccgp_he_2a9ca892bf9d0b6a')
        record['facts']['product_categories']=['旧分类']
        record['evidence'].append({'field_path':'facts.product_categories','source_url':record['source']['url'],'locator':'旧采购目录'})
        unrelated=[deepcopy(e) for e in record['evidence'] if e['field_path'] not in target.PRODUCT_EVIDENCE_PATHS]
        self.baselines[1].write_text(json.dumps(rows,ensure_ascii=False))
        def review(request):
            request['baseline_files']=sorted([{'path':p.name,'sha256':target.digest(p.read_bytes())} for p in self.baselines],key=lambda r:r['path'])
            request['selected_records'][0]['before_record_sha256']=target.object_hash(record)
        self.revise_request(review)
        change=self.run_dry()['changes'][0]
        self.assertEqual(change['after']['product_categories'],[])
        self.assertFalse(any(e['field_path']=='facts.product_categories' for e in change['after']['evidence']))
        self.assertEqual([e for e in change['candidate_record']['evidence'] if e['field_path'] not in target.PRODUCT_EVIDENCE_PATHS],unrelated)

    def test_empty_and_six_record_selections_are_rejected(self):
        for selected in ([],[{'opportunity_id':str(n)} for n in range(6)]):
            with self.subTest(size=len(selected)):
                self.revise_request(lambda r:r.update(selected_records=selected))
                with self.assertRaisesRegex(ValueError,'SELECTION_1_TO_5'):
                    self.run_dry()

    def test_duplicate_selected_ids_are_rejected(self):
        self.revise_request(lambda r:r.update(selected_records=[r['selected_records'][0]]*2))
        with self.assertRaisesRegex(ValueError,'DUPLICATE_OR_INVALID_SELECTION'):
            self.run_dry()

    def test_alias_ids_for_the_same_project_cannot_bypass_duplicate_identity(self):
        rows=json.loads(self.baselines[1].read_text())
        original=next(r for r in rows if r['opportunity_id']=='ccgp_he_2a9ca892bf9d0b6a')
        alias=deepcopy(original);alias['opportunity_id']='ccgp_he_alias_of_same_notice';rows.append(alias)
        self.baselines[1].write_text(json.dumps(rows,ensure_ascii=False))
        manifest=json.loads(self.manifest.read_text())
        case=deepcopy(next(c for c in manifest['cases'] if c.get('baseline_id')==original['opportunity_id']))
        case['label']=alias['opportunity_id'];case['baseline_id']=alias['opportunity_id'];manifest['cases'].append(case)
        self.manifest.write_text(json.dumps(manifest,ensure_ascii=False))
        def review(request):
            selection=deepcopy(request['selected_records'][0]);selection['opportunity_id']=alias['opportunity_id'];selection['identity']['opportunity_id']=alias['opportunity_id'];selection['before_record_sha256']=target.object_hash(alias)
            request['selected_records']=[request['selected_records'][0],selection]
            request['baseline_files']=sorted([{'path':p.name,'sha256':target.digest(p.read_bytes())} for p in self.baselines],key=lambda r:r['path'])
            request['fixture_manifest_sha256']=target.digest(self.manifest.read_bytes())
        self.revise_request(review)
        with self.assertRaisesRegex(ValueError,'DUPLICATE_CANONICAL_OPPORTUNITY|DUPLICATE_NOTICE_IDENTITY'):
            self.run_dry()

    def test_unknown_and_non_original_ids_are_rejected(self):
        for key in ('ccgp_missing','qualification_general_table'):
            with self.subTest(key=key):
                self.revise_request(lambda r:r.update(selected_records=[{'opportunity_id':key}]))
                with self.assertRaisesRegex(ValueError,'SELECTED_ID_NOT_PROPOSED'):
                    self.run_dry()

    def test_production_wrong_epoch_and_wrong_database_are_rejected(self):
        original = json.loads(REQUEST.read_text())
        for key,value in [('target','production'),('preview_epoch','mcai-p0-OTHER'),('database','neondb'),('project_id','prj_OTHER')]:
            with self.subTest(key=key):
                self.request.write_text(json.dumps(original))
                self.revise_request(lambda r:r['target_scope'].update({key:value}))
                with self.assertRaisesRegex(ValueError,'ENVIRONMENT_MISMATCH'):
                    self.run_dry()

    def test_stale_record_hash_is_rejected(self):
        self.revise_request(lambda r:r['selected_records'][0].update(before_record_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'RECORD_VERSION_MISMATCH'):
            self.run_dry()

    def test_wrong_market_project_source_and_url_are_rejected(self):
        original = json.loads(REQUEST.read_text())
        for key,value in [('market_code','BJ'),('project_number','OTHER'),('source_id','ccgp:OTHER'),('source_url','https://example.com/')]:
            with self.subTest(key=key):
                self.request.write_text(json.dumps(original))
                self.revise_request(lambda r:r['selected_records'][0]['identity'].update({key:value}))
                with self.assertRaisesRegex(ValueError,'RECORD_IDENTITY_MISMATCH'):
                    self.run_dry()

    def test_unreviewed_request_byte_change_is_rejected(self):
        self.request.write_bytes(self.request.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'REQUEST_HASH_MISMATCH'):
            self.run_dry()

    def test_stale_parser_and_official_versions_are_rejected(self):
        original = json.loads(REQUEST.read_text())
        self.revise_request(lambda r:r.update(parser_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'PARSER_VERSION_MISMATCH'):
            self.run_dry()
        self.request.write_text(json.dumps(original))
        self.revise_request(lambda r:r['selected_records'][0].update(official_html_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'OFFICIAL_VERSION_MISMATCH'):
            self.run_dry()

    def test_changed_baseline_file_is_rejected_even_when_record_is_unchanged(self):
        self.baselines[1].write_bytes(self.baselines[1].read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'BASELINE_VERSION_MISMATCH'):
            self.run_dry()

    def test_changed_manifest_and_official_blob_are_rejected(self):
        before = self.manifest.read_bytes()
        self.manifest.write_bytes(before+b'\n')
        with self.assertRaisesRegex(ValueError,'MANIFEST_VERSION_MISMATCH'):
            self.run_dry()
        self.manifest.write_bytes(before)
        fixture = next(self.corpus.glob('*.html'))
        fixture.write_bytes(fixture.read_bytes()+b' changed')
        with self.assertRaisesRegex(ValueError,'FIXTURE_HASH_OR_SIZE_MISMATCH'):
            self.run_dry()

    def test_no_runtime_export_may_be_mislabelled_as_frozen_input(self):
        self.revise_request(lambda r:r.update(input_kind='RUNTIME_CANONICAL_EXPORT'))
        with self.assertRaisesRegex(ValueError,'FROZEN_INPUT_REQUIRED'):
            self.run_dry()

    def test_cli_writes_only_requested_artifact_and_rejects_overwriting_request(self):
        output = self.folder/'change-set.json'
        with patch.object(sys,'argv',self.cli_args(output)),redirect_stdout(StringIO()):
            self.assertEqual(target.main(),0)
        self.assertEqual(json.loads(output.read_text()),self.run_dry())
        before = self.request.read_bytes()
        with patch.object(sys,'argv',self.cli_args(self.request)):
            with self.assertRaisesRegex(ValueError,'OUTPUT_MUST_NOT_OVERWRITE_INPUT'):
                target.main()
        self.assertEqual(before,self.request.read_bytes())

    def test_output_symlink_and_hardlink_to_baseline_are_rejected(self):
        for name,kind in [('symlink.json','symlink'),('hardlink.json','hardlink')]:
            output = self.folder/name
            if kind=='symlink':output.symlink_to(self.baselines[0])
            else:output.hardlink_to(self.baselines[0])
            before = self.baselines[0].read_bytes()
            with patch.object(sys,'argv',self.cli_args(output)):
                with self.assertRaisesRegex(ValueError,'OUTPUT_MUST_NOT_OVERWRITE_INPUT'):
                    target.main()
            self.assertEqual(before,self.baselines[0].read_bytes())

    def test_output_in_protected_data_tree_is_rejected(self):
        fake_root=self.folder/'project';(fake_root/'data').mkdir(parents=True)
        output=fake_root/'data/other.json';output.write_text('KEEP')
        with patch.object(target,'ROOT',fake_root),patch.object(sys,'argv',self.cli_args(output)):
            with self.assertRaisesRegex(ValueError,'PROTECTED_INPUT_TREE'):
                target.main()
        self.assertEqual(output.read_text(),'KEEP')

    def test_artifact_replacement_cannot_modify_an_unselected_hardlinked_input(self):
        untouched=self.folder/'unselected-original.json';untouched.write_text('KEEP')
        output=self.folder/'artifact.json';output.hardlink_to(untouched)
        with patch.object(sys,'argv',self.cli_args(output)),redirect_stdout(StringIO()):
            self.assertEqual(target.main(),0)
        self.assertEqual(untouched.read_text(),'KEEP')
        self.assertFalse(json.loads(output.read_text())['apply_allowed'])

    def test_invalid_lock_cannot_replace_existing_output(self):
        output=self.folder/'result.json';output.write_text('KEEP')
        self.request.write_bytes(self.request.read_bytes()+b'\n')
        with patch.object(sys,'argv',self.cli_args(output)):
            with self.assertRaisesRegex(ValueError,'REQUEST_HASH_MISMATCH'):
                target.main()
        self.assertEqual(output.read_text(),'KEEP')

    def test_independent_scope_and_request_lock_are_mandatory(self):
        args=self.cli_args(self.folder/'out.json');args=args[:args.index('--expected-request-sha256')]
        with patch.object(sys,'argv',args):
            with self.assertRaisesRegex(ValueError,'INDEPENDENT_SCOPE_AND_REQUEST_LOCK_REQUIRED'):
                target.main()
