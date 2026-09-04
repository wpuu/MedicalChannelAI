import json
from pathlib import Path
import unittest


WEB_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = WEB_ROOT / "pipeline" / "data"


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

    def test_today_exposes_intent_followup_without_loading_full_pool(self):
        today = (WEB_ROOT / "src/pages/TodayPage.tsx").read_text(encoding="utf-8")

        self.assertIn("navigate('/intent-followup')", today)
        self.assertIn("采购意向跟进", today)
        self.assertIn("按需加载完整商机池，核查采购意向及可能的后续正式公告", today)
        self.assertIn("todayActionsService.getTodayActions()", today)
        self.assertNotIn("getTodayActions({ hydrateFollowups: false })", today)
        self.assertNotIn("getTodayActions({ loadProfile: 'FULL_POOL'", today)

    def test_today_light_summary_surfaces_formal_window_without_private_context(self):
        helper = (WEB_ROOT / "api/_procurementIntentFollowup.js").read_text(encoding="utf-8")
        entry = (WEB_ROOT / "api/private.js").read_text(encoding="utf-8")
        adapter = (WEB_ROOT / "src/services/ApiTodayActionsService.ts").read_text(encoding="utf-8")
        metric = (WEB_ROOT / "src/components/today/MetricCards.tsx").read_text(encoding="utf-8")

        self.assertIn("procurementIntentFollowupSummary(fullPool)", entry)
        self.assertIn("procurement_intent_followup_summary", entry)
        self.assertIn("procurement_intent_followup_summary: data.procurement_intent_followup_summary", adapter)
        self.assertIn("intents_with_formal_successor", metric)
        self.assertIn("条采购意向已出现可能的正式窗口", metric)
        self.assertIn("只依据公开事实自动提示", metric)
        self.assertIn("不代表官方确认同一项目", metric)
        self.assertNotIn("customer_context", helper)
        self.assertNotIn("hospital_relationship", helper)
        self.assertNotIn("target_hospital", helper)
        self.assertNotIn("matching_product_capabilities", helper)
        self.assertNotIn("priority", helper)

    def test_successor_linkage_is_conservative_and_explained_as_candidate_only(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("function successorCandidates", page)
        self.assertIn("institutionKey(candidate) === institution", page)
        self.assertIn("item.published >= intentPublished", page)
        self.assertIn("item.terms.length > 0 || item.subjectMatch", page)
        self.assertIn("GENERIC_PRODUCT_TERMS", page)
        self.assertIn("GENERIC_PROJECT_SUBJECTS", page)
        self.assertIn("Math.min(leftTerm.length, rightTerm.length) >= 4", page)
        self.assertIn("function projectSubject", page)
        self.assertIn("intentSubject === candidateSubject", page)
        self.assertIn("结构化产品重合，或去掉采购单位和采购意向公告前缀后的项目主题精确一致", page)
        self.assertIn("不是官方声明为同一项目", page)
        self.assertIn("最终仍需人工核对项目编号、科室、产品和公告原文", page)
        self.assertIn("关联候选不会改变公开优先级或中标判断", page)
        self.assertIn("这不代表项目取消或没有后续", page)
        self.assertIn("不要把“未发现关联”当成业务结论", page)

    def test_real_lung_function_lineage_uses_verified_canonical_history_not_active_pool(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")
        intent_records = json.loads(
            (DATA_ROOT / "tianjin_live_tjzyefy_intent_records.json").read_text(encoding="utf-8")
        )
        ccgp_records = json.loads(
            (DATA_ROOT / "tianjin_live_ccgp_records.json").read_text(encoding="utf-8")
        )
        intents = {record["opportunity_id"]: record for record in intent_records}
        formal_records = {record["opportunity_id"]: record for record in ccgp_records}
        intent = intents["tjzyefy_intent_20260804_030195986"]
        formal = formal_records["ccgp_bf77073fba23504b"]

        self.assertEqual(intent["source"]["url"], "https://www.tjzyefy.com/system/2026/08/04/030195986.shtml")
        self.assertEqual(formal["source"]["url"], "https://www.ccgp.gov.cn/cggg/dfgg/gkzb/202609/t20260902_27255226.htm")
        self.assertEqual(intent["facts"]["buyer_name"], "天津中医药大学第二附属医院")
        self.assertEqual(formal["facts"]["buyer_name"], "天津中医药大学第二附属医院")
        self.assertEqual(intent["facts"]["published_at"], "2026-08-04")
        self.assertEqual(formal["facts"]["published_at"], "2026-09-02")
        self.assertIn("肺功能仪等医疗设备采购项目", intent["facts"]["project_name"])
        self.assertIn("肺功能仪等医疗设备采购项目", formal["facts"]["project_name"])
        self.assertEqual(formal["facts"]["product_items"], [])
        self.assertEqual(formal["facts"]["registration_deadline"], "2026-09-09T17:00:00+08:00")
        self.assertEqual(formal["facts"]["bid_deadline"], "2026-09-23T08:30:00+08:00")
        self.assertIn("subject.replace(/^采购意向公告", page)
        self.assertIn("intentSubject === candidateSubject", page)
        self.assertIn("项目主题精确一致", page)

    def test_formal_successor_is_promoted_ahead_of_phase_only_monitoring(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("successorDiff = Number(right.successors.length > 0) - Number(left.successors.length > 0)", page)
        self.assertIn("if (successorDiff !== 0) return successorDiff", page)
        self.assertIn("已出现可能的正式窗口 · 需人工核对", page)
        self.assertIn("已出现 ${successors.length} 条可能的正式窗口（需核对）", page)
        self.assertIn("function formalDeadlineSummary", page)
        self.assertIn("报名截止", page)
        self.assertIn("投标/响应截止", page)

    def test_intents_are_prioritized_by_expected_procurement_window_phase(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("expectedProcurementWindowPhase", page)
        self.assertIn("if (phase === 'AFTER') return 0", page)
        self.assertIn("if (phase === 'ACTIVE') return 1", page)
        self.assertIn("if (phase === 'BEFORE') return 2", page)
        self.assertIn("预计采购月份已过，优先核查后续公告", page)
        self.assertIn("已进入预计采购月份，重点盯正式公告", page)
        self.assertIn("预计采购月份未到，继续提前布局", page)

    def test_phase_actions_are_operational_but_do_not_invent_business_outcomes(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("function phaseActions", page)
        self.assertIn("已出现满足保守关联规则的后续正式商机候选", page)
        self.assertIn("只有人工核对确认后再记录实际业务动作", page)
        self.assertIn("候选关联本身不等于官方确认", page)
        self.assertIn("先查医院官网、政府采购/招标等已核验公开源", page)
        self.assertIn("公开源仍未发现时，可使用公告公开电话确认项目是否延期", page)
        self.assertIn("把正式公告核查提升为当前任务", page)
        self.assertIn("同步确认厂家/渠道资源", page)
        self.assertIn("不把采购意向当成已经开放的订单", page)
        self.assertIn("不把“没有搜到”解释成项目取消", page)
        self.assertIn("只记录对方明确回复", page)

    def test_public_phone_is_one_tap_but_never_auto_marks_contacted(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("function telHref", page)
        self.assertIn("intent.facts.official_contact?.phone", page)
        self.assertIn("公告公开电话", page)
        self.assertIn("拨号只打开电话，不会自动记录为已联系", page)
        self.assertIn("实际沟通结果仍由用户明确确认", page)
        self.assertNotIn("status: 'CONTACTED'", page)

    def test_intent_followup_requires_explicit_user_action(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("const startFollowup = async", page)
        self.assertIn("onClick={() => void startFollowup(intent, 'INTENT')}", page)
        self.assertIn("updateFollowup(card.opportunity_id, { status: 'REVIEWING' })", page)
        self.assertIn("加入采购意向跟进", page)
        self.assertIn("提醒时间和下一步行动由你确认后再设置", page)
        self.assertNotIn("status: 'CONTACTED'", page)

    def test_formal_candidate_can_be_explicitly_followed_without_confirming_lineage(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("onClick={() => void startFollowup(card, 'FORMAL')}", page)
        self.assertIn("加入正式项目跟进", page)
        self.assertIn("正式项目已加入我的跟进", page)
        self.assertIn("不会把采购意向与正式项目自动认定为同一项目", page)
        self.assertIn("只表示你决定跟这条已核验公开商机", page)
        self.assertIn("不会把候选关联自动升级为“官方确认同一项目”", page)
        self.assertNotIn("status: 'CONTACTED'", page)

    def test_next_action_reuses_existing_reminder_and_preserves_current_stage(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("import { RemindModal }", page)
        self.assertIn("const [remindId, setRemindId]", page)
        self.assertIn("const saveNextAction = async", page)
        self.assertIn("status: card.followup_status", page)
        self.assertIn("remind_at: remindAt", page)
        self.assertIn("note: `下次行动：${nextAction}`", page)
        self.assertIn("当前销售阶段保持不变", page)
        self.assertIn("安排正式项目下一步", page)
        self.assertIn("open={Boolean(remindId)}", page)
        self.assertNotIn("status: 'CONTACTED'", page)

    def test_formal_reminder_uses_earliest_future_verified_deadline_and_stays_before_it(self):
        page = (WEB_ROOT / "src/pages/ProcurementIntentFollowupPage.tsx").read_text(encoding="utf-8")

        self.assertIn("function formalReminderConstraint", page)
        self.assertIn("addExact(card.facts.registration_deadline, '报名截止')", page)
        self.assertIn("addExact(card.facts.bid_deadline, '投标/响应截止')", page)
        self.assertIn("candidates.sort((left, right) => left.at - right.at)", page)
        self.assertIn("const maxDate = previousIsoDate(earliest.date)", page)
        self.assertIn("canSchedule: maxDate >= isoDaysFromNow(1)", page)
        self.assertIn("maxDate={reminderConstraint?.canSchedule ? reminderConstraint.maxDate : null}", page)
        self.assertIn("没有安全的未来提醒日；请现在处理，不再延后安排", page)
        self.assertIn("Asia/Shanghai", page)

    def test_shared_reminder_modal_bounds_only_callers_that_supply_verified_max_date(self):
        modal = (WEB_ROOT / "src/components/followup/RemindModal.tsx").read_text(encoding="utf-8")

        self.assertIn("maxDate?: string | null", modal)
        self.assertIn("deadlineHint?: string | null", modal)
        self.assertIn(".filter((item) => isOnOrBefore(item.value, maxDate))", modal)
        self.assertIn("max={maxDate ?? undefined}", modal)
        self.assertIn("selectedWithinDeadline", modal)
        self.assertIn("disabled={!remindAt || !normalizedNextAction}", modal)
        self.assertIn("避免把下一步安排到已核验正式窗口之后", modal)
        self.assertIn("只使用已核验官方截止时间，不会自行推算新的官方截止日期", modal)


if __name__ == "__main__":
    unittest.main()