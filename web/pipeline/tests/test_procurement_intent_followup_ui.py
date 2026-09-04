from pathlib import Path
import unittest


WEB_ROOT = Path(__file__).resolve().parents[2]


class ProcurementIntentFollowupUiTests(unittest.TestCase):
    def test_workspace_is_routed_without_new_backend_surface(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")
        app = (WEB_ROOT / "src/App.tsx").read_text(encoding="utf-8")
        notice = (WEB_ROOT / "src/components/shared/PreMarketSignalNotice.tsx").read_text(encoding="utf-8")

        self.assertIn("getTodayActions({ hydrateFollowups: false })", page)
        self.assertNotIn("/api/", page)
        self.assertIn('path="/intent-followup"', app)
        self.assertIn("ProcurementIntentFollowupPage", app)
        self.assertIn('to="/intent-followup"', notice)
        self.assertIn("核查可能的后续正式项目", notice)

    def test_successor_linkage_is_conservative_and_explained_as_candidate_only(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("function successorCandidates", page)
        self.assertIn("institutionKey(candidate) === institution", page)
        self.assertIn("item.published >= intentPublished", page)
        self.assertIn("item.terms.length > 0", page)
        self.assertIn("GENERIC_PRODUCT_TERMS", page)
        self.assertIn("Math.min(leftTerm.length, rightTerm.length) >= 4", page)
        self.assertIn("同一采购单位、明确产品重合、后续公告发布时间不早于采购意向", page)
        self.assertIn("不是官方声明为同一项目", page)
        self.assertIn("最终仍需人工核对项目编号、科室、产品和公告原文", page)
        self.assertIn("关联候选不会改变公开优先级或中标判断", page)
        self.assertIn("这不代表项目取消或没有后续", page)
        self.assertIn("不要把“未发现关联”当成业务结论", page)

    def test_intents_are_prioritized_by_expected_procurement_window_phase(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("expectedProcurementWindowPhase", page)
        self.assertIn("if (phase === 'AFTER') return 0", page)
        self.assertIn("if (phase === 'ACTIVE') return 1", page)
        self.assertIn("if (phase === 'BEFORE') return 2", page)
        self.assertIn("预计采购月份已过，优先核查后续公告", page)
        self.assertIn("已进入预计采购月份，重点盯正式公告", page)
        self.assertIn("预计采购月份未到，继续提前布局", page)

    def test_followup_requires_explicit_user_action_and_does_not_invent_reminder(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("const startFollowup = async", page)
        self.assertIn("onClick={() => void startFollowup(intent)}", page)
        self.assertIn("updateFollowup(intent.opportunity_id, { status: 'REVIEWING' })", page)
        self.assertIn("加入我的跟进", page)
        self.assertIn("提醒时间和下一步行动由你确认后再设置", page)
        self.assertNotIn("remind_at:", page)
        self.assertNotIn("status: 'CONTACTED'", page)


if __name__ == "__main__":
    unittest.main()
