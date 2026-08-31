from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PIPELINE_ROOT / 'scripts' / 'sync_tianjin_plan.py'

spec = importlib.util.spec_from_file_location('sync_tianjin_plan', SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError('SYNC_TIANJIN_PLAN_IMPORT_FAILED')
sync_tianjin_plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_tianjin_plan)


class TianjinPlanSyncTests(unittest.TestCase):
    def write_plan(self, payload: dict) -> Path:
        handle = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.json',
            encoding='utf-8',
            delete=False,
        )
        with handle:
            json.dump(payload, handle, ensure_ascii=False)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def base_plan(self) -> dict:
        return {
            'schema_version': '0.1',
            'region': '天津',
            'keywords': ['医院', '医疗'],
            'notice_types': ['公开招标', '竞争性磋商'],
            'lookback_days': 3,
            'max_candidates': 12,
            'max_event_watch_projects': 30,
            'delay_seconds': 4.0,
        }

    def test_load_plan_accepts_safe_tianjin_defaults(self) -> None:
        plan = sync_tianjin_plan.load_plan(self.write_plan(self.base_plan()))
        self.assertEqual(plan['region'], '天津')
        self.assertEqual(plan['keywords'], ['医院', '医疗'])
        self.assertEqual(plan['notice_types'], ['公开招标', '竞争性磋商'])
        self.assertEqual(plan['lookback_days'], 3)
        self.assertEqual(plan['delay_seconds'], 4.0)

    def test_load_plan_rejects_notice_type_without_verified_adapter(self) -> None:
        payload = self.base_plan()
        payload['notice_types'] = ['询价公告']
        with self.assertRaisesRegex(ValueError, 'NOTICE_TYPE_UNSUPPORTED'):
            sync_tianjin_plan.load_plan(self.write_plan(payload))

    def test_load_plan_rejects_rate_limit_bypass_delay(self) -> None:
        payload = self.base_plan()
        payload['delay_seconds'] = 2.9
        with self.assertRaisesRegex(ValueError, 'DELAY_TOO_LOW'):
            sync_tianjin_plan.load_plan(self.write_plan(payload))

    def test_as_of_keeps_absolute_time_and_supports_shanghai_window(self) -> None:
        as_of = sync_tianjin_plan.parse_as_of('2026-08-31T23:30:00+08:00')
        self.assertEqual(as_of.astimezone(sync_tianjin_plan.SHANGHAI).date().isoformat(), '2026-08-31')

        utc_value = sync_tianjin_plan.parse_as_of('2026-08-31T15:30:00Z')
        self.assertEqual(utc_value.astimezone(sync_tianjin_plan.SHANGHAI).date().isoformat(), '2026-08-31')

    def test_parse_as_of_rejects_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, 'timezone'):
            sync_tianjin_plan.parse_as_of('2026-08-31T12:00:00')

    def test_default_plan_file_is_valid_and_rate_limited(self) -> None:
        plan = sync_tianjin_plan.load_plan(sync_tianjin_plan.DEFAULT_PLAN)
        self.assertEqual(plan['region'], '天津')
        self.assertGreaterEqual(plan['delay_seconds'], 3)
        self.assertGreaterEqual(len(plan['keywords']), 3)
        self.assertLessEqual(plan['max_candidates'], 50)

    def test_stable_id_is_same_for_same_detail_url_across_keywords(self) -> None:
        url = 'https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/example.htm'
        first = sync_tianjin_plan.stable_id('ccgp', url)
        second = sync_tianjin_plan.stable_id('ccgp', url)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith('ccgp_'))

    def test_parse_as_of_default_is_timezone_aware(self) -> None:
        value = sync_tianjin_plan.parse_as_of(None)
        self.assertIsNotNone(value.tzinfo)
        self.assertEqual(value.tzinfo, timezone.utc)


if __name__ == '__main__':
    unittest.main()
