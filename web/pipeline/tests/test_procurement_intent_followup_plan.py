from __future__ import annotations

import unittest
from datetime import datetime, timezone

from medical_channel_pipeline.procurement_intent_followup_plan import (
    MAX_CCGP_KEYWORDS,
    MAX_DIRECTED_TASKS,
    build_procurement_intent_followup_plan,
)
from medical_channel_pipeline.tjzyefy_procurement_intent import (
    OFFICIAL_FOLLOWUP_SOURCE_CEB,
    OFFICIAL_FOLLOWUP_SOURCE_PREFIX,
    OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC,
)

AS_OF = datetime(2026, 9, 5, tzinfo=timezone.utc)


def intent(
    opportunity_id: str,
    *,
    source: str | None,
    product: str = '空气压力治疗仪（淋巴水肿专用）',
    published_at: str = '2026-08-04',
    lifecycle: str = 'PROCUREMENT_INTENT',
) -> dict:
    flags = [] if source is None else [f'{OFFICIAL_FOLLOWUP_SOURCE_PREFIX}{source}']
    return {
        'opportunity_id': opportunity_id,
        'facts': {
            'lifecycle_state': lifecycle,
            'published_at': published_at,
            'project_name': f'采购意向公告（2026年44号）-{product}采购项目',
            'buyer_name': '天津中医药大学第二附属医院',
            'product_items': [{'raw_name': product}],
        },
        'quality_flags': flags,
    }


class ProcurementIntentFollowupPlanTests(unittest.TestCase):
    def test_tianjin_gpc_hint_routes_only_to_existing_ccgp_discovery(self) -> None:
        plan = build_procurement_intent_followup_plan(
            [intent('intent-1', source=OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC)],
            as_of=AS_OF,
        )
        self.assertEqual(plan['ccgp_keywords'], ['空气压力治疗仪（淋巴水肿专用）'])
        self.assertEqual(plan['ready_task_count'], 1)
        self.assertEqual(plan['unsupported_task_count'], 0)
        task = plan['tasks'][0]
        self.assertEqual(task['execution_adapter'], 'CCGP_QUERY')
        self.assertEqual(task['status'], 'READY')
        self.assertNotIn('url', task)
        self.assertNotIn('lineage', task)
        self.assertNotIn('followup_status', task)

    def test_ceb_hint_is_preserved_but_never_executed_without_verified_adapter(self) -> None:
        plan = build_procurement_intent_followup_plan(
            [intent('intent-2', source=OFFICIAL_FOLLOWUP_SOURCE_CEB)],
            as_of=AS_OF,
        )
        self.assertEqual(plan['ccgp_keywords'], [])
        self.assertEqual(plan['ready_task_count'], 0)
        self.assertEqual(plan['unsupported_task_count'], 1)
        task = plan['tasks'][0]
        self.assertIsNone(task['execution_adapter'])
        self.assertEqual(task['status'], 'UNSUPPORTED_SOURCE_ADAPTER')

    def test_no_official_source_flag_means_no_directed_task(self) -> None:
        plan = build_procurement_intent_followup_plan(
            [intent('intent-3', source=None)],
            as_of=AS_OF,
        )
        self.assertEqual(plan['tasks'], [])
        self.assertEqual(plan['ccgp_keywords'], [])

    def test_non_intent_and_stale_or_future_records_are_ignored(self) -> None:
        rows = [
            intent('formal', source=OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC, lifecycle='OPEN_BID'),
            intent('stale', source=OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC, published_at='2026-01-01'),
            intent('future', source=OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC, published_at='2026-09-06'),
        ]
        plan = build_procurement_intent_followup_plan(rows, as_of=AS_OF)
        self.assertEqual(plan['tasks'], [])

    def test_task_and_keyword_caps_bound_network_expansion(self) -> None:
        rows = [
            intent(
                f'intent-{index}',
                source=OFFICIAL_FOLLOWUP_SOURCE_TIANJIN_GPC,
                product=f'定向设备{index}',
                published_at='2026-09-01',
            )
            for index in range(12)
        ]
        plan = build_procurement_intent_followup_plan(rows, as_of=AS_OF)
        self.assertLessEqual(plan['task_count'], MAX_DIRECTED_TASKS)
        self.assertLessEqual(len(plan['ccgp_keywords']), MAX_CCGP_KEYWORDS)
        self.assertEqual(plan['policy']['maximum_tasks'], MAX_DIRECTED_TASKS)
        self.assertEqual(plan['policy']['maximum_ccgp_keywords'], MAX_CCGP_KEYWORDS)

    def test_timezone_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, 'TIMEZONE_REQUIRED'):
            build_procurement_intent_followup_plan([], as_of=datetime(2026, 9, 5))


if __name__ == '__main__':
    unittest.main()
