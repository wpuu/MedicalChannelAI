from __future__ import annotations

import unittest
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[2]
OUTREACH = WEB_ROOT / "src" / "components" / "followup" / "OutreachDrawer.tsx"


class OutreachFollowupClosureUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = OUTREACH.read_text(encoding="utf-8")

    def test_copying_draft_never_fakes_contacted_business_state(self) -> None:
        start = self.source.index('const copyDraft = async () => {')
        end = self.source.index('\n\n  const recordContacted = async () => {', start)
        block = self.source[start:end]
        self.assertIn('navigator.clipboard.writeText(sendableDraft)', block)
        self.assertNotIn('updateFollowup', block)
        self.assertNotIn("status: 'CONTACTED'", block)

    def test_contacted_state_requires_explicit_user_action_and_persists_followup(self) -> None:
        start = self.source.index('const recordContacted = async () => {')
        end = self.source.index('\n\n  return (', start)
        block = self.source[start:end]
        self.assertIn('todayActionsService.updateFollowup(opportunityId', block)
        self.assertIn("status: 'CONTACTED'", block)
        self.assertIn('从沟通草稿入口确认已完成联系。', block)
        self.assertIn('navigate(`/followed?focus=${encodeURIComponent(opportunityId)}`)', block)
        self.assertIn('已联系，已记入“我的跟进”', block)

    def test_drawer_explains_copy_and_contact_confirmation_are_separate(self) -> None:
        self.assertIn('实际联系后再确认写入跟进台账', self.source)
        self.assertIn('复制内容', self.source)
        self.assertIn('已联系，记入跟进', self.source)
        self.assertIn('onClick={() => void recordContacted()}', self.source)


if __name__ == "__main__":
    unittest.main()
