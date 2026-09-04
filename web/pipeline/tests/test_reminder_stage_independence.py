from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class ReminderStageIndependenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private_api = (WEB_ROOT / "api" / "_privateCore.js").read_text(encoding="utf-8")
        cls.today = (WEB_ROOT / "src" / "pages" / "TodayPage.tsx").read_text(encoding="utf-8")
        cls.detail = (WEB_ROOT / "src" / "pages" / "OpportunityDetailPage.tsx").read_text(encoding="utf-8")
        cls.followup_card = (WEB_ROOT / "src" / "components" / "opportunity" / "FollowupCard.tsx").read_text(encoding="utf-8")
        cls.remind_modal = (WEB_ROOT / "src" / "components" / "followup" / "RemindModal.tsx").read_text(encoding="utf-8")
        cls.local_store = (WEB_ROOT / "src" / "services" / "localFollowupStore.ts").read_text(encoding="utf-8")
        cls.local_reminders = (WEB_ROOT / "src" / "services" / "reminderApi.ts").read_text(encoding="utf-8")

    def test_server_accepts_reminder_without_forcing_monitor(self) -> None:
        self.assertIn("const REMINDER_TERMINAL_STATUSES = new Set(['WON', 'LOST', 'NOT_FIT', 'ARCHIVED'])", self.private_api)
        self.assertIn('REMINDER_TERMINAL_STATUSES.has(status) && reminderSupplied && remindAt', self.private_api)
        self.assertNotIn("status !== 'MONITOR' && reminderSupplied && remindAt", self.private_api)

    def test_server_preserves_reminder_across_non_terminal_stage_changes(self) -> None:
        self.assertIn('else if (REMINDER_TERMINAL_STATUSES.has(mutation.status)) nextReminder = null', self.private_api)
        self.assertNotIn("else if (mutation.status !== 'MONITOR') nextReminder = null", self.private_api)

    def test_due_reminder_inbox_is_independent_from_monitor(self) -> None:
        start = self.private_api.index('async function dueReminderRows')
        end = self.private_api.index('async function remindersRoute', start)
        block = self.private_api[start:end]
        self.assertIn("f.status NOT IN ('WON', 'LOST', 'NOT_FIT', 'ARCHIVED')", block)
        self.assertNotIn("f.status = 'MONITOR'", block)

    def test_today_reminder_preserves_current_status(self) -> None:
        self.assertIn('currentCard?.followup_status ?? \'NEW\'', self.today)
        self.assertIn('销售阶段保持不变', self.today)
        self.assertNotIn("updateStatus(id, 'MONITOR', { remind_at", self.today)
        self.assertIn('if (!card.remind_at) return false', self.today)

    def test_detail_reminder_preserves_current_status(self) -> None:
        self.assertIn('updateStatus(card.followup_status, {', self.detail)
        self.assertIn('销售阶段保持不变', self.detail)
        self.assertNotIn("updateStatus('MONITOR', { remind_at", self.detail)

    def test_monitor_remains_a_normal_sales_stage(self) -> None:
        self.assertNotIn("if (status === 'MONITOR')", self.followup_card)
        self.assertIn('“持续观察”只是销售阶段；提醒时间独立保存', self.followup_card)
        self.assertIn('设置提醒', self.followup_card)

    def test_terminal_sales_results_do_not_offer_new_reminders(self) -> None:
        self.assertIn('const REMINDER_TERMINAL_STATUSES = new Set<FollowupStatus>', self.followup_card)
        self.assertIn('const terminal = REMINDER_TERMINAL_STATUSES.has(card.followup_status)', self.followup_card)
        self.assertIn('const reminderAllowed = !terminal', self.followup_card)
        self.assertIn('当前项目已结束，不再新增后续提醒。', self.followup_card)
        self.assertIn('{reminderAllowed ? (', self.followup_card)

    def test_local_store_preserves_reminder_and_allows_new_with_reminder(self) -> None:
        self.assertIn('card.remind_at ?? existing?.remind_at ?? null', self.local_store)
        self.assertIn("entry.status !== 'NEW' || Boolean(entry.remind_at)", self.local_store)
        self.assertIn('REMINDER_TERMINAL_STATUSES.has(card.followup_status)', self.local_store)

    def test_local_due_reminders_exclude_terminal_results(self) -> None:
        self.assertIn("const REMINDER_TERMINAL_STATUSES = new Set(['WON', 'LOST', 'NOT_FIT', 'ARCHIVED'])", self.local_reminders)
        self.assertIn('REMINDER_TERMINAL_STATUSES.has(entry.status)', self.local_reminders)

    def test_reminder_copy_explicitly_says_stage_is_unchanged(self) -> None:
        self.assertGreaterEqual(self.remind_modal.count('不会改变当前销售阶段'), 2)


if __name__ == '__main__':
    unittest.main()
