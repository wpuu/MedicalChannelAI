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
        end = self.source.index('\n\n  const goToFollowed = () => {', start)
        block = self.source[start:end]
        self.assertIn('navigator.clipboard.writeText(sendableDraft)', block)
        self.assertNotIn('updateFollowup', block)
        self.assertNotIn("status: 'CONTACTED'", block)

    def test_contacted_state_requires_explicit_user_action_and_does_not_auto_schedule(self) -> None:
        start = self.source.index('const recordContacted = async () => {')
        end = self.source.index('\n\n  const scheduleNextAction = async', start)
        block = self.source[start:end]
        self.assertIn('todayActionsService.updateFollowup(opportunityId', block)
        self.assertIn("status: 'CONTACTED'", block)
        self.assertIn('从沟通草稿入口确认已完成联系。', block)
        self.assertIn('setContactRecorded(true)', block)
        self.assertIn('已联系，已记入“我的跟进”', block)
        self.assertNotIn('remind_at:', block)
        self.assertNotIn('setRemindOpen(true)', block)
        self.assertNotIn("navigate('/followed')", block)

    def test_after_contact_user_can_choose_followed_or_explicit_next_action(self) -> None:
        self.assertIn('contactRecorded ? (', self.source)
        self.assertIn('先去我的跟进', self.source)
        self.assertIn('安排下一步', self.source)
        self.assertIn('onClick={() => setRemindOpen(true)}', self.source)
        self.assertIn("navigate('/followed')", self.source)
        self.assertNotIn('/followed?focus=', self.source)

    def test_scheduled_next_action_keeps_contacted_stage(self) -> None:
        start = self.source.index('const scheduleNextAction = async')
        end = self.source.index('\n\n  return (', start)
        block = self.source[start:end]
        self.assertIn("status: 'CONTACTED'", block)
        self.assertIn('remind_at: remindAt', block)
        self.assertIn('note: `下次行动：${nextAction}`', block)
        self.assertIn('下一步已安排，销售阶段仍为“已联系”', block)
        self.assertIn('goToFollowed()', block)
        self.assertIn('!contactRecorded', block)

    def test_contacted_bridge_reuses_required_next_action_modal(self) -> None:
        self.assertIn("import { RemindModal } from '@/components/followup/RemindModal'", self.source)
        self.assertIn('open={open && remindOpen && Boolean(opportunityId)}', self.source)
        self.assertIn('onConfirm={(remindAt, nextAction) => void scheduleNextAction(remindAt, nextAction)}', self.source)
        self.assertIn('只会增加私有下一步和提醒时间，不会再次改变销售阶段', self.source)

    def test_public_contact_quick_actions_only_use_verified_card_contact_fields(self) -> None:
        lookup_start = self.source.index('todayActionsService\n      .getOpportunity(opportunityId)')
        draft_start = self.source.index('void todayActionsService\n      .requestOutreachDraft', lookup_start)
        block = self.source[lookup_start:draft_start]
        self.assertIn('const contact = card?.facts.official_contact', block)
        self.assertIn("contactNames(contact?.name ?? '')", block)
        self.assertIn("contactPhones(contact?.phone ?? '')", block)
        self.assertIn("contact?.email?.trim() || null", block)
        for forbidden in ('hospital_relationship', 'customer_context', 'target_hospital', 'matching_product_capabilities'):
            self.assertNotIn(forbidden, block)

    def test_phone_and_email_actions_do_not_claim_contact_happened(self) -> None:
        render_start = self.source.index('{publicContact ? (')
        render_end = self.source.index('{draft ? (', render_start)
        block = self.source[render_start:render_end]
        self.assertIn('safeTelephoneHref(phone)', block)
        self.assertIn('safeEmailHref(publicContact.email)', block)
        self.assertIn('href={href}', block)
        self.assertIn('mailto:', self.source)
        self.assertNotIn('updateFollowup', block)
        self.assertNotIn("status: 'CONTACTED'", block)

    def test_public_contact_never_implies_private_relationship(self) -> None:
        self.assertIn('公告公开联系方式', self.source)
        self.assertIn('官方公开信息', self.source)
        self.assertIn('不代表你与联系人或医院存在私人关系', self.source)
        self.assertIn('safeTelephoneHref', self.source)
        self.assertIn('/[\\r\\n]/.test(email)', self.source)

    def test_drawer_explains_copy_and_contact_confirmation_are_separate(self) -> None:
        self.assertIn('实际联系后再确认写入跟进台账', self.source)
        self.assertIn('复制内容', self.source)
        self.assertIn('已联系，记入跟进', self.source)
        self.assertIn('onClick={() => void recordContacted()}', self.source)


if __name__ == "__main__":
    unittest.main()
