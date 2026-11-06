from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_ccgp_product_backfill import audit, main


class OfflineBackfillAuditSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        corpus = ROOT / 'tests/fixtures/ccgp_template_audit_20261106'
        manifest = json.loads((corpus / 'manifest.json').read_text())
        self.case = deepcopy(next(c for c in manifest['cases'] if c['label'] == 'ccgp_he_2a9ca892bf9d0b6a'))
        self.fixture = self.folder / self.case['file']
        self.fixture.write_bytes((corpus / self.case['file']).read_bytes())
        self.manifest = self.folder / 'manifest.json'
        self.manifest.write_text(json.dumps({**manifest, 'cases': [self.case]}))
        records = json.loads((ROOT / 'data/regional_live_ccgp_records.json').read_text())
        self.record = next(r for r in records if r['opportunity_id'] == self.case['baseline_id'])
        self.baseline = self.folder / 'baseline.json'
        self.baseline.write_text(json.dumps([self.record]))

    def test_passing_fixture_only_proposes_and_never_rewrites_inputs(self):
        files = [self.fixture, self.manifest, self.baseline]
        before = [p.read_bytes() for p in files]
        report = audit(self.manifest, [self.baseline])
        self.assertTrue(report['fixture_gate_pass'])
        self.assertFalse(report['apply_allowed'])
        self.assertEqual(report['network_requests'], 0)
        self.assertEqual(len(report['patch_proposals']), 1)
        self.assertEqual(report['patch_proposals'][0]['allowed_fact_fields'], ['product_items', 'product_categories'])
        self.assertTrue(report['patch_proposals'][0]['evidence_updates_required_before_apply'])
        self.assertEqual(before, [p.read_bytes() for p in files])

    def test_changed_official_bytes_are_rejected_before_proposal(self):
        self.fixture.write_bytes(self.fixture.read_bytes() + b' changed')
        with self.assertRaisesRegex(ValueError, 'FIXTURE_HASH_OR_SIZE_MISMATCH'):
            audit(self.manifest, [self.baseline])

    def test_duplicate_baseline_identity_is_rejected(self):
        self.baseline.write_text(json.dumps([self.record, self.record]))
        with self.assertRaisesRegex(ValueError, 'BASELINE_DUPLICATE_ID'):
            audit(self.manifest, [self.baseline])

    def test_same_id_with_other_project_number_is_rejected(self):
        changed = deepcopy(self.record)
        changed['facts']['project_number'] += '-OTHER'
        self.baseline.write_text(json.dumps([changed]))
        with self.assertRaisesRegex(ValueError, 'BASELINE_OFFICIAL_IDENTITY_MISMATCH'):
            audit(self.manifest, [self.baseline])

    def test_fixture_path_escape_is_rejected(self):
        manifest = json.loads(self.manifest.read_text())
        manifest['cases'][0]['file'] = '../outside.html'
        self.manifest.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'FIXTURE_PATH_OUTSIDE_CORPUS'):
            audit(self.manifest, [self.baseline])

    def test_cli_cannot_overwrite_baseline(self):
        before = self.baseline.read_bytes()
        with patch.object(sys, 'argv', ['audit', '--manifest', str(self.manifest), '--baseline', str(self.baseline), '--output', str(self.baseline)]):
            with self.assertRaisesRegex(ValueError, 'OUTPUT_MUST_NOT_OVERWRITE_INPUT'):
                main()
        self.assertEqual(self.baseline.read_bytes(), before)
