from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]


class ReminderNextActionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.modal = (WEB_ROOT / "src" / "components" / "followup" / "RemindModal.tsx").read_text(encoding="utf-8")
        cls.today = (WEB_ROOT / "src" / "pages" / "TodayPage.tsx").read_text(encoding="utf-8")
        cls.detail = (WEB_ROOT / "src" / "pages" / "OpportunityDetailPage.tsx").read_text(encoding="utf-8")
        cls.reminder_api = (WEB_ROOT / "src" / "services" / "reminderApi.ts").read_text(encoding="utf-8")

    def test_reminder_collects_optional_next_action(self) -> None:
        self.assertIn('onConfirm: (remindAt: string, nextAction: string | null) => void', self.modal)
        self.assertIn('到时要做什么（可选）', self.modal)
        self.assertIn('再联系设备科，确认参数要求和厂家授权情况', self.modal)
        self.assertIn('maxLength={500}', self.modal)
        self.assertIn('nextAction.trim() || null', self.modal)

    def test_today_persists_next_action_as_private_followup_note(self) -> None:
        self.assertIn('onConfirm={(remindAt, nextAction) => {', self.today)
        self.assertIn('`下次行动：${nextAction}`', self.today)
        self.assertIn('remind_at: remindAt', self.today)

    def test_detail_persists_next_action_without_changing_stage(self) -> None:
        self.assertIn('onConfirm={(remindAt, nextAction) => {', self.detail)
        self.assertIn('updateStatus(card.followup_status, {', self.detail)
        self.assertIn('`下次行动：${nextAction}`', self.detail)

    def test_due_reminder_already_surfaces_latest_private_note(self) -> None:
        self.assertIn('note: latestNote', self.reminder_api)
        self.assertIn("entry.history.find((record) => Boolean(record.note?.trim()))", self.reminder_api)


if __name__ == '__main__':
    unittest.main()
