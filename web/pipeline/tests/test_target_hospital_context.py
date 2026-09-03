from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class TargetHospitalContextTests(unittest.TestCase):
    def test_private_context_loads_target_hospitals_separately(self):
        source = (WEB_ROOT / 'api' / '_privateProfileContext.js').read_text(encoding='utf-8')
        self.assertIn('FROM private_target_hospitals', source)
        self.assertIn('targets: [...targets]', source)
        self.assertIn('target_hospital: matchingTarget', source)
        self.assertIn('context.target_hospital ||', source)

    def test_target_hospital_does_not_add_relationship_points(self):
        source = (WEB_ROOT / 'api' / '_privateProfileContext.js').read_text(encoding='utf-8')
        priority = source[source.index('export function privatePriorityPoints'):source.index('export async function minimalPrivateContextForOpportunity')]
        self.assertIn('context.hospital_relationship', priority)
        self.assertNotIn('context.target_hospital', priority)
        self.assertIn('contributes zero relationship points', priority)

    def test_target_focus_marks_personalized_match_without_score_inflation(self):
        source = (WEB_ROOT / 'api' / '_pilotOpportunity.js').read_text(encoding='utf-8')
        self.assertIn('const hasTargetFocus = Boolean(privateResult.context.target_hospital)', source)
        self.assertIn("privateTotal > 0 || hasTargetFocus ? 'MATCHED_PERSONALIZED'", source)
        self.assertIn('target_hospital:', source)

    def test_ai_prompt_explicitly_forbids_treating_target_as_relationship(self):
        core = (WEB_ROOT / 'api' / 'ai' / '_analyzeCore.js').read_text(encoding='utf-8')
        contract = (WEB_ROOT / 'api' / 'ai' / '_decisionContract.js').read_text(encoding='utf-8')
        self.assertIn('target_hospital: hasTarget ? sanitizedTarget : null', core)
        self.assertIn('用户重点关注医院', contract)
        self.assertIn('不代表已经认识院内人员', contract)
        self.assertIn('重点关注绝不能冒充已有关系', contract)

    def test_trial_ai_keeps_target_focus_as_context_without_affecting_score(self):
        source = (WEB_ROOT / 'src' / 'services' / 'aiDecisionApi.ts').read_text(encoding='utf-8')
        self.assertIn('context.target_hospital ||', source)
        self.assertIn('const useLocalContext = !isApiMode', source)
        self.assertIn('const customerContext = useLocalContext ? customerContextPayload(card) : null', source)

    def test_frontend_shows_target_and_relationship_separately(self):
        detail = (WEB_ROOT / 'src' / 'components' / 'opportunity' / 'CustomerContextCard.tsx').read_text(encoding='utf-8')
        today = (WEB_ROOT / 'src' / 'components' / 'today' / 'CustomerResourceBlock.tsx').read_text(encoding='utf-8')
        local = (WEB_ROOT / 'src' / 'services' / 'localCustomerProfile.ts').read_text(encoding='utf-8')
        self.assertIn('重点关注', detail)
        self.assertIn('不代表已有关系', detail)
        self.assertIn('医院关系', detail)
        self.assertIn('重点关注', today)
        self.assertIn('不代表已有医院关系', today)
        self.assertIn('当前不增加医院关系分', today)
        self.assertIn('targetForCard', local)
        self.assertIn('privatePoints > 0 || target', local)


if __name__ == '__main__':
    unittest.main()
