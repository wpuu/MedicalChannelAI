from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]
ACTION_CARD = WEB_ROOT / 'src' / 'components' / 'today' / 'ActionCard.tsx'
FACTS_CARD = WEB_ROOT / 'src' / 'components' / 'opportunity' / 'FactsCard.tsx'
POOL_PAGE = WEB_ROOT / 'src' / 'pages' / 'OpportunityPoolPage.tsx'


class PublicContactActionsTests(unittest.TestCase):
    def test_mobile_sales_surfaces_offer_tel_and_mailto_for_verified_public_contacts(self) -> None:
        for path in [ACTION_CARD, FACTS_CARD, POOL_PAGE]:
            source = path.read_text(encoding='utf-8')
            self.assertIn('function telHref(', source)
            self.assertIn('function mailtoHref(', source)
            self.assertIn('href={contactPhoneHref}', source)
            self.assertIn('href={contactEmailHref}', source)

    def test_multiple_public_phone_numbers_are_never_concatenated_into_one_dial_target(self) -> None:
        for path in [ACTION_CARD, FACTS_CARD, POOL_PAGE]:
            source = path.read_text(encoding='utf-8')
            self.assertIn("if (!raw || /[、,，;；/]/.test(raw)) return null", source)
            self.assertIn("const digits = raw.replace(/\\D/g, '')", source)
            self.assertIn("return `tel:${leadingPlus ? '+' : ''}${digits}`", source)

    def test_contact_shortcuts_do_not_auto_mutate_crm_contacted_status(self) -> None:
        action = ACTION_CARD.read_text(encoding='utf-8')
        detail = FACTS_CARD.read_text(encoding='utf-8')

        # Opening a dialer/mail client is not proof that a real conversation
        # happened. The explicit CRM action remains a separate button.
        self.assertIn('onContacted={onContacted}', action)
        self.assertIn('href={contactPhoneHref}', action)
        self.assertNotIn('onClick={onContacted}', action)
        self.assertIn('不会自动把商机标记为“已联系”', detail)


if __name__ == '__main__':
    unittest.main()
