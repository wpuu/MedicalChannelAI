from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2]


class TargetHospitalContextTests(unittest.TestCase):
    def test_private_context_loads_target_hospitals_separately(self):
        source = (WEB_ROOT / 'api' / '_privateProfileContext.js').read_text(encoding='utf-8')
        self.assertIn('FROM private_target_hospitals', source)
        self.assertIn('AS targets', source)
        self.assertIn('targets: Array.isArray(row.targets) ? row.targets : []', source)
        self.assertIn('relationships: Array.isArray(row.relationships) ? row.relationships : []', source)
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

    def test_ai_contract_requires_confirmed_execution_context_for_resource_action(self):
        core = (WEB_ROOT / 'api' / 'ai' / '_analyzeCore.js').read_text(encoding='utf-8')
        contract = (WEB_ROOT / 'api' / 'ai' / '_decisionContract.js').read_text(encoding='utf-8')
        self.assertIn('target_hospital: hasTarget ? sanitizedTarget : null', core)
        self.assertIn('function hasConfirmedExecutionContext(context)', contract)
        self.assertIn('root.hospital_relationship', contract)
        self.assertIn('root.matching_product_capabilities', contract)
        self.assertIn("if (hasConfirmedExecutionContext(customerContext)) allowed.add('MATCH_CONFIRMED_RESOURCES')", contract)
        self.assertIn('不把重点关注对象当作已有关系', contract)
        self.assertNotIn("asObject(root.target_hospital)?.watched_by_customer === true) return true", contract)

    def test_trial_ai_keeps_target_focus_as_context_without_affecting_score(self):
        source = (WEB_ROOT / 'src' / 'services' / 'aiDecisionApi.ts').read_text(encoding='utf-8')
        self.assertIn('context.target_hospital ||', source)
        self.assertIn('const useLocalContext = !isApiMode', source)
        self.assertIn('const customerContext = useLocalContext ? customerContextPayload(card) : null', source)

    def test_detail_one_click_target_defaults_to_whole_hospital(self):
        source = (WEB_ROOT / 'src' / 'components' / 'opportunity' / 'OpportunityExecutionCard.tsx').read_text(encoding='utf-8')
        self.assertIn('const matchedTarget = useMemo(() => {', source)
        self.assertIn('{ hospital, department: null }', source)
        self.assertIn('加入重点关注（全院）', source)
        self.assertIn('加入后默认关注全院，可在“我的资源”中再细化重点科室。', source)
        self.assertIn("matchedTarget.department ? ` / ${matchedTarget.department}` : ' · 全院'", source)

    def test_detail_target_scope_matches_server_department_semantics(self):
        source = (WEB_ROOT / 'src' / 'components' / 'opportunity' / 'OpportunityExecutionCard.tsx').read_text(encoding='utf-8')
        self.assertIn('function targetScopeMatchesCard(', source)
        self.assertIn('if (!scopedDepartment) return true', source)
        self.assertIn('if (!opportunityDepartment) return false', source)
        self.assertIn('targetScopeMatchesCard(item.hospital, item.department, hospital, department)', source)

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
