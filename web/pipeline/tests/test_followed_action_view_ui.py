from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class FollowedActionViewUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = (WEB_ROOT / "src" / "pages" / "FollowedPage.tsx").read_text(encoding="utf-8")

    def test_structured_private_notes_are_presented_as_business_context(self) -> None:
        self.assertIn("const NEXT_ACTION_PREFIX = '下次行动：'", self.page)
        self.assertIn("const LOST_REASON_PREFIX = '未成交原因（当前用户判断）：'", self.page)
        self.assertIn("{ label: '下一步', text }", self.page)
        self.assertIn("{ label: '未成交复盘（私有）', text }", self.page)
        self.assertIn("下一步、结果与复盘均属于私有跟进数据", self.page)

    def test_generic_system_reminder_note_is_not_shown_as_user_note(self) -> None:
        self.assertIn("const GENERIC_REMINDER_NOTE = '设置下次跟进提醒；销售阶段保持不变。'", self.page)
        self.assertIn("if (!note || note === GENERIC_REMINDER_NOTE) return null", self.page)

    def test_action_view_prioritizes_due_then_scheduled_followups(self) -> None:
        self.assertIn("if (reminderIsDue(item)) return 0", self.page)
        self.assertIn("if (!CLOSED_STATUSES.has(item.followup_status) && item.remind_at) return 1", self.page)
        self.assertIn("if (ACTIVE_STATUSES.has(item.followup_status)) return 2", self.page)
        self.assertIn("if (item.followup_status === 'MONITOR') return 3", self.page)
        self.assertIn("return leftReminder - rightReminder", self.page)
        self.assertIn("[...filteredItems].sort(compareForActionView)", self.page)

    def test_due_filter_and_metric_use_same_private_reminder_semantics(self) -> None:
        self.assertIn("type PipelineFilter = 'ALL' | 'DUE'", self.page)
        self.assertIn("if (filter === 'DUE') return reminderIsDue(item)", self.page)
        self.assertIn("due: statusIndex.filter((item) => reminderIsDue(item)).length", self.page)
        self.assertIn("['DUE', '待处理']", self.page)
        self.assertIn("['待处理', metrics.due]", self.page)

    def test_followed_card_distinguishes_due_and_future_next_time(self) -> None:
        self.assertIn('已到期', self.page)
        self.assertIn('已安排', self.page)
        self.assertIn("{due ? '到期时间' : '下次时间'}", self.page)
        self.assertNotIn('最近备注：{item.latest_note}', self.page)
        self.assertIn('搜索已加载的医院、项目、产品、下一步、备注...', self.page)


if __name__ == '__main__':
    unittest.main()
