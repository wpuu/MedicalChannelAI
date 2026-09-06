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
        cls.panel = (WEB_ROOT / "src" / "components" / "today" / "DueRemindersPanel.tsx").read_text(encoding="utf-8")

    def test_reminder_requires_explicit_next_action(self) -> None:
        self.assertIn('onConfirm: (remindAt: string, nextAction: string) => void', self.modal)
        self.assertIn('const NEXT_ACTION_PRESETS = [', self.modal)
        self.assertIn('再次联系采购/设备科', self.modal)
        self.assertIn('确认产品参数与匹配情况', self.modal)
        self.assertIn('确认厂家/授权/供货能力', self.modal)
        self.assertIn('查看项目最新进展', self.modal)
        self.assertIn('disabled={!remindAt || !normalizedNextAction}', self.modal)
        self.assertIn('具体说明（必填，可直接修改快捷选项）', self.modal)
        self.assertIn('每个提醒都必须对应一个明确动作', self.modal)
        self.assertIn('maxLength={500}', self.modal)
        self.assertNotIn('nextAction: string | null', self.modal)
        self.assertNotIn('到时要做什么（可选）', self.modal)

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

    def test_due_panel_promotes_action_note_to_next_step(self) -> None:
        self.assertIn("text.startsWith('下次行动：')", self.panel)
        self.assertIn("{ label: '下一步', text: action }", self.panel)
        self.assertIn('{note.label}：{note.text}', self.panel)


if __name__ == '__main__':
    unittest.main()
