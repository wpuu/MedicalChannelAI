from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class PrivateOutcomeSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile_api = (WEB_ROOT / "api" / "profile.js").read_text(encoding="utf-8")
        cls.client = (WEB_ROOT / "src" / "services" / "outcomeSummaryApi.ts").read_text(encoding="utf-8")
        cls.card = (WEB_ROOT / "src" / "components" / "followup" / "OutcomeSummaryCard.tsx").read_text(encoding="utf-8")
        cls.followed = (WEB_ROOT / "src" / "pages" / "FollowedPage.tsx").read_text(encoding="utf-8")

    def test_server_summary_is_current_account_private_only(self) -> None:
        start = self.profile_api.index("async function outcomeSummaryRoute")
        end = self.profile_api.index("\n\nasync function publicHistoryRoute", start)
        block = self.profile_api[start:end]
        self.assertIn("FROM private_followups f", block)
        self.assertIn("private_followup_events", block)
        self.assertIn("f.user_id = ${user.id}", block)
        self.assertIn("f.organization_id = ${user.organization_id}", block)
        self.assertNotIn("publicOpportunityHistory", block)
        self.assertNotIn("public_opportunities", block)
        self.assertNotIn("loadVerifiedSnapshot", block)

    def test_summary_fails_closed_instead_of_returning_truncated_statistics(self) -> None:
        self.assertIn("LIMIT 5001", self.profile_api)
        self.assertIn("OUTCOME_SUMMARY_TRUNCATED", self.profile_api)
        self.assertIn("rows.length > 5000", self.profile_api)

    def test_controlled_win_and_loss_reviews_survive_later_freeform_notes(self) -> None:
        self.assertIn("const WON_REASON_NOTE_PREFIX = '成交复盘（当前用户判断）：'", self.profile_api)
        self.assertIn("const LOST_REASON_NOTE_PREFIX = '未成交原因（当前用户判断）：'", self.profile_api)
        self.assertIn("const wonNotePattern = `${WON_REASON_NOTE_PREFIX}%`", self.profile_api)
        self.assertIn("const lostNotePattern = `${LOST_REASON_NOTE_PREFIX}%`", self.profile_api)
        self.assertIn("WON_REASON_LABEL_TO_CODE.get(label)", self.profile_api)
        self.assertIn("LOST_REASON_LABEL_TO_CODE.get(label)", self.profile_api)
        self.assertIn("历史未结构化", self.card)

    def test_client_validates_server_math_and_supports_local_demo(self) -> None:
        self.assertIn("PRIVATE_OUTCOME_SUMMARY", self.client)
        self.assertIn("root.total_terminal !== root.won + root.lost + root.not_fit", self.client)
        self.assertIn("root.decided_count !== root.won + root.lost", self.client)
        self.assertIn("won_reason_counts", self.client)
        self.assertIn("unclassified_won", self.client)
        self.assertIn("if (!isApiMode) return localSummary()", self.client)
        self.assertIn("/profile?route=outcome-summary", self.client)

    def test_client_rejects_duplicate_or_internally_inconsistent_reason_counts(self) -> None:
        self.assertIn("const seen = new Set<string>()", self.client)
        self.assertIn("seen.has(row.code)", self.client)
        self.assertIn("function reasonCountTotal", self.client)
        self.assertIn("reasonCountTotal(wonReasonCounts) + root.unclassified_won !== root.won", self.client)
        self.assertIn("reasonCountTotal(lostReasonCounts) + root.unclassified_lost !== root.lost", self.client)
        self.assertIn("reasonCountTotal(notFitReasonCounts) + root.unclassified_not_fit !== root.not_fit", self.client)

    def test_followed_page_surfaces_private_review_without_claiming_public_learning(self) -> None:
        self.assertIn("<OutcomeSummaryCard />", self.followed)
        self.assertIn("只统计当前账号已结束的私有跟进结果", self.card)
        self.assertIn("不写入公开商机事实", self.card)
        self.assertIn("不自动改变公共机会排序", self.card)
        self.assertIn("已决成交率", self.card)
        self.assertIn("已成交 ÷（已成交 + 未成交）", self.card)
        self.assertIn("成交常见因素（私有判断）", self.card)
        self.assertIn("未成交主要原因", self.card)

    def test_small_sample_is_recorded_without_claiming_a_business_rule(self) -> None:
        self.assertIn("const MIN_REVIEW_SAMPLE = 5", self.card)
        self.assertIn("summary.decided_count < MIN_REVIEW_SAMPLE", self.card)
        self.assertIn("暂不足以判断成交规律", self.card)
        self.assertIn("当前数字只用于记录", self.card)
        self.assertIn("不代表因果关系", self.card)
        self.assertIn("不会自动修改公开事实或公共机会排序", self.card)


if __name__ == "__main__":
    unittest.main()
