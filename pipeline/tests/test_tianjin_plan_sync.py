from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace

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

    def test_load_plan_deduplicates_keywords_before_network_queries(self) -> None:
        payload = self.base_plan()
        payload['keywords'] = ['医院', ' 医院 ', '医疗', '医疗']
        plan = sync_tianjin_plan.load_plan(self.write_plan(payload))
        self.assertEqual(plan['keywords'], ['医院', '医疗'])

    def test_load_plan_rejects_non_tianjin_region(self) -> None:
        payload = self.base_plan()
        payload['region'] = '北京'
        with self.assertRaisesRegex(ValueError, 'REGION_LOCKED'):
            sync_tianjin_plan.load_plan(self.write_plan(payload))

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

    def test_plan_date_window_uses_shanghai_calendar_days(self) -> None:
        as_of = sync_tianjin_plan.parse_as_of('2026-08-31T16:30:00Z')
        start_date, end_date = sync_tianjin_plan.plan_date_window(as_of, 3)
        self.assertEqual(start_date, '2026-08-30')
        self.assertEqual(end_date, '2026-09-01')

    def test_parse_as_of_rejects_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, 'timezone'):
            sync_tianjin_plan.parse_as_of('2026-08-31T12:00:00')

    def test_default_plan_file_is_valid_and_rate_limited(self) -> None:
        plan = sync_tianjin_plan.load_plan(sync_tianjin_plan.DEFAULT_PLAN)
        self.assertEqual(plan['region'], '天津')
        self.assertGreaterEqual(plan['delay_seconds'], 3)
        self.assertGreaterEqual(len(plan['keywords']), 3)
        self.assertLessEqual(plan['max_candidates'], 50)

    def test_same_detail_url_across_keywords_is_verified_once(self) -> None:
        shared = SimpleNamespace(
            detail_url='https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/shared.htm',
            published_at='2026-08-31',
            title='共享项目',
        )
        second = SimpleNamespace(
            detail_url='https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202608/second.htm',
            published_at='2026-08-31',
            title='第二项目',
        )
        discovered_by_url: dict[str, tuple[str, object]] = {}
        discovered_keywords: dict[str, set[str]] = {}

        sync_tianjin_plan.merge_discovered_candidates(
            discovered_by_url,
            discovered_keywords,
            keyword='医院',
            candidates=[('公开招标', shared)],
        )
        sync_tianjin_plan.merge_discovered_candidates(
            discovered_by_url,
            discovered_keywords,
            keyword='医疗',
            candidates=[('公开招标', shared), ('竞争性磋商', second)],
        )
        sync_tianjin_plan.merge_discovered_candidates(
            discovered_by_url,
            discovered_keywords,
            keyword='检验',
            candidates=[('公开招标', shared)],
        )

        self.assertEqual(len(discovered_by_url), 2)
        self.assertEqual(
            discovered_keywords[shared.detail_url],
            {'医院', '医疗', '检验'},
        )
        self.assertIs(discovered_by_url[shared.detail_url][1], shared)

    def test_parse_as_of_default_is_timezone_aware(self) -> None:
        value = sync_tianjin_plan.parse_as_of(None)
        self.assertIsNotNone(value.tzinfo)
        self.assertEqual(value.tzinfo, timezone.utc)


if __name__ == '__main__':
    unittest.main()
