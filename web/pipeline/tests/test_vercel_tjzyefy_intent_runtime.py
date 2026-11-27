from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from test_daily_collector_recovery import collector_modules


class VercelTjzyefyIntentRuntimeTests(unittest.TestCase):
    def test_daily_source_is_after_hospitals_before_regional(self):
        with collector_modules() as queue:
            stages = queue.runtime.STAGE_ORDER
            self.assertEqual(stages.count("tjzyefy_intent"), 1)
            self.assertLess(stages.index("tjfch"), stages.index("tjzyefy_intent"))
            self.assertLess(stages.index("tjzyefy_intent"), stages.index("regional_bj"))

    def test_medical_intent_is_verified_pre_market_signal(self):
        with collector_modules() as queue:
            rt = queue.runtime
            title = "采购意向公告（2026年76号）-非接触眼压计等医疗设备采购项目"
            index = '<a href="/system/2026/11/13/030203150.shtml">' + title + '</a>'
            body = ('<html><body><h1>' + title + '</h1>'
                    '<div>2026-11-13 10:05 发布人：采购办公室</div>'
                    '<p>天津中医药大学第二附属医院</p>'
                    '<p>我院将于近期对天津中医药大学第二附属医院非接触眼压计等医疗设备'
                    '采购项目进行采购，欢迎各位有资质的供应商咨询。'
                    '预计采购时间2026年12月。联系电话：022-60637522 联系人：潘老师。</p>'
                    '</body></html>')
            with patch.object(rt, "_cached_list", return_value=([], False)), \
                 patch.object(rt, "fetch_tjzyefy_intent_page_with_retry",
                              side_effect=[index, body]) as fetch, \
                 patch.object(rt.time, "sleep") as sleep, \
                 patch.object(rt, "_cache_set") as write:
                result = rt._run_tjzyefy_intent(MagicMock(), {
                    "cycle_as_of": "2026-11-27T08:20:00+08:00"
                })
                self.assertEqual(result["new_verified_record_count"], 1)
                self.assertEqual(result["publish_gate_reason"], "PASS")
                self.assertEqual(fetch.call_count, 2)
                sleep.assert_called_once_with(3.0)
                write.assert_called_once()
                records = write.call_args.args[2]
                self.assertEqual(records[0]["facts"]["lifecycle_state"], "PROCUREMENT_INTENT")
                self.assertIsNone(records[0]["facts"]["registration_deadline"])

    def test_unresolved_detail_failure_never_writes_canonical(self):
        with collector_modules() as queue:
            rt = queue.runtime
            title = "采购意向公告（2026年76号）-非接触眼压计等医疗设备采购项目"
            index = '<a href="/system/2026/11/13/030203150.shtml">' + title + '</a>'
            with patch.object(rt, "_cached_list", return_value=([], False)), \
                 patch.object(rt, "fetch_tjzyefy_intent_page_with_retry",
                              side_effect=[index, RuntimeError("TJZYEFY_HTTP_404")]), \
                 patch.object(rt.time, "sleep"), \
                 patch.object(rt, "_cache_set") as write:
                with self.assertRaisesRegex(rt.CollectorStageBlocked,
                                             "TJZYEFY_INTENT_VERIFICATION_INCOMPLETE:1"):
                    rt._run_tjzyefy_intent(MagicMock(), {
                        "cycle_as_of": "2026-11-27T08:20:00+08:00"
                    })
                write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
