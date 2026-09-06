from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from medical_channel_pipeline.procurement_intent_followup_plan import (
    build_procurement_intent_followup_plan,
)
from medical_channel_pipeline.state import merge_canonical_records
from medical_channel_pipeline.tjzyefy_procurement_intent import (
    OFFICIAL_FOLLOWUP_SOURCE_CEB,
    OFFICIAL_FOLLOWUP_SOURCE_PREFIX,
    OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC,
)

ROOT = Path(__file__).resolve().parents[1]
INTENTS_PATH = ROOT / 'data' / 'tianjin_live_tjzyefy_intent_records.json'
AS_OF = datetime(2026, 9, 5, tzinfo=timezone.utc)

OFFICIAL_ROUTING = {
    'tjzyefy_intent_20260804_030195992': OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC,
    'tjzyefy_intent_20260804_030195991': OFFICIAL_FOLLOWUP_SOURCE_CEB,
    'tjzyefy_intent_20260804_030195988': OFFICIAL_FOLLOWUP_SOURCE_CEB,
    'tjzyefy_intent_20260804_030195986': OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC,
}


def _without_followup_flags(record: dict) -> dict:
    result = copy.deepcopy(record)
    flags = result.get('quality_flags') or []
    result['quality_flags'] = [
        flag
        for flag in flags
        if not str(flag).startswith(OFFICIAL_FOLLOWUP_SOURCE_PREFIX)
    ]
    return result


def _with_official_source(record: dict, source: str) -> dict:
    result = _without_followup_flags(record)
    result.setdefault('quality_flags', []).append(
        f'{OFFICIAL_FOLLOWUP_SOURCE_PREFIX}{source}'
    )
    return result


class ProcurementIntentFollowupMaterializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical = json.loads(INTENTS_PATH.read_text(encoding='utf-8'))
        cls.by_id = {
            record['opportunity_id']: record
            for record in cls.canonical
            if record.get('opportunity_id') in OFFICIAL_ROUTING
        }
        if set(cls.by_id) != set(OFFICIAL_ROUTING):
            raise AssertionError('REAL_TJZYEFY_INTENT_FIXTURE_INCOMPLETE')

    def test_quality_flag_only_refresh_replaces_same_intent_without_duplicate(self) -> None:
        opportunity_id = 'tjzyefy_intent_20260804_030195992'
        legacy = _without_followup_flags(self.by_id[opportunity_id])
        refreshed = _with_official_source(
            self.by_id[opportunity_id],
            OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC,
        )
        refreshed['source']['observed_at'] = '2026-09-05T04:01:46+00:00'

        merged = merge_canonical_records([legacy], [refreshed])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['opportunity_id'], opportunity_id)
        self.assertEqual(merged[0]['facts'], legacy['facts'])
        self.assertEqual(
            merged[0]['source']['observed_at'],
            '2026-09-05T04:01:46+00:00',
        )
        self.assertIn(
            f'{OFFICIAL_FOLLOWUP_SOURCE_PREFIX}{OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC}',
            merged[0]['quality_flags'],
        )
        self.assertIn(
            'EXPECTED_PROCUREMENT_MONTH_WINDOW_UNSTRUCTURED',
            merged[0]['quality_flags'],
        )

    def test_real_four_intents_route_by_official_live_probe_outcome(self) -> None:
        records = [
            _with_official_source(self.by_id[opportunity_id], source)
            for opportunity_id, source in OFFICIAL_ROUTING.items()
        ]

        plan = build_procurement_intent_followup_plan(records, as_of=AS_OF)
        tasks = {
            task['intent_opportunity_id']: task
            for task in plan['tasks']
        }

        self.assertEqual(plan['task_count'], 4)
        self.assertEqual(plan['ready_task_count'], 2)
        self.assertEqual(plan['unsupported_task_count'], 2)
        self.assertEqual(plan['ccgp_keywords'], ['云影像服务', '肺功能仪'])

        for opportunity_id, source in OFFICIAL_ROUTING.items():
            task = tasks[opportunity_id]
            self.assertEqual(task['official_followup_source'], source)
            if source == OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC:
                self.assertEqual(task['execution_adapter'], 'CCGP_QUERY')
                self.assertEqual(task['status'], 'READY')
            else:
                self.assertIsNone(task['execution_adapter'])
                self.assertEqual(task['status'], 'UNSUPPORTED_SOURCE_ADAPTER')
            self.assertNotIn('url', task)
            self.assertNotIn('lineage', task)
            self.assertNotIn('followup_status', task)


if __name__ == '__main__':
    unittest.main()
