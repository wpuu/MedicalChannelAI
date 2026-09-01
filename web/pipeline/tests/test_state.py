from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from medical_channel_pipeline.state import (
    active_ccgp_project_numbers,
    merge_canonical_records,
    merge_notice_events,
)

ROOT = Path(__file__).resolve().parents[1]


class PipelineStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ccgp_records = json.loads(
            (ROOT / 'data' / 'tianjin_verified_seed.json').read_text(encoding='utf-8')
        )
        cls.institution_records = json.loads(
            (ROOT / 'data' / 'tianjin_official_institution_seed.json').read_text(encoding='utf-8')
        )

    def test_new_record_replaces_same_project_number_without_duplicate_state(self) -> None:
        original = copy.deepcopy(self.ccgp_records[0])
        replacement = copy.deepcopy(original)
        replacement['opportunity_id'] = 'replacement_opportunity_id'
        merged = merge_canonical_records([original], [replacement])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['opportunity_id'], 'replacement_opportunity_id')
        self.assertEqual(
            merged[0]['facts']['project_number'],
            original['facts']['project_number'],
        )

    def test_corrected_project_number_replaces_same_opportunity_id(self) -> None:
        corrected = copy.deepcopy(self.ccgp_records[0])
        polluted = copy.deepcopy(corrected)
        polluted['facts']['project_number'] = (
            f"{corrected['facts']['project_number']})公开招标公告"
        )
        polluted['source']['source_id'] = (
            f"ccgp:{polluted['facts']['project_number']}"
        )
        merged = merge_canonical_records([polluted], [corrected])
        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0]['facts']['project_number'],
            corrected['facts']['project_number'],
        )
        self.assertEqual(merged[0]['opportunity_id'], corrected['opportunity_id'])

    def test_new_record_collapses_project_and_opportunity_identity_duplicates(self) -> None:
        corrected = copy.deepcopy(self.ccgp_records[0])
        polluted = copy.deepcopy(corrected)
        polluted['facts']['project_number'] = (
            f"{corrected['facts']['project_number']})公开招标公告"
        )
        polluted['source']['source_id'] = (
            f"ccgp:{polluted['facts']['project_number']}"
        )
        merged = merge_canonical_records([polluted, corrected], [corrected])
        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0]['facts']['project_number'],
            corrected['facts']['project_number'],
        )

    def test_hospital_seed_transitions_to_live_state_without_duplicate(self) -> None:
        original = copy.deepcopy(self.institution_records[0])
        replacement = copy.deepcopy(original)
        replacement['source']['observed_at'] = '2026-08-31T11:30:00+00:00'
        merged = merge_canonical_records([original], [replacement])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['opportunity_id'], original['opportunity_id'])
        self.assertEqual(
            merged[0]['source']['observed_at'],
            '2026-08-31T11:30:00+00:00',
        )

    def test_event_with_same_id_can_be_reconciled_by_newer_state(self) -> None:
        base = {
            'schema_version': '0.1',
            'event_id': 'correction_demo',
            'event_type': 'CORRECTION',
            'project_number': 'XCSD-2026-C-181',
            'project_name': '病原微生物能力提升相关设备购置',
            'published_at': '2026-09-01',
            'source_url': 'https://www.ccgp.gov.cn/cggg/dfgg/gzgg/202609/t20260901_99999999.htm',
            'observed_at': '2026-09-01T10:00:00+08:00',
            'summary': 'DISCOVERY_ONLY_EVENT_REQUIRES_DETAIL_REVIEW',
            'changed_fact_paths': [],
            'fact_overrides': {},
            'unresolved_fact_paths': ['__discovery_only_event__'],
            'requires_reconciliation': True,
            'terminal': False,
        }
        reconciled = copy.deepcopy(base)
        reconciled['changed_fact_paths'] = ['facts.bid_deadline']
        reconciled['fact_overrides'] = {
            'facts.bid_deadline': '2026-09-18T09:30:00+08:00'
        }
        reconciled['unresolved_fact_paths'] = []
        reconciled['requires_reconciliation'] = False
        merged = merge_notice_events([base], [reconciled])
        self.assertEqual(len(merged), 1)
        self.assertFalse(merged[0]['requires_reconciliation'])
        self.assertEqual(
            merged[0]['fact_overrides']['facts.bid_deadline'],
            '2026-09-18T09:30:00+08:00',
        )

    def test_event_watch_keeps_only_active_ccgp_projects(self) -> None:
        records = [*copy.deepcopy(self.ccgp_records), *copy.deepcopy(self.institution_records)]
        active = active_ccgp_project_numbers(
            records,
            datetime.fromisoformat('2026-09-18T12:00:00+08:00'),
        )
        self.assertIn('TJBH-2026-A-0052', active)
        self.assertNotIn('XCSD-2026-A-641', active)
        self.assertNotIn('tjmugh_20260805_030326488', active)


if __name__ == '__main__':
    unittest.main()
